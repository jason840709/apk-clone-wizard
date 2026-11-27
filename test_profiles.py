import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import clone_profiles as policy
import clone_bridge as bridge
class Profiles(unittest.TestCase):
 def base(self,code=120,name="App"):return dict(package="org.example.gallery",name=name,code=code,version="13")
 def profile(self):return dict(schema=1,source_package="org.example.gallery",signing=dict(keystore="key.p12",password_file="password.txt",alias="a"),signer_sha256="a"*64,slots={})
 def test_name_change_preserves_identity_and_slot_codes(self):
  old=policy.rows_for(self.base(),2,names=["漫畫","照片"],profile=self.profile());saved=policy.updated_profile(self.profile(),old)
  new=policy.rows_for(self.base(100,"Changed original label"),2,names=["O'Brien & {週刊} 50%","相片"],profile=saved)
  self.assertEqual([r["package"] for r in old],[r["package"] for r in new]);self.assertEqual([r["version_code"]+1 for r in old],[r["version_code"] for r in new]);self.assertEqual(new[0]["name"],"O'Brien & {週刊} 50%")
 def test_slot2_update_keeps_slot1(self):
  saved=policy.updated_profile(self.profile(),policy.rows_for(self.base(),2,profile=self.profile()))
  row=policy.rows_for(self.base(130),1,2,["New2"],saved)[0]
  updated=policy.updated_profile(saved,[row]);self.assertEqual(saved["slots"]["1"],updated["slots"]["1"]);self.assertEqual(row["package"],saved["slots"]["2"]["package"])
 def test_old_partial_snapshot_cannot_drop_or_downgrade(self):
  current=policy.updated_profile(self.profile(),policy.rows_for(self.base(200),2,profile=self.profile()))
  partial=policy.updated_profile(self.profile(),policy.rows_for(self.base(100),1,2,["Old"],self.profile()))
  merged=policy.merge_profiles(current,partial);self.assertEqual(merged,current)
 def test_merge_rejects_changed_signer_source_or_slot(self):
  current=policy.updated_profile(self.profile(),policy.rows_for(self.base(),2,profile=self.profile()))
  for field in ["signer","source","package"]:
   other=json.loads(json.dumps(current))
   if field=="signer":other["signer_sha256"]="b"*64
   elif field=="source":other["source_package"]="org.other.app"
   else:other["slots"]["1"]["package"]="org.other.clone1"
   with self.assertRaises(ValueError):policy.merge_profiles(current,other)
 def test_invalid_range_names_and_overflow(self):
  for count,start,names in [(2,99,[]),(0,1,[]),(2,1,["only one"]),(1,1,["\n"]),(1,1,["bad\x00name"])]:
   with self.assertRaises(ValueError):policy.rows_for(self.base(),count,start,names,self.profile())
  with self.assertRaises(ValueError):policy.rows_for(self.base(2100000000),1,profile=self.profile())
 def test_settings_write_failure_keeps_previous_bytes(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"profile.json";policy.save_profile(p,self.profile());old=p.read_bytes()
   changed=policy.updated_profile(self.profile(),policy.rows_for(self.base(),1,profile=self.profile()))
   with patch.object(policy.os,"replace",side_effect=OSError("synthetic failure")):
    with self.assertRaises(OSError):policy.save_profile(p,changed)
   self.assertEqual(old,p.read_bytes());self.assertEqual([x.name for x in p.parent.iterdir()],["profile.json"])
 def test_complete_name_with_apostrophe_from_aapt(self):
  import subprocess
  label="O'Brien & {漫畫} 50%"
  for output in ["application-label:'"+label+"'\n","application: label='"+label+"' icon=''\n"]:
   with patch.object(bridge,"run_tool",return_value=subprocess.CompletedProcess([],0,"package: name='org.example.gallery' versionCode='12' versionName='13'\n"+output)):
    self.assertEqual(bridge.metadata(Path("any.apk"),{"aapt2":Path("aapt2")})["name"],label)
class SigningSafety(unittest.TestCase):
 def value(self):return dict(schema=1,source_package="org.example.gallery",signing=dict(keystore="lost.p12",password_file="lost-password.txt",alias="local-clones"),signer_sha256="a"*64,slots={})
 def base(self):return dict(package="org.example.gallery",name="App",code=13,version="13")
 def test_missing_key_does_not_generate_a_replacement(self):
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);folder=home/"07-分身設定";folder.mkdir();profile=folder/"org.example.gallery.json";policy.save_profile(profile,self.value());before=profile.read_bytes()
   with patch.object(bridge,"HOME",home),patch.object(bridge,"signing_identity") as generate:
    with self.assertRaises(ValueError):bridge.profile_for(self.base(),{})
    generate.assert_not_called()
   self.assertEqual(before,profile.read_bytes());self.assertFalse((home/"06-精靈私有簽章").exists())
 def test_changed_signer_is_rejected_before_build(self):
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);folder=home/"07-分身設定";folder.mkdir();profile=folder/"org.example.gallery.json";policy.save_profile(profile,self.value())
   with patch.object(bridge,"HOME",home),patch.object(bridge,"signing_digest",return_value="b"*64):
    with self.assertRaises(ValueError):bridge.profile_for(self.base(),{})
 def test_wrong_source_profile_is_rejected(self):
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);selected=home/"chosen.json";other=self.value();other["source_package"]="org.other.app";policy.save_profile(selected,other)
   with patch.object(bridge,"HOME",home),patch.object(bridge,"signing_digest") as digest:
    with self.assertRaises(ValueError):bridge.profile_for(self.base(),{},selected)
    digest.assert_not_called()
