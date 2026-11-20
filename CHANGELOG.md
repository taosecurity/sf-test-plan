# Changelog

## 0.1.0 (2026-11-19)

First release.

- `build`: one self-contained checklist page from a Markdown test plan: Pass / Fail / Skip and a note per step, smoke test and folded deep checks, Copy buttons for console commands, light and dark theme, phone width, no network loads.
- The page keeps marks in the browser, with Export and Import (JSON, `sf-test-plan-marks/1`), Copy results and Reset.
- `check`: finds plan mistakes (missing `run:`, duplicate ids, keys with no step, unknown `log:` ids with `--rules`, and more), each with its line number and the fix.
- `import`: adds a marks file to `<plan>.results.json`; `build` shows it as the page's Results log.
- `logs`: turns a papyrus-log-check (0.3.0 or later) JSON report into marks for steps with `log:` ids.
- `new`: writes a starter plan.
- `--verbose` and `--log FILE` on every command.
