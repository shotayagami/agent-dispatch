import os, pathlib, subprocess, tempfile, unittest

HELPER = os.environ.get('VERIFY_TEST_SOURCE', '/home/yagamin/bin/agent-dispatch-verify')
F = '```'

class VerifyTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.r = pathlib.Path(self.t.name)
        self.wt = self.r / 'wt'; self.wt.mkdir(); self.out = self.r / 'out.md'
    def tearDown(self): self.t.cleanup()
    def run_helper(self, issue):
        (self.r / 'issue.md').write_text(issue)
        p = subprocess.run(['python3', HELPER, str(self.wt), str(self.r / 'issue.md'), str(self.out)], capture_output=True, text=True)
        return p.returncode, self.out.read_text() if self.out.exists() else ''

    def test_pass(self):
        rc, rep = self.run_helper(f'## 仕様\n{F}verify\ntrue\n# comment\necho hi\n{F}\n'); self.assertEqual(rc, 0); self.assertIn('2 件中 2 件成功', rep)
    def test_fail_reports_tail(self):
        rc, rep = self.run_helper(f'{F}verify\necho boom >&2; exit 7\n{F}\n'); self.assertEqual(rc, 1); self.assertIn('終了コード 7', rep); self.assertIn('boom', rep)
    def test_no_block_is_not_a_pass(self):
        rc, rep = self.run_helper('検証方法: pytest を実行\n'); self.assertEqual(rc, 3)
    def test_last_block_wins(self):
        rc, _ = self.run_helper(f'{F}verify\nfalse\n{F}\n\n{F}verify\ntrue\n{F}\n'); self.assertEqual(rc, 0)
    def test_runs_in_worktree_and_writes_there(self):
        rc, _ = self.run_helper(f'{F}verify\ntouch made-here\n{F}\n'); self.assertEqual(rc, 0); self.assertTrue((self.wt / 'made-here').exists())
    def test_no_network_and_no_home(self):
        home = pathlib.Path.home()
        rc, rep = self.run_helper(f'{F}verify\ntest ! -e {home}/.env\n(exec 3<>/dev/tcp/1.1.1.1/53) 2>/dev/null && exit 9 || true\n{F}\n')
        self.assertEqual(rc, 0, rep)
    def test_timeout_is_failure(self):
        import importlib.machinery, importlib.util
        spec = importlib.util.spec_from_loader('v', importlib.machinery.SourceFileLoader('v', HELPER)); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        m.TIMEOUT = 1; (self.r / 'issue.md').write_text(f'{F}verify\nsleep 5\n{F}\n')
        self.assertEqual(m.main(str(self.wt), str(self.r / 'issue.md'), str(self.out)), 1)

if __name__ == '__main__': unittest.main()
