#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local JSON-lines bridge for the unchanged APK clone engine."""
import argparse, contextlib, fcntl, hashlib, importlib.util, io, json, os, re
import secrets, shutil, signal, subprocess, sys, tempfile, zipfile
from clone_profiles import rows_for, validate_profile, updated_profile, save_profile, merge_profiles
from datetime import datetime
from pathlib import Path
sys.dont_write_bytecode = True
HOME = Path(__file__).resolve().parent
OUT = sys.stdout

def event(kind, message='', **data):
    print(json.dumps(dict(event=kind, message=message, **data), ensure_ascii=False), file=OUT, flush=True)

def validate_apk(path):
    path = Path(path).expanduser().resolve()
    if path.suffix.lower() != '.apk' or not path.is_file():
        raise ValueError('請選擇存在的 .apk 檔案。')
    try:
        with zipfile.ZipFile(path) as archive:
            if 'AndroidManifest.xml' not in archive.namelist() or archive.testzip():
                raise ValueError('APK 內容不完整或已損壞。')
    except (zipfile.BadZipFile, OSError) as e:
        raise ValueError('無法讀取 APK：檔案不是完整的 APK。') from e
    return path

def identities(package, name, code, version, count):
    if type(count) is not int or not 1 <= count <= 99:
        raise ValueError('分身數量必須是 1 到 99 的整數。')
    if code < 1 or code + count > 2100000000:
        raise ValueError('版本代碼超出 Android 可用範圍。')
    return [dict(number=i, name=name+str(i),
                 package=package+'clone'+str(i),
                 version_code=code+i, version_name=version) for i in range(1,count+1)]

def secure_sign_args(command, password_file):
    command = [str(a) for a in command]
    if '--key-pass' in command:
        i = command.index('--key-pass'); del command[i:i+2]
    if '--ks-pass' in command:
        command[command.index('--ks-pass')+1] = 'file:'+str(password_file)
    return command

def run_tool(command, **kwargs):
    child = subprocess.Popen([str(a) for a in command], cwd=kwargs.get('cwd'),
                             text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                             start_new_session=True, env=kwargs.get("env"))
    try:
        output, _ = child.communicate()
    except BaseException:
        try: os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try: child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            try: os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            child.wait()
        raise
    result = subprocess.CompletedProcess(command,child.returncode,output)
    if kwargs.get('check', True) and result.returncode:
        # Commands and credentials are never included in diagnostics.
        raise RuntimeError(Path(str(command[0])).name+' 執行失敗：\n'+(result.stdout or '')[-6000:])
    return result

def load_tools():
    local = HOME/'.local-env/runtime'
    def project_path(value):
        p = Path(value).expanduser()
        return (p if p.is_absolute() else HOME/p).resolve()
    config_path = HOME/'tools.local.json'
    config = json.loads(config_path.read_text()) if config_path.is_file() else {}
    sdk_value = config.get('android_sdk') or os.environ.get('ANDROID_SDK_ROOT') or os.environ.get('ANDROID_HOME') or (str(local/'android-sdk') if (local/'android-sdk').is_dir() else None)
    if not sdk_value:
        raise ValueError('請先執行「安裝本機環境.command」，或設定 tools.local.json 的 android_sdk。')
    sdk = project_path(sdk_value)
    versions = [p for p in (sdk/'build-tools').iterdir() if p.is_dir()] if (sdk/'build-tools').is_dir() else []
    def version_key(p): return tuple(int(x) for x in re.findall(r'\d+',p.name))
    if config.get('build_tools_version'):
        bt = sdk/'build-tools'/config['build_tools_version']
    elif versions:
        bt = max(versions,key=version_key)
    else:
        raise ValueError('Android SDK 未安裝 Build Tools。')
    apktool_value = config.get('apktool') or os.environ.get('APKTOOL_PATH') or (str(local/'apktool.jar') if (local/'apktool.jar').is_file() else None) or shutil.which('apktool')
    if not apktool_value:
        jar = HOME/'apktool-cli-2.11.1.jar'
        if jar.is_file(): apktool_value = str(jar)
        else: raise ValueError('請安裝 apktool，或在 tools.local.json 指定官方 JAR 路徑。')
    tools = dict(apktool=project_path(apktool_value), sdk=sdk,
                 aapt2=bt/'aapt2', zipalign=bt/'zipalign', signer=bt/'lib/apksigner.jar')
    for name,path in tools.items():
        if not path.exists(): raise ValueError('缺少本機 Android 工具：'+name)
    java_home = config.get('java_home') or (str(local/'jdk/Contents/Home') if (local/'jdk/Contents/Home').is_dir() else None) or os.environ.get('JAVA_HOME')
    for name in ['java','keytool']:
        found = str(project_path(java_home)/'bin'/name) if java_home else shutil.which(name)
        if not found: raise ValueError('缺少本機工具：'+name)
        tools[name] = Path(found)
        if not tools[name].is_file(): raise ValueError('缺少本機工具：'+name)
    return tools

