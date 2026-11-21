"""Command line (master-owned). Exit codes: 0 OK, 1 plan errors (check/build), 2 bad input or setup."""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import logging
import os
import stat
import sys
import tempfile

from . import model, parse, render, results, rules
from .model import SetupError

log = logging.getLogger("sf-test-plan")


def _setup_logging(verbose: bool, log_file: str | None) -> None:
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    if verbose:
        h = logging.StreamHandler(sys.stderr)
        h.setLevel(logging.DEBUG)
        h.setFormatter(logging.Formatter("[verbose] %(message)s"))
        log.addHandler(h)
    if log_file:
        try:
            fh = logging.FileHandler(log_file, mode="w", encoding="utf-8")
        except OSError as e:
            raise SetupError(f"can't write the log file {log_file}: {e.strerror}. Pick a folder you can write to.")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        log.addHandler(fh)
    if not log.handlers:
        log.addHandler(logging.NullHandler())
    log.debug("%s, Python %s, args %s", model.TOOL_ID, sys.version.split()[0], sys.argv[1:])


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _report(plan: model.Plan) -> int:
    for p in plan.problems:
        print(p.format(plan.path))
    n_err = len(plan.errors())
    n_warn = len(plan.problems) - n_err
    checks = plan.checks()
    print(f"{plan.path}: {len(plan.groups)} groups, {len(checks)} checks, {len(plan.smoke())} smoke; "
          f"{n_err} errors, {n_warn} warnings")
    return 1 if n_err else 0


def _rule_ids(args) -> set[str] | None:
    return parse.load_rule_ids(args.rules) if getattr(args, "rules", None) else None


def cmd_check(args) -> int:
    plan = parse.parse_file(args.plan, _rule_ids(args))
    return _report(plan)


def cmd_build(args) -> int:
    plan = parse.parse_file(args.plan, _rule_ids(args))
    code = _report(plan)
    if code:
        print("No page written: fix the errors above first.")
        return code
    rows = results.load_results(args.plan)
    out = args.out or _default_out(args.plan)
    html = render.render(plan, rows)
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
    except OSError as e:
        raise SetupError(f"can't write {out}: {e.strerror}. Pick another --out.")
    log.debug("wrote %s (%d bytes)", out, len(html))
    print(f"Page: {out}")
    return 0


def _default_out(plan_path: str) -> str:
    base = plan_path[:-3] if plan_path.lower().endswith(".md") else plan_path
    return base + ".html"


def cmd_import(args) -> int:
    plan = parse.parse_file(args.plan)
    if plan.errors():
        return _report(plan)
    marks = results.read_marks(args.marks)
    if marks.get("run") != plan.run:
        print(f"Note: the marks are for run {marks.get('run')!r}; the plan's run is {plan.run!r}.")
    row = results.summarize(plan, marks, _dt.date.today().isoformat())
    path = results.add_result(args.plan, row)
    print(f"{row['test']}: {row['happened']}")
    if row.get("notes"):
        print(row["notes"])
    print(f"Results: {path} (rebuild the page to show it)")
    return 0


def cmd_logs(args) -> int:
    plan = parse.parse_file(args.plan)
    if plan.errors():
        return _report(plan)
    report = results._load_json(args.report, "Give the .json report papyrus-log-check wrote.")
    marks, lines = results.logs_to_marks(plan, report, args.mod, _now())
    for line in lines:
        print(line)
    out = args.out or os.path.splitext(args.report)[0] + ".marks.json"
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(marks, f, indent=1)
    except OSError as e:
        raise SetupError(f"can't write {out}: {e.strerror}. Pick another --out.")
    print(f"Marks: {out} (open the page and use Import, or run: sf-test-plan import {out} --plan {args.plan})")
    return 0


def _default_rules_out(plan_path: str) -> str:
    base = plan_path
    for ending in (".testplan.md", ".md"):
        if base.lower().endswith(ending):
            base = base[:-len(ending)]
            break
    return base + ".logrules.json"


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _same_file(a: str, b: str) -> bool:
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _ascii(s: str) -> str:
    """s for printing: JSON-escaped to ASCII, so no console encoding can fail on it (no quotes added)."""
    return json.dumps(s)[1:-1]


def _remove_temp(tmp: str) -> None:
    try:
        os.remove(tmp)
    except OSError:
        try:                       # a read-only temp file can't be removed on Windows: clear the flag, try once more
            os.chmod(tmp, stat.S_IWRITE)
            os.remove(tmp)
        except OSError as e:
            log.debug("couldn't remove the temp file %s: %s", tmp, e)


