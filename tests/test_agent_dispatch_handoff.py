import os, pathlib, subprocess, tempfile, unittest

HELPER=os.environ.get('HANDOFF_TEST_SOURCE','/home/yagamin/bin/agent-dispatch-handoff')
class SnapshotTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.temp.name); self.src=self.root/'src'; self.src.mkdir(); self.dest=self.root/'dest'; self.snap=self.root/'snap'
  self.git(self.src,'init','-q','-b','main'); self.git(self.src,'config','user.name','T'); self.git(self.src,'config','user.email','t@example.test'); (self.src/'a').write_text('base\n'); self.git(self.src,'add','a'); self.git(self.src,'commit','-qm','base'); self.head=self.git(self.src,'rev-parse','HEAD').strip(); self.git(self.root,'clone','-q',str(self.src),str(self.dest))
 def tearDown(self): self.temp.cleanup()
 def git(self,cwd,*a): return subprocess.run(['git','-C',str(cwd),*a],check=True,text=True,capture_output=True).stdout
 def run_helper(self,mode,path): return subprocess.run(['python3',HELPER,mode,str(path),str(self.snap),self.head],capture_output=True,text=True)
 def test_carries_staged_unstaged_untracked(self):
  (self.src/'a').write_text('staged\n'); self.git(self.src,'add','a'); (self.src/'a').write_text('later\n'); (self.src/'new file').write_text('new\n')
  self.assertEqual(self.run_helper('capture',self.src).returncode,0); self.assertEqual(self.run_helper('apply',self.dest).returncode,0); self.assertEqual((self.dest/'a').read_text(),'later\n'); self.assertEqual((self.dest/'new file').read_text(),'new\n'); self.assertEqual(self.run_helper('verify',self.src).returncode,0)
 def test_detects_original_change(self):
  (self.src/'a').write_text('one\n'); self.assertEqual(self.run_helper('capture',self.src).returncode,0); (self.src/'a').write_text('two\n'); self.assertNotEqual(self.run_helper('verify',self.src).returncode,0)
 def test_rejects_untracked_symlink(self):
  (self.src/'link').symlink_to('/etc/passwd'); self.assertNotEqual(self.run_helper('capture',self.src).returncode,0)
