"""0.4.0 /code-review round 5 fixes: a style problem in a paragraph wrapped over short source lines names the right
line, and ngplus never writes its --out or --order over a plan's results file."""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sftestplan import results  # noqa: E402
from test_ngplus import BASE, LANTERN, run  # noqa: E402
from test_style import GOOD, R, _codes, _run  # noqa: E402


class WrappedParagraphLine(unittest.TestCase):
    def test_short_first_line_still_found(self):
        text = GOOD.replace("This plan tests Lantern 0.1.0, a made-up mod.\n",
                            "this plan tests\nLantern 0.1.0, a made-up mod.\n")
        _, found = _run(R(full_sentences=True), text)
        self.assertEqual(_codes(found), ["style-sentence"], found)
        self.assertEqual(found[0].line, 6)


class NgplusKeepsResultsFiles(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ng plus ")
        d = self.tmp.name
        self.base = os.path.join(d, "Base.testplan.md")
        self.lantern = os.path.join(d, "Lantern.testplan.md")
        for path, text in ((self.base, BASE), (self.lantern, LANTERN)):
            with open(path, "w", encoding="utf-8", newline="\n") as f:
                f.write(text)
        self.saved = results.results_path(self.lantern)
        with open(self.saved, "w", encoding="utf-8") as f:
            f.write("{}")

    def tearDown(self):
        self.tmp.cleanup()

    def test_out_is_a_results_file(self):
        code, text, err = run("ngplus", "--base", self.base, "--order", os.path.join(self.tmp.name, "o.json"),
                              "--out", self.saved, "--force", self.lantern)
        self.assertEqual(code, 2, text + err)
        self.assertIn("results file", text + err)
        with open(self.saved, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{}")

    def test_order_is_a_results_file(self):
        code, text, err = run("ngplus", "--base", self.base, "--order", self.saved,
                              "--out", os.path.join(self.tmp.name, "NG.testplan.md"), self.lantern)
        self.assertEqual(code, 2, text + err)
        with open(self.saved, encoding="utf-8") as f:
            self.assertEqual(f.read(), "{}")


if __name__ == "__main__":
    unittest.main()
