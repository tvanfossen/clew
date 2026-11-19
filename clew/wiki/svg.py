# SPDX-License-Identifier: MIT
"""A derived flow drawn as a UML sequence diagram, in SVG with no dependency.

1.4.0 W3/W12, and W18 (owner 2026-11-15: "sequence diagram is good but could be better" —
UML-proper, drawn frames, theme and layout, interactive). The diagram has:

  * a HEAD per lane at the top and the bottom, joined by its dashed lifeline;
  * an ACTIVATION BAR for every call, from the call to its return, nested bars offset on the same
    lane, the entry's bar running the whole diagram;
  * one numbered CALL ARROW per step (a loop-back arrow for a call within a lane) and a dashed
    RETURN ARROW when a cross-lane call's subtree ends;
  * a FRAME box around the steps a `loop` / `if` / `else` / `try` / `catch` / `case` encloses,
    labelled with its UML operator;
  * lane widths fitted to their labels and to the messages between neighbours.

Colours are theme tokens (`var(--acc, <fallback>)`), so the diagram follows the site's palette and
colour scheme, and still renders standalone (`clew wiki flow --svg`) with the fallbacks.

`animate=True` (W12) plays the steps in call order with CSS inside the SVG — no script, nothing
remote, `prefers-reduced-motion` honoured. A step's return arrow belongs to the group of the step
that closes its subtree, so the animation delay is still one per step. Each step group carries
`data-step` (its 0-based position) for the site's interactive layer (`flowpage`).

@brief Render a Flow as an SVG sequence diagram.
@version 3
"""

from __future__ import annotations

from html import escape

from dataclasses import replace

from .flow import Flow, Step

