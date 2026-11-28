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


class PinsFileReading(Base):
    """Rows 10 and 3: --pins reads a byte-order mark and UTF-16 like the marks and report files; the warning ends in a period."""

    def zips(self):
        a, b = self.path("a.zip"), self.path("b.zip")
        for path, body in ((a, b"ESM1"), (b, b"ESM2")):
            with zipfile.ZipFile(path, "w") as z:
                z.writestr("Mod.esm", body)
        with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
            return a, b, builds._sha16(za, za.getinfo("Mod.esm")), builds._sha16(zb, zb.getinfo("Mod.esm"))

    def pins_bytes(self, sa, sb, why, encoding):
        doc = {"format": "sf-test-plan-pins/1", "pins": {"mod.esm": {"tested": sa, "built": sb, "why": why}}}
        path = self.path("pins.json")
        with open(path, "wb") as f:
            f.write(json.dumps(doc).encode(encoding))
        return path

    def test_bom_and_utf16_pins_are_read(self):
        a, b, sa, sb = self.zips()
        for enc in ("utf-8-sig", "utf-16"):
            code, out, err = run("compare-builds", a, b, "--pins", self.pins_bytes(sa, sb, "only the date", enc))
            self.assertEqual(code, 0, (enc, out, err))
            self.assertIn("pinned", out)

    def test_check_build_pin_warning_has_a_period(self):
        a, b, sa, sb = self.zips()
        pins = self.pins_bytes(sa, sb, "only the date changed", "utf-8")
        code, out, err = run("check-build", self.write("p.testplan.md", PLAN), "--tested", a, "--built", b, "--pins", pins)
        self.assertEqual(code, 0, out + err)
        self.assertIn("exact pair: only the date changed. The tested zip is", out)
        pins = self.pins_bytes(sa, sb, "only the date changed.", "utf-8")
        code, out, err = run("check-build", self.write("p.testplan.md", PLAN), "--tested", a, "--built", b, "--pins", pins)
        self.assertIn("exact pair: only the date changed. The tested zip is", out)


class FragmentStylesheet(Base):
    """Row 1: render --assets also writes a style sheet scoped to .sf-test-plan; row 16: the page.js comment."""

    def test_assets_hold_a_scoped_fragment_sheet(self):
        plan = self.write("p.testplan.md", PLAN)
        out, assets = self.path("frag.html"), self.path("assets")
        code, so, err = run("render", plan, "--fragment", "--out", out, "--assets", assets)
        self.assertEqual(code, 0, so + err)
        with open(os.path.join(assets, "sf-test-plan-fragment.css"), encoding="utf-8") as f:
            css = f.read()
        import re
        body = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        for m in re.finditer(r"(?:^|[}\n])\s*([^{}@\n][^{}]*)\{", body):
            for sel in m.group(1).split(","):
                sel = sel.strip()
                if sel and not re.match(r"^(\.sf-test-plan|:root(:not\(\[data-theme=\"light\"\]\)|\[data-theme=\"dark\"\]) \.sf-test-plan)", sel):
                    self.fail(f"selector not scoped to .sf-test-plan: {sel}")
        self.assertNotIn("body{", body)
        # the whole-page sheet is still written, unchanged
        self.assertTrue(os.path.exists(os.path.join(assets, "sf-test-plan.css")))

    def test_page_script_comment_is_not_stale(self):
        with open(os.path.join(ROOT, "assets", "page.js"), encoding="utf-8") as f:
            self.assertNotIn("This matches `sf-test-plan import`", f.read())


