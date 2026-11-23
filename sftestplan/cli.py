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
            # backslashreplace: a path that isn't valid Unicode is written as \udcff, not a logging error
            fh = logging.FileHandler(log_file, mode="w", encoding="utf-8", errors="backslashreplace")
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
    protected = (args.plan, results.results_path(args.plan))
    hint = _free_name(_default_out(args.plan), protected)
    given = f"--out {out}" if args.out else f"The default page {out}"
    if _same_file(out, args.plan):
        raise SetupError(f"{given} is the plan itself. Give the page another name with --out, such as {hint}.")
    if _same_file(out, protected[1]):
        raise SetupError(f"{given} is the plan's results file. Give the page another name with --out, such as {hint}.")
    _refuse_linked_output(out, given, hint)
    if os.path.isdir(out):
        raise SetupError(f"{out} is a folder, not a page file. Give a file name with --out, such as {out}{os.sep}page.html.")
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
    out = args.out or os.path.splitext(args.report)[0] + ".marks.json"
    guarded = ((args.plan, "the plan"), (args.report, "the report"),
               (results.results_path(args.plan), "the plan's results file"))
    hint = _free_name(os.path.splitext(args.report)[0] + ".marks.json", [p for p, _ in guarded])
    given = f"--out {out}" if args.out else f"The default marks file {out}"
    for other, what in guarded:
        if _same_file(out, other):
            raise SetupError(f"{given} is {what} itself. Give the marks file another name with --out, such as {hint}.")
    _refuse_linked_output(out, given, hint)
    if os.path.isdir(out):     # before any output, so a refused run prints only its error
        raise SetupError(f"{out} is a folder, not a marks file. Give a file name with --out, such as {out}{os.sep}marks.json.")
    marks, lines = results.logs_to_marks(plan, report, args.mod, _now())
    for line in lines:
        print(line)
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(marks, f, indent=1)
    except OSError as e:
        raise SetupError(f"can't write {out}: {e.strerror}. Pick another --out.")
    print(f"Marks: {out} (open the page and use Import, or run: sf-test-plan import {out} --plan {args.plan})")
    return 0


def _strip_plan_ending(name: str) -> str:
    """name without a plan ending: ".testplan.md", else ".md" (either case). Other names stay whole."""
    for ending in (".testplan.md", ".md"):
        if name.lower().endswith(ending):
            return name[:-len(ending)]
    return name


def _default_rules_out(plan_path: str) -> str:
    return _strip_plan_ending(plan_path) + ".logrules.json"


_TEXT_ENDINGS = ("txt", "text", "markdown", "mdown", "mkd")


def _mod_from_path(path: str) -> str:
    """The mod name a plan's file name gives ("Beacon.testplan.md" -> "Beacon", "My.Mod.testplan.md" -> "My.Mod";
    0.3.2 keeps dots that are part of the name). A plain-text ending (.txt, .text, .markdown, .mdown, .mkd) is
    removed too ("plan.txt" -> "plan"); any other name stays whole ("Cool.Mod" -> "Cool.Mod"). A name that
    starts with a dot (".hidden", ".hidden.txt") gives "My Mod". A file name that isn't valid Unicode (Linux
    bytes, read as lone surrogates) loses those characters, since a plan or rule file is saved as UTF-8 and
    can't hold them (0.3.1). "My Mod" if nothing is left, as in the starter plan."""
    base = os.path.basename(path)
    name = _strip_plan_ending(base)
    if name == base:
        stem, dot, ext = base.rpartition(".")
        if dot and stem and ext.lower() in _TEXT_ENDINGS:
            name = stem
    if name.startswith("."):
        name = ""
    kept = " ".join(name.encode("utf-8", "ignore").decode("utf-8").split()) or "My Mod"
    log.debug("mod name %r from the file name %r (a plan ending, if there is one, is removed; characters that aren't valid Unicode "
              "and extra spaces are left out, and \"My Mod\" is used when nothing is left; give --mod or a mod: "
              "line to set it)", kept, base)
    return kept


def _count(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def _same_file(a: str, b: str) -> bool:
    """True when a and b are the same file: same real path, or (both exist) a hard link to one file.

    The hard-link test trusts file ids only when they are non-zero: some drives (certain network shares,
    RAM disks, \\\\wsl$ mounts) give every file the id 0, and os.path.samefile would call them all one file.
    """
    if os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b)):
        return True
    try:
        sa, sb = os.stat(a), os.stat(b)
    except (OSError, ValueError):
        return False
    return sa.st_ino != 0 and (sa.st_ino, sa.st_dev) == (sb.st_ino, sb.st_dev)


def _lstat(name: str) -> os.stat_result:
    """os.lstat, in one place so the tests can stand in for it."""
    return os.lstat(name)


def _is_link(name: str) -> bool:
    """os.path.islink, in one place so the tests can stand in for it."""
    return os.path.islink(name)


def _refuse_linked_output(out: str, given: str, hint: str) -> None:
    """build and logs: refuse an output that is a symbolic link (writing would replace the file it points to) or an
    existing file with another hard link (writing would change that other file too). Other Windows reparse points,
    such as OneDrive files, are ordinary files that Windows writes in place, so they aren't refused (0.3.2). On a
    drive that gives every file the id 0 a hard link can't be seen, so it isn't refused there."""
    if _is_link(out):
        raise SetupError(f"{given} is a symbolic link. Give the real file, or another name, with --out, such as {hint}.")
    try:
        st = _lstat(out)
    except (OSError, ValueError):
        return
    if stat.S_ISREG(st.st_mode) and st.st_ino != 0 and st.st_nlink > 1:
        raise SetupError(f"{given} has another hard link, so writing it would change that other file too. "
                         f"Give another name with --out, such as {hint}.")


