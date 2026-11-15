# SPDX-License-Identifier: MIT
"""The requirement summary: charts and per-group counts of implementation and evidence.

1.4.0 W14 (owner 2026-11-15: "summary page of requirements implementation", "requirements and
test piegraph"). The summary groups requirements by their id with the trailing number dropped
(`REQ-W-001` → `REQ-W`) and counts, per group: requirements, IMPLEMENTED (an implementing function
is tagged), TESTED (a test is linked, from any source), each evidence tier, and — when
`wiki.tests.min_layers` is set — the tested requirements whose tests span FEWER LAYERS than that,
so single-layer coverage is visible instead of reading as tested.

Two donuts summarise the whole trace: requirements by tier, and distinct tests by status.

@brief Summary page and the trace charts.
@version 1
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from .charts import donut

## Tiers and test statuses, in chart order.
TIERS = ("PASS", "GAP", "TARGET", "NOT_RUN", "MISSING")
STATUSES = ("passed", "failed", "error", "skipped", "absent")
_GROUP = re.compile(r"[-_.]?\d+$")


## @brief The two trace donuts as one HTML block.
## @param evidence Requirement evidence rows.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-012
def charts_block(evidence: list) -> str:
    """A TEST LINKED TO SEVERAL REQUIREMENTS is one test: the status donut counts distinct tests.

    @brief Draw the charts.
    @return HTML.
    """
    tiers = [(t, sum(1 for r in evidence if r.tier == t)) for t in TIERS]
    tests = dict(t for r in evidence for t in r.tests)
    statuses = [(s, sum(1 for v in tests.values() if v == s)) for s in STATUSES]
    return (
        '<div class="charts">'
        f'<div class="chart-card"><h4>Requirements by tier</h4>{donut(tiers, "Requirements by tier")}</div>'
        f'<div class="chart-card"><h4>Tests by status</h4>{donut(statuses, "Tests by status")}</div>'
        "</div>"
    )


## @brief Write the summary page.
## @param evidence Requirement evidence rows.
## @param min_layers The layer minimum, or None.
## @param source The Sphinx source directory.
## @param burndown A burndown SVG for a versioned site, or "".
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-012
def summary_page(evidence: list, min_layers: int | None, source: Path, burndown: str = "") -> str:
    """@brief Render the summary. @return Page name."""
    implemented = sum(1 for r in evidence if r.implementers)
    tested = sum(1 for r in evidence if r.tests)
    lines = [
        "# Summary",
        "",
        f"{len(evidence)} requirements: {implemented} implemented, {tested} tested, "
        f"{sum(1 for r in evidence if r.tier == 'PASS')} passing.",
        "",
        "```{raw} html",
        charts_block(evidence),
        "```",
        "",
    ]
    if burndown:
        lines += [
            "## Burndown",
            "",
            "```{raw} html",
            f'<div class="chart-card">{burndown}</div>',
            "```",
            "",
        ]
    lines += ["## By group", "", "```{raw} html", _group_table(evidence, min_layers), "```", ""]
    (source / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "summary"


## @brief The per-group table.
## @param evidence Requirement evidence rows.
## @param min_layers The layer minimum, or None (no layer column).
## @return HTML.
## @version 1
## @dg_internal
def _group_table(evidence: list, min_layers: int | None) -> str:
    """@brief Count per group. @return HTML."""
    groups: dict[str, list] = {}
    for row in evidence:
        groups.setdefault(_GROUP.sub("", row.req_id) or row.req_id, []).append(row)
    head = ["group", "requirements", "implemented", "tested", *TIERS]
    if min_layers is not None:
        head.append(f"below {min_layers} layers")
    rows = []
    for group, members in sorted(groups.items()):
        cells = [
            len(members),
            sum(1 for r in members if r.implementers),
            sum(1 for r in members if r.tests),
            *(sum(1 for r in members if r.tier == t) for t in TIERS),
        ]
        if min_layers is not None:
            cells.append(sum(1 for r in members if r.tests and len(r.layers or ()) < min_layers))
        rows.append(
            f"<tr><td>{escape(group)}</td>"
            + "".join(f'<td class="n">{c}</td>' for c in cells)
            + "</tr>"
        )
    header = "".join(f"<th>{escape(h)}</th>" for h in head)
    return f'<table class="clew"><thead><tr>{header}</tr></thead><tbody>{"".join(rows)}</tbody></table>'
