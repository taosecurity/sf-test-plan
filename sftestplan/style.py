"""Style rules for `check --style` and `build --style` (FORMAT.md section 7; format sf-test-plan-style/1).

A style file holds a project's own writing rules: how many smoke checks, ISO dates, full sentences and banned words.
Every rule is optional. Style problems join the plan's other problems with codes style-smoke, style-date,
style-sentence and style-banned, at the file's `level` (default error)."""
from __future__ import annotations

import json
import logging
import re

from . import parse
from .model import Plan, Problem, SetupError

log = logging.getLogger("sf-test-plan")

STYLE_FORMAT = "sf-test-plan-style/1"
KEYS = ("format", "level", "smoke", "iso_dates", "full_sentences", "banned")

_MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december"]
_MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?" \
       r"|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
_DATE_RES = [
    ("mdy", re.compile(r"(?<![\w./-])(\d{1,2})/(\d{1,2})/(\d{4})(?![\w/])")),
    ("ymd", re.compile(r"(?<![\w./-])(\d{4})/(\d{1,2})/(\d{1,2})(?![\w/])")),
    ("dmy", re.compile(r"(?<![\w.])(\d{1,2})\.(\d{1,2})\.(\d{4})(?![\w]|\.\d)")),
    ("Mdy", re.compile(r"(?<!\w)(" + _MON + r")\.?[ \t]+(\d{1,2})(?:st|nd|rd|th)?,?[ \t]+(\d{4})(?!\w)", re.I)),
    ("dMy", re.compile(r"(?<!\w)(\d{1,2})(?:st|nd|rd|th)?[ \t]+(" + _MON + r")\.?,?[ \t]+(\d{4})(?!\w)", re.I)),
]
_CODE_RE = re.compile(r"(`+)(.+?)\1")
_LINK_TARGET_RE = re.compile(r"\]\([^)]*\)")
_AUTOLINK_RE = re.compile(r"<[A-Za-z][A-Za-z0-9+.-]*:[^>\s]*>")
# Key lines whose value is data, not prose: never scanned for dates or banned words.
_DATA_KEYS = {"run", "mod", "version", "zip", "ngplus", "smoke", "log", "id"}
_KEY_RE = re.compile(r"^[ \t]*([A-Za-z][A-Za-z0-9_-]*):")
_LEAD_MARKUP_RE = re.compile(r"^(?:\*\*|__|\*|_|\[|~~)+")
_TRAIL_RE = re.compile(r"(?:\*\*|__|\*|_|~~|[)\]\"'”’])+$")


class Style:
    def __init__(self, level: str = "error", smoke_min: int | None = None, smoke_max: int | None = None,
                 iso_dates: bool = False, full_sentences: bool = False,
                 banned: list[tuple[str, str]] | None = None):
        self.level = level
        self.smoke_min = smoke_min
        self.smoke_max = smoke_max
        self.iso_dates = iso_dates
        self.full_sentences = full_sentences
        self.banned = banned or []


def _bad(path: str, key: str, why: str) -> SetupError:
    return SetupError(f"{path}: '{key}' {why}. Fix the style file (format {STYLE_FORMAT}; FORMAT.md section 7).")


