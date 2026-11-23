"""0.4.0 /code-review round 4 fixes: non-UTF-8 text in a script or a BA2 file name is kept byte for byte (so two
different strings never read as the same), and the shared New Game+ plan's zip: still points at the base plan's zip."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sftestplan import builds, parse, pex  # noqa: E402
from test_builds import ba2  # noqa: E402
from test_ngplus import BASE, LANTERN, run  # noqa: E402
from test_pex import PexWriter  # noqa: E402


class NonUtf8TextIsKept(unittest.TestCase):
    def test_scripts_with_different_windows_1252_text_differ(self):
        base = PexWriter().build(greeting="CafQ")
        a = base.replace(b"CafQ", b"Caf\xe9")   # e-acute in Windows-1252
        b = base.replace(b"CafQ", b"Caf\xe8")   # e-grave
        self.assertNotEqual(a, b)
        self.assertNotEqual(pex.listing(a), pex.listing(b))

    def test_utf8_text_still_reads_as_utf8(self):
        self.assertEqual(pex.text("Café".encode("utf-8")), "Café")

    def test_ba2_names_with_windows_1252_letters_stay_apart(self):
        raw = ba2({"scripts/cafQ.pex": b"one", "scripts/cafZ.pex": b"two"})
        raw = raw.replace(b"cafQ", b"caf\xe9").replace(b"cafZ", b"caf\xe8")
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "Mod - Main.ba2")
            with open(path, "wb") as f:
                f.write(raw)
            self.assertEqual(len(builds.ba2_digests(path)), 2)


class SharedPlanZipPointsAtBaseZip(unittest.TestCase):
    def test_zip_is_rewritten_for_the_out_folder(self):
        with tempfile.TemporaryDirectory(prefix="ng plus ") as d:
            os.makedirs(os.path.join(d, "Base"))
            os.makedirs(os.path.join(d, "Shared"))
            base = os.path.join(d, "Base", "Base.testplan.md")
            with open(base, "w", encoding="utf-8", newline="\n") as f:
                f.write(BASE.replace("run: ngplus-1\n", "run: ngplus-1\nzip: Mod-0.1.0.zip\n"))
            lantern = os.path.join(d, "Lantern.testplan.md")
            with open(lantern, "w", encoding="utf-8", newline="\n") as f:
                f.write(LANTERN)
            out = os.path.join(d, "Shared", "NG.testplan.md")
            code, text, err = run("ngplus", "--base", base, "--order", os.path.join(d, "order.json"),
                                  "--out", out, lantern)
            self.assertEqual(code, 0, text + err)
            shared = parse.parse_file(out)
            self.assertEqual(shared.zip, "../Base/Mod-0.1.0.zip")
            self.assertEqual(os.path.normpath(builds.tested_zip_from_plan(out, shared.zip)),
                             os.path.normpath(os.path.join(d, "Base", "Mod-0.1.0.zip")))


class CheapNits(unittest.TestCase):
    def test_style_skips_dates_in_a_fenced_log_sample(self):
        from test_style import GOOD, R, _codes, _run
        text = GOOD.replace("These checks prove it loads.\n",
                            "These checks prove it loads.\n\n```\n11/23/2026 12:00 LANTERN: started\n```\n")
        _, found = _run(R(iso_dates=True), text)
        self.assertEqual(_codes(found), [])

    def test_logs_names_ngplus_ids_when_they_are_the_only_ones(self):
        import json
        with tempfile.TemporaryDirectory() as d:
            plan = os.path.join(d, "Lantern.testplan.md")
            with open(plan, "w", encoding="utf-8", newline="\n") as f:
                f.write(LANTERN)
            rp = os.path.join(d, "report.json")
            with open(rp, "w", encoding="utf-8") as f:
                json.dump({"mods": [{"mod": "Lantern", "status": "LOADED", "rules": []}]}, f)
            code, text, err = run("logs", rp, "--plan", plan, "--out", os.path.join(d, "m.json"))
            self.assertEqual(code, 0, text + err)
            self.assertIn("Only the plan's New Game+ checks have log: ids", text)


if __name__ == "__main__":
    unittest.main()
