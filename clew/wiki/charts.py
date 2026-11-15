# SPDX-License-Identifier: MIT
"""Inline-SVG charts for the wiki: donuts of counts, and a burndown across versions.

1.4.0 W14 and W17 (owner 2026-11-15: "requirements and test piegraph not represented",
"burndown via a ROADMAP.md"). No charting library and no script: each chart is an SVG string
styled by the theme's tokens (`c-<label>` classes), with every segment carrying `data-label` /
`data-count` and a `<title>`, so the figure is inspectable and a reader without colour vision
still has the legend's numbers.

THE BURNDOWN plots OPEN requirements — every tier but PASS and TARGET — at each recorded version,
in recording order. ROADMAP.md headings that name a version become milestones: a milestone at a
recorded version marks that point; one not yet recorded is drawn AHEAD of the data, and the ideal
line runs from the first version's open count to zero at the last milestone.

@brief Donut and burndown SVG charts.
@version 1
"""

from __future__ import annotations

import math
import re
from html import escape
from pathlib import Path

## Tiers that count as closed in a burndown.
CLOSED = ("PASS", "TARGET")
## A heading that LEADS with a version (optionally after "Roadmap to", "Milestone", "Release"):
## v1.2, 1.2.3, v0.8.0-rc1. A version mentioned later in a heading is not a milestone.
_VERSION = re.compile(
    r"^(?:(?:roadmap\s+to|milestone|release)\s+)?(v?\d+\.\d+(?:\.\d+)?(?:[-+][\w.]+)?)\b",
    re.IGNORECASE,
)


## @brief A donut of labelled counts with its legend.
## @param counts (label, count) in drawing order; zero counts are listed, not drawn.
## @param title The chart's accessible title.
## @return SVG markup.
## @version 1
## @req REQ-DDB-WIKI-012
def donut(counts: list[tuple[str, int]], title: str) -> str:
    """@brief Draw a donut. @return SVG."""
    total = sum(n for _l, n in counts)
    r, cx, cy, width = 52, 70, 70, 22
    parts = [
        f'<svg class="donut" xmlns="http://www.w3.org/2000/svg" width="300" '
        f'height="{max(150, 24 * len(counts) + 20)}" role="img" aria-label="{escape(title)}">',
        f"<title>{escape(title)}</title>",
    ]
    start = -math.pi / 2
    for label, n in counts:
        if total and n:
            sweep = 2 * math.pi * n / total
            parts.append(_arc(label, n, (cx, cy, r, width), start, sweep))
            start += sweep
    if not total:
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" class="c-absent" '
            f'stroke-width="{width}"/>'
        )
    parts.append(
        f'<text x="{cx}" y="{cy + 7}" text-anchor="middle" font-size="22" '
        f'font-weight="600">{total}</text>'
    )
    for i, (label, n) in enumerate(counts):
        y = 22 + 24 * i
        parts.append(
            f'<rect x="160" y="{y - 11}" width="14" height="14" rx="3" class="c-{escape(label)}"/>'
            f'<text x="182" y="{y}" font-size="13">{escape(label)} {n}</text>'
        )
    parts.append("</svg>")
    return "".join(parts)


## @brief One donut segment.
## @param label Its label.
## @param n Its count.
## @param geometry (cx, cy, radius, stroke width).
## @param start Start angle (radians).
## @param sweep Sweep angle (radians).
## @return SVG markup.
## @version 1
## @dg_internal
def _arc(
    label: str, n: int, geometry: tuple[int, int, int, int], start: float, sweep: float
) -> str:
    """A FULL CIRCLE is drawn as a circle: an arc's end point equal to its start draws nothing.

    @brief Draw a segment.
    @return SVG.
    """
    cx, cy, r, width = geometry
    attrs = f'class="c-{escape(label)}" data-label="{escape(label)}" data-count="{n}"'
    tip = f"<title>{escape(label)}: {n}</title>"
    if sweep >= 2 * math.pi - 1e-9:
        return (
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" {attrs} '
            f'stroke-width="{width}">{tip}</circle>'
        )
    x1, y1 = cx + r * math.cos(start), cy + r * math.sin(start)
    x2, y2 = cx + r * math.cos(start + sweep), cy + r * math.sin(start + sweep)
    large = 1 if sweep > math.pi else 0
    return (
        f'<path d="M{x1:.2f} {y1:.2f} A{r} {r} 0 {large} 1 {x2:.2f} {y2:.2f}" fill="none" '
        f'stroke-width="{width}" {attrs}>{tip}</path>'
    )