def _count(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def parse_style(data, path: str) -> Style:
    """A Style from a decoded JSON value. Raises SetupError (exit 2) naming the key for anything wrong."""
    if not isinstance(data, dict):
        raise SetupError(f"{path} isn't a style file: it should be a JSON object with \"format\": \"{STYLE_FORMAT}\".")
    for k in data:
        if k not in KEYS:
            raise _bad(path, k, f"isn't a style key (the keys are {', '.join(KEYS)})")
    if data.get("format") != STYLE_FORMAT:
        raise _bad(path, "format", f"should be \"{STYLE_FORMAT}\"")
    st = Style()
    if "level" in data:
        if data["level"] not in ("error", "warning"):
            raise _bad(path, "level", "should be \"error\" or \"warning\"")
        st.level = data["level"]
    if "smoke" in data:
        sm = data["smoke"]
        if not isinstance(sm, dict):
            raise _bad(path, "smoke", "should be an object such as {\"min\": 1, \"max\": 12}")
        for k in sm:
            if k not in ("min", "max"):
                raise _bad(path, f"smoke.{k}", "isn't a smoke key (use min and max)")
            if not _count(sm[k]):
                raise _bad(path, f"smoke.{k}", "should be a whole number, 0 or more")
        st.smoke_min, st.smoke_max = sm.get("min"), sm.get("max")
        if st.smoke_min is not None and st.smoke_max is not None and st.smoke_min > st.smoke_max:
            raise _bad(path, "smoke.min", f"({st.smoke_min}) is more than smoke.max ({st.smoke_max})")
    for k in ("iso_dates", "full_sentences"):
        if k in data:
            if not isinstance(data[k], bool):
                raise _bad(path, k, "should be true or false")
            setattr(st, k, data[k])
    if "banned" in data:
        if not isinstance(data["banned"], list):
            raise _bad(path, "banned", "should be a list of words, or of {\"word\": ..., \"use\": ...} objects")
        for i, b in enumerate(data["banned"]):
            where = f"banned[{i}]"
            if isinstance(b, str):
                word, use = b, ""
            elif isinstance(b, dict):
                for k in b:
                    if k not in ("word", "use"):
                        raise _bad(path, f"{where}.{k}", "isn't a banned-word key (use word and use)")
                word, use = b.get("word"), b.get("use", "")
                if not isinstance(use, str):
                    raise _bad(path, f"{where}.use", "should be text")
            else:
                raise _bad(path, where, "should be a word or a {\"word\": ..., \"use\": ...} object")
            if not isinstance(word, str) or not word.strip():
                raise _bad(path, where if isinstance(b, str) else f"{where}.word", "should be a word that isn't empty")
            st.banned.append((word.strip(), use.strip()))
    return st


def load_style(path: str) -> Style:
    text = parse._read_text(path, "style file")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SetupError(f"{path} isn't valid JSON (line {e.lineno}: {e.msg}). Give a style file (.json).")
    st = parse_style(data, path)
    log.debug("style file %s: level %s, smoke %s..%s, iso_dates %s, full_sentences %s, %d banned",
              path, st.level, st.smoke_min, st.smoke_max, st.iso_dates, st.full_sentences, len(st.banned))
    return st


# ---- helpers

def _prose(text: str) -> str:
    """The text with code spans, link targets and autolinks blanked out (same length, so columns stay)."""
    blank = lambda m: " " * len(m.group(0))  # noqa: E731
    text = _CODE_RE.sub(blank, text)
    text = _LINK_TARGET_RE.sub(lambda m: "]" + " " * (len(m.group(0)) - 1), text)
    return _AUTOLINK_RE.sub(blank, text)


def _iso(kind: str, m: re.Match) -> str:
    try:
        if kind == "mdy":
            a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            mo, d = (a, b) if a <= 12 else (b, a)
        elif kind == "ymd":
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif kind == "dmy":
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        elif kind == "Mdy":
            mo, d, y = _month(m.group(1)), int(m.group(2)), int(m.group(3))
        else:
            d, mo, y = int(m.group(1)), _month(m.group(2)), int(m.group(3))
    except ValueError:
        return ""
    if not (1 <= mo <= 12 and 1 <= d <= 31):
        return ""
    return f"{y:04d}-{mo:02d}-{d:02d}"


def _month(name: str) -> int:
    n = name.lower().rstrip(".")
    for i, full in enumerate(_MONTHS, 1):
        if full.startswith(n[:3]):
            return i
    raise ValueError(name)


def _sentence_ok(text: str, check_start: bool = True) -> str:
    """'' when text reads as a full sentence, else what is wrong."""
    t = text.strip()
    if not t:
        return ""
    if check_start:
        s = _LEAD_MARKUP_RE.sub("", t)
        first = s[:1]
        if not (first.isupper() or first.isdigit() or first in "\"'`“‘"):
            return "doesn't start with a capital letter"
    end = _TRAIL_RE.sub("", t)
    if not end or end[-1] not in ".!?:":
        return "doesn't end with '.', '!', '?' or ':'"
    return ""


def _find_line(lines: list[tuple[int, str]], text: str, start: int = 0) -> int:
    """The first line at or after `start` that holds the start of `text` (0 if none)."""
    probe = text.strip().split("\n", 1)[0][:40].strip()
    if not probe:
        return 0
    for n, raw in lines:
        if n >= start and probe in raw:
            return n
    return 0


def _key_line(lines: list[tuple[int, str]], key: str, start: int) -> int:
    rx = re.compile(r"^[ \t]*" + re.escape(key) + r":", re.I)
    for n, raw in lines:
        if n > start and rx.match(raw):
            return n
    return start


def _paragraphs(text: str) -> list[str]:
    out = []
    for para in re.split(r"\n[ \t]*\n", text or ""):
        p = para.strip()
        if p and not p.startswith(("|", "- ", "* ", ">", "#", "```")):
            out.append(" ".join(x.strip() for x in p.splitlines()))
    return out


# ---- the check

def apply(plan: Plan, text: str, st: Style) -> list[Problem]:
    """Add the style problems for plan (parsed from text) to plan.problems, and return them."""
    lines = [(n, raw) for n, raw, skip in parse._lines(text)[0] if not skip]
    found: list[Problem] = []

    def add(code: str, line: int, msg: str) -> None:
        found.append(Problem(st.level, code, line, msg))

    n_smoke = len(plan.smoke())
    if st.smoke_min is not None and n_smoke < st.smoke_min:
        add("style-smoke", 0, f"the plan has {n_smoke} smoke checks; the style file asks for at least {st.smoke_min}. "
                              "Mark more checks with 'smoke: yes'.")
    if st.smoke_max is not None and n_smoke > st.smoke_max:
        add("style-smoke", 0, f"the plan has {n_smoke} smoke checks; the style file allows at most {st.smoke_max}. "
                              "Move the less important ones to the deep checks (remove 'smoke: yes').")

    if st.iso_dates or st.banned:
        banned = [(w, use, re.compile(r"(?<!\w)" + r"\s+".join(re.escape(x) for x in w.split()) + r"(?!\w)", re.I))
                  for w, use in st.banned]
        for n, raw in lines:
            km = _KEY_RE.match(raw)
            if km and km.group(1).lower() in _DATA_KEYS:
                continue
            prose = _prose(raw)
            if st.iso_dates:
                for kind, rx in _DATE_RES:
                    for m in rx.finditer(prose):
                        iso = _iso(kind, m)
                        fix = f"Write it as {iso}." if iso else "Write it as YYYY-MM-DD."
                        add("style-date", n, f"the date '{m.group(0)}' isn't written as YYYY-MM-DD. {fix}")
            for w, use, rx in banned:
                for m in rx.finditer(prose):
                    fix = f"Write '{use}' instead." if use else "Reword it."
                    add("style-banned", n, f"'{m.group(0)}' is on the style file's banned list. {fix}")

    if st.full_sentences:
        def sent(what: str, body: str, line: int, check_start: bool = True) -> None:
            why = _sentence_ok(body, check_start)
            if why:
                add("style-sentence", line, f"{what} {why}, so it isn't a full sentence. Write it as a full sentence.")

        for para in _paragraphs(plan.intro):
            sent("the introduction", para, _find_line(lines, para))
        for item in plan.setup:
            sent("a Before you start item", item, _find_line(lines, item))
        sections = [("check", g.checks, g.intro, g.line, f"group {g.number}'s introduction") for g in plan.groups]
        sections.append(("Log check", plan.log_checks, plan.log_intro, plan.log_line, "the Log checks introduction"))
        sections.append(("New Game+ check", plan.ngplus_checks, plan.ngplus_intro, plan.ngplus_line,
                         "the New Game+ introduction"))
        for kind, checks, intro, hline, intro_name in sections:
            for para in _paragraphs(intro):
                sent(intro_name, para, _find_line(lines, para, hline))
            for i, c in enumerate(checks, 1):
                name = f"{kind} {c.id}" if kind != "New Game+ check" else f"{kind} {i}"
                sent(f"{name}'s step", c.step, c.line)
                # Expect: and logcheck: follow a label on the page ("Expect:", "Check in the log:"), so they may
                # start in lower case ("Expect: one beacon in your inventory."); they must still end a sentence.
                if c.expect:
                    sent(f"{name}'s Expect", c.expect, _key_line(lines, "expect", c.line), check_start=False)
                if c.note:
                    sent(f"{name}'s note", c.note, _key_line(lines, "note", c.line))
                if c.logcheck:
                    sent(f"{name}'s logcheck", c.logcheck, _key_line(lines, "logcheck", c.line), check_start=False)

    plan.problems.extend(found)
    plan.problems.sort(key=lambda x: x.line)
    log.debug("style: %d problems", len(found))
    return found
