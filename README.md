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
2. Download `sf-test-plan-0.3.2.zip` from the [releases page](https://github.com/taosecurity/sf-test-plan/releases) and unpack it anywhere.
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
| `sf-test-plan build PLAN [--out PAGE] [--rules FILE]` | Checks the plan and writes the page (default: the plan's name with `.html`). |
| `sf-test-plan check PLAN [--rules FILE]` | Checks the plan for mistakes without writing anything. With `--rules`, it also checks every `log:` id against a papyrus-log-check rule file. |
| `sf-test-plan import MARKS --plan PLAN` | Adds a marks file (from the page's Export button) to `<plan>.results.json` as one results row, and prints the tally. Build again to show it on the page. |
| `sf-test-plan logs REPORT --plan PLAN [--mod NAME] [--out MARKS]` | Reads a papyrus-log-check JSON report and writes marks for the steps with `log:` ids. Import them on the page, or with `import`. |
| `sf-test-plan rules PLAN [--out FILE] [--from FILE] [--prefix TEXT] [--plugin NAME] [--force]` | Writes a starter papyrus-log-check rule file with a rule for each `log:` id in the plan, or adds the missing ids to the rule file you already have. |
| `sf-test-plan new PLAN [--mod NAME] [--force]` | Writes a starter plan. |

Every command also takes `--verbose` and `--log FILE`. The exit codes are:

- **0** means the command finished. Warnings are fine.
- **1** means the plan has errors. Each one is printed with its line number and the fix.
- **2** means a file can't be read or written, or an option is wrong.

`build`, `logs` and `rules` never write over the plan or the plan's results file, and `logs` never writes over its report. When the output (from `--out`, `--from` or the default name) is one of those files, or a hard link to one, the command stops with exit 2, writes nothing and suggests a name to give with `--out` (never a folder or a link; for `build` and `logs` either a new name or a plain file you can write that has no other hard link, and for `rules` one that doesn't exist yet). For all three, an output that is a symbolic link is refused too: give the real file with `--out`.

Some network shares, RAM disks and WSL folders (`\\wsl$`) give every file the id 0, so a hard link can't be detected there: on such a drive only the same path is refused, and the suggested name is one that doesn't exist yet.

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
Smoke test: 2 pass, 1 fail, 1 skip, 1 not run
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
Marks: logcheck-beacon.marks.json (open the page and use Import, or run: sf-test-plan import logcheck-beacon.marks.json --plan examples\Beacon.testplan.md)
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
- Without `--out`, the file is the plan's name with `.logrules.json` (`Beacon.testplan.md` gives `Beacon.logrules.json`). The command never replaces a file unless you add `--force`, and when it would write, it refuses an output file that is itself a symbolic link: give the real file with `--out`. It never writes over the plan or its results file, even with `--force` (see [Commands](#commands)).

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

## The page

- **Pass / Fail / Skip** on each step, and a note box. Click a chosen mark again to clear it.
- The tally at the top counts pass, fail, skip and not run. With a smoke test, only the smoke checks count until you mark a deep check. From then on the tally covers every check, and `import` calls the round a "Full test".
- **Export** downloads your marks as `<run>-marks-<date>.json`. **Import** reads one back (a tester's file, or one from `sf-test-plan logs`). For each step the newer mark wins, but a mark from the log never replaces one you made yourself.
- **Copy results** puts a plain-text summary on the clipboard, ready to paste into a bug report or a Nexus post.
- **Reset** clears the marks and notes on this page's steps in this browser. Marks that another build of the plan saved for steps this page doesn't have are kept, and the page says how many.
- Marks are kept in the browser's local storage for that page. A private window, or a browser that blocks storage, keeps them only until you close the tab. The page says so, so use Export before you close it.

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
[verbose] sf-test-plan 0.3.2, Python 3.13.15, args ['check', 'examples\\Beacon.testplan.md', '--verbose']
[verbose] read plan examples\Beacon.testplan.md (1356 characters)
[verbose] parsed examples\Beacon.testplan.md: title 'Beacon Mod test plan', run 'beacon-0.1.0', 2 setup items, 3 groups, 6 checks (5 smoke), 0 problems
[verbose]   group 1 'Install and load' (line 13): 1.1 smoke, 1.2 smoke
[verbose]   group 2 'Main feature' (line 24): 2.1 smoke, 2.2 smoke, 2.3
[verbose]   group 3 'Save and load' (line 36): 3.1 smoke
examples\Beacon.testplan.md: 3 groups, 6 checks, 5 smoke; 0 errors, 0 warnings
```

## Background

New to testing mods? The STEP project's [Mod Testing guide](https://wiki.step-project.com/Guide:Mod_Testing) explains testing against a clean setup and with new and existing saves. It's written for Skyrim, but the method carries over.

## For developers

GitHub Actions runs the unit tests on Windows and Linux with Python 3.10 and 3.13. It also checks that both systems build the same release zip, and it runs the page test with Chrome on Windows.

- **Unit tests:** `python -I -m unittest discover -s tests`.
- **Page test:** `node tests\page_test.mjs <page.html> [screenshots folder]` tests the page's script in a browser. It needs Node 22 or newer (for its built-in WebSocket) and Google Chrome on Windows.
- **Chrome settings:** set `CHROME_PATH` if Chrome is somewhere else. Set `TP_CDP_WAIT` (1 to 600 seconds, default 30) to wait longer for Chrome to start. The test runs Chrome headless with the profile folder `%LOCALAPPDATA%\HeadlessChromeProfile`.

## Found a mistake?

Open an issue: https://github.com/taosecurity/sf-test-plan/issues

## Credits and License

sf-test-plan is by Richard Bejtlich. It grew out of the private test plan pages used for the author's own mods, and it uses only the [Python](https://www.python.org/) standard library. [PRIVACY.md](PRIVACY.md) says what the tool and the page store.

It is released under the MIT License; see [LICENSE](LICENSE).
