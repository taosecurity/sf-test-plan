"""0.3.2 code-review round 6: rules --out may not be the results file; hints name a free file; hard links."""
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


class Round6(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        with open(self.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(PLAN)
        self.res = results.results_path(self.plan)
        with open(self.res, "w", encoding="utf-8") as f:
            f.write("[]")

    def tearDown(self):
        self._tmp.cleanup()

    def res_text(self):
        with open(self.res, encoding="utf-8") as f:
            return f.read()

    def test_rules_out_is_the_results_file(self):
        code, out, err = run("rules", self.plan, "--out", self.res, "--force")
        self.assertEqual(code, 2, out + err)
        self.assertIn("results file", err)
        self.assertEqual(self.res_text(), "[]")

    @unittest.skipUnless(hasattr(os, "link"), "no hard links here")
    def test_logs_refusal_hint_is_another_name(self):
        # The default marks name is itself a hard link to the plan, so the hint must not name it (round 7:
        # the round 6 version of this test used a case where the old hint was already different).
        rep = os.path.join(self.d, "r.json")
        with open(rep, "w", encoding="utf-8") as f:
            json.dump(REPORT, f)
        default = os.path.join(self.d, "r.marks.json")
        try:
            os.link(self.plan, default)
        except OSError:
            self.skipTest("can't make a hard link here")
        code, out, err = run("logs", rep, "--plan", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + os.path.join(self.d, "r.marks-2.json") + ".", err)

    def test_free_name_avoids_protected_files(self):
        taken = os.path.join(self.d, "q.html")
        self.assertEqual(cli._free_name(taken, [taken]), os.path.join(self.d, "q-2.html"))
        self.assertEqual(cli._free_name(taken, [self.plan]), taken)

    @unittest.skipUnless(hasattr(os, "link"), "no hard links here")
    def test_hard_link_to_the_plan_is_refused(self):
        link = os.path.join(self.d, "page.html")
        try:
            os.link(self.plan, link)
        except OSError:
            self.skipTest("can't make a hard link here")
        code, out, err = run("build", self.plan, "--out", link)
        self.assertEqual(code, 2, out + err)
        with open(self.plan, encoding="utf-8") as f:
            self.assertEqual(f.read(), PLAN)


if __name__ == "__main__":
    unittest.main()
