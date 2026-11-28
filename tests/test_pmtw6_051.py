"""0.5.1 (PMTW6): the folder rule of compare-builds, --log refusing to name an input, and logs --out needing
--force over an existing file. Made-up mods and files only."""
import io
import json
import os
import sys
import tempfile
import unittest
import zipfile
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import builds, cli, results  # noqa: E402

PLAN = "# T\nrun: a\n\n## 1 G\n- [ ] one\n  log: x\n"
REPORT = {"mods": [{"mod": "M", "status": "PASS", "rules": [{"kind": "expect", "id": "x", "status": "PASS"}]}]}


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Base(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sf test plan ")
        self.d = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name):
        return os.path.join(self.d, name)

    def write(self, name, text):
        with open(self.path(name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return self.path(name)

    def read(self, name):
        with open(self.path(name), encoding="utf-8") as f:
            return f.read()

    def zip(self, name, files):
        with zipfile.ZipFile(self.path(name), "w", zipfile.ZIP_DEFLATED) as zf:
            for n, data in files.items():
                zf.writestr(zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0)), data)
        return self.path(name)


class FolderRule(Base):
    """Row 8: a document or picture is left out only outside the game's folders."""

    def test_triage_repro_fontconfig_change_is_a_difference(self):
        # The triage repro: only Data/Interface/fontconfig.txt changed, which the game reads. 0.5.0 said OK.
        a = self.zip("a.zip", {"Data/StarlightMod.esm": b"E", "Data/Interface/fontconfig.txt": b"map one"})
        b = self.zip("b.zip", {"Data/StarlightMod.esm": b"E", "Data/Interface/fontconfig.txt": b"map two"})
        code, out, _ = run("compare-builds", a, b)
        self.assertEqual(code, 1, out)
        self.assertIn("Data/Interface/fontconfig.txt: differs", out)

    def test_documents_and_pictures_in_game_folders_count(self):
        base = {"Data/StarlightMod.esm": b"E"}
        for name in ("Data/SFSE/Plugins/StarlightMod/notes.txt", "Data/MCM/Config/StarlightMod/icon.png",
                     "StarlightMod/Data/Interface/Translations/StarlightMod_en.txt", "Data/Textures/Overlay.png"):
            with self.subTest(name=name):
                a = self.zip("a.zip", dict(base, **{name: b"one"}))
                b = self.zip("b.zip", dict(base, **{name: b"two"}))
                code, out, _ = run("compare-builds", a, b)
                self.assertEqual(code, 1, out)
                self.assertIn(f"{name}: differs", out)
                self.assertFalse(builds._is_packaging(name.lower()))

    def test_packaging_outside_game_folders_still_ignored(self):
        files = {"Data/StarlightMod.esm": b"E"}
        docs = ("readme.txt", "Data/StarlightMod - Readme.md", "Docs/guide.pdf", "Images/cover.png",
                "StarlightMod/LICENSE", "fomod/images/cover.png", "Data/Interface/Thumbs.db",
                "__MACOSX/Data/Interface/._x.txt")
        a = self.zip("a.zip", dict(files, **{n: b"one" for n in docs}))
        b = self.zip("b.zip", dict(files, **{n: b"two" for n in docs}))
        code, out, _ = run("compare-builds", a, b)
        self.assertEqual(code, 0, out)
        for n in docs:
            self.assertTrue(builds._is_packaging(n.lower()), n)


class LogNamesAnInput(Base):
    """Row 7: --log naming the plan (or another input) emptied it before it was read."""

    def test_log_naming_the_plan_is_refused_and_plan_kept(self):
        plan = self.write("p.testplan.md", PLAN)
        code, out, err = run("check", plan, "--log", plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn(f"--log {plan} is the plan, so nothing was written", err)
        self.assertEqual(self.read("p.testplan.md"), PLAN)

    def test_log_naming_the_pins_file_is_refused(self):
        a = self.zip("a.zip", {"Data/StarlightMod.esm": b"E"})
        pins = self.write("pins.json", '{"format": "sf-test-plan-pins/1", "pins": {}}')
        code, _, err = run("compare-builds", a, a, "--pins", pins, "--log", pins)
        self.assertEqual(code, 2, err)
        self.assertIn("is the --pins file", err)
        self.assertIn("sf-test-plan-pins/1", self.read("pins.json"))

    def test_log_naming_the_results_file_is_refused(self):
        plan = self.write("p.testplan.md", PLAN)
        res = results.results_path(plan)
        with open(res, "w", encoding="utf-8") as f:
            f.write("keep")
        marks = self.write("m.json", "{}")
        code, _, err = run("import", marks, "--plan", plan, "--log", res)
        self.assertEqual(code, 2, err)
        self.assertIn("is the plan's results file", err)
        with open(res, encoding="utf-8") as f:
            self.assertEqual(f.read(), "keep")

    def test_log_elsewhere_still_works(self):
        plan = self.write("p.testplan.md", PLAN)
        code, out, err = run("check", plan, "--log", self.path("run.log"))
        self.assertEqual(code, 0, out + err)
        self.assertIn("read plan", self.read("run.log"))


class LogsOutNeedsForce(Base):
    """Row 13: logs --out replaced an existing file without --force."""

    def setUp(self):
        super().setUp()
        self.plan = self.write("p.testplan.md", PLAN)
        self.rep = self.write("r.json", json.dumps(REPORT))

    def test_existing_out_needs_force(self):
        out = self.write("marks.json", "keep")
        code, so, err = run("logs", self.rep, "--plan", self.plan, "--out", out)
        self.assertEqual(code, 2, so + err)
        self.assertIn(f"--out {out} already exists, so nothing was written. Add --force", err)
        self.assertEqual(so, "")
        self.assertEqual(self.read("marks.json"), "keep")
        code, so, err = run("logs", self.rep, "--plan", self.plan, "--out", out, "--force")
        self.assertEqual(code, 0, so + err)
        self.assertEqual(json.loads(self.read("marks.json"))["checks"][0]["id"], "1.1")

    def test_default_out_second_run_needs_force(self):
        self.assertEqual(run("logs", self.rep, "--plan", self.plan)[0], 0)
        code, _, err = run("logs", self.rep, "--plan", self.plan)
        self.assertEqual(code, 2, err)
        self.assertIn("The default marks file", err)
        self.assertIn("already exists", err)
        self.assertEqual(run("logs", self.rep, "--plan", self.plan, "--force")[0], 0)


if __name__ == "__main__":
    unittest.main()
