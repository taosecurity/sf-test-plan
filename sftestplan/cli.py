"""Command line (master-owned). Exit codes: 0 OK, 1 plan errors (check/build), 2 bad input or setup."""
from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import json
import logging
import os
import re
import shlex
import stat
import sys
import tempfile

from . import builds, model, ngplus, parse, render, results, rules, style
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


def _parse_with_style(args, rule_ids: set[str] | None) -> model.Plan:
    """Parse the plan; with --style, also apply the style file's rules (a bad style file is exit 2 before parsing)."""
    st = style.load_style(args.style) if getattr(args, "style", None) else None
    text = parse._read_text(args.plan, "plan")
    log.debug("read plan %s (%d characters)", args.plan, len(text))
    plan = parse.parse_text(text, args.plan, rule_ids)
    if st is not None:
        style.apply(plan, text, st)
    return plan


def cmd_check(args) -> int:
    plan = _parse_with_style(args, _rule_ids(args))
    return _report(plan)


def _load_for_page(args):
    """Parse the plan (with --rules and --style) and report it. Returns (plan, rule_file, exit code)."""
    rule_file = parse.load_rule_file(args.rules) if args.rules else None
    plan = _parse_with_style(args, parse.rule_ids_of(rule_file, args.rules) if rule_file is not None else None)
    code = _report(plan)
    if code:
        print("No page written: fix the errors above first.")
    return plan, rule_file, code


def _refuse_input_as_output(args, out: str, given: str, fix: str) -> None:
    """An output must never be the plan, its results file, the --rules file or the --style file."""
    for other, what in ((args.plan, "the plan itself"), (results.results_path(args.plan), "the plan's results file"),
                        (getattr(args, "rules", None), "the --rules file"),
                        (getattr(args, "style", None), "the --style file")):
        if other and _same_file(out, other):
            raise SetupError(f"{given} is {what}. {fix}.")


def _check_page_out(args, out: str, given: str) -> None:
    fix = "Give the page another name with --out"
    _refuse_input_as_output(args, out, given, fix)
    if os.path.isdir(out):
        raise SetupError(f"{out} is a folder, not a page file. Give a file name with --out, such as {out}{os.sep}page.html.")
    _refuse_unsafe_output(out, given, fix)


def _write_page(out: str, html: str) -> None:
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
    except OSError as e:
        raise SetupError(f"can't write {out}: {e.strerror}. Pick another --out.")
    log.debug("wrote %s (%d bytes)", out, len(html))


def cmd_build(args) -> int:
    plan, rule_file, code = _load_for_page(args)
    if code:
        return code
    rows = results.load_results(args.plan)
    out = args.out or _default_out(args.plan)
    _check_page_out(args, out, f"--out {out}" if args.out else f"The default page {out}")
    _write_page(out, render.render(plan, rows, rule_file))
    print(f"Page: {out}")
    return 0


def _plan_assets(args) -> list[tuple[str, bytes, bool]]:
    """The --assets files to write: (path, bytes, already the same). All refusals come before anything is written."""
    folder = args.assets
    if os.path.lexists(folder) and not os.path.isdir(folder):
        raise SetupError(f"--assets {folder} isn't a folder. Give a folder for sf-test-plan.js and sf-test-plan.css.")
    todo = []
    for name, source in render.HOST_ASSETS:
        path = os.path.join(folder, name)
        data = render.asset_bytes(source)
        given, fix = f"--assets file {path}", "Give another folder with --assets"
        _refuse_input_as_output(args, path, given, fix)
        if args.out and _same_file(path, args.out):
            raise SetupError(f"--out {args.out} is the {given}. Give the page another name with --out.")
        if os.path.isdir(path):
            raise SetupError(f"{given} is a folder, so nothing was written. {fix}.")
        _refuse_unsafe_output(path, given, fix)
        same = False
        if os.path.lexists(path):
            try:
                with open(path, "rb") as f:
                    same = f.read() == data
            except OSError as e:
                raise SetupError(f"can't read {path}: {e.strerror}. {fix}.")
            if not same and not args.force:
                raise SetupError(f"{path} already exists with other contents: add --force to replace it, or "
                                 "give another folder with --assets. Nothing was written.")
        todo.append((path, data, same))
    return todo


