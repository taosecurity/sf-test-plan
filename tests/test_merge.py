"""Master tests added at the C4 merge: wrapped lines follow the field above, unclosed comments warn,
and the example plan goes through build, logs and import end to end."""
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse, results  # noqa: E402

PLAN = """# T test plan
run: t-1

## 1 G
- [ ] Do the thing
  that wraps.
  Expect: you see a
  long message.
  note: a hint
  that wraps too.
- [ ] Second.
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class WrapTests(unittest.TestCase):
    def test_wrapped_lines_follow_the_field_above(self):
        p = parse.parse_text(PLAN)
        c = p.checks()[0]
        self.assertEqual(c.step, "Do the thing that wraps.")
        self.assertEqual(c.expect, "you see a long message.")
        self.assertEqual(c.note, "a hint that wraps too.")
        self.assertEqual(p.checks()[1].step, "Second.")
        self.assertEqual(p.errors(), [])

    def test_unclosed_comment_warns(self):
        p = parse.parse_text(PLAN + "<!-- oops\n- [ ] Hidden.\n")
        codes = [(x.code, x.line) for x in p.problems]
        self.assertIn(("unclosed-comment", 12), codes)
        self.assertEqual(len(p.checks()), 2)


class EndToEndTests(unittest.TestCase):
    def test_example_build_logs_import(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "Beacon.testplan.md")
            shutil.copy(os.path.join(ROOT, "examples", "Beacon.testplan.md"), plan)
            code, out, err = run("build", plan, "--rules", os.path.join(ROOT, "examples", "Beacon.logrules.json"))
            self.assertEqual(code, 0, out + err)
            page = os.path.join(d, "Beacon.testplan.html")
            with open(page, encoding="utf-8") as f:
                html = f.read()
            self.assertIn('id="tp-config"', html)
            self.assertIn("sfTestplan", html)          # page.js inlined
            report = {"mods": [{"mod": "Beacon Mod", "status": "PASS", "rules": [
                {"kind": "expect", "id": "loaded", "status": "PASS"},
                {"kind": "expect", "id": "placed", "status": "FAIL"},
                {"kind": "expect", "id": "restored", "status": "NOT SEEN"}]}]}
            rp = os.path.join(d, "logcheck.json")
            with open(rp, "w", encoding="utf-8") as f:
                json.dump(report, f)
            code, out, err = run("logs", rp, "--plan", plan)
            self.assertEqual(code, 0, out + err)
            marks = os.path.join(d, "logcheck.marks.json")
            code, out, err = run("import", marks, "--plan", plan)
            self.assertEqual(code, 0, out + err)
            rows = results.load_results(plan)
            self.assertEqual(len(rows), 1)
            self.assertIn("1 pass, 1 fail", rows[0]["happened"])
            code, out, err = run("build", plan)        # the results log now shows on the page
            self.assertEqual(code, 0, out + err)
            with open(page, encoding="utf-8") as f:
                self.assertIn('id="results"', f.read())

    def test_new_plan_is_valid(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "MyMod.testplan.md")
            code, out, err = run("new", plan, "--mod", "My Mod")
            self.assertEqual(code, 0, out + err)
            p = parse.parse_file(plan)
            self.assertEqual(p.errors(), [], [x.message for x in p.problems])
            self.assertTrue(p.smoke())
            code, out, err = run("build", plan)
            self.assertEqual(code, 0, out + err)


if __name__ == "__main__":
    unittest.main()
