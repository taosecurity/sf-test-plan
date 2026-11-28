# sf-test-plan

sf-test-plan turns a plain-text test plan for your Starfield mod into a checklist page that you tick off while you play. You write the steps in a Markdown file (what to do, and what you should see), and sf-test-plan makes one web page from it.

Download the latest zip from the [releases page](https://github.com/taosecurity/sf-test-plan/releases), unpack it, open a Command Prompt in the folder and build the example page:

```
sf-test-plan build examples\Beacon.testplan.md
```

For AI assistants: step-by-step instructions are in [AGENTS.md](AGENTS.md).

## Example

The release zip holds a plan for a made-up mod called Beacon Mod. Building it checks the plan and writes the page next to it:

```
> sf-test-plan build examples\Beacon.testplan.md
examples\Beacon.testplan.md: 3 groups, 6 checks, 5 smoke; 0 errors, 0 warnings
Page: examples\Beacon.testplan.html
```

Open `examples\Beacon.testplan.html` in your browser. Click Pass on a step, type a note and reload the page: your marks are still there.

A mistake in a plan is reported with the fix, and nothing is written. Here the `run:` line was deleted from a copy of the example:

```
> sf-test-plan check Broken.testplan.md
Broken.testplan.md: error no-run: the plan has no 'run:' line. Add one under the title, such as 'run: mymod-0.1.0' (give each new build a new run).
Broken.testplan.md: 3 groups, 6 checks, 5 smoke; 1 errors, 0 warnings
```

## What it does for you

- Open the page in any browser beside the game (or on your phone), and mark each step Pass, Fail or Skip with a note.
- Your marks stay in that browser. **Export** saves them to a file you can keep, share with a tester, or turn into a results log next to your plan.
- If your mod writes Papyrus log lines, sf-test-plan can also read a [papyrus-log-check](https://github.com/taosecurity/papyrus-log-check) report and mark the steps the log proves. It can also start the rule file that papyrus-log-check needs, from the steps in your plan.
- It needs only Python. The page works offline, loads nothing from the internet, and nothing is ever uploaded.

## Install (two minutes)

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/). On the first screen of the installer, tick **Add python.exe to PATH**. To check that it worked, open a new Command Prompt and type `python --version`. It should print a version number. (sf-test-plan itself needs Python 3.10 or newer, and is tested on 3.10 and 3.13 on Windows and Linux.)
2. Download `sf-test-plan-0.5.1.zip` from the [releases page](https://github.com/taosecurity/sf-test-plan/releases) and unpack it anywhere.
3. Open the unpacked folder in File Explorer, click the address bar at the top, type `cmd` and press Enter. A Command Prompt window opens in that folder, ready for the commands below.
4. Build the example page with `sf-test-plan build examples\Beacon.testplan.md`, as in the Example above, and open `examples\Beacon.testplan.html` in your browser.

The commands in this README are written as `sf-test-plan`, which works in a Command Prompt opened in the unpacked folder. In PowerShell, type `.\sf-test-plan.cmd` instead. On Linux or macOS, type `./sf-test-plan`. On any system, `python sf_test_plan.py` works too. To use the short form from any folder, add the unpacked folder to your PATH.

Then make your own plan:

```
> sf-test-plan new MyMod.testplan.md --mod "My Mod"
Starter plan: MyMod.testplan.md. Edit it, then run: sf-test-plan build MyMod.testplan.md
```

`new` writes a starter plan with comments explaining each part. Edit it in any text editor and build it.

## Words used here

- **Papyrus:** Starfield's scripting language. Scripts are written as `.psc` source files and compiled into `.pex` files that the game runs. A mod's scripts can write lines to the Papyrus log with `Debug.Trace`.
- **Smoke test:** a short first test (five to eight steps) that shows the mod loads and its main feature works once, before the longer checks.
- **Console:** the PC command line inside the game, opened with ~. Plans often use console commands such as `player.additem`.
- **Rule file:** a papyrus-log-check file (`*.logrules.json`) that lists the log lines a mod should write. Each rule has an id, which a plan step can name in `log:`.

## Writing a plan

This is the start of the example plan, `examples\Beacon.testplan.md`:

```markdown
# Beacon Mod test plan
run: beacon-0.1.0
mod: Beacon Mod
version: 0.1.0
zip: BeaconMod-0.1.0.zip

This plan tests Beacon Mod 0.1.0, a made-up example mod that gives you a placeable beacon. Start with the smoke test; the deep checks are for before a public release.

## Before you start
- Install BeaconMod-0.1.0.zip with your mod manager and enable it.
- Turn on Papyrus logging (the mod's README says how), so `sf-test-plan logs` can check the log lines.

## 1 Install and load
These checks prove the mod loads.

- [ ] Start a new game and finish the character creator.
  Expect: no error message about Beacon Mod.
  smoke: yes
  log: loaded
...

## 2 Main feature
- [ ] Open the console and type `player.additem 0001A2B3 1`.
  Expect: one Beacon in your inventory.
  smoke: yes
...
```

- `run:` names this test round. Marks are saved under it, so **change it for each new build** (for example `beacon-0.1.1`). The page then starts fresh, while the old marks stay in their own file.
- `## <number> <title>` starts a group of steps. `- [ ] ...` is one step.
- These lines can go under a step:
  - `Expect:` says what you should see.
  - `smoke: yes` puts the step in the short smoke test.
  - `note:` adds a hint.
  - `log:` lists papyrus-log-check rule ids that also prove this step.
  - `id: 2.4` keeps a step's number fixed.
- Console commands in backticks get a **Copy** button on the page.

When any step has `smoke: yes`, the page puts those first in a "Smoke test" box and folds the rest into "Deep checks (optional)". Five to eight smoke steps is a good size: the mod loads, its options are there, its main feature works once, and a save and load.

The whole format, every warning and every file sf-test-plan reads or writes are in [FORMAT.md](FORMAT.md).

## Commands

| Command | What it does |
|---|---|
| `sf-test-plan build PLAN [--out PAGE] [--rules FILE] [--style FILE]` | Checks the plan and writes the page (default: the plan's name with `.html`). |
| `sf-test-plan check PLAN [--rules FILE] [--style FILE]` | Checks the plan for mistakes without writing anything. With `--rules`, it also checks every `log:` id against a papyrus-log-check rule file. With `--style`, it also checks your own writing rules. |
| `sf-test-plan import MARKS --plan PLAN` | Adds a marks file (from the page's Export button) to `<plan>.results.json` as one results row, and prints the tally. Build again to show it on the page. |
| `sf-test-plan logs REPORT --plan PLAN [--mod NAME] [--out MARKS] [--force]` | Reads a papyrus-log-check JSON report and writes marks for the steps with `log:` ids (an existing marks file is replaced only with `--force`). Import them on the page, then Export and give that file to `import` (the marks file alone holds none of the page's marks). |
| `sf-test-plan rules PLAN [--out FILE] [--from FILE] [--prefix TEXT] [--plugin NAME] [--force]` | Writes a starter papyrus-log-check rule file with a rule for each `log:` id in the plan, or adds the missing ids to the rule file you already have. |
| `sf-test-plan new PLAN [--mod NAME] [--force]` | Writes a starter plan. |
| `sf-test-plan render PLAN [--fragment] [--out FILE] [--assets DIR] [--force]` | Writes the page, or with `--fragment` only the part a host page embeds. See "render" below. |
| `sf-test-plan compare-builds TESTED BUILT [--pins FILE] [--json]` | Says whether two mod zips hold the same plugins, scripts and other files (such as an SFSE DLL). |
| `sf-test-plan check-build PLAN --built ZIP [--tested ZIP] [--pins FILE] [--json]` | Says whether the plan's tested zip holds the same plugins, scripts and other files as a new build. |
| `sf-test-plan ngplus --base FILE --order FILE --out FILE PLAN...` | Writes one shared New Game+ plan from several mods' plans. |

Every command also takes `--verbose` and `--log FILE`. The log file must not be one of the command's own files (the plan, its results file, a report, marks, pins or rule file, a zip or `--out`): such a `--log` is refused with exit 2 before anything is written. The exit codes are:

| Exit code | Meaning |
|---|---|
| 0 | The command finished. Warnings are fine. `--help` always exits 0. For `compare-builds` and `check-build`, 0 also means the two zips have the same plugins, scripts and other files. |
| 1 | The plan has errors (each one is printed with its line number and the fix). For `compare-builds` and `check-build`, 1 means the zips differ. |
| 2 | A file can't be read or written, or an option is wrong. |

`build`, `logs` and `rules` never write over the plan or the plan's results file, `logs` never writes over its report and replaces an existing marks file only with `--force`, and `build` never writes over its `--rules` file. They also refuse an output that is a symbolic link, a read-only file or something other than a regular file. In each case the command stops with exit 2, writes nothing, and names the file (from `--out`, `--from` or the default name) and the fix, usually to give another name with `--out`. The null device (`NUL` on Windows, `/dev/null` elsewhere) is allowed as an output. `rules` checks for a link or a read-only file only when it would write, so a linked `--from` file with nothing to add still exits 0.

### build and check

`build` is shown in the Example. `check` prints the same summary line without writing a page. With `--rules`, it also confirms that every `log:` id in the plan is in the rule file:

```
> sf-test-plan check examples\Beacon.testplan.md --rules examples\Beacon.logrules.json
examples\Beacon.testplan.md: 3 groups, 6 checks, 5 smoke; 0 errors, 0 warnings
```

### import

After a test round, add the marks file the tester exported to the plan's results, then build again to show them on the page as the Results log. This run uses a sample marks file from the repo's `tests\fixtures` folder:

```
> sf-test-plan import marks-beacon.json --plan examples\Beacon.testplan.md
Smoke test: 2 pass, 1 fail, 1 skip, 2 not run
1.2 fail: No Beacon group in Gameplay options.; 2.1 pass: Took two tries.; 3.1: Ran out of time.
Results: examples\Beacon.testplan.results.json (rebuild the page to show it)
```

### logs

`logs` reads a papyrus-log-check JSON report and marks the steps whose `log:` rules it can prove. This run uses a sample report from `tests\fixtures`:

```
> sf-test-plan logs logcheck-beacon.json --plan examples\Beacon.testplan.md
Using 'Beacon Mod' from the report (the plan's mod: line).
1.1 pass: loaded PASS.
2.2 FAIL: placed FAIL.
3.1 no mark: not proved: restored NOT SEEN.
Marks: logcheck-beacon.marks.json (open the page and use Import, then Export and give that file to: sf-test-plan import <export> --plan examples\Beacon.testplan.md)
```

See "Papyrus logs" below for how to make the report.

### rules

`rules` starts a papyrus-log-check rule file for you. It writes one `expect` rule for each `log:` id in the plan, with a pattern made from your mod's log prefix and the id, and it notes which step each rule proves:

```
> sf-test-plan rules examples\Beacon.testplan.md --out Beacon.logrules.json
examples\Beacon.testplan.md: 3 log ids on 3 steps
New expect rule 'loaded' (step 1.1): re "BeaconMod: loaded"
New expect rule 'placed' (step 2.2): re "BeaconMod: placed"
New expect rule 'restored' (step 3.1): re "BeaconMod: restored"
Rule file: Beacon.logrules.json. Edit each new 're' to match the line your mod writes, and move a rule for a line that must never appear to 'forbid'. Then run: sf-test-plan check examples\Beacon.testplan.md --rules Beacon.logrules.json
```

The file it writes looks like this:

```json
{
 "mod": "Beacon Mod",
 "version": "0.1.0",
 "plugins": ["BeaconMod.esm"],
 "prefix": "BeaconMod:",
 "expect": [
  {"id": "loaded", "re": "BeaconMod: loaded", "means": "Step 1.1: Start a new game and finish the character creator."},
  {"id": "placed", "re": "BeaconMod: placed", "means": "Step 2.2: Drop the beacon and activate it."},
  {"id": "restored", "re": "BeaconMod: restored", "means": "Step 3.1: Save, quit to the main menu and load the save."}
 ],
 "forbid": []
}
```

- The patterns are only a start. Change each `re` to match the line your mod really writes, such as `"re": "BeaconMod: loaded \\d"` for the line "BeaconMod: loaded 0.1.0" (JSON needs each backslash written twice). The papyrus-log-check README explains the patterns.
- A rule for a line that must never appear belongs under `forbid`, so move it there.
- `--prefix` sets the text your mod's log lines start with. The default is the `mod:` name's letters and digits, then a colon (`BeaconMod:`).
- `--plugin MyMod.esm` names the mod's plugin file (repeat it for several). The default is the same name with `.esm`.
- Without `--out`, the file is the plan's name with `.logrules.json` (`Beacon.testplan.md` gives `Beacon.logrules.json`). The command never replaces a file unless you add `--force`, and when it would write, it refuses an output file that is a symbolic link or read-only, even with `--force`: give another name with `--out`. It never writes over the plan or its results file, even with `--force` (see [Commands](#commands)).

When you add steps later, `--from` keeps the rule file you already have and adds only the ids it doesn't hold yet. Add `--force` to write the new rules into that same file.

- The new patterns start with the file's `prefix`. If that prefix is a pattern rather than one fixed text, the command warns you and uses the mod name instead.
- To fix that, delete the rules it just added, then run it again with `--prefix` and `--force`. `--prefix` sets the text, updates the file's `prefix` (keeping a leading `^` and a trailing `$`) and adds those rules again. It updates the `prefix` even when no id is missing, and rules already in the file keep their patterns.
- `--plugin` doesn't go with `--from`, because the file keeps its own `plugins` list.

When nothing is missing and the prefix stays the same, it writes nothing:

```
> sf-test-plan rules examples\Beacon.testplan.md --from examples\Beacon.logrules.json
examples\Beacon.testplan.md: 3 log ids on 3 steps
Already in examples\Beacon.logrules.json: 3 of the 3 ids.
Nothing to add, so nothing was written.
```

### render

`render` writes the same page as `build`, to `--out` (or to stdout, with the report on stderr). With `--fragment` it writes only the checklist, inside `<div class="sf-test-plan">`, with no styles, no inline script and no footer, so a web page of your own can hold it. `--assets DIR` also writes `sf-test-plan.js`, `sf-test-plan.css` (the style of the whole page) and `sf-test-plan-fragment.css` (the same style with every rule scoped to `.sf-test-plan`) into DIR (it makes the folder, and it replaces a file that has other contents only with `--force`). Link `sf-test-plan-fragment.css` beside a fragment: `sf-test-plan.css` also styles `body`, headings and links, so it would restyle the whole host page. The host page has a viewport meta tag and loads the script after the fragment. It holds one fragment:

```
> sf-test-plan render examples\Beacon.testplan.md --fragment --out frag.html --assets assets
examples\Beacon.testplan.md: 3 groups, 6 checks, 5 smoke; 0 errors, 0 warnings
Wrote: assets\sf-test-plan.js
Wrote: assets\sf-test-plan.css
Wrote: assets\sf-test-plan-fragment.css
Fragment: frag.html
```

```html
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="stylesheet" href="assets/sf-test-plan-fragment.css">
...
<!-- the contents of frag.html here -->
<script src="assets/sf-test-plan.js"></script>
```

Marks saved on the full page are found on the fragment, and the other way round. FORMAT.md says what the fragment holds.

### compare-builds and check-build

After a test round, these say whether the zip you tested is the build you are about to release. `compare-builds` compares the files in two zips. A `.esm`, `.esp` or `.esl` is compared by checksum, and each `.ba2` by what is inside it, so a different archive packing alone is not a difference. Every other file is compared by checksum too, such as an SFSE DLL, an `.ini` or a loose Papyrus script (a `.pex` file outside an archive). In a zip that has a plugin, the files that may change between builds without changing the mod are left out: documents (`.txt`, `.md`, `.pdf` and the like), pictures (`.png`, `.jpg`) and readme and license files with no extension, when they are outside the game's folders, and anywhere a `fomod` folder and the junk files macOS and Windows add (`__MACOSX`, `Thumbs.db`). A document or picture inside a folder the game or a plugin reads from (`Interface`, `SFSE`, `MCM`, `Scripts`, `Textures` and the like, such as `Data/Interface/fontconfig.txt`) is part of the mod and is compared. A zip with no plugin, such as a DLL-only mod, has every file compared. A script, inside an archive or loose, is compared by what it does, so recompiling the same source, which gives the script a new compile time and a new order of its names, is not a difference either. The exit code is 0 when they match and 1 when they differ:

```
> sf-test-plan compare-builds BeaconMod-0.1.0.zip BeaconMod-0.1.1.zip
BeaconMod.esm: differs: the tested zip's copy has sha256 b24d0704d411a3ed, and the built zip's copy has d31fc532bc45d48d
DIFFERENT: 1 of 1 files differ.
```

`--json` prints the result as JSON (format `sf-test-plan-compare/1`). `--pins FILE` names differences you have looked at and accepted. The pins file is JSON, with each file's lower-case name without its folder (such as `beaconmod.esm` or `beaconmod.dll`) and the first 16 hex digits of the two checksums that the report printed. Only that exact pair is accepted, and it is shown as a warning:

```json
{"format": "sf-test-plan-pins/1",
 "pins": {"beaconmod.esm": {"tested": "b24d0704d411a3ed", "built": "d31fc532bc45d48d", "why": "rebuilt with the same content"}}}
```

```
> sf-test-plan compare-builds BeaconMod-0.1.0.zip BeaconMod-0.1.1.zip --pins pins.json
BeaconMod.esm: pinned: rebuilt with the same content
WARNING: BeaconMod.esm differs, but the --pins file allows this exact pair: rebuilt with the same content.
OK: the built zip has the same plugins, scripts and other files as the tested zip.
```

`check-build` does the same with the zip named by the plan's `zip:` line (relative to the plan's folder, or give `--tested`) and a new build given with `--built`. A network path on the `zip:` line (one that starts with `\\` or `//`, or with the Windows prefix `\??\`) is refused, because on Windows even looking for it sends your sign-in to that computer; copy the zip to this PC, or give it with `--tested`:

```
> sf-test-plan check-build examples\Beacon.testplan.md --built BeaconMod-0.1.1.zip
The tested zip is not the current build. The tested zip is examples\BeaconMod-0.1.0.zip, and the built zip is BeaconMod-0.1.1.zip. BeaconMod.esm differs: the tested zip's copy has sha256 b24d0704d411a3ed, and the built zip's copy has d31fc532bc45d48d. Rebuild the test zip from the current build, or give the plan a new run: and zip:.
```

### Log checks

Some checks are done in the logs after play, not on the page. Put them under a `## Log checks` heading, written like other checks. The page shows them as a table ("Checks in the logs") with no Pass or Fail buttons, and they are not counted in the tally. Their ids are `L.1`, `L.2` and so on. A single check can also carry a `logcheck:` line, which the page shows as "Check in the log:" under the step:

```markdown
## 1 Install
- [ ] Start a new game and finish the character creator.
  Expect: no error message.
  logcheck: the log shows "BeaconMod: loaded" once.

## Log checks
- [ ] Look for errors in the Papyrus log.
  Expect: none from BeaconMod.
```

`build --rules FILE` also adds a table of what each log line in the rule file means.

### New Game+

A mod that has its own New Game+ checks puts them under `## New Game+` (or `## NG+`). They are left off that mod's page. A header line such as `ngplus: ../NewGamePlus.html` puts a link to the shared page on the mod's page. To make the shared plan, give `ngplus` a base plan (the checks every mod shares), an order file and the mods' plans:

```
> sf-test-plan ngplus --base Base.testplan.md --order order.json --out NewGamePlus.testplan.md Styled.testplan.md
Order file: order.json (added Beacon Mod)
Group 2: Beacon Mod (1 check)
Shared plan: NewGamePlus.testplan.md (1 mod). Then run: sf-test-plan build NewGamePlus.testplan.md
```

The order file is a JSON list of mod names. A mod's group number is the base plan's highest group number plus the mod's place in the list, so marks never move when a mod is added; new mods are added at the end. A new base group with a number above the base's highest moves every mod's group, and the testers' saved marks for those groups then show on the wrong checks. To add shared checks later, add them at the end of an existing base group instead. Build the shared plan as usual.

### Style rules

`--style FILE` on `check`, `build` and `render` also checks your own writing rules, from a JSON file. The release zip has `examples\style.json`:

```json
{
  "format": "sf-test-plan-style/1",
  "level": "error",
  "smoke": {"min": 3, "max": 12},
  "iso_dates": true,
  "full_sentences": true,
  "banned": [
    "obviously",
    {"word": "just", "use": "nothing (leave it out)"},
    {"word": "slate", "use": "note"}
  ]
}
```

Here a plan has one smoke check, a step that doesn't end like a sentence, a date written 11/23/2026 and a banned word. Each is reported with the fix. With `"level": "error"`, a style problem makes the command exit 1 and `build` writes nothing:

```
> sf-test-plan check Styled.testplan.md --style examples\style.json
Styled.testplan.md: error style-smoke: the plan has 1 smoke checks; the style file asks for at least 3. Mark more checks with 'smoke: yes'.
Styled.testplan.md:8: error style-banned: 'just' is on the style file's banned list. Write 'nothing (leave it out)' instead.
Styled.testplan.md:8: error style-sentence: check 1.1's step doesn't end with '.', '!', '?' or ':', so it isn't a full sentence. Write it as a full sentence.
Styled.testplan.md:9: error style-date: the date '11/23/2026' isn't written as YYYY-MM-DD. Write it as 2026-11-23.
Styled.testplan.md: 1 groups, 1 checks, 1 smoke; 4 errors, 0 warnings
```

FORMAT.md section 7 lists every key.

## The page

- **Pass / Fail / Skip** on each step, and a note box. Click a chosen mark again to clear it.
- The tally at the top counts pass, fail, skip and not run. With a smoke test, only the smoke checks count on the page until you mark a deep check. From then on the tally covers every check, and `import` calls the round a "Full test". `import` always counts every plan check that has no mark as not run, so a smoke round whose deep checks were never marked says so in its row.
- **Export** downloads your marks as `<run>-marks-<date>.json`. **Import** reads one back (a tester's file, or one from `sf-test-plan logs`). For each step the newer mark wins, but a mark from the log never replaces a mark or note you made yourself. `sf-test-plan import` follows the same rule when a marks file holds both.
- **Copy results** puts a plain-text summary on the clipboard, ready to paste into a bug report or a Nexus post.
- **Reset** clears the marks and notes on this page's steps in this browser. Marks that another build of the plan saved for steps this page doesn't have are kept, and the page says how many.
- Marks are kept in the browser's local storage for that page. A private window, or a browser that blocks storage, keeps them only until you close the tab. The page says so, so use Export before you close it.

## A quest example

`examples\QuestExample.testplan.md` is a plan for a made-up quest mod, Tidewater Errand, whose quest has three stages. It shows how to test a quest honestly:

- Each stage has one check that plays the stage, one check that types `getstage <QuestID>` in the console and says what number to expect, and a `note:` that names the console fix (`setstage <QuestID> <stage>`) for a stage that never starts. A stage you moved by hand is a Fail, so the note says to mark the check that plays that stage Fail on the page. The forced stage still writes its log line, so the plan says to bring the log's marks in with the page's Import button, where a mark set on the page wins over a Pass from the log. For the results row, the plan says to Export from the page after that and give the export to `sf-test-plan import`. The file from `sf-test-plan logs` doesn't hold the marks made on the page, so importing it alone would record the log's Pass.
- The mod writes one `Debug.Trace` line for each stage change, and the plan's `log:` ids point at those lines. The rule file `examples\QuestExample.logrules.json` proves them, and its `order` rule proves that the stages came in the right order.
- The Log checks group tells the tester to read the quest's stages in the save with `sf-save-reader quests <save> --data <Data folder> --filter <name> --details` (without `--data`, the quests have no names to filter on).

```
> sf-test-plan check examples\QuestExample.testplan.md --rules examples\QuestExample.logrules.json
examples\QuestExample.testplan.md: 5 groups, 10 checks, 5 smoke; 0 errors, 0 warnings
```

Copy the two files, change the names, the quest ID and the log lines to your own, and keep one check per stage.

## Papyrus logs

If you don't have a rule file yet, `sf-test-plan rules` (above) starts one from your plan. If your mod logs with `Debug.Trace` and you have a papyrus-log-check rule file for it, run papyrus-log-check on the log first, then give its JSON report to `logs`:

```
python papyrus_log_check.py "<Documents>\My Games\Starfield\Logs\Script\Papyrus.0.log" --rules BeaconMod.logrules.json
sf-test-plan logs out\logcheck-<time>.json --plan BeaconMod.testplan.md
```

Steps whose `log:` rules all passed are marked Pass, and any failed rule marks the step Fail. Steps the log couldn't prove get no mark, and the command says why. Marks from the log show a "Checked from the log" badge on the page.

## Troubleshooting

- Run the command again with `--verbose` to see what was read and decided, or `--log sf-test-plan.log` to save the same details to a file. The log names the plan, each group and step it read, each warning and why, and the files it wrote. Attach it when you report a problem.
- **"run ... isn't allowed"**: use only letters, digits, `.`, `_` and `-` in `run:`.
- **Marks are gone**: the page's `run:` or `mod:` changed, the plan file or its folder was renamed or moved, or the browser cleared its site data. A renamed or moved plan starts a new, empty round, so import the old marks file if you need them. Export before you rename or move a plan.
- **A step shows a mark from an older build**: marks are kept by step number. When a new build changes its steps, give it a new `run:` so it starts fresh.
- **Marks are per browser and per plan**: a browser keeps marks for a plan by its folder and file name, `mod:` and `run:`. Copies of the same page in that browser share marks, while another browser or computer starts empty. Export on one, and Import on the other.

This is what `--verbose` prints for the example plan:

```
> sf-test-plan check examples\Beacon.testplan.md --verbose
[verbose] sf-test-plan 0.5.1, Python 3.13.15, args ['check', 'examples\\Beacon.testplan.md', '--verbose']
[verbose] read plan examples\Beacon.testplan.md (1356 characters)
[verbose] parsed examples\Beacon.testplan.md: title 'Beacon Mod test plan', run 'beacon-0.1.0', 2 setup items, 3 groups, 6 checks (5 smoke), 0 problems
[verbose]   group 1 'Install and load' (line 13): 1.1 smoke, 1.2 smoke
[verbose]   group 2 'Main feature' (line 24): 2.1 smoke, 2.2 smoke, 2.3
[verbose]   group 3 'Save and load' (line 36): 3.1 smoke
examples\Beacon.testplan.md: 3 groups, 6 checks, 5 smoke; 0 errors, 0 warnings
```

## Background

New to testing mods? The STEP project's [Mod Testing guide](https://wiki.step-project.com/Guide:Mod_Testing) explains testing against a clean setup and with new and existing saves. It's written for Skyrim, but the method carries over.

## Known limits

These are known and left as they are, because they need an unusual setup or have a plain workaround:

- On Linux and macOS, `import` leaves the results file at mode 0600 and replaces a link with a plain file.
- `new` follows a symbolic link at the plan's name, unlike the other writing commands.
- A printed "then run" line whose path holds `$`, a backtick, `%` or `@` may not paste cleanly into PowerShell or cmd. The command itself works.
- `"r": null` in a marks file is refused by `import` but accepted by the page's Import. Neither the page nor `logs` writes null.
- A hand-edited browser store with a bad `saved` time shows "NaN" in the page's save line.
- In a smoke round the page's tally leaves unmarked deep checks out, while `import` counts them as not run. This is deliberate.
- A `--pins` key is the file name without its folder (a key written with its folder is cut to the file name), so two same-named files in different folders share one pin, and only one of them can be accepted.
- In one marks file that holds the same id twice (only a hand-merged file does), a newer log mark listed before an older page mark wins.
- A path typed with the Windows long-path prefix (`\\?\C:\...`) is not matched with its plain spelling of the same file, so the check that an output is not an input can miss it.

## For developers

GitHub Actions runs the unit tests on Windows and Linux with Python 3.10 and 3.13. It also checks that both systems build the same release zip, and it runs the page test with Chrome on Windows.

- **Release:** pushing a version tag (`v0.5.1`, say) makes GitHub Actions build the zip and its `.sha256` file from the tag with `build_release.py --tag`, once every test job has passed, and publish the release with the CHANGELOG entry as its text. Nobody uploads a release by hand. Locally, `python -I build_release.py` builds the same zip from the last commit.
- **Unit tests:** `python -I -m unittest discover -s tests`.
- **Page test:** `node tests\page_test.mjs <page.html> [screenshots folder]` tests the page's script in a browser. It needs Node 22 or newer (for its built-in WebSocket) and Google Chrome on Windows.
- **Chrome settings:** set `CHROME_PATH` if Chrome is somewhere else. Set `TP_CDP_WAIT` (1 to 600 seconds, default 30) to wait longer for Chrome to start. The test runs Chrome headless with the profile folder `%LOCALAPPDATA%\HeadlessChromeProfile`.

## Found a mistake?

Open an issue: https://github.com/taosecurity/sf-test-plan/issues

## Credits and License

sf-test-plan is by Richard Bejtlich. It grew out of the private test plan pages used for the author's own mods, and it uses only the [Python](https://www.python.org/) standard library. [PRIVACY.md](PRIVACY.md) says what the tool and the page store.

It is released under the MIT License; see [LICENSE](LICENSE).