## Row height per event, top of the first row, lane head height.
_ROW = 30
_TOP = 64
_HEAD = 30
_MIN_COL, _MAX_COL = 160, 380
## Seconds between two steps of an animated diagram.
STEP_SECONDS = 0.7
## A frame kind's UML operator.
_OPERATOR = {
    "loop": "loop",
    "if": "opt",
    "else": "alt",
    "case": "alt",
    "try": "try",
    "catch": "catch",
}
_STYLE = (
    "<style>.seq g.nr{opacity:.45}.seq g.nr .lbl{font-style:italic}.seq g.dim{opacity:.28}"
    ".seq g.ex .ca{stroke-width:2.6}.seq .ent{font-size:11px;font-weight:700;"
    "fill:var(--acc,#3D6B2E)}"
    ".seq text{font-family:var(--sans,sans-serif);font-size:12px;fill:var(--ink,#2A2118)}"
    ".seq .head{fill:var(--paper,#FAF1D9);stroke:var(--acc,#3D6B2E);stroke-width:1.2}"
    ".seq .head-t{font-weight:700;font-size:12px;fill:var(--accink,#1F3B16)}"
    ".seq .lane{stroke:var(--rule,#CFC0A0);stroke-dasharray:3 5;stroke-width:1.2}"
    ".seq .act{fill:var(--accbg,#DDE8C9);stroke:var(--acc,#3D6B2E);stroke-width:1}"
    ".seq .ca{stroke:var(--acc,#3D6B2E);fill:none;stroke-width:1.6;stroke-linecap:round}"
    ".seq .self .ca{stroke:var(--ink2,#6A5B4D)}.seq .tip{fill:var(--acc,#3D6B2E)}"
    ".seq .self .tip{fill:var(--ink2,#6A5B4D)}"
    ".seq .ret{stroke:var(--faint,#998874);fill:none;stroke-dasharray:4 4;stroke-width:1.2}"
    ".seq .frame{fill:var(--rootbg,#F4DDCB);fill-opacity:.28;stroke:var(--root,#A6502C);"
    "stroke-width:1;stroke-dasharray:6 3}"
    ".seq .fl{fill:var(--root,#A6502C)}.seq .flt{fill:#fff;font-weight:700;font-size:10.5px;"
    "letter-spacing:.04em}"
    ".seq .badge{fill:var(--acc,#3D6B2E)}.seq .num{fill:#fff;font-size:10px;font-weight:700}"
    ".seq .pill{fill:var(--paper,#FAF1D9);stroke:var(--rule2,#E2D5B4)}"
    ".seq .lbl{font-weight:600}"
    ".seq .band{fill:var(--accbg,#DDE8C9);fill-opacity:0;transition:fill-opacity .15s}"
    ".seq g[data-step]:hover .band{fill-opacity:.45}.seq g.sel .band{fill-opacity:.8}"
    ".seq g.sel .pill{stroke:var(--acc,#3D6B2E);stroke-width:1.5}</style>"
)
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
## v3: UML-proper (W18): heads at both ends, activation bars, numbered steps, return arrows,
## drawn frames, fitted lanes, theme tokens, `data-step` per step.
## v4: a viewBox, so the page's pan / zoom (round 3, P1b) can move it.
## v5 (OWNER 2026-11-17, round 5): consecutive identical leaf calls draw once, framed `loop ×N`;
## the group names every step it stands for, and the animation plays drawn arrows only.
## @param marks Extra classes per step (round 5: `ex` / `dim` / `entry` for a test's slice).
## @param first The master-flow number of this flow's first step (a window keeps its numbering).
## v6 (round 5): `marks` and `first`, so a test's slice is drawn as a window of its master flow.
## @version 6
## @req REQ-DDB-WIKI-008
## @req REQ-DDB-WIKI-041
def flow_svg(
    flow: Flow, animate: bool = False, marks: dict[int, str] | None = None, first: int = 0
) -> str:
    """@brief Lay out and draw the diagram. @return SVG text."""
    marks = marks or {}
    runs = _runs(flow.steps, marks)
    layout = _Layout(replace(flow, steps=tuple(flow.steps[start] for start, _n in runs)))
    parts = [
        f'<svg class="seq" xmlns="http://www.w3.org/2000/svg" width="{layout.width}" '
        f'height="{layout.height}" viewBox="0 0 {layout.width} {layout.height}" role="img" '
        f'aria-label="Sequence from {escape(flow.entry)}">',
        _STYLE,
    ]
    if animate:
        parts.append(_ANIMATION)
    parts += layout.lanes_markup()
    parts += layout.frames_markup()
    parts += [layout.repeat_frame(d, n) for d, (_s, n) in enumerate(runs) if n > 1]
    parts += layout.activations_markup()
    for d, (start, n) in enumerate(runs):
        mark = marks.get(start, "")
        shape = layout.step_markup(d, first + start + 1, n)
        if "entry" in mark:
            shape += layout.entry_marker(d)
        group = _step_group(first + start, flow.steps[start], shape, animate, (d, n, mark))
        parts.append(group)
    parts.append("</svg>")
    return "".join(parts)


## @brief Runs of consecutive identical leaf calls.
## @param steps The flow's steps.
## @param marks Extra classes per step: steps marked differently never fold together.
## @return (first step, how many) per drawn arrow, in order.
## v2 (round 5): a test's exercised call never folds with a dimmed one.
## @version 2
## @utility
def _runs(steps: tuple[Step, ...], marks: dict[int, str] | None = None) -> list[tuple[int, int]]:
    """A RUN IS THE SAME CALL REPEATED WITH NOTHING UNDER IT: same caller, callee, lanes, depth and
    frames, and no deeper step after any member (a call with a subtree is never folded — its
    subtree would be hidden).

    @brief Fold runs.
    @return Runs.
    """

    def key(i: int) -> tuple:
        step = steps[i]
        return (
            (marks or {}).get(i, ""),
            step.caller_qualified or step.caller,
            step.callee_qualified or step.callee,
            step.from_lane,
            step.to_lane,
            step.depth,
            step.frames,
        )

    def leaf(i: int) -> bool:
        return i + 1 >= len(steps) or steps[i + 1].depth <= steps[i].depth

    runs: list[tuple[int, int]] = []
    for i in range(len(steps)):
        if runs and leaf(i) and key(runs[-1][0]) == key(i) and leaf(i - 1):
            runs[-1] = (runs[-1][0], runs[-1][1] + 1)
        else:
            runs.append((i, 1))
    return runs


