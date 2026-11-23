"""0.3.2 code-review round 8: the hint skips an existing default name, the --from message, default-name wording."""
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


class Round8(unittest.TestCase):
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

    def link(self, target, path):
        if not hasattr(os, "link"):
            self.skipTest("no hard links here")
        try:
            os.link(target, path)
        except OSError:
            self.skipTest("can't make a hard link here")

    # Finding 1 and 2: a default name that already exists (and isn't protected) is not suggested.
    def test_free_name_skips_an_existing_default(self):
        default = os.path.join(self.d, "q.json")
        self.write(default, "x")
        self.assertEqual(cli._free_name(default, [self.plan]), os.path.join(self.d, "q-2.json"))

    def test_rules_hint_skips_an_existing_default_rule_file(self):
        default = cli._default_rules_out(self.plan)
        self.write(default, "{}")
        code, out, err = run("rules", self.plan, "--out", self.plan)
        self.assertEqual(code, 2, out + err)
        stem, ext = os.path.splitext(default)
        self.assertIn("such as " + stem + "-2" + ext + ".", err)
        self.assertEqual(self.read(self.plan), PLAN)

    # Finding 3 is documentation (README and CHANGELOG): a drive with file id 0 can't show hard links.
    def test_readme_names_the_file_id_zero_limit(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            self.assertIn("a hard link can't be detected there", f.read())

    # Finding 4: the --from refusal is two plain sentences, with no aside between subject and verb.
    def test_rules_from_plan_message_reads_plainly(self):
        code, out, err = run("rules", self.plan, "--from", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("--from " + self.plan + " is the plan itself. Without --out, the rule file is written back "
                      "to the --from file, so give it another name with --out, such as ", err)

    # Finding 5: the default-name wording for logs and rules.
    def test_logs_default_marks_file_linked_to_plan(self):
        default = os.path.splitext(self.rep)[0] + ".marks.json"
        self.link(self.plan, default)
        code, out, err = run("logs", self.rep, "--plan", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("The default marks file " + default + " is the plan itself.", err)
        self.assertEqual(self.read(self.plan), PLAN)

    def test_rules_default_rule_file_linked_to_plan(self):
        default = cli._default_rules_out(self.plan)
        self.link(self.plan, default)
        code, out, err = run("rules", self.plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("The default rule file " + default + " is the plan itself.", err)
        self.assertEqual(self.read(self.plan), PLAN)


if __name__ == "__main__":
    unittest.main()
