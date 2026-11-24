# SPDX-License-Identifier: MIT
"""A short evidence summary for a CI run's summary tab (#72 item 12, 2.1).

#72 (an adopter, 2026-11-23): one Markdown file per build for the run's summary — Azure DevOps'
`##vso[task.uploadsummary]`, GitHub's `$GITHUB_STEP_SUMMARY` — holding the requirements by tier,
how many are implemented, this run's tests by result, and line and branch coverage. `clew wiki
build --out X` writes it as `X/summary.md`, beside `X/html`.

WHAT WAS NOT MEASURED SAYS SO: no test report read is a sentence, never "0 passed"; no Cobertura
report is "not measured", never 0%.

@brief Write the CI evidence summary.
@version 1
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from typing import Any

## The requirement tiers, in the order the summary lists them.
_TIERS = ("PASS", "GAP", "NOT_RUN", "MISSING", "TARGET", "EXEMPT")
## Test results, in the order the summary lists them.
_RESULTS = ("passed", "failed", "error", "skipped")


## @brief The summary's Markdown.
## @param title The wiki's title.
## @param evidence The graded requirements.
## @param results This run's test results, by test.
## @param coverage The Cobertura report, or None.
## @return Markdown.
## @version 1
## @req REQ-DDB-WIKI-002
def ci_summary(
    title: str, evidence: list[Any], results: dict[str, Any], coverage: Path | None
) -> str:
    """@brief Summary. @return Markdown."""
    tiers = Counter(r.tier for r in evidence)
    implemented = sum(1 for r in evidence if r.implementers)
    lines = [
        f"## {title} — clew evidence",
        "",
        f"**{len(evidence)}** requirements · {implemented} implemented",
        "",
        "| tier | requirements |",
        "|---|---|",
        *(f"| {t} | {tiers[t]} |" for t in _TIERS if tiers[t]),
        "",
        _tests_line(results),
        "",
        _coverage_line(coverage),
    ]
    return "\n".join(lines) + "\n"


## @brief This run's tests by result, or a sentence saying none was read.
## @param results Results by test.
## @return One line.
## @version 1
## @utility
def _tests_line(results: dict[str, Any]) -> str:
    """@brief Tests. @return Text."""
    if not results:
        return "No test report was read for this build."
    counts = Counter(r.status for r in results.values())
    shown = ", ".join(f"{counts[s]} {s}" for s in _RESULTS if counts[s])
    return f"**{len(results)}** tests: {shown}"


## @brief Line and branch coverage from a Cobertura report's root, or "not measured".
## @param coverage The report, or None.
## @return One line.
## @version 1
## @utility
def _coverage_line(coverage: Path | None) -> str:
    """A rate the report does not carry is left out, not shown as 0%.

    @brief Coverage.
    @return Text.
    """
    if coverage is None or not Path(coverage).is_file():
        return "Coverage: not measured."
    try:
        root = ET.parse(coverage).getroot()
    except ET.ParseError as exc:
        return f"Coverage: {Path(coverage).name} could not be read ({exc})."
    rates = [
        f"{name} {float(root.get(attr)) * 100:.1f}%"
        for name, attr in (("line", "line-rate"), ("branch", "branch-rate"))
        if root.get(attr) not in (None, "")
    ]
    return "Coverage: " + (" · ".join(rates) if rates else "not measured.")
