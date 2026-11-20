# sf-test-plan formats

This file is the contract between the plan file, the builder, the page and other tools. Format version 1 (sf-test-plan 0.1.0).

## 1. The test plan (Markdown)

A plan is a UTF-8 text file, usually named `<Mod>.testplan.md`. It reads well as plain Markdown and on GitHub.

```markdown
# Beacon Mod test plan
run: beacon-0.1.0
mod: Beacon Mod
version: 0.1.0
zip: BeaconMod-0.1.0.zip

Free text here is the page's introduction. It can be several paragraphs.

## Before you start
- Install BeaconMod-0.1.0.zip with your mod manager.
- Turn on Papyrus logging (see the mod's README).

## 1 Install and load
Text right after a group heading is the group's introduction.

- [ ] Start a new game.
  Expect: no error message.
  smoke: yes
- [ ] Open Settings > Gameplay.
  Expect: a "Beacon" group with "Show Debug Messages (PC only)".

## 2 Main feature
- [ ] Type `player.additem 0001A2B3 1` in the console.
  Expect: a beacon in your inventory.
  log: placed, beacon-ready
  id: 2.1
```

### Rules

1. **Title.** The first `# ` line is the title. It is required.
2. **Header keys.** `key: value` lines right after the title (a blank line between the title and the first key is allowed). A blank line after the keys ends the header, so a later line such as `Warning: back up your saves.` is introduction text. Keys are case-insensitive.
   - `run` (required): a short id for this test round, such as `beacon-0.1.0`. Marks are saved under it, so a new build gets a new `run` and starts with empty marks. Allowed characters: letters, digits, `.`, `_`, `-`; 1 to 64 characters.
   - `mod`, `version`, `zip` (optional): shown in the page's facts box.
   - Any other header key is a warning (`unknown header key`).
3. **Introduction.** Any text after the header and before the first `## ` heading. Markdown inline only (see 6).
4. **Before you start.** A `## Before you start` heading (case-insensitive) holds a bullet list (`- ` or `* `). It becomes the numbered setup list. Its items are not checks.
5. **Groups.** `## <n> <title>`, where `<n>` is a whole number. Group numbers must be unique, and they need not be in order or without gaps. A `## ` heading without a number (other than Before you start) is an error. Text after the heading and before the first check is the group's introduction.
6. **Checks.** `- [ ] <step>` (also `- [x]`, `* [ ]`; the box state in the file is ignored). Indented lines (2 or more spaces, or a tab) right after it belong to the check:
   - `Expect: <text>`: what the tester should see. Optional. Several `Expect:` lines join with a space.
   - `smoke: yes`: the check is in the smoke test (see 7). `smoke: no` is the default.
   - `log: <rule id>[, <rule id> ...]`: papyrus-log-check rule ids that also prove this check.
   - `note: <text>`: a hint shown under the step in muted text.
   - `id: <g>.<n>`: pins the check's id. `<g>` must equal the group number.
   - Any other indented line that isn't `key:` continues the field above it (the step, its Expect or its note), joined with a space. So does an unindented line right after the check with no blank line between (Markdown's lazy continuation), unless it starts a new bullet. An indented `key:` with an unknown key is a warning, and the line is kept as step text.
7. **Ids.** By default a check's id is `<group>.<position>` (1-based, counting checks in that group). A pinned `id:` overrides it. Ids must be unique; a duplicate is an error. Later default ids don't move when an earlier check is pinned.
8. **Smoke test.** If any check has `smoke: yes`, the page shows those checks first, in file order, in a "Smoke test" box, and the rest fold into "Deep checks (optional)". A smoke list of more than 12 checks is a warning.
9. **Inline Markdown** allowed in the intro, group intros, steps, Expect and notes: `` `code` ``, `**bold**`, `*italic*`, `[text](https://...)` (http and https links only). Everything else is shown as literal text. Raw HTML is never passed through: `<` and `&` are escaped.
10. **Comments.** Text inside `<!-- ... -->` is ignored, also across lines. A comment that never closes hides the rest of the file and gives an `unclosed-comment` warning.
11. **Copy buttons.** A `` `code` `` span whose whole text is a console or PowerShell command (the `COMMAND_PATTERN` in `sftestplan/model.py`) gets a Copy button on the page.

### Problems `check` reports

Each problem has a level (`error` or `warning`), the file, the line number, and a message that says the fix.

| Code | Level | When |
|---|---|---|
| `no-title` | error | no `# ` line |
| `no-run` | error | no `run:` key |
| `bad-run` | error | `run` has characters outside the allowed set or is too long |
| `group-no-number` | error | a `## ` heading other than Before you start has no number |
| `dup-group` | error | two groups share a number |
| `dup-id` | error | two checks share an id |
| `bad-id` | error | a pinned id isn't `<g>.<n>` or its group part doesn't match |
| `orphan-key` | error | an indented `Expect:`/`smoke:`/`log:`/`note:`/`id:` line with no check above it |
| `no-checks` | error | the plan has no checks |
| `check-outside-group` | error | a `- [ ]` line before the first group or under Before you start |
| `empty-group` | warning | a group has no checks |
| `unknown-key` | warning | an unknown header key or check key |
| `big-smoke` | warning | more than 12 smoke checks |
| `unclosed-comment` | warning | a `<!--` with no `-->` after it |
| `unknown-log-id` | error | (only with `--rules`) a `log:` id not in the rule file's `expect` or `forbid` ids |

