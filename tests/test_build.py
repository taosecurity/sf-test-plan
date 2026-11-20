"""C1: inline Markdown and the page writer (FORMAT.md rule 9 and section 2)."""
import json
import os
import re
import sys
import unittest
from html.parser import HTMLParser

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from sftestplan import model, parse, render  # noqa: E402

EXAMPLE = os.path.join(ROOT, "examples", "Beacon.testplan.md")
HEAD = "# T\nrun: r-1\n\n"


class Tree(HTMLParser):
    """Collects start tags with their attributes, and the text of script elements by id."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.scripts = {}
        self._script = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        self.tags.append((tag, a))
        if tag == "script":
            self._script = a.get("id", "")
            self.scripts.setdefault(self._script, "")

    def handle_endtag(self, tag):
        if tag == "script":
            self._script = None

    def handle_data(self, data):
        if self._script is not None:
            self.scripts[self._script] += data

    def find(self, tag=None, **want):
        out = []
        for t, a in self.tags:
            if tag and t != tag:
                continue
            if all(a.get(k.replace("_", "-")) == v for k, v in want.items()):
                out.append(a)
        return out


def tree(html):
    t = Tree()
    t.feed(html)
    return t


class InlineTests(unittest.TestCase):
    def test_escapes_html(self):
        self.assertEqual(render.inline("<script>alert(1)</script> & co"),
                         "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co")
        self.assertEqual(render.inline('"quoted" \'x\''), "&quot;quoted&quot; &#x27;x&#x27;")

    def test_bold_italic_code(self):
        self.assertEqual(render.inline("**b** and *i*"), "<strong>b</strong> and <em>i</em>")
        self.assertEqual(render.inline("`a **not bold** <b>`"), "<code>a **not bold** &lt;b&gt;</code>")
        self.assertEqual(render.inline("2 * 3 * 4"), "2 * 3 * 4")

    def test_links(self):
        self.assertEqual(render.inline("[page](https://example.com/a?x=1&y=2)"),
                         '<a href="https://example.com/a?x=1&amp;y=2" rel="noopener">page</a>')
        self.assertEqual(render.inline("[**b**](http://e.com)"), '<a href="http://e.com" rel="noopener"><strong>b</strong></a>')

    def test_unsafe_links_stay_text(self):
        for md in ("[x](javascript:alert(1))", "[x](JavaScript:alert(1))", "[x](data:text/html,hi)",
                   "[x](vbscript:msgbox)", "[x](//evil.com)", "[x](https://e.com\" onclick=\"a)"):
            h = render.inline(md)
            self.assertNotIn("<a", h, md)
        h = render.inline('[x](https://e.com/"onmouseover="alert(1))')
        self.assertNotIn('"onmouseover', h)

    def test_injection_in_code_and_link_text(self):
        h = render.inline("`</code><script>x</script>` [<img src=x onerror=a>](https://e.com)")
        self.assertNotIn("<script", h)
        self.assertNotIn("<img", h)
        self.assertIn("&lt;img src=x onerror=a&gt;", h)

    def test_nul_cannot_forge_slots(self):
        h = render.inline("\x000\x00 `x`")
        self.assertNotIn("\x00", h)
        self.assertEqual(h.count("<code"), 1)

    def test_command_spans(self):
        self.assertEqual(render.inline("type `player.additem 0001A2B3 1`"),
                         'type <code class="cmd">player.additem 0001A2B3 1</code>')
        self.assertEqual(render.inline("`Papyrus.0.log`"), "<code>Papyrus.0.log</code>")


class PageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = parse.parse_file(EXAMPLE)
        cls.html = render.render(cls.plan, [
            {"date": "2026-11-19", "run": "beacon-0.1.0", "test": "Smoke test", "happened": "5 pass",
             "notes": "<b>all</b> good"}])
        cls.t = tree(cls.html)

    def test_document_shell(self):
        h = self.html
        self.assertTrue(h.startswith("<!doctype html>"))
        self.assertIn('<meta charset="utf-8">', h)
        self.assertIn('name="viewport"', h)
        self.assertIn("<title>Beacon Mod test plan</title>", h)
        self.assertIn("<style>", h)
        self.assertIn("prefers-color-scheme", h)

    def test_no_network_loads(self):
        for tag, a in self.t.tags:
            for k in ("src", "href"):
                v = a.get(k) or ""
                if tag == "a":
                    continue
                self.assertFalse(re.match(r"(?i)(https?:)?//", v), (tag, a))
        self.assertNotIn("@import", self.html)
        self.assertNotIn("fonts.googleapis", self.html)
        self.assertEqual(self.t.find("link"), [])

    def test_config_json(self):
        cfg = json.loads(self.t.scripts["tp-config"])
        self.assertEqual(cfg["format"], model.PAGE_FORMAT)
        self.assertEqual(cfg["run"], "beacon-0.1.0")
        self.assertEqual(cfg["title"], "Beacon Mod test plan")
        self.assertEqual(cfg["tool"], model.TOOL_ID)

    def test_config_json_cannot_close_script(self):
        plan = parse.parse_text("# </script><script>alert(1)</script> <!-- x\nrun: a\n## 1 G\n- [ ] x\n")
        plan.title = "</script><script>alert(1)</script><!--"
        html = render.render(plan)
        t = tree(html)
        self.assertEqual(json.loads(t.scripts["tp-config"])["title"], plan.title)
        self.assertEqual(len(t.find("script")), 2)
        self.assertNotIn("<script>alert", html)

    def test_checks_and_attributes(self):
        lis = self.t.find("li", **{"class": "check"})
        self.assertEqual(len(lis), 6)
        first = lis[0]
        self.assertEqual((first["data-id"], first["data-group"], first["data-smoke"], first["data-log"]),
                         ("1.1", "1", "1", "loaded"))
        deep = [a for a in lis if a["data-smoke"] == "0"]
        self.assertEqual([a["data-id"] for a in deep], ["2.3"])
        self.assertIn('<div class="hint">Try it in a building too;', self.html)
        self.assertIn('<code class="cmd">player.additem 0001A2B3 1</code>', self.html)

    def test_smoke_and_deep(self):
        h = self.html
        self.assertIn('<section class="smoke" id="smoke"', h)
        self.assertIn('<details class="deep" id="deep">', h)
        smoke = h[h.index('id="smoke"'):h.index('id="deep"')]
        self.assertEqual(re.findall(r'data-id="([\d.]+)"', smoke), ["1.1", "1.2", "2.1", "2.2", "3.1"])
        self.assertIn("From group 2: Main feature", smoke)
        deep = h[h.index('id="deep"'):h.index("</details>")]
        self.assertIn('<section class="group" id="g2"', deep)
        self.assertNotIn('id="g1"', deep)  # every check of group 1 is in the smoke test
        tally = self.t.find(id="tally")[0]
        self.assertEqual((tally["class"], tally["data-total"]), ("bar", "5"))

    def test_toolbar_and_status(self):
        self.assertEqual(len(self.t.find("span", id="saved", **{"class": "saved"})), 1)
        self.assertEqual(self.t.find("div", id="tools")[0]["class"], "tools")
        acts = [a["data-act"] for a in self.t.find("button") if "data-act" in a]
        self.assertEqual(acts, ["export", "import", "copy", "reset"])
        inp = self.t.find("input", id="importfile")[0]
        self.assertEqual((inp["type"], inp["accept"]), ("file", ".json,application/json"))
        self.assertIn("hidden", inp)

    def test_facts_setup_results_footer(self):
        h = self.html
        for v in ("Beacon Mod", "0.1.0", "BeaconMod-0.1.0.zip", "beacon-0.1.0"):
            self.assertIn(f"<dd>{v}</dd>", h)
        self.assertIn('<section class="prep" id="prep">', h)
        self.assertEqual(h.count("<li>", h.index('id="prep"'), h.index('id="smoke"')), 2)
        self.assertIn('id="results"', h)
        self.assertIn("&lt;b&gt;all&lt;/b&gt; good", h)
        self.assertIn(model.URL, h)
        self.assertIn(model.TOOL_ID, h)
        self.assertIn("made-up example mod", h)

    def test_no_smoke_uses_group_sections(self):
        plan = parse.parse_text(HEAD + "Intro *x*.\n\n## 1 A\nGroup intro.\n- [ ] a\n## 2 B\n- [ ] b\n- [ ] c\n")
        html = render.render(plan)
        t = tree(html)
        self.assertNotIn('id="smoke"', html)
        self.assertNotIn('id="deep"', html)
        self.assertEqual([a["id"] for a in t.find("section", **{"class": "group"})], ["g1", "g2"])
        self.assertEqual(t.find(id="tally")[0]["data-total"], "3")
        self.assertNotIn('id="results"', html)
        self.assertIn("<p>Intro <em>x</em>.</p>", html)
        self.assertIn("<p>Group intro.</p>", html)

    def test_all_smoke_has_no_deep(self):
        plan = parse.parse_text(HEAD + "## 1 A\n- [ ] a\n  smoke: yes\n")
        self.assertNotIn('id="deep"', render.render(plan))

    def test_step_injection(self):
        plan = parse.parse_text(HEAD + '## 1 A\n- [ ] <img src=x onerror="alert(1)"> [x](javascript:alert(1))\n'
                                '  Expect: <script>alert(2)</script>\n  note: </textarea><b>\n  log: a"b\n')
        html = render.render(plan)
        t = tree(html)
        self.assertEqual(t.find("img"), [])
        self.assertIn('<div class="hint">&lt;/textarea&gt;&lt;b&gt;</div>', html)
        self.assertEqual(t.find("textarea"), [])
        self.assertNotIn("<script>alert", html)
        self.assertNotIn('href="javascript', html.lower())
        self.assertEqual(t.find("li", **{"class": "check"})[0]["data-log"], 'a"b')
        self.assertEqual(len(t.find("script")), 2)

    def test_missing_script_gives_empty_script(self):
        old = render.ASSETS
        try:
            import tempfile
            import shutil
            with tempfile.TemporaryDirectory() as d:
                shutil.copy(os.path.join(old, "page.css"), d)
                render.ASSETS = d
                html = render.render(self.plan)
                self.assertIn("<script>\n\n</script>", html)
                render.ASSETS = os.path.join(d, "none")
                with self.assertRaises(model.SetupError):
                    render.render(self.plan)
        finally:
            render.ASSETS = old


if __name__ == "__main__":
    unittest.main()
