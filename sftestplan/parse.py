"""Markdown plan parser and linter (chunk C1). Interface frozen by the master; see FORMAT.md section 1."""
from __future__ import annotations

import json
import logging
import os
import re

from . import model
from .model import Check, Group, Plan, Problem, SetupError

log = logging.getLogger("sf-test-plan")

_MARK = "\x01"  # stands in for removed comment text, so a line that held only a comment can be skipped
_COMMENT_RE = re.compile(r"<!--.*?(?:-->|\Z)", re.S)
_TITLE_RE = re.compile(r"^#[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_H2_RE = re.compile(r"^##[ \t]+(.*?)(?:[ \t]+#+)?[ \t]*$")
_GROUP_RE = re.compile(r"^(\d+)\.?(?:[ \t]+(.*))?$")
_KEY_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):(?:[ \t]+(.*?)|[ \t]*)$")
_CHECK_RE = re.compile(r"^[-*][ \t]+\[[ xX]\](?:[ \t]+(.*?))?[ \t]*$")
_BULLET_RE = re.compile(r"^[-*][ \t]+(?:\[[ xX]\][ \t]*)?(.*?)[ \t]*$")
_ID_RE = re.compile(r"^(\d+)\.(\d+)$")
_YES = {"yes", "y", "true", "1", "on"}
_NO = {"no", "n", "false", "0", "off"}


def _lines(text: str) -> tuple[list[tuple[int, str, bool]], int]:
    """(line number, text, skip) for each line, and the line of an unclosed <!-- (0 if none). Comments are cut out; a line that held only comment text is
    skipped, so it doesn't end a check the way a blank line does. An unclosed <!-- runs to the end of the file."""
    if text.startswith("﻿"):
        text = text[1:]
    text = text.replace(_MARK, "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")   # one line-break form, so comment line counts are right
    unclosed: list[int] = []

    def cut(m: re.Match) -> str:
        if not m.group(0).endswith("-->"):
            unclosed.append(text.count("\n", 0, m.start()) + 1)
        return _MARK + ("\n" + _MARK) * m.group(0).count("\n")

    text = _COMMENT_RE.sub(cut, text)
    if unclosed:
        log.debug("the comment opened on line %d never closes (no -->): the rest of the file is ignored", unclosed[0])
    out = []
    for i, raw in enumerate(re.split(r"\r\n|\r|\n", text), 1):
        if _MARK in raw:
            raw = raw.replace(_MARK, "")
            out.append((i, raw.rstrip(), not raw.strip()))
        else:
            out.append((i, raw.rstrip(), False))
    return out, (unclosed[0] if unclosed else 0)


def _indented(raw: str) -> bool:
    return raw.startswith("\t") or raw.startswith("  ")


def _join(old: str, new: str) -> str:
    return f"{old} {new}" if old else new


