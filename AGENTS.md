# AGENTS.md: sf-test-plan for AI assistants

Plain steps for an AI assistant helping someone use sf-test-plan. Every command here was run once on sf-test-plan
0.3.2 before release. The [README](README.md) has the full description and [FORMAT.md](FORMAT.md) the exact formats.

## 1. What it is for

sf-test-plan turns a Markdown test plan (`<Mod>.testplan.md`) into one self-contained HTML checklist page. A tester
opens the page in a browser, marks each step Pass, Fail or Skip with a note, and exports the marks as JSON. The tool
can add exported marks to a results file next to the plan, turn a papyrus-log-check JSON report into marks, and
start a papyrus-log-check rule file from the plan's `log:` ids.

Use it when a mod author wants a repeatable, tick-off test plan for a Starfield mod (or any manual test). Don't use
it for automated tests, and don't treat its results as proof a mod is safe: it records what a person saw.

## 2. Prerequisites

- Python 3.10 or newer (tested on 3.10 and 3.13, on Windows and Linux). Standard library only: nothing to install.
- Windows, Linux or macOS. Any current browser (Chrome, Edge, Firefox, Safari) for the page.
- Optional: papyrus-log-check 0.3.0 or newer, for `logs`.

## 3. Install

Download `sf-test-plan-0.3.2.zip` from https://github.com/taosecurity/sf-test-plan/releases and check it against the
`.sha256` file:

    certutil -hashfile sf-test-plan-0.3.2.zip SHA256

