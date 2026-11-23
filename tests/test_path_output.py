"""0.3.1: a file path a console can't show must not crash any command (NOTES "0.3.0 last review: left for later").

Each command runs as a subprocess asked for cp1252 or ASCII output (PYTHONIOENCODING), on a folder whose name holds
a character cp1252 can't show and, on Linux, bytes that aren't valid UTF-8 (surrogate escapes). The tool switches its
own output to UTF-8 (cli._utf8_output), so the output must decode as UTF-8 and show the path, with each character
that isn't valid Unicode as '?'. With --log, the log file must take the same paths without a logging error. A second
set of runs puts the same characters in the plan's own file name (code review of 0.3.1): `new` and `rules` take the
mod name from it.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENTRY = os.path.join(ROOT, "sf_test_plan.py")
EXAMPLE = os.path.join(ROOT, "examples", "Beacon.testplan.md")
REPORT = os.path.join(ROOT, "tests", "fixtures", "logcheck-beacon.json")
sys.path.insert(0, ROOT)            # as the other test modules do

from sftestplan import cli  # noqa: E402

SNOWMAN = "plan-☃"                       # not in cp1252
# On Linux, the name Python gives a file whose bytes aren't UTF-8; Windows takes the same lone surrogates as a name.
UNDECODABLE = "plan-\udcff\udcfe"


def _shown(name):
    """How the tool prints a name: UTF-8, with each lone surrogate as '?'."""
    return name.encode("utf-8", "replace").decode("utf-8")


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
                    text = (out + err).decode("utf-8")    # strict: the output is UTF-8 whatever was asked for
                    self.assertEqual(code, want, text)
                    self.assertNotIn("Traceback", text)
                    self.assertNotIn("unexpected error", text)
                    self.assertNotIn("Logging error", text)
                    self.assertIn(_shown(folder_name), text)   # the path was printed, '?' for what isn't Unicode
            self.assertTrue(os.path.exists(os.path.join(d, "Beacon.testplan.html")))
            self.assertTrue(os.path.exists(marks))
            with open(log, encoding="utf-8") as f:                # the log is valid UTF-8 and names the path
                logged = f.read()
            self.assertIn("\\udcff\\udcfe" if folder_name == UNDECODABLE else folder_name, logged)

    def _plan_named(self, stem):
        """`new` and `rules` on a plan whose own file name holds stem; the mod name comes from that name."""
        with tempfile.TemporaryDirectory() as top:
            new_plan = os.path.join(top, stem + ".testplan.md")
            code, out, err = self._run("ascii", "new", new_plan)
            text = (out + err).decode("utf-8")
            self.assertEqual(code, 0, text)
            self.assertNotIn("unexpected error", text)
            with open(new_plan, encoding="utf-8") as f:            # written in full, as valid UTF-8
                first = f.readline()
            self.assertEqual(first, f"# {_shown(stem).replace('?', '')} test plan\n")

            plan = os.path.join(top, stem + "-nomod.testplan.md")  # no mod: line, so rules uses the file name too
            with open(EXAMPLE, encoding="utf-8") as f:
                body = "".join(line for line in f if not line.startswith("mod:"))
            with open(plan, "w", encoding="utf-8") as f:
                f.write(body)
            out_file = os.path.join(top, "r.json")
            code, out, err = self._run("ascii", "rules", plan, "--out", out_file)
            text = (out + err).decode("utf-8")
            self.assertEqual(code, 0, text)
            self.assertIn(f"Rule file: {_shown(out_file)}.", text)
            with open(out_file, encoding="utf-8") as f:
                data = json.load(f)
            self.assertEqual(data["mod"], _shown(stem).replace("?", "") + "-nomod")

    def test_mod_from_path(self):
        """No file system needed, so this also runs where the OS refuses such names (macOS)."""
        self.assertEqual(cli._mod_from_path(os.path.join("x", "Beacon.testplan.md")), "Beacon")
        self.assertEqual(cli._mod_from_path("plan-\udcff\udcfe-nomod.testplan.md"), "plan--nomod")
        self.assertEqual(cli._mod_from_path("\udcff\udcfe.testplan.md"), "My Mod")   # nothing left: the default
        self.assertEqual(cli._mod_from_path(SNOWMAN + ".md"), SNOWMAN)
        self.assertEqual(cli._mod_from_path("\udcff \udcfe.testplan.md"), "My Mod")   # only a space left (round 3)
        self.assertEqual(cli._mod_from_path(".testplan.md"), "My Mod")

    @unittest.skipIf(not _can_make("\udcff\udcfe"), "this file system refuses the name")
    def test_rules_name_all_undecodable_gets_default_mod(self):
        """Code review round 2 of 0.3.1: a name with nothing valid left wrote "mod": "" into the rule file."""
        with tempfile.TemporaryDirectory() as top:
            plan = os.path.join(top, "\udcff\udcfe.testplan.md")
            with open(EXAMPLE, encoding="utf-8") as f:
                body = "".join(line for line in f if not line.startswith("mod:"))
            with open(plan, "w", encoding="utf-8") as f:
                f.write(body)
            out_file = os.path.join(top, "r.json")
            code, out, err = self._run("utf-8", "rules", plan, "--out", out_file)
            self.assertEqual(code, 0, (out + err).decode("utf-8"))
            with open(out_file, encoding="utf-8") as f:
                self.assertEqual(json.load(f)["mod"], "My Mod")

    def test_plan_file_name_unshowable(self):
        self._plan_named(SNOWMAN)

    @unittest.skipIf(not _can_make(UNDECODABLE), "this file system refuses the name")
    def test_plan_file_name_undecodable(self):
        self._plan_named(UNDECODABLE)

    def test_new_mod_not_unicode_is_refused_before_writing(self):
        with tempfile.TemporaryDirectory() as top:
            plan = os.path.join(top, "Keep.testplan.md")
            with open(plan, "w", encoding="utf-8") as f:
                f.write("old text")
            err = io.StringIO()
            with redirect_stdout(io.StringIO()), redirect_stderr(err):
                code = cli.main(["new", plan, "--force", "--mod", "Bad\udcffName"])
            self.assertEqual(code, 2)
            self.assertIn("--mod holds text that can't be saved as UTF-8", err.getvalue())
            with open(plan, encoding="utf-8") as f:
                self.assertEqual(f.read(), "old text")             # the existing plan wasn't emptied

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
