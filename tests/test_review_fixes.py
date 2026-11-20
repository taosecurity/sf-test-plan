"""Tests for the /code-review (medium) findings fixed on 2026-11-19."""
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse  # noqa: E402

ENTRY = os.path.join(ROOT, "sf_test_plan.py")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ParserFixes(unittest.TestCase):
    def test_check_before_first_group_is_an_error(self):
        p = parse.parse_text("# T\nrun: a\n\n- [ ] lost check\n\n## 1 G\n- [ ] one\n")
        self.assertIn(("check-outside-group", 4), [(x.code, x.line) for x in p.problems])
        self.assertNotIn("lost check", p.intro)

    def test_check_in_before_you_start_is_an_error(self):
        p = parse.parse_text("# T\nrun: a\n\n## Before you start\n- [ ] not a step\n\n## 1 G\n- [ ] one\n")
        self.assertIn("check-outside-group", [x.code for x in p.errors()])
        self.assertEqual(p.setup, [])

    def test_blank_line_ends_the_header(self):
        p = parse.parse_text("# T\nrun: a\n\nWarning: back up your saves.\nmod: not a key here\n\n## 1 G\n- [ ] one\n")
        self.assertEqual(p.problems, [])
        self.assertIn("Warning: back up your saves.", p.intro)
        self.assertEqual(p.mod, "")

    def test_keys_may_still_follow_a_blank_line_after_the_title(self):
        p = parse.parse_text("# T\n\nrun: a\nmod: M\n\n## 1 G\n- [ ] one\n")
        self.assertEqual((p.run, p.mod), ("a", "M"))
        self.assertEqual(p.errors(), [])

    def test_wrapped_log_line_adds_ids(self):
        p = parse.parse_text("# T\nrun: a\n\n## 1 G\n- [ ] one\n  log: a,\n    b\n")
        c = p.checks()[0]
        self.assertEqual((c.step, c.log), ("one", ["a", "b"]))


