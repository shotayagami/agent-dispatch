import json, pathlib, subprocess, os
import test_agent_dispatch_fallback as base

class PRFixFixture(base.DispatchFixture):
 def setUp(self):
  super().setUp()
  self.script.write_text(base.SOURCE)
  (self.home/'bin').mkdir(exist_ok=True); (self.home/'bin/agent-dispatch-handoff').write_bytes(pathlib.Path(os.environ.get('HANDOFF_TEST_SOURCE', '/home/yagamin/bin/agent-dispatch-handoff')).read_bytes()); (self.home/'bin/agent-dispatch-handoff').chmod(0o755)
  src=self.root/'source'; self.git('push','-q','origin','HEAD:refs/heads/feat/issue-906',cwd=src)
  self.head=self.git('rev-parse','HEAD',cwd=src).strip()
  mock=base.MOCK.replace("label='agent:review' if scenario.startswith('review') else ('agent:spec' if scenario.startswith('spec') else 'agent:impl')", "label='agent:pr-fix' if scenario.startswith('prfix') else ('agent:review' if scenario.startswith('review') else ('agent:spec' if scenario.startswith('spec') else 'agent:impl'))")
  mock=mock.replace("if url.endswith('/pulls/1'): print('{\"user\":{\"login\":\"tester\"},\"base\":{\"ref\":\"main\"}}'); sys.exit(0)", "if url.endswith('/pulls/1'):\n  print(json.dumps({'user':{'login': 'other' if scenario=='prfix_foreign' else 'tester'},'state':'open','head':{'ref':'feat/issue-906','sha':os.environ['PR_HEAD'],'repo':{'id':1}},'base':{'ref':'main','repo':{'id':1}}})); sys.exit(0)")
  (self.bin/'tea').write_text(mock); (self.bin/'tea').chmod(0o755)
  codex=mock.replace('import json, os, pathlib, sys','import json, os, pathlib, sys, subprocess').replace("if name=='codex':", "if name=='codex' and scenario=='prfix_src_race':\n (state.parent/'home/.worktrees/proj-issue-906/README.md').write_text('changed during work\\n')\nif name=='codex':").replace("if name=='codex':", "if name=='codex' and scenario=='prfix_race':\n subprocess.run(['git','--git-dir='+str(state.parent/'forge/gitea/proj.git'),'update-ref','refs/heads/feat/issue-906',os.environ['PR_HEAD']+'^'],check=True)\nif name=='codex':")
  codex=codex.replace("scenario in ('impl_fallback','impl_dirty','impl_ignored','impl_denied','impl_timeout','impl_unknown')","scenario in ('impl_fallback','impl_dirty','impl_ignored','impl_denied','impl_timeout','impl_unknown','prfix_partial')").replace("if scenario=='impl_dirty': pathlib.Path('partial.txt').write_text('keep me\\n')","if scenario=='impl_dirty': pathlib.Path('partial.txt').write_text('keep me\\n')\n  if scenario=='prfix_partial': pathlib.Path('README.md').write_text('interrupted edit\\n')")
  (self.bin/'codex').write_text(codex); (self.bin/'codex').chmod(0o755)
 def run_pr(self,scenario):
  env={'AGENT_GH_OWNER':'tester','AGENT_GITEA_WEB':'https://gitea.example.test','AGENT_GITEA_GIT':f'file://{self.root}/forge','HOME':str(self.home),'XDG_STATE_HOME':str(self.state),'PATH':str(self.bin)+':/usr/bin:/bin','MOCK_SCENARIO':scenario,'MOCK_STATE':str(self.state),'PR_HEAD':self.head,'GIT_AUTHOR_NAME':'Test','GIT_AUTHOR_EMAIL':'test@example.test','GIT_COMMITTER_NAME':'Test','GIT_COMMITTER_EMAIL':'test@example.test','GIT_CONFIG_NOSYSTEM':'1'}
  return subprocess.run([str(self.script)],cwd=self.home,env=env,text=True,capture_output=True,timeout=100)
