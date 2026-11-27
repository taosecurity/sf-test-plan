"""compare-builds and check-build on made-up zips and BA2 archives built in the test."""
import io
import json
import os
import struct
import sys
import tempfile
import unittest
import zipfile
import zlib
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import builds, cli  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def pex(body: bytes, stamp: int) -> bytes:
    """A made-up script: the pex magic, version and game id, an 8-byte compile time, then the body."""
    return b"\xde\xc0\x57\xfa" + b"\x03\x0c\x02\x00" + struct.pack("<Q", stamp) + body


def ba2(files: dict, packed: bool = True, version: int = 1, method: int = 0, magic: bytes = b"BTDX",
        lie_size: int | None = None) -> bytes:
    """A GNRL BA2 holding files {name: bytes}."""
    names = list(files)
    head = 24 + (8 if version in (2, 3) else 0) + (4 if version == 3 else 0)
    data_at = head + 36 * len(names)
    blobs, records, off = [], [], data_at
    for n in names:
        raw = files[n]
        stored = zlib.compress(raw) if packed else raw
        usize = len(raw) if lie_size is None else lie_size
        records.append(struct.pack("<I4sIIQIII", 0, b"pex\0", 0, 0, off, len(stored) if packed else 0, usize, 0))
        blobs.append(stored)
        off += len(stored)
    names_at = off
    out = struct.pack("<4sI4sIQ", magic, version, b"GNRL", len(names), names_at)
    if version in (2, 3):
        out += b"\0" * 8
    if version == 3:
        out += struct.pack("<I", method)
    out += b"".join(records) + b"".join(blobs)
    for n in names:
        enc = n.encode("utf-8")
        out += struct.pack("<H", len(enc)) + enc
    return out


class BuildsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory(prefix="sf test plan ")   # a path with spaces
        self.d = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def zip(self, name: str, files: dict, date=(2026, 1, 1, 0, 0, 0)) -> str:
        path = os.path.join(self.d, name)
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
            for n, data in files.items():
                zf.writestr(zipfile.ZipInfo(n, date), data)
        return path

    def compare(self, a, b, *extra):
        return run("compare-builds", a, b, *extra)

    # ---- plain plugins
    def test_same_plugins_other_dates_and_readme(self):
        a = self.zip("a.zip", {"Data/Mod.esm": b"ESM1", "readme.txt": b"one"})
        b = self.zip("b.zip", {"Data/Mod.esm": b"ESM1", "readme.txt": b"two"}, (2026, 5, 5, 0, 0, 0))
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 0, out)
        self.assertIn("Data/Mod.esm: same", out)
        self.assertIn("OK:", out)

    def test_esm_differs(self):
        a = self.zip("a.zip", {"Mod.esm": b"ESM1"})
        b = self.zip("b.zip", {"Mod.esm": b"ESM2"})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("Mod.esm: differs", out)
        self.assertIn("DIFFERENT: 1 of 1", out)

    def test_only_in_one(self):
        a = self.zip("a.zip", {"Mod.esm": b"E", "Mod - Main.ba2": ba2({"x.txt": b"x"})})
        b = self.zip("b.zip", {"Mod.esm": b"E", "Other.esp": b"P"})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("Mod - Main.ba2: only in tested", out)
        self.assertIn("Other.esp: only in built", out)
        self.assertIn("DIFFERENT: 2 of 3", out)

    def test_names_compared_case_blind_and_slashes(self):
        a = self.zip("a.zip", {"Data\\MOD.ESM": b"E"})
        b = self.zip("b.zip", {"data/mod.esm": b"E"})
        self.assertEqual(self.compare(a, b)[0], 0)

    # ---- BA2
    def test_ba2_recompiled_script_is_same(self):
        a = self.zip("a.zip", {"Mod - Main.ba2": ba2({"Scripts/Q.pex": pex(b"BODY", 1)})})
        b = self.zip("b.zip", {"Mod - Main.ba2": ba2({"Scripts/Q.pex": pex(b"BODY", 2)})})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 0, out)
        self.assertIn("scripts compared by meaning", out)

    def test_ba2_stored_unpacked_same(self):
        a = self.zip("a.zip", {"M.ba2": ba2({"q.pex": pex(b"B", 1)}, packed=False)})
        b = self.zip("b.zip", {"M.ba2": ba2({"q.pex": pex(b"B", 9)}, packed=False)})
        self.assertEqual(self.compare(a, b)[0], 0)

    def test_ba2_script_body_differs(self):
        a = self.zip("a.zip", {"M.ba2": ba2({"scripts/q.pex": pex(b"ONE", 1), "t.txt": b"t"})})
        b = self.zip("b.zip", {"M.ba2": ba2({"scripts/q.pex": pex(b"TWO", 1), "t.txt": b"t"})})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("1 of its files differ (scripts/q.pex)", out)

    def test_ba2_other_file_differs(self):
        a = self.zip("a.zip", {"M.ba2": ba2({"a.txt": b"1"})})
        b = self.zip("b.zip", {"M.ba2": ba2({"a.txt": b"2"})})
        self.assertEqual(self.compare(a, b)[0], 1)

    def test_ba2_file_only_in_one_archive(self):
        a = self.zip("a.zip", {"M.ba2": ba2({"a.txt": b"1"})})
        b = self.zip("b.zip", {"M.ba2": ba2({"a.txt": b"1", "b.txt": b"2"})})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("b.txt", out)

    def test_unreadable_ba2_compared_whole(self):
        a = self.zip("a.zip", {"M.ba2": b"NOT A BA2 one" * 4})
        b = self.zip("b.zip", {"M.ba2": b"NOT A BA2 two" * 4})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("compared as a whole file because it is not a BA2 archive", out)

    def test_lz4_ba2_compared_whole(self):
        a = self.zip("a.zip", {"M.ba2": ba2({"q.pex": pex(b"B", 1)}, version=3, method=3)})
        b = self.zip("b.zip", {"M.ba2": ba2({"q.pex": pex(b"B", 2)}, version=3, method=3)})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("LZ4", out)

    def test_zlib_v3_ba2_read(self):
        a = self.zip("a.zip", {"M.ba2": ba2({"q.pex": pex(b"B", 1)}, version=3, method=0)})
        b = self.zip("b.zip", {"M.ba2": ba2({"q.pex": pex(b"B", 2)}, version=3, method=0)})
        self.assertEqual(self.compare(a, b)[0], 0)

    def test_packed_file_larger_than_stated(self):
        a = self.zip("a.zip", {"M.ba2": ba2({"a.txt": b"A" * 5000}, lie_size=10)})
        b = self.zip("b.zip", {"M.ba2": ba2({"a.txt": b"B" * 5000}, lie_size=10)})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("more than its stated size", out)

    def test_cut_short_ba2(self):
        whole = ba2({"a.txt": b"1"})
        a = self.zip("a.zip", {"M.ba2": whole[:30]})
        b = self.zip("b.zip", {"M.ba2": whole[:31]})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("whole file", out)

    # ---- pins
    def pins(self, name, tested, built, why="only the header date changed"):
        path = os.path.join(self.d, "pins.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "sf-test-plan-pins/1", "pins": {name: {"tested": tested, "built": built, "why": why}}}, f)
        return path

    def shas(self, a, b, name):
        with zipfile.ZipFile(a) as za, zipfile.ZipFile(b) as zb:
            return builds._sha16(za, za.getinfo(name)), builds._sha16(zb, zb.getinfo(name))

    def test_pinned_pair_is_warning(self):
        a = self.zip("a.zip", {"Mod.esm": b"ESM1"})
        b = self.zip("b.zip", {"Mod.esm": b"ESM2"})
        sa, sb = self.shas(a, b, "Mod.esm")
        code, out, _ = self.compare(a, b, "--pins", self.pins("mod.esm", sa, sb))
        self.assertEqual(code, 0, out)
        self.assertIn("Mod.esm: pinned: only the header date changed", out)
        self.assertIn("WARNING:", out)

    def test_pin_for_other_pair_still_differs(self):
        a = self.zip("a.zip", {"Mod.esm": b"ESM1"})
        b = self.zip("b.zip", {"Mod.esm": b"ESM2"})
        sa, _ = self.shas(a, b, "Mod.esm")
        code, _, _ = self.compare(a, b, "--pins", self.pins("mod.esm", sa, "0" * 16))
        self.assertEqual(code, 1)

    def test_bad_pins_is_exit_2(self):
        a = self.zip("a.zip", {"Mod.esm": b"E"})
        path = self.pins("mod.esm", "nothex", "0" * 16)
        code, _, err = self.compare(a, a, "--pins", path)
        self.assertEqual(code, 2)
        self.assertIn("bad pin", err)
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not json")
        self.assertEqual(self.compare(a, a, "--pins", path)[0], 2)
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"format": "other/1", "pins": {}}, f)
        self.assertEqual(self.compare(a, a, "--pins", path)[0], 2)

    # ---- DLL-only and empty
    def test_dll_only_compares_every_file(self):
        a = self.zip("a.zip", {"SFSE/Plugins/X.dll": b"D1", "SFSE/Plugins/X.ini": b"i"})
        b = self.zip("b.zip", {"SFSE/Plugins/X.dll": b"D1", "SFSE/Plugins/X.ini": b"i"})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 0)
        self.assertIn("X.dll: same", out)
        c = self.zip("c.zip", {"SFSE/Plugins/X.dll": b"D2", "SFSE/Plugins/X.ini": b"i"})
        code, out, _ = self.compare(a, c)
        self.assertEqual(code, 1)
        self.assertIn("X.dll: differs", out)

    def test_dll_only_report_says_files(self):
        a = self.zip("a.zip", {"SFSE/Plugins/X.dll": b"D1"})
        b = self.zip("b.zip", {"SFSE/Plugins/X.dll": b"D2"})
        self.assertIn("DIFFERENT: 1 of 1 files differ.", self.compare(a, b)[1])
        self.assertIn("OK: the built zip has the same files as the tested zip.", self.compare(a, a)[1])

    # ---- loose files next to a plugin (0.5.0)
    def test_dll_beside_plugin_differs(self):
        a = self.zip("a.zip", {"Data/Mod.esm": b"E", "Data/SFSE/Plugins/X.dll": b"D1"})
        b = self.zip("b.zip", {"Data/Mod.esm": b"E", "Data/SFSE/Plugins/X.dll": b"D2"})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1, out)
        self.assertIn("Data/SFSE/Plugins/X.dll: differs", out)
        self.assertIn("DIFFERENT: 1 of 2 files differ.", out)

    def test_loose_file_beside_plugin_only_in_one(self):
        a = self.zip("a.zip", {"Data/Mod.esm": b"E"})
        b = self.zip("b.zip", {"Data/Mod.esm": b"E", "Data/SFSE/Plugins/X.ini": b"i"})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1, out)
        self.assertIn("X.ini: only in built", out)

    def test_same_files_beside_plugin_ok(self):
        files = {"Data/Mod.esm": b"E", "Data/SFSE/Plugins/X.dll": b"D1", "readme.txt": b"r"}
        a, b = self.zip("a.zip", files), self.zip("b.zip", dict(files, **{"readme.txt": b"new", "CHANGES.md": b"c"}))
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 0, out)
        self.assertIn("X.dll: same", out)

    def test_packaging_files_beside_plugin_ignored(self):
        # A release bumps the fomod version, refreshes its picture and license; the mod itself is the same.
        files = {"Data/Mod.esm": b"E", "Data/SFSE/Plugins/X.dll": b"D1", "fomod/info.xml": b"<Version>0.1.0</Version>",
                 "fomod/images/cover.png": b"p1", "LICENSE": b"l1", "Screenshot.jpg": b"j1"}
        a = self.zip("a.zip", files)
        b = self.zip("b.zip", dict(files, **{"fomod/info.xml": b"<Version>1.0.0</Version>",
                                            "fomod/images/cover.png": b"p2", "LICENSE": b"l2", "Screenshot.jpg": b"j2",
                                            "__MACOSX/Data/._Mod.esm": b"x", "Data/Thumbs.db": b"t"}))
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 0, out)
        self.assertNotIn("fomod", out)
        b2 = self.zip("b2.zip", dict(files, **{"fomod/info.xml": b"<Version>1.0.0</Version>",
                                              "Data/SFSE/Plugins/X.dll": b"D2"}))
        code, out, _ = self.compare(a, b2)
        self.assertEqual(code, 1, out)   # the DLL still counts
        self.assertIn("DIFFERENT: 1 of 2 files differ.", out)

    # ---- loose scripts next to a plugin
    def test_loose_script_change_differs(self):
        a = self.zip("a.zip", {"Data/Mod.esm": b"E", "Data/Scripts/ModQuest.pex": pex(b"body one", 1)})
        b = self.zip("b.zip", {"Data/Mod.esm": b"E", "Data/Scripts/ModQuest.pex": pex(b"body two", 1)})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1, out)
        self.assertIn("Data/Scripts/ModQuest.pex: differs", out)
        self.assertIn("DIFFERENT: 1 of 2 files differ.", out)

    def test_loose_script_recompiled_is_same(self):
        a = self.zip("a.zip", {"Data/Mod.esm": b"E", "Data/Scripts/ModQuest.pex": pex(b"body", 1)})
        b = self.zip("b.zip", {"Data/Mod.esm": b"E", "Data/Scripts/ModQuest.pex": pex(b"body", 999)})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 0, out)
        self.assertIn("OK: the built zip has the same plugins, scripts and other files as the tested zip.", out)

    def test_loose_script_only_in_one(self):
        a = self.zip("a.zip", {"Data/Mod.esm": b"E"})
        b = self.zip("b.zip", {"Data/Mod.esm": b"E", "Data/Scripts/New.pex": pex(b"x", 1)})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("Data/Scripts/New.pex: only in built", out)

    def test_both_empty(self):
        a = self.zip("a.zip", {})
        b = self.zip("b.zip", {})
        code, out, _ = self.compare(a, b)
        self.assertEqual(code, 1)
        self.assertIn("Both zips are empty", out)

    # ---- bad input
    def test_missing_zip_is_exit_2(self):
        a = self.zip("a.zip", {"Mod.esm": b"E"})
        code, _, err = self.compare(a, os.path.join(self.d, "none.zip"))
        self.assertEqual(code, 2)
        self.assertIn("doesn't exist", err)

    def test_not_a_zip_is_exit_2(self):
        a = self.zip("a.zip", {"Mod.esm": b"E"})
        bad = os.path.join(self.d, "bad.zip")
        with open(bad, "wb") as f:
            f.write(b"not a zip")
        self.assertEqual(self.compare(a, bad)[0], 2)

    def test_json_output(self):
        a = self.zip("a.zip", {"Mod.esm": b"E1"})
        b = self.zip("b.zip", {"Mod.esm": b"E2"})
        code, out, _ = self.compare(a, b, "--json")
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["format"], "sf-test-plan-compare/1")
        self.assertFalse(data["same"])
        self.assertEqual(data["entries"][0]["status"], "differs")

    def test_help_exits_0(self):
        for cmd in ("compare-builds", "check-build"):
            self.assertEqual(run(cmd, "--help")[0], 0)

    # ---- check-build
    def plan(self, zip_line: str) -> str:
        sub = os.path.join(self.d, "plans folder")
        os.makedirs(sub, exist_ok=True)
        path = os.path.join(sub, "Mod.testplan.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(f"# Mod test plan\nrun: mod-0.1.0\nmod: Mod\n{zip_line}\n\n## 1 Load\n"
                    "- [ ] Start a new game.\n  Expect: no error.\n  smoke: yes\n")
        return path

    def test_check_build_zip_from_plan_folder(self):
        plan = self.plan("zip: tested zips/Mod-0.1.0.zip")
        os.makedirs(os.path.join(self.d, "plans folder", "tested zips"))
        self.zip(os.path.join("plans folder", "tested zips", "Mod-0.1.0.zip"), {"Mod.esm": b"E"})
        same = self.zip("built same.zip", {"Mod.esm": b"E"})
        other = self.zip("built other.zip", {"Mod.esm": b"F"})
        code, out, _ = run("check-build", plan, "--built", same)
        self.assertEqual(code, 0, out)
        code, out, _ = run("check-build", plan, "--built", other)
        self.assertEqual(code, 1)
        self.assertIn("Rebuild the test zip from the current build", out)
        self.assertIn("Mod.esm differs", out)

    def test_check_build_no_zip_line(self):
        plan = self.plan("")
        built = self.zip("b.zip", {"Mod.esm": b"E"})
        code, _, err = run("check-build", plan, "--built", built)
        self.assertEqual(code, 2)
        self.assertIn("no zip: line", err)
        self.assertEqual(run("check-build", plan, "--built", built, "--tested", built)[0], 0)

    def test_check_build_zip_line_missing_file(self):
        plan = self.plan("zip: gone.zip")
        built = self.zip("b.zip", {"Mod.esm": b"E"})
        self.assertEqual(run("check-build", plan, "--built", built)[0], 2)

    def test_check_build_pinned_warning(self):
        tested = self.zip("t.zip", {"Mod.esm": b"E1"})
        built = self.zip("b.zip", {"Mod.esm": b"E2"})
        sa, sb = self.shas(tested, built, "Mod.esm")
        plan = self.plan(f"zip: {tested}")
        code, out, _ = run("check-build", plan, "--built", built, "--pins", self.pins("mod.esm", sa, sb))
        self.assertEqual(code, 0, out)
        self.assertIn("WARNING:", out)

    def test_tested_zip_relative_to_plan_as_given(self):
        self.assertEqual(builds.tested_zip_from_plan(os.path.join("examples", "p.md"), "M-0.1.0.zip"),
                         os.path.join("examples", "M-0.1.0.zip"))
        self.assertEqual(builds.tested_zip_from_plan("p.md", "M-0.1.0.zip"), "M-0.1.0.zip")

    def test_tested_zip_absolute_kept(self):
        absolute = os.path.join(self.d, "x.zip")
        self.assertEqual(builds.tested_zip_from_plan(os.path.join(self.d, "p.md"), absolute), absolute)


if __name__ == "__main__":
    unittest.main()
