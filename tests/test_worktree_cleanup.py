import importlib.machinery, importlib.util, os, pathlib, subprocess, sys, tempfile, unittest
from unittest.mock import patch
loader=importlib.machinery.SourceFileLoader('worktree_cleanup',str(pathlib.Path(__file__).resolve().parents[1] / 'bin' / 'worktree-cleanup'))
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
 def env(self,text):
  f=self.base/'env';f.write_text(text);host=patch.object(m,'GITEA_TOKEN_HOST','gitea.example.test');host.start();self.addCleanup(host.stop);return patch.object(m,'ENV_FILE',f)
 def test_gitea_token_only_for_its_host(self):
  with self.env('A=1\nexport GITEA_TOKEN=old\nGITEA_API_KEY="tok-1.x" # note\n'):
   self.assertEqual(m.gitea_token(m.GITEA_TOKEN_HOST),'tok-1.x');self.assertIsNone(m.gitea_token('other.example.test'));self.assertIsNone(m.gitea_token('github.com'))
 def test_gitea_token_absent_or_odd_value(self):
  with self.env('GITEA_TOKEN=old\n'):self.assertIsNone(m.gitea_token(m.GITEA_TOKEN_HOST))
  with self.env('GITEA_API_KEY=a b"c\n'):self.assertIsNone(m.gitea_token(m.GITEA_TOKEN_HOST))
  with patch.object(m,'ENV_FILE',self.base/'missing'):self.assertIsNone(m.gitea_token(m.GITEA_TOKEN_HOST))
 def gitea_call(self,env_text):
  pr='{"merged_at":"t","state":"closed","head":{"sha":"abc"},"base":{"ref":"main","repo":{"name":"r","owner":{"login":"o"}}}}'
  calls=[];fake=lambda a,**k:(calls.append((a,k)),subprocess.CompletedProcess(a,0,pr,''))[1]
  with self.env(env_text),patch.object(m,'git',return_value='https://%s/o/r.git'%m.GITEA_TOKEN_HOST),patch.object(m.subprocess,'run',fake),patch.object(m,'run',lambda a,cwd=None:fake(a)):
   m.merged_pr(self.target,'https://%s/o/r/pulls/1'%m.GITEA_TOKEN_HOST,'abc')
  return calls[0]
 def test_gitea_token_goes_via_stdin_not_argv(self):
  a,k=self.gitea_call('GITEA_API_KEY=secrettok\n')
  self.assertNotIn('secrettok',' '.join(a));self.assertNotIn('--netrc',a);self.assertIn('Authorization: token secrettok',k['input'])
 def test_gitea_falls_back_to_netrc_without_token(self):
  a,k=self.gitea_call('OTHER=1\n')
 def test_no_token_host_configured_uses_netrc_only(self):
  with self.env('GITEA_API_KEY=tok\n'),patch.object(m,'GITEA_TOKEN_HOST',''):self.assertIsNone(m.gitea_token('gitea.example.test'));self.assertIsNone(m.gitea_token(''))
if __name__=='__main__':unittest.main()
