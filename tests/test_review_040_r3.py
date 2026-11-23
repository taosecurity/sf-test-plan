"""0.4.0 /code-review round 3 fixes: New Game+ log ids get rules, a base plan's New Game+ section is refused, and a
Log check whose rule has no status says so."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sftestplan import parse, rules  # noqa: E402
from test_logchecks import PLAN, run  # noqa: E402
from test_ngplus import BASE, LANTERN  # noqa: E402


class NgplusLogIdsGetRules(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.plan = os.path.join(self.tmp.name, "Lantern.testplan.md")
        with open(self.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(LANTERN)

    def tearDown(self):
        self.tmp.cleanup()

    def test_plan_log_uses_has_ngplus_ids(self):
        self.assertIn("lantern-kept", rules.plan_log_uses(parse.parse_file(self.plan)))

    def test_rules_then_check_rules_passes(self):
        rf = os.path.join(self.tmp.name, "lantern-rules.json")
        code, out, err = run("rules", self.plan, "--out", rf)
        self.assertEqual(code, 0, out + err)
        with open(rf, encoding="utf-8") as f:
            ids = [r["id"] for r in json.load(f)["expect"]]
        self.assertIn("lantern-kept", ids)
        code, out, err = run("check", self.plan, "--rules", rf)
        self.assertEqual(code, 0, out + err)


class BaseNgplusRefused(unittest.TestCase):
    def test_base_with_ngplus_section_is_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            paths = {}
            for name, text in (("base", BASE + "\n## New Game+\n- [ ] Check the base after New Game+.\n"),
                               ("lantern", LANTERN)):
                paths[name] = os.path.join(d, f"{name}.testplan.md")
                with open(paths[name], "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
            order, out = os.path.join(d, "order.json"), os.path.join(d, "NewGamePlus.testplan.md")
            code, text, err = run("ngplus", "--base", paths["base"], "--order", order, "--out", out,
                                  paths["lantern"])
            self.assertEqual(code, 2, text + err)
            self.assertIn("New Game+ section", err)
            self.assertFalse(os.path.exists(out))
            self.assertFalse(os.path.exists(order))


class EmptyStatusWording(unittest.TestCase):
    def test_rule_with_no_status_is_not_called_missing(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "Lantern.testplan.md")
            with open(plan, "w", encoding="utf-8") as f:
                f.write(PLAN)
            rp = os.path.join(d, "report.json")
            with open(rp, "w", encoding="utf-8") as f:
                json.dump({"mods": [{"mod": "Lantern", "status": "LOADED", "rules": [
                    {"kind": "expect", "id": "started", "status": ""}]}]}, f)
            code, text, err = run("logs", rp, "--plan", plan, "--out", os.path.join(d, "m.json"))
            self.assertEqual(code, 0, text + err)
            self.assertIn("L.1 log check NOT SEEN: started has no status in the report.", text)
            self.assertIn("no-errors isn't in the report", text)


if __name__ == "__main__":
    unittest.main()
