"""The quest example (0.4.1) checks clean with its rule file, prints the summary the docs show, and its log: ids
are all in the rule file."""
import io
import json
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli  # noqa: E402

PLAN = os.path.join(ROOT, "examples", "QuestExample.testplan.md")
RULES = os.path.join(ROOT, "examples", "QuestExample.logrules.json")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class QuestExampleTests(unittest.TestCase):
    def test_check_matches_docs(self):
        code, out, err = run("check", PLAN, "--rules", RULES)
        self.assertEqual(code, 0, out + err)
        self.assertIn("5 groups, 10 checks, 5 smoke; 0 errors, 0 warnings", out)

    def test_log_ids_are_in_rule_file(self):
        with open(RULES, encoding="utf-8") as f:
            rules = json.load(f)
        ids = {r["id"] for r in rules["expect"] + rules["forbid"]}
        with open(PLAN, encoding="utf-8") as f:
            used = {line.split(":", 1)[1].strip() for line in f if line.strip().startswith("log:")}
        self.assertTrue(used)
        self.assertLessEqual(used, ids)


if __name__ == "__main__":
    unittest.main()
