import json, os, pathlib, subprocess, tempfile, unittest

SOURCE = pathlib.Path(os.environ.get('AGENT_DISPATCH_TEST_SOURCE', pathlib.Path(__file__).resolve().parents[1] / 'bin' / 'agent-dispatch')).read_text()
MOCK = r'''#!/usr/bin/python3
import json, os, pathlib, sys
name=pathlib.Path(sys.argv[0]).name
args=sys.argv[1:]
scenario=os.environ['MOCK_SCENARIO']
state=pathlib.Path(os.environ['MOCK_STATE'])
with (state/'calls').open('a') as f: f.write(name+' '+('readonly' if '--ignore-user-config' in args else 'primary')+'\n')
if name=='gh':
 print('[]'); sys.exit(0)
if name=='agent-notify': sys.exit(0)
if name=='tea':
 if 'comment' in args:
  with (state/'comments').open('a') as f: f.write(args[-1]+'\n\x1e\n')
  sys.exit(0)
 if 'edit' in args: sys.exit(0)
 url=next((a for a in args if a.startswith('/repos/') or a=='/user'),'')
 label='agent:review' if scenario.startswith('review') else ('agent:spec' if scenario.startswith('spec') else 'agent:impl')
 if url.startswith('/repos/issues/search'):
  match=('labels='+label) in url
  print(json.dumps([{'repository':{'full_name':'gitea/proj'},'number':1,'title':'Test task','labels':[{'name':label}]}] if match else [])); sys.exit(0)
 if url=='/user': print('{"login":"tester"}'); sys.exit(0)
 if url.endswith('/issues/1/comments'): print('[]'); sys.exit(0)
 if url.endswith('/issues/1'): print(json.dumps({'state':'open','labels':[{'name':label}],'user':{'login':'tester'},'title':'Test task','body':'## 仕様\nImplement the issue.'})); sys.exit(0)
 if url.endswith('/pulls/1'): print('{"user":{"login":"tester"},"base":{"ref":"main"}}'); sys.exit(0)
 if url.endswith('/pulls'): print('{"number":45}'); sys.exit(0)
 sys.exit(2)
if name=='claude':
 with (state/'claude_args.jsonl').open('a') as f: f.write(json.dumps(args)+'\n')
 if scenario.startswith('spec') or scenario.startswith('review') or scenario=='impl_primary':
  if scenario=='spec_primary':
   pathlib.Path('.agent-spec-comment.md').write_text('## 仕様\n- 決定: テスト\n')
   print('{"type":"result","is_error":false,"result":"done"}'); sys.exit(0)
  if scenario=='spec_decision':
   pathlib.Path('.agent-spec-comment.md').write_text('## 仕様\n- 決定: テスト\n- 次の担当: 人\n\n## 判断待ち\n- 操作: 選ぶ\n')
   print('{"type":"result","is_error":false,"result":"done"}'); sys.exit(0)
  if scenario=='spec_denied':
   print(json.dumps({'type':'result','is_error':True,'result':'approval rejected'})); sys.exit(1)
  if scenario=='spec_partial': pathlib.Path('.agent-spec-comment.md').write_text('partial\n')
  if scenario=='spec_dirty': pathlib.Path('partial.txt').write_text('changed\n')
  if scenario=='review_success':
   pathlib.Path('.agent-review.md').write_text('## レビュー\n判定: 問題なし\n')
   print('{"type":"result","is_error":false,"result":"done"}'); sys.exit(0)
  if scenario=='review_partial': pathlib.Path('.agent-review.md').write_text('partial\n')
  if scenario=='review_zero_quota':
   print(json.dumps({'type':'result','is_error':False,'result':"You've hit your limit"})); sys.exit(0)
  if scenario=='review_weekly_quota':
   print(json.dumps({'type':'result','subtype':'success','is_error':True,'result':"You've hit your weekly limit · resets 8am (Asia/Tokyo)"})); sys.exit(1)
  print(json.dumps({'type':'result','is_error':True,'result':"You've hit your limit"})); sys.exit(1)
 pathlib.Path('feature.txt').write_text('implemented by claude\n')
 pathlib.Path('.agent-impl-report.md').write_text('## 実装の報告\n- 検証: 未実行\n')
 print('{"type":"result","is_error":false,"result":"done"}'); sys.exit(0)
if name=='codex':
 readonly='--ignore-user-config' in args
 with (state/'codex_args.jsonl').open('a') as f: f.write(json.dumps(args)+'\n')
 if readonly and scenario in ('spec_luna_unavailable','spec_both_fail') and '-m' in args and args[args.index('-m')+1]=='gpt-6-luna':
  print(json.dumps({'type':'turn.failed','error':{'message':'usage_limit_reached'}})); sys.exit(1)
 if readonly and scenario=='spec_denied':
  print(json.dumps({'type':'turn.failed','error':{'message':'approval rejected'}})); sys.exit(1)
 if readonly and scenario=='spec_partial':
  pathlib.Path('.agent-spec-comment.md').write_text('partial\n'); print(json.dumps({'type':'turn.failed','error':{'message':'usage_limit_reached'}})); sys.exit(1)
 if readonly and scenario=='spec_dirty':
  pathlib.Path('partial.txt').write_text('changed\n'); print(json.dumps({'type':'turn.failed','error':{'message':'usage_limit_reached'}})); sys.exit(1)
 if readonly and scenario=='spec_both_fail':
  print(json.dumps({'type':'turn.failed','error':{'message':'usage_limit_reached'}})); sys.exit(1)
 if not readonly and scenario in ('impl_fallback','impl_dirty','impl_ignored','impl_denied','impl_timeout','impl_unknown'):
  if scenario=='impl_dirty': pathlib.Path('partial.txt').write_text('keep me\n')
  if scenario=='impl_ignored':
   pathlib.Path('scratch').mkdir(exist_ok=True); pathlib.Path('scratch/output').write_text('keep me\n')
  message={'impl_denied':'approval rejected','impl_unknown':'unexpected failure'}.get(scenario,'usage_limit_reached')
  print(json.dumps({'type':'turn.failed','error':{'message':message}})); sys.exit(124 if scenario=='impl_timeout' else 1)
 if readonly and scenario=='impl_fallback':
  print(json.dumps({'type':'turn.failed','error':{'message':'usage_limit_reached'}})); sys.exit(1)
 if '-o' in args:
  out=pathlib.Path(args[args.index('-o')+1])
  out.write_text('## レビュー\n判定: 問題なし\n' if scenario.startswith('review') else '## 仕様\n- 決定: テスト\n')
 if not readonly:
  pathlib.Path('feature.txt').write_text('implemented by codex\n')
  pathlib.Path('.agent-impl-report.md').write_text('## 実装の報告\n- 検証: 完了\n')
 print('{"type":"turn.completed"}'); sys.exit(0)
'''

