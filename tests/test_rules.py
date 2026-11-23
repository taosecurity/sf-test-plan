"""The rules command and sftestplan.rules: starter papyrus-log-check rule files from a plan's log: ids."""
import io
import json
import os
import re
import shutil
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse, rules  # noqa: E402
from sftestplan.model import SetupError  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "Beacon.testplan.md")
EXAMPLE_RULES = os.path.join(ROOT, "examples", "Beacon.logrules.json")

TWO_STEPS = """# Two test plan
run: two-0.1.0
mod: Two (Mod)

## 1 Load
- [ ] Start a game.
  log: started, ready
- [ ] Load a save.
  log: started
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def write(path, text):
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


class RulesModuleTests(unittest.TestCase):
    def test_plan_log_uses_in_file_order_with_every_step(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "Two.testplan.md")
            write(p, TWO_STEPS)
            uses = rules.plan_log_uses(parse.parse_file(p))
        self.assertEqual(list(uses), ["started", "ready"])
        self.assertEqual([c for c, _ in uses["started"]], ["1.1", "1.2"])
        self.assertEqual(uses["ready"], [("1.1", "Start a game.")])

    def test_regex_text_matches_itself_only(self):
        for s in ("BeaconMod: placed", "My.Mod (v2): a+b [x] {version} | y$", "back\\slash"):
            rx = rules.regex_text(s)
            self.assertTrue(re.fullmatch(rx, s), rx)
        self.assertEqual(rules.regex_text("A: b-c"), "A: b-c")
        self.assertFalse(re.search(rules.regex_text("a.b"), "axb"))

    def test_default_tag(self):
        self.assertEqual(rules.default_tag("Beacon Mod"), "BeaconMod")
        self.assertEqual(rules.default_tag("Two (Mod)"), "TwoMod")
        self.assertEqual(rules.default_tag("!!"), "MyMod")

    def test_starter_rules_shape(self):
        uses = {"loaded": [("1.1", "Start a game.")], "placed": [("2.1", "Drop it."), ("2.3", "Drop it again.")]}
        data, added = rules.starter_rules("Beacon Mod", "0.1.0", uses)
        self.assertEqual([r["id"] for r in added], ["loaded", "placed"])
        self.assertEqual(data["mod"], "Beacon Mod")
        self.assertEqual(data["version"], "0.1.0")
        self.assertEqual(data["plugins"], ["BeaconMod.esm"])
        self.assertEqual(data["prefix"], "BeaconMod:")
        self.assertEqual(data["forbid"], [])
        self.assertEqual(data["expect"][0], {"id": "loaded", "re": "BeaconMod: loaded", "means": "Step 1.1: Start a game."})
        self.assertEqual(data["expect"][1]["means"], "Step 2.1: Drop it.; Step 2.3: Drop it again.")
        # every pattern matches the line the starter suggests, and the prefix matches it too
        for r in data["expect"]:
            line = f"BeaconMod: {r['id']}"
            self.assertTrue(re.search(r["re"], line))
            self.assertTrue(re.search(data["prefix"], line))

    def test_prefix_and_plugins_options(self):
        data, _ = rules.starter_rules("X", "", {"go": [("1.1", "Go.")]}, prefix="MY.MOD: ", plugins=["A.esm", "B.esm"])
        self.assertEqual(data["prefix"], "MY\\.MOD: ")
        self.assertEqual(data["expect"][0]["re"], "MY\\.MOD: go")
        self.assertEqual(data["plugins"], ["A.esm", "B.esm"])
        self.assertTrue(re.search(data["expect"][0]["re"], "[ts] MY.MOD: go now"))

    def test_base_keeps_rules_and_adds_only_missing_ids(self):
        base = {"mod": "Beacon Mod", "prefix": "BEACON:", "scripts": "^Beacon_", "custom": 1,
                "expect": [{"id": "loaded", "re": "BEACON: up", "min": 2}],
                "forbid": [{"id": "boom", "re": "BEACON: boom"}]}
        uses = {"loaded": [("1.1", "a")], "boom": [("1.2", "b")], "new": [("2.1", "c")]}
        data, added = rules.starter_rules("Beacon Mod", "0.1.0", uses, base=base)
        self.assertEqual([r["id"] for r in added], ["new"])
        self.assertEqual(data["expect"][0], {"id": "loaded", "re": "BEACON: up", "min": 2})
        self.assertEqual(data["expect"][1]["re"], "BEACON: new")   # the file's plain prefix leads new patterns
        self.assertEqual(data["forbid"], base["forbid"])
        self.assertEqual(data["custom"], 1)
        self.assertEqual(list(data)[:3], ["mod", "prefix", "scripts"])
        self.assertEqual(len(base["expect"]), 1, "the base object itself isn't changed")

    def test_base_with_regex_prefix_uses_the_mod_tag(self):
        for prefix in ("^(MYMOD|MyMod):", "MyMod:\\s", ""):
            base = {"mod": "M", "prefix": prefix, "expect": []}
            data, _ = rules.starter_rules("My Mod", "", {"go": [("1.1", "Go.")]}, base=base)
            self.assertEqual(data["expect"][0]["re"], "MyMod: go", prefix)
            self.assertEqual(data["prefix"], prefix)

    def test_base_with_escaped_literal_prefix_keeps_it(self):
        base = {"mod": "M", "prefix": "MY\\.MOD:", "expect": []}
        data, _ = rules.starter_rules("My Mod", "", {"go": [("1.1", "Go.")]}, base=base)
        self.assertEqual(data["expect"][0]["re"], "MY\\.MOD: go")

    def test_base_with_anchored_or_escaped_prefix_keeps_its_text(self):
        for prefix, want in (("^BCN:", "BCN: go"), ("BCN\\:", "BCN: go"), ("^BCN:$", "BCN: go"),
                             ("^MY\\.MOD\\:", "MY\\.MOD: go"), ("A\\$", "A\\$ go")):
            base = {"mod": "M", "prefix": prefix, "expect": []}
            data, _ = rules.starter_rules("My Mod", "", {"go": [("1.1", "Go.")]}, base=base)
            self.assertEqual(data["expect"][0]["re"], want, prefix)
            self.assertEqual(data["prefix"], prefix, "the file's prefix isn't changed")

    def test_literal_prefix(self):
        self.assertEqual(rules.literal_prefix("^BCN\\:$"), "BCN:")
        self.assertEqual(rules.literal_prefix("A\\$"), "A$")
        self.assertEqual(rules.literal_prefix("A\\\\$"), "A\\")
        for rx in ("", "^", "MyMod:\\s", "^(A|B):", "a.b", "x\\d", 5, None):
            self.assertIsNone(rules.literal_prefix(rx), rx)

    def test_base_with_non_string_ids(self):
        base = {"expect": [{"id": ["x"], "re": "a"}, {"id": 5}, {"id": {"k": 1}}, "junk"],
                "forbid": [{"id": None}]}
        data, added = rules.starter_rules("M", "", {"go": [("1.1", "Go.")]}, base=base)
        self.assertEqual([r["id"] for r in added], ["go"])
        self.assertEqual(len(data["expect"]), 5)

    def test_prefix_replaces_the_base_prefix(self):
        base = {"mod": "M", "prefix": "OLD:", "expect": []}
        data, _ = rules.starter_rules("M", "", {"go": [("1.1", "Go.")]}, prefix="NEW.X:", base=base)
        self.assertEqual(data["prefix"], "NEW\\.X:")
        self.assertEqual(data["expect"][0]["re"], "NEW\\.X: go")
        self.assertEqual(base["prefix"], "OLD:")

    def test_means_is_not_cut_short(self):
        long_step = "Walk " + "far " * 120 + "end."
        data, _ = rules.starter_rules("M", "", {"go": [("1.1", rules.plain_text(long_step, None))]})
        self.assertTrue(data["expect"][0]["means"].endswith("end."))
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "Long.testplan.md")
            write(p, f"# P\nrun: p-1\nmod: M\n\n## 1 G\n- [ ] {long_step}\n  log: go\n")
            uses = rules.plan_log_uses(parse.parse_file(p))
        self.assertGreater(len(uses["go"][0][1]), 300)
        self.assertTrue(uses["go"][0][1].endswith("end."))

    def test_base_wrong_shape(self):
        for base in ([], {"expect": {}}, {"forbid": "x"}):
            with self.assertRaises(SetupError):
                rules.starter_rules("M", "", {"go": [("1.1", "Go.")]}, base=base, base_name="r.json")

    def test_dumps_round_trips_and_puts_one_rule_per_line(self):
        data, _ = rules.starter_rules("Bé Mod", "1", {"a": [("1.1", "x")], "b": [("1.2", "y")]})
        text = rules.dumps(data)
        self.assertEqual(json.loads(text), data)
        self.assertIn("Bé Mod", text)
        self.assertEqual(sum(1 for line in text.splitlines() if line.lstrip().startswith('{"id"')), 2)
        self.assertIn('"forbid": []', text)


class RulesCommandTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.plan = os.path.join(self.d, "Beacon.testplan.md")
        shutil.copy(EXAMPLE, self.plan)

    def test_writes_default_file_that_check_accepts(self):
        code, out, err = run("rules", self.plan)
        self.assertEqual(code, 0, err)
        target = os.path.join(self.d, "Beacon.logrules.json")
        self.assertIn(f"Rule file: {target}", out)
        self.assertIn("New expect rule 'placed' (step 2.2): re \"BeaconMod: placed\"", out)
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual([r["id"] for r in data["expect"]], ["loaded", "placed", "restored"])
        self.assertEqual(run("check", self.plan, "--rules", target)[0], 0)

    def test_refuses_existing_file_without_force(self):
        target = os.path.join(self.d, "Beacon.logrules.json")
        write(target, "keep me")
        code, _, err = run("rules", self.plan)
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), "keep me")
        self.assertEqual(run("rules", self.plan, "--force")[0], 0)
        with open(target, encoding="utf-8") as f:
            self.assertEqual(len(json.load(f)["expect"]), 3)

    def test_from_adds_missing_ids_to_the_same_file_with_force(self):
        target = os.path.join(self.d, "mine.logrules.json")
        with open(EXAMPLE_RULES, encoding="utf-8") as f:
            data = json.load(f)
        data["expect"] = [r for r in data["expect"] if r["id"] != "restored"]
        write(target, json.dumps(data))
        code, _, err = run("rules", self.plan, "--from", target)
        self.assertEqual(code, 2)
        self.assertIn("add --force", err)
        code, out, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 0, err)
        self.assertIn(f"Already in {target}: 2 of the 3 ids.", out)
        self.assertIn("3 log ids on 3 steps", out)
        with open(target, encoding="utf-8") as f:
            new = json.load(f)
        self.assertEqual([r["id"] for r in new["expect"]], ["loaded", "placed", "restored"])
        self.assertEqual(new["expect"][:2], data["expect"])
        self.assertEqual(new["forbid"], data["forbid"])
        self.assertEqual(new["expect"][2]["re"], "BeaconMod: restored")

    def test_counts_are_singular_for_one(self):
        p = os.path.join(self.d, "One.testplan.md")
        write(p, "# P\nrun: p-1\nmod: One\n\n## 1 G\n- [ ] Do it.\n  log: go\n")
        code, out, _ = run("rules", p)
        self.assertEqual(code, 0)
        self.assertIn(": 1 log id on 1 step\n", out)

    def test_from_with_nothing_missing_writes_nothing(self):
        out_file = os.path.join(self.d, "out.json")
        code, out, _ = run("rules", self.plan, "--from", EXAMPLE_RULES, "--out", out_file)
        self.assertEqual(code, 0)
        self.assertIn("Nothing to add", out)
        self.assertFalse(os.path.exists(out_file))

    def test_from_bad_json_is_exit_2(self):
        bad = os.path.join(self.d, "bad.json")
        write(bad, "{nope")
        code, _, err = run("rules", self.plan, "--from", bad, "--out", os.path.join(self.d, "o.json"))
        self.assertEqual(code, 2)
        self.assertIn("isn't valid JSON", err)

    def test_out_is_the_plan_is_refused_even_with_force(self):
        code, _, err = run("rules", self.plan, "--out", self.plan, "--force")
        self.assertEqual(code, 2)
        self.assertIn("is the plan itself", err)
        with open(self.plan, encoding="utf-8") as f, open(EXAMPLE, encoding="utf-8") as g:
            self.assertEqual(f.read(), g.read())

    def test_no_log_ids_writes_nothing(self):
        p = os.path.join(self.d, "Plain.testplan.md")
        write(p, "# P\nrun: p-1\n\n## 1 G\n- [ ] Do it.\n")
        code, out, _ = run("rules", p)
        self.assertEqual(code, 0)
        self.assertIn("nothing to write", out)
        self.assertFalse(os.path.exists(os.path.join(self.d, "Plain.logrules.json")))

    def test_no_log_ids_with_out_as_the_plan_is_refused(self):
        p = os.path.join(self.d, "Plain.testplan.md")
        text = "# P\nrun: p-1\n\n## 1 G\n- [ ] Do it.\n"
        write(p, text)
        code, _, err = run("rules", p, "--out", p)
        self.assertEqual(code, 2)
        self.assertIn("is the plan itself", err)
        with open(p, encoding="utf-8") as f:
            self.assertEqual(f.read(), text)

    def test_no_log_ids_with_out_a_folder_is_refused(self):
        p = os.path.join(self.d, "Plain.testplan.md")
        write(p, "# P\nrun: p-1\n\n## 1 G\n- [ ] Do it.\n")
        code, _, err = run("rules", p, "--out", self.d)
        self.assertEqual(code, 2)
        self.assertIn("is a folder", err)

    def test_plan_errors_are_exit_1(self):
        p = os.path.join(self.d, "Bad.testplan.md")
        write(p, "# P\n\n## 1 G\n- [ ] Do it.\n  log: x\n")
        code, out, _ = run("rules", p)
        self.assertEqual(code, 1)
        self.assertIn("no-run", out)

    def test_prefix_and_plugin_options(self):
        target = os.path.join(self.d, "r.json")
        code, _, err = run("rules", self.plan, "--out", target, "--prefix", "BEACON:", "--plugin", "Beacon.esm",
                           "--plugin", "BeaconAddon.esm")
        self.assertEqual(code, 0, err)
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["prefix"], "BEACON:")
        self.assertEqual(data["plugins"], ["Beacon.esm", "BeaconAddon.esm"])
        self.assertEqual(data["expect"][0]["re"], "BEACON: loaded")

    def _beacon_rules_without_restored(self, **changes):
        target = os.path.join(self.d, "mine.logrules.json")
        with open(EXAMPLE_RULES, encoding="utf-8") as f:
            data = json.load(f)
        data["expect"] = [r for r in data["expect"] if r["id"] != "restored"]
        data.update(changes)
        write(target, json.dumps(data))
        return target

    def test_failed_write_keeps_the_old_file(self):
        target = self._beacon_rules_without_restored()
        with open(target, encoding="utf-8") as f:
            before = f.read()
        with mock.patch("sftestplan.cli.os.replace", side_effect=OSError(13, "Permission denied")):
            code, _, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 2)
        self.assertIn("can't write", err)
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(sorted(os.listdir(self.d)), ["Beacon.testplan.md", "mine.logrules.json"])

    def test_from_with_regex_prefix_warns_that_the_tag_was_used(self):
        target = self._beacon_rules_without_restored(prefix="^(BeaconMod|BCN):")
        code, out, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 0, err)
        self.assertIn("WARNING", out)
        self.assertIn("BeaconMod:", out)
        target2 = self._beacon_rules_without_restored(prefix="^BCN\\:")
        code, out, err = run("rules", self.plan, "--from", target2, "--force")
        self.assertEqual(code, 0, err)
        self.assertNotIn("WARNING", out)
        with open(target2, encoding="utf-8") as f:
            self.assertEqual(json.load(f)["expect"][-1]["re"], "BCN: restored")

    def test_from_with_non_string_id_is_not_a_crash(self):
        with open(EXAMPLE_RULES, encoding="utf-8") as f:
            data = json.load(f)
        data["expect"] = [r for r in data["expect"] if r["id"] != "restored"] + [{"id": ["restored"], "re": "x"}]
        target = os.path.join(self.d, "odd.json")
        write(target, json.dumps(data))
        code, out, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 0, err)
        self.assertIn("New expect rule 'restored'", out)

    def test_plugin_with_from_is_refused(self):
        target = self._beacon_rules_without_restored()
        code, _, err = run("rules", self.plan, "--from", target, "--plugin", "X.esm", "--force")
        self.assertEqual(code, 2)
        self.assertIn("--plugin", err)
        self.assertIn("--from", err)
        with open(target, encoding="utf-8") as f:
            self.assertNotIn("X.esm", f.read())

    def test_from_with_prefix_updates_the_file_prefix(self):
        target = self._beacon_rules_without_restored()
        code, out, err = run("rules", self.plan, "--from", target, "--prefix", "BCN.X:", "--force")
        self.assertEqual(code, 0, err)
        self.assertIn('prefix changed from "BeaconMod: " to "BCN\\\\.X:"', out)
        with open(target, encoding="utf-8") as f:
            new = json.load(f)
        self.assertEqual(new["prefix"], "BCN\\.X:")
        self.assertEqual(new["expect"][-1]["re"], "BCN\\.X: restored")

    def test_prefix_is_stripped(self):
        target = os.path.join(self.d, "r.json")
        code, _, err = run("rules", self.plan, "--out", target, "--prefix", "  BEACON:  ")
        self.assertEqual(code, 0, err)
        with open(target, encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["prefix"], "BEACON:")
        self.assertEqual(data["expect"][0]["re"], "BEACON: loaded")

    def test_empty_prefix_is_exit_2(self):
        code, _, err = run("rules", self.plan, "--prefix", " ")
        self.assertEqual(code, 2)
        self.assertIn("--prefix is empty", err)

    def test_default_out_names(self):
        self.assertEqual(cli._default_rules_out("a/Mod.testplan.md"), "a/Mod.logrules.json")
        self.assertEqual(cli._default_rules_out("Mod.md"), "Mod.logrules.json")
        self.assertEqual(cli._default_rules_out("Mod.txt"), "Mod.txt.logrules.json")


class LastReviewTests(unittest.TestCase):
    """0.3.0 last review: prefix-only updates, note order, odd entries, unwritable text."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.plan = os.path.join(self.d, "Beacon.testplan.md")
        shutil.copy(EXAMPLE, self.plan)

    def _rules(self, name="mine.logrules.json", drop=("restored",), **changes):
        target = os.path.join(self.d, name)
        with open(EXAMPLE_RULES, encoding="utf-8") as f:
            data = json.load(f)
        data["expect"] = [r for r in data["expect"] if r["id"] not in drop]
        data.update(changes)
        write(target, json.dumps(data))
        return target

    def _load(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_prefix_is_written_even_when_no_id_is_missing(self):
        target = self._rules(drop=())
        code, out, err = run("rules", self.plan, "--from", target, "--prefix", "BCN:", "--force")
        self.assertEqual(code, 0, err)
        self.assertNotIn("Nothing to add", out)
        self.assertIn("only the prefix changed", out)
        self.assertEqual(self._load(target)["prefix"], "BCN:")

    def test_prefix_only_update_needs_force(self):
        target = self._rules(drop=())
        code, out, err = run("rules", self.plan, "--from", target, "--prefix", "BCN:")
        self.assertEqual(code, 2)
        self.assertIn("add --force to update its prefix", err)
        self.assertNotIn("Note:", out)
        self.assertEqual(self._load(target)["prefix"], "BeaconMod: ")

    def test_same_prefix_with_nothing_missing_writes_nothing(self):
        target = self._rules(drop=(), prefix="BCN:")
        before = os.path.getmtime(target)
        code, out, _ = run("rules", self.plan, "--from", target, "--prefix", "BCN:", "--force")
        self.assertEqual(code, 0)
        self.assertIn("Nothing to add", out)
        self.assertEqual(os.path.getmtime(target), before)

    def test_no_note_or_warning_when_the_write_is_refused(self):
        target = self._rules()
        code, out, _ = run("rules", self.plan, "--from", target, "--prefix", "BCN:")
        self.assertEqual(code, 2)
        self.assertNotIn("Note:", out)
        target2 = self._rules(name="regex.json", prefix="^(A|B):")
        code, out, _ = run("rules", self.plan, "--from", target2)
        self.assertEqual(code, 2)
        self.assertNotIn("WARNING", out)

    def test_note_says_set_when_the_file_had_no_prefix(self):
        target = self._rules()
        data = self._load(target)
        del data["prefix"]
        write(target, json.dumps(data))
        code, out, err = run("rules", self.plan, "--from", target, "--prefix", "BCN:", "--force")
        self.assertEqual(code, 0, err)
        self.assertIn('set the file\'s prefix to "BCN:"', out)
        self.assertNotIn("null", out)

    def test_prefix_keeps_the_old_anchor(self):
        base = {"prefix": "^OLD:", "expect": []}
        data, _ = rules.starter_rules("M", "", {"go": [("1.1", "Go.")]}, prefix="NEW:", base=base)
        self.assertEqual(data["prefix"], "^NEW:")
        self.assertEqual(data["expect"][0]["re"], "NEW: go")
        data, _ = rules.starter_rules("M", "", {"go": [("1.1", "Go.")]}, prefix="NEW:", base={"prefix": "OLD:"})
        self.assertEqual(data["prefix"], "NEW:")

    def test_non_dict_entries_in_expect_are_not_a_crash(self):
        target = self._rules()
        data = self._load(target)
        data["expect"] = ["junk", 5, None] + data["expect"]
        data["forbid"] = ["more junk"]
        write(target, json.dumps(data))
        code, out, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 0, err)
        self.assertIn("New expect rule 'restored'", out)
        new = self._load(target)
        self.assertEqual(new["expect"][:3], ["junk", 5, None])
        self.assertEqual(new["expect"][-1]["id"], "restored")

    def test_text_that_cant_be_utf8_is_a_setup_error(self):
        target = self._rules()
        with open(target, encoding="utf-8") as f:
            text = f.read()
        write(target, text.replace('"mod": "', '"mod": "\\ud800', 1))
        with open(target, encoding="utf-8") as f:
            before = f.read()
        code, out, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 2)
        self.assertIn("can't be saved as UTF-8", err)
        self.assertIn(f"It comes from the --from file {target}", err)
        self.assertEqual(out, "")                      # checked before anything is printed
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)
        self.assertEqual(sorted(os.listdir(self.d)), ["Beacon.testplan.md", "mine.logrules.json"])

    def test_text_that_cant_be_utf8_without_from_names_prefix_or_plan(self):
        target = os.path.join(self.d, "r.json")
        code, out, err = run("rules", self.plan, "--out", target, "--prefix", "B\ud800:")
        self.assertEqual(code, 2)
        self.assertIn(f"It comes from --prefix or the plan {self.plan}", err)
        self.assertEqual(out, "")
        self.assertFalse(os.path.exists(target))


