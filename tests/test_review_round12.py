"""0.3.2 code-review round 12: build and logs refuse an existing output with another hard link; the rules link
refusal names where the path came from and gives a hint; the docs say what is checked."""
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


class Round12(unittest.TestCase):
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

    def hard_link(self, other, name):
        self.write(other, "keep")
        if os.stat(other).st_ino == 0:
            self.skipTest("this drive gives every file the id 0")
        try:
            os.link(other, name)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"hard links can't be made here: {e}")

    # Finding 2: writing a hard-linked output would change the other file too.
    def test_build_refuses_a_default_page_with_another_hard_link(self):
        other = os.path.join(self.d, "notes.html")
        page = cli._default_out(self.plan)
        self.hard_link(other, page)
        code, out, err = run("build", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn(f"The default page {page} has another hard link, so writing it would change that other file "
                      "too. Give another name with --out, such as ", err)
        self.assertEqual(self.read(other), "keep")

    def test_logs_refuses_an_out_with_another_hard_link(self):
        other = os.path.join(self.d, "notes.json")
        marks = os.path.join(self.d, "m.json")
        self.hard_link(other, marks)
        code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", marks)
        self.assertEqual(code, 2, out + err)
        self.assertIn(f"--out {marks} has another hard link", err)
        self.assertEqual(out, "")
        self.assertEqual(self.read(other), "keep")

    def test_build_still_writes_an_existing_plain_page(self):
        page = cli._default_out(self.plan)
        self.write(page, "old")
        code, out, err = run("build", self.plan)
        self.assertEqual(code, 0, out + err)
        self.assertNotEqual(self.read(page), "old")

    # Finding 3: the rules link refusal names where the path came from and suggests a name.
    def test_rules_link_refusal_names_out_and_a_hint(self):
        target = os.path.join(self.d, "linked.json")
        real_is_link = cli._is_link
        with mock.patch.object(cli, "_is_link", side_effect=lambda p: p == target or real_is_link(p)):
            code, out, err = run("rules", self.plan, "--out", target)
        self.assertEqual(code, 2, out + err)
        hint = os.path.join(self.d, "p.logrules.json")
        self.assertIn(f"--out {target} is a symbolic link. Give the rule file another name with --out, such as "
                      f"{hint}, or give the real file with --out.", err)
        self.assertEqual(out, "")

    def test_docs_describe_the_checks(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            readme = f.read()
        self.assertIn("`rules` refuses a symbolic link as its output only when it would write", readme)
        self.assertIn("has another hard link", readme)
        self.assertNotIn("a plain file you can write", readme)
        with open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8") as f:
            changelog = f.read()
        self.assertIn("`build` and `logs` now refuse an existing output that has another hard link", changelog)
        self.assertNotIn("a plain file you can write", changelog)


if __name__ == "__main__":
    unittest.main()