class CommitFaults(unittest.TestCase):
 def exercise(self,after_commit):
  import zipfile,hashlib
  with tempfile.TemporaryDirectory() as d:
   home=Path(d);base=home/"input.apk"
   with zipfile.ZipFile(base,"w") as z:z.writestr("AndroidManifest.xml","synthetic")
   profile=Profiles().profile();profile=policy.updated_profile(profile,policy.rows_for(dict(package="org.example.gallery",name="App",code=10,version="10"),1,profile=profile));file=home/"07-分身設定/org.example.gallery.json";policy.save_profile(file,profile);before=file.read_bytes()
   engine=home/"apk_clone_maker.py";engine.write_text("import sys,json,hashlib\nfrom pathlib import Path\ndef sha256_file(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()\ndef main():\n a=sys.argv;out=Path(a[a.index('--output-dir')+1]);row=json.loads(Path(a[a.index('--clone-plan')+1]).read_text())[0];p=out/'fixture.apk';p.write_bytes(b'synthetic result');(out/'clone-summary.json').write_text(json.dumps({'clones':[{'spec':{'number':row['number'],'output_apk':'fixture.apk'},'warnings':[],'apk_sha256':sha256_file(p)}]}));return 0\n")
   tools={k:Path('/synthetic/'+k) for k in ['java','apktool','sdk','aapt2','zipalign','signer']}
   base_meta=dict(package="org.example.gallery",name="App",code=13,version="13");expected=dict(package="org.example.galleryclone1",name="New",code=14,version="13")
   real=Path.write_text
   def write(path,value,*args,**kwargs):
    if not after_commit and path.name=='clone-summary.json' and 'bridge_validation' in value:raise OSError("synthetic final summary failure")
    return real(path,value,*args,**kwargs)
   real_save=bridge.save_profile
   def interrupted_save(path,value):
    real_save(path,value)
    if after_commit=="interrupt":raise KeyboardInterrupt("after atomic replace")
   def event(kind,*args,**kwargs):
    if after_commit is True and kind=='done':raise BrokenPipeError("synthetic closed UI pipe")
   from contextlib import ExitStack
   with ExitStack() as stack:
    for object,name,value in [(bridge,'HOME',home),(bridge,'load_tools',lambda:tools),(bridge,'profile_for',lambda *a:(file,profile,home/'key',home/'password','alias')),(bridge,'metadata',lambda apk,tools:base_meta if apk==base else expected),(bridge,'certificate',lambda *a:'a'*64),(bridge,'event',event),(bridge,'save_profile',interrupted_save),(Path,'write_text',write)]:stack.enter_context(patch.object(object,name,value))
    with self.assertRaises((OSError,BrokenPipeError,KeyboardInterrupt)):bridge.build(base,1,names=['New'])
   files=list((home/'01-輸出').glob('*/fixture.apk'))
   if after_commit:
    self.assertEqual(len(files),1);self.assertEqual(json.loads(file.read_text())['slots']['1']['last_version_code'],14)
   else:
    self.assertEqual(files,[]);self.assertEqual(file.read_bytes(),before)
 def test_interrupt_after_replace_keeps_completed_apks(self):self.exercise("interrupt")
 def test_final_summary_failure_keeps_previous_settings(self):self.exercise(False)
 def test_closed_ui_after_commit_preserves_complete_pair(self):self.exercise(True)
if __name__=="__main__":unittest.main()
