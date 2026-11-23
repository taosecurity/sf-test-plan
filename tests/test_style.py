"""0.4.0: check --style / build --style (FORMAT.md section 7; format sf-test-plan-style/1)."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse, style  # noqa: E402
from sftestplan.model import SetupError  # noqa: E402

GOOD = """# Lantern test plan
run: lantern-0.1.0
mod: Lantern
version: 0.1.0

This plan tests Lantern 0.1.0, a made-up mod.

## Before you start
- Install the mod and enable it.

## 1 Load
These checks prove it loads.

- [ ] Start a new game.
  Expect: no error message.
  smoke: yes
- [ ] Open the inventory.
  Expect: one lantern is there.
  note: Run `player.additem 0001A2B3 1` if it isn't.
  smoke: yes

## Log checks
- [ ] Look for the start line.
  Expect: it appears once.

## New Game+
- [ ] Enter the Unity and start again.
  Expect: the lantern is still there.
"""


def _plan(text=GOOD):
    return parse.parse_text(text, "lantern.testplan.md")


def _run(rules: dict, text=GOOD):
    plan = _plan(text)
    found = style.apply(plan, text, style.parse_style(rules, "style.json"))
    return plan, found


def _codes(found):
    return [p.code for p in found]


def R(**kw):
    d = {"format": style.STYLE_FORMAT}
    d.update(kw)
    return d


class StyleRules(unittest.TestCase):
    def test_good_plan_is_clean_with_every_rule(self):
        _, found = _run(R(smoke={"min": 1, "max": 5}, iso_dates=True, full_sentences=True,
                          banned=["obviously", {"word": "slate", "use": "note"}]))
        self.assertEqual(found, [])

    def test_format_only_checks_nothing(self):
        _, found = _run(R(), GOOD.replace("Start a new game.", "start a new game on 11/23/2026 obviously"))
        self.assertEqual(found, [])

    def test_smoke_min_and_max(self):
        _, found = _run(R(smoke={"min": 3}))
        self.assertEqual(_codes(found), ["style-smoke"])
        self.assertIn("at least 3", found[0].message)
        self.assertEqual(found[0].line, 0)
        _, found = _run(R(smoke={"max": 1}))
        self.assertEqual(_codes(found), ["style-smoke"])
        self.assertIn("at most 1", found[0].message)
        _, found = _run(R(smoke={"min": 2, "max": 2}))
        self.assertEqual(found, [])

    def test_dates(self):
        cases = {"11/23/2026": "2026-11-23", "23/11/2026": "2026-11-23", "2026/11/23": "2026-11-23",
                 "23.11.2026": "2026-11-23", "Nov 23, 2026": "2026-11-23", "November 23 2026": "2026-11-23",
                 "23 November 2026": "2026-11-23", "Sept. 3rd, 2026": "2026-09-03"}
        for written, iso in cases.items():
            with self.subTest(written=written):
                text = GOOD.replace("one lantern is there.", f"one lantern is there on {written}.")
                _, found = _run(R(iso_dates=True), text)
                self.assertEqual(_codes(found), ["style-date"])
                self.assertIn(iso, found[0].message)
                self.assertEqual(found[0].line, 18)

    def test_dates_skip_iso_versions_and_code(self):
        text = GOOD.replace("one lantern is there.", "one lantern 1.2.3 is there on 2026-11-23 (`11/23/2026`).")
        _, found = _run(R(iso_dates=True), text)
        self.assertEqual(found, [])

    def test_dates_and_banned_skip_data_keys(self):
        text = GOOD.replace("version: 0.1.0", "version: 11/23/2026")
        _, found = _run(R(iso_dates=True, banned=["lantern"]), text.replace("This plan tests Lantern 0.1.0, a made-up mod.", "This plan is made up."))
        # "lantern" is still in check text, but not the header's run:/mod: lines or the version date
        self.assertNotIn(2, [p.line for p in found])
        self.assertNotIn(4, [p.line for p in found])
        self.assertNotIn("style-date", _codes(found))

    def test_banned_word_phrase_and_use(self):
        text = GOOD.replace("Open the inventory.", "Just open the   Main  Menu inventory.")
        _, found = _run(R(banned=[{"word": "just", "use": "nothing"}, "main menu", "inv"]), text)
        self.assertEqual(_codes(found), ["style-banned", "style-banned"])
        self.assertIn("'Just'", found[0].message)
        self.assertIn("Write 'nothing' instead.", found[0].message)
        self.assertIn("Main  Menu", found[1].message)
        self.assertEqual(found[0].line, 17)

    def test_banned_skips_code_and_link_targets(self):
        text = GOOD.replace("Open the inventory.", "Open [the page](https://example.com/just) and type `just`.")
        _, found = _run(R(banned=["just"]), text)
        self.assertEqual(found, [])

    def test_sentences(self):
        bad = {
            "Start a new game.": ("start a new game.", 14, "capital"),
            "Expect: no error message.": ("Expect: no error message", 15, "end"),
            "This plan tests Lantern 0.1.0, a made-up mod.": ("this plan tests Lantern.", 6, "capital"),
            "- Install the mod and enable it.": ("- Install the mod", 9, "end"),
            "These checks prove it loads.": ("These checks prove it loads", 12, "end"),
            "if it isn't.": ("if it isn't", 19, "end"),
            "Look for the start line.": ("look for the start line.", 23, "capital"),
            "Enter the Unity and start again.": ("enter the Unity", 27, "capital"),
        }
        for old, (new, line, why) in bad.items():
            with self.subTest(old=old):
                _, found = _run(R(full_sentences=True), GOOD.replace(old, new))
                self.assertEqual(_codes(found), ["style-sentence"], found)
                self.assertEqual(found[0].line, line)
                self.assertIn("capital" if why == "capital" else "end with", found[0].message)

    def test_sentence_allows_markup_quotes_and_code(self):
        text = (GOOD.replace("Start a new game.", "**Start** a new game (twice).")
                .replace("Open the inventory.", "`coc` to the lodge, then open it:")
                .replace("Look for the start line.", "\"Lantern\" appears in the log!"))
        _, found = _run(R(full_sentences=True), text)
        self.assertEqual(found, [])

    def test_level_warning_does_not_fail_check(self):
        plan, found = _run(R(level="warning", smoke={"min": 9}))
        self.assertEqual([p.level for p in found], ["warning"])
        self.assertEqual(plan.errors(), [])
        plan, found = _run(R(smoke={"min": 9}))
        self.assertEqual(len(plan.errors()), 1)


class StyleFileErrors(unittest.TestCase):
    def assertBad(self, data, key):
        with self.assertRaises(SetupError) as cm:
            style.parse_style(data, "style.json")
        self.assertIn(f"'{key}'", str(cm.exception))

    def test_exit2_cases(self):
        self.assertBad({"format": "sf-test-plan-style/2"}, "format")
        self.assertBad({}, "format")
        self.assertBad(R(colour=True), "colour")
        self.assertBad(R(level="fatal"), "level")
        self.assertBad(R(smoke=5), "smoke")
        self.assertBad(R(smoke={"min": 5, "max": 2}), "smoke.min")
        self.assertBad(R(smoke={"min": -1}), "smoke.min")
        self.assertBad(R(smoke={"max": True}), "smoke.max")
        self.assertBad(R(smoke={"most": 3}), "smoke.most")
        self.assertBad(R(iso_dates="yes"), "iso_dates")
        self.assertBad(R(full_sentences=1), "full_sentences")
        self.assertBad(R(banned="just"), "banned")
        self.assertBad(R(banned=[3]), "banned[0]")
        self.assertBad(R(banned=["ok", ""]), "banned[1]")
        self.assertBad(R(banned=[{"word": "x", "instead": "y"}]), "banned[0].instead")
        self.assertBad(R(banned=[{"use": "y"}]), "banned[0].word")
        self.assertBad(R(banned=[{"word": "x", "use": 2}]), "banned[0].use")
        with self.assertRaises(SetupError):
            style.parse_style([], "style.json")


class StyleCli(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.plan = os.path.join(self.dir, "Lantern Mod.testplan.md")
        with open(self.plan, "w", encoding="utf-8") as f:
            f.write(GOOD.replace("Open the inventory.", "Obviously open the inventory."))

    def tearDown(self):
        self.tmp.cleanup()

    def style(self, data, name="house style.json"):
        p = os.path.join(self.dir, name)
        with open(p, "w", encoding="utf-8") as f:
            f.write(data if isinstance(data, str) else json.dumps(data))
        return p

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_check_style_reports_and_fails(self):
        code, out, _ = self.run_cli("check", self.plan, "--style", self.style(R(banned=["obviously"])))
        self.assertEqual(code, 1)
        self.assertIn(":17: error style-banned:", out)
        code, out, _ = self.run_cli("check", self.plan)
        self.assertEqual(code, 0)

    def test_build_style_error_stops_build(self):
        page = os.path.join(self.dir, "page.html")
        code, out, _ = self.run_cli("build", self.plan, "--out", page, "--style", self.style(R(banned=["obviously"])))
        self.assertEqual(code, 1)
        self.assertIn("No page written", out)
        self.assertFalse(os.path.exists(page))
        code, out, _ = self.run_cli("build", self.plan, "--out", page,
                                    "--style", self.style(R(level="warning", banned=["obviously"])))
        self.assertEqual(code, 0)
        self.assertTrue(os.path.exists(page))

    def test_bad_style_file_is_exit2(self):
        for data, needle in ((R(smoke={"min": 4, "max": 1}), "'smoke.min'"), ("{not json", "isn't valid JSON"),
                             (R(extra=1), "'extra'")):
            with self.subTest(needle=needle):
                code, out, err = self.run_cli("check", self.plan, "--style", self.style(data))
                self.assertEqual(code, 2)
                self.assertIn(needle, err)
                self.assertEqual(out, "")
        code, _, err = self.run_cli("check", self.plan, "--style", os.path.join(self.dir, "missing.json"))
        self.assertEqual(code, 2)
        self.assertIn("can't find the style file", err)

    def test_build_out_is_style_file_refused(self):
        sp = self.style(R())
        code, _, err = self.run_cli("build", self.plan, "--out", sp, "--style", sp)
        self.assertEqual(code, 2)
        self.assertIn("--style file", err)

    def test_example_style_file_passes_example_plan(self):
        code, out, _ = self.run_cli("check", os.path.join(ROOT, "examples", "Beacon.testplan.md"),
                                    "--style", os.path.join(ROOT, "examples", "style.json"))
        self.assertEqual(code, 0, out)

    def test_help_exits_0(self):
        for cmd in ("check", "build"):
            code, out, _ = self.run_cli(cmd, "--help")
            self.assertEqual(code, 0)
            self.assertIn("--style", out)


if __name__ == "__main__":
    unittest.main()
