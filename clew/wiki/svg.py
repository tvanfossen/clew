# SPDX-License-Identifier: MIT
"""A derived flow drawn as an inline SVG sequence diagram — no script, no CDN.

1.4.0 Track 4, W5 (#67's fifth consumer: the site must be self-contained, with no outbound
network). One column per lane with a lifeline, one arrow per step in order, the step's frames
written as a `[loop]`/`[if]` prefix on its label. Deliberately plain: a picture a browser renders
offline from the HTML file alone.

ANIMATED (W12): `animate=True` plays the diagram in call order — each step's arrow draws itself
and its label fades in, one step after another, then the diagram holds complete. It is CSS inside
the SVG (`stroke-dashoffset` over a `pathLength="1"` path, `animation-delay` per step): no script,
no library, nothing fetched. `prefers-reduced-motion` shows the finished diagram at once, and the
final frame IS the static diagram, so nothing is lost where animation does not run.

@brief Render a Flow as SVG, optionally animated.
@version 2
"""

from __future__ import annotations

from html import escape

from .flow import Flow

_COL = 200
_ROW = 30
_TOP = 60
## Seconds between two steps of an animated diagram.
STEP_SECONDS = 0.7
_ANIMATION = (
    "<style>.cs{opacity:0;animation:cs-in .3s ease-out forwards}"
    ".cs .ca{stroke-dasharray:1;stroke-dashoffset:1;animation:cs-draw .45s ease-in-out forwards;"
    "animation-delay:inherit}"
    "@keyframes cs-in{to{opacity:1}}@keyframes cs-draw{to{stroke-dashoffset:0}}"
    "@media (prefers-reduced-motion:reduce){.cs,.cs .ca{animation:none;opacity:1;"
    "stroke-dashoffset:0}}</style>"
)


## @brief The flow as an SVG document fragment.
## @param flow A derived flow.
## @param animate Play the steps in call order (CSS only), holding the complete diagram at the end.
## @return SVG markup.
## v2: `animate` (W12).
## @version 2
## @req REQ-DDB-WIKI-008
def flow_svg(flow: Flow, animate: bool = False) -> str:
    """@brief Draw lanes, lifelines and one arrow per step. @return SVG text."""
    lanes = [lane.id for lane in flow.lanes]
    x = {lane: _COL // 2 + i * _COL for i, lane in enumerate(lanes)}
    height = _TOP + _ROW * (len(flow.steps) + 1)
    width = max(_COL, _COL * len(lanes))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="sans-serif" font-size="12">'
    ]
    if animate:
        parts.append(_ANIMATION)
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
            shape = (
                f'<path class="ca" pathLength="1" d="M{x1} {y} h40 v12 h-40" fill="none" '
                f'stroke="#333"/><text x="{x1 + 46}" y="{y + 10}">{label}</text>'
            )
        else:
            shape = (
                f'<path class="ca" pathLength="1" d="M{x1} {y} H{x2}" stroke="#333"/>'
                f'<circle cx="{x2}" cy="{y}" r="3" fill="#333"/>'
                f'<text x="{(x1 + x2) // 2}" y="{y - 4}" text-anchor="middle">{label}</text>'
            )
        parts.append(_step_group(i, step.caller, step.callee, shape, animate))
    parts.append("</svg>")
    return "".join(parts)


## @brief One step's group: titled for hover, delayed by its position when animated.
## @param index The step's position.
## @param caller The caller's name.
## @param callee The callee's name.
## @param shape The step's arrow and label markup.
## @param animate Whether the diagram is animated.
## @return SVG markup.
## @version 1
## @dg_internal
def _step_group(index: int, caller: str, callee: str, shape: str, animate: bool) -> str:
    """@brief Wrap a step. @return SVG text."""
    title = f"<title>{index + 1}. {escape(caller)} → {escape(callee)}</title>"
    if not animate:
        return f"<g>{title}{shape}</g>"
    delay = f"{index * STEP_SECONDS:.2f}s"
    return f'<g class="cs" style="animation-delay:{delay}">{title}{shape}</g>'


## @brief A lane label short enough for its box.
## @param lane The lane id.
## @return The label.
## @version 1
## @dg_internal
def _short(lane: str) -> str:
    """@brief Keep the tail of a long path. @return Label."""
    return lane if len(lane) <= 26 else "…" + lane[-25:]
