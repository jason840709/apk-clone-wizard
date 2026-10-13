# SPDX-License-Identifier: MIT
import shutil
import hashlib
import io
import json
import tarfile
import zipfile
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent

class InstallerTests(unittest.TestCase):
    def project(self,td):
        p=Path(td)/'中文 含空格'; p.mkdir()
        for name in ['安裝本機環境.command','environment.lock.json']:
            if (ROOT/name).exists(): shutil.copy2(ROOT/name,p/name)
        shutil.copytree(ROOT/'tool-licenses',p/'tool-licenses')
        return p
    def test_installer_exists(self):
        self.assertTrue((ROOT/'安裝本機環境.command').is_file())
    def test_check_missing_environment_does_not_create_files(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.project(td)
            result=subprocess.run(['/bin/zsh',str(p/'安裝本機環境.command'),'--check'],capture_output=True,text=True)
            self.assertEqual(result.returncode,1)
            self.assertFalse((p/'.local-env').exists())
    def test_declining_sdk_terms_creates_no_environment(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.project(td)
            result=subprocess.run(['/bin/zsh',str(p/'安裝本機環境.command')],input='n\n',capture_output=True,text=True)
            self.assertIn('尚未同意',result.stdout+result.stderr)
            self.assertFalse((p/'.local-env').exists())


    def seed_synthetic_packages(self,p):
        # These are local test archives, never third-party binaries or real terms.
        cache=p/'.local-env/downloads';cache.mkdir(parents=True)
        arch=subprocess.check_output(['/usr/bin/uname','-m'],text=True).strip()
        def tar(name,paths):
            with tarfile.open(cache/name,'w:gz') as archive:
                for name,data in paths.items():
                    info=tarfile.TarInfo(name);info.mode=0o755;info.size=len(data)
                    archive.addfile(info,io.BytesIO(data))
        executable=b'#!/bin/sh\nexit 0\n'
        tar('python-'+arch+'.tar.gz',{'python/bin/python3':executable})
        tar('jdk-'+arch+'.tar.gz',{'test-jdk/Contents/Home/bin/java':executable,'test-jdk/Contents/Home/bin/keytool':executable})
        with zipfile.ZipFile(cache/'android-build-tools.zip','w') as archive:
            for name,data in {'aapt2':executable,'zipalign':executable,'lib/apksigner.jar':b'synthetic','NOTICE.txt':b'Synthetic test only'}.items():
                info=zipfile.ZipInfo('android-16/'+name);info.create_system=3;info.external_attr=0o100755<<16
                archive.writestr(info,data)
        (cache/'apktool.jar').write_bytes(b'Synthetic test only')
        lock=json.loads((p/'environment.lock.json').read_text())
        for key,name in [('python','python-'+arch+'.tar.gz'),('jdk','jdk-'+arch+'.tar.gz')]:
            lock['architectures'][arch][key]['sha256']=hashlib.sha256((cache/name).read_bytes()).hexdigest()
        for key,name in [('apktool','apktool.jar'),('android','android-build-tools.zip')]:
            lock[key]['sha256']=hashlib.sha256((cache/name).read_bytes()).hexdigest()
        license=p/'tool-licenses/android-sdk-license.txt'
        license.write_text('Synthetic test only: no real license agreement.\n')
        lock['android']['license_sha256']=hashlib.sha256(license.read_bytes()).hexdigest()
        (p/'environment.lock.json').write_text(json.dumps(lock))

    def test_install_transaction_and_relocation_with_synthetic_archives(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.project(td);self.seed_synthetic_packages(p)
            custom=p/'tools.local.json';custom.write_text('user configuration')
            result=subprocess.run(['/bin/zsh',str(p/'安裝本機環境.command')],input='我同意\n',capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(custom.read_text(),'user configuration')
            self.assertTrue((p/'.local-env/runtime/python/bin/python3').is_file())
            self.assertFalse((p/'.local-env/install.lock').exists())
            moved=Path(td)/'另一個 位置';p.rename(moved)
            result=subprocess.run(['/bin/zsh',str(moved/'安裝本機環境.command'),'--check'],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)


    def test_failed_reinstall_keeps_existing_environment(self):
        with tempfile.TemporaryDirectory() as td:
            p=self.project(td);self.seed_synthetic_packages(p)
            command=['/bin/zsh',str(p/'安裝本機環境.command')]
            first=subprocess.run(command,input='我同意\n',capture_output=True,text=True)
            self.assertEqual(first.returncode,0,first.stdout+first.stderr)
            marker=p/'.local-env/runtime/installed.lock.json';before=marker.read_bytes()
            arch=subprocess.check_output(['/usr/bin/uname','-m'],text=True).strip()
            archive=p/('.local-env/downloads/python-'+arch+'.tar.gz')
            archive.write_bytes(b'Not a tar archive')
            lock=json.loads((p/'environment.lock.json').read_text())
            lock['architectures'][arch]['python']['sha256']=hashlib.sha256(archive.read_bytes()).hexdigest()
            (p/'environment.lock.json').write_text(json.dumps(lock))
            result=subprocess.run(command,input='我同意\n',capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(marker.read_bytes(),before)
            self.assertFalse((p/'.local-env/install.lock').exists())
            self.assertEqual(list((p/'.local-env').glob('stage.*')),[])

if __name__=='__main__': unittest.main()
