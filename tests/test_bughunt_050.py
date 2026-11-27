"""0.5.0 bug hunt fixes: a DLL beside a plugin can be pinned by its file name, the --pins error's sample is valid
JSON, and the README and AGENTS.md name the current version (download zip and the --verbose sample)."""
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

from sftestplan import builds, cli  # noqa: E402
from sftestplan.model import VERSION  # noqa: E402


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def read(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return f.read()


class PinsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def zip(self, name, files):
        p = os.path.join(self.d, name)
        with zipfile.ZipFile(p, "w") as z:
            for n, data in files.items():
                z.writestr(n, data)
        return p

    def test_dll_beside_plugin_pinned_by_file_name(self):
        a = self.zip("a.zip", {"Data/Demo.esm": b"plugin", "Data/SFSE/Plugins/Demo.dll": b"dll one"})
        b = self.zip("b.zip", {"Data/Demo.esm": b"plugin", "Data/SFSE/Plugins/Demo.dll": b"dll two"})
        r = builds.compare(a, b)
        self.assertFalse(r["same"])
        (e,) = [e for e in r["entries"] if e["status"] == "differs"]
        sa, sb = e["detail"].split("sha256 ")[1].split(",")[0], e["detail"].rsplit("has ", 1)[1]
        pins = os.path.join(self.d, "pins.json")
        with open(pins, "w", encoding="utf-8") as f:
            json.dump({"format": "sf-test-plan-pins/1",
                       "pins": {"demo.dll": {"tested": sa, "built": sb, "why": "rebuilt"}}}, f)
        code, out, _ = run("compare-builds", a, b, "--pins", pins)
        self.assertEqual(code, 0, out)
        self.assertIn("Data/SFSE/Plugins/Demo.dll: pinned: rebuilt", out)

    def test_pins_error_sample_is_valid_json(self):
        bad = os.path.join(self.d, "bad.json")
        with open(bad, "w", encoding="utf-8") as f:
            f.write("{bad")
        with self.assertRaises(builds.SetupError) as cm:
            builds.load_pins(bad)
        sample = str(cm.exception).split("Give a JSON file like ", 1)[1].rstrip(".")
        self.assertEqual(json.loads(sample)["format"], "sf-test-plan-pins/1")


class DocsVersionTest(unittest.TestCase):
    def test_download_names_current_version(self):
        for name in ("README.md", "AGENTS.md"):
            text = read(name)
            self.assertIn(f"sf-test-plan-{VERSION}.zip", text, name)
            self.assertNotIn("sf-test-plan-0.4.1.zip", text, name)

    def test_readme_verbose_sample_matches(self):
        text = read("README.md")
        self.assertIn(f"[verbose] sf-test-plan {VERSION}, Python", text)
        n = len(read(os.path.join("examples", "Beacon.testplan.md")))
        self.assertIn(f"read plan examples\\Beacon.testplan.md ({n} characters)", text)


if __name__ == "__main__":
    unittest.main()
