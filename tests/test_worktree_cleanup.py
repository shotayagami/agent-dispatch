import importlib.machinery, importlib.util, os, pathlib, subprocess, sys, tempfile, unittest
from unittest.mock import patch
loader=importlib.machinery.SourceFileLoader('worktree_cleanup','/home/yagamin/bin/worktree-cleanup')
spec=importlib.util.spec_from_loader(loader.name,loader); m=importlib.util.module_from_spec(spec); loader.exec_module(m)
class CleanupTest(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(); self.base=pathlib.Path(self.temp.name); self.repo=self.base/'repo';self.repo.mkdir();self.root=self.base/'worktrees';self.root.mkdir();self.target=self.root/'feature';self.backups=self.base/'backups';m.ROOT=self.root;m.BACKUPS=self.backups
  self.git('init','-q','-b','main');self.git('config','user.name','Test');self.git('config','user.email','test@example.test');(self.repo/'tracked').write_text('hello\n');(self.repo/'.gitignore').write_text('.yomiyasu/\nnode_modules/\n');self.git('add','.');self.git('commit','-qm','initial');self.git('worktree','add','-qb','feature',str(self.target))
 def tearDown(self):self.temp.cleanup()
 def git(self,*a):subprocess.run(['git','-C',str(self.repo),*a],check=True,capture_output=True)
 def call(self,*args):
  with patch.object(m,'merged_pr'),patch.object(sys,'argv',['worktree-cleanup',str(self.target),'--pr','https://github.com/o/r/pull/1',*args]):return m.main()
 def test_backup_and_remove(self):
  d=self.target/'.yomiyasu';d.mkdir();(d/'input').write_text('retain this\n');self.assertEqual(self.call(),0);self.assertTrue(self.target.exists());self.assertEqual(self.call('--apply'),0);self.assertFalse(self.target.exists());self.assertEqual(len(list(self.backups.glob('*.tar'))),1);self.assertTrue((self.repo/'.git/refs/heads/feature').exists())
 def test_modified_untracked_ignored_are_retained(self):
  (self.target/'tracked').write_text('change');self.assertEqual(self.call('--apply'),1);self.assertTrue(self.target.exists());(self.target/'tracked').write_text('hello\n');(self.target/'extra').write_text('data');self.assertEqual(self.call('--apply'),1);(self.target/'extra').unlink();(self.target/'node_modules').mkdir();(self.target/'node_modules'/'x').write_text('data');self.assertEqual(self.call('--apply'),1);self.assertTrue(self.target.exists())
 def test_open_file_retained(self):
  with open(self.target/'tracked') as f:self.assertEqual(self.call('--apply'),1);self.assertTrue(self.target.exists())
 def test_unmerged_rejected(self):
  with patch.object(m,'merged_pr',side_effect=RuntimeError('PR is not merged')),patch.object(sys,'argv',['worktree-cleanup',str(self.target),'--pr','https://github.com/o/r/pull/1','--apply']):self.assertEqual(m.main(),1)
  self.assertTrue(self.target.exists())
 def test_origin_parser(self):
  self.assertEqual(m.origin_identity('git@github.com:o/r.git'),('github.com','o','r'));self.assertEqual(m.origin_identity('https://gitea.example/o/r.git'),('gitea.example','o','r'))
if __name__=='__main__':unittest.main()