class PRFixTest(PRFixFixture):
 def test_fix_existing_pr(self):
  r=self.run_pr('prfix_ok'); self.assertEqual(r.returncode,0,r.stderr); new=self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip(); self.assertNotEqual(new,self.head); self.git('merge-base','--is-ancestor',self.head,new,cwd=self.origin); self.assertIn('完了: codex (impl)',self.comments())
 def test_reject_foreign_pr(self):
  r=self.run_pr('prfix_foreign'); self.assertNotEqual(r.returncode,0); self.assertEqual(self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip(),self.head); self.assertNotIn('codex primary',self.calls())
 def test_reject_moved_head(self):
  self.head='a'*40; r=self.run_pr('prfix_ok'); self.assertNotEqual(r.returncode,0); self.assertNotIn('codex primary',self.calls())

 def test_race_does_not_overwrite_remote(self):
  parent=self.git('rev-parse',self.head+'^',cwd=self.origin).strip()
  r=self.run_pr('prfix_race'); self.assertNotEqual(r.returncode,0); self.assertEqual(self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip(),parent); self.assertIn('push に失敗',self.comments())

 def test_dirty_original_branch_is_preserved(self):
  cache=self.state/'agent-dispatch/repos/gitea_gitea_proj.git'; cache.parent.mkdir(parents=True)
  self.git('clone','--bare','-q',str(self.origin),str(cache),cwd=self.root)
  self.git('config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*',cwd=cache); self.git('fetch','-q','origin',cwd=cache)
  other=self.home/'.worktrees/proj-issue-906'; other.parent.mkdir(exist_ok=True); self.git('worktree','add','-q',str(other),'feat/issue-906',cwd=cache)
  (other/'README.md').write_text('unsaved work\n')
  r=self.run_pr('prfix_ok'); self.assertEqual(r.returncode,0,r.stderr); self.assertEqual((other/'README.md').read_text(),'unsaved work\n'); self.assertEqual(self.git('show','refs/heads/feat/issue-906:README.md',cwd=self.origin),'unsaved work\n')

 def test_source_change_stops_push(self):
  cache=self.state/'agent-dispatch/repos/gitea_gitea_proj.git'; cache.parent.mkdir(parents=True); self.git('clone','--bare','-q',str(self.origin),str(cache),cwd=self.root); self.git('config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*',cwd=cache); self.git('fetch','-q','origin',cwd=cache)
  other=self.home/'.worktrees/proj-issue-906'; other.parent.mkdir(exist_ok=True); self.git('worktree','add','-q',str(other),'feat/issue-906',cwd=cache); (other/'README.md').write_text('first change\n')
  r=self.run_pr('prfix_src_race'); self.assertNotEqual(r.returncode,0); self.assertEqual(self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip(),self.head); self.assertIn('引き継ぎ元が変更されました',self.comments())

 def test_resume_same_pr_worktree_preserves_partial_changes(self):
  cache=self.state/'agent-dispatch/repos/gitea_gitea_proj.git'; cache.parent.mkdir(parents=True)
  self.git('clone','--bare','-q',str(self.origin),str(cache),cwd=self.root)
  self.git('config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*',cwd=cache); self.git('fetch','-q','origin',cwd=cache)
  wt=self.home/'.worktrees/proj-pr-1'; wt.parent.mkdir(exist_ok=True)
  self.git('worktree','add','-q','--detach',str(wt),self.head,cwd=cache)
  (wt/'.agent-issue.md').write_text('# previous PR task\n')
  (wt/'README.md').write_text('partial implementation\n')
  (wt/'new-file.txt').write_text('untracked implementation\n')
  (wt/'scratch').mkdir(); (wt/'scratch/output').write_text('ignored output\n')
  r=self.run_pr('prfix_ok'); self.assertEqual(r.returncode,0,r.stderr)
  new=self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip()
  self.assertNotEqual(new,self.head); self.git('merge-base','--is-ancestor',self.head,new,cwd=self.origin)
  self.assertEqual(self.git('show',new+':README.md',cwd=self.origin),'partial implementation\n')
  self.assertEqual(self.git('show',new+':new-file.txt',cwd=self.origin),'untracked implementation\n')
  self.assertEqual((wt/'scratch/output').read_text(),'ignored output\n')
  snapshots=list((self.state/'agent-dispatch').glob('*.log.files/pr-resume/snapshot.json'))
  self.assertEqual(len(snapshots),1)
  archived=list((self.state/'agent-dispatch').glob('*.log.files/previous-agent-issue.md'))
  self.assertEqual(len(archived),1)

 def test_resume_rejects_stale_report_without_changing_worktree(self):
  cache=self.state/'agent-dispatch/repos/gitea_gitea_proj.git'; cache.parent.mkdir(parents=True)
  self.git('clone','--bare','-q',str(self.origin),str(cache),cwd=self.root)
  self.git('config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*',cwd=cache); self.git('fetch','-q','origin',cwd=cache)
  wt=self.home/'.worktrees/proj-pr-1'; wt.parent.mkdir(exist_ok=True)
  self.git('worktree','add','-q','--detach',str(wt),self.head,cwd=cache)
  (wt/'.agent-issue.md').write_text('# prior\n'); (wt/'.agent-impl-report.md').write_text('old report\n')
  (wt/'README.md').write_text('keep\n')
  r=self.run_pr('prfix_ok'); self.assertNotEqual(r.returncode,0)
  self.assertEqual((wt/'README.md').read_text(),'keep\n')
  self.assertEqual((wt/'.agent-impl-report.md').read_text(),'old report\n')
  self.assertNotIn('codex primary',self.calls())

 def test_retry_after_partial_quota_failure_resumes_worktree(self):
  first=self.run_pr('prfix_partial'); self.assertNotEqual(first.returncode,0)
  wt=self.home/'.worktrees/proj-pr-1'
  self.assertEqual((wt/'README.md').read_text(),'interrupted edit\n')
  second=self.run_pr('prfix_ok'); self.assertEqual(second.returncode,0,second.stdout+second.stderr+self.comments())
  new=self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip()
  self.assertEqual(self.git('show',new+':README.md',cwd=self.origin),'interrupted edit\n')
  self.assertIn('前回の途中変更',self.codex_args()[-1][self.codex_args()[-1].index('-o')+2])

 def test_successive_fixes_resume_after_dispatcher_archives_agent_files(self):
  first=self.run_pr('prfix_ok'); self.assertEqual(first.returncode,0,first.stderr)
  first_head=self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip()
  wt=self.home/'.worktrees/proj-pr-1'
  self.assertFalse((wt/'.agent-issue.md').exists())
  (wt/'followup.txt').write_text('second review follow-up\n')
  self.head=first_head
  second=self.run_pr('prfix_ok'); self.assertEqual(second.returncode,0,second.stdout+second.stderr+self.comments())
  second_head=self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip()
  self.assertNotEqual(second_head,first_head)
  self.git('merge-base','--is-ancestor',first_head,second_head,cwd=self.origin)

 def test_clean_stale_source_worktree_is_not_mistaken_for_wip(self):
  src=self.root/'source'
  old_head=self.head
  (src/'followup.txt').write_text('newer PR head\n')
  self.git('add','followup.txt',cwd=src); self.git('commit','-qm','advance PR head',cwd=src)
  self.head=self.git('rev-parse','HEAD',cwd=src).strip()
  self.git('push','-q','origin','HEAD:refs/heads/feat/issue-906',cwd=src)
  cache=self.state/'agent-dispatch/repos/gitea_gitea_proj.git'; cache.parent.mkdir(parents=True)
  self.git('clone','--bare','-q',str(self.origin),str(cache),cwd=self.root)
  self.git('config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*',cwd=cache); self.git('fetch','-q','origin',cwd=cache)
  source=self.home/'.worktrees/proj-issue-906'; source.parent.mkdir(exist_ok=True)
  self.git('worktree','add','-q','--detach',str(source),old_head,cwd=cache)
  self.git('branch','-q','-f','feat/issue-906',old_head,cwd=cache)
  self.git('switch','-q','feat/issue-906',cwd=source)
  wt=self.home/'.worktrees/proj-pr-1'; self.git('worktree','add','-q','--detach',str(wt),self.head,cwd=cache)
  (wt/'.agent-issue.md').write_text('# PR fix\n')
  (wt/'README.md').write_text('partial PR work\n')
  r=self.run_pr('prfix_ok'); self.assertEqual(r.returncode,0,r.stderr)
  new=self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip()
  self.assertEqual(self.git('show',new+':README.md',cwd=self.origin),'partial PR work\n')
  self.assertEqual(self.git('rev-parse','HEAD',cwd=source).strip(),old_head)
  self.assertEqual(self.git('status','--porcelain',cwd=source),'')

 def test_resume_rejects_worktree_at_different_head(self):
  cache=self.state/'agent-dispatch/repos/gitea_gitea_proj.git'; cache.parent.mkdir(parents=True)
  self.git('clone','--bare','-q',str(self.origin),str(cache),cwd=self.root)
  self.git('config','remote.origin.fetch','+refs/heads/*:refs/remotes/origin/*',cwd=cache); self.git('fetch','-q','origin',cwd=cache)
  wt=self.home/'.worktrees/proj-pr-1'; wt.parent.mkdir(exist_ok=True)
  self.git('worktree','add','-q','--detach',str(wt),'main',cwd=cache)
  (wt/'.agent-issue.md').write_text('# prior\n'); (wt/'README.md').write_text('keep\n')
  r=self.run_pr('prfix_ok'); self.assertNotEqual(r.returncode,0)
  self.assertEqual((wt/'README.md').read_text(),'keep\n')
  self.assertNotIn('codex primary',self.calls())

