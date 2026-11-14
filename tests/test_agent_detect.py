import json, os, pathlib, subprocess, tempfile, unittest

SCRIPT = os.environ.get('DETECT_TEST_SOURCE', '/home/yagamin/bin/agent-detect')
# gh と tea の代役。GET は fixture のファイル (パスの / を _ にしたもの) を返し、POST/PATCH は呼ばれた内容を log に残す
STUB = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]; d = os.environ['FIX']
if a[0] != 'api': sys.exit(2)
a = a[1:]
if a[:2] == ['--login', 'gitea-home']: a = a[2:]
m = 'GET'
if a[0] == '-X': m = a[1]; a = a[2:]
path = a[0]
if m != 'GET':
    open(os.environ['LOG'], 'a').write(json.dumps([m, path, json.loads(sys.stdin.read() or '{}')]) + '\n'); print('{"html_url":"https://x/issues/9"}'); sys.exit(0)
f = os.path.join(d, path.split('?')[0].strip('/').replace('/', '_'))
if not os.path.exists(f): sys.exit(1)
sys.stdout.write(open(f).read())
'''

class DetectTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); r = pathlib.Path(self.t.name)
        self.fix, self.bin, self.state = r / 'fix', r / 'bin', r / 'state'
        for p in (self.fix, self.bin): p.mkdir()
        for n in ('gh', 'tea'):
            (self.bin / n).write_text(STUB); (self.bin / n).chmod(0o755)
        (self.bin / 'agent-notify').write_text('#!/bin/bash\necho "$@" >> "$LOG.notify"\n'); (self.bin / 'agent-notify').chmod(0o755)
        (r / 'repos').write_text('gitea gitea/app\n')
        self.log = r / 'log'; self.log.touch()
        self.put('user', {'login': 'me'}); self.put('repos_gitea_app', {'default_branch': 'main'})
        self.put('repos_gitea_app_pulls', [])
        self.ci('failure'); self.issues([])
        self.env = {**os.environ, 'FIX': str(self.fix), 'LOG': str(self.log), 'PATH': f'{self.bin}:{os.environ["PATH"]}',
                    'AGENT_DETECT_REPOS': str(r / 'repos'), 'AGENT_DETECT_STATE': str(self.state)}
    def tearDown(self): self.t.cleanup()
    def put(self, name, obj): (self.fix / name).write_text(json.dumps(obj))
    def ci(self, concl): self.put('repos_gitea_app_actions_runs', {'workflow_runs': [{'status': 'completed', 'conclusion': concl, 'html_url': 'https://x/run/1', 'name': 'ci'}]})
    def issues(self, l): self.put('repos_gitea_app_issues', l)
    def run_once(self, *args):
        p = subprocess.run(['bash', SCRIPT, *args], env=self.env, capture_output=True, text=True); self.assertEqual(p.returncode, 0, p.stderr); return p.stdout
    def writes(self): return [json.loads(l) for l in self.log.read_text().splitlines() if l]

    def test_creates_only_after_two_consecutive_runs(self):
        self.run_once(); self.assertEqual(self.writes(), [])           # 1 回目は作らない
        self.run_once(); w = self.writes(); self.assertEqual(len(w), 1)  # 2 回目で作る
        self.assertEqual(w[0][:2], ['POST', '/repos/gitea/app/issues'])
        self.assertIn('<!-- agent-detect:ci gitea gitea/app main -->', w[0][2]['body'])
        self.assertTrue(w[0][2]['title'].startswith('[agent-detect]'))
    def test_no_duplicate_when_issue_is_open(self):
        self.issues([{'number': 5, 'title': '[agent-detect] x', 'body': 'b\n\n<!-- agent-detect:ci gitea gitea/app main -->'}])
        self.run_once(); self.run_once(); self.assertEqual(self.writes(), [])
    def test_closes_when_resolved(self):
        self.issues([{'number': 5, 'title': '[agent-detect] x', 'body': 'b\n\n<!-- agent-detect:ci gitea gitea/app main -->'}])
        self.ci('success'); self.run_once()
        self.assertEqual([x[:2] for x in self.writes()], [['POST', '/repos/gitea/app/issues/5/comments'], ['PATCH', '/repos/gitea/app/issues/5']])
    def test_unreadable_repo_never_closes(self):
        self.issues([{'number': 5, 'title': '[agent-detect] x', 'body': '<!-- agent-detect:ci gitea gitea/app main -->'}])
        (self.fix / 'repos_gitea_app_actions_runs').unlink(); out = self.run_once()   # runs が取れない
        self.assertEqual(self.writes(), []); self.assertIn('取得できなかった repo: 1', out)
    def test_stale_own_pr_only(self):
        self.ci('success')
        self.put('repos_gitea_app_pulls', [
            {'number': 1, 'user': {'login': 'me'}, 'updated_at': '2020-01-01T00:00:00Z', 'html_url': 'u1', 'title': 't1'},
            {'number': 2, 'user': {'login': 'bot'}, 'updated_at': '2020-01-01T00:00:00Z', 'html_url': 'u2', 'title': 't2'},
            {'number': 3, 'user': {'login': 'me'}, 'updated_at': '2999-01-01T00:00:00Z', 'html_url': 'u3', 'title': 't3'}])
        self.run_once(); self.run_once(); w = self.writes()
        self.assertEqual(len(w), 1); self.assertIn('PR #1', w[0][2]['title'])
    def test_dry_run_changes_nothing(self):
        self.run_once('--dry-run'); self.run_once('--dry-run'); self.assertEqual(self.writes(), [])
        self.assertEqual((self.state / 'current').read_text(), '')

if __name__ == '__main__': unittest.main()
