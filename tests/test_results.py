"""C3 tests: marks, results file, papyrus-log-check import and the starter plan (FORMAT.md 3 to 5)."""
import json
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import model, results  # noqa: E402
from sftestplan.model import Check, Group, Plan, SetupError  # noqa: E402

FIX = os.path.join(ROOT, "tests", "fixtures")
NOW = "2026-11-19T21:10:00Z"


def fx(name):
    return os.path.join(FIX, name)


def load(name):
    with open(fx(name), encoding="utf-8") as f:
        return json.load(f)


def beacon_plan(mod="Beacon Mod"):
    """The example plan built by hand (parse.py is another chunk's)."""
    return Plan(title="Beacon Mod test plan", run="beacon-0.1.0", mod=mod, version="0.1.0", path="Beacon.testplan.md",
                groups=[
                    Group(1, "Install and load", checks=[
                        Check("1.1", 1, "Start a new game.", smoke=True, log=["loaded"]),
                        Check("1.2", 1, "Open **Settings > Gameplay**.", smoke=True)]),
                    Group(2, "Main feature", checks=[
                        Check("2.1", 2, "Type `player.additem 0001A2B3 1`.", smoke=True),
                        Check("2.2", 2, "Drop the beacon.", smoke=True, log=["placed"]),
                        Check("2.3", 2, "Pick it up; see [the page](https://example.com/b).")]),
                    Group(3, "Save and load", checks=[
                        Check("3.1", 3, "Save and load.", smoke=True, log=["restored"])]),
                    Group(4, "Log only", checks=[
                        Check("4.1", 4, "No light errors.", log=["no-light"]),
                        Check("4.2", 4, "No crash line.", log=["no-crash", "loaded"]),
                        Check("4.3", 4, "Unknown rule.", log=["loaded", "nope"]),
                        Check("4.4", 4, "Loaded and no light errors.", log=["loaded", "no-light"])]),
                ])


