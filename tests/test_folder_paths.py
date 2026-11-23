"""A folder given where a file belongs gets a plain message (on Windows it was 'Permission denied')."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli  # noqa: E402

PLAN = "# T\nrun: a\n\n## 1 G\n- [ ] one\n"


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class FolderPaths(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        with open(self.plan, "w", encoding="utf-8") as f:
            f.write(PLAN)

    def tearDown(self):
        self._tmp.cleanup()

    def assert_folder_message(self, argv):
        code, out, err = run(*argv)
        self.assertEqual(code, 2, out + err)
        self.assertIn("is a folder", err)
        self.assertNotIn("Permission denied", err)

    def test_plan_is_a_folder(self):
        for cmd in ("check", "build", "rules"):
            with self.subTest(cmd=cmd):
                self.assert_folder_message([cmd, self.d])

    def test_marks_and_report_are_folders(self):
        self.assert_folder_message(["import", self.d, "--plan", self.plan])
        self.assert_folder_message(["logs", self.d, "--plan", self.plan])

    def test_rule_file_is_a_folder(self):
        self.assert_folder_message(["check", self.plan, "--rules", self.d])

    def test_build_out_is_a_folder(self):
        self.assert_folder_message(["build", self.plan, "--out", self.d])

    def test_logs_out_is_a_folder(self):
        rep = os.path.join(self.d, "r.json")
        with open(rep, "w", encoding="utf-8") as f:
            f.write('{"mods": [{"mod": "M", "status": "PASS", '
                    '"rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}')
        code, out, err = run("logs", rep, "--plan", self.plan, "--out", self.d)
        self.assertEqual(code, 2, out + err)
        self.assertIn("is a folder", err)

    def test_logs_out_folder_prints_no_report_lines(self):
        rep = os.path.join(self.d, "r.json")
        with open(rep, "w", encoding="utf-8") as f:
            f.write('{"mods": [{"mod": "M", "status": "PASS", '
                    '"rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}')
        code, out, err = run("logs", rep, "--plan", self.plan, "--out", self.d)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")

    def test_rules_out_is_a_folder(self):
        with open(self.plan, "w", encoding="utf-8") as f:
            f.write("# T\nrun: a\nmod: M\n\n## 1 G\n- [ ] one\n  log: x\n")
        for extra in ([], ["--force"]):
            with self.subTest(extra=extra):
                code, out, err = run("rules", self.plan, "--out", self.d, *extra)
                self.assertEqual(code, 2, out + err)
                self.assertIn("is a folder", err)
                self.assertNotIn("already exists", err)
                self.assertEqual(out, "")

    def test_rules_out_is_a_folder_even_without_log_lines(self):
        code, out, err = run("rules", self.plan, "--out", self.d)
        self.assertEqual(code, 2, out + err)
        self.assertIn("is a folder", err)
        self.assertEqual(out, "")

    def test_new_plan_is_a_folder(self):
        for extra in ([], ["--force"]):
            with self.subTest(extra=extra):
                code, out, err = run("new", self.d, *extra)
                self.assertEqual(code, 2, out + err)
                self.assertIn("is a folder", err)
                self.assertNotIn("already exists", err)

    def test_new_in_a_missing_folder_says_how_to_fix(self):
        code, out, err = run("new", os.path.join(self.d, "nope", "M.testplan.md"))
        self.assertEqual(code, 2)
        self.assertIn("Check that the folder exists", err)


if __name__ == "__main__":
    unittest.main()
