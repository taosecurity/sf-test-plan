"""The shared New Game+ plan (FORMAT.md rule 14 and section 8): the base plan's crossing checks, then one group per
mod that has its own `## New Game+` checks, with group numbers fixed by an order file so saved marks never move."""
from __future__ import annotations

import json
import logging
import os

from .model import Check, Plan, SetupError
from .results import _load_json

log = logging.getLogger("sf-test-plan")

SKIP_LINE = "Skip this group if the mod isn't installed."


def load_order(path: str) -> list[str]:
    """The order file: a JSON list of mod names, each once. A missing file is an empty list (it is written later)."""
    if not os.path.lexists(path):
        log.debug("no order file %s yet: every mod is new", path)
        return []
    fix = 'It should be a JSON list of mod names, such as ["Beacon", "Lantern"].'
    data = _load_json(path, fix)
    if not isinstance(data, list) or not all(isinstance(x, str) and x.strip() for x in data):
        raise SetupError(f"the order file {path} isn't a list of mod names. {fix}")
    names = [" ".join(x.split()) for x in data]
    seen: set[str] = set()
    for x in names:
        if x in seen:
            raise SetupError(f"the order file {path} lists the mod {json.dumps(x)} twice. Remove one of them: each "
                             "mod keeps one place, so its group number never changes.")
        seen.add(x)
    log.debug("order file %s: %d mods", path, len(names))
    return names


def mod_name(plan: Plan) -> str:
    return " ".join(plan.mod.split())


def _check_md(c: Check, keep_id: bool, keep_smoke: bool) -> list[str]:
    out = [f"- [ ] {c.step}".rstrip()]
    for key, value in (("Expect", c.expect), ("note", c.note), ("logcheck", c.logcheck)):
        if value:
            out.append(f"  {key}: {value}")
    if c.log:
        out.append("  log: " + ", ".join(c.log))
    if keep_smoke and c.smoke:
        out.append("  smoke: yes")
    if keep_id and c.pinned:
        out.append(f"  id: {c.id}")
    return out


def _paras(text: str) -> list[str]:
    out: list[str] = []
    for p in (text or "").split("\n\n"):
        if p.strip():
            out += [p.strip(), ""]
    return out


def shared_plan(base: Plan, mods: list[Plan], order: list[str]) -> tuple[str, list[str], list[tuple[str, int, int]]]:
    """The shared plan's Markdown, the new order list (new mods appended) and, for each mod plan, (name, group
    number, number of NG+ checks). mods must have unique, non-empty mod names (the caller checks)."""
    new_order = list(order)
    for p in mods:
        if mod_name(p) not in new_order:
            new_order.append(mod_name(p))
    top = max(g.number for g in base.groups)
    place = {name: i for i, name in enumerate(new_order, 1)}
    out = [f"# {base.title}", f"run: {base.run}"]
    out += [f"{k}: {getattr(base, k)}" for k in ("mod", "version", "zip") if getattr(base, k)]
    out.append("")
    n = len(mods)
    out += _paras(base.intro)
    out += [f"This page covers {n} mod{'' if n == 1 else 's'}.", ""]
    if base.setup:
        out += ["## Before you start"] + [f"- {s}" for s in base.setup] + [""]
    for g in base.groups:
        out += [f"## {g.number} {g.title}".rstrip(), ""] + _paras(g.intro)
        for c in g.checks:
            out += _check_md(c, True, True)
        out.append("")
    summary = []
    for p in sorted(mods, key=lambda p: place[mod_name(p)]):
        num = top + place[mod_name(p)]
        summary.append((mod_name(p), num, len(p.ngplus_checks)))
        if not p.ngplus_checks:
            continue
        out += [f"## {num} {mod_name(p)}", "", SKIP_LINE, ""] + _paras(p.ngplus_intro)
        for c in p.ngplus_checks:
            out += _check_md(c, False, False)
        out.append("")
    if base.log_checks:
        out += ["## Log checks", ""] + _paras(base.log_intro)
        for c in base.log_checks:
            out += _check_md(c, True, False)
        out.append("")
    return "\n".join(out).rstrip("\n") + "\n", new_order, summary
