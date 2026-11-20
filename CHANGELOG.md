# Changelog

## 0.1.1 (2026-11-20)

- Page: when another tab removes the saved marks, the "Saved in this browser at ..." line no longer shows the old time.
- Page: Reset with damaged saved data now says the saved copy couldn't be read and was replaced, instead of counting marks held in memory as kept.
- Page: when another tab writes saved data that can't be read, this tab keeps the marks it shows instead of clearing them, and its save line warns that they aren't saved until the next change (or use Export).
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