## @brief Positions of everything in a diagram, computed once.
## @version 1
class _Layout:
    """THE EVENT LIST IS THE TIMELINE: one `call` per step in order, and a `ret` when a step's
    subtree ends (the next step is no deeper, or the flow ends). A cross-lane return takes a row;
    a return within a lane only closes its bar.

    @brief Diagram geometry.
    @version 1
    """

    ## @brief Compute lane columns, event rows and activation spans.
    ## @param flow The flow.
    ## @version 1
    ## @utility
    def __init__(self, flow: Flow) -> None:
        """@brief Lay out. @return None."""
        self.flow = flow
        self.lanes = [lane.id for lane in flow.lanes] or [flow.entry]
        self.x = self._columns()
        self.call_y: dict[int, float] = {}
        self.ret_y: dict[int, float] = {}
        self.offset: dict[int, int] = {}
        self.returns_in: dict[int, list[int]] = {}
        self._timeline()
        self.width = int(max(self.x.values()) + self._half(self.lanes[-1]) + 20)
        self.height = int(self.end_y + _HEAD + 24)

    ## @brief Lane centres, each column fitted to its label and its neighbours' messages.
    ## @return {lane: x}.
    ## @version 1
    ## @utility
    def _columns(self) -> dict[str, float]:
        """@brief Fit columns. @return Centres."""
        width = {lane: _clamp(_text_w(_short(lane)) + 40) for lane in self.lanes}
        index = {lane: i for i, lane in enumerate(self.lanes)}
        for step in self.flow.steps:
            a, b = index.get(step.from_lane, 0), index.get(step.to_lane, 0)
            need = _text_w(step.callee) + 60
            if abs(a - b) == 1:
                for lane in (step.from_lane, step.to_lane):
                    width[lane] = _clamp(max(width[lane], need))
            elif a == b:
                width[step.from_lane] = _clamp(max(width[step.from_lane], need + 60))
        x, cursor = {}, 20.0
        for lane in self.lanes:
            x[lane] = cursor + width[lane] / 2
            cursor += width[lane]
        self._width = width
        return x

    ## @brief Half a lane's column width.
    ## @param lane The lane.
    ## @return Pixels.
    ## @version 1
    ## @utility
    def _half(self, lane: str) -> float:
        """@brief Half width. @return Px."""
        return self._width[lane] / 2

    ## @brief Walk the steps into call and return events with their rows.
    ## @return None.
    ## @version 1
    ## @utility
    def _timeline(self) -> None:
        """@brief Build the timeline. @return None."""
        y = float(_TOP)
        open_: list[int] = []
        nesting: dict[str, int] = {self._entry_lane(): 1}
        for i, step in enumerate(self.flow.steps):
            while open_ and self.flow.steps[open_[-1]].depth >= step.depth:
                y = self._close(open_.pop(), y, nesting, i - 1)
            y += _ROW / 2 if i == 0 else 0
            self.call_y[i] = y
            self.offset[i] = 6 * nesting.get(step.to_lane, 0)
            nesting[step.to_lane] = nesting.get(step.to_lane, 0) + 1
            open_.append(i)
            y += _ROW
        while open_:
            y = self._close(open_.pop(), y, nesting, len(self.flow.steps) - 1)
        self.end_y = y + 6

    ## @brief Close one step's activation; a cross-lane return takes a row.
    ## @param i The step.
    ## @param y The current row.
    ## @param nesting Open activations per lane; decremented.
    ## @param last The step whose group carries the return arrow.
    ## @return The next row.
    ## @version 1
    ## @utility
    def _close(self, i: int, y: float, nesting: dict[str, int], last: int) -> float:
        """@brief Close. @return Row."""
        step = self.flow.steps[i]
        nesting[step.to_lane] -= 1
        cross = step.from_lane != step.to_lane
        self.ret_y[i] = y - _ROW / 2 + (_ROW / 2 if cross else 8)
        if cross:
            self.returns_in.setdefault(last, []).append(i)
        return y + (_ROW * 0.6 if cross else 4)

    ## @brief The entry function's lane.
    ## @return The lane id.
    ## @version 1
    ## @utility
    def _entry_lane(self) -> str:
        """@brief Entry lane. @return Lane."""
        return self.flow.steps[0].from_lane if self.flow.steps else self.lanes[0]

    ## @brief Heads at top and bottom and the lifelines.
    ## @return SVG parts.
    ## v2: themed head labels, rounder heads.
    ## @version 2
    ## @utility
    def lanes_markup(self) -> list[str]:
        """@brief Draw lanes. @return Parts."""
        parts = []
        for lane in self.lanes:
            x, w = self.x[lane], self._width[lane] - 24
            label = (
                f'<text class="head-t" x="{x:.0f}" y="{{y}}" text-anchor="middle">'
                f"{escape(_short(lane))}<title>{escape(lane)}</title></text>"
            )
            parts.append(
                f'<line class="lane" x1="{x:.0f}" y1="{10 + _HEAD}" x2="{x:.0f}" '
                f'y2="{self.end_y:.0f}"/>'
            )
            for top in (10, self.end_y):
                parts.append(
                    f'<rect class="head" x="{x - w / 2:.0f}" y="{top:.0f}" width="{w:.0f}" '
                    f'height="{_HEAD}" rx="10"/>' + label.replace("{y}", f"{top + 19:.0f}")
                )
        return parts

    ## @brief Activation bars: the entry's, then one per step.
    ## @return SVG parts.
    ## @version 1
    ## @utility
    def activations_markup(self) -> list[str]:
        """@brief Draw bars. @return Parts."""
        entry = self.x[self._entry_lane()]
        parts = [_bar(entry, _TOP - 8, self.end_y - 6, 0)]
        for i, step in enumerate(self.flow.steps):
            parts.append(_bar(self.x[step.to_lane], self.call_y[i], self.ret_y[i], self.offset[i]))
        return parts

    ## @brief Frame boxes around the steps each loop / if / try encloses.
    ## @return SVG parts.
    ## @version 1
    ## @utility
    def frames_markup(self) -> list[str]:
        """A FRAME IS ONE SPAN OF ONE CALLER'S BODY: steps share it when the same caller's call
        sites sit inside the same frame (kind and line). Nested frames inset by their depth.

        @brief Draw frames.
        @return Parts.
        """
        groups: dict[tuple[str, str, int], list[tuple[int, int]]] = {}
        for i, step in enumerate(self.flow.steps):
            for depth, frame in enumerate(step.frames):
                key = (step.caller_qualified or step.caller, frame.kind, frame.line)
                groups.setdefault(key, []).append((i, depth))
        parts = []
        for (_caller, kind, line), members in groups.items():
            idx = [i for i, _d in members]
            inset = 4 * min(d for _i, d in members)
            lanes = {self.flow.steps[i].from_lane for i in idx} | {
                self.flow.steps[i].to_lane for i in idx
            }
            left = min(self.x[ln] for ln in lanes) - 52 + inset
            right = max(self.x[ln] for ln in lanes) + 90 - inset
            top = min(self.call_y[i] for i in idx) - 20 + inset
            bottom = max(self.ret_y[i] for i in idx) + 8 - inset
            parts.append(_frame(_OPERATOR.get(kind, kind), line, (left, top, right, bottom)))
        return parts

    ## @brief A `loop ×N` frame around one folded arrow.
    ## @param i The drawn step.
    ## @param times How many calls it stands for.
    ## @return SVG markup.
    ## @version 1
    ## @utility
    def repeat_frame(self, i: int, times: int) -> str:
        """@brief Frame a fold. @return Markup."""
        step = self.flow.steps[i]
        lanes = (step.from_lane, step.to_lane)
        box = (
            min(self.x[ln] for ln in lanes) - 44,
            self.call_y[i] - 26,
            max(self.x[ln] for ln in lanes) + 82,
            self.ret_y[i] + 4,
        )
        return _frame(f"loop ×{times}", step.line, box)

    ## @brief The "test enters" marker under one drawn step's arrow.
    ## @param i The drawn step.
    ## @return SVG markup.
    ## @version 1
    ## @utility
    def entry_marker(self, i: int) -> str:
        """@brief Mark the entry. @return Markup."""
        step = self.flow.steps[i]
        return (
            f'<text class="ent" x="{self.x[step.from_lane] + 8:.0f}" y="{self.call_y[i] + 14:.0f}">'
            "▶ test enters</text>"
        )

    ## @brief One step's call arrow, badge, label and any returns it closes.
    ## @param i The drawn step.
    ## @param number The number its badge shows (its first step's, counted from 1).
    ## @param times How many calls the arrow stands for.
    ## @return SVG markup.
    ## v2: label pills, a full-width row band (hover / selected), self-calls grouped.
    ## v3 (round 5): a folded arrow keeps its first step's number and reads `callee ×N`.
    ## v4 (round 5): a `not_run` stub reads "… N calls not run".
    ## @version 4
    ## @utility
    def step_markup(self, i: int, number: int, times: int = 1) -> str:
        """@brief Draw a step. @return Markup."""
        step = self.flow.steps[i]
        y = self.call_y[i]
        x1 = self.x[step.from_lane] + (self.offset[i] if step.from_lane == step.to_lane else 0)
        x2 = self.x[step.to_lane] + self.offset[i]
        if step.from_lane == step.to_lane:
            arrow = (
                f'<path class="ca" pathLength="1" d="M{x1 + 5:.0f} {y - 6:.0f} h34 v12 h-28"/>'
                f'<path class="tip" d="M{x2 + 5:.0f} {y + 6:.0f} l7 -4 v8 z"/>'
            )
            lx, anchor = x1 + 46, "start"
        else:
            sign = 1 if x2 > x1 else -1
            end = x2 - sign * 5
            arrow = (
                f'<path class="ca" pathLength="1" d="M{x1 + sign * 5:.0f} {y:.0f} H{end:.0f}"/>'
                f'<path class="tip" d="M{end:.0f} {y:.0f} l{-sign * 9} -4 v8 z"/>'
            )
            lx, anchor = (x1 + x2) / 2, "middle"
        text = _message(step, times)
        tw = _text_w(text)
        left = lx + 12 if anchor == "start" else lx - tw / 2
        bx = left - 14
        label = (
            f'<rect class="pill" x="{bx - 11:.0f}" y="{y - 21:.0f}" width="{tw + 32:.0f}" '
            f'height="18" rx="9"/>'
            f'<circle class="badge" cx="{bx:.0f}" cy="{y - 12:.0f}" r="7.5"/>'
            f'<text class="num" x="{bx:.0f}" y="{y - 8.5:.0f}" text-anchor="middle">{number}</text>'
            f'<text class="lbl" x="{left:.0f}" y="{y - 8:.0f}">{escape(text)}</text>'
        )
        band = (
            f'<rect class="band" x="0" y="{y - _ROW / 2 - 6:.0f}" width="{self.width}" '
            f'height="{_ROW:.0f}"/>'
        )
        if step.from_lane == step.to_lane:
            arrow = f'<g class="self">{arrow}</g>'
        returns = "".join(self._return(j) for j in self.returns_in.get(i, ()))
        return band + arrow + label + returns

    ## @brief A dashed return arrow for a cross-lane call.
    ## @param j The step returning.
    ## @return SVG markup.
    ## @version 1
    ## @utility
    def _return(self, j: int) -> str:
        """@brief Draw a return. @return Markup."""
        step = self.flow.steps[j]
        y = self.ret_y[j]
        x1, x2 = self.x[step.to_lane] + self.offset[j], self.x[step.from_lane]
        sign = 1 if x2 > x1 else -1
        end = x2 - sign * 5
        return (
            f'<path class="ret" d="M{x1 + sign * 5:.0f} {y:.0f} H{end:.0f}"/>'
            f'<path class="ret" d="M{end - sign * 8:.0f} {y - 4:.0f} L{end:.0f} {y:.0f} '
            f'L{end - sign * 8:.0f} {y + 4:.0f}"/>'
        )