class SecondReviewFixes(unittest.TestCase):
    """The public-commit /code-review (medium), 2026-11-19."""

    def test_plan_id_in_config_names_the_plan(self):
        from sftestplan import render
        a = parse.parse_text("# A\nrun: r1\n\n## 1 G\n- [ ] one\n")
        b = parse.parse_text("# B\nrun: r1\n\n## 1 G\n- [ ] one\n")

        def cfg(p):
            h = render.render(p)
            s = h.index('id="tp-config">') + len('id="tp-config">')
            return json.loads(h[s:h.index("</script>", s)])
        ca, cb = cfg(a), cfg(b)
        self.assertRegex(ca["plan"], r"^[0-9a-f]{12}$")
        self.assertNotEqual(ca["plan"], cb["plan"])          # same run, different plans: different storage keys
        self.assertEqual(ca["plan"], cfg(parse.parse_text("# A\nrun: r1\n\n## 1 G\n- [ ] one\n- [ ] two\n"))["plan"])
        # from a file, the key is the file name and run: a title edit keeps it, two plans for one mod differ
        def from_file(name, title):
            p = parse.parse_text(f"# {title}\nrun: r1\nmod: Astrid Reloaded\n\n## 1 G\n- [ ] one\n",
                                 path=os.path.join("plans", name))
            return cfg(p)["plan"]
        self.assertEqual(from_file("Astrid.testplan.md", "Astrid test"), from_file("Astrid.testplan.md", "Astrid tests"))
        self.assertNotEqual(from_file("Astrid.testplan.md", "Astrid test"),
                            from_file("AstridRomance.testplan.md", "Astrid Romance test"))
        # two testplan.md files in different mod folders differ by mod
        def by_mod(mod):
            p = parse.parse_text(f"# T\nrun: r1\nmod: {mod}\n\n## 1 G\n- [ ] one\n", path=os.path.join(mod, "testplan.md"))
            return cfg(p)["plan"]
        self.assertNotEqual(by_mod("ModA"), by_mod("ModB"))
        # ... and without a mod: line, by folder
        def no_mod(folder):
            p = parse.parse_text("# T\nrun: r1\n\n## 1 G\n- [ ] one\n", path=os.path.join(folder, "testplan.md"))
            return cfg(p)["plan"]
        self.assertNotEqual(no_mod("ModA"), no_mod("ModB"))
        # mod case and spaces don't matter
        p1 = parse.parse_text("# T\nrun: r1\nmod: Astrid  Reloaded\n\n## 1 G\n- [ ] one\n", path=os.path.join("A", "t.md"))
        p2 = parse.parse_text("# T\nrun: r1\nmod: astrid reloaded\n\n## 1 G\n- [ ] one\n", path=os.path.join("A", "t.md"))
        self.assertEqual(cfg(p1)["plan"], cfg(p2)["plan"])

    def test_all_smoke_group_keeps_its_intro(self):
        from sftestplan import render
        p = parse.parse_text("# T\nrun: a\n\n## 1 G\n- [ ] one\n  smoke: yes\n- [ ] two\n\n"
                             "## 3 Save and load\nUse a save made before installing the mod.\n\n- [ ] Load it.\n  smoke: yes\n")
        h = render.render(p)
        self.assertIn("Use a save made before installing the mod.", h)
        # the precondition comes first; the step is div.step (the page script reads the step text from it)
        self.assertIn('Use a save made before installing the mod.</div><div class="step">Load it.</div>', h)

    def test_cr_only_line_numbers_after_a_comment(self):
        text = "# T\nrun: a\n\n<!-- two\nlines -->\n## 1 G\n- [ ] one\n## 1 Again\n- [ ] two\n"
        want = [(x.code, x.line) for x in parse.parse_text(text).problems]
        got = [(x.code, x.line) for x in parse.parse_text(text.replace("\n", "\r")).problems]
        self.assertEqual(got, want)
        self.assertIn(("dup-group", 8), got)


class CliFixes(unittest.TestCase):
    def test_non_ascii_output_through_a_pipe(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "p.md")
            with open(plan, "w", encoding="utf-8") as f:
                f.write("# Tëst → plan\nrun: b→\n\n## 1 G\n- [ ] one\n")
            env = dict(os.environ, PYTHONIOENCODING="cp1252")
            p = subprocess.run([sys.executable, "-I", ENTRY, "check", plan], capture_output=True, env=env)
            self.assertEqual(p.returncode, 1, p.stderr)          # bad-run is a plan error, not a crash
            self.assertNotIn(b"Traceback", p.stderr)
            self.assertIn("bad-run", p.stdout.decode("utf-8"))

    def test_logs_reads_a_utf16_report(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "p.md")
            with open(plan, "w", encoding="utf-8") as f:
                f.write("# T\nrun: a\nmod: M\n\n## 1 G\n- [ ] one\n  log: x\n")
            rep = os.path.join(d, "r.json")
            with open(rep, "w", encoding="utf-16") as f:     # with a BOM, as PowerShell's '>' writes
                json.dump({"mods": [{"mod": "M", "status": "PASS", "rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}, f)
            code, out, err = run("logs", rep, "--plan", plan)
            self.assertEqual(code, 0, out + err)
            self.assertIn("1.1 pass", out)

    def test_logs_bad_bytes_is_exit_2(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "p.md")
            with open(plan, "w", encoding="utf-8") as f:
                f.write("# T\nrun: a\n\n## 1 G\n- [ ] one\n")
            rep = os.path.join(d, "r.json")
            with open(rep, "wb") as f:
                f.write(b"\x80\x81\x82 not text")
            code, out, err = run("logs", rep, "--plan", plan)
            self.assertEqual(code, 2)
            self.assertIn("isn't UTF-8", err)


if __name__ == "__main__":
    unittest.main()
