# SPDX-License-Identifier: MIT
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('local_bridge',Path(__file__).parent/'clone_bridge.py')
bridge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bridge)

class LocalEnvironmentTests(unittest.TestCase):
    def fixture(self, root):
        env = root/'.local-env/runtime'
        for rel in ['android-sdk/build-tools/36.0.0/aapt2','android-sdk/build-tools/36.0.0/zipalign',
                    'android-sdk/build-tools/36.0.0/lib/apksigner.jar','apktool.jar',
                    'jdk/Contents/Home/bin/java','jdk/Contents/Home/bin/keytool']:
            p=env/rel; p.parent.mkdir(parents=True,exist_ok=True); p.touch()
        return env

    def test_project_tools_work_without_system_environment(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve(); env=self.fixture(root)
            with patch.object(bridge,'HOME',root),patch.dict(os.environ,{'PATH':''},clear=True):
                tools=bridge.load_tools()
            self.assertEqual(tools['sdk'],env/'android-sdk')
            self.assertEqual(tools['java'],env/'jdk/Contents/Home/bin/java')
            self.assertEqual(tools['apktool'],env/'apktool.jar')

    def test_relative_configuration_is_resolved_against_project(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td).resolve(); env=self.fixture(root)
            (root/'tools.local.json').write_text(json.dumps({'android_sdk':'.local-env/runtime/android-sdk','apktool':'.local-env/runtime/apktool.jar','java_home':'.local-env/runtime/jdk/Contents/Home'}))
            with patch.object(bridge,'HOME',root),patch.dict(os.environ,{'PATH':''},clear=True):
                tools=bridge.load_tools()
            self.assertEqual(tools['sdk'],env/'android-sdk')
            self.assertEqual(tools['java'],env/'jdk/Contents/Home/bin/java')

    def test_missing_local_environment_has_actionable_message(self):
        with tempfile.TemporaryDirectory() as td:
            with patch.object(bridge,'HOME',Path(td)),patch.dict(os.environ,{'PATH':''},clear=True):
                with self.assertRaisesRegex(ValueError,'安裝本機環境.command'):
                    bridge.load_tools()

if __name__=='__main__': unittest.main()
