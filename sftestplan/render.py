"""HTML page writer (chunk C1). Interface frozen by the master; see FORMAT.md section 2.
The page's CSS and script come from ../assets/page.css and ../assets/page.js (C2) and are inlined."""
from __future__ import annotations

import hashlib
import html as _html
import json
import logging
import os
import re
import urllib.parse

from . import model
from .model import Check, Group, Plan, SetupError
from .results import plain_text

log = logging.getLogger("sf-test-plan")

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")

_CODE_RE = re.compile(r"`([^`]+)`")
_LINK_RE = re.compile(r"\[([^\[\]]+)\]\((https?://[^\s()<>\"\x00]+)\)")  # \x00: a code span can't sit inside a URL
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


HOST_ASSETS = (("sf-test-plan.js", "page.js"), ("sf-test-plan.css", "page.css"),
               ("sf-test-plan-fragment.css", "fragment.css"))


def asset_bytes(name: str) -> bytes:
    """An asset file's exact bytes (render --assets copies them for a host page)."""
    path = os.path.join(ASSETS, name)
    try:
        with open(path, "rb") as f:
            return f.read()
    except OSError as e:
        raise SetupError(f"can't read {path}: {e.strerror}. Reinstall sf-test-plan: the assets folder is part of it.")


def _json_for_script(obj) -> str:
    """JSON that can sit inside <script> safely: no </script>, <!-- or & sequences survive."""
    return (json.dumps(obj, ensure_ascii=False)
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def _check_li(c: Check, groups: dict[int, Group], show_from: bool, intro: str = "") -> str:
    # the page script reads the step text from div.step; a group intro (a precondition) is read first, so it goes first
    parts = [f'<span class="id">{esc(c.id)}</span>']
    if intro:
        parts += [f'<div class="group-intro">{inline(p)}</div>' for p in re.split(r"\n\s*\n", intro) if p.strip()]
    parts.append(f'<div class="step">{inline(c.step)}</div>')
    if c.expect:
        parts.append(f'<div class="expect">Expect: {inline(c.expect)}</div>')
    if c.note:
        parts.append(f'<div class="hint">{inline(c.note)}</div>')
    if c.log:
        ids = " ".join(f"<code>{esc(x)}</code>" for x in c.log)
        parts.append(f'<div class="bylog">Also checked from the Papyrus log: {ids}</div>')
    if c.logcheck:
        parts.append(f'<div class="bylog logcheck">Check in the log: {inline(c.logcheck)}</div>')
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


def _log_checks_section(plan: Plan) -> list[str]:
    """The Log checks table (FORMAT.md rule 12): no Pass/Fail control, not in the tally."""
    out = ['<section class="ref" id="log-checks">', "  <h2>Checks in the logs</h2>"]
    out += ["  " + p for p in _paras(plan.log_intro)]
    out += ['  <p class="muted">Check these in the logs after you play. They aren\'t marked on this page and '
            "don't count in the tally.</p>",
            '  <div class="tbl"><table>',
            "    <thead><tr><th>#</th><th>What</th><th>Expected</th></tr></thead>",
            "    <tbody>"]
    for c in plan.log_checks:
        what = [inline(c.step)]
        if c.note:
            what.append(f'<div class="hint">{inline(c.note)}</div>')
        if c.logcheck:
            what.append(f'<div class="bylog logcheck">Check in the log: {inline(c.logcheck)}</div>')
        if c.log:
            ids = " ".join(f"<code>{esc(x)}</code>" for x in c.log)
            what.append(f'<div class="bylog">Log rules: {ids}</div>')
        out.append(f'      <tr data-id="{esc(c.id)}"><td>{esc(c.id)}</td><td>{"".join(what)}</td>'
                   f"<td>{inline(c.expect)}</td></tr>")
    out += ["    </tbody>", "  </table></div>", "</section>"]
    return out


def _log_lines_section(rule_file: dict) -> list[str]:
    """'What the log lines mean' from a papyrus-log-check rule file's expect and forbid rules."""
    rows = []
    for kind, label in (("expect", "Expected"), ("forbid", "Must not appear")):
        for r in rule_file.get(kind) or []:
            if not isinstance(r, dict):
                continue
            rid, rx, means = (r.get(k) if isinstance(r.get(k), str) else "" for k in ("id", "re", "means"))
            pattern = f"<code>{esc(rx)}</code>" if rx else ""
            rows.append(f"      <tr><td>{esc(rid)}</td><td>{pattern}</td><td>{label}</td><td>{esc(means)}</td></tr>")
    if not rows:
        return []
    return (['<section class="ref" id="log-lines">', "  <h2>What the log lines mean</h2>",
             '  <p class="muted">The Papyrus log lines this mod writes, from its papyrus-log-check rule file.</p>',
             '  <div class="tbl"><table>',
             "    <thead><tr><th>Rule</th><th>Log line</th><th>Kind</th><th>What it means</th></tr></thead>",
             "    <tbody>"] + rows + ["    </tbody>", "  </table></div>", "</section>"])


def log_items(plan: Plan) -> list[dict]:
    """The tp-logchecks JSON (FORMAT.md section 2): every Log check ("log only") and every page check with a
    logcheck: line ("in-game"), in plain text, so a log reviewer can read them without parsing HTML."""
    items = [{"id": c.id, "kind": "log only", "what": plain_text(c.step, None), "expect": plain_text(c.expect, None),
              "log": list(c.log)} for c in plan.log_checks]
    items += [{"id": c.id, "kind": "in-game", "what": plain_text(c.logcheck, None),
               "expect": plain_text(c.expect, None), "log": list(c.log), "step": plain_text(c.step, None)}
              for c in plan.checks() if c.logcheck]
    return items


def ngplus_href(value: str) -> str:
    """The href for an ngplus: value the parser accepted (parse.ngplus_link_ok): an http(s) address as it is; a
    relative path with forward slashes and its spaces and other unsafe characters percent-encoded."""
    v = value.strip()
    if re.match(r"^https?://", v, re.I):
        return v
    return urllib.parse.quote(v.replace("\\", "/"), safe="/#?&=%+@!$,;~._-")


def _safe_inline_code(text: str, tag: str) -> str:
    """Our own CSS or script, made safe to inline: it can't close its element early."""
    return re.sub(rf"</({tag})", r"<\\/\1", text, flags=re.I)


def render(plan: Plan, results: list[dict] | None = None, rule_file: dict | None = None,
           fragment: bool = False) -> str:
    """The whole page as one HTML string (no network loads). results: rows from a results file, newest first.
    rule_file: a papyrus-log-check rule file object (--rules), shown as the "What the log lines mean" table.
    fragment: only the <div class="sf-test-plan"> a host page embeds (FORMAT.md section 2): no <h1>, <style>,
    inline script or footer; the host loads sf-test-plan.js after it."""
    css = "" if fragment else _asset("page.css", required=True)
    js = "" if fragment else _asset("page.js", required=False)
    title = plan.title or "Test plan"
    groups = {g.number: g for g in plan.groups}
    checks = plan.checks()
    smoke = plan.smoke()
    total = len(smoke) if smoke else len(checks)
    rows = [r for r in (results or []) if isinstance(r, dict)]
    # browsers share one storage area for all file:// pages, so the page's storage key also names the plan: its
    # folder and file name (two plans for one mod differ; two testplan.md files in different folders differ, with or
    # without a mod: line), its mod (case and spaces ignored) and its run. The title isn't part of it, so fixing a
    # typo in it keeps the marks.
    if plan.path and not plan.path.startswith("<"):
        full = os.path.abspath(plan.path)
        name = os.path.basename(os.path.dirname(full)).lower() + "/" + os.path.basename(full).lower()
    else:
        name = title
    mod = " ".join(plan.mod.split()).casefold()
    # surrogatepass: a folder name that isn't valid Unicode (Linux bytes, a Windows lone surrogate) still gets a key;
    # every other name encodes as before, so existing pages keep their marks.
    plan_id = hashlib.sha256(f"{name}\n{mod}\n{plan.run}".encode("utf-8", "surrogatepass")).hexdigest()[:12]
    config = {"format": model.PAGE_FORMAT, "run": plan.run, "title": title, "tool": model.TOOL_ID,
              "mod": plan.mod, "version": plan.version, "zip": plan.zip, "total": total, "plan": plan_id}

    if fragment:
        out = [f'<div class="sf-test-plan" data-run="{esc(plan.run)}">', '<section class="tp-intro">']
    else:
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
    if plan.ngplus:
        out.append(f'  <p class="ngplus" id="ngplus-link">New Game+ checks for this mod are on the '
                   f'<a href="{esc(ngplus_href(plan.ngplus))}">shared New Game+ page</a>.</p>')
    toc = []
    if plan.setup:
        toc.append(("prep", "Before you start"))
    if smoke:
        toc.append(("smoke", "Smoke test"))
        if len(smoke) < len(checks):
            toc.append(("deep", "Deep checks"))
    else:
        toc += [(f"g{g.number}", f"{g.number} {g.title}".strip()) for g in plan.groups if g.checks]
    log_lines = _log_lines_section(rule_file) if rule_file else []
    if plan.log_checks:
        toc.append(("log-checks", "Checks in the logs"))
    if log_lines:
        toc.append(("log-lines", "What the log lines mean"))
    if rows:
        toc.append(("results", "Results log"))
    if toc:
        out.append('  <nav class="toc" aria-label="On this page">'
                   + "".join(f'<a href="#{a}">{esc(t)}</a>' for a, t in toc) + "</nav>")
    out.append("</section>" if fragment else "</header>")

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
        # a group whose checks are all in the smoke test has no deep section, so its introduction goes with its
        # first smoke check (code review, 2026-11-19)
        shown: set[int] = set()
        for c in smoke:
            g = groups.get(c.group)
            alone = bool(g and g.intro and c.group not in shown and all(x.smoke for x in g.checks))
            out.append(_check_li(c, groups, True, g.intro if alone else ""))
            shown.add(c.group)
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

    if plan.log_checks:
        out += _log_checks_section(plan)
    out += log_lines
    if rows:
        out += _results_section(rows)

    data = [f'<script type="application/json" id="tp-config">{_json_for_script(config)}</script>',
            f'<script type="application/json" id="tp-logchecks">{_json_for_script(log_items(plan))}</script>']
    if fragment:
        page = "\n".join(out + data + ["</div>", ""])
        log.debug("rendered the fragment for %r: %d checks, %d characters", title, len(checks), len(page))
        return page
    out += ["<footer>",
            f'  <p>Made with <a href="{esc(model.URL)}" rel="noopener">{esc(model.TOOL_ID)}</a>. '
            f"Marks are kept in this browser under the run <code>{esc(plan.run)}</code>; "
            "a new run starts with empty marks. If the line under the tally says saving isn't available, "
            "use <strong>Export</strong> before you close the page.</p>",
            "</footer>", "</div>"] + data + [
            "<script>", _safe_inline_code(js, "script"), "</script>", "</body>", "</html>", ""]
    page = "\n".join(out)
    log.debug("rendered %r: %d checks on the page (%d smoke), total %d, %d results rows, %d characters",
              title, len(checks), len(smoke), total, len(rows), len(page))
    return page
