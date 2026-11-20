# sf-test-plan

**Turn a plain-text test plan for your Starfield mod into a checklist page you tick off while you play.**

You write the steps in a Markdown file: what to do, and what you should see. sf-test-plan makes one web page from it.
Open the page in any browser beside the game (or on your phone), and mark each step Pass, Fail or Skip with a note.
Your marks stay in that browser. **Export** saves them to a file you can keep, share with a tester, or turn into a
results log next to your plan. If your mod writes Papyrus log lines, sf-test-plan can also read a
[papyrus-log-check](https://github.com/taosecurity/papyrus-log-check) report and mark the steps the log proves.

It needs only Python. The page works offline, loads nothing from the internet, and nothing is ever uploaded.

For AI assistants: read [AGENTS.md](AGENTS.md).

## First run (two minutes)

1. Install Python 3.10 or newer (tested on 3.10 and 3.13, on Windows and Linux; [python.org](https://www.python.org/downloads/); on Windows tick "Add python.exe to PATH").
2. Download `sf-test-plan-0.1.1.zip` from the [releases page](https://github.com/taosecurity/sf-test-plan/releases) and unpack it anywhere.
3. Open a terminal in the unpacked folder and build the example page:

   ```
   .\sf-test-plan.cmd build examples\Beacon.testplan.md
   ```

   (On Linux or macOS: `./sf-test-plan build examples/Beacon.testplan.md`. Anywhere: `python sf_test_plan.py build ...`. The examples below write just `sf-test-plan`: use whichever form works for you, or put the folder on your PATH.)

4. Open `examples\Beacon.testplan.html` in your browser. Click Pass on a step, type a note, reload the page: your marks are still there.

Then make your own plan:

```
sf-test-plan new MyMod.testplan.md --mod "My Mod"
sf-test-plan build MyMod.testplan.md
```

`new` writes a starter plan with comments explaining each part. Edit it in any text editor and build again.

## Writing a plan

```markdown
# Beacon Mod test plan
run: beacon-0.1.0
mod: Beacon Mod
version: 0.1.0

What this round tests, in a sentence or two.

## Before you start
- Install BeaconMod-0.1.0.zip and start a new game.

## 1 Install and load
- [ ] Open Settings > Gameplay.
  Expect: a "Beacon" group.
  smoke: yes

## 2 Main feature
- [ ] Type `player.additem 0001A2B3 1` in the console.
  Expect: one Beacon in your inventory.
  log: placed
```

- `run:` names this test round. Marks are saved under it, so **change it for each new build** (for example `beacon-0.1.1`) and the page starts fresh while the old marks stay in their own file.
- `## <number> <title>` starts a group of steps. `- [ ] ...` is one step.
- Under a step: `Expect:` (what you should see), `smoke: yes` (part of the short smoke test), `note:` (a hint), `log:` (papyrus-log-check rule ids that also prove this step), `id: 2.4` (keep a step's number fixed).
- Console commands in backticks get a **Copy** button on the page.

When any step has `smoke: yes`, the page puts those first in a "Smoke test" box and folds the rest into "Deep checks (optional)". Five to eight smoke steps is a good size: the mod loads, its options are there, its main feature works once, and a save and load.

The whole format, every warning and every file sf-test-plan reads or writes are in [FORMAT.md](FORMAT.md).

## Commands

| Command | What it does |
|---|---|
| `sf-test-plan build PLAN [--out PAGE] [--rules FILE]` | Checks the plan and writes the page (default: the plan's name with `.html`). |
| `sf-test-plan check PLAN [--rules FILE]` | Checks the plan for mistakes without writing anything. With `--rules`, also checks every `log:` id against a papyrus-log-check rule file. |
| `sf-test-plan import MARKS --plan PLAN` | Adds a marks file (from the page's Export button) to `<plan>.results.json` as one results row, and prints the tally. Build again to show it on the page. |
| `sf-test-plan logs REPORT --plan PLAN [--mod NAME] [--out MARKS]` | Reads a papyrus-log-check JSON report and writes marks for the steps with `log:` ids. Import them on the page, or with `import`. |
| `sf-test-plan new PLAN [--mod NAME] [--force]` | Writes a starter plan. |

Every command also takes `--verbose` and `--log FILE`.
Exit codes: **0** done (warnings are fine), **1** the plan has errors (each one is printed with its line number and the fix), **2** a file can't be read or written, or an option is wrong.

## The page

- **Pass / Fail / Skip** on each step, and a note box. Click a chosen mark again to clear it.
- The tally at the top counts pass, fail, skip and not run. With a smoke test, only the smoke checks count until you mark a deep check; from then on the tally covers every check (and `import` calls the round a "Full test").
- **Export** downloads your marks as `<run>-marks-<date>.json`. **Import** reads one back (a tester's file, or one from `sf-test-plan logs`); for each step, the newer mark wins, but a mark from the log never replaces one you made yourself.
- **Copy results** puts a plain-text summary on the clipboard, ready to paste into a bug report or a Nexus post.
- **Reset** clears the marks and notes on this page's steps in this browser. Marks another build of the plan saved for steps this page doesn't have are kept, and the page says how many.
- Marks are kept in the browser's local storage for that page. A private window, or a browser that blocks storage, keeps them only until you close the tab: the page says so, so use Export before you close it.

## Papyrus logs

If your mod logs with `Debug.Trace` and you have a papyrus-log-check rule file for it:

```
python papyrus_log_check.py "<Documents>\My Games\Starfield\Logs\Script\Papyrus.0.log" --rules BeaconMod.logrules.json
sf-test-plan logs out\logcheck-<time>.json --plan BeaconMod.testplan.md
```

Steps whose `log:` rules all passed are marked Pass; any failed rule marks the step Fail. Steps the log couldn't prove get no mark, and the command says why. Marks from the log show a "Checked from the log" badge on the page.

## Troubleshooting

- Run the command again with `--verbose` to see what was read and decided, or `--log sf-test-plan.log` to save the same details to a file. The log names the plan, each group and step it read, each warning and why, and the files it wrote. Attach it when you report a problem.
- **"run ... isn't allowed"**: use only letters, digits, `.`, `_` and `-` in `run:`.
- **Marks are gone**: the page's `run:` or `mod:` changed, the plan file or its folder was renamed or moved (a new round starts empty: import the old marks file if you need them), or the browser cleared its site data. Export before you rename or move a plan.
- **A step shows a mark from an older build**: marks are kept by step number. When a new build changes its steps, give it a new `run:` so it starts fresh.
- **Marks are per browser and per plan**: a browser keeps marks for a plan by its folder and file name, `mod:` and `run:`, so copies of the same page in that browser share marks, while another browser or computer starts empty. Export on one, Import on the other.

## Background

New to testing mods? The STEP project's [Mod Testing guide](https://wiki.step-project.com/Guide:Mod_Testing) explains testing against a clean setup and with new and existing saves. It's written for Skyrim, but the method carries over.

## For developers

GitHub Actions runs the unit tests on Windows and Linux with Python 3.10 and 3.13, checks that both systems build the same release zip, and runs the page test with Chrome on Windows. Unit tests: `python -I -m unittest discover -s tests`. The page script's browser test, `node tests\page_test.mjs <page.html> [screenshots folder]`, needs Node 18+ and Google Chrome on Windows (set `CHROME_PATH` if Chrome is elsewhere, and `TP_CDP_WAIT` to wait longer than 30 seconds for Chrome to start); it runs Chrome headless with the profile folder `%LOCALAPPDATA%\HeadlessChromeProfile`.

## License and credits

MIT License (see [LICENSE](LICENSE)). By Richard Bejtlich. sf-test-plan grew out of the private test plan pages used for the author's own mods. [PRIVACY.md](PRIVACY.md) says what the tool and page store.
