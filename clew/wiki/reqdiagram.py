# SPDX-License-Identifier: MIT
"""A requirement's evidence as a diagram: implementers → tests → result (round 5, P5.4).

THREE COLUMNS, EDGES ONLY WHERE THE INDEX KNOWS ONE. An edge from a test to an implementer comes
from the evidence row's `extent` — which implementers that test exercises, measured from coverage or
reached through the call graph — so a drawn line is never a guess. An implementer no test reaches
is drawn apart and marked uncovered; a test with no result is drawn with its status as the index
reports it (absent, skipped).

Static SVG, sized from its labels, so it needs no script and prints as it shows. Labels are full
names, never shortened: a diagram that cuts a name off hides which function it means.

@brief The implementers → tests → result diagram on a requirement page.
@version 1
"""

from __future__ import annotations

from html import escape
from typing import Any

## Row pitch, column gap and the pixels a label character takes, in SVG units.
_PITCH = 26
_GAP = 70
_CHAR = 7.2
_PAD = 10
## ABOVE THIS MANY TESTS the diagram summarises by result (2.0.0, P5.4 follow-up). MEASURED on clew
## at 788ea335: REQ-DDB-CONFIG-001 drew 553 tests and 7,758 edges, a 1.15 MB SVG ~14,000 px tall,
## and the 140 requirement pages carried 14.6 MB of evidence SVG of 24.7 MB. 40 rows at the pitch
## is ~1,050 px, about one screen; the full list stays in the page's tests table.
SUMMARY_TESTS = 40


## @brief The SVG for one requirement's evidence, or "" when it has neither implementer nor test.
## @param row The requirement's evidence row.
## @return SVG HTML.
## v2 (2.0.0): above SUMMARY_TESTS tests, summarised by result (`_summary_svg`).
## @version 2
## @req REQ-DDB-WIKI-022
def evidence_svg(row: Any) -> str:
    """@brief Draw implementers, tests and results with the measured edges between them.
    @return SVG, or "".
    """
    impls = list(row.implementers)
    tests = list(row.tests)
    if not impls and not tests:
        return ""
    if len(tests) > SUMMARY_TESTS:
        return _summary_svg(row, impls, tests)
    reached = {test: set(names) for test, names in (row.extent or ())}
    uncovered = set(row.implementers_uncovered or ())
    widths = [_width(impls), _width([t for t, _s in tests]), _width([s for _t, s in tests])]
    xs = [0.0, widths[0] + _GAP, widths[0] + widths[1] + 2 * _GAP]
    height = _PITCH * max(len(impls), len(tests), 1) + _PITCH
    parts = [_heads(xs)]
    at = {name: _PITCH * (i + 1) for i, name in enumerate(impls)}
    for name, y in at.items():
        cls = "impl uncovered" if name in uncovered else "impl"
        parts.append(_label(xs[0], y, name, cls))
    for i, (test, status) in enumerate(tests):
        y = _PITCH * (i + 1)
        parts += [_label(xs[1], y, test, "test"), _label(xs[2], y, status, f"result r-{status}")]
        parts += [
            _edge(test, name, xs, widths, y, at[name])
            for name in impls
            if name in reached.get(test, ())
        ]
    total = xs[2] + widths[2] + _PAD
    summary = f"{len(impls)} implementers, {len(tests)} tests, {sum(1 for _t, s in tests if s == 'passed')} passed"
    return (
        f'<svg class="req-evidence" role="img" aria-label="{escape(summary)}" '
        f'viewBox="0 0 {total:.0f} {height}" width="{total:.0f}" height="{height}">'
        + "".join(parts)
        + "</svg>"
    )


