"""0.4.0: the New Game+ section, the ngplus: header key and the ngplus command (FORMAT.md rule 14)."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse, render  # noqa: E402

LANTERN = """# Lantern test plan
run: lantern-0.1.0
mod: Lantern
ngplus: NewGamePlus.testplan.html

## 1 Load
- [ ] Start a new game.
  Expect: no error.

## New Game+
The lantern must come back after the Unity.

- [ ] Open the inventory after New Game+.
  Expect: the **Lantern** is there.
  log: lantern-kept
- [ ] Light it.
"""

BEACON = """# Beacon test plan
run: beacon-0.1.0
mod: Beacon

## 1 Load
- [ ] Place a beacon.

## NG+
- [ ] Check the beacon list after New Game+.
"""

QUIET = """# Quiet test plan
run: quiet-0.1.0
mod: Quiet

## 1 Load
- [ ] Load a save.
"""

BASE = """# New Game+ test plan
run: ngplus-1

Play through the Unity with every mod installed.

## Before you start
- Back up your saves.

## 1 Crossing
- [ ] Enter the Unity.
  smoke: yes
- [ ] Start New Game+.
  id: 1.5

## 2 After
- [ ] Load the new universe.

## Log checks
- [ ] No script errors after the crossing.
  log: no-errors
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def codes(plan):
    return [p.code for p in plan.problems]


