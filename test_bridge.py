# SPDX-License-Identifier: MIT
import importlib.util, tempfile, unittest, zipfile, sys
from unittest.mock import patch
import subprocess
from pathlib import Path
BRIDGE = Path(__file__).resolve().parent / 'clone_bridge.py'
spec = importlib.util.spec_from_file_location('bridge', BRIDGE)
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class IdentityTests(unittest.TestCase):
    def test_preserves_update_identity(self):
        rows = bridge.identities('com.example.gallery', '相簿', 11000003, '11.0.0', 5)
        self.assertEqual([r['package'] for r in rows], ['com.example.galleryclone'+str(i) for i in range(1,6)])
        self.assertEqual([r['name'] for r in rows], ['相簿'+str(i) for i in range(1,6)])
        self.assertEqual([r['version_code'] for r in rows], list(range(11000004,11000009)))
        self.assertTrue(all(r['version_name']=='11.0.0' for r in rows))
        newer = bridge.identities('com.example.gallery', '相簿', 11000103, '11.0.1', 2)
        self.assertEqual(rows[0]['package'], newer[0]['package'])
        self.assertGreater(newer[0]['version_code'], rows[0]['version_code'])
    def test_other_packages_append_to_leaf(self):
        row = bridge.identities('com.example.gallery', '相簿', 43, '2.0', 1)[0]
        self.assertEqual(row['package'], 'com.example.galleryclone1')
        self.assertEqual(row['name'], '相簿1')
    def test_count_bounds(self):
        for n in [0,-1,100,1.5]:
            with self.assertRaises(ValueError): bridge.identities('a.b','App',1,'1',n)
    def test_rejects_non_apk_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'中文 含空格.apk'
            p.write_text('not a zip')
            with self.assertRaises(ValueError): bridge.validate_apk(p)
            p = Path(td)/'x.zip'
            with zipfile.ZipFile(p,'w') as z: z.writestr('AndroidManifest.xml','x')
            with self.assertRaises(ValueError): bridge.validate_apk(p)
    def test_accepts_chinese_path_with_spaces(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)/'中文 含空格.apk'
            with zipfile.ZipFile(p,'w') as z: z.writestr('AndroidManifest.xml','x')
            self.assertEqual(bridge.validate_apk(p), p.resolve())
    def test_signing_arguments_never_contain_password(self):
        args = bridge.secure_sign_args(['signer','sign','--ks-pass','pass:placeholder','--key-pass','pass:placeholder'],Path('/safe/password.txt'))
        self.assertNotIn('--key-pass', args)
        self.assertEqual(args[args.index('--ks-pass')+1], 'file:/safe/password.txt')
        self.assertFalse(any('pass:' in str(a) for a in args))
    def test_refuses_version_code_overflow(self):
        with self.assertRaises(ValueError): bridge.identities('a.b','App',2100000000,'1',1)

class LiteralLabelTests(unittest.TestCase):
    def test_badging_literal_label(self):
        badging = "package: name='com.example.gallery' versionCode='43' versionName='2.0'\napplication: label='Gallery' icon=''"
        with patch.object(bridge, 'run_tool', return_value=subprocess.CompletedProcess([],0,badging)):
            result = bridge.metadata(Path('/synthetic.apk'), {'aapt2':Path('/tool/aapt2')})
        self.assertEqual(result['name'], 'Gallery')

    def test_engine_reads_literal_label(self):
        engine_spec = importlib.util.spec_from_file_location('tested_engine',BRIDGE.parent/'apk_clone_maker.py')
        engine = importlib.util.module_from_spec(engine_spec)
        sys.modules[engine_spec.name] = engine
        engine_spec.loader.exec_module(engine)
        with tempfile.TemporaryDirectory() as td:
            project = Path(td)
            (project/'AndroidManifest.xml').write_text('<manifest><application android:label="Gallery &amp; Photos"/></manifest>')
            self.assertEqual(engine.parse_default_app_name(project),'Gallery & Photos')

if __name__ == '__main__': unittest.main()