class SimplifyRoundTests(unittest.TestCase):
    """0.3.0 simplify round: links refused, mode put back after the move, ASCII printing, prefix sameness."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.plan = os.path.join(self.d, "Beacon.testplan.md")
        shutil.copy(EXAMPLE, self.plan)

    def _rules(self, name="mine.logrules.json", drop=("restored",), **changes):
        target = os.path.join(self.d, name)
        with open(EXAMPLE_RULES, encoding="utf-8") as f:
            data = json.load(f)
        data["expect"] = [r for r in data["expect"] if r["id"] not in drop]
        data.update(changes)
        write(target, json.dumps(data))
        return target

    def _load(self, path):
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    # 1, 2: links
    def test_a_link_is_refused_even_with_force(self):
        target = self._rules()
        with open(target, encoding="utf-8") as f:
            before = f.read()
        real_islink = os.path.islink
        with mock.patch("sftestplan.cli.os.path.islink", side_effect=lambda p: p == target or real_islink(p)):
            code, out, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 2)
        self.assertIn(f"--from {target} is a symbolic link. Without --out, the rule file is written back to the --from file, so give the rule file another name with --out, such as ", err)
        with open(target, encoding="utf-8") as f:
            self.assertEqual(f.read(), before)

    def _snapshot(self, path):
        """The file's bytes and modified time, and the folder's listing."""
        with open(path, "rb") as f:
            data = f.read()
        return data, os.stat(path).st_mtime_ns, sorted(os.listdir(self.d))

    def test_a_linked_from_file_with_nothing_to_add_still_exits_0(self):
        target = self._rules(drop=())
        # An old modified time, so a rewrite in the same clock tick still shows.
        os.utime(target, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        before = self._snapshot(target)
        real_islink = os.path.islink
        with mock.patch("sftestplan.cli.os.path.islink", side_effect=lambda p: p == target or real_islink(p)):
            code, out, err = run("rules", self.plan, "--from", target)
        self.assertEqual(code, 0, err)
        self.assertIn("Nothing to add, so nothing was written.", out)
        self.assertNotIn("symbolic link", err)
        self.assertEqual(self._snapshot(target), before)

    def test_a_real_symlinked_from_file_with_nothing_to_add_is_left_alone(self):
        real = self._rules(drop=())
        link = os.path.join(self.d, "link.logrules.json")
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"can't make a symlink here: {e}")
        os.utime(real, ns=(1_000_000_000_000_000_000, 1_000_000_000_000_000_000))
        before = self._snapshot(real)
        before_target = os.readlink(link)
        code, out, err = run("rules", self.plan, "--from", link)
        self.assertEqual(code, 0, err)
        self.assertIn("Nothing to add, so nothing was written.", out)
        self.assertTrue(os.path.islink(link))
        self.assertEqual(os.readlink(link), before_target)
        self.assertEqual(self._snapshot(real), before)

    def test_a_real_symlink_is_refused(self):
        real = self._rules()
        link = os.path.join(self.d, "link.logrules.json")
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"can't make a symlink here: {e}")
        code, _, err = run("rules", self.plan, "--from", link, "--force")
        self.assertEqual(code, 2)
        self.assertIn("is a symbolic link", err)
        self.assertTrue(os.path.islink(link))
        self.assertEqual(self._load(real)["expect"][-1]["id"], "placed")

    def test_a_dangling_symlink_is_refused(self):
        link = os.path.join(self.d, "dangling.logrules.json")
        try:
            os.symlink(os.path.join(self.d, "gone.json"), link)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"can't make a symlink here: {e}")
        code, _, err = run("rules", self.plan, "--out", link, "--force")
        self.assertEqual(code, 2)
        self.assertIn("is a symbolic link", err)
        self.assertFalse(os.path.exists(os.path.join(self.d, "gone.json")))

    def test_existing_check_counts_a_dangling_link(self):
        target = os.path.join(self.d, "r.json")
        with mock.patch("sftestplan.cli.os.path.lexists", side_effect=lambda p: p == target):
            code, _, err = run("rules", self.plan, "--out", target)
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    # 0.3.1: a refused run prints only its error (nothing on stdout before the refusal)
    def test_a_refused_link_run_prints_nothing_on_stdout(self):
        target = self._rules()
        real_islink = os.path.islink
        with mock.patch("sftestplan.cli.os.path.islink", side_effect=lambda p: p == target or real_islink(p)):
            code, out, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(f"--from {target} is a symbolic link. Without --out, the rule file is written back to the --from file, so give the rule file another name with --out, such as ", err)

    def test_a_refused_real_symlink_run_prints_nothing_on_stdout(self):
        real = self._rules()
        link = os.path.join(self.d, "link.logrules.json")
        try:
            os.symlink(real, link)
        except (OSError, NotImplementedError) as e:
            self.skipTest(f"can't make a symlink here: {e}")
        code, out, err = run("rules", self.plan, "--from", link, "--force")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("is a symbolic link", err)

    def test_a_refused_existing_file_run_prints_nothing_on_stdout(self):
        target = self._rules()
        code, out, err = run("rules", self.plan, "--from", target)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn(f"{target} already exists: add --force to add the new rules to it.", err)

    def test_a_refused_new_out_run_prints_nothing_on_stdout(self):
        target = os.path.join(self.d, "Beacon.logrules.json")
        write(target, "keep me")
        code, out, err = run("rules", self.plan)
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("already exists: pick another --out", err)

    def test_a_linked_from_file_with_nothing_to_add_still_prints_its_counts(self):
        target = self._rules(drop=())
        real_islink = os.path.islink
        with mock.patch("sftestplan.cli.os.path.islink", side_effect=lambda p: p == target or real_islink(p)):
            code, out, err = run("rules", self.plan, "--from", target)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.splitlines(), [
            f"{self.plan}: 3 log ids on 3 steps",
            f"Already in {target}: 3 of the 3 ids.",
            "Nothing to add, so nothing was written.",
        ])

    # 3: mode and temp-file cleanup
    def test_mode_is_put_back_on_the_file_after_the_move(self):
        target = self._rules()
        if os.name != "nt":
            os.chmod(target, 0o640)
        mode = stat.S_IMODE(os.stat(target).st_mode)
        with mock.patch("sftestplan.cli.os.chmod", wraps=os.chmod) as ch:
            code, _, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 0, err)
        self.assertEqual(ch.call_args_list, [mock.call(target, mode)])
        self.assertEqual(stat.S_IMODE(os.stat(target).st_mode), mode)
        self.assertEqual(self._load(target)["expect"][-1]["id"], "restored")

    def test_new_file_gets_no_chmod(self):
        target = os.path.join(self.d, "r.json")
        with mock.patch("sftestplan.cli.os.chmod", wraps=os.chmod) as ch:
            code, _, err = run("rules", self.plan, "--out", target)
        self.assertEqual(code, 0, err)
        self.assertEqual(ch.call_count, 0)

    def test_read_only_temp_file_is_still_removed(self):
        target = self._rules()
        real_remove = os.remove
        calls = []

        def remove_once_fails(p):
            calls.append(p)
            if len(calls) == 1:
                raise PermissionError(13, "Access is denied")
            real_remove(p)

        with mock.patch("sftestplan.cli.os.replace", side_effect=OSError(13, "Permission denied")), \
                mock.patch("sftestplan.cli.os.remove", side_effect=remove_once_fails), \
                mock.patch("sftestplan.cli.os.chmod", wraps=os.chmod) as ch:
            code, _, err = run("rules", self.plan, "--from", target, "--force")
        self.assertEqual(code, 2)
        self.assertEqual(len(calls), 2)
        self.assertEqual(ch.call_args_list, [mock.call(calls[0], stat.S_IWRITE)])
        self.assertEqual(sorted(os.listdir(self.d)), ["Beacon.testplan.md", "mine.logrules.json"])

    # 4: printing is ASCII
    def test_non_ascii_text_is_printed_escaped(self):
        p = os.path.join(self.d, "Uni.testplan.md")
        write(p, "# P\nrun: p-1\nmod: Uni\n\n## 1 G\n- [ ] Do it.\n  log: café\n")
        target = os.path.join(self.d, "u.json")
        code, out, err = run("rules", p, "--out", target, "--prefix", "ÉTÉ:")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.isascii(), out)
        self.assertIn("New expect rule 'caf\\u00e9'", out)
        self.assertIn('re "\\u00c9T\\u00c9: caf\\u00e9"', out)
        self.assertEqual(self._load(target)["expect"][0]["re"], "ÉTÉ: café")

    # 5: a prefix that already means the same text is unchanged
    def test_escaped_old_prefix_with_the_same_text_is_unchanged(self):
        target = self._rules(drop=(), prefix="^BCN\\:")
        before = os.path.getmtime(target)
        code, out, _ = run("rules", self.plan, "--from", target, "--prefix", "BCN:", "--force")
        self.assertEqual(code, 0)
        self.assertIn("Nothing to add", out)
        self.assertNotIn("Note:", out)
        self.assertEqual(os.path.getmtime(target), before)
        self.assertEqual(self._load(target)["prefix"], "^BCN\\:")

    def test_prefix_keeps_both_anchors(self):
        go = {"go": [("1.1", "Go.")]}
        data, _ = rules.starter_rules("M", "", go, prefix="NEW:", base={"prefix": "^OLD:$"})
        self.assertEqual(data["prefix"], "^NEW:$")
        data, _ = rules.starter_rules("M", "", go, prefix="NEW:", base={"prefix": "OLD\\$"})
        self.assertEqual(data["prefix"], "NEW:")
        data, _ = rules.starter_rules("M", "", go, prefix="OLD:", base={"prefix": "^OLD\\:$"})
        self.assertEqual(data["prefix"], "^OLD\\:$")

    # 6: the printed list comes from what starter_rules added
    def test_starter_rules_returns_the_new_rules(self):
        base = {"expect": [{"id": "a", "re": "x"}], "forbid": []}
        data, added = rules.starter_rules("M", "", {"a": [("1.1", "A.")], "b": [("1.2", "B.")]}, base=base)
        self.assertEqual(added, [{"id": "b", "re": "M: b", "means": "Step 1.2: B."}])
        self.assertIs(added[0], data["expect"][-1])

    def test_printed_rules_are_the_added_ones_not_the_tail_of_expect(self):
        target = os.path.join(self.d, "r.json")
        real = rules.starter_rules

        def add_then_append(*a, **k):
            data, added = real(*a, **k)
            data["expect"].append({"id": "loaded", "re": "tail"})   # an entry after the new ones
            return data, added

        with mock.patch("sftestplan.cli.rules.starter_rules", side_effect=add_then_append):
            code, out, err = run("rules", self.plan, "--out", target)
        self.assertEqual(code, 0, err)
        self.assertEqual(out.count("New expect rule"), 3)
        self.assertNotIn('"tail"', out)


if __name__ == "__main__":
    unittest.main()
