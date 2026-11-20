# Changelog

## Unreleased

- Page test: waits up to 30 seconds for Chrome to start (set `TP_CDP_WAIT`, from 1 to 600 seconds, to change it), because a fresh CI runner can take more than 10 seconds. One timer covers the whole start, including connecting to Chrome, so the test can't hang there, and the timeout message names the setting. The README now says the page test needs Node 22 or newer.

## 0.1.1 (2026-11-20)

- Page: when another tab removes the saved marks, the "Saved in this browser at ..." line no longer shows the old time.
- Page: Reset with damaged saved data now says the saved copy couldn't be read and was replaced, instead of counting marks held in memory as kept.
- Page: when the saved copy can't be read (found when the page opens, or after another tab's save), the page keeps the marks it shows instead of clearing them, writes nothing, and its save line warns that the next change replaces the unreadable copy (use Export to keep a copy).
- Tests run on GitHub Actions: unit tests on Windows and Linux with Python 3.10 and 3.13, a check that both systems build the same release zip, and the page test with Chrome on Windows.
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