def metadata(apk, tools):
    text = run_tool([tools['aapt2'],'dump','badging',apk]).stdout
    match = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']*)'",text)
    label = re.search(r"(?m)^application-label:'(.*)'\r?$",text) or re.search(r"(?m)^application: label='(.*)' icon='",text)
    if not match: raise ValueError('無法讀取 APK 套件與版本。')
    return dict(package=match[1], code=int(match[2]), version=match[3], name=label[1] if label else match[1].rsplit('.',1)[-1])

def certificate(apk, tools):
    text = run_tool([tools['java'],'-jar',tools['signer'],'verify','--print-certs',apk]).stdout
    match = re.search(r'Signer #1 certificate SHA-256 digest: (\S+)',text)
    if not match: raise ValueError('無法確認 APK 簽章憑證。')
    return match[1]

def signing_identity(package, tools):
    private = HOME/'06-精靈私有簽章'
    private.mkdir(mode=0o700, exist_ok=True); private.chmod(0o700)
    key,password,alias = private/'local-clones.p12',private/'password.txt','local-clones'
    if key.exists() != password.exists():
        raise ValueError('一般 APK 的簽章資料不完整，請恢復 06-精靈私有簽章備份。')
    if not key.exists() and (HOME/"07-分身設定").exists() and any((HOME/"07-分身設定").glob("*.json")):
        raise ValueError("已有分身設定但原簽章遺失，不能改用新簽章。請找回06-精靈私有簽章。")
    if not key.exists():
        fd = os.open(password, os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
        with os.fdopen(fd,'w') as stream: stream.write(secrets.token_urlsafe(48)+'\n')
        try:
            run_tool([tools['keytool'],'-genkeypair','-keystore',key,'-storetype','PKCS12',
                      '-alias',alias,'-keyalg','RSA','-keysize','2048','-validity','10000',
                      '-storepass:file',password,'-dname','CN=Local APK Clones'])
            key.chmod(0o600)
        except BaseException:
            password.unlink(missing_ok=True); key.unlink(missing_ok=True); raise
    return key,password,alias

def signing_digest(key, password, alias, tools):
    if not key.is_file() or not password.is_file():
        raise ValueError("找不到原有簽章檔，不能改用新簽章。請保留或找回原簽章資料。")
    result=run_tool([tools['keytool'],'-exportcert','-rfc','-keystore',key,'-alias',alias,'-storepass:file',password]).stdout
    import base64
    pem=re.search(r'-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----',result,re.S)
    if not pem: raise ValueError("無法確認原簽章身分。")
    return hashlib.sha256(base64.b64decode(pem[1])).hexdigest()

def key_paths(profile):
    signing=profile['signing']
    def resolve(value):
        path=Path(value).expanduser()
        return (path if path.is_absolute() else HOME/path).resolve()
    return resolve(signing['keystore']),resolve(signing['password_file']),signing['alias']

def profile_for(base, tools, selected=None):
    folder=HOME/'07-分身設定'
    default=folder/(base['package']+'.json')
    path=Path(selected).expanduser().resolve() if selected else default
    if path.is_file():
        value=json.loads(path.read_text())
        if value.get('schema')==1:
            profile=validate_profile(value)
        elif 'clones' in value and 'base_package' in value:
            profile=import_summary(path,value,tools)
            path=folder/(profile['source_package']+'.json')
        else:raise ValueError("請選擇分身設定檔，或上次輸出中的clone-summary.json。")
    elif selected:raise ValueError("選擇的分身設定不存在。")
    else:
        key,password,alias=signing_identity(base['package'],tools)
        profile=dict(schema=1,source_package=base['package'],signing=dict(keystore=str(key.relative_to(HOME)),password_file=str(password.relative_to(HOME)),alias=alias),signer_sha256=signing_digest(key,password,alias,tools),slots={})
    if profile['source_package']!=base['package']:
        raise ValueError("這份分身設定屬於另一個App，已停止。請選擇同一原始App的更新檔，避免覆蓋錯誤的分身。")
    canonical=folder/(profile['source_package']+'.json')
    if canonical.is_file() and canonical.resolve()!=path.resolve():
        profile=merge_profiles(validate_profile(json.loads(canonical.read_text())),profile)
    elif canonical.is_file() and selected and value.get('schema')!=1:
        profile=merge_profiles(validate_profile(json.loads(canonical.read_text())),profile)
    path=canonical
    key,password,alias=key_paths(profile)
    actual=signing_digest(key,password,alias,tools)
    if actual!=profile['signer_sha256']:
        raise ValueError("這份簽章與原分身不一致，已停止製作；不會產生無法覆蓋的新簽章版本。")
    return path,profile,key,password,alias

def import_summary(path, summary, tools):
    # Old GUI runs use the persistent wizard key. Old terminal runs may have
    # generated a key next to clone-summary.json. Import only a verified match.
    reports=summary['clones']
    fingerprints=[];slots={}
    for row in reports:
        spec=row['spec']
        match=re.search(r'Signer #1 certificate SHA-256 digest: (\S+)',row.get('signature_summary',''))
        if not match:raise ValueError("舊輸出缺少簽章紀錄，不能猜測更新身分。")
        candidate=(path.parent/spec['output_apk']).resolve()
        if candidate.parent!=path.parent.resolve() or not candidate.is_file():
            raise ValueError("上次輸出的APK不完整，不能核對原更新身分；請選完整輸出資料夾。")
        if hashlib.sha256(candidate.read_bytes()).hexdigest()!=row.get('apk_sha256'):
            raise ValueError("上次輸出的APK與紀錄不符，已停止。")
        old=metadata(candidate,tools)
        if old!=dict(package=spec['package_name'],name=spec['app_name'],code=spec['version_code'],version=spec['version_name']):
            raise ValueError("上次分身的套件或版本與紀錄不符，已停止。")
        actual=certificate(candidate,tools)
        if actual!=match[1].lower():raise ValueError("上次分身的實際簽章與紀錄不符，已停止。")
        fingerprints.append(actual)
        slots[str(spec['number'])]=dict(package=spec['package_name'],name=spec['app_name'],last_version_code=spec['version_code'])
    if len(set(fingerprints))!=1:raise ValueError("舊分身使用不同簽章，請分開載入設定。")
    expected=fingerprints[0]
    key=HOME/'06-精靈私有簽章/local-clones.p12';password=key.parent/'password.txt';alias='local-clones'
    if not(key.is_file() and password.is_file() and signing_digest(key,password,alias,tools)==expected):
        oldkey=path.parent/'apk-clone-test.jks'
        if not oldkey.is_file():raise ValueError("找不到這批舊分身的原簽章；請找回原輸出中的簽章檔，不能用新簽章替代。")
        # Only the engine's documented default credential is attempted.
        env={**os.environ,'WIZARD_LEGACY_STORE_PASSWORD':'android'}
        text=run_tool([tools['keytool'],'-exportcert','-rfc','-keystore',oldkey,'-alias','apkclone','-storepass:env','WIZARD_LEGACY_STORE_PASSWORD'],env=env).stdout
        import base64
        pem=re.search(r'-----BEGIN CERTIFICATE-----(.*?)-----END CERTIFICATE-----',text,re.S)
        if not pem or hashlib.sha256(base64.b64decode(pem[1])).hexdigest()!=expected:raise ValueError("舊簽章與輸出不一致，已停止。")
        private=HOME/'06-精靈私有簽章/匯入';private.mkdir(parents=True,exist_ok=True,mode=0o700)
        key=private/(expected+'.jks');password=private/(expected+'.password');alias='apkclone'
        if key.exists() and hashlib.sha256(key.read_bytes()).digest()!=hashlib.sha256(oldkey.read_bytes()).digest():raise ValueError("已有不同的匯入簽章，請人工確認。")
        if not key.exists():
            shutil.copy2(oldkey,key);key.chmod(0o600)
        if not password.exists():
            fd=os.open(password,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'w') as stream:stream.write('android'+chr(10))
    value=dict(schema=1,source_package=summary['base_package'],signing=dict(keystore=str(key.relative_to(HOME)),password_file=str(password.relative_to(HOME)),alias=alias),signer_sha256=expected,slots=slots)
    return validate_profile(value)

class EngineMessages(io.TextIOBase):
    def write(self, value):
        for line in value.splitlines():
            line = line.strip()
            match = re.match(r'=== Clone (\d+): (.*?) / ', line)
            if match: event('progress','製作分身 '+match[1]+'：'+match[2])
            elif line.startswith('WARNING:'): event('progress',line)

        return len(value)
    def flush(self): pass

def build(apk, count, output_parent=None, start_number=1, names=None, profile_file=None):
    old_env={key:os.environ.get(key) for key in ('PATH','TMPDIR')}
    old_temp=tempfile.tempdir
    try:
        return _build(apk,count,output_parent,start_number,names,profile_file)
    finally:
        tempfile.tempdir=old_temp
        for key,value in old_env.items():
            if value is None:os.environ.pop(key,None)
            else:os.environ[key]=value

def _build(apk, count, output_parent=None, start_number=1, names=None, profile_file=None):
    apk = validate_apk(apk)
    cache = HOME/'03-精靈快取'
    cache.mkdir(exist_ok=True)
    with (cache/'build.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('另一個分身建置正在執行，請等它完成。')
        tools = load_tools()
        os.environ['PATH'] = str(tools['java'].parent)+os.pathsep+os.environ.get('PATH','')
        base = metadata(apk, tools)
        profile_path,profile,key,password,alias = profile_for(base,tools,profile_file)
        rows = rows_for(base,count,start_number,names,profile)
        pending_profile = updated_profile(profile,rows)
        parent = Path(output_parent).expanduser().resolve() if output_parent else HOME/'01-輸出'
        # Always create a new run folder; never replace released APKs.
        parent.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r'[/:\\\x00]','_',base['name'])[:70] or 'App'
        destination = parent/(stem+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        destination.mkdir(exist_ok=False)
        temp = cache/('temp-'+destination.name); temp.mkdir()
        plan = temp/'clone-plan.json';plan.write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        os.environ['TMPDIR'] = str(temp); tempfile.tempdir = str(temp)
        spec = importlib.util.spec_from_file_location('clone_engine', HOME/'apk_clone_maker.py')
        engine = importlib.util.module_from_spec(spec); sys.modules[spec.name]=engine; spec.loader.exec_module(engine)
        def secure_run(command, **kwargs):
            command = secure_sign_args(command,password)
            if str(command[0]) == str(tools['signer']):
                command = [str(tools['java']),'-jar',str(tools['signer']),*command[1:]]
            tool = Path(str(command[0])).name
            if tool == 'apktool' or '-jar' in command and str(tools['apktool']) in command:
                message = '讀取原 APK…' if 'd' in command else '重新打包分身…'
            elif tool == 'zipalign': message = '檢查 APK 對齊…' if '-c' in command else '整理 APK…'
            elif 'sign' in command: message = '套用分身簽章…'
            elif 'verify' in command: message = '確認分身簽章…'
            elif tool == 'aapt2': message = '檢查名稱、套件與版本…'
            else: message = '正在處理 APK…'
            event('progress',message)
            return run_tool(command,**kwargs)
        engine.run = secure_run
        # Existing engine remains untouched. Defaults are overwritten explicitly.
        argv = [str(HOME/'apk_clone_maker.py'),'--apk',str(apk),'--output-dir',str(destination),
                '--numbers',','.join(str(row['number']) for row in rows),
                '--clone-plan',str(plan),
                '--name-template','{base_name}{n}',
                '--package-template',base['package']+'clone{n}',
                '--version-name-template','{base_version_name}', '--filename-template','{name}-{base_version_name}.apk',
                '--apktool',str(tools['apktool']), '--android-sdk',str(tools['sdk']),
                '--aapt2',str(tools['aapt2']), '--zipalign',str(tools['zipalign']), '--apksigner',str(tools['signer']),
                '--keystore',str(key),'--ks-alias',alias]
        previous = sys.argv
        committed = False
        commit_started = False
        try:
            event('started','正在製作 '+str(count)+' 個分身', output=str(destination), base=base)
            sys.argv = argv
            with contextlib.redirect_stdout(EngineMessages()), contextlib.redirect_stderr(EngineMessages()):
                if engine.main(): raise RuntimeError('分身工具執行失敗。')
            summary = json.loads((destination/'clone-summary.json').read_text())
            if len(summary['clones']) != count: raise ValueError('分身數量不符。')
            for report,row in zip(summary['clones'],rows):
                p = destination/report['spec']['output_apk']
                result = metadata(p,tools)
                if result != dict(package=row['package'],name=row['name'],code=row['version_code'],version=row['version_name']):
                    raise ValueError('建置後的名稱、套件或版本不符。')
                if certificate(p,tools)!=profile['signer_sha256']:raise ValueError('成品簽章與原分身設定不符。')
                if report['warnings']: raise ValueError('APK 結構需要人工檢查：'+'; '.join(report['warnings']))
                if engine.sha256_file(p) != report['apk_sha256']: raise ValueError('APK 檔案校驗失敗。')
            (destination/'SHA256SUMS.txt').write_text(''.join(r['apk_sha256']+'  '+r['spec']['output_apk']+'\n' for r in summary['clones']))
            summary['profile_file']=str(profile_path)
            summary['signer_sha256']=profile['signer_sha256']
            summary['update_identity']='persistent per-slot package and signer; monotonically increasing versionCode'
            summary['bridge_validation'] = 'ZIP, alignment, metadata, signature; runtime not tested'
            (destination/'clone-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
            commit_started = True
            save_profile(profile_path,pending_profile)
            committed = True
            event('done','完成 '+str(count)+' 個分身',output=str(destination),clones=rows,profile=str(profile_path))
            return destination
        except BaseException as error:
            if commit_started and not committed:
                # Cancellation may land after replace() but before save_profile
                # returns. Re-read the commit rather than deleting its APKs.
                try:committed = json.loads(profile_path.read_text()) == pending_profile
                except (OSError, ValueError):
                    # Unable to prove the old state: retain verified outputs for recovery.
                    committed = True
            if committed:
                # The completed APKs and canonical settings remain a consistent pair
                # even if the UI pipe closes after the final commit.
                raise
            for p in destination.glob('*.apk'): p.unlink()
            (destination/'build-error.json').write_text(json.dumps(dict(error=str(error) or type(error).__name__,input_apk=str(apk),status='failed; candidate APKs removed'),ensure_ascii=False,indent=2)+'\n')
            raise
        finally:
            sys.argv = previous
            shutil.rmtree(destination/'work',ignore_errors=True)
            shutil.rmtree(temp,ignore_errors=True)

def main():
    def cancelled(signum, frame): raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,cancelled)
    parser = argparse.ArgumentParser()
    parser.add_argument('--apk',required=True,type=Path)
    parser.add_argument('--count',required=True,type=int)
    parser.add_argument('--output-parent',type=Path)
    parser.add_argument('--start-number',type=int,default=1)
    parser.add_argument('--names-json',default='[]')
    parser.add_argument('--profile',type=Path)
    args = parser.parse_args()
    try: build(args.apk,args.count,args.output_parent,args.start_number,json.loads(args.names_json),args.profile)
    except KeyboardInterrupt:
        event('error','建置已停止，暫存已清除。'); return 130
    except Exception as error:
        event('error',str(error)); return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
