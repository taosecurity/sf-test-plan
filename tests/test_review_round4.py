"""0.3.2 code-review round 4: --out may not be the plan or report itself; names that keep dots; --from folder."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli  # noqa: E402

PLAN = "# T\nrun: a\n\n## 1 G\n- [ ] one\n  log: x\n"
REPORT = {"mods": [{"mod": "M", "status": "PASS", "rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Round4(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        with open(self.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(PLAN)
        self.rep = os.path.join(self.d, "r.json")
        with open(self.rep, "w", encoding="utf-8") as f:
            json.dump(REPORT, f)

    def tearDown(self):
        self._tmp.cleanup()

    def plan_text(self):
        with open(self.plan, encoding="utf-8") as f:
            return f.read()

    def test_build_out_is_the_plan(self):
        code, out, err = run("build", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("is the plan itself", err)
        self.assertEqual(self.plan_text(), PLAN)

    def test_logs_out_is_the_plan(self):
        code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("the plan itself", err)
        self.assertEqual(self.plan_text(), PLAN)

    def test_logs_out_is_the_report(self):
        code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", self.rep)
        self.assertEqual(code, 2, out + err)
        self.assertIn("the report itself", err)
        with open(self.rep, encoding="utf-8") as f:
            self.assertEqual(json.load(f), REPORT)

    def test_from_folder_without_out_does_not_mention_out(self):
        code, out, err = run("rules", self.plan, "--from", self.d)
        self.assertEqual(code, 2, out + err)
        self.assertIn("--from", err)
        self.assertIn("is a folder", err)
        self.assertNotIn("Give a file name with --out", err)

    def test_names_without_a_plan_ending_keep_their_dots(self):
        for name, want in {"Cool.Mod": "Cool.Mod", "v1.2": "v1.2", "Cool.Mod.txt": "Cool.Mod",
                           "Cool.Mod.MARKDOWN": "Cool.Mod", "plan.txt": "plan"}.items():
            with self.subTest(name=name):
                self.assertEqual(cli._mod_from_path(name), want)


if __name__ == "__main__":
    unittest.main()