def cmd_render(args) -> int:
    to_stdout = not args.out
    if to_stdout:   # the report goes to stderr, so the page on stdout can be piped
        with contextlib.redirect_stdout(sys.stderr):
            plan, rule_file, code = _load_for_page(args)
    else:
        plan, rule_file, code = _load_for_page(args)
    if code:
        return code
    rows = results.load_results(args.plan)
    if args.out:
        _check_page_out(args, args.out, f"--out {args.out}")
    assets = _plan_assets(args) if args.assets else []
    html = render.render(plan, rows, rule_file, fragment=args.fragment)
    note = sys.stderr if to_stdout else sys.stdout
    if assets:
        try:
            os.makedirs(args.assets, exist_ok=True)
        except OSError as e:
            raise SetupError(f"can't make the folder {args.assets}: {e.strerror}. Give another folder with --assets.")
        for path, data, same in assets:
            if same:
                print(f"Unchanged: {path}", file=note)
                continue
            try:
                with open(path, "wb") as f:
                    f.write(data)
            except OSError as e:
                raise SetupError(f"can't write {path}: {e.strerror}. Give another folder with --assets.")
            print(f"Wrote: {path}", file=note)
    if to_stdout:   # bytes, so the page piped to a file is the same as --out's (no \r\n on Windows)
        sys.stdout.flush()
        buf = getattr(sys.stdout, "buffer", None)
        if buf is not None:
            buf.write(html.encode("utf-8", "replace"))
            buf.flush()
        else:
            sys.stdout.write(html)
    else:
        _write_page(args.out, html)
        print(f"{'Fragment' if args.fragment else 'Page'}: {args.out}")
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
    given = f"--out {out}" if args.out else f"The default marks file {out}"
    fix = "Give the marks file another name with --out"
    for other, what in guarded:
        if _same_file(out, other):
            raise SetupError(f"{given} is {what} itself. {fix}.")
    # All refusals come before any output, so a refused run prints only its error.
    if os.path.isdir(out):
        raise SetupError(f"{out} is a folder, not a marks file. Give a file name with --out, such as {out}{os.sep}marks.json.")
    _refuse_unsafe_output(out, given, fix)
    marks, lines = results.logs_to_marks(plan, report, args.mod, _now())
    for line in lines:
        print(line)
    try:
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            json.dump(marks, f, indent=1)
    except OSError as e:
        raise SetupError(f"can't write {out}: {e.strerror}. Pick another --out.")
    print(f"Marks: {out} (open the page and use Import, or run: sf-test-plan import {_q(out)} --plan {_q(args.plan)})")
    return 0


_PLAIN_ARG = re.compile(r"^[A-Za-z0-9_./\\:+=@%,-]+$")


def _q(path: str, windows: bool | None = None) -> str:
    """path for a printed command line: as it is when it is plain, else quoted so it can be pasted as is (double
    quotes on Windows, single quotes elsewhere)."""
    if _PLAIN_ARG.match(path):
        return path
    if windows if windows is not None else os.name == "nt":
        return '"' + path.replace('"', '\\"') + '"'
    return shlex.quote(path)


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
    removed too ("plan.txt" -> "plan", "Beacon.testplan.txt" -> "Beacon"); any other name stays whole ("Cool.Mod" -> "Cool.Mod"). A name that
    starts with a dot (".hidden", ".hidden.txt") gives "My Mod". A file name that isn't valid Unicode (Linux
    bytes, read as lone surrogates) loses those characters, since a plan or rule file is saved as UTF-8 and
    can't hold them (0.3.1). "My Mod" if nothing is left, as in the starter plan."""
    base = os.path.basename(path)
    name = _strip_plan_ending(base)
    if name == base:
        stem, dot, ext = base.rpartition(".")
        if dot and stem and ext.lower() in _TEXT_ENDINGS:
            name = stem[:-len(".testplan")] if stem.lower().endswith(".testplan") else stem
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
    return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))


def _is_link(name: str) -> bool:
    """os.path.islink, in one place so the tests can stand in for it."""
    return os.path.islink(name)


def _refuse_unsafe_output(out: str, given: str, fix: str) -> None:
    """Refuse an output this command must not write: a symbolic link (writing would change the file it points to,
    or replace the link), or an existing name that isn't a regular file or is read-only. A missing name, or an
    existing regular file that isn't read-only (OneDrive files included), is fine, and so is the null device
    (NUL, /dev/null). Folders get their own message before this is called. It prints nothing itself."""
    if os.path.normcase(out) == os.path.normcase(os.devnull):
        return
    if _is_link(out):
        raise SetupError(f"{given} is a symbolic link, so nothing was written. {fix}.")
    if not os.path.lexists(out):
        return
    if not os.path.isfile(out):
        raise SetupError(f"{given} isn't a regular file, so nothing was written. {fix}.")
    if not os.access(out, os.W_OK):
        raise SetupError(f"{given} is read-only, so nothing was written. {fix}, or clear its read-only "
                         f"setting.")


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
    # Without --out the rule file is the --from file, so a refusal names the option the path came from.
    if args.out:
        given, fix = f"--out {out}", "Give the rule file another name with --out"
    elif args.from_file:
        given = f"--from {out}"
        fix = "Without --out, the rule file is written back to the --from file, so give the rule file another name with --out"
    else:
        given, fix = f"The default rule file {out}", "Give the rule file another name with --out"
    if _same_file(out, args.plan):
        raise SetupError(f"{given} is the plan itself. {fix}.")
    if _same_file(out, results.results_path(args.plan)):
        raise SetupError(f"{given} is the plan's results file. {fix}.")
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
    # The output must be a plain file this command may write (never a link: replacing a link's target, or the
    # link, is a surprise either way). Checked only when something will be written, so a linked --from file with
    # nothing to add still exits 0. Both refusals come before any output, so a refused run prints only its error.
    _refuse_unsafe_output(out, given, fix)
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
          f"that must never appear to 'forbid'. Then run: sf-test-plan check {_q(args.plan)} --rules {_q(out)}")
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
        raise SetupError(f"can't write {args.plan}: {e.strerror}. Check that the folder exists, that you can write to it and that the file isn't read-only, or pick another name.")
    print(f"Starter plan: {args.plan}. Edit it, then run: sf-test-plan build {_q(args.plan)}")
    return 0