def _write_atomic(path: str, text: str, fix: str) -> None:
    """Write text to a temp file in path's folder, then move it over path, so a failed write leaves path as it was.

    An existing file's permission bits are put back on the new file after the move. path must not be a link
    (cmd_rules refuses links before this).
    """
    try:
        old_mode = stat.S_IMODE(os.stat(path).st_mode)
    except OSError:
        old_mode = None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix=".rules-", suffix=".tmp", dir=os.path.dirname(os.path.abspath(path)))
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        os.replace(tmp, path)
        tmp = None
    except OSError as e:
        raise SetupError(f"can't write {path}: {e.strerror or e}. {fix}")
    finally:
        if tmp is not None:
            _remove_temp(tmp)
    if old_mode is not None:
        try:
            os.chmod(path, old_mode)
        except OSError as e:
            print(f"Note: {path} was written, but its old permissions couldn't be put back ({e.strerror or e}).")


def cmd_rules(args) -> int:
    if args.prefix is not None:
        args.prefix = args.prefix.strip()
        if not args.prefix:
            raise SetupError("--prefix is empty. Give the text your mod's log lines start with, such as "
                             "--prefix \"MYMOD:\".")
    if args.from_file and args.plugin:
        raise SetupError("--plugin can't be used with --from: --from keeps the rule file's own 'plugins' list. "
                         "Edit 'plugins' in that file instead, or leave out --from to start a new file.")
    plan = parse.parse_file(args.plan)
    if plan.errors():
        return _report(plan)
    uses = rules.plan_log_uses(plan)
    n_steps = len({cid for steps in uses.values() for cid, _ in steps})
    counts = f"{args.plan}: {_count(len(uses), 'log id')} on {_count(n_steps, 'step')}"
    if not uses:
        print(counts)
        print("No step has a 'log:' line, so there is nothing to write. Add 'log: <id>' under the steps the "
              "mod's log can prove, then run this again.")
        return 0
    out = args.out or (args.from_file if args.from_file else _default_rules_out(args.plan))
    # Links are never followed: replacing a link's target (or the link) is a surprise either way.
    if os.path.islink(out):
        raise SetupError(f"{out} is a link; give the real file with --out.")
    if _same_file(out, args.plan):
        raise SetupError(f"--out {out} is the plan itself. Give the rule file another name, such as "
                         f"{_default_rules_out(args.plan)}.")
    base = None
    if args.from_file:
        base = results._load_json(args.from_file, "Give the papyrus-log-check rule file (.json).")
    mod = plan.mod or os.path.basename(args.plan).split(".")[0]
    data, added = rules.starter_rules(mod, plan.version, uses, prefix=args.prefix, plugins=args.plugin,
                                      base=base, base_name=args.from_file or "the rule file")
    text = rules.dumps(data)
    try:
        text.encode("utf-8")
    except UnicodeError as e:
        source = (f"the --from file {args.from_file}" if args.from_file
                  else f"--prefix or the plan {args.plan}")
        raise SetupError(f"the rule file would hold text that can't be saved as UTF-8 ({e.reason}). It comes from "
                         f"{source}: look for a broken escape such as a lone \\ud800. Nothing was written.")
    print(counts)
    old_prefix = base.get("prefix") if base is not None else None
    prefix_changed = base is not None and args.prefix is not None and old_prefix != data["prefix"]
    if base is not None:
        kept = len(uses) - len(added)
        print(f"Already in {args.from_file}: {kept} of the {_count(len(uses), 'id')}.")
        if not added and not prefix_changed:
            print("Nothing to add, so nothing was written.")
            return 0
    if os.path.lexists(out) and not args.force:
        if base is not None and _same_file(out, args.from_file):
            hint = "add --force to add the new rules to it" if added else "add --force to update its prefix"
        else:
            hint = "pick another --out, or add --force to replace it"
        raise SetupError(f"{out} already exists: {hint}.")
    if prefix_changed:
        new = json.dumps(data["prefix"])
        if isinstance(old_prefix, str) and old_prefix:
            print(f"Note: the file's prefix changed from {json.dumps(old_prefix)} to {new} "
                  "(from --prefix). Rules already in the file are kept as they are.")
        else:
            print(f"Note: set the file's prefix to {new} (from --prefix). Rules already in the file are kept as "
                  "they are.")
        if not added:
            print("No ids were missing, so only the prefix changed.")
    elif base is not None and args.prefix is None and rules.literal_prefix(old_prefix) is None:
        tag = rules.default_tag(mod) + ":"
        what = (f"prefix {json.dumps(old_prefix)} isn't one fixed text"
                if isinstance(old_prefix, str) and old_prefix else "has no 'prefix' text")
        print(f"WARNING: the file's {what}, so the new patterns start with {json.dumps(tag)} "
              "instead. Give --prefix with the text your mod's log lines start with to use that.")
    for r in added:
        steps = ", ".join(cid for cid, _ in uses[r["id"]])
        print(f"New expect rule '{_ascii(r['id'])}' (step {steps}): re {json.dumps(r['re'])}")
    _write_atomic(out, text, "The old file, if any, is unchanged. Pick another --out, or check the folder is writable.")
    log.debug("wrote %s (%d bytes, %d new rules)", out, len(text), len(added))
    print(f"Rule file: {out}. Edit each new 're' to match the line your mod writes, and move a rule for a line "
          f"that must never appear to 'forbid'. Then run: sf-test-plan check {args.plan} --rules {out}")
    return 0