class ReadMarksTests(unittest.TestCase):
    def test_reads_good_file_and_ignores_unknown_fields(self):
        m = results.read_marks(fx("marks-beacon.json"))
        self.assertEqual(m["run"], "beacon-0.1.0")
        self.assertEqual(len(m["checks"]), 5)
        self.assertNotIn("future_field", m)
        self.assertNotIn("extra", m["checks"][1])
        self.assertEqual(m["checks"][1]["r"], "fail")

    def test_refuses_other_major_version(self):
        with self.assertRaises(SetupError) as cm:
            results.read_marks(fx("marks-v2.json"))
        msg = str(cm.exception)
        self.assertIn("marks-v2.json", msg)
        self.assertIn("sf-test-plan-marks/2", msg)
        self.assertIn("update sf-test-plan", msg)

    def test_bad_json_names_line(self):
        with self.assertRaises(SetupError) as cm:
            results.read_marks(fx("marks-badjson.json"))
        self.assertIn("line 5", str(cm.exception))
        self.assertIn("marks-badjson.json", str(cm.exception))

    def test_bad_r(self):
        with self.assertRaises(SetupError) as cm:
            results.read_marks(fx("marks-badr.json"))
        self.assertIn("maybe", str(cm.exception))

    def test_missing_fields(self):
        cases = [
            ({"run": "a", "checks": []}, "isn't a marks file"),
            ({"format": "sf-test-plan-marks/1", "checks": []}, "no \"run\""),
            ({"format": "sf-test-plan-marks/1", "run": "a"}, "no \"checks\""),
            ({"format": "sf-test-plan-marks/1", "run": "a", "checks": [{"r": "pass"}]}, "no \"id\""),
            ({"format": "sf-test-plan-marks/1", "run": "a", "checks": [{"id": "1.1"}]}, "no \"r\""),
            ([1, 2], "one JSON object"),
        ]
        with tempfile.TemporaryDirectory() as d:
            for data, want in cases:
                p = os.path.join(d, "m.json")
                with open(p, "w", encoding="utf-8") as f:
                    json.dump(data, f)
                with self.assertRaises(SetupError, msg=want) as cm:
                    results.read_marks(p)
                self.assertIn(want, str(cm.exception))

    def test_missing_file(self):
        with self.assertRaises(SetupError):
            results.read_marks(fx("no-such-marks.json"))

    def test_minor_version_accepted(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump({"format": "sf-test-plan-marks/1.1", "run": "a", "checks": [{"id": "1.1", "r": ""}]}, f)
            self.assertEqual(results.read_marks(p)["checks"][0]["n"], "")


class SummarizeTests(unittest.TestCase):
    def test_smoke_round(self):
        plan = beacon_plan()
        plan.groups = plan.groups[:3]
        row = results.summarize(plan, results.read_marks(fx("marks-beacon.json")), "2026-11-19")
        self.assertEqual(row["test"], "Smoke test")
        self.assertEqual(row["happened"], "2 pass, 1 fail, 1 skip, 1 not run")
        self.assertEqual(row["date"], "2026-11-19")
        self.assertEqual(row["run"], "beacon-0.1.0")
        self.assertEqual(row["notes"], "1.2 fail: No Beacon group in Gameplay options.; "
                                       "2.1 pass: Took two tries.; 3.1: Ran out of time.")

    def test_full_round_when_deep_marked(self):
        plan = beacon_plan()
        plan.groups = plan.groups[:3]
        marks = results.read_marks(fx("marks-beacon.json"))
        marks["checks"].append({"id": "2.3", "r": "fail", "n": "", "t": "", "g": 2, "at": "x", "src": "page"})
        row = results.summarize(plan, marks, "2026-11-19")
        self.assertEqual(row["test"], "Full test")
        self.assertEqual(row["happened"], "2 pass, 2 fail, 1 skip, 1 not run")
        self.assertTrue(row["notes"].startswith("1.2 fail: No Beacon group in Gameplay options.; 2.3 fail; 2.1 pass"))

    def test_no_smoke_plan_is_full(self):
        plan = Plan(title="t", run="r", groups=[Group(1, "g", checks=[Check("1.1", 1, "a"), Check("1.2", 1, "b")])])
        marks = {"run": "r", "checks": [{"id": "1.1", "r": "pass", "n": "", "at": ""}]}
        row = results.summarize(plan, marks, "2026-11-19")
        self.assertEqual(row["test"], "Full test")
        self.assertEqual(row["happened"], "1 pass, 0 fail, 0 skip, 1 not run")
        self.assertEqual(row["notes"], "")

    def test_newer_at_wins_and_ids_sort_numerically(self):
        plan = Plan(title="t", run="r", groups=[Group(1, "g", checks=[Check(f"1.{i}", 1, "s") for i in range(1, 11)])])
        marks = {"run": "r", "checks": [
            {"id": "1.10", "r": "fail", "n": "ten", "at": "2026-11-19T10:00:00Z"},
            {"id": "1.2", "r": "fail", "n": "old", "at": "2026-11-19T09:00:00Z"},
            {"id": "1.2", "r": "pass", "n": "", "at": "2026-11-19T11:00:00Z"},
            {"id": "1.9", "r": "fail", "n": "nine", "at": "2026-11-19T10:00:00Z"}]}
        row = results.summarize(plan, marks, "d")
        self.assertEqual(row["happened"], "1 pass, 2 fail, 0 skip, 7 not run")
        self.assertEqual(row["notes"], "1.9 fail: nine; 1.10 fail: ten")


class ResultsFileTests(unittest.TestCase):
    def test_path(self):
        self.assertEqual(results.results_path(os.path.join("x", "Beacon.testplan.md")),
                         os.path.join("x", "Beacon.testplan.results.json"))
        self.assertEqual(results.results_path("plan.txt"), "plan.txt.results.json")

    def test_add_and_load_newest_first(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "Beacon.testplan.md")
            self.assertEqual(results.load_results(plan), [])
            p = results.add_result(plan, {"date": "2026-11-18", "test": "Smoke test", "happened": "a", "notes": ""})
            results.add_result(plan, {"date": "2026-11-19", "test": "Full test", "happened": "b", "notes": "é"})
            self.assertEqual(p, results.results_path(plan))
            rows = results.load_results(plan)
            self.assertEqual([r["date"] for r in rows], ["2026-11-19", "2026-11-18"])
            with open(p, encoding="utf-8") as f:
                text = f.read()
            data = json.loads(text)
            self.assertEqual(data["format"], model.RESULTS_FORMAT)
            self.assertIn("\n ", text)      # indented
            self.assertIn("é", text)        # UTF-8, not \u escapes
            self.assertEqual([n for n in os.listdir(d) if n.endswith(".tmp")], [])

    def test_broken_file_refused_and_kept(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "Beacon.testplan.md")
            p = results.results_path(plan)
            for bad in ('{"rows": [', '{"format": "sf-test-plan-results/2", "rows": []}', '"x"',
                        '{"format": "sf-test-plan-results/1"}', '{"format": "sf-test-plan-results/1", "rows": [1]}'):
                with open(p, "w", encoding="utf-8") as f:
                    f.write(bad)
                with self.assertRaises(SetupError) as cm:
                    results.add_result(plan, {"date": "d"})
                self.assertIn(p, str(cm.exception))
                with open(p, encoding="utf-8") as f:
                    self.assertEqual(f.read(), bad)

    def test_kit_list_rows_readable(self):
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "Kit.testplan.md")
            with open(results.results_path(plan), "w", encoding="utf-8") as f:
                json.dump([{"date": "2026-11-16", "test": "smoke", "happened": "ok", "notes": "n"}], f)
            self.assertEqual(results.load_results(plan)[0]["happened"], "ok")
            results.add_result(plan, {"date": "2026-11-19", "test": "Full test", "happened": "x", "notes": ""})
            self.assertEqual(len(results.load_results(plan)), 2)


