"""0.3.2 code-review round 11: the build and logs hints skip existing names that are hard-linked elsewhere,
read-only or Windows reparse points; build --out and logs --out refuse a symbolic link, as rules does."""
import io
import json
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from types import SimpleNamespace
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli  # noqa: E402

PLAN = "# T\nrun: a\n\n## 1 G\n- [ ] one\n  log: x\n"
REPORT = {"mods": [{"mod": "M", "status": "PASS", "rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Round11(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        self.write(self.plan, PLAN)
        self.rep = os.path.join(self.d, "r.json")
        self.write(self.rep, json.dumps(REPORT))

    def tearDown(self):
        for root, _, files in os.walk(self.d):
            for name in files:
                os.chmod(os.path.join(root, name), stat.S_IREAD | stat.S_IWRITE)
        self._tmp.cleanup()

    def write(self, path, text):
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

    def read(self, path):
        with open(path, encoding="utf-8") as f:
            return f.read()

    def second(self, path):
        stem, ext = os.path.splitext(path)
        return f"{stem}-2{ext}"

    def real_id(self, path):
        if os.stat(path).st_ino == 0:
            self.skipTest("this drive gives every file the id 0")

    # Finding 1: a default name that is a hard link to another (unprotected) file is never the hint.
    def test_build_hint_skips_a_hard_link_to_another_file(self):
        other = os.path.join(self.d, "notes.html")
        self.write(other, "keep")
        self.real_id(other)
        page = cli._default_out(self.plan)
        try:
            os.link(other, page)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"hard links can't be made here: {e}")
        code, out, err = run("build", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + self.second(page) + ".", err)
        self.assertEqual(self.read(other), "keep")

    def test_logs_hint_skips_a_hard_link_to_another_file(self):
        other = os.path.join(self.d, "notes.json")
        self.write(other, "keep")
        self.real_id(other)
        marks = os.path.splitext(self.rep)[0] + ".marks.json"
        try:
            os.link(other, marks)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"hard links can't be made here: {e}")
        code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + self.second(marks) + ".", err)

    # Finding 3: a Windows reparse point that isn't a symbolic link is never the hint.
    def test_free_name_skips_a_reparse_point(self):
        default = os.path.join(self.d, "q.html")
        self.write(default, "x")
        real_lstat = cli._lstat

        def reparse(p):
            st = real_lstat(p)
            return SimpleNamespace(st_mode=st.st_mode, st_ino=st.st_ino or 7, st_dev=st.st_dev, st_nlink=1,
                                   st_file_attributes=0x400)

        with mock.patch.object(cli, "_lstat", reparse):
            self.assertEqual(cli._free_name(default, [self.plan]), self.second(default))

    # Finding 4: a read-only file at the default name is never the hint (following it would only fail).
    def test_build_hint_skips_a_read_only_file(self):
        page = cli._default_out(self.plan)
        self.write(page, "old")
        self.real_id(page)
        os.chmod(page, stat.S_IREAD)
        if os.access(page, os.W_OK):
            self.skipTest("read-only files can still be written here (running as root?)")
        code, out, err = run("build", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + self.second(page) + ".", err)

    def test_free_name_still_keeps_a_writable_plain_file(self):
        default = os.path.join(self.d, "q.html")
        self.write(default, "x")
        self.real_id(default)
        self.assertEqual(cli._free_name(default, [self.plan]), default)

    # Finding 2: build --out and logs --out refuse a symbolic link, as rules does.
    def _as_link(self, target):
        real_islink = os.path.islink
        return mock.patch("sftestplan.cli.os.path.islink", side_effect=lambda p: p == target or real_islink(p))

    def test_build_refuses_a_link_as_the_output(self):
        page = os.path.join(self.d, "page.html")
        self.write(page, "keep")
        with self._as_link(page):
            code, out, err = run("build", self.plan, "--out", page)
        self.assertEqual(code, 2, out + err)
        self.assertIn(f"--out {page} is a symbolic link. Give the real file, or another name, with --out", err)
        self.assertEqual(self.read(page), "keep")

    def test_logs_refuses_a_link_as_the_output(self):
        marks = os.path.join(self.d, "m.json")
        self.write(marks, "keep")
        with self._as_link(marks):
            code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", marks)
        self.assertEqual(code, 2, out + err)
        self.assertIn(f"--out {marks} is a symbolic link.", err)
        self.assertEqual(out, "")
        self.assertEqual(self.read(marks), "keep")

    def test_build_refuses_a_real_symlink_as_the_output(self):
        other = os.path.join(self.d, "notes.html")
        self.write(other, "keep")
        page = os.path.join(self.d, "page.html")
        try:
            os.symlink(other, page)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"can't make a symlink here: {e}")
        code, out, err = run("build", self.plan, "--out", page)
        self.assertEqual(code, 2, out + err)
        self.assertIn("is a symbolic link", err)
        self.assertEqual(self.read(other), "keep")

    def test_docs_say_build_and_logs_refuse_links(self):
        with open(os.path.join(ROOT, "AGENTS.md"), encoding="utf-8") as f:
            agents = f.read()
        for cmd in ("build", "logs"):
            row = next(line for line in agents.splitlines() if line.startswith(f"| `{cmd}` |"))
            self.assertIn("refuses a symbolic link as the output", row, cmd)
        wanted = {"README.md": "an output that is a symbolic link is refused",
                  "CHANGELOG.md": "`build --out` and `logs --out` now refuse an output file that is a symbolic link"}
        for name, phrase in wanted.items():
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                self.assertIn(phrase, f.read(), name)


if __name__ == "__main__":
    unittest.main()
