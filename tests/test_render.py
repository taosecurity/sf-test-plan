"""0.4.0: the render command, --fragment, --assets, and quoted paths in printed commands (FORMAT.md section 2)."""
import io
import json
import os
import re
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse, render  # noqa: E402

PLAN = """# Lantern test plan
run: lantern-0.1.0
mod: Lantern
version: 0.1.0

This plan tests a made-up lantern mod.

## Before you start
- Back up your saves.

## 1 Load
- [ ] Start a new game.
  Expect: no error.
  smoke: yes
- [ ] Open the inventory.
  logcheck: the log says LANTERN: ready.

## Log checks
- [ ] The script started once.
  Expect: one LANTERN: start line.
"""


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


def config_of(html):
    m = re.search(r'<script type="application/json" id="tp-config">(.*?)</script>', html, re.S)
    return json.loads(m.group(1))


class FragmentTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.plan = os.path.join(self.dir, "Lantern.testplan.md")
        with open(self.plan, "w", encoding="utf-8") as f:
            f.write(PLAN)

    def tearDown(self):
        self.tmp.cleanup()

    def fragment(self):
        return render.render(parse.parse_file(self.plan), fragment=True)

    def test_fragment_has_no_style_inline_script_h1_or_footer(self):
        h = self.fragment()
        self.assertTrue(h.startswith('<div class="sf-test-plan" data-run="lantern-0.1.0">'))
        self.assertTrue(h.rstrip().endswith("</div>"))
        for bad in ("<style", "<h1", "<footer", "<html", "<head", "<body", "<script>"):
            self.assertNotIn(bad, h, bad)
        # every script element is a JSON data block
        self.assertEqual(re.findall(r"<script(?![^>]*application/json)", h), [])

    def test_fragment_has_the_parts_a_host_needs(self):
        h = self.fragment()
        for part in ('class="tp-intro"', 'id="tally"', 'id="tools"', 'id="saved"', 'id="importfile"', 'id="prep"',
                     'id="smoke"', 'id="deep"', 'id="log-checks"', 'id="tp-config"', 'id="tp-logchecks"',
                     "This plan tests a made-up lantern mod."):
            self.assertIn(part, h, part)

    def test_same_config_as_the_full_page(self):
        full = render.render(parse.parse_file(self.plan))
        self.assertEqual(config_of(self.fragment()), config_of(full))

    def test_render_without_fragment_is_the_build_page(self):
        page = os.path.join(self.dir, "b.html")
        self.assertEqual(run("build", self.plan, "--out", page)[0], 0)
        out = os.path.join(self.dir, "r.html")
        code, stdout, _ = run("render", self.plan, "--out", out)
        self.assertEqual(code, 0)
        self.assertIn("Page: ", stdout)
        with open(page, encoding="utf-8") as a, open(out, encoding="utf-8") as b:
            self.assertEqual(a.read(), b.read())

    def test_stdout_gets_only_the_html(self):
        code, stdout, stderr = run("render", self.plan, "--fragment")
        self.assertEqual(code, 0)
        self.assertTrue(stdout.startswith('<div class="sf-test-plan"'))
        self.assertIn("0 errors", stderr)

    def test_plan_errors_write_nothing(self):
        with open(self.plan, "w", encoding="utf-8") as f:
            f.write("# Bad\n\n## 1 Load\n- [ ] A step.\n")      # no run:
        out = os.path.join(self.dir, "f.html")
        code, _, _ = run("render", self.plan, "--fragment", "--out", out, "--assets", self.dir)
        self.assertEqual(code, 1)
        self.assertFalse(os.path.exists(out))
        self.assertFalse(os.path.exists(os.path.join(self.dir, "sf-test-plan.js")))

    def test_out_refusals_as_build(self):
        code, _, err = run("render", self.plan, "--out", self.plan)
        self.assertEqual(code, 2)
        self.assertIn("is the plan itself", err)
        code, _, err = run("render", self.plan, "--out", self.dir)
        self.assertEqual(code, 2)
        self.assertIn("is a folder", err)


class AssetsTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = self.tmp.name
        self.plan = os.path.join(self.dir, "Lantern.testplan.md")
        with open(self.plan, "w", encoding="utf-8") as f:
            f.write(PLAN)
        self.assets = os.path.join(self.dir, "assets out")

    def tearDown(self):
        self.tmp.cleanup()

    def render_assets(self, *extra):
        return run("render", self.plan, "--fragment", "--out", os.path.join(self.dir, "f.html"),
                   "--assets", self.assets, *extra)

    def read(self, name):
        with open(os.path.join(self.assets, name), "rb") as f:
            return f.read()

    def test_assets_are_the_exact_bytes(self):
        code, out, _ = self.render_assets()
        self.assertEqual(code, 0, out)
        with open(os.path.join(ROOT, "assets", "page.js"), "rb") as f:
            self.assertEqual(self.read("sf-test-plan.js"), f.read())
        with open(os.path.join(ROOT, "assets", "page.css"), "rb") as f:
            self.assertEqual(self.read("sf-test-plan.css"), f.read())

    def test_same_bytes_are_left_alone(self):
        self.render_assets()
        code, out, _ = self.render_assets()
        self.assertEqual(code, 0)
        self.assertEqual(out.count("Unchanged: "), 3)

    def test_other_bytes_need_force(self):
        self.render_assets()
        js = os.path.join(self.assets, "sf-test-plan.js")
        with open(js, "wb") as f:
            f.write(b"// the host's own edit\n")
        os.remove(os.path.join(self.dir, "f.html"))
        code, _, err = self.render_assets()
        self.assertEqual(code, 2)
        self.assertIn("--force", err)
        self.assertEqual(self.read("sf-test-plan.js"), b"// the host's own edit\n")
        self.assertFalse(os.path.exists(os.path.join(self.dir, "f.html")))     # refused before anything was written
        code, _, _ = self.render_assets("--force")
        self.assertEqual(code, 0)
        self.assertNotEqual(self.read("sf-test-plan.js"), b"// the host's own edit\n")

    def test_assets_that_is_a_file_is_refused(self):
        with open(self.assets, "w") as f:
            f.write("x")
        code, _, err = self.render_assets()
        self.assertEqual(code, 2)
        self.assertIn("isn't a folder", err)

    def test_read_only_asset_is_refused(self):
        self.render_assets()
        css = os.path.join(self.assets, "sf-test-plan.css")
        with open(css, "wb") as f:
            f.write(b"/* other */")
        os.chmod(css, 0o444)
        try:
            code, _, err = self.render_assets("--force")
            self.assertEqual(code, 2)
            self.assertIn("read-only", err)
        finally:
            os.chmod(css, 0o666)


class QuotedPathTests(unittest.TestCase):
    def test_quote_rules(self):
        self.assertEqual(cli._q("plans/Lantern.testplan.md"), "plans/Lantern.testplan.md")
        self.assertEqual(cli._q(r"C:\plans\Lantern.testplan.md", windows=True), r"C:\plans\Lantern.testplan.md")
        self.assertEqual(cli._q(r"C:\My Plans\L.md", windows=True), '"C:\\My Plans\\L.md"')
        self.assertEqual(cli._q("my plans/L.md", windows=False), "'my plans/L.md'")
        self.assertEqual(cli._q("a&b.md", windows=True), '"a&b.md"')
        self.assertEqual(cli._q("it's.md", windows=False), "'it'\"'\"'s.md'")

    def test_new_and_rules_print_quoted_paths(self):
        with tempfile.TemporaryDirectory() as d:
            folder = os.path.join(d, "my plans")
            os.mkdir(folder)
            plan = os.path.join(folder, "Lantern.testplan.md")
            code, out, _ = run("new", plan)
            self.assertEqual(code, 0)
            self.assertIn(f"then run: sf-test-plan build {cli._q(plan)}", out)
            self.assertNotEqual(cli._q(plan), plan)
            with open(plan, "w", encoding="utf-8") as f:
                f.write("# L\nrun: l-1\nmod: Lantern\n\n## 1 Load\n- [ ] Load.\n  log: lantern-ready\n")
            code, out, _ = run("rules", plan)
            self.assertEqual(code, 0, out)
            rules_out = os.path.join(folder, "Lantern.logrules.json")
            self.assertIn(f"Then run: sf-test-plan check {cli._q(plan)} --rules {cli._q(rules_out)}", out)


if __name__ == "__main__":
    unittest.main()
