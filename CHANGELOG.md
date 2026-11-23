# Changelog

## 0.4.0 (unreleased)

This release adds what a team that keeps many plans needs: a check that the tested zip is the build being released, a table of checks done in the logs, shared New Game+ plans, your own writing rules for `check`, and a `render` command that writes only the part of the page a host page embeds.

### What's new

- `compare-builds <tested> <built>` and `check-build <plan> --built <zip>` say whether two mod zips hold the same plugins and scripts. A plugin file is compared by checksum, and a `.ba2` by what is inside it. Each Papyrus script, loose or inside an archive, is compared by what it does (a recompile of the same source matches). Exit 0 means the same, 1 different, 2 bad input. `--json` prints the result, and `--pins FILE` accepts a known pair of differences as a warning.
- A `## Log checks` section holds checks that someone does in the logs after play. The page shows them as a table with no Pass or Fail control, outside the tally. A `logcheck:` line on a check adds "Check in the log:" under it. `build --rules` adds a table of what each log line in the rule file means.
- A `## New Game+` section holds a mod's New Game+ checks and leaves them off its page. The `ngplus:` header line links the shared page, and `sf-test-plan ngplus` writes the shared plan, with group numbers fixed by an order file.
- `check`, `build` and `render` take `--style FILE` (format `sf-test-plan-style/1`): smoke count, ISO dates, full sentences and banned words, each with its fix. `examples\style.json` is a sample.
- `render` writes the page to `--out` or stdout. With `--fragment` it writes only the checklist for a host page, and `--assets DIR` writes the script and style sheet it needs (`--force` replaces changed ones). Marks saved on the full page are found on the fragment.
- The `new`, `rules`, `logs` and `ngplus` messages that say "Then run: ..." now put a path with spaces in quotes.

### Example

Two zips of a made-up mod, where the new one has a different plugin file, and an accepted pair of differences:

    > sf-test-plan compare-builds BeaconMod-0.1.0.zip BeaconMod-0.1.1.zip
    BeaconMod.esm: differs: the tested zip's copy has sha256 b24d0704d411a3ed, and the built zip's copy has d31fc532bc45d48d
    DIFFERENT: 1 of 1 files differ.

    > sf-test-plan compare-builds BeaconMod-0.1.0.zip BeaconMod-0.1.1.zip --pins pins.json
    BeaconMod.esm: pinned: rebuilt with the same content
    WARNING: BeaconMod.esm differs, but the --pins file allows this exact pair: rebuilt with the same content
    OK: the built zip has the same plugins and scripts as the tested zip.

The first run exits 1 and the second exits 0. The README has the same example with the pins file, and the other new commands.

### Changes

- `--help` of every command exits 0 and is listed in the README's exit-code table.
- `FORMAT.md` has the rules for Log checks (12, 13), New Game+ (14), the page's fragment and the style file (section 7), and the new codes `bad-ngplus`, `smoke-log-check`, `style-smoke`, `style-date`, `style-sentence` and `style-banned`.
- The page's `tp-config` and the marks format `sf-test-plan-marks/1` are unchanged, so saved marks carry over.

## 0.3.2 (2026-11-22)

This release fixes the mod name that `new` and `rules` take from a plan file name, so a dotted name such as `My.Mod.testplan.md` is no longer cut short. It also replaces the sample names in the public tests with made-up ones.

### Example

A plan named `My.Mod.testplan.md` with no `mod:` line now gets its mod name from the file name, dots kept (before, the name was "My"):

    > sf-test-plan rules My.Mod.testplan.md
    My.Mod.testplan.md: 3 log ids on 3 steps
    New expect rule 'loaded' (step 1.1): re "MyMod: loaded"
    New expect rule 'placed' (step 2.2): re "MyMod: placed"
    New expect rule 'restored' (step 3.1): re "MyMod: restored"
    Rule file: My.Mod.logrules.json. Edit each new 're' to match the line your mod writes, and move a rule for a line that must never appear to 'forbid'. Then run: sf-test-plan check My.Mod.testplan.md --rules My.Mod.logrules.json

The rule file's `mod` is "My.Mod".

### Fixes

