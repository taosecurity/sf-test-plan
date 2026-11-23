"""0.3.2 code-review round 5: --out may not be the results file; names that start with a dot."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, results  # noqa: E402

PLAN = "# T\nrun: a\n\n## 1 G\n- [ ] one\n  log: x\n"
REPORT = {"mods": [{"mod": "M", "status": "PASS", "rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Round5(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        with open(self.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(PLAN)
        self.rep = os.path.join(self.d, "r.json")
        with open(self.rep, "w", encoding="utf-8") as f:
            json.dump(REPORT, f)
        self.res = results.results_path(self.plan)
        with open(self.res, "w", encoding="utf-8") as f:
            f.write("[]")

    def tearDown(self):
        self._tmp.cleanup()

    def res_text(self):
        with open(self.res, encoding="utf-8") as f:
            return f.read()

    def test_build_out_is_the_results_file(self):
        code, out, err = run("build", self.plan, "--out", self.res)
        self.assertEqual(code, 2, out + err)
        self.assertIn("results file", err)
        self.assertEqual(self.res_text(), "[]")

    def test_logs_out_is_the_results_file(self):
        code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", self.res)
        self.assertEqual(code, 2, out + err)
        self.assertIn("results file", err)
        self.assertEqual(self.res_text(), "[]")

    def test_names_starting_with_a_dot_give_the_default(self):
        for name in (".Mod", ".hidden.txt", ".hidden.testplan.md", ".hidden"):
            with self.subTest(name=name):
                self.assertEqual(cli._mod_from_path(os.path.join("d", name)), "My Mod")
        self.assertEqual(cli._mod_from_path("Cool.Mod"), "Cool.Mod")


if __name__ == "__main__":
    unittest.main()
