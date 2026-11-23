"""Marks, results and log-check import, and the starter plan (chunk C3). See FORMAT.md sections 3 to 5."""
from __future__ import annotations

import json
import logging
import os
import re
import tempfile

from .model import MARKS_FORMAT, RESULTS, RESULTS_FORMAT, RUN_RE, TOOL_ID, Plan, SetupError

log = logging.getLogger("sf-test-plan")

STEP_TEXT_MAX = 300  # FORMAT.md 3: "t" is plain text, at most 300 characters


# ---------------------------------------------------------------- helpers

def _split_format(fmt: str) -> tuple[str, str]:
    family, _, major = fmt.partition("/")
    return family, major


def _major(fmt: object, family: str) -> str | None:
    """The major version in "<family>/<major>", or None when fmt isn't of that family."""
    if not isinstance(fmt, str) or not fmt.startswith(family + "/"):
        return None
    return fmt[len(family) + 1:].split(".")[0]


def _id_key(cid: str):
    """Sort key for check ids such as "2.10": by number, not by text."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in str(cid).split(".")]


def plain_text(md: str, limit: int | None = STEP_TEXT_MAX) -> str:
    """Inline Markdown -> plain text (for the "t" field): drops `code`, **bold**, *italic* marks and link targets.

    The text is cut to limit characters (ending "...") unless limit is None."""
    s = re.sub(r"\[([^\]]*)\]\((https?://[^)\s]*)\)", r"\1", md or "")
    s = s.replace("`", "")
    s = re.sub(r"\*\*(.+?)\*\*", r"\1", s)
    s = re.sub(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])", r"\1", s)
    s = " ".join(s.split())
    if limit is not None and len(s) > limit:
        s = s[:limit - 3].rstrip() + "..."
    return s


def _str(v: object) -> str:
    return v if isinstance(v, str) else ""


def _load_json(path: str, fix: str):
    if os.path.isdir(path):     # Windows reports a folder as "Permission denied", so look first
        raise SetupError(f"{path} is a folder, not a file. {fix}")
    try:
        with open(path, "rb") as f:
            raw = f.read()
    except OSError as e:
        raise SetupError(f"can't read {path}: {e.strerror}. {fix}")
    try:
        # UTF-16 with a byte-order mark is what Windows PowerShell's '>' writes; read it too
        text = raw.decode("utf-16") if raw[:2] in (b"\xff\xfe", b"\xfe\xff") else raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise SetupError(f"{path} isn't UTF-8 (or UTF-16) text. Save it as UTF-8. {fix}")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise SetupError(f"{path} isn't valid JSON (line {e.lineno}, column {e.colno}: {e.msg}). {fix}")


# ---------------------------------------------------------------- marks (FORMAT.md 3)

def read_marks(path: str) -> dict:
    """Read and validate a marks file (FORMAT.md 3). Raises SetupError on a bad file or another major format."""
    fix = "Give the marks file the page's Export button (or sf-test-plan logs) wrote."
    data = _load_json(path, fix)
    if not isinstance(data, dict):
        raise SetupError(f"{path} isn't a marks file (it should hold one JSON object). {fix}")
    fmt = data.get("format")
    family, want = _split_format(MARKS_FORMAT)
    major = _major(fmt, family)
    if major is None:
        raise SetupError(f"{path} isn't a marks file (format is {fmt!r}, expected {MARKS_FORMAT!r}). {fix}")
    if major != want:
        raise SetupError(f"{path} uses {fmt}, a marks format this sf-test-plan doesn't read (it reads "
                         f"{MARKS_FORMAT}). Use the sf-test-plan version that wrote the file, or update sf-test-plan.")
    run = data.get("run")
    if not isinstance(run, str) or not run:
        raise SetupError(f"{path} has no \"run\". {fix}")
    checks = data.get("checks")
    if not isinstance(checks, list):
        raise SetupError(f"{path} has no \"checks\" list. {fix}")
    out_checks = []
    for i, c in enumerate(checks, 1):
        where = f"{path}: check {i}"
        if not isinstance(c, dict):
            raise SetupError(f"{where} isn't a JSON object. {fix}")
        cid = c.get("id")
        if not isinstance(cid, str) or not cid:
            raise SetupError(f"{where} has no \"id\". Each check needs an id such as \"1.2\".")
        if "r" not in c:
            raise SetupError(f"{where} (id {cid}) has no \"r\". Use \"pass\", \"fail\", \"skip\" or \"\".")
        r = c["r"]
        if r not in RESULTS:
            raise SetupError(f"{where} (id {cid}) has r = {r!r}. Use \"pass\", \"fail\", \"skip\" or \"\".")
        g = c.get("g")
        out_checks.append({
            "id": cid, "r": r, "n": _str(c.get("n")), "t": _str(c.get("t")),
            "g": g if isinstance(g, int) and not isinstance(g, bool) else None,
            "at": _str(c.get("at")), "src": _str(c.get("src")),
        })
    log.debug("read %s: run %s, %d checks", path, run, len(out_checks))
    return {"format": fmt, "run": run, "title": _str(data.get("title")), "exported": _str(data.get("exported")),
            "tool": _str(data.get("tool")), "checks": out_checks}


def _latest_by_id(marks: dict) -> dict[str, dict]:
    """One mark per id; when an id appears twice, the newer "at" wins (the later entry wins a tie)."""
    best: dict[str, dict] = {}
    for c in marks.get("checks", []):
        old = best.get(c["id"])
        if old is None or (c.get("at") or "") >= (old.get("at") or ""):
            best[c["id"]] = c
    return best


# ---------------------------------------------------------------- results (FORMAT.md 4)

def summarize(plan: Plan, marks: dict, today: str) -> dict:
    """One results row (FORMAT.md 4) from a plan and its marks: test = "Smoke test" when the plan has smoke checks
    and no deep check is marked, else "Full test"; happened = counts; notes = every fail and every note, by id."""
    by_id = _latest_by_id(marks)
    checks = plan.checks()
    has_smoke = any(c.smoke for c in checks)
    deep_marked = any(by_id.get(c.id, {}).get("r") for c in checks if not c.smoke)
    smoke_round = has_smoke and not deep_marked
    counted = [c for c in checks if c.smoke] if smoke_round else checks
    counts = {"pass": 0, "fail": 0, "skip": 0}
    not_run = 0
    for c in counted:
        r = by_id.get(c.id, {}).get("r", "")
        if r in counts:
            counts[r] += 1
        else:
            not_run += 1
    plan_ids = {c.id for c in checks}
    extra = sorted((i for i in by_id if i not in plan_ids), key=_id_key)
    if extra:
        log.debug("marks for ids not in the plan, left out of the counts: %s", ", ".join(extra))

    fails, others = [], []
    for cid in sorted(by_id, key=_id_key):
        m = by_id[cid]
        note = " ".join((m.get("n") or "").split())
        if m.get("r") == "fail":
            fails.append(f"{cid} fail: {note}" if note else f"{cid} fail")
        elif note:
            label = f"{cid} {m['r']}" if m.get("r") else cid
            others.append(f"{label}: {note}")
    row = {"date": today, "run": marks.get("run") or plan.run,
           "test": "Smoke test" if smoke_round else "Full test",
           "happened": f"{counts['pass']} pass, {counts['fail']} fail, {counts['skip']} skip, {not_run} not run",
           "notes": "; ".join(fails + others)}
    log.debug("summary: %s", row)
    return row


def results_path(plan_path: str) -> str:
    """<plan>.results.json next to the plan (Beacon.testplan.md -> Beacon.testplan.results.json)."""
    base = plan_path[:-3] if plan_path.lower().endswith(".md") else plan_path
    return base + ".results.json"


def load_results(plan_path: str) -> list[dict]:
    """Rows of the plan's results file, newest first; [] when there is none. SetupError if it's broken."""
    path = results_path(plan_path)
    if not os.path.exists(path):
        log.debug("no results file %s", path)
        return []
    fix = "Fix the file by hand, or move it away (sf-test-plan won't overwrite it), then run the command again."
    data = _load_json(path, fix)
    family, want = _split_format(RESULTS_FORMAT)
    if isinstance(data, list):        # the private kit's results.json is a bare list of rows
        rows = data
    elif isinstance(data, dict):
        fmt = data.get("format")
        major = _major(fmt, family)
        if major is None:
            raise SetupError(f"{path} isn't a results file (format is {fmt!r}, expected {RESULTS_FORMAT!r}). {fix}")
        if major != want:
            raise SetupError(f"{path} uses {fmt}, a results format this sf-test-plan doesn't read (it reads "
                             f"{RESULTS_FORMAT}). Update sf-test-plan, or move the file away.")
        rows = data.get("rows")
        if not isinstance(rows, list):
            raise SetupError(f"{path} has no \"rows\" list. {fix}")
    else:
        raise SetupError(f"{path} isn't a results file. {fix}")
    for i, r in enumerate(rows, 1):
        if not isinstance(r, dict):
            raise SetupError(f"{path}: row {i} isn't a JSON object. {fix}")
    log.debug("read %s: %d rows", path, len(rows))
    return rows


def add_result(plan_path: str, row: dict) -> str:
    """Put a row first in the results file (made if missing). Returns the file's path."""
    path = results_path(plan_path)
    rows = load_results(plan_path)          # raises on a broken file, so a broken file is never overwritten
    data = {"format": RESULTS_FORMAT, "rows": [row] + rows}
    folder = os.path.dirname(os.path.abspath(path))
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".results-", suffix=".tmp", dir=folder)
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            json.dump(data, f, indent=1, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, path)
        tmp = None
    except OSError as e:
        raise SetupError(f"can't write {path}: {e.strerror}. Check that the plan's folder is writable.")
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)
    log.debug("wrote %s (%d rows)", path, len(data["rows"]))
    return path


