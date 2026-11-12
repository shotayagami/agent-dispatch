import pathlib, re, subprocess, tempfile, unittest
# agent-dispatch の impl でコミットに入れるファイルの選び方と、CI 定義を止める検査を、script の実際の行を抜き出して試す
SRC = pathlib.Path('/home/yagamin/bin/agent-dispatch').read_text()
STAGE = next(l for l in SRC.splitlines() if l.startswith('git ls-files '))
GUARD = re.search(r"^WF=.*?grep -E '([^']+)'", SRC, re.M).group(1)

class StageTest(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory(); self.r = pathlib.Path(self.t.name)
        self.git('init', '-q', '-b', 'main'); self.git('config', 'user.name', 'T'); self.git('config', 'user.email', 't@example.test')
        for f in ['keep', 'mod', 'del', 'sub/old name.txt', '.gitignore']: self.w(f, 'x\n')
        self.w('.gitignore', 'build/\n'); self.git('add', '.'); self.git('commit', '-qm', 'init')
        (self.r / '.git/info/exclude').write_text('.agent-*\n')  # agent-dispatch が bare clone の info/exclude に足す行と同じ
    def tearDown(self): self.t.cleanup()
    def w(self, f, s): p = self.r / f; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(s)
    def git(self, *a): return subprocess.run(['git', '-C', str(self.r), *a], check=True, capture_output=True, text=True).stdout

    def test_stages_exactly_the_changes(self):
        self.w('mod', 'changed\n'); (self.r / 'del').unlink(); self.w('new file.txt', 'n\n'); self.w('sub/old name.txt', 'y\n')
        self.w('.agent-impl-report.md', 'r'); self.w('.agent-issue.md', 'i'); self.w('build/out', 'o')
        subprocess.run(['bash', '-c', STAGE], cwd=self.r, check=True, env={'PATH': '/usr/bin:/bin', 'LOG': '/dev/null'})
        st = dict(l.split('\t')[::-1] for l in self.git('diff', '--cached', '--name-status').splitlines())
        self.assertEqual(st, {'mod': 'M', 'del': 'D', 'new file.txt': 'A', 'sub/old name.txt': 'M'})

    def test_nothing_changed_stages_nothing(self):
        self.w('.agent-impl-report.md', 'r')
        subprocess.run(['bash', '-c', STAGE], cwd=self.r, check=True, env={'PATH': '/usr/bin:/bin', 'LOG': '/dev/null'})
        self.assertEqual(self.git('diff', '--cached', '--name-only'), '')

class GuardTest(unittest.TestCase):
    def test_ci_definitions_blocked(self):
        for f, blocked in [('.github/workflows/ci.yml', True), ('.gitea/workflows/a.yaml', True),
                           ('docs/.github/workflows/x', False), ('.github/CODEOWNERS', False), ('src/a.py', False)]:
            self.assertEqual(bool(re.search(GUARD, f)), blocked, f)

if __name__ == '__main__': unittest.main()