## @brief Milestones named by a roadmap's headings.
## @param path The roadmap file (Markdown).
## @return (version, heading text) in file order, one per version.
## v2: the heading must lead with the version (a passing mention was read as a milestone).
## @version 2
## @req REQ-DDB-WIKI-013
def roadmap_milestones(path: Path) -> list[tuple[str, str]]:
    """ONLY A HEADING THAT LEADS WITH A VERSION is a milestone ("## v0.9 — later", "# Roadmap to
    v0.8.0"); a version mentioned in passing names something else. Prose and tables are not read,
    so a roadmap's item lists can change shape without moving the chart.

    @brief Read milestones.
    @return Milestones.
    """
    out: dict[str, str] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.startswith("#"):
            continue
        heading = line.lstrip("#").strip()
        match = _VERSION.match(heading)
        if match:
            out.setdefault(match.group(1), heading)
    return list(out.items())


## @brief The burndown of open requirements across versions.
## @param series (version key, {tier: count}) in recording order.
## @param milestones (version, heading) from the roadmap.
## @return SVG markup.
## @version 1
## @req REQ-DDB-WIKI-013
def burndown(series: list[tuple[str, dict[str, int]]], milestones: list[tuple[str, str]]) -> str:
    """@brief Draw the burndown. @return SVG."""
    keys = [k for k, _c in series]
    ahead = [v for v, _h in milestones if not any(_same(v, k) for k in keys)]
    columns = keys + ahead
    opens = [sum(n for t, n in counts.items() if t not in CLOSED) for _k, counts in series]
    top = max([*opens, 1])
    w, h, left, bottom = max(360, 90 * len(columns) + 80), 240, 50, 200
    step = (w - left - 60) / max(1, len(columns) - 1)
    xs = [left + step * i for i in range(len(columns))]
    y = lambda n: bottom - (bottom - 30) * n / top  # noqa: E731
    parts = [
        f'<svg class="burndown" xmlns="http://www.w3.org/2000/svg" width="{w:.0f}" height="{h}" '
        'role="img" aria-label="Open requirements by version"><title>Open requirements by '
        "version</title>",
        f'<path class="axis" d="M{left} 20 V{bottom} H{w - 20}"/>',
        f'<text x="{left - 8}" y="{y(top) + 4:.1f}" text-anchor="end" font-size="11">{top}</text>',
        f'<text x="{left - 8}" y="{bottom + 4}" text-anchor="end" font-size="11">0</text>',
    ]
    parts += _milestone_marks(columns, xs, milestones, bottom)
    if opens and ahead:
        parts.append(
            f'<path class="ideal" d="M{xs[0]:.1f} {y(opens[0]):.1f} L{xs[-1]:.1f} {bottom}"/>'
        )
    if opens:
        points = " ".join(f"{x:.1f},{y(n):.1f}" for x, n in zip(xs, opens, strict=False))
        parts.append(f'<polyline class="open" points="{points}"/>')
    for x, n, key in zip(xs, opens, keys, strict=False):
        parts.append(
            f'<circle class="pt" cx="{x:.1f}" cy="{y(n):.1f}" r="4"><title>{escape(key)}: '
            f"{n} open</title></circle>"
        )
    for x, key in zip(xs, columns, strict=True):
        parts.append(
            f'<text x="{x:.1f}" y="{bottom + 18}" text-anchor="middle" font-size="12">'
            f"{escape(key)}</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


## @brief Vertical marks for the milestones.
## @param columns The x-axis keys.
## @param xs Their x positions.
## @param milestones (version, heading).
## @param bottom The axis baseline.
## @return SVG parts.
## @version 1
## @dg_internal
def _milestone_marks(
    columns: list[str], xs: list[float], milestones: list[tuple[str, str]], bottom: int
) -> list[str]:
    """@brief Milestone lines. @return Parts."""
    parts = []
    for version, heading in milestones:
        i = next((i for i, k in enumerate(columns) if _same(version, k)), None)
        if i is None:
            continue
        parts.append(
            f'<line class="milestone" x1="{xs[i]:.1f}" y1="24" x2="{xs[i]:.1f}" y2="{bottom}">'
            f"<title>{escape(heading)}</title></line>"
            f'<text class="ms-label" x="{xs[i] + 4:.1f}" y="22" font-size="11">'
            f"{escape(version)}</text>"
        )
    return parts


## @brief Whether a roadmap version and a version key name the same release.
## @param version The roadmap's token.
## @param key The recorded key.
## @return True when equal, ignoring a leading `v`.
## @version 1
## @dg_internal
def _same(version: str, key: str) -> bool:
    """@brief Compare. @return Equal?"""
    return version.lstrip("vV") == key.lstrip("vV")
