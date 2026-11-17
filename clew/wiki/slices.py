# SPDX-License-Identifier: MIT
"""A test is a slice of a master flow (round 5, R5-4).

OWNER 2026-11-17: "a test itself doesn't need a sequence diagram, a test case is testing a portion
OF a sequence diagram". Per-test coverage (`imports.parse_contexts`: coverage.py contexts, or an
LCOV tracefile's `TN:` sections) says which lines each test ran. Against a master flow:

  * a step is EXERCISED by a test when its call-site line ran in that test — the call happened,
    not merely the callee's file being touched;
  * the test ENTERS the flow at a function whose calls it ran while no exercised step called that
    function: the test called it itself (the flow's entry, or a function in its middle).

This is measurement. Without per-test coverage nothing here applies; a slice is then static reach,
and the page says so.

@brief Test slices of master flows from per-test coverage.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from .flow import Flow
from .svg import flow_svg

## {file: {line: tests}}, as `imports.parse_contexts` returns it.
Contexts = dict[str, dict[int, set[str]]]
## {file: lines one test ran}.
Lines = dict[str, set[int]]


## @brief One test's portion of one master flow.
## @version 1
@dataclass(frozen=True)
class Slice:
    """@brief Exercised step indices and where the test entered. @version 1"""

    exercised: tuple[int, ...] = ()
    entered: tuple[str, ...] = ()


## @brief Per-test coverage turned around: each test's lines per file.
## @param contexts {file: {line: tests}}.
## @return {test: {file: lines}}.
## @version 1
## @req REQ-DDB-WIKI-041
def lines_per_test(contexts: Contexts) -> dict[str, Lines]:
    """@brief Group lines by test. @return Lines per test."""
    out: dict[str, Lines] = {}
    for rel, lines in contexts.items():
        for line, tests in lines.items():
            for test in tests:
                out.setdefault(test, {}).setdefault(rel, set()).add(line)
    return out


## @brief The steps of a flow one test exercised, and where it entered.
## @param flow The master flow.
## @param lines The lines that test ran, per file.
## @return The slice.
## v2: entries computed by the shared `_slice` (with `slices_of`).
## @version 2
## @req REQ-DDB-WIKI-041
def slice_of(flow: Flow, lines: Lines) -> Slice:
    """A STEP'S CALL SITE is `site_file:line` — the line in the caller where the call is made — so
    a step is exercised only if that call happened in this test. Entry points are listed in the
    order their first exercised step appears.

    @brief Slice a flow.
    @return The slice.
    """
    exercised = tuple(
        i
        for i, step in enumerate(flow.steps)
        if step.line in lines.get(step.site_file or step.file, ())
    )
    return _slice(flow, exercised)


## @brief Every test's slice of one flow, from its steps' call sites in one pass.
## @param flow The master flow.
## @param contexts {file: {line: tests}}.
## @return {test: slice}, only for tests that exercised a step.
## @version 1
## @req REQ-DDB-WIKI-041
def slices_of(flow: Flow, contexts: Contexts) -> dict[str, Slice]:
    """@brief Slice a flow for all its tests. @return Slices."""
    hit: dict[str, list[int]] = {}
    for i, step in enumerate(flow.steps):
        for test in (contexts.get(step.site_file or step.file) or {}).get(step.line, ()):
            hit.setdefault(test, []).append(i)
    return {test: _slice(flow, tuple(steps)) for test, steps in sorted(hit.items())}


## @brief A slice from its exercised steps: where the test entered follows from them.
## @param flow The master flow.
## @param exercised Exercised step indices, ascending.
## @return The slice.
## @version 1
## @dg_internal
def _slice(flow: Flow, exercised: tuple[int, ...]) -> Slice:
    """@brief Entries from exercised steps. @return Slice."""
    called = {flow.steps[i].callee_qualified or flow.steps[i].callee for i in exercised}
    entered: list[str] = []
    for i in exercised:
        caller = flow.steps[i].caller_qualified or flow.steps[i].caller
        if caller not in called and caller not in entered:
            entered.append(caller)
    return Slice(exercised, tuple(entered))


## @brief A test's slice drawn as a window of its master flow.
## @param flow The master flow.
## @param cut The test's slice.
## @param pad Steps of context kept on each side of the slice.
## @return HTML: the counts of hidden steps around the diagram; "" for an empty slice.
## @version 1
## @req REQ-DDB-WIKI-041
def slice_svg(flow: Flow, cut: Slice, pad: int = 2) -> str:
    """THE PORTION OF THE DIAGRAM, numbered as in the master flow so the reader can find it there:
    exercised steps lit, the rest of the window dimmed, the entry marked, only the lanes the window
    uses drawn, and what lies outside the window counted rather than drawn.

    @brief Draw a slice.
    @return HTML.
    """
    if not cut.exercised:
        return ""
    lo = max(0, cut.exercised[0] - pad)
    hi = min(len(flow.steps), cut.exercised[-1] + pad + 1)
    steps = flow.steps[lo:hi]
    used = {s.from_lane for s in steps} | {s.to_lane for s in steps}
    window = replace(flow, steps=steps, lanes=tuple(ln for ln in flow.lanes if ln.id in used))
    svg = flow_svg(window, marks=_marks(flow, cut, lo, hi), first=lo)
    return f'<div class="slice">{_hidden(lo, "earlier")}{svg}{_hidden(len(flow.steps) - hi, "later")}</div>'


## @brief Classes per step of a window: lit, dimmed, and the first step of each entry.
## @param flow The master flow.
## @param cut The slice.
## @param lo The window's first master step.
## @param hi One past its last.
## @return {window index: classes}.
## @version 1
## @dg_internal
def _marks(flow: Flow, cut: Slice, lo: int, hi: int) -> dict[int, str]:
    """@brief Mark steps. @return Classes."""
    lit, entered, seen = set(cut.exercised), set(cut.entered), set()
    out = {}
    for i in range(lo, hi):
        mark = "ex" if i in lit else "dim"
        caller = flow.steps[i].caller_qualified or flow.steps[i].caller
        if i in lit and caller in entered and caller not in seen:
            seen.add(caller)
            mark += " entry"
        out[i - lo] = mark
    return out


## @brief A line counting steps outside a window.
## @param n How many.
## @param where "earlier" or "later".
## @return HTML, or "" for none.
## @version 1
## @dg_internal
def _hidden(n: int, where: str) -> str:
    """@brief Count hidden steps. @return HTML."""
    return f'<p class="slice-more">… {n} {where} step{"s" if n != 1 else ""}</p>' if n else ""