class _Parser:
    """A line-by-line state machine. States: header (title and key lines), intro (plan introduction),
    setup (Before you start), group (a numbered group), ignore (under a heading with no number)."""

    def __init__(self, path: str, rule_ids: set[str] | None):
        self.path = path
        self.rule_ids = rule_ids
        self.plan = Plan(path=path)
        self.state = "header"
        self.group: Group | None = None
        self.check: Check | None = None
        self.lazy = False          # the last line belonged to the open check, with no blank line since
        self.setup_open = False    # the last setup item takes the next unindented line as its continuation
        self.paras: list[list[str]] = [[]]
        self.target: object = "plan"   # where self.paras goes: "plan", a Group, or None (dropped)
        self.log_lines: list[tuple[str, int]] = []
        self.group_lines: dict[int, int] = {}
        self.run_line = 0
        self.header_keys_seen = False
        self.last_field = "step"   # where a wrapped check line goes: step, expect, note or log

    def problem(self, level: str, code: str, line: int, message: str) -> None:
        self.plan.problems.append(Problem(level, code, line, message))

    # ---- introduction text (the plan's, or a group's)
    def flush(self) -> None:
        text = "\n\n".join(" ".join(p) for p in self.paras if p)
        self.paras = [[]]
        if not text:
            return
        if self.target == "plan":
            self.plan.intro = self.plan.intro + "\n\n" + text if self.plan.intro else text
        elif isinstance(self.target, Group):
            g = self.target
            g.intro = g.intro + "\n\n" + text if g.intro else text

    def retarget(self, target: object) -> None:
        self.flush()
        self.target = target

    # ---- one line
    def feed(self, n: int, raw: str) -> None:
        if not raw.strip():
            self.lazy = False
            self.setup_open = False
            if self.state == "header" and self.header_keys_seen:
                self.state = "intro"   # the header is the key lines right after the title; a blank line ends it
            if self.state != "header" and self.paras[-1]:
                self.paras.append([])
            return

        tm = _TITLE_RE.match(raw)
        if tm:
            if not self.plan.title:
                self.close_check()
                self.plan.title = tm.group(1).strip()
                return
            # a second "# " line is ordinary text
        else:
            hm = _H2_RE.match(raw)
            if hm:
                self.heading(n, hm.group(1).strip())
                return

        if self.state == "header":
            km = _KEY_RE.match(raw)
            if km:
                self.header_keys_seen = True
                self.header_key(n, km.group(1), (km.group(2) or "").strip())
                return
            self.state = "intro"

        cm = _CHECK_RE.match(raw)
        if cm and self.state == "group":
            self.new_check(n, cm.group(1) or "")
            return
        if cm and self.state in ("intro", "setup") and not _indented(raw):
            self.close_check()
            where = "'Before you start'" if self.state == "setup" else "the introduction"
            self.problem("error", "check-outside-group", n,
                         f"this '- [ ]' check is in {where}, so it would not be on the page. Move it under a "
                         "'## <number> <title>' group heading (or make it a plain '- ' bullet in Before you start).")
            return
        # indented lines belong to the open check; so does an unindented line right after it (Markdown's
        # lazy continuation), unless it starts a new bullet
        if self.check is not None and (_indented(raw) or (self.lazy and not _BULLET_RE.match(raw))):
            self.check_line(n, raw.strip())
            return
        self.close_check()

        if _indented(raw):
            km = _KEY_RE.match(raw.strip())
            if km and km.group(1).lower() in model.CHECK_KEYS:
                self.problem("error", "orphan-key", n, self.orphan_message(km.group(1)))
                return

        if self.state == "setup":
            self.setup_line(raw)
        elif self.state != "ignore":
            if self.state == "group" and self.group is not None and self.group.checks:
                log.debug("line %d: text after the checks of group %d is added to the group's introduction",
                          n, self.group.number)
            self.paras[-1].append(raw.strip())

    def orphan_message(self, key: str) -> str:
        if self.state in ("header", "intro"):
            fix = "Checks go under a '## <number> <title>' group heading, as '- [ ] <step>' lines"
        elif self.state == "setup":
            fix = "'Before you start' holds plain bullets, not checks: move the line under a check in a group"
        else:
            fix = "Put it right under a '- [ ] <step>' check line, or remove it"
        return f"the '{key}:' line has no check above it. {fix}."

    def header_key(self, n: int, key: str, value: str) -> None:
        k = key.lower()
        if k == "run":
            self.plan.run = value
            self.run_line = n
            if not model.RUN_RE.match(value):
                self.problem("error", "bad-run", n,
                             f"run '{value}' isn't allowed. Use 1 to 64 letters, digits, '.', '_' or '-', "
                             "such as 'run: beacon-0.1.0'.")
        elif k in model.HEADER_KEYS:
            setattr(self.plan, k, value)
        else:
            self.problem("warning", "unknown-key", n,
                         f"unknown header key '{key}:' (ignored). The header keys are run, mod, version and zip. "
                         "If this line is meant as introduction text, put a blank line between the header and it.")

    def setup_line(self, raw: str) -> None:
        bm = _BULLET_RE.match(raw)
        setup = self.plan.setup
        if bm:
            setup.append(bm.group(1))
        elif setup and (self.setup_open or _indented(raw)):
            setup[-1] = _join(setup[-1], raw.strip())
        else:
            setup.append(raw.strip())
        self.setup_open = True

    def heading(self, n: int, text: str) -> None:
        self.close_check()
        self.setup_open = False
        self.group = None
        if text.lower() == model.SETUP_TITLE:
            self.retarget(None)
            self.state = "setup"
            return
        gm = _GROUP_RE.match(text)
        if not gm:
            self.retarget(None)
            self.state = "ignore"
            self.problem("error", "group-no-number", n,
                         f"the heading '## {text}' has no group number. Start it with a whole number, "
                         f"such as '## 1 {text}', or make it '## Before you start'.")
            return
        num = int(gm.group(1))
        g = Group(number=num, title=(gm.group(2) or "").strip(), line=n)
        if num in self.group_lines:
            # parsed so its lines don't cause more problems, but kept off the page
            self.problem("error", "dup-group", n,
                         f"group number {num} is already used on line {self.group_lines[num]}. "
                         "Give this group a number no other group has.")
        else:
            self.group_lines[num] = n
            self.plan.groups.append(g)
        self.group = g
        self.state = "group"
        self.retarget(g)

    def new_check(self, n: int, step: str) -> None:
        self.close_check()
        g = self.group
        self.flush()
        pos = len(g.checks) + 1  # pinned checks still take their place, so later default ids don't move
        c = Check(id=f"{g.number}.{pos}", group=g.number, step=step.strip(), line=n)
        self.last_field = "step"
        g.checks.append(c)
        self.check = c
        self.lazy = True

    def check_line(self, n: int, text: str) -> None:
        c = self.check
        self.lazy = True
        km = _KEY_RE.match(text)
        if not km:
            # a wrapped line continues the field above it: the step, its Expect, its note or its log ids
            if self.last_field == "log":
                self.add_log_ids(c, text, n)
            else:
                setattr(c, self.last_field, _join(getattr(c, self.last_field), text))
            return
        key, value = km.group(1).lower(), (km.group(2) or "").strip()
        self.last_field = "step"
        if key == "expect":
            c.expect = _join(c.expect, value)
            self.last_field = "expect"
        elif key == "note":
            c.note = _join(c.note, value)
            self.last_field = "note"
        elif key == "smoke":
            v = value.lower()
            if v in _YES:
                c.smoke = True
            elif v in _NO:
                c.smoke = False
            else:
                self.problem("warning", "unknown-key", n,
                             f"'smoke: {value}' isn't yes or no, so this check stays out of the smoke test. "
                             "Write 'smoke: yes' or 'smoke: no'.")
        elif key == "log":
            self.add_log_ids(c, value, n)
            self.last_field = "log"
        elif key == "id":
            m = _ID_RE.match(value)
            if not m:
                self.problem("error", "bad-id", n,
                             f"id '{value}' isn't <group>.<number>. Write it like 'id: {c.group}.1', or remove the line.")
            elif int(m.group(1)) != c.group:
                self.problem("error", "bad-id", n,
                             f"id '{value}' doesn't start with this check's group number {c.group}. "
                             f"Write 'id: {c.group}.{int(m.group(2))}', or remove the line.")
            else:
                c.id = f"{int(m.group(1))}.{int(m.group(2))}"
                c.pinned = True
        else:
            self.problem("warning", "unknown-key", n,
                         f"unknown check key '{km.group(1)}:' (kept as part of the step text). The check keys are "
                         "Expect, smoke, log, note and id; reword the line if it isn't meant as one.")
            c.step = _join(c.step, text)

    def add_log_ids(self, c: Check, text: str, n: int) -> None:
        for rid in re.split(r"[,\s]+", text):
            if rid and rid not in c.log:
                c.log.append(rid)
                self.log_lines.append((rid, n))

    def close_check(self) -> None:
        self.check = None
        self.lazy = False

    # ---- whole-plan checks
    def finish(self) -> Plan:
        self.close_check()
        self.flush()
        p = self.plan
        if not p.title:
            self.problem("error", "no-title", 0, "the plan has no title. Make the first line '# <Mod> test plan'.")
        if not self.run_line:
            self.problem("error", "no-run", 0,
                         "the plan has no 'run:' line. Add one under the title, such as 'run: mymod-0.1.0' "
                         "(give each new build a new run).")
        for g in p.groups:
            if not g.checks:
                self.problem("warning", "empty-group", g.line,
                             f"group {g.number} has no checks. Add '- [ ] <step>' lines under it, or remove the heading.")
        checks = p.checks()
        if not checks:
            self.problem("error", "no-checks", 0,
                         "the plan has no checks. Add '- [ ] <step>' lines under a '## 1 <title>' group heading.")
        seen: dict[str, Check] = {}
        for c in checks:
            if c.id in seen:
                fix = "change this check's 'id:' line" if c.pinned else "pin a different id on one of them with 'id:'"
                self.problem("error", "dup-id", c.line,
                             f"check id {c.id} is already used by the check on line {seen[c.id].line}. "
                             f"Give one of them another id: {fix}.")
            else:
                seen[c.id] = c
        smoke = p.smoke()
        if len(smoke) > model.SMOKE_WARN:
            self.problem("warning", "big-smoke", smoke[model.SMOKE_WARN].line,
                         f"{len(smoke)} smoke checks; a smoke test works best with {model.SMOKE_WARN} or fewer. "
                         "Move the less important ones to the deep checks (remove 'smoke: yes').")
        if self.rule_ids is not None:
            known = ", ".join(sorted(self.rule_ids)) or "none"
            for rid, n in self.log_lines:
                if rid not in self.rule_ids:
                    self.problem("error", "unknown-log-id", n,
                                 f"log id '{rid}' isn't in the rule file (its ids: {known}). "
                                 "Fix the spelling, or add the rule to the rule file.")
        p.problems.sort(key=lambda x: x.line)
        log.debug("parsed %s: title %r, run %r, %d setup items, %d groups, %d checks (%d smoke), %d problems",
                  self.path, p.title, p.run, len(p.setup), len(p.groups), len(checks), len(smoke), len(p.problems))
        for g in p.groups:
            log.debug("  group %d %r (line %d): %s", g.number, g.title, g.line,
                      ", ".join(c.id + (" smoke" if c.smoke else "") for c in g.checks) or "no checks")
        for pr in p.problems:
            log.debug("  %s", pr.format(self.path))
        return p


