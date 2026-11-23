import json, os, pathlib, subprocess, tempfile, unittest

SCRIPT = os.environ.get('DETECT_TEST_SOURCE', str(pathlib.Path(__file__).resolve().parents[1] / 'bin' / 'agent-detect'))
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
f = os.path.join(d, path.split('?')[0].strip('/').replace('/', '_')) + ('_closed' if 'state=closed' in path else '')
if not os.path.exists(f): sys.exit(1)
sys.stdout.write(open(f).read())
'''

class Base(unittest.TestCase):
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
                    'AGENT_DETECT_REPOS': str(r / 'repos'), 'AGENT_DETECT_STATE': str(self.state), 'AGENT_DETECT_ALERT_REPO': '',
                    'AGENT_DETECT_WAZUH_SSH': '', 'AGENT_DETECT_SR_URL': ''}   # 本物の Wazuh・SimpleRisk へつながない
    def tearDown(self): self.t.cleanup()
    def put(self, name, obj): (self.fix / name).write_text(json.dumps(obj))
    def ci(self, concl): self.put('repos_gitea_app_actions_runs', {'workflow_runs': [{'status': 'completed', 'conclusion': concl, 'html_url': 'https://x/run/1', 'name': 'ci'}]})
    def issues(self, l): self.put('repos_gitea_app_issues', l)
    def run_once(self, *args):
        p = subprocess.run(['bash', SCRIPT, *args], env=self.env, capture_output=True, text=True); self.assertEqual(p.returncode, 0, p.stderr); return p.stdout
    def writes(self): return [json.loads(l) for l in self.log.read_text().splitlines() if l]

class DetectTest(Base):
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
    def notifies(self):
        f = pathlib.Path(f'{self.log}.notify'); return f.read_text() if f.exists() else ''
    def test_issue_list_failure_is_reported_and_notified_once(self):
        self.put('repos_gitea_app_issues', {'message': 'Validation Failed'})   # 配列でない応答も失敗として数える
        out = self.run_once(); self.assertIn('Issue 一覧を取得できなかった: gitea gitea/app', out)
        self.run_once(); self.assertNotIn('続けて取得できません', self.notifies())
        self.run_once(); self.assertEqual(self.notifies().count('3 回続けて取得できません'), 1)
        self.run_once(); self.assertEqual(self.notifies().count('3 回続けて取得できません'), 1)   # 4 回目は鳴らさない
        self.issues([]); self.run_once(); self.assertEqual((self.state / 'issues-fail').read_text(), '')   # 取れたら 0 に戻る
    def test_dry_run_changes_nothing(self):
        self.run_once('--dry-run'); self.run_once('--dry-run'); self.assertEqual(self.writes(), [])
        self.assertEqual((self.state / 'current').read_text(), '')

# kubectl (Alertmanager)・curl (Zabbix)・claude の代役。応答は fixture の am / zbx、呼び出しは LOG.<名前> に残す
ALERT_STUBS = {
    'kubectl': '#!/bin/bash\necho "$@" >> "$LOG.kubectl"\n[[ -f "$FIX/am" ]] && cat "$FIX/am" || exit 1\n',
    'curl': '#!/bin/bash\ncat > /dev/null\n[[ -f "$FIX/zbx" ]] && cat "$FIX/zbx" || exit 7\n',
    'claude': '#!/bin/bash\ncat > /dev/null\necho "$2" >> "$LOG.claude"\n',   # 本物と同じく stdin を読む
}
AM_JOB = {'labels': {'alertname': 'KubeJobFailed', 'severity': 'warning', 'namespace': 'monitoring', 'job_name': 'audit-29123456'},
          'annotations': {'summary': 'Job failed'}, 'startsAt': '2026-11-20T00:00:00Z'}
KEY = 'alert am KubeJobFailed monitoring audit'

class AlertTest(Base):
    def setUp(self):
        super().setUp()
        for n, body in ALERT_STUBS.items():
            (self.bin / n).write_text(body); (self.bin / n).chmod(0o755)
        envf = pathlib.Path(self.t.name) / 'env'; envf.write_text('ZBX_API_TOKEN="tok"\n')
        self.env.update({'AGENT_DETECT_ALERT_REPO': 'gitea gitea/app', 'AGENT_DETECT_ZBX_ENV': str(envf), 'AGENT_DETECT_ZBX_URL': 'https://zbx.example/api_jsonrpc.php'})
        self.ci('success'); self.put('zbx', {'result': []})
    def claude_calls(self):
        f = pathlib.Path(str(self.log) + '.claude'); return f.read_text() if f.exists() else ''

    def test_alert_creates_labeled_issue_and_investigates(self):
        self.put('am', [AM_JOB, {**AM_JOB, 'labels': {**AM_JOB['labels'], 'job_name': 'audit-29123999'}},
                        {'labels': {'alertname': 'Watchdog', 'severity': 'none'}, 'annotations': {}, 'startsAt': 'x'}])
        self.run_once(); self.assertEqual(self.writes(), [])
        self.run_once(); w = self.writes()
        self.assertEqual(len(w), 1)                                   # 同じ CronJob の 2 Job は 1 件、Watchdog は除外
        self.assertEqual(w[0][2]['labels'], ['incident'])
        self.assertIn(f'<!-- agent-detect:{KEY} -->', w[0][2]['body'])
        self.assertIn('https://x/issues/9', self.claude_calls())
    def test_each_new_issue_is_investigated(self):
        self.put('zbx', {'result': [{'triggerid': t, 'description': 'd', 'priority': '4', 'lastchange': '1763700000', 'hosts': [{'name': 'h'}]} for t in ('1', '2')]})
        self.put('am', []); self.run_once(); self.run_once()
        self.assertEqual(self.claude_calls().count('サーバーのアラートから自動で作った Issue'), 2)
        self.assertEqual(self.claude_calls().count('必ず手順 4 のコメントを投稿して終える'), 2)   # プロンプトが途中で切れていない
        self.assertEqual(self.claude_calls().count('必ず手順 4 のコメントを投稿して終える'), 2)   # プロンプトが途中で切れていない   # claude が残りの URL を stdin から食べない
    def test_recurrence_reopens_closed_issue(self):
        self.put('am', [AM_JOB])
        self.put('repos_gitea_app_issues_closed', [{'number': 7, 'title': '[agent-detect] x', 'body': f'b\n\n<!-- agent-detect:{KEY} -->'}])
        self.run_once(); self.run_once(); w = self.writes()
        self.assertEqual([x[:2] for x in w], [['POST', '/repos/gitea/app/issues/7/comments'], ['PATCH', '/repos/gitea/app/issues/7']])
        self.assertIn('再発 1 回目', w[0][2]['body']); self.assertEqual(w[1][2], {'state': 'open'})
    def test_alert_fetch_failure_never_closes(self):
        self.issues([{'number': 5, 'title': '[agent-detect] x', 'body': f'<!-- agent-detect:{KEY} -->'}])
        out = self.run_once()                                          # am fixture なし = kubectl 失敗
        self.assertEqual(self.writes(), []); self.assertIn('取得できなかったアラート: alert am', out)
    def test_resolved_alert_closes(self):
        self.put('am', [])
        self.issues([{'number': 5, 'title': '[agent-detect] x', 'body': f'<!-- agent-detect:{KEY} -->'}])
        self.run_once(); self.assertEqual([x[:2] for x in self.writes()][-1], ['PATCH', '/repos/gitea/app/issues/5'])
    def test_zabbix_problem(self):
        self.put('am', [])
        self.put('zbx', {'result': [{'triggerid': '123', 'description': 'High swap on host-a', 'priority': '4', 'lastchange': '1763700000', 'hosts': [{'name': 'proxmox'}]}]})
        self.run_once(); self.run_once(); w = self.writes()
        self.assertEqual(len(w), 1); self.assertIn('<!-- agent-detect:alert zbx 123 -->', w[0][2]['body'])
        self.assertIn('High', w[0][2]['body']); self.assertIn('proxmox', w[0][2]['title'])
    def test_alert_dry_run_changes_nothing(self):
        self.put('am', [AM_JOB]); self.run_once('--dry-run'); out = self.run_once('--dry-run')
        self.assertEqual(self.writes(), []); self.assertEqual(self.claude_calls(), ''); self.assertIn('KubeJobFailed', out)

# ssh (Wazuh への転送)・curl (indexer と SimpleRisk) の代役。応答は fixture の wz / sr、curl に渡った引数は LOG.curl に残す
SEC_STUBS = {
    'ssh': '#!/bin/bash\necho "$@" >> "$LOG.ssh"\n[[ -f "$FIX/ssh_fail" ]] && exit 255\nexit 0\n',
    'curl': r'''#!/usr/bin/env python3
