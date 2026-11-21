# Changelog

## 0.3.0 (2026-11-20)

### What's new

The new `rules` command starts a papyrus-log-check rule file for you. It reads the `log:` ids in your plan and writes one rule for each, with a pattern you then edit to match the line your mod writes. When you add steps later, it adds only the rules your file lacks. The page's text also uses the full width of the window now.

### Example

    > sf-test-plan rules examples\Beacon.testplan.md --out Beacon.logrules.json
    examples\Beacon.testplan.md: 3 log ids on 3 steps
    New expect rule 'loaded' (step 1.1): re "BeaconMod: loaded"
    New expect rule 'placed' (step 2.2): re "BeaconMod: placed"
    New expect rule 'restored' (step 3.1): re "BeaconMod: restored"
    Rule file: Beacon.logrules.json. Edit each new 're' to match the line your mod writes, and move a rule for a line that must never appear to 'forbid'. Then run: sf-test-plan check examples\Beacon.testplan.md --rules Beacon.logrules.json

### New command: rules

- `sf-test-plan rules PLAN` writes `<plan name>.logrules.json` with the mod's name, version, plugin and log prefix, and one `expect` rule for each `log:` id. Each rule's `means` names the steps it proves.
- `--prefix TEXT` sets the text the mod's log lines start with, and `--plugin NAME` sets its plugin files. By default both come from the plan's `mod:` name (`BeaconMod:` and `BeaconMod.esm`).
- `--from FILE` keeps an existing rule file as it is and adds only the ids that are in neither its `expect` nor its `forbid` list. When nothing is missing, it writes nothing.
- With `--from`, new patterns start with the file's `prefix` (a `^` or `$` anchor and escaped characters such as `\:` are fine). If the prefix is a pattern rather than one fixed text, the command prints a warning and uses the mod name. `--prefix` with `--from` also updates the file's `prefix` (keeping a leading `^`), even when no id is missing, and `--plugin` with `--from` is refused.
- The command never replaces a file unless you add `--force`, and it never writes over the plan. It writes to a temporary file first, so a failed write leaves the old file as it was. A replaced file keeps its permissions, and a symbolic link keeps pointing to the updated file.
- The code is in `sftestplan/rules.py`, so other scripts can make the same rule files from their own list of ids.
- FORMAT.md section 6 describes the file it writes.

### Changes to the page

- The page no longer limits the width of its text, and its column is wider (76rem instead of 900 pixels).

### Changes to the page test (for developers)

- CI now waits up to 90 seconds for Chrome to start in the page test (`TP_CDP_WAIT: "90"`), because Chrome's first start on a fresh Windows runner sometimes took longer than the default 30 seconds.

### Download

Download `sf-test-plan-0.3.0.zip` below, unpack it and follow the Install steps in the README. It needs Python 3.10 or newer and nothing else.

## 0.2.0 (2026-11-20)

### What's new

This release protects your marks. If a page finds marks in the browser that a newer sf-test-plan saved, it never writes over them: it keeps its own marks in memory and tells you to use Export, or to open the plan with that newer version. The page test that runs in CI is also sturdier, so it no longer hangs or crashes when Chrome is slow to start.

### Example

Building the example plan works as before:

    > sf-test-plan build examples\Beacon.testplan.md
    examples\Beacon.testplan.md: 3 groups, 6 checks, 5 smoke; 0 errors, 0 warnings
    Page: examples\Beacon.testplan.html

Open `examples\Beacon.testplan.html` in your browser, mark a step and reload the page: your marks are still there.

### Changes to the page

- The page now checks the format of the marks saved in the browser. When they come from a newer sf-test-plan (a newer major store format), the page never writes over them, and the save line says to use Export or open the plan with that newer version.
- Import and Reset follow the same rule, and they say that they saved nothing.
- A store format counts as newer when its name starts with `sf-test-plan-store/<n>`, where n is 1 or more, whatever follows (such as `/2`, `/1.1` or `/2-rc`). The one exception is exactly `sf-test-plan-store/1`, which is the current format.
- After finding a newer format, the page saves nothing until it is reloaded, so other tabs' saves never replace the marks it shows.
- Saved marks with no format still count as format 1. Saved marks with any other format (such as `sf-test-plan-store/0`, `sf-test-plan-store/garbage` or another name) count as damaged.
- The warning about a damaged saved copy now says that your next saved change replaces it. Marks kept from other builds are saved too, and notes save after their short pause.

### Changes to the page test (for developers)

- The page test now waits for a page that Chrome lists with a connection address, instead of crashing when the address is missing.
- If the page test loses its connection to Chrome during the run, it stops with its own message and exit code 2. A command that Chrome never answers fails after 30 seconds instead of hanging.
- The page test has new checks for the store format: a newer format, a missing format, an unknown format name and format 1.
- The page test now waits up to 30 seconds for Chrome to start, because Chrome's first start on a fresh CI runner can take more than 10 seconds. Set `TP_CDP_WAIT` (1 to 600 seconds) to change the wait.
- One timer covers the whole start, including the connection to Chrome, so the test can't hang there. While the test waits for Chrome, a request for its page list that gets no answer is dropped after 5 seconds and sent again.
- If Chrome lists the page but the connection to it fails, the test stops at once with its own message. The timeout message names `TP_CDP_WAIT`.
- The README now says that the page test needs Node 22 or newer.

### Download

Download `sf-test-plan-0.2.0.zip` below, unpack it and follow the Install steps in the README. It needs Python 3.10 or newer and nothing else.

## 0.1.1 (2026-11-20)

- The page no longer shows an old "Saved in this browser at ..." time after another tab removes the saved marks.
- Reset now says when the saved copy couldn't be read and was replaced. Before, it counted marks held in memory as kept.
- When the saved copy can't be read, the page keeps the marks it shows instead of clearing them, and it writes nothing. This covers a damaged copy found when the page opens and one left by another tab. The save line warns that the next change replaces the unreadable copy, so use Export to keep a copy.
- Tests now run on GitHub Actions. The unit tests run on Windows and Linux with Python 3.10 and 3.13, a check confirms that both systems build the same release zip, and the page test runs with Chrome on Windows.
- The release zip leaves out the repo's CI setup (`.github/`).

## 0.1.0 (2026-11-19)

First release.

- `build`: one self-contained checklist page from a Markdown test plan: Pass / Fail / Skip and a note per step, smoke test and folded deep checks, Copy buttons for console commands, light and dark theme, phone width, no network loads.
- The page keeps marks in the browser, with Export and Import (JSON, `sf-test-plan-marks/1`), Copy results and Reset.
- `check`: finds plan mistakes (missing `run:`, duplicate ids, keys with no step, unknown `log:` ids with `--rules`, and more), each with its line number and the fix.
- `import`: adds a marks file to `<plan>.results.json`; `build` shows it as the page's Results log.
- `logs`: turns a papyrus-log-check (0.3.0 or later) JSON report into marks for steps with `log:` ids.
- `new`: writes a starter plan.
- `--verbose` and `--log FILE` on every command.