class GitHubPRFixTest(PRFixFixture):
 def setUp(self):
  super().setUp()
  s=self.script.read_text().replace('GITURL="git@github.com:$REPO.git"',f'GITURL="file://{self.root}/forge/$REPO.git"'); self.script.write_text(s)
  self.bin.joinpath('tea').write_text('#!/bin/sh\necho "[]"\n'); self.bin.joinpath('tea').chmod(0o755)
  gh='''#!/usr/bin/python3
import sys, json, os, pathlib
args=sys.argv[1:]; state=pathlib.Path(os.environ['MOCK_STATE'])
if args[0]=='search':
 label=args[args.index('--label')+1]
 print(json.dumps([{'repository':{'nameWithOwner':'gitea/proj'},'number':1,'url':'https://example.test/pr/1','title':'Test task','labels':[{'name':label}]}] if args[1]=='prs' and label=='agent:pr-fix' else [])); sys.exit(0)
if args[:2]==['api','user']: print('tester');sys.exit(0)
if args[0]=='api' and '-X' in args and 'DELETE' in args: sys.exit(0)
if args[0] in ('issue','pr') and args[1] in ('edit','comment'):
 if args[1]=='comment':
  path=pathlib.Path(args[args.index('--body-file')+1]); (state/'comments').open('a').write(path.read_text()+'\\n')
 sys.exit(0)
if args[:2]==['pr','view']:
 fields=args[args.index('--json')+1]
 if fields=='labels,state': print('OPEN agent:pr-fix')
 elif fields=='title,body,author,comments': print(json.dumps({'title':'Test task','body':'Fix review comments','author':{'login':'tester'},'comments':[]}))
 elif fields.startswith('author,'): print('tester OPEN feat/issue-906 '+os.environ['PR_HEAD']+' main false')
 elif fields.startswith('state,headRefName'): print('OPEN feat/issue-906 '+os.environ['PR_HEAD']+' main false')
 else: sys.exit(2)
 sys.exit(0)
sys.exit(2)
'''
  self.bin.joinpath('gh').write_text(gh); self.bin.joinpath('gh').chmod(0o755)
 def test_github_existing_pr(self):
  r=self.run_pr('prfix_ok'); self.assertEqual(r.returncode,0,r.stderr); new=self.git('rev-parse','refs/heads/feat/issue-906',cwd=self.origin).strip(); self.assertNotEqual(new,self.head); self.git('merge-base','--is-ancestor',self.head,new,cwd=self.origin)