def cmd_new(args) -> int:
    if os.path.exists(args.plan) and not args.force:
        raise SetupError(f"{args.plan} already exists. Pick another name, or add --force to replace it.")
    mod = args.mod or os.path.basename(args.plan).split(".")[0]
    text = results.starter_plan(mod)
    try:
        with open(args.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except OSError as e:
        raise SetupError(f"can't write {args.plan}: {e.strerror}.")
    print(f"Starter plan: {args.plan}. Edit it, then run: sf-test-plan build {args.plan}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=model.TOOL, description="Turn a Markdown test plan into a checklist page you tick off while playing.")
    p.add_argument("--version", action="version", version=model.TOOL_ID)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--verbose", action="store_true", help="say what was read and decided, on stderr")
    common.add_argument("--log", metavar="FILE", help="write the same details to FILE")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build", parents=[common], help="write the checklist page")
    b.add_argument("plan")
    b.add_argument("--out", metavar="FILE", help="page path (default: the plan's name with .html)")
    b.add_argument("--rules", metavar="FILE", help="papyrus-log-check rule file: check the log: ids against it")
    b.set_defaults(func=cmd_build)

    c = sub.add_parser("check", parents=[common], help="check the plan for mistakes, without writing a page")
    c.add_argument("plan")
    c.add_argument("--rules", metavar="FILE", help="papyrus-log-check rule file: check the log: ids against it")
    c.set_defaults(func=cmd_check)

    i = sub.add_parser("import", parents=[common], help="add a marks file from the page to the plan's results file")
    i.add_argument("marks")
    i.add_argument("--plan", required=True)
    i.set_defaults(func=cmd_import)

    lg = sub.add_parser("logs", parents=[common], help="turn a papyrus-log-check JSON report into marks for log: checks")
    lg.add_argument("report")
    lg.add_argument("--plan", required=True)
    lg.add_argument("--mod", help="the mod's name in the report, when it holds several")
    lg.add_argument("--out", metavar="FILE", help="marks file (default: <report>.marks.json)")
    lg.set_defaults(func=cmd_logs)

    r = sub.add_parser("rules", parents=[common],
                       help="write a starter papyrus-log-check rule file from the plan's log: ids")
    r.add_argument("plan")
    r.add_argument("--out", metavar="FILE",
                   help="rule file to write (default: --from's file, else <plan name>.logrules.json)")
    r.add_argument("--from", dest="from_file", metavar="FILE",
                   help="an existing rule file: keep its rules and add only the log: ids it lacks")
    r.add_argument("--prefix", metavar="TEXT",
                   help="the text the mod's log lines start with (default: the mod name's letters and digits, then "
                        "':'; with --from, the file's prefix, and --prefix replaces it)")
    r.add_argument("--plugin", action="append", metavar="NAME",
                   help="the mod's plugin file, such as MyMod.esm (repeat for several; default <mod name>.esm; "
                        "not with --from, which keeps the file's plugins)")
    r.add_argument("--force", action="store_true", help="replace or update an existing file")
    r.set_defaults(func=cmd_rules)

    n = sub.add_parser("new", parents=[common], help="write a starter plan")
    n.add_argument("plan")
    n.add_argument("--mod", help="the mod's name (default: from the file name)")
    n.add_argument("--force", action="store_true", help="replace an existing file")
    n.set_defaults(func=cmd_new)
    return p


def _utf8_output() -> None:
    """Notes, run names and step text can hold any character. A Windows console or pipe defaults to cp1252, where
    printing them would crash, so write UTF-8 and replace what the stream can't show."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_output()
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as e:
        return 0 if e.code == 0 else 2
    try:
        _setup_logging(args.verbose, args.log)
        return args.func(args)
    except SetupError as e:
        log.debug("setup error: %s", e)
        print(f"sf-test-plan: {e}", file=sys.stderr)
        return 2
    except Exception as e:  # noqa: BLE001 - an unexpected failure still gets exit 2 and a readable message
        log.exception("unexpected error")
        print(f"sf-test-plan: unexpected error: {type(e).__name__}: {e}. Run again with --log sf-test-plan.log and "
              "report it with that file at " + model.URL + "/issues", file=sys.stderr)
        return 2
    finally:
        for h in list(log.handlers):
            h.close()
            log.removeHandler(h)
