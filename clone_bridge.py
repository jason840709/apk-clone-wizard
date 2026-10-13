#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Local JSON-lines bridge for the unchanged APK clone engine."""
import argparse, contextlib, fcntl, hashlib, importlib.util, io, json, os, re
import secrets, shutil, signal, subprocess, sys, tempfile, zipfile
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
                             start_new_session=True)
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
    label = re.search(r"application-label:'(.*?)'",text) or re.search(r"application: label='(.*?)'",text)
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

class EngineMessages(io.TextIOBase):
    def write(self, value):
        for line in value.splitlines():
            line = line.strip()
            match = re.match(r'=== Clone (\d+): (.*?) / ', line)
            if match: event('progress','製作分身 '+match[1]+'：'+match[2])
            elif line.startswith('WARNING:'): event('progress',line)

        return len(value)
    def flush(self): pass

def build(apk, count, output_parent=None):
    apk = validate_apk(apk)
    cache = HOME/'03-精靈快取'
    cache.mkdir(exist_ok=True)
    with (cache/'build.lock').open('a') as lock:
        try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError: raise ValueError('另一個分身建置正在執行，請等它完成。')
        tools = load_tools()
        os.environ['PATH'] = str(tools['java'].parent)+os.pathsep+os.environ.get('PATH','')
        base = metadata(apk, tools)
        rows = identities(base['package'],base['name'],base['code'],base['version'],count)
        parent = Path(output_parent).expanduser().resolve() if output_parent else HOME/'01-輸出'
        # Always create a new run folder; never replace released APKs.
        parent.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r'[/:\\\x00]','_',base['name'])[:70] or 'App'
        destination = parent/(stem+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        destination.mkdir(exist_ok=False)
        key,password,alias = signing_identity(base['package'], tools)
        temp = cache/('temp-'+destination.name); temp.mkdir()
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
                '--numbers',','.join(str(i) for i in range(1,count+1)),
                '--name-template','{base_name}{n}',
                '--package-template',base['package']+'clone{n}',
                '--version-name-template','{base_version_name}', '--filename-template','{name}-{base_version_name}.apk',
                '--apktool',str(tools['apktool']), '--android-sdk',str(tools['sdk']),
                '--aapt2',str(tools['aapt2']), '--zipalign',str(tools['zipalign']), '--apksigner',str(tools['signer']),
                '--keystore',str(key),'--ks-alias',alias]
        previous = sys.argv
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
                if report['warnings']: raise ValueError('APK 結構需要人工檢查：'+'; '.join(report['warnings']))
                if engine.sha256_file(p) != report['apk_sha256']: raise ValueError('APK 檔案校驗失敗。')
            (destination/'SHA256SUMS.txt').write_text(''.join(r['apk_sha256']+'  '+r['spec']['output_apk']+'\n' for r in summary['clones']))
            summary['bridge_validation'] = 'ZIP, alignment, metadata, signature; runtime not tested'
            (destination/'clone-summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
            event('done','完成 '+str(count)+' 個分身',output=str(destination),clones=rows)
            return destination
        except BaseException as error:
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
    args = parser.parse_args()
    try: build(args.apk,args.count,args.output_parent)
    except KeyboardInterrupt:
        event('error','建置已停止，暫存已清除。'); return 130
    except Exception as error:
        event('error',str(error)); return 1
    return 0

if __name__ == '__main__': raise SystemExit(main())
