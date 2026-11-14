import os, pathlib, unittest

import test_agent_dispatch_fallback as base

HELPER = pathlib.Path(os.environ.get('VERIFY_TEST_SOURCE', '/home/yagamin/bin/agent-dispatch-verify'))
VERIFY_BODY = "('## 仕様\\nImplement.' if scenario=='gate_none' else '## 仕様\\n```verify\\ntest -f fixed.txt\\n```\\n')"
# gate_fix は、検証失敗を伝える 2 回目の実装呼び出しのときだけ fixed.txt を作る。gate_never は作らない
MOCK = base.MOCK.replace("'body':'## 仕様\\nImplement the issue.'", "'body':" + VERIFY_BODY).replace(
    " if not readonly:\n  pathlib.Path('feature.txt')",
    " if not readonly:\n  if scenario=='gate_fix' and '前回の実装は、仕様の検証コマンド' in args[-1]: pathlib.Path('fixed.txt').write_text('ok\\n')\n  pathlib.Path('feature.txt')")
assert MOCK != base.MOCK and 'gate_fix' in MOCK and 'gate_none' in MOCK


class GateTest(base.DispatchFixture):
    def setUp(self):
        super().setUp()
        for name in ('gh', 'tea', 'agent-notify', 'claude', 'codex'):
            (self.bin / name).write_text(MOCK)
        (self.home / 'bin').mkdir(); (self.home / 'bin' / 'agent-dispatch-verify').symlink_to(HELPER)
    def impl_calls(self): return [a for a in self.codex_args() if '--ignore-user-config' not in a]

    def test_failing_verification_is_fixed_by_rerun(self):
        r = self.run_dispatch('gate_fix'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('検証: 成功 (再実装 1 回)', self.comments()); self.assertEqual(len(self.impl_calls()), 2)
        self.assertIn('前回の実装は、仕様の検証コマンド', self.impl_calls()[1][-1])
    def test_gives_up_after_two_retries_and_says_so(self):
        r = self.run_dispatch('gate_never'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('検証: 失敗 (再実装 2 回', self.comments()); self.assertEqual(len(self.impl_calls()), 3)
    def test_no_verify_block_is_reported_not_passed(self):
        r = self.run_dispatch('gate_none'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('検証: 未実施', self.comments()); self.assertEqual(len(self.impl_calls()), 1)


if __name__ == '__main__': unittest.main()