# ---------------------------------------------------------------- papyrus-log-check (FORMAT.md 5)

def _pick_mod(plan: Plan, mods: list[dict], mod: str | None) -> tuple[dict, str]:
    names = [str(m.get("mod", "")) for m in mods]
    listing = ", ".join(repr(n) for n in names) or "(none)"
    if mod:
        for m in mods:
            if str(m.get("mod", "")).casefold() == mod.casefold():
                return m, f"Using {m.get('mod')!r} from the report (--mod)."
        raise SetupError(f"the report has no mod named {mod!r}. Mods in the report: {listing}. "
                         f"Give one of these with --mod.")
    if plan.mod:
        for m in mods:
            if str(m.get("mod", "")).casefold() == plan.mod.casefold():
                return m, f"Using {m.get('mod')!r} from the report (the plan's mod: line)."
    if len(mods) == 1:
        return mods[0], f"Using {mods[0].get('mod')!r}, the only mod in the report."
    why = f"none is named {plan.mod!r} (the plan's mod: line)" if plan.mod else "the plan has no mod: line"
    raise SetupError(f"the report holds {len(mods)} mods and {why}. Mods in the report: {listing}. "
                     f"Pick one with --mod.")


def logs_to_marks(plan: Plan, report: dict, mod: str | None, now: str) -> tuple[dict, list[str]]:
    """papyrus-log-check JSON -> a marks dict (src "log") plus plain lines saying what was decided for each check."""
    fix = "Give the .json report papyrus-log-check (0.3.0 or later) wrote."
    if not isinstance(report, dict) or not isinstance(report.get("mods"), list):
        raise SetupError(f"the report has no \"mods\" list, so it isn't a papyrus-log-check JSON report. {fix}")
    mods = [m for m in report["mods"] if isinstance(m, dict)]
    if not mods:
        raise SetupError(f"the report lists no mods. Run papyrus-log-check with your mod's rule file. {fix}")
    entry, how = _pick_mod(plan, mods, mod)
    name = entry.get("mod")
    lines = [how]
    marks = {"format": MARKS_FORMAT, "run": plan.run, "title": plan.title, "exported": now, "tool": TOOL_ID,
             "checks": []}
    status = str(entry.get("status", ""))
    log.debug("mod %r status %s", name, status)
    if status == "NOT LOADED":
        lines.append(f"{name} was NOT LOADED in that game session (its plugin was missing or turned off), "
                     f"so no marks were written. Enable the mod, play again and collect new logs.")
        return marks, lines

    rules: dict[str, dict] = {}
    for r in entry.get("rules", []) or []:
        if isinstance(r, dict) and "id" in r:
            rules.setdefault(str(r["id"]), r)

    log_checks = [c for c in plan.checks() if c.log]
    log_only = [c for c in plan.log_checks if c.log]
    if not log_checks and not log_only:
        lines.append("The plan has no checks with log: ids, so there is nothing to mark.")
    elif not log_checks:
        lines.append("No page check has log: ids, so the marks file has no marks. The Log checks are below.")
    for c in log_checks:
        found = [rid for rid in c.log if rid in rules]
        missing = [rid for rid in c.log if rid not in rules]
        desc = {}
        for rid in found:
            r = rules[rid]
            st = str(r.get("status", ""))
            if r.get("kind") == "forbid" and st == "PASS":
                desc[rid] = f"{rid} PASS (the forbidden line never appeared)"
            else:
                desc[rid] = f"{rid} {st}"
        fails = [rid for rid in found if rules[rid].get("status") == "FAIL"]
        if fails:
            res = "fail"
            note = "Log: " + "; ".join(desc[rid] for rid in fails) + "."
        elif not missing and all(rules[rid].get("status") == "PASS" for rid in found):
            res = "pass"
            note = "Log: " + "; ".join(desc[rid] for rid in found) + "."
        else:
            res = ""
            bits = [desc[rid] for rid in found if rules[rid].get("status") != "PASS"]
            bits += [f"{rid} isn't in the report" for rid in missing]
            note = "Log: not proved: " + "; ".join(bits) + "."
        # A check the log didn't prove gets no entry: an empty-result entry would replace a tester's own mark on
        # import (newer "at" wins). The reason stays in the printed lines.
        if res:
            marks["checks"].append({"id": c.id, "r": res, "n": note, "t": plain_text(c.step), "g": c.group,
                                    "at": now, "src": "log"})
        verdict = {"pass": "pass", "fail": "FAIL", "": "no mark"}[res]
        lines.append(f"{c.id} {verdict}: {note[len('Log: '):]}")
        for rid in missing:
            lines.append(f"  {c.id}: rule {rid!r} isn't in the report for {name}. Check the id against the rule "
                         f"file, and that papyrus-log-check used the current rule file.")
        log.debug("check %s: %s (%s)", c.id, res or "no mark", note)
    # Log checks have no control on the page, so they get a line each but never a mark (FORMAT.md 5).
    for c in log_only:
        sts = {rid: str(rules[rid].get("status", "")) if rid in rules else "" for rid in c.log}
        if any(s == "FAIL" for s in sts.values()):
            verdict = "FAIL"
        elif all(s == "PASS" for s in sts.values()):
            verdict = "PASS"
        else:
            verdict = "NOT SEEN"
        bits = [f"{rid} {s}" if s else f"{rid} isn't in the report" for rid, s in sts.items()]
        lines.append(f"{c.id} log check {verdict}: {'; '.join(bits)}.")
        log.debug("log check %s: %s", c.id, verdict)
    return marks, lines