def _plain_file(name: str) -> bool:
    """True when an existing name may be suggested for build or logs to overwrite: a regular file (not a folder or
    a symbolic link), with a file id that isn't 0 (on a drive that gives every file the id 0 a hard link can't be
    seen), no other hard link (build and logs refuse those), and not read-only (else following the hint would
    only fail). os.access checks only the read-only flag on Windows, not the file's permission lists."""
    try:
        st = _lstat(name)
    except (OSError, ValueError):
        return False
    if not stat.S_ISREG(st.st_mode) or st.st_ino == 0 or st.st_nlink != 1:
        return False
    return os.access(name, os.W_OK)


def _free_name(default: str, protected, skip_existing: bool = False) -> str:
    """A name for a refusal hint: default, else default with "-2", "-3" ... before its ending, the first that is
    not a protected file. With skip_existing (rules, which refuses an existing output without --force) it must
    not be on disk either, so following the hint never runs into "already exists". build and logs overwrite
    their output, so their hint keeps the usual default name when it is on disk but not protected, as long as
    _plain_file says following the hint is safe to overwrite and will work."""
    def free(name):
        if os.path.lexists(name) and (skip_existing or not _plain_file(name)):
            return False
        return not any(_same_file(name, p) for p in protected)
    if free(default):
        return default
    stem, ext = os.path.splitext(default)
    n = 2
    while not free(f"{stem}-{n}{ext}"):
        n += 1
    return f"{stem}-{n}{ext}"


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
    if args.from_file and not args.out and os.path.isdir(args.from_file):
        raise SetupError(f"--from {args.from_file} is a folder, not a rule file. Give the papyrus-log-check rule "
                         f"file (.json).")
    out = args.out or (args.from_file if args.from_file else _default_rules_out(args.plan))
    protected = (args.plan, results.results_path(args.plan))
    hint = _free_name(_default_rules_out(args.plan), protected, skip_existing=True)
    # Without --out the rule file is the --from file, so a refusal names the option the path came from.
    if args.out:
        given, fix = f"--out {out}", "Give the rule file another name with --out"
    elif args.from_file:
        given = f"--from {out}"
        fix = "Without --out, the rule file is written back to the --from file, so give the rule file another name with --out"
    else:
        given, fix = f"The default rule file {out}", "Give the rule file another name with --out"
    if _same_file(out, args.plan):
        raise SetupError(f"{given} is the plan itself. {fix}, such as {hint}.")
    if _same_file(out, protected[1]):
        raise SetupError(f"{given} is the plan's results file. {fix}, such as {hint}.")
    if os.path.isdir(out):
        raise SetupError(f"{out} is a folder, not a rule file. Give a file name with --out, such as "
                         f"{out}{os.sep}rules.json.")
    n_steps = len({cid for steps in uses.values() for cid, _ in steps})
    counts = f"{args.plan}: {_count(len(uses), 'log id')} on {_count(n_steps, 'step')}"
    if not uses:
        print(counts)
        print("No step has a 'log:' line, so there is nothing to write. Add 'log: <id>' under the steps the "
              "mod's log can prove, then run this again.")
        return 0
    base = None
    if args.from_file:
        base = results._load_json(args.from_file, "Give the papyrus-log-check rule file (.json).")
    mod = plan.mod or _mod_from_path(args.plan)
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
    old_prefix = base.get("prefix") if base is not None else None
    prefix_changed = base is not None and args.prefix is not None and old_prefix != data["prefix"]
    kept_line = (f"Already in {args.from_file}: {len(uses) - len(added)} of the {_count(len(uses), 'id')}."
                 if base is not None else None)
    if base is not None and not added and not prefix_changed:
        print(counts)
        print(kept_line)
        print("Nothing to add, so nothing was written.")
        return 0
    # The output file itself is never a link: replacing a link's target (or the link) is a surprise either way.
    # Checked only when something will be written, so a linked --from file with nothing to add still exits 0.
    # Both refusals come before any output, so a refused run prints only its error (0.3.1).
    if _is_link(out):
        raise SetupError(f"{given} is a symbolic link. {fix}, such as {hint}, or give the real file with --out.")
    if os.path.lexists(out) and not args.force:
        if base is not None and _same_file(out, args.from_file):
            hint = "add --force to add the new rules to it" if added else "add --force to update its prefix"
        else:
            hint = "pick another --out, or add --force to replace it"
        raise SetupError(f"{out} already exists: {hint}.")
    print(counts)
    if kept_line is not None:
        print(kept_line)
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
    if os.path.isdir(args.plan):
        raise SetupError(f"{args.plan} is a folder, not a plan file. Give a file name, such as "
                         f"{args.plan}{os.sep}MyMod.testplan.md.")
    if os.path.exists(args.plan) and not args.force:
        raise SetupError(f"{args.plan} already exists. Pick another name, or add --force to replace it.")
    mod = args.mod or _mod_from_path(args.plan)
    try:
        mod.encode("utf-8")       # checked before the file is opened, so a refused run never empties a plan
    except UnicodeError as e:
        raise SetupError(f"--mod holds text that can't be saved as UTF-8 ({e.reason}). Give the mod's name in "
                         f"plain text. Nothing was written.")
    text = results.starter_plan(mod)
    try:
        text.encode("utf-8")      # and the whole text, in case the starter ever adds text from elsewhere
    except UnicodeError as e:
        raise SetupError(f"the starter plan holds text that can't be saved as UTF-8 ({e.reason}). Nothing was "
                         f"written.")
    try:
        with open(args.plan, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    except OSError as e:
        raise SetupError(f"can't write {args.plan}: {e.strerror}. Check that the folder exists and you can write to it, or pick another name.")
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
