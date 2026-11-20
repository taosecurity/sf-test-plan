# Changelog

## Unreleased

- The page test now waits up to 30 seconds for Chrome to start, because Chrome's first start on a fresh CI runner can take more than 10 seconds. Set `TP_CDP_WAIT` (1 to 600 seconds) to change the wait.
- One timer covers the whole start, including the connection to Chrome, so the test can't hang there. While the test waits for Chrome, a request for its page list that gets no answer is dropped after 5 seconds and sent again.
- If Chrome lists the page but the connection to it fails, the test stops at once with its own message. The timeout message names `TP_CDP_WAIT`.
- The README now says that the page test needs Node 22 or newer.

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
