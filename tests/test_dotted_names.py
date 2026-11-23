"""0.3.2: the mod name taken from a plan's file name keeps dots that belong to the name.

0.3.1 cut the name at the first dot, so "My.Mod.testplan.md" gave "My". Only the plan ending (".testplan.md",
else ".md", either case) is removed now, the same ending the default rule file name drops.
"""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXAMPLE = os.path.join(ROOT, "examples", "Beacon.testplan.md")
sys.path.insert(0, ROOT)

from sftestplan import cli  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class DottedNames(unittest.TestCase):
    def test_mod_from_path(self):
        cases = {
            "My.Mod.testplan.md": "My.Mod",
            "Beacon.testplan.md": "Beacon",
            "My.Mod.TESTPLAN.MD": "My.Mod",
            "My.Mod.md": "My.Mod",
            "v1.2.testplan.md": "v1.2",
            "plan.txt": "plan",          # a plain-text ending goes
            "My.Mod.txt": "My.Mod",
            "plain": "plain",
            ".testplan.md": "My Mod",
            ".hidden": "My Mod",
        }
        for name, want in cases.items():
            with self.subTest(name=name):
                self.assertEqual(cli._mod_from_path(os.path.join("some dir", name)), want)

    def test_default_rules_name_shares_the_ending_rule(self):
        self.assertEqual(cli._default_rules_out("a.b.testplan.md"), "a.b.logrules.json")
        self.assertEqual(cli._default_rules_out("a.b.MD"), "a.b.logrules.json")
        self.assertEqual(cli._default_rules_out("a.b.txt"), "a.b.txt.logrules.json")

    def test_new_and_rules_use_the_dotted_name(self):
        with tempfile.TemporaryDirectory() as top:
            plan = os.path.join(top, "My.Mod.testplan.md")
            code, out, err = run("new", plan)
            self.assertEqual(code, 0, out + err)
            with open(plan, encoding="utf-8") as f:
                self.assertEqual(f.readline(), "# My.Mod test plan\n")

            nomod = os.path.join(top, "Dotted.Beacon.testplan.md")
            with open(EXAMPLE, encoding="utf-8") as f:
                body = "".join(line for line in f if not line.startswith("mod:"))
            with open(nomod, "w", encoding="utf-8") as f:
                f.write(body)
            code, out, err = run("rules", nomod)
            self.assertEqual(code, 0, out + err)
            rules_file = os.path.join(top, "Dotted.Beacon.logrules.json")
            self.assertTrue(os.path.exists(rules_file), out)
            with open(rules_file, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["mod"], "Dotted.Beacon")

    def test_verbose_logs_the_name_it_took(self):
        import logging
        with tempfile.TemporaryDirectory() as top:
            plan = os.path.join(top, "A.B.testplan.md")
            log = os.path.join(top, "run.log")
            code, out, err = run("new", plan, "--log", log)
            self.assertEqual(code, 0, out + err)
            logging.shutdown()
            with open(plan, encoding="utf-8") as f:
                self.assertEqual(f.readline(), "# A.B test plan\n")
            with open(log, encoding="utf-8") as f:
                text = f.read()
            self.assertIn("mod name 'A.B' from the file name 'A.B.testplan.md'", text)


if __name__ == "__main__":
    unittest.main()