## @brief One activation bar.
## @param x The lane centre.
## @param top Its top.
## @param bottom Its bottom.
## @param offset Its nesting offset.
## @return SVG markup.
## @version 1
## @utility
def _bar(x: float, top: float, bottom: float, offset: int) -> str:
    """@brief Draw a bar. @return Markup."""
    height = max(8.0, bottom - top)
    return (
        f'<rect class="act" x="{x - 5 + offset:.0f}" y="{top:.0f}" width="10" '
        f'height="{height:.0f}" rx="2"/>'
    )


## @brief One frame box with its operator tab.
## @param operator The UML operator.
## @param line The frame's source line.
## @param box (left, top, right, bottom).
## @return SVG markup.
## @version 1
## @utility
def _frame(operator: str, line: int, box: tuple[float, float, float, float]) -> str:
    """@brief Draw a frame. @return Markup."""
    left, top, right, bottom = box
    tab = _text_w(operator) + 16
    return (
        f"<g><title>{escape(operator)} (line {line})</title>"
        f'<rect class="frame" x="{left:.0f}" y="{top:.0f}" width="{right - left:.0f}" '
        f'height="{bottom - top:.0f}" rx="4"/>'
        f'<path class="fl" d="M{left:.0f} {top:.0f} h{tab:.0f} v10 l-6 6 h{-tab + 6:.0f} z"/>'
        f'<text class="flt" x="{left + 6:.0f}" y="{top + 12:.0f}">{escape(operator)}</text></g>'
    )


