"""Data model shared by every part of sf-test-plan (master-owned; see FORMAT.md)."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

TOOL = "sf-test-plan"
VERSION = "0.3.1"
TOOL_ID = f"{TOOL} {VERSION}"
URL = "https://github.com/taosecurity/sf-test-plan"

PAGE_FORMAT = "sf-test-plan-page/1"
MARKS_FORMAT = "sf-test-plan-marks/1"
RESULTS_FORMAT = "sf-test-plan-results/1"

RUN_RE = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
HEADER_KEYS = ("run", "mod", "version", "zip")
CHECK_KEYS = ("expect", "smoke", "log", "note", "id")
SMOKE_WARN = 12
SETUP_TITLE = "before you start"
RESULTS = ("pass", "fail", "skip", "")

# A <code> span whose whole text matches gets a Copy button (ported from the private kit's testplan.js, 2026-11-11).
COMMAND_PATTERN = (
    r"^(?:player\.\w+\s+\S.*"
    r"|(?:getav|setav|getstage|getstagedone|setstage|completequest|startquest|stopquest|resetquest|cqf|cgf|coc|cow"
    r"|help|GetGlobalValue|tgm|tcl|tai)\s+\S.*"
    r"|set\s+\S+\s+to\s+\S.*"
    r"|sglv(?:\s*\|.*)?"
    r"|sfse_plugin_console_api_\w+"
    r"|\.\\[\w.-]+(?:\.exe)?(?:\s.*)?"
    r"|powershell\s+.*"
    r"|(?:[A-Z][A-Z0-9_]*=\S*\s+)*\./[\w.-]+(?:\s.*)?"
    r"|(?:printf|unset|sudo|export|mkdir|tar|cd|while|mv|bash)\s+\S.*)$"
)
COMMAND_RE = re.compile(COMMAND_PATTERN)


@dataclass
class Problem:
    level: str      # "error" or "warning"
    code: str       # see FORMAT.md, "Problems check reports"
    line: int       # 1-based; 0 when the problem is about the whole file
    message: str    # says what is wrong and the fix

    def format(self, path: str) -> str:
        where = f"{path}:{self.line}" if self.line else path
        return f"{where}: {self.level} {self.code}: {self.message}"


@dataclass
class Check:
    id: str                 # "2.1"
    group: int
    step: str               # raw Markdown inline text
    expect: str = ""
    note: str = ""
    smoke: bool = False
    log: list[str] = field(default_factory=list)
    line: int = 0
    pinned: bool = False


@dataclass
class Group:
    number: int
    title: str
    intro: str = ""         # raw Markdown, paragraphs separated by blank lines
    checks: list[Check] = field(default_factory=list)
    line: int = 0


@dataclass
class Plan:
    title: str = ""
    run: str = ""
    mod: str = ""
    version: str = ""
    zip: str = ""
    intro: str = ""
    setup: list[str] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    path: str = ""
    problems: list[Problem] = field(default_factory=list)

    def checks(self) -> list[Check]:
        return [c for g in self.groups for c in g.checks]

    def smoke(self) -> list[Check]:
        return [c for c in self.checks() if c.smoke]

    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level == "error"]


class SetupError(Exception):
    """Bad input or options (exit 2). The message names the file and the fix."""
