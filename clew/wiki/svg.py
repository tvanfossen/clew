# SPDX-License-Identifier: MIT
"""A derived flow drawn as an inline SVG sequence diagram — no script, no CDN.

1.4.0 Track 4, W5 (#67's fifth consumer: the site must be self-contained, with no outbound
network). One column per lane with a lifeline, one arrow per step in order, the step's frames
written as a `[loop]`/`[if]` prefix on its label. Deliberately plain: a picture a browser renders
offline from the HTML file alone.

@brief Render a Flow as SVG.
@version 1
"""

from __future__ import annotations

from html import escape

from .flow import Flow

_COL = 200
_ROW = 30
_TOP = 60


## @brief The flow as an SVG document fragment.
## @param flow A derived flow.
## @return SVG markup.
## @version 1
## @req REQ-DDB-WIKI-003
def flow_svg(flow: Flow) -> str:
    """@brief Draw lanes, lifelines and one arrow per step. @return SVG text."""
    lanes = [lane.id for lane in flow.lanes]
    x = {lane: _COL // 2 + i * _COL for i, lane in enumerate(lanes)}
    height = _TOP + _ROW * (len(flow.steps) + 1)
    width = max(_COL, _COL * len(lanes))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="sans-serif" font-size="12">'
    ]
    for lane in lanes:
        parts.append(
            f'<rect x="{x[lane] - 90}" y="10" width="180" height="26" fill="#eef" stroke="#557"/>'
            f'<text x="{x[lane]}" y="28" text-anchor="middle">{escape(_short(lane))}</text>'
            f'<line x1="{x[lane]}" y1="36" x2="{x[lane]}" y2="{height - 5}" stroke="#aab" '
            f'stroke-dasharray="4 3"/>'
        )
    for i, step in enumerate(flow.steps):
        y = _TOP + _ROW * i
        x1, x2 = x[step.from_lane], x[step.to_lane]
        frames = "".join(f"[{f.kind}]" for f in step.frames)
        label = escape(f"{frames} {step.callee}".strip())
        if x1 == x2:
            parts.append(
                f'<path d="M{x1} {y} h40 v12 h-40" fill="none" stroke="#333"/>'
                f'<text x="{x1 + 46}" y="{y + 10}">{label}</text>'
            )
        else:
            mid = (x1 + x2) // 2
            parts.append(
                f'<line x1="{x1}" y1="{y}" x2="{x2}" y2="{y}" stroke="#333"/>'
                f'<circle cx="{x2}" cy="{y}" r="3" fill="#333"/>'
                f'<text x="{mid}" y="{y - 4}" text-anchor="middle">{label}</text>'
            )
    parts.append("</svg>")
    return "".join(parts)


## @brief A lane label short enough for its box.
## @param lane The lane id.
## @return The label.
## @version 1
## @dg_internal
def _short(lane: str) -> str:
    """@brief Keep the tail of a long path. @return Label."""
    return lane if len(lane) <= 26 else "…" + lane[-25:]
