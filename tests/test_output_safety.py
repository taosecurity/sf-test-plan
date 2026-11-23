"""0.3.2: build, logs and rules write only a plain file they may write, and never over the plan, its results
file or (logs) the report. One refusal each, naming the file and the fix (exit 2, nothing written)."""
import io
import json
import os
import stat
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


class OutputSafety(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        self.write(self.plan, PLAN)
        self.rep = os.path.join(self.d, "r.json")
        self.write(self.rep, json.dumps(REPORT))
        self.results = results.results_path(self.plan)

    def tearDown(self):
        for name in os.listdir(self.d):
            path = os.path.join(self.d, name)
            if not os.path.islink(path) and os.path.isfile(path):
                os.chmod(path, stat.S_IREAD | stat.S_IWRITE)
        self._tmp.cleanup()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def read_only(self, path, text="keep"):
        self.write(path, text)
        os.chmod(path, stat.S_IREAD)
        if os.access(path, os.W_OK):
            self.skipTest("this account can write read-only files (root)")

    def as_link(self, target):
        """Make cli see target as a symbolic link (real links need extra rights on Windows)."""
        real = cli._is_link
        return mock.patch.object(cli, "_is_link", side_effect=lambda p: p == target or real(p))

    # The plan, its results file and the report are never written.
    def test_build_out_is_the_plan(self):
        code, out, err = run("build", self.plan, "--out", self.plan)
        self.assertEqual(code, 2)
        self.assertIn(f"--out {self.plan} is the plan itself. Give the page another name with --out.\n", err)
        self.assertEqual(self.read(self.plan), PLAN)

    def test_build_out_is_the_results_file(self):
        self.write(self.results, "[]")
        code, _, err = run("build", self.plan, "--out", self.results)
        self.assertEqual(code, 2)
        self.assertIn(f"--out {self.results} is the plan's results file. Give the page another name with --out.\n",
                      err)
        self.assertEqual(self.read(self.results), "[]")

    def test_logs_out_is_a_guarded_file(self):
        self.write(self.results, "[]")
        for target, what in ((self.plan, "the plan"), (self.rep, "the report"),
                             (self.results, "the plan's results file")):
            with self.subTest(target=os.path.basename(target)):
                before = self.read(target)
                code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", target)
                self.assertEqual(code, 2)
                self.assertEqual(out, "")
                self.assertIn(f"--out {target} is {what} itself. Give the marks file another name with --out.\n", err)
                self.assertEqual(self.read(target), before)

    def test_rules_out_is_the_results_file(self):
        self.write(self.results, "[]")
        code, _, err = run("rules", self.plan, "--out", self.results, "--force")
        self.assertEqual(code, 2)
        self.assertIn(f"--out {self.results} is the plan's results file. Give the rule file another name with "
                      f"--out.\n", err)

    def test_rules_from_the_plan_names_from(self):
        code, _, err = run("rules", self.plan, "--from", self.plan)
        self.assertEqual(code, 2)
        self.assertIn(f"--from {self.plan} is the plan itself. Without --out, the rule file is written back to the "
                      f"--from file, so give the rule file another name with --out.\n", err)

    # Symbolic links are refused.
    def test_build_default_page_that_is_a_link(self):
        page = cli._default_out(self.plan)
        self.write(page, "keep")
        with self.as_link(page):
            code, out, err = run("build", self.plan)
        self.assertEqual(code, 2)
        self.assertNotIn("Page:", out)
        self.assertIn(f"The default page {page} is a symbolic link, so nothing was written. Give the page another "
                      f"name with --out.\n", err)
        self.assertEqual(self.read(page), "keep")

    def test_logs_out_that_is_a_link(self):
        marks = os.path.join(self.d, "m.json")
        self.write(marks, "keep")
        with self.as_link(marks):
            code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", marks)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(f"--out {marks} is a symbolic link, so nothing was written.", err)
        self.assertEqual(self.read(marks), "keep")

    def test_build_and_logs_refuse_a_real_symlink(self):
        real = os.path.join(self.d, "real.txt")
        self.write(real, "keep")
        link = os.path.join(self.d, "link.out")
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"can't make a symlink here: {e}")
        for argv in (("build", self.plan, "--out", link), ("logs", self.rep, "--plan", self.plan, "--out", link)):
            with self.subTest(command=argv[0]):
                code, _, err = run(*argv)
                self.assertEqual(code, 2)
                self.assertIn("is a symbolic link, so nothing was written.", err)
                self.assertEqual(self.read(real), "keep")

    # Read-only files are refused, before anything is printed.
    def test_build_refuses_a_read_only_page(self):
        page = os.path.join(self.d, "page.html")
        self.read_only(page)
        code, out, err = run("build", self.plan, "--out", page)
        self.assertEqual(code, 2)
        self.assertNotIn("Page:", out)
        self.assertIn(f"--out {page} is read-only, so nothing was written. Give the page another name with --out, "
                      f"or clear its read-only setting.\n", err)
        self.assertEqual(self.read(page), "keep")

    def test_logs_refuses_a_read_only_marks_file(self):
        marks = os.path.join(self.d, "r.marks.json")
        self.read_only(marks)
        code, out, err = run("logs", self.rep, "--plan", self.plan)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(f"The default marks file {marks} is read-only, so nothing was written.", err)
        self.assertEqual(self.read(marks), "keep")

    def test_rules_refuses_a_read_only_output_even_with_force(self):
        target = os.path.join(self.d, "mine.logrules.json")
        self.read_only(target)
        code, out, err = run("rules", self.plan, "--out", target, "--force")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(f"--out {target} is read-only, so nothing was written. Give the rule file another name with "
                      f"--out, or clear its read-only setting.\n", err)
        self.assertEqual(self.read(target), "keep")

    # Something that isn't a regular file (a named pipe here) is refused.
    def test_build_refuses_a_special_file(self):
        if not hasattr(os, "mkfifo"):
            self.skipTest("no named pipes here")
        fifo = os.path.join(self.d, "pipe.html")
        os.mkfifo(fifo)
        code, _, err = run("build", self.plan, "--out", fifo)
        self.assertEqual(code, 2)
        self.assertIn(f"--out {fifo} isn't a regular file, so nothing was written.", err)

    # Plain files are still written: an existing writable page, and a file with another hard link.
    def test_build_overwrites_an_existing_plain_page(self):
        page = cli._default_out(self.plan)
        self.write(page, "old")
        code, out, err = run("build", self.plan)
        self.assertEqual(code, 0, err)
        self.assertIn(f"Page: {page}", out)
        self.assertIn("<html", self.read(page).lower())

    def test_build_writes_a_hard_linked_page_like_any_file(self):
        other = os.path.join(self.d, "other.html")
        self.write(other, "old")
        page = os.path.join(self.d, "page.html")
        try:
            os.link(other, page)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"hard links can't be made here: {e}")
        code, _, err = run("build", self.plan, "--out", page)
        self.assertEqual(code, 0, err)

    def test_no_hint_or_hard_link_helpers_left(self):
        for name in ("_free_name", "_plain_file", "_lstat", "_refuse_linked_output"):
            self.assertFalse(hasattr(cli, name), name)

    def test_docs_describe_the_checks(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        with open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8") as f:
            agents = f.read()
        for text in (readme, agents):
            self.assertIn("read-only", text)
            self.assertIn("symbolic link", text)
            self.assertNotIn("hard link", text)
            self.assertNotIn("file id", text)


if __name__ == "__main__":
    unittest.main()