class CodeReviewRound1(Base):
    """0.5.1 code review round 1: --log over a default output, escapes in --verbose lines, drives with file ID 0,
    a folder with a colon, new over a mod file, and the pinned-pair warning's ending."""

    def test_log_naming_the_default_page_is_refused(self):
        plan = self.write("p.testplan.md", PLAN)
        page = self.path("p.testplan.html")
        code, out, err = run("build", plan, "--log", page)
        self.assertEqual(code, 2, out + err)
        self.assertIn("is the default page, so nothing was written", err)
        self.assertFalse(os.path.exists(page))

    def test_log_naming_the_default_marks_file_is_refused(self):
        plan = self.write("p.testplan.md", PLAN)
        rep = self.write("r.json", json.dumps(REPORT))
        code, out, err = run("logs", rep, "--plan", plan, "--log", self.path("r.marks.json"))
        self.assertEqual(code, 2, out + err)
        self.assertIn("is the default marks file, so nothing was written", err)
        self.assertFalse(os.path.exists(self.path("r.marks.json")))

    def test_log_naming_the_default_rule_file_or_an_asset_is_refused(self):
        plan = self.write("p.testplan.md", PLAN)
        code, out, err = run("rules", plan, "--log", self.path("p.logrules.json"))
        self.assertEqual(code, 2, out + err)
        self.assertIn("is the default rule file", err)
        assets = self.path("assets")
        os.mkdir(assets)
        code, out, err = run("render", plan, "--out", self.path("x.html"), "--assets", assets,
                             "--log", os.path.join(assets, "sf-test-plan.css"))
        self.assertEqual(code, 2, out + err)
        self.assertIn("is one of the --assets files", err)
        self.assertEqual(os.listdir(assets), [])

    def test_verbose_line_escapes_a_hostile_entry_name(self):
        name = "Data/Scripts/evil\x1b[31mred.pex"
        a = self.zip("a.zip", {name: b"not a script 1"})
        b = self.zip("b.zip", {name: b"not a script 2"})
        code, out, err = run("compare-builds", a, b, "--verbose")
        self.assertEqual(code, 1, out + err)
        self.assertIn("compared by bytes", err)
        self.assertNotIn("\x1b", out + err)
        self.assertIn("evil\\u001b[31mred.pex", err)

    def test_file_id_zero_is_not_the_same_file(self):
        from unittest import mock
        one, two = self.write("one.txt", "1"), self.write("two.txt", "2")
        real = os.stat

        def zero_ino(path, *a, **k):
            s = real(path, *a, **k)
            return os.stat_result((s.st_mode, 0, s.st_dev, s.st_nlink, s.st_uid, s.st_gid, s.st_size,
                                   int(s.st_atime), int(s.st_mtime), int(s.st_ctime)))
        with mock.patch("os.stat", zero_ino):
            self.assertFalse(cli._same_file(one, two))
        self.assertTrue(cli._same_file(one, one))

    def test_colon_only_in_the_file_name_counts(self):
        cli._refuse_mod_file_name(os.path.join("runs", "10:00", "page.html"), "--out x", "Fix")
        with self.assertRaises(cli.SetupError):
            cli._refuse_mod_file_name(os.path.join("runs", "report.txt:hidden"), "--out x", "Fix")

    def test_new_refuses_a_mod_file_name(self):
        esm = self.path("MyMod.esm")
        with open(esm, "wb") as f:
            f.write(b"TES4 plugin bytes")
        code, out, err = run("new", esm, "--force")
        self.assertEqual(code, 2, out + err)
        self.assertIn("is named like a mod file", err)
        with open(esm, "rb") as f:
            self.assertEqual(f.read(), b"TES4 plugin bytes")

    def test_pin_warning_ending(self):
        p = PinsFileReading("test_bom_and_utf16_pins_are_read")
        p.d, p.path = self.d, self.path
        a, b, sa, sb = p.zips()
        for why, want in (("", "exact pair. The tested"), ("is it the date?", "exact pair: is it the date? The tested")):
            pins = p.pins_bytes(sa, sb, why, "utf-8")
            code, out, err = run("check-build", self.write("p.testplan.md", PLAN), "--tested", a, "--built", b, "--pins", pins)
            self.assertEqual(code, 0, out + err)
            self.assertIn(want, out)


class CodeReviewRound2(Base):
    """0.5.1 code review round 2: --out NUL with --log NUL, --log over the --base plan's results file, and the
    fragment sheet's column layout (a fragment has no .wrap element)."""

    def test_out_and_log_both_the_null_device(self):
        plan = self.write("p.testplan.md", PLAN)
        code, out, err = run("build", plan, "--out", os.devnull, "--log", os.devnull)
        self.assertEqual(code, 0, out + err)

    def test_log_naming_the_base_results_file_is_refused(self):
        import argparse
        base = self.write("b.testplan.md", PLAN)
        args = argparse.Namespace(log=results.results_path(base), base=base, plan=self.path("m.testplan.md"),
                                  out=self.path("s.testplan.md"), func=cli.cmd_ngplus)
        with self.assertRaises(cli.SetupError) as cm:
            cli._refuse_log_over_file(args)
        self.assertIn("is the plan's results file", str(cm.exception))

    def test_fragment_sheet_lays_out_the_fragment_div(self):
        import re
        plan = self.write("p.testplan.md", PLAN)
        out, assets = self.path("frag.html"), self.path("assets")
        code, so, err = run("render", plan, "--fragment", "--out", out, "--assets", assets)
        self.assertEqual(code, 0, so + err)
        self.assertNotIn('class="wrap"', self.read("frag.html"))
        with open(os.path.join(assets, "sf-test-plan-fragment.css"), encoding="utf-8") as f:
            css = re.sub(r"/\*.*?\*/", "", f.read(), flags=re.S)
        rules = re.findall(r"(?:^|(?<=\}))\s*\.sf-test-plan\{([^}]*)\}", css)
        layout = " ".join(rules)
        for want in ("display:grid", "gap:22px", "max-width:76rem"):
            self.assertIn(want, layout)


