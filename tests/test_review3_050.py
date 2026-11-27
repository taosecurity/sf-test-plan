"""0.5.0 code review round 3 fixes: `logs`, the README and AGENTS.md no longer offer `import` on the logs marks file
alone (it holds none of the tester's page marks), and the quest example sets the order check's Fail before Export."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from test_logchecks import PLAN, run  # noqa: E402


def read(rel):
    with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
        return f.read()


class LogsHintTest(unittest.TestCase):
    def test_logs_says_export_then_import(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "Lantern.testplan.md")
            with open(plan, "w", encoding="utf-8") as f:
                f.write(PLAN)
            rp = os.path.join(d, "report.json")
            with open(rp, "w", encoding="utf-8") as f:
                json.dump({"mods": [{"mod": "Lantern", "status": "LOADED", "rules": [
                    {"kind": "expect", "id": "started", "status": "PASS"}]}]}, f)
            out = os.path.join(d, "marks.json")
            code, text, err = run("logs", rp, "--plan", plan, "--out", out)
        self.assertEqual(code, 0, text + err)
        (line,) = [ln for ln in text.splitlines() if ln.startswith("Marks: ")]
        self.assertIn("then Export", line)
        self.assertNotIn("import " + out, line)   # never the logs file itself


class DocsTest(unittest.TestCase):
    def test_docs_do_not_offer_import_on_the_logs_file(self):
        for rel in ("README.md", "AGENTS.md"):
            text = read(rel)
            self.assertNotIn("or with `import`", text, rel)
            self.assertNotIn("use Import, or run: sf-test-plan import logcheck", text, rel)

    def test_quest_example_sets_order_fail_before_export(self):
        text = read(os.path.join("examples", "QuestExample.testplan.md"))
        para = [p for p in text.split("\n\n") if p.startswith("`sf-test-plan logs` turns the report")][0]
        self.assertLess(para.index("order check"), para.index("Then use Export"))


if __name__ == "__main__":
    unittest.main()