def parse_text(text: str, path: str = "<plan>", rule_ids: set[str] | None = None) -> Plan:
    """Parse a plan. Never raises on plan mistakes: every one goes in Plan.problems (FORMAT.md table),
    with its line number. rule_ids (from --rules) turns on the unknown-log-id check."""
    p = _Parser(path, rule_ids)
    lines, unclosed = _lines(text)
    for n, raw, skip in lines:
        if not skip:
            p.feed(n, raw)
    if unclosed:
        p.problem("warning", "unclosed-comment", unclosed,
                  "this '<!--' comment never closes, so everything after it is ignored. Add '-->' where the "
                  "comment should end.")
    return p.finish()


def _read_text(path: str, what: str) -> str:
    if os.path.isdir(path):     # Windows reports a folder as "Permission denied", so look first
        raise SetupError(f"{path} is a folder, not a {what}. Give the file's path.")
    try:
        with open(path, "rb") as f:
            data = f.read()
    except FileNotFoundError:
        raise SetupError(f"can't find the {what} {path}. Check the name and the folder.")
    except IsADirectoryError:
        raise SetupError(f"{path} is a folder, not a {what}. Give the file's path.")
    except OSError as e:
        raise SetupError(f"can't read the {what} {path}: {e.strerror}. Check that the file exists and you can open it.")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError as e:
        line = data.count(b"\n", 0, e.start) + 1
        raise SetupError(f"{path} isn't UTF-8 text (a bad byte on line {line}). Save it as UTF-8 in your editor.")