Exit codes for `check` and `build`: 0 = no errors (warnings allowed), 1 = errors, 2 = the file can't be read or the options are wrong.

## 2. The page

`build` writes one HTML file with the CSS and the script inline. It loads nothing from the network. The builder embeds:

- `<script type="application/json" id="tp-config">{"format":"sf-test-plan-page/1","run":...,"title":...,"tool":"sf-test-plan 0.1.0"}</script>`
- Each check as `<li class="check" data-id="2.1" data-group="2" data-smoke="0|1" data-log="placed beacon-ready">` holding `<div class="what"><div>step html</div><div class="expect">Expect: ...</div><div class="hint">note</div></div>`. The script adds the Pass/Fail/Skip control and the note box.
- `<span id="saved" class="saved"></span>` for the save status, the tally bar `<div class="bar" id="tally" data-total="N">`, and the toolbar `<div class="tools" id="tools">` holding `button`s with `data-act="export|import|copy|reset"` and a hidden `<input type="file" id="importfile" accept=".json,application/json">`.
- Smoke checks inside `<section id="smoke">`, the rest inside `<details id="deep">` when smoke is set; otherwise groups are `<section class="group" id="g<n>">`.
- `<code class="cmd">` on spans that match the command pattern (the script adds the Copy button).

The page saves marks in `localStorage` under `sf-test-plan:<run>:<plan>`, where `<plan>` is the `plan` value in tp-config: the first 12 hex digits of the SHA-256 of `<folder>/<file>` (the plan's own folder name and file name, lower case), `mod` (case and extra spaces ignored) and `run`, joined with newlines. Browsers share one storage area for every `file://` page, so this keeps two plans with the same `run` apart, while rebuilds of one plan in its folder share marks; editing the title keeps them, and moving or renaming the plan file starts empty (Export first). Marks are keyed by step id. Stored marks for ids the page doesn't have (from another build) are kept as they are, so two builds open at once never erase each other's marks; Reset clears only the page's own steps and says how many other marks it kept. **When a new build changes its steps, give it a new `run:`**, so its marks start fresh and no old mark sits on a renumbered step. If storage throws, the page keeps marks in memory and says so in `#saved`. When another tab of the same page saves (or the browser's site data is cleared), this page takes that save, so marks, clears and Reset carry over; only a note typed here that wasn't saved yet is laid on top of it.

Import merges by id: the newer `at` wins, except that a mark with `src: "log"` never replaces a mark the tester set on the page. A newer log mark may replace an older log mark, but a note the tester typed on that check stays. Typing a note doesn't change where a log mark came from, but like any change it moves the entry's `at`, so a log file older than the tester's last change to that step doesn't replace it.

## 3. Marks file (`marks.json`)

Written by the page's Export button and by `sf-test-plan logs`. Read by `import` and the page's Import button.

```json
{
  "format": "sf-test-plan-marks/1",
  "run": "beacon-0.1.0",
  "title": "Beacon Mod test plan",
  "exported": "2026-11-19T21:04:00Z",
  "tool": "sf-test-plan 0.1.0",
  "checks": [
    {"id": "1.1", "r": "pass", "n": "", "t": "Start a new game.", "g": 1, "at": "2026-11-19T20:58:10Z", "src": "page"}
  ]
}
```

- `r` is `pass`, `fail`, `skip` or `""` (no mark, only a note). `n` is the note, `t` the step text (plain, at most 300 characters), `g` the group number, `at` an ISO 8601 UTC time, `src` `page` or `log` (where the mark came from). Optional `ns: "page"` says the note was typed by a person; the page's Import reads it, so a later log import keeps that note even when the mark came from the log. `sf-test-plan import` ignores it (every note goes into the results notes).
- A reader must refuse a different major format (`sf-test-plan-marks/2`), and must ignore unknown fields.
- When the page imports a file whose `run` differs from its own, it asks before merging. Merging goes by `id`: the newer `at` wins.

## 4. Results file (`<plan>.results.json`)

Written next to the plan by `import`. Newest round first. `build` shows it as the page's "Results log".

```json
{
  "format": "sf-test-plan-results/1",
  "rows": [
    {"date": "2026-11-19", "run": "beacon-0.1.0", "test": "Smoke test", "happened": "7 pass, 1 fail, 0 skip, 2 not run",
     "notes": "1.2 fail: no Beacon group in Gameplay options."}
  ]
}
```

`date`, `test`, `happened` and `notes` match the private kit's results.json rows, so either tool can read them.

## 5. papyrus-log-check input (`logs`)

`sf-test-plan logs` reads the JSON report papyrus-log-check (0.3.0 or later) writes: a `mods` list, each with `mod`, `status` and `rules`, each rule with `kind`, `id` and `status` (`PASS`, `FAIL`, `NOT SEEN`). It uses the `mods` entry whose `mod` equals the plan's `mod:` key (case-insensitive), or the one named by `--mod`, or the only entry; otherwise it stops with exit 2 and lists the mods in the report. If that entry's status is `NOT LOADED`, it writes no marks and says so (exit 0). For a `forbid` rule, PASS means the forbidden line never appeared. For each check with `log:` ids:
- every listed rule PASS gives `r: pass`;
- any listed rule FAIL gives `r: fail`, with the rule ids and status in `n`;
- otherwise the check gets no entry in the marks file (an empty entry could replace a tester's mark), and the command's printed lines say which rule wasn't seen.
Marks it writes have `src: "log"`.