class LogsTests(unittest.TestCase):
    def marks(self, report="logcheck-beacon.json", plan=None, mod=None):
        return results.logs_to_marks(plan or beacon_plan(), load(report), mod, NOW)

    def test_marks_shape(self):
        marks, lines = self.marks()
        self.assertEqual(marks["format"], model.MARKS_FORMAT)
        self.assertEqual(marks["run"], "beacon-0.1.0")
        self.assertEqual(marks["exported"], NOW)
        self.assertEqual(marks["tool"], model.TOOL_ID)
        for c in marks["checks"]:
            self.assertEqual(c["src"], "log")
            self.assertEqual(c["at"], NOW)
            self.assertIn(c["r"], model.RESULTS)
        ids = [c["id"] for c in marks["checks"]]
        # only checks with log: whose result is proved; 3.1 and 4.3 aren't, so they get no entry (no mark)
        self.assertEqual(ids, ["1.1", "2.2", "4.1", "4.2", "4.4"])

    def test_round_trip_through_read_marks(self):
        marks, _ = self.marks()
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "m.json")
            with open(p, "w", encoding="utf-8") as f:
                json.dump(marks, f)
            self.assertEqual(len(results.read_marks(p)["checks"]), 5)

    def test_decisions(self):
        marks, lines = self.marks()
        by = {c["id"]: c for c in marks["checks"]}
        self.assertEqual(by["1.1"]["r"], "pass")
        self.assertEqual(by["2.2"]["r"], "fail")
        self.assertIn("placed FAIL", by["2.2"]["n"])
        text = "\n".join(lines)
        self.assertNotIn("3.1", by)                                    # not proved: no entry, reason printed
        self.assertIn("3.1 no mark: not proved: restored NOT SEEN", text)
        self.assertEqual(by["4.1"]["r"], "pass")                       # forbid PASS = never seen
        self.assertIn("never appeared", by["4.1"]["n"])
        self.assertEqual(by["4.2"]["r"], "fail")                       # forbid FAIL
        self.assertIn("no-crash FAIL", by["4.2"]["n"])
        self.assertNotIn("4.3", by)                                    # one id not in the report
        self.assertIn("nope isn't in the report", text)
        self.assertEqual(by["4.4"]["r"], "pass")
        self.assertEqual(by["2.2"]["t"], "Drop the beacon.")
        self.assertEqual(by["2.2"]["g"], 2)
        self.assertIn("rule 'nope' isn't in the report", text)
        self.assertIn("plan's mod: line", lines[0])

    def test_plain_step_text(self):
        plan = beacon_plan()
        plan.groups[1].checks[0].log = ["loaded"]
        plan.groups[1].checks[2].log = ["loaded"]
        by = {c["id"]: c for c in results.logs_to_marks(plan, load("logcheck-beacon.json"), None, NOW)[0]["checks"]}
        self.assertEqual(by["2.1"]["t"], "Type player.additem 0001A2B3 1.")
        self.assertEqual(by["2.3"]["t"], "Pick it up; see the page.")
        self.assertLessEqual(len(results.plain_text("x" * 400)), 300)
        self.assertEqual(results.plain_text("**Settings > Gameplay** and *this*"), "Settings > Gameplay and this")

    def test_not_loaded(self):
        marks, lines = self.marks("logcheck-notloaded.json")
        self.assertEqual(marks["checks"], [])
        self.assertTrue(any("NOT LOADED" in l and "no marks" in l for l in lines))

    def test_two_mods_by_plan_mod(self):
        marks, lines = self.marks("logcheck-twomods.json")
        by = {c["id"]: c for c in marks["checks"]}
        self.assertNotIn("1.1", by)                      # Beacon Mod's loaded is NOT SEEN, not Other Mod's PASS
        self.assertIn("'Beacon Mod'", lines[0])

    def test_two_mods_case_insensitive_and_mod_option(self):
        marks, _ = self.marks("logcheck-twomods.json", plan=beacon_plan(mod="beacon MOD"))
        self.assertNotIn("1.1", {c["id"]: c for c in marks["checks"]})
        marks, lines = self.marks("logcheck-twomods.json", mod="other mod")
        self.assertEqual({c["id"]: c for c in marks["checks"]}["1.1"]["r"], "pass")
        self.assertIn("--mod", lines[0])

    def test_two_mods_no_match_lists_mods(self):
        for plan, mod in ((beacon_plan(mod=""), None), (beacon_plan(mod="Nope"), None), (beacon_plan(), "Nope")):
            with self.assertRaises(SetupError) as cm:
                self.marks("logcheck-twomods.json", plan=plan, mod=mod)
            msg = str(cm.exception)
            self.assertIn("'Other Mod'", msg)
            self.assertIn("'Beacon Mod'", msg)
            self.assertIn("--mod", msg)

    def test_only_entry_used(self):
        marks, lines = self.marks(plan=beacon_plan(mod=""))
        self.assertIn("only mod", lines[0])
        self.assertEqual(len(marks["checks"]), 5)

    def test_not_a_report(self):
        for bad in ({}, {"mods": []}, [], {"mods": "x"}):
            with self.assertRaises(SetupError):
                results.logs_to_marks(beacon_plan(), bad, None, NOW)

    def test_plan_without_log_checks(self):
        plan = Plan(title="t", run="r", mod="Beacon Mod", groups=[Group(1, "g", checks=[Check("1.1", 1, "a")])])
        marks, lines = results.logs_to_marks(plan, load("logcheck-beacon.json"), None, NOW)
        self.assertEqual(marks["checks"], [])
        self.assertIn("nothing to mark", lines[-1])


