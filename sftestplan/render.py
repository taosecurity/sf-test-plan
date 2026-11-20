"""HTML page writer (chunk C1). Interface frozen by the master; see FORMAT.md section 2.
The page's CSS and script come from ../assets/page.css and ../assets/page.js (C2) and are inlined."""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re

from . import model
from .model import Check, Group, Plan, SetupError

log = logging.getLogger("sf-test-plan")

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\[\]]+)\]\((https?://[^\s()<>\"]+)\)")
_BOLD_RE = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*")
_ITALIC_RE = re.compile(r"(?<![\w*])\*(?=[^\s*])(.+?)(?<=[^\s*])\*(?![\w*])")
_SLOT_RE = re.compile(r"\x00(\d+)\x00")


def esc(text: str) -> str:
    return _html.escape(str(text), quote=True)


def _emphasis(h: str) -> str:
    h = _BOLD_RE.sub(r"<strong>\1</strong>", h)
    return _ITALIC_RE.sub(r"<em>\1</em>", h)


def inline(md: str) -> str:
    """Inline Markdown to safe HTML (FORMAT.md rule 9): escape everything, then code, bold, italic, http(s) links.
    Code spans matching model.COMMAND_RE get class="cmd"."""
    slots: list[str] = []

    def keep(fragment: str) -> str:
        slots.append(fragment)
        return f"\x00{len(slots) - 1}\x00"

    def code(m: re.Match) -> str:
        raw = m.group(1)
        cls = ' class="cmd"' if model.COMMAND_RE.match(raw.strip()) else ""
        return keep(f"<code{cls}>{esc(raw)}</code>")

    text = str(md).replace("\x00", "")
    text = _CODE_RE.sub(code, text)          # code first, so nothing inside it becomes bold or a link
    text = esc(text)                          # then everything else is plain text

    def link(m: re.Match) -> str:
        return keep(f'<a href="{m.group(2)}" rel="noopener">{_emphasis(m.group(1))}</a>')

    text = _LINK_RE.sub(link, text)          # the url is already escaped, and only http(s) matches
    text = _emphasis(text)
    for _ in range(3):                        # links can hold code slots
        text = _SLOT_RE.sub(lambda m: slots[int(m.group(1))], text)
    return text


def _paras(md: str, cls: str = "") -> list[str]:
    attr = f' class="{cls}"' if cls else ""
    return [f"<p{attr}>{inline(p)}</p>" for p in re.split(r"\n\s*\n", md or "") if p.strip()]


def _asset(name: str, required: bool) -> str:
    path = os.path.join(ASSETS, name)
    try:
        with open(path, encoding="utf-8-sig") as f:
            text = f.read()
    except OSError as e:
        if required:
            raise SetupError(f"can't read {path}: {e.strerror}. Reinstall sf-test-plan: the assets folder is part of it.")
        log.debug("no %s (%s): the page gets an empty script", path, e.strerror)
        return ""
    log.debug("inlined %s (%d characters)", path, len(text))
    return text


def _json_for_script(obj) -> str:
    """JSON that can sit inside <script> safely: no </script>, <!-- or & sequences survive."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _check_li(c: Check, groups: dict[int, Group], show_from: bool) -> str:
    parts = [f'<span class="id">{esc(c.id)}</span>', f"<div>{inline(c.step)}</div>"]
    if c.expect:
        parts.append(f'<div class="expect">Expect: {inline(c.expect)}</div>')
    if c.note:
        parts.append(f'<div class="hint">{inline(c.note)}</div>')
    if c.log:
        ids = " ".join(f"<code>{esc(x)}</code>" for x in c.log)
        parts.append(f'<div class="bylog">Also checked from the Papyrus log: {ids}</div>')
    if show_from:
        g = groups.get(c.group)
        title = f": {esc(g.title)}" if g and g.title else ""
        parts.append(f'<div class="from">From group {c.group}{title}</div>')
    attrs = (f'class="check" data-id="{esc(c.id)}" data-group="{c.group}" data-smoke="{1 if c.smoke else 0}" '
             f'data-log="{esc(" ".join(c.log))}"')
    return f'    <li {attrs}><div class="what">{"".join(parts)}</div></li>'


def _group_section(g: Group, checks: list[Check], groups: dict[int, Group]) -> list[str]:
    title = f" {esc(g.title)}" if g.title else ""
    out = [f'<section class="group" id="g{g.number}" data-group="{g.number}">',
           f'  <h2><span class="n">{g.number}</span>{title}</h2>']
    out += ["  " + p for p in _paras(g.intro)]
    out.append('  <ul class="checks">')
    out += [_check_li(c, groups, False) for c in checks]
    out.append("  </ul>\n</section>")
    return out


def _results_section(rows: list[dict]) -> list[str]:
    out = ['<section class="ref" id="results">', "  <h2>Results log</h2>",
           '  <p class="muted">One row per test round, newest first.</p>',
           '  <div class="tbl"><table>',
           "    <thead><tr><th>Date</th><th>Run</th><th>Test</th><th>What happened</th><th>Notes</th></tr></thead>",
           "    <tbody>"]
    for r in rows:
        if not isinstance(r, dict):
            continue
        cells = "".join(f"<td>{esc(r.get(k, '') or '')}</td>" for k in ("date", "run", "test", "happened", "notes"))
        out.append(f"      <tr>{cells}</tr>")
    out += ["    </tbody>", "  </table></div>", "</section>"]
    return out


def _safe_inline_code(text: str, tag: str) -> str:
    """Our own CSS or script, made safe to inline: it can't close its element early."""
    return re.sub(rf"</({tag})", r"<\\/\1", text, flags=re.I)


def render(plan: Plan, results: list[dict] | None = None) -> str:
    """The whole page as one HTML string (no network loads). results: rows from a results file, newest first."""
    css = _asset("page.css", required=True)
    js = _asset("page.js", required=False)
    title = plan.title or "Test plan"
    groups = {g.number: g for g in plan.groups}
    checks = plan.checks()
    smoke = plan.smoke()
    total = len(smoke) if smoke else len(checks)
    rows = [r for r in (results or []) if isinstance(r, dict)]
    config = {"format": model.PAGE_FORMAT, "run": plan.run, "title": title, "tool": model.TOOL_ID,
              "mod": plan.mod, "version": plan.version, "zip": plan.zip, "total": total}

    out = ["<!doctype html>", '<html lang="en">', "<head>", '<meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width, initial-scale=1">',
           f"<title>{esc(title)}</title>",
           f'<meta name="generator" content="{esc(model.TOOL_ID)}">',
           "<style>", _safe_inline_code(css, "style"), "</style>", "</head>", "<body>", '<div class="wrap">',
           "<header>", '  <div class="eyebrow">Test plan</div>', f"  <h1>{esc(title)}</h1>"]
    out += ["  " + p for p in _paras(plan.intro)]
    facts = [("Mod", plan.mod), ("Version", plan.version), ("Zip", plan.zip), ("Run", plan.run)]
    out.append('  <dl class="facts">')
    out += [f"    <div><dt>{k}</dt><dd>{esc(v)}</dd></div>" for k, v in facts if v]
    out.append("  </dl>")
    how = ("Mark each check Pass, Fail or Skip and add a note if something looks wrong. Your marks are saved in "
           "this browser as you go. Use <strong>Export</strong> to save them to a file you can share or import later.")
    if smoke:
        how = ("<strong>Smoke test first.</strong> The checks in the Smoke test box are the core ones. "
               "The deep checks are optional: open them before a public release, or when something looks wrong. " + how)
    out.append(f'  <p class="muted how">{how}</p>')
    toc = []
    if plan.setup:
        toc.append(("prep", "Before you start"))
    if smoke:
        toc.append(("smoke", "Smoke test"))
        if len(smoke) < len(checks):
            toc.append(("deep", "Deep checks"))
    else:
        toc += [(f"g{g.number}", f"{g.number} {g.title}".strip()) for g in plan.groups if g.checks]
    if rows:
        toc.append(("results", "Results log"))
    if toc:
        out.append('  <nav class="toc" aria-label="On this page">'
                   + "".join(f'<a href="#{a}">{esc(t)}</a>' for a, t in toc) + "</nav>")
    out.append("</header>")

    out += ['<div class="topbar" role="region" aria-label="Results">',
            f'  <div class="bar" id="tally" data-total="{total}">'
            # the page script rebuilds these; they show the right numbers when scripts are off
            '<span class="tally-item tally-pass"><b>0</b> pass</span> '
            '<span class="tally-item tally-fail"><b>0</b> fail</span> '
            '<span class="tally-item tally-skip"><b>0</b> skip</span> '
            f'<span class="tally-item tally-open"><b>{total}</b> not run</span> '
            f'<span class="tally-total">of {total} check{"" if total == 1 else "s"}</span></div>',
            '  <div class="tools" id="tools">'
            '<button type="button" data-act="export">Export</button>'
            '<button type="button" data-act="import">Import</button>'
            '<button type="button" data-act="copy">Copy results</button>'
            '<button type="button" data-act="reset">Reset</button>'
            '<input type="file" id="importfile" accept=".json,application/json" hidden></div>',
            '  <span id="saved" class="saved" aria-live="polite"></span>',
            "</div>"]

    if plan.setup:
        out += ['<section class="prep" id="prep">', "  <h2>Before you start</h2>", "  <ol>"]
        out += [f"    <li>{inline(s)}</li>" for s in plan.setup]
        out += ["  </ol>", "</section>"]

    if smoke:
        n = len(smoke)
        out += ['<section class="smoke" id="smoke" data-group="smoke">',
                f'  <h2><span class="n">S</span> Smoke test ({n} check{"s" if n != 1 else ""})</h2>',
                '  <p class="muted">Do these in this order. Each one keeps its number from its group.</p>',
                '  <ul class="checks">']
        out += [_check_li(c, groups, True) for c in smoke]
        out += ["  </ul>", "</section>"]
        rest = len(checks) - n
        if rest:
            out.append(f'<details class="deep" id="deep"><summary>Deep checks (optional): {rest} more</summary>')
            for g in plan.groups:
                left = [c for c in g.checks if not c.smoke]
                if left:
                    out += _group_section(g, left, groups)
            out.append("</details>")
    else:
        for g in plan.groups:
            if g.checks:
                out += _group_section(g, g.checks, groups)

    if rows:
        out += _results_section(rows)

    out += ["<footer>",
            f'  <p>Made with <a href="{esc(model.URL)}" rel="noopener">{esc(model.TOOL_ID)}</a>. '
            f"Marks are kept in this browser under the run <code>{esc(plan.run)}</code>; "
            "a new run starts with empty marks. If the line under the tally says saving isn't available, "
            "use <strong>Export</strong> before you close the page.</p>",
            "</footer>", "</div>",
            f'<script type="application/json" id="tp-config">{_json_for_script(config)}</script>',
            "<script>", _safe_inline_code(js, "script"), "</script>", "</body>", "</html>", ""]
    page = "\n".join(out)
    log.debug("rendered %r: %d checks on the page (%d smoke), total %d, %d results rows, %d characters",
              title, len(checks), len(smoke), total, len(rows), len(page))
    return page
