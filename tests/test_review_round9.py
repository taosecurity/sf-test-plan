"""0.3.2 code-review round 9: build and logs keep their usual default name in the hint, the --from wording,
the file id 0 drives in the docs."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

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


class Round9(unittest.TestCase):
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

    # Findings 1 and 3: build and logs overwrite their output, so an existing default page or marks file
    # is still the name the hint gives.
    def test_free_name_keeps_an_existing_default_without_skip(self):
        default = os.path.join(self.d, "q.json")
        self.write(default, "x")
        self.assertEqual(cli._free_name(default, [self.plan]), default)

    def test_build_hint_keeps_an_existing_default_page(self):
        page = cli._default_out(self.plan)
        self.write(page, "<html></html>")
        code, out, err = run("build", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + page + ".", err)
        self.assertEqual(self.read(self.plan), PLAN)

    def test_logs_hint_keeps_an_existing_default_marks_file(self):
        marks = os.path.splitext(self.rep)[0] + ".marks.json"
        self.write(marks, "{}")
        code, out, err = run("logs", self.rep, "--plan", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("such as " + marks + ".", err)
        self.assertEqual(self.read(self.plan), PLAN)

    # Finding 2: the docstring says which caller skips names on disk.
    def test_free_name_docstring_names_the_rules_caller(self):
        self.assertIn("skip_existing (rules", cli._free_name.__doc__)

    # Finding 4: the --from fix sentence names the rule file, not "it".
    def test_rules_from_fix_names_the_rule_file(self):
        code, out, err = run("rules", self.plan, "--from", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("so give the rule file another name with --out", err)
        self.assertNotIn("give it another name", err)

    # Finding 5: README and CHANGELOG list WSL folders among the drives with file id 0.
    def test_docs_name_wsl_folders(self):
        for name in ("README.md", "CHANGELOG.md"):
            with open(os.path.join(ROOT, name), encoding="utf-8") as f:
                self.assertIn("WSL folders (`\\\\wsl$`)", f.read(), name)


if __name__ == "__main__":
    unittest.main()
