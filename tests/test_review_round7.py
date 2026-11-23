"""0.3.2 code-review round 7: file id 0, free hint names, which option a refusal names, hard links for logs and rules."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

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


class Round7(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        self.write(self.plan, PLAN)
        self.res = results.results_path(self.plan)
        self.write(self.res, "[]")
        self.rep = os.path.join(self.d, "r.json")
        self.write(self.rep, json.dumps(REPORT))

    def tearDown(self):
        self._tmp.cleanup()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def link(self, target, name):
        if not hasattr(os, "link"):
            self.skipTest("no hard links here")
        path = os.path.join(self.d, name)
        try:
            os.link(target, path)
        except OSError:
            self.skipTest("can't make a hard link here")
        return path

    # Finding 1: a drive that gives every file the id 0 must not make every file "the plan".
    def test_file_id_zero_is_not_the_same_file(self):
        page = os.path.join(self.d, "p.testplan.html")
        self.write(page, "old")
        real_stat = os.stat

        def fake_stat(path, *a, **k):
            st = real_stat(path, *a, **k)
            if os.path.basename(str(path)) in ("p.testplan.md", "p.testplan.html", "p.testplan.results.json"):
                return os.stat_result((st.st_mode, 0, 7) + tuple(st)[3:])
            return st

        with mock.patch("os.stat", fake_stat):
            self.assertFalse(cli._same_file(page, self.plan))
            code, out, err = run("build", self.plan)
        self.assertEqual(code, 0, out + err)
        self.assertNotEqual(self.read(page), "old")

    # Finding 2 is in test_review_round6 (the hint test now has a case it can fail on).

    # Finding 3: without --out, a refusal names --from (or the default file), not --out.
    def test_rules_from_results_file_names_from(self):
        code, out, err = run("rules", self.plan, "--from", self.res)
        self.assertEqual(code, 2, out + err)
        self.assertIn("--from " + self.res, err)
        self.assertNotIn("--out " + self.res, err)
        self.assertEqual(self.read(self.res), "[]")

    def test_rules_from_plan_names_from(self):
        code, out, err = run("rules", self.plan, "--from", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("--from " + self.plan, err)
        self.assertNotIn("--out " + self.plan, err)

    def test_default_page_linked_to_plan_names_the_default(self):
        self.link(self.plan, "p.testplan.html")
        code, out, err = run("build", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("The default page", err)
        self.assertNotIn("--out " + os.path.join(self.d, "p.testplan.html") + " is", err)
        self.assertEqual(self.read(self.plan), PLAN)

    # Finding 4: the hint skips names that are already on disk.
    def test_free_name_skips_files_on_disk(self):
        taken = os.path.join(self.d, "q.json")
        self.write(os.path.join(self.d, "q-2.json"), "x")
        self.assertEqual(cli._free_name(taken, [taken]), os.path.join(self.d, "q-3.json"))

    # Finding 5: hard links for logs --out and rules --out.
    def test_logs_out_hard_link_to_plan_report_or_results(self):
        for target in (self.plan, self.rep, self.res):
            with self.subTest(target=os.path.basename(target)):
                before = self.read(target)
                link = self.link(target, "link-" + os.path.basename(target))
                code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", link)
                self.assertEqual(code, 2, out + err)
                self.assertEqual(self.read(target), before)

    def test_rules_out_hard_link_to_results(self):
        link = self.link(self.res, "rules.json")
        code, out, err = run("rules", self.plan, "--out", link, "--force")
        self.assertEqual(code, 2, out + err)
        self.assertIn("results file", err)
        self.assertEqual(self.read(self.res), "[]")


if __name__ == "__main__":
    unittest.main()