class StarterPlanTests(unittest.TestCase):
    def strip_comments(self, text):
        return re.sub(r"<!--.*?-->", "", text, flags=re.S)

    def test_structure(self):
        text = results.starter_plan("Beacon Mod")
        self.assertIn("<!--", text)
        body = self.strip_comments(text)
        lines = body.splitlines()
        self.assertEqual(lines[0], "# Beacon Mod test plan")
        self.assertIn("run: beacon-mod-0.1.0", lines[1:6])
        self.assertIn("mod: Beacon Mod", lines[1:6])
        heads = [l for l in lines if l.startswith("## ")]
        self.assertEqual(heads[0], "## Before you start")
        groups = heads[1:]
        self.assertTrue(2 <= len(groups) <= 3, groups)
        nums = [int(re.match(r"## (\d+) \S", g).group(1)) for g in groups]
        self.assertEqual(len(nums), len(set(nums)))
        checks = [l for l in lines if l.startswith("- [ ] ")]
        self.assertGreaterEqual(len(checks), 3)
        self.assertGreaterEqual(sum(1 for l in lines if l == "  smoke: yes"), 1)
        # every indented key line uses a known key and follows a check
        for i, l in enumerate(lines):
            m = re.match(r"^  (\w+):", l)
            if m:
                self.assertIn(m.group(1).lower(), model.CHECK_KEYS, l)
        # setup bullets exist between Before you start and the first group
        start = lines.index("## Before you start")
        first = lines.index(groups[0])
        self.assertTrue(any(l.startswith("- ") for l in lines[start:first]))
        # every comment opens and closes, and no comment line starts like a heading or check
        self.assertEqual(text.count("<!--"), text.count("-->"))
        for c in re.findall(r"<!--.*?-->", text, flags=re.S):
            for cl in c.splitlines():
                self.assertFalse(re.match(r"^\s*(#|- \[)", cl), cl)

    def test_run_ids(self):
        cases = {"Beacon Mod": "beacon-mod-0.1.0", "Nova's  Beacon!": "nova-s-beacon-0.1.0",
                 "   ": "my-mod-0.1.0", "!!!": "my-mod-0.1.0", "X" * 100: "x" * 58 + "-0.1.0",
                 "Crew Quest Completion - Vega": "crew-quest-completion-vega-0.1.0"}
        for mod, want in cases.items():
            run = results._run_id(mod)
            self.assertEqual(run, want, mod)
            self.assertTrue(model.RUN_RE.match(run), run)
        text = results.starter_plan("Ü & Co")
        run = re.search(r"^run: (\S+)$", text, flags=re.M).group(1)
        self.assertTrue(model.RUN_RE.match(run), run)

    def test_empty_mod_name(self):
        self.assertTrue(results.starter_plan("").startswith("# My Mod test plan\nrun: my-mod-0.1.0\n"))


if __name__ == "__main__":
    unittest.main()
