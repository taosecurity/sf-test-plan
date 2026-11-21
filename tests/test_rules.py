"""The rules command and sftestplan.rules: starter papyrus-log-check rule files from a plan's log: ids."""
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

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
        self.assertEqual(added, ["loaded", "placed"])
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
        self.assertEqual(added, ["new"])
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

    def test_empty_prefix_is_exit_2(self):
        code, _, err = run("rules", self.plan, "--prefix", " ")
        self.assertEqual(code, 2)
        self.assertIn("--prefix is empty", err)

    def test_default_out_names(self):
        self.assertEqual(cli._default_rules_out("a/Mod.testplan.md"), "a/Mod.logrules.json")
        self.assertEqual(cli._default_rules_out("Mod.md"), "Mod.logrules.json")
        self.assertEqual(cli._default_rules_out("Mod.txt"), "Mod.txt.logrules.json")


if __name__ == "__main__":
    unittest.main()