class ParseTests(unittest.TestCase):
    def test_section_is_left_off_the_mod_page(self):
        p = parse.parse_text(LANTERN)
        self.assertEqual(p.errors(), [])
        self.assertEqual([c.id for c in p.checks()], ["1.1"])
        self.assertEqual(len(p.ngplus_checks), 2)
        self.assertEqual(p.ngplus_checks[0].log, ["lantern-kept"])
        self.assertIn("Unity", p.ngplus_intro)
        page = render.render(p)
        self.assertNotIn("Open the inventory", page)
        self.assertNotIn("Light it", page)

    def test_ng_plus_heading_and_case(self):
        self.assertEqual(len(parse.parse_text(BEACON).ngplus_checks), 1)
        p = parse.parse_text(BEACON.replace("## NG+", "## new game+"))
        self.assertEqual(len(p.ngplus_checks), 1)
        self.assertNotIn("group-no-number", codes(p))

    def test_link_line(self):
        page = render.render(parse.parse_text(LANTERN))
        self.assertIn('id="ngplus-link"', page)
        self.assertIn('href="NewGamePlus.testplan.html"', page)
        page = render.render(parse.parse_text(BEACON))
        self.assertNotIn('id="ngplus-link"', page)

    def test_link_path_with_spaces_and_backslashes(self):
        p = parse.parse_text(LANTERN.replace("ngplus: NewGamePlus.testplan.html",
                                             "ngplus: ..\\NG Plus\\shared page.html"))
        self.assertEqual(p.errors(), [])
        self.assertIn('href="../NG%20Plus/shared%20page.html"', render.render(p))

    def test_https_link(self):
        p = parse.parse_text(LANTERN.replace("NewGamePlus.testplan.html", "https://example.com/ng.html?a=1&b=2"))
        self.assertIn('href="https://example.com/ng.html?a=1&amp;b=2"', render.render(p))

    def test_bad_links_refused(self):
        for bad in ("javascript:alert(1)", "data:text/html,x", "C:\\Pages\\ng.html", "//evil.example/x", "a\"b"):
            p = parse.parse_text(LANTERN.replace("NewGamePlus.testplan.html", bad))
            self.assertIn("bad-ngplus", codes(p), bad)
            self.assertNotIn("ngplus-link", render.render(p), bad)

    def test_id_is_bad_id(self):
        p = parse.parse_text(LANTERN.replace("- [ ] Light it.", "- [ ] Light it.\n  id: 3.1"))
        self.assertIn("bad-id", [e.code for e in p.errors()])

    def test_smoke_is_a_warning_and_ignored(self):
        p = parse.parse_text(LANTERN.replace("- [ ] Light it.", "- [ ] Light it.\n  smoke: yes"))
        self.assertEqual(p.errors(), [])
        self.assertIn("unknown-key", codes(p))
        self.assertFalse(p.ngplus_checks[1].smoke)
        self.assertEqual(p.smoke(), [])

    def test_empty_section_is_fine(self):
        p = parse.parse_text(QUIET + "\n## New Game+\n")
        self.assertEqual(p.problems, [])
        self.assertTrue(p.ngplus_line)

    def test_ngplus_ids_dont_clash(self):
        # N.<n> names don't count as page ids, so a group check can't collide with them
        p = parse.parse_text(LANTERN)
        self.assertNotIn("dup-id", codes(p))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        self.files = {}
        for name, text in (("base", BASE), ("lantern", LANTERN), ("beacon", BEACON), ("quiet", QUIET)):
            path = os.path.join(self.d, f"{name}.testplan.md")
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
            self.files[name] = path
        self.order = os.path.join(self.d, "order.json")
        self.out = os.path.join(self.d, "NewGamePlus.testplan.md")

    def tearDown(self):
        self.tmp.cleanup()

    def ngplus(self, *plans, extra=()):
        return run("ngplus", "--base", self.files["base"], "--order", self.order, "--out", self.out,
                   *extra, *[self.files[p] for p in plans])

    def shared(self):
        return parse.parse_file(self.out)

    def read_order(self):
        with open(self.order, encoding="utf-8") as f:
            return json.load(f)

    def test_writes_shared_plan(self):
        code, out, err = self.ngplus("lantern", "beacon", "quiet")
        self.assertEqual(code, 0, out + err)
        p = self.shared()
        self.assertEqual(p.errors(), [])
        self.assertEqual(p.run, "ngplus-1")
        self.assertIn("This page covers 3 mods.", p.intro)
        self.assertEqual(p.setup, ["Back up your saves."])
        # base groups keep their numbers and ids, mods follow with base max (2) + their place
        self.assertEqual([(g.number, g.title) for g in p.groups], [(1, "Crossing"), (2, "After"), (3, "Lantern"),
                                                                    (4, "Beacon")])
        self.assertEqual([c.id for c in p.groups[0].checks], ["1.1", "1.5"])
        self.assertTrue(p.groups[0].checks[0].smoke)
        self.assertEqual([c.id for c in p.groups[2].checks], ["3.1", "3.2"])
        self.assertIn("Skip this group if the mod isn't installed.", p.groups[2].intro)
        self.assertIn("Unity", p.groups[2].intro)
        self.assertEqual(p.groups[2].checks[0].expect, "the **Lantern** is there.")
        self.assertEqual(p.groups[2].checks[0].log, ["lantern-kept"])
        self.assertEqual([c.id for c in p.log_checks], ["L.1"])
        self.assertEqual(self.read_order(), ["Lantern", "Beacon", "Quiet"])
        self.assertIn("Quiet: no New Game+ checks", out)
        self.assertIn("Then run: sf-test-plan build", out)
        self.assertEqual(run("build", self.out)[0], 0)

    def test_order_fixes_numbers_and_new_mods_are_appended(self):
        with open(self.order, "w", encoding="utf-8") as f:
            json.dump(["Beacon", "Gone", "Lantern"], f)
        code, out, _ = self.ngplus("lantern", "beacon", "quiet")
        self.assertEqual(code, 0, out)
        p = self.shared()
        # Gone left but keeps place 2 (group 4), so Lantern stays group 5
        self.assertEqual([(g.number, g.title) for g in p.groups][2:], [(3, "Beacon"), (5, "Lantern")])
        self.assertEqual(self.read_order(), ["Beacon", "Gone", "Lantern", "Quiet"])
        self.assertIn("added Quiet", out)

    def test_order_not_rewritten_when_unchanged(self):
        with open(self.order, "w", encoding="utf-8") as f:
            f.write('[ "Lantern",  "Beacon" ]')
        code, out, _ = self.ngplus("lantern", "beacon")
        self.assertEqual(code, 0, out)
        with open(self.order, encoding="utf-8") as f:
            self.assertEqual(f.read(), '[ "Lantern",  "Beacon" ]')
        self.assertIn("(unchanged)", out)

    def test_duplicate_mod_is_exit_2(self):
        dup = os.path.join(self.d, "lantern2.testplan.md")
        with open(dup, "w", encoding="utf-8") as f:
            f.write(LANTERN.replace("lantern-0.1.0", "lantern-0.2.0"))
        code, out, err = run("ngplus", "--base", self.files["base"], "--order", self.order, "--out", self.out,
                             self.files["lantern"], dup)
        self.assertEqual(code, 2)
        self.assertIn("Lantern", err)
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(self.order))

    def test_missing_mod_name_is_exit_2(self):
        with open(self.files["quiet"], "w", encoding="utf-8") as f:
            f.write(QUIET.replace("mod: Quiet\n", ""))
        code, _, err = self.ngplus("quiet")
        self.assertEqual(code, 2)
        self.assertIn("mod:", err)

    def test_bad_order_files(self):
        for text in ('{"a": 1}', '["A", 3]', '["A", "A"]', "not json"):
            with open(self.order, "w", encoding="utf-8") as f:
                f.write(text)
            code, _, err = self.ngplus("lantern")
            self.assertEqual(code, 2, text)
            self.assertIn("order", err, text)
            self.assertFalse(os.path.exists(self.out), text)

    def test_nothing_written_on_plan_errors(self):
        with open(self.files["beacon"], "w", encoding="utf-8") as f:
            f.write(BEACON.replace("run: beacon-0.1.0\n", ""))
        code, out, _ = self.ngplus("lantern", "beacon")
        self.assertEqual(code, 1)
        self.assertIn("no-run", out)
        self.assertIn("Nothing written", out)
        self.assertFalse(os.path.exists(self.out))
        self.assertFalse(os.path.exists(self.order))

    def test_existing_out_needs_force(self):
        with open(self.out, "w", encoding="utf-8") as f:
            f.write("old")
        code, _, err = self.ngplus("lantern")
        self.assertEqual(code, 2)
        self.assertIn("--force", err)
        with open(self.out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "old")
        self.assertFalse(os.path.exists(self.order))
        code, out, _ = self.ngplus("lantern", extra=("--force",))
        self.assertEqual(code, 0, out)
        self.assertEqual(self.shared().errors(), [])

    def test_out_is_an_input(self):
        code, _, err = run("ngplus", "--base", self.files["base"], "--order", self.order,
                           "--out", self.files["lantern"], "--force", self.files["lantern"])
        self.assertEqual(code, 2)
        self.assertIn("is the plan", err)
        code, _, err = run("ngplus", "--base", self.files["base"], "--order", self.files["base"],
                           "--out", self.out, self.files["lantern"])
        self.assertEqual(code, 2)
        self.assertIn("--order", err)
        with open(self.files["base"], encoding="utf-8") as f:
            self.assertEqual(f.read(), BASE)

    def test_read_only_out_refused(self):
        with open(self.out, "w", encoding="utf-8") as f:
            f.write("old")
        os.chmod(self.out, 0o444)
        try:
            code, _, err = self.ngplus("lantern", extra=("--force",))
            self.assertEqual(code, 2)
            self.assertIn("read-only", err)
        finally:
            os.chmod(self.out, 0o666)

    def test_help_exits_0(self):
        code, out, _ = run("ngplus", "--help")
        self.assertEqual(code, 0)
        self.assertIn("--order", out)


if __name__ == "__main__":
    unittest.main()
