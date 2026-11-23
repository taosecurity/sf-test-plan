"""0.3.1: a file path a console can't show must not crash any command (NOTES "0.3.0 last review: left for later").

Each command runs as a subprocess whose stdout and stderr are cp1252 or ASCII (PYTHONIOENCODING), on a folder whose
name holds a character cp1252 can't show and, on Linux, bytes that aren't valid UTF-8 (surrogate escapes). With
--log, the log file must take the same paths without a logging error.
"""
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "sf_test_plan.py")
EXAMPLE = os.path.join(ROOT, "examples", "Beacon.testplan.md")
REPORT = os.path.join(ROOT, "tests", "fixtures", "logcheck-beacon.json")

SNOWMAN = "plan-☃"                       # not in cp1252
# On Linux, the name Python gives a file whose bytes aren't UTF-8; Windows takes the same lone surrogates as a name.
UNDECODABLE = "plan-\udcff\udcfe"


def _can_make(name):
    """Some file systems (macOS) refuse names that aren't valid Unicode."""
    with tempfile.TemporaryDirectory() as top:
        try:
            os.mkdir(os.path.join(top, name))
            return True
        except (OSError, UnicodeError):
            return False


class PathOutput(unittest.TestCase):
    def _run(self, encoding, *argv, log=None):
        env = dict(os.environ, PYTHONIOENCODING=encoding)
        cmd = [sys.executable, "-I", ENTRY, *argv]
        if log:
            cmd += ["--log", log]
        p = subprocess.run(cmd, capture_output=True, env=env)
        return p.returncode, p.stdout, p.stderr

    def _every_command(self, folder_name, encoding):
        with tempfile.TemporaryDirectory() as top:
            d = os.path.join(top, folder_name)
            os.mkdir(d)
            plan = os.path.join(d, "Beacon.testplan.md")
            shutil.copyfile(EXAMPLE, plan)
            report = os.path.join(d, "report.json")
            shutil.copyfile(REPORT, report)
            log = os.path.join(d, "run.log")
            marks = os.path.join(d, "report.marks.json")
            runs = [
                ("check", 0, ["check", plan]),
                ("build", 0, ["build", plan]),
                ("rules", 0, ["rules", plan, "--out", os.path.join(d, "r.json")]),
                ("logs", 0, ["logs", report, "--plan", plan]),
                ("import", 0, ["import", marks, "--plan", plan]),
                ("new", 0, ["new", os.path.join(d, "New.testplan.md")]),
                ("missing plan", 2, ["check", os.path.join(d, "missing.md")]),
                ("existing new", 2, ["new", plan]),
            ]
            for name, want, argv in runs:
                with self.subTest(command=name, encoding=encoding):
                    code, out, err = self._run(encoding, *argv, log=log)
                    text = (out + err).decode("utf-8", "replace")
                    self.assertEqual(code, want, text)
                    self.assertNotIn("Traceback", text)
                    self.assertNotIn("unexpected error", text)
                    self.assertNotIn("Logging error", text)
                    self.assertIn("plan-", text)          # the path was printed, with what the stream couldn't show replaced
            self.assertTrue(os.path.exists(os.path.join(d, "Beacon.testplan.html")))
            self.assertTrue(os.path.exists(marks))
            with open(log, encoding="utf-8") as f:                # the log is valid UTF-8 and names the path
                logged = f.read()
            self.assertIn("\\udcff\\udcfe" if folder_name == UNDECODABLE else folder_name, logged)

    def test_unshowable_character_cp1252(self):
        self._every_command(SNOWMAN, "cp1252")

    def test_unshowable_character_ascii(self):
        self._every_command(SNOWMAN, "ascii")

    @unittest.skipIf(not _can_make(UNDECODABLE), "this file system refuses the name")
    def test_undecodable_bytes_ascii(self):
        self._every_command(UNDECODABLE, "ascii")

    @unittest.skipIf(not _can_make(UNDECODABLE), "this file system refuses the name")
    def test_undecodable_bytes_utf8(self):
        self._every_command(UNDECODABLE, "utf-8")


if __name__ == "__main__":
    unittest.main()