## @brief One step's group: titled for hover, numbered for the interactive layer, delayed when
## animated.
## @param index The step's position.
## @param step The step.
## @param shape The step's markup.
## @param animate Whether the diagram is animated.
## @return SVG markup.
## @param drawn (its position among drawn arrows, how many steps it stands for, extra classes).
## v2: takes the step; carries `data-step`.
## v3 (round 5): a fold carries `data-steps` (every step it stands for) and is delayed by its
## DRAWN position, so folding leaves no gap in the animation.
## v4 (round 5): a `not_run` stub's group is classed `nr` (dimmed).
## v5 (round 5): extra classes (a test slice's `ex` / `dim` / `entry`).
## @version 5
## @utility
def _step_group(
    index: int, step: Step, shape: str, animate: bool, drawn: tuple[int, int, str] = (-1, 1, "")
) -> str:
    """@brief Wrap a step. @return SVG text."""
    slot, times, mark = drawn if drawn[0] >= 0 else (index, 1, "")
    kind = " ".join(c for c in ("st", "nr" if step.not_run else "", mark) if c)
    numbers = f"{index + 1}–{index + times}" if times > 1 else f"{index + 1}"
    title = f"<title>{numbers}. {escape(step.caller)} → {escape(step.callee)}</title>"
    steps = f' data-steps="{" ".join(str(index + k) for k in range(times))}"' if times > 1 else ""
    if not animate:
        return f'<g class="{kind}" data-step="{index}"{steps}>{title}{shape}</g>'
    delay = f"{slot * STEP_SECONDS:.2f}s"
    return (
        f'<g class="{kind.replace("st", "cs")}" data-step="{index}"{steps} '
        f'style="animation-delay:{delay}">'
        f"{title}{shape}</g>"
    )


## @brief The text on a step's arrow.
## @param step The step.
## @param times How many calls a folded arrow stands for.
## @return The label.
## @version 1
## @utility
def _message(step: Step, times: int) -> str:
    """@brief Arrow label. @return Text."""
    if step.not_run:
        return f"… {step.not_run} call{'s' if step.not_run != 1 else ''} not run"
    return f"{step.callee} ×{times}" if times > 1 else step.callee


## @brief A label's approximate rendered width at 12px.
## @param text The label.
## @return Pixels.
## @version 1
## @utility
def _text_w(text: str) -> float:
    """@brief Estimate width. @return Px."""
    return 7.0 * len(text)


## @brief A column width within the allowed range.
## @param width Wanted width.
## @return Clamped width.
## @version 1
## @utility
def _clamp(width: float) -> float:
    """@brief Clamp. @return Px."""
    return max(_MIN_COL, min(_MAX_COL, width))


## @brief A lane label short enough for its box.
## @param lane The lane id.
## @return The label.
## v2: 40 characters (heads are fitted to their labels now).
## @version 2
## @utility
def _short(lane: str) -> str:
    """@brief Keep the tail of a long path. @return Label."""
    return lane if len(lane) <= 40 else "…" + lane[-39:]
