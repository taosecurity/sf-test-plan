"""0.4.0: the Log checks section, the logcheck: key, the tp-logchecks JSON and the log-lines table (FORMAT.md rules
12 and 13, sections 2 and 5)."""
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import cli, parse, render, results, rules  # noqa: E402
from test_build import tree  # noqa: E402

HEAD = "# Lantern test plan\nrun: lantern-0.1.0\nmod: Lantern\n\n"
PLAN = HEAD + """## 1 Load
- [ ] Start a new game.
  Expect: no error.
  smoke: yes
  logcheck: the line `LANTERN: ready` appears once.
- [ ] Open the settings.

## Log checks
These are read from the Papyrus log after play.

- [ ] The quest starts.
  Expect: `LANTERN: quest started` once.
  log: started
- [ ] No script errors from Lantern.
  log: no-errors, started
  note: Look for `Lantern` in the error lines.
- [ ] The old place number is kept.
  id: 7.3
"""


def codes(plan):
    return [p.code for p in plan.problems]


def run(*argv):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = cli.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class ParseTests(unittest.TestCase):
    def test_default_and_pinned_ids(self):
        p = parse.parse_text(PLAN)
        self.assertEqual(p.errors(), [])
        self.assertEqual([c.id for c in p.log_checks], ["L.1", "L.2", "7.3"])
        self.assertTrue(p.log_checks[2].pinned)
        self.assertEqual(p.log_checks[0].log, ["started"])
        self.assertEqual(p.log_checks[1].log, ["no-errors", "started"])
        self.assertIn("error lines", p.log_checks[1].note)
        self.assertEqual(p.log_intro, "These are read from the Papyrus log after play.")

    def test_log_checks_are_not_page_checks(self):
        p = parse.parse_text(PLAN)
        self.assertEqual([c.id for c in p.checks()], ["1.1", "1.2"])
        self.assertEqual(len(p.smoke()), 1)

    def test_pinned_L_id_and_heading_case(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n## LOG CHECKS\n- [ ] y\n  id: l.5\n- [ ] z\n")
        self.assertEqual([c.id for c in p.log_checks], ["L.5", "L.2"])

    def test_bad_log_id(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n## Log checks\n- [ ] y\n  id: Q.1\n")
        self.assertIn("bad-id", codes(p))

    def test_dup_id_with_a_page_check(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n## Log checks\n- [ ] y\n  id: 1.1\n")
        self.assertIn("dup-id", codes(p))

    def test_smoke_log_check_is_an_error(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n## Log checks\n- [ ] y\n  smoke: yes\n")
        self.assertIn("smoke-log-check", codes(p))
        self.assertEqual(p.errors()[0].line, 9)
        ok = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n## Log checks\n- [ ] y\n  smoke: no\n")
        self.assertEqual(ok.problems, [])

    def test_empty_section_is_empty_group(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n## Log checks\nNothing yet.\n")
        self.assertEqual(codes(p), ["empty-group"])
        self.assertEqual(p.problems[0].level, "warning")
        self.assertEqual(p.problems[0].line, 7)

    def test_only_log_checks_is_no_checks(self):
        p = parse.parse_text(HEAD + "## Log checks\n- [ ] y\n")
        self.assertIn("no-checks", codes(p))

    def test_logcheck_key_and_wrapping(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n  logcheck: the line\n  appears once.\n")
        self.assertEqual(p.problems, [])
        self.assertEqual(p.checks()[0].logcheck, "the line appears once.")

    def test_unknown_log_id_in_log_checks(self):
        p = parse.parse_text(PLAN, rule_ids={"started"})
        self.assertEqual(codes(p), ["unknown-log-id"])

    def test_orphan_logcheck(self):
        p = parse.parse_text(HEAD + "Intro.\n  logcheck: x\n## 1 A\n- [ ] x\n")
        self.assertIn("orphan-key", codes(p))


class PageTests(unittest.TestCase):
    def setUp(self):
        self.plan = parse.parse_text(PLAN)
        self.html = render.render(self.plan)
        self.t = tree(self.html)

    def test_table_and_no_controls(self):
        self.assertEqual(len(self.t.find("section", id="log-checks")), 1)
        rows = [a["data-id"] for t, a in self.t.tags if t == "tr" and "data-id" in a]
        self.assertEqual(rows, ["L.1", "L.2", "7.3"])
        lis = [a["data-id"] for a in self.t.find("li", **{"class": "check"})]
        self.assertEqual(lis, ["1.1", "1.2"])
        section = self.html[self.html.index('id="log-checks"'):]
        section = section[:section.index("</section>")]
        self.assertNotIn("<li", section)
        self.assertNotIn("<input", section)
        self.assertIn("Checks in the logs", section)
        self.assertIn("These are read from the Papyrus log after play.", section)
        self.assertIn('<a href="#log-checks">', self.html)

    def test_tally_leaves_log_checks_out(self):
        bar = self.t.find("div", id="tally")[0]
        self.assertEqual(bar["data-total"], "1")
        self.assertEqual(json.loads(self.t.scripts["tp-config"])["total"], 1)

    def test_logcheck_line(self):
        self.assertIn('<div class="bylog logcheck">Check in the log: the line <code>LANTERN: ready</code> appears '
                      'once.</div>', self.html)

    def test_logchecks_json_is_plain_text(self):
        items = json.loads(self.t.scripts["tp-logchecks"])
        self.assertEqual([(i["id"], i["kind"]) for i in items],
                         [("L.1", "log only"), ("L.2", "log only"), ("7.3", "log only"), ("1.1", "in-game")])
        self.assertEqual(items[0]["expect"], "LANTERN: quest started once.")
        self.assertEqual(items[1]["log"], ["no-errors", "started"])
        self.assertEqual(items[3]["what"], "the line LANTERN: ready appears once.")
        self.assertEqual(items[3]["step"], "Start a new game.")

    def test_logchecks_json_cannot_close_script(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n## Log checks\n- [ ] </script><script>alert(1)</script>\n")
        html = render.render(p)
        self.assertNotIn("<script>alert", html)
        self.assertEqual(json.loads(tree(html).scripts["tp-logchecks"])[0]["what"],
                         "</script><script>alert(1)</script>")

    def test_plan_without_log_checks(self):
        p = parse.parse_text(HEAD + "## 1 A\n- [ ] x\n")
        html = render.render(p)
        self.assertNotIn('id="log-checks"', html)
        self.assertEqual(json.loads(tree(html).scripts["tp-logchecks"]), [])

    def test_log_lines_table(self):
        rf = {"expect": [{"id": "started", "re": "LANTERN: quest <started>", "means": "The quest began."}],
              "forbid": [{"id": "no-errors", "re": "error.*Lantern", "means": "A script error."}, "junk"]}
        html = render.render(self.plan, None, rf)
        self.assertIn('id="log-lines"', html)
        self.assertIn("<td>started</td><td><code>LANTERN: quest &lt;started&gt;</code></td><td>Expected</td>"
                      "<td>The quest began.</td>", html)
        self.assertIn("<td>Must not appear</td>", html)
        self.assertIn('<a href="#log-lines">', html)
        self.assertNotIn('id="log-lines"', render.render(self.plan, None, {"expect": [], "forbid": []}))


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.TemporaryDirectory()
        self.plan = os.path.join(self.d.name, "Lantern.testplan.md")
        with open(self.plan, "w", encoding="utf-8") as f:
            f.write(PLAN)

    def tearDown(self):
        self.d.cleanup()

    def write_json(self, name, data):
        path = os.path.join(self.d.name, name)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return path

    def test_rules_names_log_check_ids(self):
        uses = rules.plan_log_uses(parse.parse_text(PLAN))
        self.assertEqual(list(uses), ["started", "no-errors"])
        self.assertEqual([cid for cid, _ in uses["started"]], ["L.1", "L.2"])

    def test_build_with_rules_adds_log_lines(self):
        rf = self.write_json("rules.json", {"expect": [{"id": "started", "re": "LANTERN: started", "means": "M."},
                                                       {"id": "no-errors", "re": "x", "means": "N."}], "forbid": []})
        out = os.path.join(self.d.name, "page.html")
        code, text, err = run("build", self.plan, "--rules", rf, "--out", out)
        self.assertEqual(code, 0, text + err)
        with open(out, encoding="utf-8") as f:
            html = f.read()
        self.assertIn('id="log-lines"', html)
        self.assertIn('id="log-checks"', html)

    def test_logs_prints_lines_and_writes_no_mark(self):
        report = {"mods": [{"mod": "Lantern", "status": "LOADED", "rules": [
            {"kind": "expect", "id": "started", "status": "PASS"},
            {"kind": "forbid", "id": "no-errors", "status": "FAIL"}]}]}
        rp = self.write_json("report.json", report)
        out = os.path.join(self.d.name, "marks.json")
        code, text, err = run("logs", rp, "--plan", self.plan, "--out", out)
        self.assertEqual(code, 0, text + err)
        self.assertIn("L.1 log check PASS: started PASS.", text)
        self.assertIn("L.2 log check FAIL: no-errors FAIL; started PASS.", text)
        self.assertNotIn("7.3", text)   # no log: ids, so nothing to say
        with open(out, encoding="utf-8") as f:
            marks = json.load(f)
        self.assertEqual(marks["checks"], [])

    def test_logs_not_seen(self):
        report = {"mods": [{"mod": "Lantern", "status": "LOADED", "rules": [
            {"kind": "expect", "id": "started", "status": "NOT SEEN"}]}]}
        rp = self.write_json("report.json", report)
        code, text, _ = run("logs", rp, "--plan", self.plan, "--out", os.path.join(self.d.name, "m.json"))
        self.assertEqual(code, 0)
        self.assertIn("L.1 log check NOT SEEN: started NOT SEEN.", text)
        self.assertIn("L.2 log check NOT SEEN: no-errors isn't in the report; started NOT SEEN.", text)

    def test_marks_for_log_ids_stay_out_of_the_summary(self):
        p = parse.parse_text(PLAN)
        marks = {"run": "lantern-0.1.0", "checks": [{"id": "L.1", "r": "fail", "n": "", "at": ""},
                                                    {"id": "1.1", "r": "pass", "n": "", "at": ""}]}
        row = results.summarize(p, marks, "2026-11-23")
        self.assertEqual(row["happened"], "1 pass, 0 fail, 0 skip, 0 not run")


if __name__ == "__main__":
    unittest.main()