On Linux or macOS: `sha256sum -c sf-test-plan-0.3.2.zip.sha256`. Unpack it anywhere. The commands below run from
the unpacked folder; `python -I sf_test_plan.py` works everywhere, `.\sf-test-plan.cmd` (Windows, with the `.\`) and
`./sf-test-plan` (Linux, macOS) are short forms.

## 4. Prove the install works

    python -I sf_test_plan.py check examples/Beacon.testplan.md --rules examples/Beacon.logrules.json

It prints `examples/Beacon.testplan.md: 3 groups, 6 checks, 5 smoke; 0 errors, 0 warnings` and exits with code 0.

## 5. Common tasks

- Start a plan for a mod:

      python -I sf_test_plan.py new MyMod.testplan.md --mod "My Mod"

- Check a plan after editing it (fix every `error`; `warning`s are advice):

      python -I sf_test_plan.py check MyMod.testplan.md

- Build the page (writes `MyMod.testplan.html` next to the plan):

      python -I sf_test_plan.py build MyMod.testplan.md

- After a test round, add the marks file the tester exported to the plan's results, then rebuild to show them:

      python -I sf_test_plan.py import my-mod-0.1.0-marks-20261120-2130.json --plan MyMod.testplan.md
      python -I sf_test_plan.py build MyMod.testplan.md

- Mark steps from the Papyrus log (run papyrus-log-check first; it writes a `logcheck-*.json` report):

      python -I sf_test_plan.py logs out/logcheck-20261120-213000.json --plan MyMod.testplan.md

  It writes `out/logcheck-20261120-213000.marks.json`. Import that on the page, or with `import`.

- Start a papyrus-log-check rule file from the plan's `log:` ids (writes `MyMod.logrules.json` next to the plan,
  one `expect` rule per id; it refuses to replace a file without `--force`):

      python -I sf_test_plan.py rules MyMod.testplan.md

  Then edit each new rule's `re` to match the line the mod really writes, move rules for lines that must never
  appear to `forbid`, and run `check MyMod.testplan.md --rules MyMod.logrules.json`. Use `--prefix "MYMOD:"` when
  the mod's log prefix isn't its `mod:` name, and `--plugin MyMod.esm` for its plugin file names.

- After adding steps with new `log:` ids, add only the missing rules to the existing rule file (keeps every rule and
  field already there):

      python -I sf_test_plan.py rules MyMod.testplan.md --from MyMod.logrules.json --force

  New patterns start with the file's `prefix`. If it prints a WARNING that the prefix isn't one fixed text, the
  rules it just added start with the mod name instead: delete those rules from the file, then rerun with
  `--prefix "MYMOD:"` and `--force`. That writes the file's `prefix` (keeping a leading `^` and a trailing `$`)
  and adds the deleted rules again with the right start; it writes the new `prefix` even when no id is missing.
  Rules you didn't delete keep their patterns. `--plugin` with `--from` is refused (exit 2): edit the file's
  `plugins` list instead. When something would be written, an output file that is itself a symbolic link is refused (exit 2): give the real file with `--out`. A linked `--from` file with nothing to add still exits 0.

- Start a new test round for a new build: change the plan's `run:` line (for example `my-mod-0.1.1`) and build again.
  The page then starts with empty marks.

## 6. Writing or editing a plan for the user

Follow FORMAT.md section 1 exactly. In short: `# Title`, then `run:` (required), `mod:`, `version:`, `zip:`; a
`## Before you start` bullet list; groups as `## <n> <title>`; steps as `- [ ] <step>` with indented `Expect:`,
`smoke: yes`, `log: <ids>`, `note:`, `id: <g>.<n>` lines. Aim for about 5 to 8 smoke steps (advice only: `check`
warns only above 12). Put console commands in backticks.
Run `check` after every edit and fix what it reports before building.

## 7. Inputs, outputs, exit codes, logs

| Command | Reads | Writes |
|---|---|---|
| `build` | the plan; `<plan>.results.json` if present; `--rules` file if given | the page (`--out`, default `<plan>.html`) |
| `check` | the plan; `--rules` file if given | nothing |
| `import` | a marks file; the plan; the results file | `<plan>.results.json` (new row first) |
| `logs` | a papyrus-log-check JSON report; the plan | a marks file (`--out`, default `<report>.marks.json`) |
| `rules` | the plan; the `--from` rule file if given | a rule file (`--out`, default the `--from` file, else `<plan name>.logrules.json`; refuses to replace a file without `--force`, never writes over the plan, and refuses a symbolic link as the output); writes nothing when no id is missing |
| `new` | nothing | the starter plan (refuses to replace a file without `--force`) |

`<plan>.results.json` means the plan's name without `.md`, plus `.results.json`
(`MyMod.testplan.md` gives `MyMod.testplan.results.json`). The page, rule file and results file names drop only
`.md` (the rule file drops `.testplan.md`), so a plan named `Cool.Mod.txt` gives the mod name "Cool.Mod" but the
files `Cool.Mod.txt.html`, `Cool.Mod.txt.logrules.json` and `Cool.Mod.txt.results.json`.

Exit codes: 0 done (warnings allowed); 1 the plan has errors (printed as `file:line: error code: message`); 2 bad
input or setup (a file can't be read or written, a folder given where a file belongs, bad JSON, a marks file in another format, a wrong option).

Logs: add `--verbose` to print details on stderr, or `--log FILE` to write them to a file. Ask the user for that log
when something goes wrong.

## 8. Limits

- It never uploads anything and makes no network connections; the page loads nothing from the internet.
- It never changes the plan file. `import` only adds a row to the results file and refuses to overwrite a broken one.
- Marks live in the browser's local storage for that page file. A private window keeps them only until the tab
  closes. Marks are kept per plan (its folder and file name, mod and run) and by step number, so give a new build
  that changes its steps a new `run:`. Rebuilds of a plan in the same browser share them, and
  another browser or computer starts empty. Export to move them. A mark imported from `logs` never replaces a
  tester's own mark or note. From 0.2.0 on, a page never writes over marks that a newer sf-test-plan
  saved; it keeps its marks in memory and says to use Export.
- `rules` only guesses each pattern (the prefix and the id). It can't know the mod's real log lines or which ids
  are lines that must never appear, so a person must edit the file before trusting its results.
- It doesn't run the game, read saves, or decide whether a mod works: a person marks the steps, and `logs` marks only
  what the log rules prove.