def _print_compare(result: dict, as_json: bool) -> int:
    if as_json:
        print(builds.as_json(result))
    else:
        builds.print_report(result)
    return 0 if result["same"] else 1


def cmd_compare_builds(args) -> int:
    result = builds.compare(args.tested, args.built, builds.load_pins(args.pins))
    return _print_compare(result, args.json)


def cmd_check_build(args) -> int:
    pins = builds.load_pins(args.pins)
    if args.tested:
        tested = args.tested
    else:
        if not os.path.isfile(args.plan):
            raise SetupError(f"the plan {args.plan} doesn't exist. Give the path to a .testplan.md file.")
        tested = builds.tested_zip_from_plan(args.plan, parse.parse_file(args.plan).zip)
    log.debug("check-build: tested %s, built %s", tested, args.built)
    result = builds.compare(tested, args.built, pins)
    if args.json:
        return _print_compare(result, True)
    for w in result["warnings"]:
        print(f"WARNING: {w} The tested zip is {tested}, and the built zip is {args.built}.")
    if not result["same"]:
        print(f"The tested zip is not the current build. The tested zip is {tested}, and the built zip is "
              f"{args.built}. " + " ".join(result["problems"]) +
              " Rebuild the test zip from the current build, or give the plan a new run: and zip:.")
        return 1
    print("OK: the built zip has the same plugins as the tested zip.")
    return 0