import os, sys
a = sys.argv[1:]; f = os.environ['FIX']
open(os.environ['LOG'] + '.curl', 'a').write(' '.join(a) + '\n')
url = [x for x in a if x.startswith('http')][-1]
def out(n):
    p = os.path.join(f, n)
    if not os.path.exists(p): sys.exit(7)
    sys.stdout.write(open(p).read()); sys.exit(0)
if '_search' in url: out('wz')
if url.endswith('/api/v2/risks?length=1000'): out('sr')
if '-w' in a: print('302' if os.path.exists(os.path.join(f, 'sr')) else '200'); sys.exit(0)
print('<input type="hidden" name="csrf_token" value="' + 'a' * 64 + '">')
''',
}
def wz_bucket(agent, pkg, sev='High', cves=('CVE-2026-1',)):
    return {'key': {'a': agent, 'p': pkg}, 'doc_count': len(cves), 'sev': {'buckets': [{'key': sev}]},
            'cve': {'buckets': [{'key': c} for c in cves]}, 'ver': {'buckets': [{'key': '1.0'}]}, 'cond': {'buckets': [{'key': 'Package less than 1.1'}]}}
RISK = {'id': 1036, 'reference_id': 'AUDIT-20260101-01', 'subject': 'テスト用のリスク', 'status': 'New', 'calculated_risk': 3.6, 'next_review': None, 'submission_date': '2026-10-22'}

class SecurityTest(Base):
    def setUp(self):
        super().setUp()
        for n, body in SEC_STUBS.items():
            (self.bin / n).write_text(body); (self.bin / n).chmod(0o755)
        r = pathlib.Path(self.t.name)
        (r / 'wzenv').write_text('WAZUH_INDEXER_USER=u\nWAZUH_INDEXER_PASS="p\\"w"\n')
        (r / 'srenv').write_text('CF_ACCESS_CLIENT_ID=id\nCF_ACCESS_CLIENT_SECRET=sec\nSIMPLERISK_USER=me\nSIMPLERISK_PASS=pw!\n')
        (self.bin / 'kubectl').write_text('#!/bin/bash\nexit 1\n'); (self.bin / 'kubectl').chmod(0o755)
        self.env.update({'AGENT_DETECT_ALERT_REPO': 'gitea gitea/app', 'AGENT_DETECT_ZBX_ENV': '/nonexistent', 'AGENT_DETECT_ZBX_URL': '',
                         'AGENT_DETECT_WAZUH_SSH': 'ubuntu@wazuh', 'AGENT_DETECT_WAZUH_ENV': str(r / 'wzenv'),
                         'AGENT_DETECT_SR_URL': 'https://sr.example', 'AGENT_DETECT_SR_ENV': str(r / 'srenv')})
        self.ci('success')
        self.put('wz', {'aggregations': {'g': {'buckets': []}}}); self.put('sr', {'status': 200, 'data': {'risks': []}})
    def log_of(self, n):
        f = pathlib.Path(f'{self.log}.{n}'); return f.read_text() if f.exists() else ''

    def test_wazuh_creates_one_issue_per_host_and_package(self):
        self.put('wz', {'aggregations': {'g': {'buckets': [wz_bucket('host-a', 'pillow', 'Critical', [f'CVE-2026-{i}' for i in range(12)]), wz_bucket('host-b', 'pillow')]}}})
        self.run_once(); self.run_once(); w = self.writes()
        self.assertEqual(len(w), 2)
        self.assertEqual(w[0][2]['labels'], ['security'])
        self.assertIn('<!-- agent-detect:sec wz host-a pillow -->', w[0][2]['body'])
        self.assertIn('(Critical)', w[0][2]['title']); self.assertIn('ほか 2 件', w[0][2]['body'])
        self.assertIn('-L 19201:127.0.0.1:9200', self.log_of('ssh')); self.assertIn('-O exit', self.log_of('ssh'))   # 転送を張り、閉じる
        self.assertNotIn('p\\"w', self.log_of('curl')); self.assertNotIn('pw!', self.log_of('curl'))   # 資格情報を引数に出さない
    def test_simplerisk_open_risks_only(self):
        self.put('sr', {'status': 200, 'data': {'risks': [RISK, {**RISK, 'id': 1001, 'status': 'Closed'}]}})
        self.run_once(); self.run_once(); w = self.writes()
        self.assertEqual(len(w), 1); self.assertIn('<!-- agent-detect:sec sr 1036 -->', w[0][2]['body'])
        self.assertIn('AUDIT-20260101-01', w[0][2]['title']); self.assertIn('https://sr.example/management/view.php?id=1036', w[0][2]['body'])
        self.assertNotIn('pw!', self.log_of('curl'))
    def test_security_issues_are_not_investigated(self):
        self.put('sr', {'status': 200, 'data': {'risks': [RISK]}})
        (self.bin / 'claude').write_text('#!/bin/bash\necho "$2" >> "$LOG.claude"\n'); (self.bin / 'claude').chmod(0o755)
        self.run_once(); self.run_once(); self.assertEqual(self.log_of('claude'), '')
    def test_fetch_failure_never_closes(self):
        self.issues([{'number': 5, 'title': '[agent-detect] x', 'body': '<!-- agent-detect:sec wz host-a pillow -->'},
                     {'number': 6, 'title': '[agent-detect] y', 'body': '<!-- agent-detect:sec sr 1036 -->'}])
        (self.fix / 'ssh_fail').touch(); (self.fix / 'sr').unlink(); out = self.run_once()
        self.assertEqual(self.writes(), []); self.assertIn('取得できなかったアラート: sec wz', out); self.assertIn('取得できなかったアラート: sec sr', out)
    def test_resolved_risk_closes(self):
        self.issues([{'number': 6, 'title': '[agent-detect] y', 'body': '<!-- agent-detect:sec sr 1036 -->'}])
        self.run_once(); self.assertEqual([x[:2] for x in self.writes()][-1], ['PATCH', '/repos/gitea/app/issues/6'])

if __name__ == '__main__': unittest.main()