def parse_file(path: str, rule_ids: set[str] | None = None) -> Plan:
    """Read a UTF-8 (BOM allowed) plan file and parse it. Raises model.SetupError if it can't be read."""
    text = _read_text(path, "plan")
    log.debug("read plan %s (%d characters)", path, len(text))
    return parse_text(text, path, rule_ids)


def load_rule_ids(rules_path: str) -> set[str]:
    """The expect and forbid ids of a papyrus-log-check rule file. Raises SetupError if unreadable."""
    text = _read_text(rules_path, "rule file")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        raise SetupError(f"{rules_path} isn't valid JSON (line {e.lineno}: {e.msg}). "
                         "Give the papyrus-log-check rule file (.json).")
    if not isinstance(data, dict):
        raise SetupError(f"{rules_path} isn't a papyrus-log-check rule file: it should be a JSON object "
                         "with 'expect' and 'forbid' lists.")
    ids: set[str] = set()
    for kind in ("expect", "forbid"):
        rules = data.get(kind, [])
        if not isinstance(rules, list):
            raise SetupError(f"{rules_path}: '{kind}' should be a list of rules. Check the rule file.")
        for r in rules:
            if isinstance(r, dict) and isinstance(r.get("id"), str) and r["id"]:
                ids.add(r["id"])
    log.debug("rule file %s: %d ids (%s)", rules_path, len(ids), ", ".join(sorted(ids)))
    return ids