def cmd_ngplus(args) -> int:
    inputs = [(args.base, "the --base plan")] + [(p, f"the plan {p}") for p in args.plans]
    fix = "Give the shared plan another name with --out"
    for path, what in inputs + [(args.order, "the --order file")]:
        if _same_file(args.out, path):
            raise SetupError(f"--out {args.out} is {what}. {fix}.")
    for path, what in inputs:
        if _same_file(args.order, path):
            raise SetupError(f"--order {args.order} is {what}. Give the order file its own name, such as "
                             "ngplus-order.json.")
    for path, opt in ((args.out, "--out"), (args.order, "--order")):
        if os.path.isdir(path):
            raise SetupError(f"{opt} {path} is a folder, not a file. Give a file name, such as "
                             f"{path}{os.sep}{'NewGamePlus.testplan.md' if opt == '--out' else 'ngplus-order.json'}.")
    _refuse_unsafe_output(args.out, f"--out {args.out}", fix)
    if os.path.lexists(args.out) and not args.force:
        raise SetupError(f"{args.out} already exists: pick another --out, or add --force to replace it.")
    order = ngplus.load_order(args.order)
    base = parse.parse_file(args.base)
    plans = [parse.parse_file(p) for p in args.plans]
    bad = [p for p in [base] + plans if p.errors()]
    if bad:
        for p in bad:
            _report(p)
        print("Nothing written: fix the errors above first.")
        return 1
    seen: dict[str, str] = {}
    for p in plans:
        name = ngplus.mod_name(p)
        if not name:
            raise SetupError(f"the plan {p.path} has no 'mod:' line, so its New Game+ group has no name. Add "
                             "'mod: <the mod's name>' under its title.")
        if name in seen:
            raise SetupError(f"the mod {json.dumps(name)} is in both {seen[name]} and {p.path}. Give each mod once.")
        seen[name] = p.path
    text, new_order, summary = ngplus.shared_plan(base, plans, order)
    check = parse.parse_text(text, args.out)
    if check.errors():   # the shared plan is made from plans with no errors, so this is a bug in sf-test-plan
        raise RuntimeError("the shared plan it made has errors: " + "; ".join(e.message for e in check.errors()))
    if new_order != order:
        _refuse_unsafe_output(args.order, f"--order {args.order}",
                              "Give the order file another name with --order")
        _write_atomic(args.order, json.dumps(new_order, indent=1, ensure_ascii=False) + "\n",
                      "Nothing was written. Pick another --order, or check the folder is writable.")
        added = [m for m in new_order if m not in order]
        print(f"Order file: {args.order} (added {', '.join(added)})")
    else:
        print(f"Order file: {args.order} (unchanged)")
    for name, num, n in summary:
        if n:
            print(f"Group {num}: {name} ({_count(n, 'check')})")
        else:
            print(f"{name}: no New Game+ checks of its own (the shared checks cover it)")
    _write_atomic(args.out, text, "The order file was updated, but the shared plan wasn't written. Pick another "
                                  "--out, or check the folder is writable.")
    log.debug("wrote %s (%d bytes, %d mods)", args.out, len(text), len(plans))
    print(f"Shared plan: {args.out} ({_count(len(plans), 'mod')}). Then run: sf-test-plan build {_q(args.out)}")
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
    b.add_argument("--rules", metavar="FILE", help="papyrus-log-check rule file: check the log: ids against it, and "
                                                   "add a table of what its log lines mean to the page")
    style_help = f"style rules file (format {style.STYLE_FORMAT}): also check smoke count, dates, sentences and banned words"
    b.add_argument("--style", metavar="FILE", help=style_help + "; style errors stop the build")
    b.set_defaults(func=cmd_build)

    rd = sub.add_parser("render", parents=[common],
                        help="write the page, or with --fragment only the part a host page embeds, to --out or stdout")
    rd.add_argument("plan")
    rd.add_argument("--fragment", action="store_true",
                    help="write only <div class=\"sf-test-plan\">: no <h1>, styles, inline script or footer (the host "
                         "page loads sf-test-plan.js after it)")
    rd.add_argument("--out", metavar="FILE", help="file to write (default: print to stdout; the report goes to stderr)")
    rd.add_argument("--assets", metavar="DIR", help="also write sf-test-plan.js and sf-test-plan.css into DIR for a host page")
    rd.add_argument("--rules", metavar="FILE", help="papyrus-log-check rule file, as for build")
    rd.add_argument("--style", metavar="FILE", help=style_help + "; style errors stop it")
    rd.add_argument("--force", action="store_true", help="replace --assets files that have other contents")
    rd.set_defaults(func=cmd_render)

    c = sub.add_parser("check", parents=[common], help="check the plan for mistakes, without writing a page")
    c.add_argument("plan")
    c.add_argument("--rules", metavar="FILE", help="papyrus-log-check rule file: check the log: ids against it")
    c.add_argument("--style", metavar="FILE", help=style_help)
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

    pins_help = ("JSON file (format sf-test-plan-pins/1) of known, accepted differences: a plugin whose two sha256 "
                 "values match its pin exactly is a warning, not a difference")
    cb = sub.add_parser("compare-builds", parents=[common],
                        help="check that two mod zips have the same plugins (exit 0 same, 1 different)")
    cb.add_argument("tested", help="the zip that was tested")
    cb.add_argument("built", help="the zip of the current build")
    cb.add_argument("--pins", metavar="FILE", help=pins_help)
    cb.add_argument("--json", action="store_true", help="print the result as JSON (format sf-test-plan-compare/1)")
    cb.set_defaults(func=cmd_compare_builds)

    ck = sub.add_parser("check-build", parents=[common],
                        help="check that the plan's tested zip has the same plugins as a new build")
    ck.add_argument("plan")
    ck.add_argument("--built", required=True, metavar="ZIP", help="the zip of the current build")
    ck.add_argument("--tested", metavar="ZIP",
                    help="the zip that was tested (default: the plan's zip: line, relative to the plan's folder)")
    ck.add_argument("--pins", metavar="FILE", help=pins_help)
    ck.add_argument("--json", action="store_true", help="print the result as JSON (format sf-test-plan-compare/1)")
    ck.set_defaults(func=cmd_check_build)

    ng = sub.add_parser("ngplus", parents=[common],
                        help="write one shared New Game+ plan from a base plan and the mods' New Game+ sections")
    ng.add_argument("plans", nargs="+", metavar="plan", help="a mod's plan (its mod: line names its group)")
    ng.add_argument("--base", required=True, metavar="FILE",
                    help="the plan with the checks every mod shares (its groups come first)")
    ng.add_argument("--order", required=True, metavar="FILE",
                    help="JSON list of mod names that fixes each mod's group number; new mods are added to it "
                         "(created if missing)")
    ng.add_argument("--out", required=True, metavar="FILE", help="the shared plan to write (.testplan.md)")
    ng.add_argument("--force", action="store_true", help="replace an existing --out file")
    ng.set_defaults(func=cmd_ngplus)
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