# ---------------------------------------------------------------- starter plan

def _run_id(mod: str) -> str:
    """Run id from a mod name: lowercase, other characters become dashes, plus -0.1.0 (FORMAT.md 1, rule 2)."""
    suffix = "-0.1.0"
    s = re.sub(r"[^a-z0-9._-]+", "-", mod.lower())
    s = re.sub(r"-{2,}", "-", s).strip("-._")
    s = s[:64 - len(suffix)].rstrip("-._") or "my-mod"
    run = s + suffix
    if not RUN_RE.match(run):   # can't happen with the rules above; kept as a guard
        run = "my-mod" + suffix
    return run


def starter_plan(mod: str) -> str:
    """Text of a starter plan for a mod, valid under FORMAT.md, with a smoke test and comments explaining each part."""
    mod = " ".join((mod or "").split()) or "My Mod"
    run = _run_id(mod)
    next_run = run[:-len("0.1.0")] + "0.1.1"
    zipname = (re.sub(r"[^A-Za-z0-9._-]+", "", mod.replace(" ", "")) or "MyMod") + "-0.1.0.zip"
    return f"""# {mod} test plan
run: {run}
mod: {mod}
version: 0.1.0
zip: {zipname}

<!-- The first "# " line is the plan's title, and the lines right under it are the header.
     The run line names this test round. Your marks are saved under it, so give each new build a new run
     (for example {next_run}) and the page starts with empty marks.
     The mod, version and zip lines are shown in the page's facts box. Keep the mod line the same as the
     "mod" name in your papyrus-log-check rule file, so "sf-test-plan logs" finds your mod in the report. -->

This plan tests {mod} 0.1.0. Start with the smoke test; the deep checks are for before a public release.

<!-- The text above is the page's introduction. Say what the mod does and what this round tests. -->

## Before you start

<!-- Each bullet in this section becomes a numbered setup step. They are not checks: nobody marks them. -->

- Install {zipname} with your mod manager and enable it.
- Turn on Papyrus logging (the mod's README says how), so `sf-test-plan logs` can check the log lines.
- Start a new character, so an old save doesn't hide problems.

## 1 Install and load

<!-- A group is a second-level heading with a number and a title. Text right after the heading is the
     group's introduction. Each "- [ ]" line is one check, and the indented lines under it belong to it:
     Expect says what you should see; "smoke: yes" puts the check in the short smoke test shown first;
     a log line lists papyrus-log-check rule ids that also prove the check (for example "log: loaded";
     "sf-test-plan rules" starts a rule file with a rule for each id); a note line is a hint shown under
     the step. -->

These checks prove the mod loads.

- [ ] Start a new game and finish the character creator.
  Expect: no error message about {mod}.
  smoke: yes
- [ ] Open the mod's settings, if it has any.
  Expect: its options are there, with the defaults its README gives.
  smoke: yes

## 2 Main feature

<!-- Replace these with the steps that use your mod's main feature. Put console commands in backticks,
     such as `player.additem 0000000F 100`: the page gives them a Copy button. -->

- [ ] Use the mod's main feature once.
  Expect: it does what the README says.
  smoke: yes
- [ ] Try the same thing in a second place (indoors, in space or on another planet).
  Expect: it works there too.
  note: Checks without "smoke: yes" fold into "Deep checks (optional)" on the page.

## 3 Save and load

- [ ] Save, quit to the main menu and load the save.
  Expect: everything the mod changed is still there.
  smoke: yes
"""
