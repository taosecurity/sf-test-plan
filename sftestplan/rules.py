"""Starter papyrus-log-check rule files from a plan's `log:` ids (FORMAT.md 6).

The `rules` command uses this, and so can other tools (such as a log-review script): `plan_log_uses` lists the ids a
plan's steps name, `starter_rules` makes a rule file object from any list of ids (it needs no Plan), and `dumps`
writes it in the one-rule-per-line layout of papyrus-log-check's own examples. Nothing here reads or writes files.
"""
from __future__ import annotations

import json
import logging
import re

from .model import Plan, SetupError
from .results import plain_text

log = logging.getLogger("sf-test-plan")

# Characters with a meaning in a Python regex. Spaces, colons and dashes are left as they are, so a starter
# pattern stays readable ("BeaconMod: placed", not "BeaconMod:\ placed").
_REGEX_SPECIAL = re.compile(r"([\\.^$*+?{}\[\]|()])")


def regex_text(s: str) -> str:
    """s as a regex that matches exactly s."""
    return _REGEX_SPECIAL.sub(r"\\\1", s)


def default_tag(mod: str) -> str:
    """The mod name with only letters and digits kept ("Beacon Mod" -> "BeaconMod"); "MyMod" if nothing is left."""
    return re.sub(r"[^A-Za-z0-9]", "", mod or "") or "MyMod"


def plan_log_uses(plan: Plan) -> dict[str, list[tuple[str, str]]]:
    """Each `log:` id in the plan, in file order, with the steps that name it: {id: [(check id, plain step text)]}."""
    uses: dict[str, list[tuple[str, str]]] = {}
    for c in plan.checks():
        for rid in c.log:
            uses.setdefault(rid, []).append((c.id, plain_text(c.step)))
    return uses


def _means(steps: list[tuple[str, str]]) -> str:
    return "; ".join(f"Step {cid}: {text}" for cid, text in steps)


def _rule_list(data: dict, kind: str, where: str) -> list:
    rules = data.get(kind, [])
    if not isinstance(rules, list):
        raise SetupError(f"{where}: '{kind}' should be a list of rules. Check the rule file.")
    return rules


def starter_rules(mod: str, version: str, uses: dict[str, list[tuple[str, str]]], *, prefix: str | None = None,
                  plugins: list[str] | None = None, base: dict | None = None,
                  base_name: str = "the rule file") -> tuple[dict, list[str]]:
    """A papyrus-log-check rule file object with an `expect` rule for every id in uses that it doesn't hold yet.

    prefix is the literal text the mod's log lines start with (default: the mod name's letters and digits plus ':').
    Each new rule's `re` is the prefix and the id ("BeaconMod: placed"): a starting point the author edits to match
    the real line. With base (an existing rule file object), its fields and rules are kept as they are, and only ids
    in neither its `expect` nor its `forbid` are added. Returns (rule file object, ids added). Raises SetupError when
    base has the wrong shape.
    """
    tag = default_tag(mod)
    lead = prefix if prefix is not None else tag + ":"
    if base is None:
        data: dict = {"mod": mod, "version": version, "plugins": list(plugins) if plugins else [tag + ".esm"],
                      "prefix": regex_text(lead), "expect": [], "forbid": []}
    else:
        if not isinstance(base, dict):
            raise SetupError(f"{base_name} isn't a papyrus-log-check rule file: it should be a JSON object "
                             "with 'expect' and 'forbid' lists.")
        data = dict(base)
        _rule_list(data, "forbid", base_name)
        data["expect"] = list(_rule_list(data, "expect", base_name))
        data.setdefault("forbid", [])
        if prefix is None and isinstance(data.get("prefix"), str):
            # The file's prefix is a regex. It leads new patterns only when it matches one fixed text (plain
            # characters, or special ones escaped the way regex_text does); "\\s" or "(A|B)" fall back to the tag.
            literal = re.sub(r"\\(.)", r"\1", data["prefix"])
            if data["prefix"] and regex_text(literal) == data["prefix"]:
                lead = literal
    have = {r.get("id") for kind in ("expect", "forbid") for r in data[kind] if isinstance(r, dict)}
    added = []
    for rid, steps in uses.items():
        if rid in have:
            log.debug("log id %r is already in %s", rid, base_name)
            continue
        pattern = regex_text(lead.rstrip() + " " + rid)
        data["expect"].append({"id": rid, "re": pattern, "means": _means(steps)})
        added.append(rid)
        log.debug("log id %r: new expect rule, re %r, from step(s) %s", rid, pattern, ", ".join(c for c, _ in steps))
    return data, added


def dumps(data: dict) -> str:
    """JSON text with one top-level field per line and one rule per line (like papyrus-log-check's examples)."""
    lines = []
    items = list(data.items())
    for i, (key, value) in enumerate(items):
        comma = "," if i < len(items) - 1 else ""
        k = json.dumps(key, ensure_ascii=False)
        if isinstance(value, list) and value and all(isinstance(v, dict) for v in value):
            inner = [" " + " " + json.dumps(v, ensure_ascii=False) for v in value]
            lines.append(f" {k}: [")
            lines.append(",\n".join(inner))
            lines.append(f" ]{comma}")
        else:
            lines.append(f" {k}: {json.dumps(value, ensure_ascii=False)}{comma}")
    return "{\n" + "\n".join(lines) + "\n}\n"