- `new` and `rules` now keep the dots in a plan's file name when they take the mod name from it. Before, `My.Mod.testplan.md` gave the mod name "My". Now it gives "My.Mod", and only the `.testplan.md` or `.md` ending is removed, the same ending the default rule file name drops. A plain-text ending (`.txt`, `.text`, `.markdown`, `.mdown`, `.mkd`) is removed too (`plan.txt` gives "plan", `Beacon.testplan.txt` gives "Beacon"), and any other name stays whole (`Cool.Mod` gives "Cool.Mod"). A name that starts with a dot gives "My Mod".
- A folder given where a file belongs (the plan, the marks file, the report, the rule file, or `--out`) now gets "is a folder, not a file" with the fix. On Windows it used to say "Permission denied".
- `rules --out <folder>` and `new <folder>` now exit 2 with "is a folder" and the fix, with or without `--force`. Before, they ended in an "already exists" message or an operating-system write error. `rules` also now checks `--out` when the plan has no `log:` lines: before, it exited 0 with "nothing to write" whatever `--out` named, and now `--out` naming the plan itself or a folder exits 2.
- `build --out`, `logs --out` and `rules --out` now refuse the plan itself and the plan's results file (and `logs --out` the report, `build --out` the `--rules` file) with exit 2, and write nothing. Before, they overwrote it. The message names where the path came from (`--out`, the `--from` file or the default name) and says to give another name with `--out`. `rules --from <folder>` without `--out` now names `--from` in its "is a folder" message instead of `--out`.
- `build` and `logs` now refuse an output that is a symbolic link, as `rules` already did. All three now also refuse an existing output that is read-only or isn't a regular file. Each refusal exits 2, writes nothing and names the file and the fix. The null device (`NUL` on Windows, `/dev/null` elsewhere) is still allowed as the output. Before, `build` and `logs` wrote through a link and replaced the file it points to, a read-only output ended in a write error (after `logs` had printed its marks), and on Linux and macOS `rules --force` replaced a read-only rule file.
- `new` in a folder that doesn't exist now says to check that the folder exists and can be written to, and that the file isn't read-only.
- `--log` now records the file name and the mod name taken from it, on `new` and `rules` runs that take the name from the file.
- The tests now use made-up mod names as samples, so the release holds no names of private projects.

## 0.3.1 (2026-11-22)

### Example

A `rules` run on the bundled example plan whose rule file already exists is refused, and now prints only the error (on stderr, exit 2), with no counts first:

    > sf-test-plan rules examples\Beacon.testplan.md
    sf-test-plan: examples\Beacon.logrules.json already exists: pick another --out, or add --force to replace it.

With the old rule file moved away, the same command writes it:

    > sf-test-plan rules examples\Beacon.testplan.md
    examples\Beacon.testplan.md: 3 log ids on 3 steps
    New expect rule 'loaded' (step 1.1): re "BeaconMod: loaded"
    New expect rule 'placed' (step 2.2): re "BeaconMod: placed"
    New expect rule 'restored' (step 3.1): re "BeaconMod: restored"
    Rule file: examples\Beacon.logrules.json. Edit each new 're' to match the line your mod writes, and move a rule for a line that must never appear to 'forbid'. Then run: sf-test-plan check examples\Beacon.testplan.md --rules examples\Beacon.logrules.json

### Fixes

- A file path that isn't valid Unicode (a Linux file name with bytes that aren't UTF-8, or a Windows name with a lone surrogate) no longer breaks `--log`: the log file writes it as `\udcff` instead of printing a "Logging error" for each line.
- `build` now writes the page for a plan in such a folder. Before, it stopped with "unexpected error" while making the page's storage key. Other folder names get the same key as before, so their pages keep their marks.
- `new` and `rules` now take a plan whose file name isn't valid Unicode. Before, `new` stopped with "unexpected error" and left an empty plan behind, and `rules` (on a plan with no `mod:` line) blamed a broken escape in the plan. The mod name now leaves those characters out, or is "My Mod" when nothing is left.
- Every command already printed any path safely, because its output is always UTF-8 (a character that isn't valid Unicode prints as `?`), even when the console's code page is cp1252 or ASCII. Tests now cover that too.
- A `rules` run that is refused (the output is a link, or it already exists without `--force`) now prints only the error. Before, it printed the counts and the "Already in" line first, as if it were going to write. A linked `--from` file with nothing to add still prints its counts and "Nothing to add" and exits 0.

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
- With `--from`, new patterns start with the file's `prefix` (a `^` or `$` anchor and escaped characters such as `\:` are fine). If the prefix is a pattern rather than one fixed text, the command prints a warning and uses the mod name. `--prefix` with `--from` also updates the file's `prefix` (keeping a leading `^` and a trailing `$`), even when no id is missing, and `--plugin` with `--from` is refused.
- The command never replaces a file unless you add `--force`, and it never writes over the plan. It writes to a temporary file first, so a failed write leaves the old file as it was. A replaced file keeps its permissions. When it would write, an output file that is itself a symbolic link is refused (give the real file with `--out`).
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

This is the first release.

- `build` makes one self-contained checklist page from a Markdown test plan. The page has Pass / Fail / Skip and a note per step, a smoke test and folded deep checks, Copy buttons for console commands, a light and dark theme, and a phone-width layout, and it loads nothing from the network.
- The page keeps marks in the browser, with Export and Import (JSON, `sf-test-plan-marks/1`), Copy results and Reset.
- `check` finds plan mistakes (missing `run:`, duplicate ids, keys with no step, unknown `log:` ids with `--rules`, and more), each with its line number and the fix.
- `import` adds a marks file to `<plan>.results.json`, and `build` shows it as the page's Results log.
- `logs` turns a papyrus-log-check (0.3.0 or later) JSON report into marks for steps with `log:` ids.
- `new` writes a starter plan.
- Every command takes `--verbose` and `--log FILE`.