class DispatchFixture(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(); self.root=pathlib.Path(self.tmp.name); self.home=self.root/'home'; self.home.mkdir(); self.bin=self.root/'mockbin'; self.bin.mkdir(); self.state=self.root/'state'; self.state.mkdir()
  for name in ('gh','tea','agent-notify','claude','codex'):
   p=self.bin/name; p.write_text(MOCK); p.chmod(0o755)
  agents=self.home/'.claude/agents'; agents.mkdir(parents=True)
  for name in ('spec','impl'): (agents/(name+'.md')).write_text('---\nname: test\n---\nrole\n')
  self.origin=self.root/'forge'/'gitea'/'proj.git'; self.origin.parent.mkdir(parents=True)
  self.git('init','--bare','-q','--initial-branch=main',str(self.origin),cwd=self.root)
  src=self.root/'source'; src.mkdir(); self.git('init','-q','-b','main',cwd=src); self.git('config','user.name','Test',cwd=src); self.git('config','user.email','test@example.test',cwd=src)
  (src/'README.md').write_text('base\n'); (src/'.gitignore').write_text('scratch/\n'); self.git('add','README.md','.gitignore',cwd=src); self.git('commit','-qm','base',cwd=src)
  self.git('remote','add','origin',str(self.origin),cwd=src); self.git('push','-q','origin','main',cwd=src)
  (src/'README.md').write_text('changed\n'); self.git('add','README.md',cwd=src); self.git('commit','-qm','pr',cwd=src); sha=self.git('rev-parse','HEAD',cwd=src).strip(); self.head=sha; self.git('push','-q','origin',sha+':refs/pull/1/head',cwd=src)
  self.script=self.root/'dispatch'; self.script.write_text(SOURCE); self.script.chmod(0o755)
 def tearDown(self): self.tmp.cleanup()
 def git(self,*args,cwd): return subprocess.run(['git',*args],cwd=cwd,text=True,capture_output=True,check=True).stdout
 def run_dispatch(self,scenario):
  env={'AGENT_GH_OWNER':'tester','AGENT_GITEA_WEB':'https://gitea.example.test','AGENT_GITEA_GIT':f'file://{self.root}/forge','HOME':str(self.home),'XDG_STATE_HOME':str(self.state),'PATH':str(self.bin)+':/usr/bin:/bin','MOCK_SCENARIO':scenario,'MOCK_STATE':str(self.state),'PR_HEAD':self.head,'GIT_AUTHOR_NAME':'Test','GIT_AUTHOR_EMAIL':'test@example.test','GIT_COMMITTER_NAME':'Test','GIT_COMMITTER_EMAIL':'test@example.test','GIT_CONFIG_NOSYSTEM':'1'}
  return subprocess.run([str(self.script)],cwd=self.home,env=env,text=True,capture_output=True,timeout=100)
 def calls(self): return (self.state/'calls').read_text()
 def comments(self): return (self.state/'comments').read_text()
 def codex_args(self): return [json.loads(line) for line in (self.state/'codex_args.jsonl').read_text().splitlines()]
 def claude_args(self): return [json.loads(line) for line in (self.state/'claude_args.jsonl').read_text().splitlines()]

class DispatchTest(DispatchFixture):
 def test_spec_uses_claude_opus_first(self):
  r=self.run_dispatch('spec_primary'); self.assertEqual(r.returncode,0,r.stderr); self.assertIn('着手: claude (spec)',self.comments()); self.assertIn('完了: claude (spec)',self.comments()); self.assertNotIn('codex',self.calls())
  args=self.claude_args()[0]; self.assertEqual(args[args.index('--model')+1],'claude-opus-5-5'); self.assertIn('--restricted',args); self.assertEqual(args[args.index('--tools')+1],'Read,Grep,Glob,Write,Skill')
  prompt=args[args.index('-p')+1]; self.assertIn('Bash は使えない',prompt); self.assertNotIn('Bash で実行できるのは',prompt)
 def test_spec_posts_decision_as_separate_comment(self):
  r=self.run_dispatch('spec_decision'); self.assertEqual(r.returncode,0,r.stderr)
  posted=[x for x in self.comments().split('\n\x1e\n') if x.strip()]
  spec=next(x for x in posted if x.startswith('## 仕様')); decision=next(x for x in posted if x.startswith('## 判断待ち'))
  self.assertLess(posted.index(spec),posted.index(decision)); self.assertNotIn('判断待ち\n',spec.split('---')[0]); self.assertIn('付けないでください',spec); self.assertNotIn('実装に進めるときは',spec); self.assertIn('- 操作: 選ぶ',decision)
 def test_claude_gets_this_environments_plugins(self):
  c=self.home/'.claude'; enabled=c/'plugins/cache/m/on/1'; disabled=c/'plugins/cache/m/off/1'; synced=c/'plugins/synced/b/sp'
  for d in (enabled,disabled,synced,c/'skills/packaged'): (d/'.claude-plugin').mkdir(parents=True); (d/'.claude-plugin/plugin.json').write_text('{}')
  (c/'settings.json').write_text(json.dumps({'enabledPlugins':{'on@m':True,'off@m':False}}))
  (c/'plugins/installed_plugins.json').write_text(json.dumps({'plugins':{'on@m':[{'installPath':str(enabled)}],'off@m':[{'installPath':str(disabled)}]}}))
  for d in (c/'skills/solo',c/'skills/synced/b/doc'): d.mkdir(parents=True); (d/'SKILL.md').write_text('---\nname: x\n---\n')
  r=self.run_dispatch('spec_primary'); self.assertEqual(r.returncode,0,r.stderr)
  args=self.claude_args()[0]; dirs=[args[i+1] for i,a in enumerate(args) if a=='--plugin-dir']
  self.assertIn(str(enabled),dirs); self.assertNotIn(str(disabled),dirs); self.assertIn(str(synced),dirs); self.assertIn(str(c/'skills/packaged'),dirs)
  self.assertEqual(sorted(pathlib.Path(d).name for d in dirs if '/plugins/user-skills' in d or '/plugins/anthropic-skills' in d),['anthropic-skills','user-skills'])
  self.assertIn('--restricted',args); self.assertIn('--strict-mcp-config',args)
 def test_spec_falls_back_to_codex_luna(self):
  r=self.run_dispatch('spec_claude_unavailable'); self.assertEqual(r.returncode,0,r.stderr); self.assertEqual(self.calls().count('claude primary'),1); self.assertEqual([a[a.index('-m')+1] for a in self.codex_args() if '-m' in a],['gpt-6-luna']); self.assertIn('完了: codex (spec)',self.comments())
  profile=' '.join(self.codex_args()[0]); self.assertIn('/usr/bin/git',profile); self.assertIn('/usr/lib/git-core',profile); self.assertIn('shell_environment_policy.set.PATH',profile); self.assertIn('Bash で実行できるのは',profile)
 def test_readonly_codex_can_read_skills_and_shared_instructions(self):
  for d in ('.codex/skills/ponytail','.agents/skills/k8s','.claude/rules','.ssh'): (self.home/d).mkdir(parents=True)
  (self.home/'.claude/CLAUDE.md').write_text('x\n')
  r=self.run_dispatch('spec_claude_unavailable'); self.assertEqual(r.returncode,0,r.stderr)
  perm=next(a for a in self.codex_args()[0] if a.startswith('permissions.dispatch_read.filesystem='))
  for d in ('.codex/skills','.agents/skills','.claude/CLAUDE.md','.claude/rules'): self.assertIn(json.dumps(str(self.home/d))+'="read"',perm)
  self.assertNotIn('.claude/knowledge',perm); self.assertNotIn('.ssh',perm)
 def test_spec_falls_back_to_codex_terra(self):
  r=self.run_dispatch('spec_luna_unavailable'); self.assertEqual(r.returncode,0,r.stderr); self.assertEqual(self.calls().count('claude primary'),1); self.assertEqual([a[a.index('-m')+1] for a in self.codex_args() if '-m' in a],['gpt-6-luna','gpt-6.1-terra']); self.assertIn('完了: codex (spec)',self.comments())
 def test_spec_denial_does_not_trigger_fallback(self):
  r=self.run_dispatch('spec_denied'); self.assertNotEqual(r.returncode,0); self.assertNotIn('codex',self.calls()); self.assertIn('中断: claude (spec)',self.comments())
 def test_spec_partial_output_does_not_trigger_fallback(self):
  r=self.run_dispatch('spec_partial'); self.assertNotEqual(r.returncode,0); self.assertNotIn('codex',self.calls())
 def test_spec_with_other_changes_does_not_trigger_fallback(self):
  r=self.run_dispatch('spec_dirty'); self.assertNotEqual(r.returncode,0); self.assertNotIn('codex',self.calls())
 def test_all_providers_unavailable_stops(self):
  r=self.run_dispatch('spec_both_fail'); self.assertNotEqual(r.returncode,0); self.assertEqual(len(self.codex_args()),2); self.assertIn('中断: codex (spec)',self.comments())
 def test_standalone_review_falls_back(self):
  r=self.run_dispatch('review_fallback'); self.assertEqual(r.returncode,0,r.stderr); self.assertIn('codex readonly',self.calls()); self.assertIn('レビュー: codex',self.comments()); self.assertNotIn('-m',self.codex_args()[0])
 def test_review_exit_zero_quota_falls_back(self):
  r=self.run_dispatch('review_zero_quota'); self.assertEqual(r.returncode,0,r.stderr); self.assertIn('codex readonly',self.calls()); self.assertIn('レビュー: codex',self.comments())
 def test_review_weekly_limit_falls_back(self):
  r=self.run_dispatch('review_weekly_quota'); self.assertEqual(r.returncode,0,r.stderr); self.assertIn('codex readonly',self.calls()); self.assertIn('レビュー: codex',self.comments())
 def test_partial_review_is_not_retried(self):
  r=self.run_dispatch('review_partial'); self.assertNotEqual(r.returncode,0); self.assertNotIn('codex readonly',self.calls())
 def test_successful_review_does_not_fallback(self):
  r=self.run_dispatch('review_success'); self.assertEqual(r.returncode,0,r.stderr); self.assertNotIn('codex readonly',self.calls()); self.assertIn('レビュー: claude',self.comments())
 def test_impl_codex_review_not_self_reviewed(self):
  r=self.run_dispatch('impl_primary'); self.assertEqual(r.returncode,0,r.stderr); self.assertNotIn('codex readonly',self.calls()); self.assertIn('独立レビューは未実施',self.comments()); self.assertEqual(self.codex_args()[0][self.codex_args()[0].index('-m')+1],'gpt-6-luna')
 def test_impl_falls_back_and_does_not_self_review(self):
  r=self.run_dispatch('impl_fallback'); self.assertEqual(r.returncode,0,r.stderr); self.assertEqual(self.calls().count('claude primary'),1); self.assertEqual(self.claude_args()[0][self.claude_args()[0].index('--model')+1],'claude-sonnet-5-5'); self.assertIn('codex readonly',self.calls()); self.assertIn('完了: claude (impl)',self.comments()); self.assertIn('独立レビューは未実施',self.comments())
 def test_partial_implementation_never_retried(self):
  r=self.run_dispatch('impl_dirty'); self.assertNotEqual(r.returncode,0); self.assertNotIn('claude primary',self.calls()); self.assertEqual((self.home/'.worktrees/proj-issue-1/partial.txt').read_text(),'keep me\n')
 def test_denial_never_retried(self):
  r=self.run_dispatch('impl_denied'); self.assertNotEqual(r.returncode,0); self.assertNotIn('claude primary',self.calls()); self.assertTrue((self.home/'.worktrees/proj-issue-1').is_dir())
 def test_ignored_output_is_not_discarded(self):
  r=self.run_dispatch('impl_ignored'); self.assertNotEqual(r.returncode,0); self.assertNotIn('claude primary',self.calls()); self.assertEqual((self.home/'.worktrees/proj-issue-1/scratch/output').read_text(),'keep me\n')
 def test_timeout_does_not_trigger_fallback(self):
  r=self.run_dispatch('impl_timeout'); self.assertNotEqual(r.returncode,0); self.assertNotIn('claude primary',self.calls())
 def test_unknown_error_does_not_trigger_fallback(self):
  r=self.run_dispatch('impl_unknown'); self.assertNotEqual(r.returncode,0); self.assertNotIn('claude primary',self.calls())

if __name__=='__main__': unittest.main()
