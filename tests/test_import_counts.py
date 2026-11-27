"""0.5.0 import fixes: a smoke round counts the unmarked deep checks as not run, a log mark never replaces the
tester's own mark or note, and `check --rules --verbose` names the rule file once."""
import io
import json
import logging
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse, results  # noqa: E402

PLAN = """# Lantern test plan
run: lantern-0.1.0

## 1 G
- [ ] Smoke one.
  smoke: yes
- [ ] Smoke two.
  smoke: yes
- [ ] Deep one.
- [ ] Deep two.
- [ ] Deep three.
"""


def marks(*checks):
    return {"run": "lantern-0.1.0", "checks": [dict({"n": "", "at": "", "src": "page"}, **c) for c in checks]}


class SmokeRoundNotRun(unittest.TestCase):
    def test_deep_checks_left_unmarked_count_as_not_run(self):
        # The real case: a smoke test, every smoke check marked Pass, three other checks never run.
        plan = parse.parse_text(PLAN)
        row = results.summarize(plan, marks({"id": "1.1", "r": "pass"}, {"id": "1.2", "r": "pass"}), "2026-11-27")
        self.assertEqual(row["test"], "Smoke test")
        self.assertEqual(row["happened"], "2 pass, 0 fail, 0 skip, 3 not run")


class LogNeverReplacesPageMark(unittest.TestCase):
    def test_newer_log_pass_keeps_the_testers_fail(self):
        plan = parse.parse_text(PLAN)
        row = results.summarize(plan, marks(
            {"id": "1.1", "r": "fail", "n": "forced stage", "at": "2026-11-27T10:00:00Z"},
            {"id": "1.1", "r": "pass", "at": "2026-11-27T11:00:00Z", "src": "log"}), "2026-11-27")
        self.assertIn("1 fail", row["happened"])
        self.assertIn("1.1 fail: forced stage", row["notes"])

    def test_log_mark_listed_first_does_not_win_either(self):
        plan = parse.parse_text(PLAN)
        row = results.summarize(plan, marks(
            {"id": "1.1", "r": "pass", "at": "2026-11-27T11:00:00Z", "src": "log"},
            {"id": "1.1", "r": "fail", "at": "2026-11-27T10:00:00Z"}), "2026-11-27")
        # An older page mark after a newer log mark: the time rule still decides, as on the page's own merge.
        self.assertIn("0 fail", row["happened"])

    def test_newer_log_mark_replaces_older_log_mark(self):
        plan = parse.parse_text(PLAN)
        row = results.summarize(plan, marks(
            {"id": "1.1", "r": "fail", "at": "2026-11-27T10:00:00Z", "src": "log"},
            {"id": "1.1", "r": "pass", "at": "2026-11-27T11:00:00Z", "src": "log"}), "2026-11-27")
        self.assertIn("1 pass", row["happened"])


class RuleFileVerboseOnce(unittest.TestCase):
    def test_rule_file_line_once(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "L.testplan.md")
            rules = os.path.join(d, "L.logrules.json")
            with open(plan, "w", encoding="utf-8", newline="\n") as f:
                f.write(PLAN)
            with open(rules, "w", encoding="utf-8") as f:
                json.dump({"expect": [{"id": "started", "re": "x"}]}, f)
            err, out = io.StringIO(), io.StringIO()
            with redirect_stderr(err), redirect_stdout(out):
                try:
                    cli.main(["check", plan, "--rules", rules, "--verbose"])
                finally:
                    logging.getLogger().handlers.clear()
                    logging.getLogger("sftestplan").handlers.clear()
            lines = [ln for ln in err.getvalue().splitlines() if "rule file" in ln and "ids" in ln]
            self.assertEqual(len(lines), 1, err.getvalue())


if __name__ == "__main__":
    unittest.main()
