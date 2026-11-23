"""0.3.2 code review round S1: a .testplan before a text ending, the null device as an output, and build
never writing over its --rules file."""
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


class ReviewS1(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        self.write(self.plan, PLAN)

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def test_testplan_before_a_text_ending(self):
        for name, mod in (("Beacon.testplan.txt", "Beacon"), ("Beacon.TESTPLAN.TXT", "Beacon"),
                          ("My.Mod.testplan.txt", "My.Mod"), ("plan.txt", "plan")):
            with self.subTest(name=name):
                self.assertEqual(cli._mod_from_path(name), mod)

    def test_new_names_the_mod_without_testplan(self):
        path = os.path.join(self.d, "Beacon.testplan.txt")
        code, _, _ = run("new", path)
        self.assertEqual(code, 0)
        with open(path, encoding="utf-8") as f:
            self.assertIn("Beacon", f.read())
        with open(path, encoding="utf-8") as f:
            self.assertNotIn("Beacon.testplan", f.read())

    def test_logs_and_build_to_the_null_device(self):
        rep = os.path.join(self.d, "r.json")
        self.write(rep, json.dumps(REPORT))
        code, out, err = run("logs", rep, "--plan", self.plan, "--out", os.devnull)
        self.assertEqual(code, 0, err)
        self.assertIn("Marks:", out)
        code, out, err = run("build", self.plan, "--out", os.devnull)
        self.assertEqual(code, 0, err)
        self.assertIn("Page:", out)

    def test_build_out_is_the_rules_file(self):
        rules = os.path.join(self.d, "p.logrules.json")
        text = json.dumps({"mod": "M", "expect": [{"id": "x", "re": "x"}], "forbid": []})
        self.write(rules, text)
        code, out, err = run("build", self.plan, "--rules", rules, "--out", rules)
        self.assertEqual(code, 2)
        self.assertNotIn("Page:", out)
        self.assertIn(f"--out {rules} is the --rules file. Give the page another name with --out.\n", err)
        with open(rules, encoding="utf-8") as f:
            self.assertEqual(f.read(), text)


if __name__ == "__main__":
    unittest.main()
