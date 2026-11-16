# SPDX-License-Identifier: MIT
"""The trace summary: charts and per-group counts of implementation and evidence (shown at the top of
the requirements page — owner 2026-11-15: one page, not two).

1.4.0 W14 (owner 2026-11-15: "summary page of requirements implementation", "requirements and
test piegraph"). The summary groups requirements by their id with the trailing number dropped
(`REQ-W-001` → `REQ-W`) and counts, per group: requirements, IMPLEMENTED (an implementing function
is tagged), TESTED (a test is linked, from any source), each evidence tier, and — when
`wiki.tests.min_layers` is set — the tested requirements whose tests span FEWER LAYERS than that,
so single-layer coverage is visible instead of reading as tested.

Two donuts summarise the whole trace: requirements by tier, and distinct tests by status.

@brief Trace charts, group cards and the per-group table.
@version 2
"""

from __future__ import annotations

import re
from html import escape

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


## @brief The group of a requirement id: the id with its trailing number dropped.
## @param req_id The id.
## @return The group.
## @version 1
## @req REQ-DDB-WIKI-012
def group_of(req_id: str) -> str:
    """@brief `REQ-W-001` → `REQ-W`. @return Group."""
    return _GROUP.sub("", req_id) or req_id


## @brief One card per requirement group: its tier progress, counts, and a filter for the list.
## @param evidence Requirement evidence rows.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-022
def group_cards(evidence: list) -> str:
    """REQUIREMENTS FRONT AND CENTRE (owner 2026-11-15): the cards are the requirements page's
    first view; a card filters the list below it to its group.

    @brief Group cards.
    @return HTML.
    """
    groups: dict[str, list] = {}
    for row in evidence:
        groups.setdefault(group_of(row.req_id), []).append(row)
    cards = []
    for group, members in sorted(groups.items()):
        segs = "".join(
            f'<span class="seg c-{t}" style="flex:{n}" title="{t} {n}"></span>'
            for t in TIERS
            if (n := sum(1 for r in members if r.tier == t))
        )
        passing = sum(1 for r in members if r.tier == "PASS")
        cards.append(
            f'<button type="button" class="group-card" data-req-filter="{escape(group)}" '
            f'aria-pressed="false"><span class="g-name">{escape(group)}</span>'
            f'<span class="g-count">{passing}/{len(members)} passing</span>'
            f'<span class="g-bar">{segs}</span>'
            f'<span class="g-sub">{sum(1 for r in members if r.implementers)} implemented · '
            f"{sum(1 for r in members if r.tests)} tested</span></button>"
        )
    return f'<div class="group-cards">{"".join(cards)}</div>'


## @brief The per-group table.
## @param evidence Requirement evidence rows.
## @param min_layers The layer minimum, or None (no layer column).
## @return HTML.
## v2: groups through `group_of`.
## @version 2
## @req REQ-DDB-WIKI-012
def group_table(evidence: list, min_layers: int | None) -> str:
    """@brief Count per group. @return HTML."""
    groups: dict[str, list] = {}
    for row in evidence:
        groups.setdefault(group_of(row.req_id), []).append(row)
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
    header = "".join(
        f'<th class="n">{escape(h)}</th>' if i else f"<th>{escape(h)}</th>"
        for i, h in enumerate(head)
    )
    return (
        f'<div class="table-wrap"><table class="clew groups"><thead><tr>{header}</tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div>"
    )
