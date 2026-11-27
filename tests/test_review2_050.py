"""0.5.0 code review round 2 fixes: the quest example's scripts rule matches the quest's stack frames, a folder entry
written with a backslash is not compared as a file, and a pin keyed by the path the report prints still works."""
import json
import os
import re
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import builds  # noqa: E402

RULES = os.path.join(ROOT, "examples", "QuestExample.logrules.json")


class QuestScriptsRuleTest(unittest.TestCase):
    def test_scripts_rule_matches_frames_and_messages(self):
        # papyrus-log-check searches the error message and each stack frame with this pattern (case-insensitive)
        with open(RULES, encoding="utf-8") as f:
            rx = re.compile(json.load(f)["scripts"], re.I)
        frame = '[TWE_Quest (0100080A)].TWE:QuestScript.OnStageSet() - "TWE:QuestScript.psc" Line 12'
        self.assertTrue(rx.search(frame))
        self.assertTrue(rx.search("Cannot call Delete() on a None object, aborting function call in TWE:QuestScript"))
        self.assertFalse(rx.search("[SQ_Main (0001F1A3)].SQ_MainScript.OnInit() - \"SQ_MainScript.psc\" Line 3"))


class ZipTest(unittest.TestCase):
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

    def test_backslash_folder_entry_is_skipped(self):
        # zipfile turns a backslash into '/' only on Windows; set the stored name by hand so this runs anywhere
        info = zipfile.ZipInfo("Data/x")
        info.filename = "Data\\"
        plugin = zipfile.ZipInfo("Data/Demo.esm")

        class FakeZip:
            def infolist(self):
                return [info, plugin]

        # On Windows ZipInfo.is_dir also accepts a backslash (through os.path.altsep); act like Linux, where it doesn't
        with mock.patch.object(os.path, "altsep", None):
            self.assertEqual(sorted(builds.zip_entries(FakeZip(), True)), ["data/demo.esm"])

    def test_pin_key_with_folder_works(self):
        a = self.zip("a.zip", {"Data/Demo.esm": b"plugin", "Data/SFSE/Plugins/Demo.dll": b"dll one"})
        b = self.zip("b.zip", {"Data/Demo.esm": b"plugin", "Data/SFSE/Plugins/Demo.dll": b"dll two"})
        (e,) = [e for e in builds.compare(a, b)["entries"] if e["status"] == "differs"]
        sa, sb = e["detail"].split("sha256 ")[1].split(",")[0], e["detail"].rsplit("has ", 1)[1]
        pins = os.path.join(self.d, "pins.json")
        with open(pins, "w", encoding="utf-8") as f:
            json.dump({"format": "sf-test-plan-pins/1",
                       "pins": {"Data/SFSE/Plugins/Demo.dll": {"tested": sa, "built": sb, "why": "rebuilt"}}}, f)
        r = builds.compare(a, b, builds.load_pins(pins))
        self.assertTrue(r["same"], r)


if __name__ == "__main__":
    unittest.main()
