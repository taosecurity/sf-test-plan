"""0.3.2 code-review round 10: the build and logs hints never name a folder, a link, or an existing file on a
drive with file id 0 (where a hard link to the plan can't be seen); the docs say so."""
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

from sftestplan import cli  # noqa: E402

PLAN = "# T\nrun: a\n\n## 1 G\n- [ ] one\n  log: x\n"
REPORT = {"mods": [{"mod": "M", "status": "PASS", "rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def _can_symlink(d):
    try:
        os.symlink(os.path.join(d, "nowhere"), os.path.join(d, ".probe"))
    except (OSError, NotImplementedError):
        return False
    os.remove(os.path.join(d, ".probe"))
    return True


class Round10(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.d = self._tmp.name
        self.plan = os.path.join(self.d, "p.testplan.md")
        self.write(self.plan, PLAN)
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

    def second(self, path):
        stem, ext = os.path.splitext(path)
        return f"{stem}-2{ext}"

    # Finding 1: a folder at the default name is never the hint.
    def test_build_hint_skips_a_folder_at_the_default_name(self):
        page = cli._default_out(self.plan)
        os.mkdir(page)
        code, out, err = run("build", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + self.second(page) + ".", err)

    def test_logs_hint_skips_a_folder_at_the_default_name(self):
        marks = os.path.splitext(self.rep)[0] + ".marks.json"
        os.mkdir(marks)
        code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + self.second(marks) + ".", err)

    # Finding 2: on a drive where every file has id 0, an existing default name is skipped.
    def test_free_name_skips_an_existing_name_with_file_id_0(self):
        default = os.path.join(self.d, "q.html")
        self.write(default, "x")
        real_stat = os.stat

        class Zero:
            def __init__(self, st):
                self._st = st
                self.st_ino = 0
                self.st_dev = st.st_dev
                self.st_mode = st.st_mode

        def fake_stat(p, *a, **k):
            st = real_stat(p, *a, **k)
            return Zero(st)

        with mock.patch.object(cli.os, "stat", fake_stat):
            self.assertEqual(cli._free_name(default, [self.plan]), self.second(default))

    def test_free_name_keeps_an_existing_plain_file_with_a_real_id(self):
        default = os.path.join(self.d, "q.html")
        self.write(default, "x")
        if os.stat(default).st_ino == 0:
            self.skipTest("this drive gives every file the id 0")
        self.assertEqual(cli._free_name(default, [self.plan]), default)

    # Finding 3: a link at the default name is never the hint.
    def test_build_hint_skips_a_link_at_the_default_name(self):
        if not _can_symlink(self.d):
            self.skipTest("symbolic links can't be made here")
        other = os.path.join(self.d, "notes.html")
        self.write(other, "keep")
        page = cli._default_out(self.plan)
        os.symlink(other, page)
        code, out, err = run("build", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + self.second(page) + ".", err)
        self.assertEqual(self.read(other), "keep")

    # Finding 4: the docs say the hint is never a folder or a link, and is a new name on a file id 0 drive.
    def test_docs_describe_the_hint(self):
        for name in ("README.md", "CHANGELOG.md"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                text = f.read()
            self.assertIn("a folder or a link", text, name)
            self.assertIn("only the same path is refused, and the suggested name is one that doesn't exist yet",
                          text, name)


if __name__ == "__main__":
    unittest.main()
