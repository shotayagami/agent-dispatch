import datetime, pathlib

import test_agent_dispatch_fallback as base


class CapTest(base.DispatchFixture):
    def usage(self):
        d = self.state / 'agent-dispatch' / 'usage'; d.mkdir(parents=True, exist_ok=True); return d / datetime.date.today().strftime('%F')
    def fill(self, n): self.usage().write_text(''.join(f'00:00:00 agent:impl x#{i}\n' for i in range(n)))

    def test_stops_at_cap_without_touching_the_issue(self):
        self.fill(60); r = self.run_dispatch('impl_primary'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn('上限', r.stdout); self.assertFalse((self.state / 'codex_args.jsonl').exists())
        self.assertTrue(pathlib.Path(str(self.usage()) + '.notified').exists())
        self.assertEqual(len(self.usage().read_text().splitlines()), 60)
    def test_below_cap_runs_and_counts_one(self):
        self.fill(59); r = self.run_dispatch('impl_primary'); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue((self.state / 'codex_args.jsonl').exists()); self.assertEqual(len(self.usage().read_text().splitlines()), 60)
    def test_next_day_is_a_fresh_count(self):
        y = self.usage().with_name((datetime.date.today() - datetime.timedelta(days=1)).strftime('%F')); y.write_text('x\n' * 99)
        r = self.run_dispatch('impl_primary'); self.assertEqual(r.returncode, 0, r.stderr); self.assertTrue((self.state / 'codex_args.jsonl').exists())

if __name__ == '__main__':
    import unittest; unittest.main()
