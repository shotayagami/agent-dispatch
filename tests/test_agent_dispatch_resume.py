import pathlib
import unittest

from test_agent_dispatch_fallback import DispatchTest


class ResumeTest(DispatchTest):
    def test_resume_clean_owned_worktree(self):
        first = self.run_dispatch('impl_denied')
        self.assertNotEqual(first.returncode, 0)
        second = self.run_dispatch('impl_primary')
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertIn('完了: codex (impl)', self.comments())
        self.assertTrue(list((self.state / 'agent-dispatch').glob('*.log.files/previous-agent-issue.md')))

    def test_resume_preserves_partial_work(self):
        self.assertNotEqual(self.run_dispatch('impl_dirty').returncode, 0)
        wt = self.home / '.worktrees/proj-issue-1'
        self.assertNotEqual(self.run_dispatch('impl_primary').returncode, 0)
        self.assertEqual((wt / 'partial.txt').read_text(), 'keep me\n')
        self.assertIn('途中の変更または生成物', self.comments())

    def test_resume_rejects_unowned_worktree(self):
        self.assertNotEqual(self.run_dispatch('impl_denied').returncode, 0)
        wt = self.home / '.worktrees/proj-issue-1'
        self.git('checkout', '-qb', 'other', cwd=wt)
        self.assertNotEqual(self.run_dispatch('impl_primary').returncode, 0)
        self.assertIn('ブランチが feat/issue-1 と一致しません', self.comments())


if __name__ == '__main__':
    unittest.main()