## @brief The summary form: each implementer to result buckets with counts.
## @param row The evidence row.
## @param impls Its implementers.
## @param tests Its (test, status) pairs.
## @return SVG HTML.
## @version 1
## @req REQ-DDB-WIKI-022
def _summary_svg(row: Any, impls: list[str], tests: list[tuple[str, str]]) -> str:
    """SAYS IT IS A SUMMARY and where the whole list is, so a reader is never shown a cut-down
    picture as if it were complete. An implementer → bucket edge means at least one test with
    that result reaches it, from the same `extent` the full form draws.

    @brief Summarised evidence.
    @return SVG.
    """
    reached = {test: set(names) for test, names in (row.extent or ())}
    uncovered = set(row.implementers_uncovered or ())
    counts: dict[str, int] = {}
    for _test, status in tests:
        counts[status] = counts.get(status, 0) + 1
    buckets = [f"{n} {s}" for s, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))]
    statuses = sorted(counts, key=lambda s: (-counts[s], s))
    widths = [_width(impls), _width(buckets)]
    xs = [0.0, widths[0] + 2 * _GAP]
    rows = max(len(impls), len(buckets), 1)
    height = _PITCH * rows + 2 * _PITCH
    parts = [
        f'<text class="head" x="0" y="12">implemented by</text>'
        f'<text class="head" x="{xs[1]:.0f}" y="12">results ({len(tests)} tests)</text>'
    ]
    for i, name in enumerate(impls):
        cls = "impl uncovered" if name in uncovered else "impl"
        parts.append(_label(xs[0], _PITCH * (i + 1), name, cls))
    for j, (label, status) in enumerate(zip(buckets, statuses, strict=True)):
        parts.append(_label(xs[1], _PITCH * (j + 1), label, f"result r-{status}"))
        for i, name in enumerate(impls):
            if any(s == status and name in reached.get(t, ()) for t, s in tests):
                parts.append(
                    f'<line class="edge" data-edge="{escape(name)}→{escape(status)}" '
                    f'x1="{widths[0] - _PAD + 6:.0f}" y1="{_PITCH * (i + 1)}" '
                    f'x2="{xs[1] - 6:.0f}" y2="{_PITCH * (j + 1)}"/>'
                )
    parts.append(
        f'<text class="note" x="0" y="{height - 6}">{len(tests)} tests, a summary by result: '
        "every test is in the tests table below</text>"
    )
    total = max(xs[1] + widths[1] + _PAD, 420)
    summary = f"{len(impls)} implementers, {len(tests)} tests: " + ", ".join(buckets)
    return (
        f'<svg class="req-evidence summary" role="img" aria-label="{escape(summary)}" '
        f'viewBox="0 0 {total:.0f} {height}" width="{total:.0f}" height="{height}">'
        + "".join(parts)
        + "</svg>"
    )


## @brief A column's width from its longest label.
## @param labels The column's labels.
## @return Width in SVG units.
## @version 1
## @utility
def _width(labels: list[str]) -> float:
    """@brief Longest label, at a fixed advance. @return Width."""
    return max((len(s) for s in labels), default=6) * _CHAR + _PAD


## @brief The three column headings.
## @param xs Column x positions.
## @return SVG.
## @version 1
## @utility
def _heads(xs: list[float]) -> str:
    """@brief Headings. @return SVG."""
    return "".join(
        f'<text class="head" x="{x:.0f}" y="12">{h}</text>'
        for x, h in zip(xs, ("implemented by", "tests", "result"), strict=True)
    )


## @brief One label.
## @param x Left edge.
## @param y Baseline row centre.
## @param value The full label.
## @param cls Its class.
## @return SVG.
## @version 1
## @utility
def _label(x: float, y: int, value: str, cls: str) -> str:
    """@brief Text. @return SVG."""
    return f'<text class="{cls}" x="{x:.0f}" y="{y + 4}">{escape(value)}</text>'


## @brief One test → implementer edge.
## @param test The test.
## @param impl The implementer it exercises.
## @param xs Column x positions.
## @param widths Column widths.
## @param y_test The test's row.
## @param y_impl The implementer's row.
## @return SVG.
## @version 1
## @utility
def _edge(
    test: str, impl: str, xs: list[float], widths: list[float], y_test: int, y_impl: int
) -> str:
    """@brief A line from the test's left edge to the implementer's right edge. @return SVG."""
    return (
        f'<line class="edge" data-edge="{escape(test)}→{escape(impl)}" '
        f'x1="{xs[1] - 6:.0f}" y1="{y_test}" x2="{widths[0] - _PAD + 6:.0f}" y2="{y_impl}"/>'
    )