class CodeReviewRound3(Base):
    """0.5.1 code review round 3: the README's pins limit and pinned example match the code, a colon in a file
    name is refused only on Windows, and a --pins read error names the option."""

    def readme(self):
        with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
            return f.read()

    def test_readme_gives_no_folder_key_workaround(self):
        # load_pins cuts every key to its file name, so a key "with its folder" can't tell two files apart
        p = self.write("pins.json", json.dumps({"format": "sf-test-plan-pins/1", "pins": {
            "Data/SFSE/Plugins/a/mod.dll": {"tested": "0" * 16, "built": "1" * 16, "why": "a"},
            "Data/SFSE/Plugins/b/mod.dll": {"tested": "2" * 16, "built": "3" * 16, "why": "b"}}}))
        self.assertEqual(list(builds.load_pins(p)), ["mod.dll"])
        self.assertNotIn("Write the key with its folder", self.readme())

    def test_readme_pinned_warning_matches_the_output(self):
        p = PinsFileReading("test_bom_and_utf16_pins_are_read")
        p.d, p.path = self.d, self.path
        a, b, sa, sb = p.zips()
        pins = p.pins_bytes(sa, sb, "rebuilt with the same content", "utf-8")
        code, out, err = run("compare-builds", a, b, "--pins", pins)
        self.assertEqual(code, 0, out + err)
        line = "WARNING: Mod.esm differs, but the --pins file allows this exact pair: rebuilt with the same content."
        self.assertIn(line, out + err)
        self.assertIn(line.replace("Mod.esm", "BeaconMod.esm") + "\n", self.readme())

    def test_colon_in_a_file_name_is_refused_only_on_windows(self):
        from unittest import mock
        name = os.path.join("runs", "report-12:30.html")
        with mock.patch.object(cli.os, "name", "posix"):
            cli._refuse_mod_file_name(name, "--out x", "Fix")
        with mock.patch.object(cli.os, "name", "nt"):
            with self.assertRaises(cli.SetupError):
                cli._refuse_mod_file_name(name, "--out x", "Fix")

    def test_unreadable_pins_file_names_the_option(self):
        a = self.zip("a.zip", {"Data/StarlightMod.esm": b"E"})
        code, out, err = run("compare-builds", a, a, "--pins", self.path("pins.jsn"))
        self.assertEqual(code, 2, out + err)
        self.assertIn("the --pins file: can't read", err)
        bad = self.write("bad.json", "{not json")
        code, out, err = run("compare-builds", a, a, "--pins", bad)
        self.assertEqual(code, 2, out + err)
        self.assertIn("the --pins file: ", err)
        self.assertIn("isn't valid JSON", err)


class CodeReviewRound4(Base):
    """0.5.1 code review round 4: the --verbose reason is escaped too (it can quote text from inside a script), and
    logs names the report file when its mods list is empty."""

    def test_verbose_reason_escapes_text_from_the_script(self):
        import hashlib
        from unittest import mock
        bad = builds.pex.PexError("object evil\x1b[2J‮name read 3 bytes but its size field says 9")
        with mock.patch.object(builds.pex, "listing", side_effect=bad):
            with self.assertLogs(builds.log, level="DEBUG") as cm:
                builds._pex_digest(hashlib.sha256(), b"x" * 20, "Data/Scripts/a.pex")
        text = "\n".join(cm.output)
        self.assertNotIn("\x1b", text)
        self.assertNotIn("‮", text)
        self.assertIn("evil\\u001b[2J\\u202ename", text)

    def test_empty_mods_list_names_the_report(self):
        plan = self.write("p.testplan.md", PLAN)
        report = self.write("empty-report.json", json.dumps({"mods": []}))
        code, out, err = run("logs", report, "--plan", plan)
        self.assertEqual(code, 2, out + err)
        self.assertIn("empty-report.json lists no mods", err)


if __name__ == "__main__":
    unittest.main()
