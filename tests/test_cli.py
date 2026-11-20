"""C0 smoke tests: the CLI dispatches, options parse, and errors give exit 2 with a plain message."""
import io
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, model  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "Beacon.testplan.md")


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class CliTests(unittest.TestCase):
    def test_version(self):
        code, out, _ = run("--version")
        self.assertEqual(code, 0)
        self.assertIn(model.VERSION, out)

    def test_no_command_is_exit_2(self):
        code, _, _ = run()
        self.assertEqual(code, 2)

    def test_unknown_option_is_exit_2(self):
        code, _, _ = run("check", EXAMPLE, "--nope")
        self.assertEqual(code, 2)

    def test_new_refuses_existing_file(self):
        code, _, err = run("new", EXAMPLE)
        self.assertEqual(code, 2)
        self.assertIn("already exists", err)

    def test_log_file_bad_folder_is_exit_2(self):
        code, _, err = run("check", EXAMPLE, "--log", os.path.join(ROOT, "no-such-folder", "x.log"))
        self.assertEqual(code, 2)
        self.assertIn("can't write the log file", err)

    def test_command_pattern(self):
        for s in ("player.additem 0001A2B3 1", "setstage MQ101 10", "set MyGlobal to 1", ".\\Tool.exe --x"):
            self.assertTrue(model.COMMAND_RE.match(s), s)
        for s in ("Papyrus.0.log", "BeaconMod.esm", "player"):
            self.assertFalse(model.COMMAND_RE.match(s), s)

    def test_problem_format(self):
        p = model.Problem("error", "no-run", 3, "add a run: line")
        self.assertEqual(p.format("a.md"), "a.md:3: error no-run: add a run: line")

    def test_log_file_written(self):
        with tempfile.TemporaryDirectory() as d:
            lf = os.path.join(d, "t.log")
            run("check", EXAMPLE, "--log", lf)
            with open(lf, encoding="utf-8") as f:
                self.assertIn(model.TOOL_ID, f.read())


if __name__ == "__main__":
    unittest.main()
