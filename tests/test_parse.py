"""C1: the plan parser and linter (FORMAT.md section 1)."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import model, parse  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "Beacon.testplan.md")
RULES = os.path.join(ROOT, "examples", "Beacon.logrules.json")

HEAD = "# T\nrun: r-1\n\n"


def codes(plan):
    return [(p.code, p.line) for p in plan.problems]


def code_set(plan):
    return {p.code for p in plan.problems}


class ExampleTests(unittest.TestCase):
    def test_example_parses_clean(self):
        plan = parse.parse_file(EXAMPLE, parse.load_rule_ids(RULES))
        self.assertEqual(plan.problems, [])
        self.assertEqual(plan.title, "Beacon Mod test plan")
        self.assertEqual((plan.run, plan.mod, plan.version, plan.zip),
                         ("beacon-0.1.0", "Beacon Mod", "0.1.0", "BeaconMod-0.1.0.zip"))
        self.assertEqual(plan.path, EXAMPLE)
        self.assertEqual([g.number for g in plan.groups], [1, 2, 3])
        self.assertEqual([c.id for c in plan.checks()], ["1.1", "1.2", "2.1", "2.2", "2.3", "3.1"])
        self.assertEqual([c.id for c in plan.smoke()], ["1.1", "1.2", "2.1", "2.2", "3.1"])
        self.assertEqual(len(plan.setup), 2)
        self.assertIn("made-up example mod", plan.intro)
        self.assertEqual(plan.groups[0].intro, "These checks prove the mod loads.")
        c = plan.checks()[0]
        self.assertEqual(c.step, "Start a new game and finish the character creator.")
        self.assertEqual(c.expect, "no error message about Beacon Mod.")
        self.assertEqual(c.log, ["loaded"])
        self.assertTrue(plan.checks()[4].note.startswith("Try it in a building"))


class HeaderTests(unittest.TestCase):
    def test_no_title(self):
        plan = parse.parse_text("run: a\n## 1 G\n- [ ] x\n")
        self.assertIn(("no-title", 0), codes(plan))
        self.assertEqual(plan.run, "a")

    def test_no_run(self):
        plan = parse.parse_text("# T\n## 1 G\n- [ ] x\n")
        self.assertEqual(codes(plan), [("no-run", 0)])

    def test_bad_run(self):
        for bad in ("has space", "a/b", "x" * 65, ""):
            plan = parse.parse_text(f"# T\nrun: {bad}\n## 1 G\n- [ ] x\n")
            self.assertEqual(codes(plan), [("bad-run", 2)], bad)
        plan = parse.parse_text("# T\nrun: " + "x" * 64 + "\n## 1 G\n- [ ] x\n")
        self.assertEqual(plan.problems, [])

    def test_keys_case_insensitive_and_unknown(self):
        plan = parse.parse_text("# T\nRUN: a\nMod: M\nauthor: me\n## 1 G\n- [ ] x\n")
        self.assertEqual(plan.run, "a")
        self.assertEqual(plan.mod, "M")
        self.assertEqual(codes(plan), [("unknown-key", 4)])
        self.assertEqual(plan.problems[0].level, "warning")

    def test_intro_after_header(self):
        plan = parse.parse_text(HEAD + "Para one\nline two.\n\nNote: still intro.\n## 1 G\n- [ ] x\n")
        self.assertEqual(plan.intro, "Para one line two.\n\nNote: still intro.")
        self.assertEqual(plan.problems, [])

    def test_url_line_is_not_a_key(self):
        plan = parse.parse_text("# T\nrun: a\nhttps://example.com\n## 1 G\n- [ ] x\n")
        self.assertEqual(plan.problems, [])
        self.assertEqual(plan.intro, "https://example.com")


class GroupTests(unittest.TestCase):
    def test_group_no_number(self):
        plan = parse.parse_text(HEAD + "## Install\n- [ ] a\n## 1 G\n- [ ] x\n")
        self.assertEqual(codes(plan), [("group-no-number", 4)])
        self.assertIn("## 1 Install", plan.problems[0].message)
        self.assertEqual([c.id for c in plan.checks()], ["1.1"])

    def test_setup_heading_any_case(self):
        plan = parse.parse_text(HEAD + "## BEFORE YOU START\n- one\n* two\n  more\n## 1 G\n- [ ] x\n")
        self.assertEqual(plan.setup, ["one", "two more"])
        self.assertEqual(plan.problems, [])

    def test_dup_group(self):
        plan = parse.parse_text(HEAD + "## 1 A\n- [ ] a\n## 1 B\n- [ ] b\n")
        self.assertEqual(codes(plan), [("dup-group", 6)])
        self.assertEqual(len(plan.groups), 1)
        self.assertIn("line 4", plan.problems[0].message)

    def test_groups_out_of_order_with_gaps(self):
        plan = parse.parse_text(HEAD + "## 5 A\n- [ ] a\n## 2 B\n- [ ] b\n")
        self.assertEqual(plan.problems, [])
        self.assertEqual([c.id for c in plan.checks()], ["5.1", "2.1"])

    def test_empty_group(self):
        plan = parse.parse_text(HEAD + "## 1 A\nJust words.\n## 2 B\n- [ ] b\n")
        self.assertEqual(codes(plan), [("empty-group", 4)])
        self.assertEqual(plan.problems[0].level, "warning")
        self.assertEqual(plan.groups[0].intro, "Just words.")

    def test_no_checks(self):
        plan = parse.parse_text(HEAD + "Words.\n")
        self.assertEqual(codes(plan), [("no-checks", 0)])


class CheckTests(unittest.TestCase):
    def test_keys_and_continuation(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [x] Do\n  this.\n  Expect: one\n  Expect: two\n\tnote: hint\n"
                                "  SMOKE: Yes\n  log: a, b c\n  log: a\n* [ ] Next\n")
        self.assertEqual(plan.problems, [])
        c, d = plan.checks()
        self.assertEqual(c.step, "Do this.")
        self.assertEqual(c.expect, "one two")
        self.assertEqual(c.note, "hint")
        self.assertTrue(c.smoke)
        self.assertEqual(c.log, ["a", "b", "c"])
        self.assertEqual(c.line, 5)
        self.assertEqual((d.id, d.step, d.smoke), ("1.2", "Next", False))

    def test_lazy_continuation(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] Do it.\nExpect: ok\n\nLater words.\n")
        c = plan.checks()[0]
        self.assertEqual(c.expect, "ok")
        self.assertEqual(plan.groups[0].intro, "Later words.")

    def test_indented_after_blank_still_belongs(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] Do it.\n\n  Expect: ok\n")
        self.assertEqual(plan.checks()[0].expect, "ok")

    def test_unknown_check_key(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] Do it.\n  Warning: hot\n")
        self.assertEqual(codes(plan), [("unknown-key", 6)])
        self.assertEqual(plan.checks()[0].step, "Do it. Warning: hot")

    def test_bad_smoke_value(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] Do it.\n  smoke: maybe\n")
        self.assertEqual(codes(plan), [("unknown-key", 6)])
        self.assertFalse(plan.checks()[0].smoke)

    def test_orphan_key(self):
        cases = {
            "# T\nrun: a\n  Expect: x\n## 1 G\n- [ ] x\n": 3,
            HEAD + "Intro.\n  smoke: yes\n## 1 G\n- [ ] x\n": 5,
            HEAD + "## Before you start\n- install\n\n  log: a\n## 1 G\n- [ ] x\n": 7,
            HEAD + "## 1 G\nIntro.\n  id: 1.1\n- [ ] x\n": 6,
        }
        for text, line in cases.items():
            plan = parse.parse_text(text)
            self.assertEqual(codes(plan), [("orphan-key", line)], text)

    def test_plain_bullet_ends_lazy_check(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] a\n- b\n")
        self.assertEqual(plan.checks()[0].step, "a")


class IdTests(unittest.TestCase):
    def test_default_ids_and_pinning(self):
        plan = parse.parse_text(HEAD + "## 2 G\n- [ ] a\n- [ ] b\n  id: 2.9\n- [ ] c\n")
        self.assertEqual(plan.problems, [])
        self.assertEqual([(c.id, c.pinned) for c in plan.checks()], [("2.1", False), ("2.9", True), ("2.3", False)])

    def test_pinned_id_normalized(self):
        plan = parse.parse_text(HEAD + "## 2 G\n- [ ] a\n  id: 02.07\n")
        self.assertEqual(plan.checks()[0].id, "2.7")

    def test_bad_id(self):
        for value in ("x", "2", "2.1.1", "3.1"):
            plan = parse.parse_text(HEAD + f"## 2 G\n- [ ] a\n  id: {value}\n")
            self.assertEqual(codes(plan), [("bad-id", 6)], value)
            self.assertEqual(plan.checks()[0].id, "2.1")

    def test_dup_id(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] a\n  id: 1.2\n- [ ] b\n")
        self.assertEqual(codes(plan), [("dup-id", 7)])
        self.assertIn("line 5", plan.problems[0].message)


class SmokeTests(unittest.TestCase):
    def test_smoke_in_file_order(self):
        plan = parse.parse_text(HEAD + "## 2 B\n- [ ] b1\n  smoke: yes\n## 1 A\n- [ ] a1\n- [ ] a2\n  smoke: yes\n")
        self.assertEqual([c.id for c in plan.smoke()], ["2.1", "1.2"])

    def test_big_smoke(self):
        body = "".join(f"- [ ] s{i}\n  smoke: yes\n" for i in range(13))
        plan = parse.parse_text(HEAD + "## 1 G\n" + body)
        self.assertEqual([p.code for p in plan.problems], ["big-smoke"])
        self.assertEqual(plan.problems[0].line, plan.smoke()[12].line)
        plan = parse.parse_text(HEAD + "## 1 G\n" + "".join(f"- [ ] s{i}\n  smoke: yes\n" for i in range(12)))
        self.assertEqual(plan.problems, [])


class CommentTests(unittest.TestCase):
    def test_comments_ignored_and_lines_kept(self):
        text = HEAD + "<!-- one\n## 9 hidden\n- [ ] hidden -->\n## 1 G\n- [ ] a <!-- inline --> b\n  <!-- c -->\n  Expect: e\n"
        plan = parse.parse_text(text)
        self.assertEqual(plan.problems, [])
        self.assertEqual([g.number for g in plan.groups], [1])
        c = plan.checks()[0]
        self.assertEqual((c.step, c.expect, c.line), ("a  b", "e", 8))

    def test_comment_line_does_not_end_lazy_check(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] a\n<!-- x -->\nExpect: e\n")
        self.assertEqual(plan.checks()[0].expect, "e")

    def test_unclosed_comment_runs_to_end(self):
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] a\n<!-- open\n- [ ] b\n")
        self.assertEqual([c.id for c in plan.checks()], ["1.1"])

    def test_problem_line_numbers_after_comment(self):
        plan = parse.parse_text("# T\n<!--\n\n\n-->\nrun: bad run\n## 1 G\n- [ ] a\n")
        self.assertEqual(codes(plan), [("bad-run", 6)])


class LogIdTests(unittest.TestCase):
    def test_unknown_log_id(self):
        ids = {"loaded", "placed"}
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] a\n  log: loaded, nope\n", rule_ids=ids)
        self.assertEqual(codes(plan), [("unknown-log-id", 6)])
        self.assertIn("nope", plan.problems[0].message)
        plan = parse.parse_text(HEAD + "## 1 G\n- [ ] a\n  log: nope\n")
        self.assertEqual(plan.problems, [])

    def test_load_rule_ids(self):
        self.assertEqual(parse.load_rule_ids(RULES), {"loaded", "placed", "restored", "no-light"})

    def test_bad_rule_files(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "r.json")
            for content in ("{nope", "[1]", '{"expect": 3}'):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(content)
                with self.assertRaises(model.SetupError) as cm:
                    parse.load_rule_ids(p)
                self.assertIn(p, str(cm.exception))
            with self.assertRaises(model.SetupError):
                parse.load_rule_ids(os.path.join(d, "missing.json"))


class FileTests(unittest.TestCase):
    def test_bom_and_crlf(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.md")
            with open(p, "wb") as f:
                f.write("﻿# T\r\nrun: a\r\n## 1 G\r\n- [ ] café\r\n  id: 1.x\r\n".encode("utf-8"))
            plan = parse.parse_file(p)
            self.assertEqual(plan.title, "T")
            self.assertEqual(plan.checks()[0].step, "café")
            self.assertEqual(codes(plan), [("bad-id", 5)])
            self.assertEqual(plan.path, p)

    def test_not_utf8(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "p.md")
            with open(p, "wb") as f:
                f.write(b"# T\nrun: a\n\xff\xfe bad\n")
            with self.assertRaises(model.SetupError) as cm:
                parse.parse_file(p)
            self.assertIn(p, str(cm.exception))
            self.assertIn("line 3", str(cm.exception))

    def test_missing_and_folder(self):
        with tempfile.TemporaryDirectory() as d:
            for p in (os.path.join(d, "none.md"), d):
                with self.assertRaises(model.SetupError) as cm:
                    parse.parse_file(p)
                self.assertIn(p, str(cm.exception))

    def test_messages_name_a_fix(self):
        plan = parse.parse_text("## x\n  Expect: y\n")
        for p in plan.problems:
            self.assertTrue(p.message[-1] in ".)", p.message)
            json.dumps(p.message)


if __name__ == "__main__":
    unittest.main()
