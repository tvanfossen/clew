# SPDX-License-Identifier: MIT
"""A test as a flowchart: each pinned assertion a diamond, each failure ending in a declared mode.

2.2, the test flowchart (owner Q/A 2026-11-25). Built only from what the test's syntax says:

- ovals start and end the run;
- a box is the function an assertion observes, its pin's `target` (`checkpins.pin_checks`);
- a diamond is each assertion, in body order; pass goes down, fail goes right.

WHERE A FAILURE GOES, in order: the assertion's INLINE MARKER (`# fails_when: FM-1`, or
`// fails_when: FM-1` in C and C++); else the test's only mode, when its doc names exactly one
with `@fails_when`; else an "unassigned" end. Never a guess: an unassigned end is a finding,
the gap propose-modes (F4) drafts markers for.

Every node is a `<g data-step="i">` in pass-path order, the hook the flow pages' player already
steps through.

@brief Derive and render a test's flowchart.
@version 1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from html import escape
from typing import Any

## The end a failure reaches when nothing names its mode.
UNASSIGNED = "unassigned"
## An inline marker on an assertion's line.
_MARKER = re.compile(r"(?:#|//)\s*fails_when:\s*([^\s,;]+)")
## Layout, in SVG units: the pass column, the mode column, row height, box size.
_X, _MX, _ROW, _W, _H = 150, 430, 70, 220, 40
## Characters a node's label keeps before it is cut with an ellipsis (the full text is the title).
_LABEL = 34


## @brief One node of a test's flowchart.
## @version 1
@dataclass(frozen=True)
class Node:
    """@brief Kind (start, step, check, passed), label, source line and, for a check, its mode."""

    kind: str
    text: str
    line: int | None = None
    fails_into: str | None = None


## @brief The failure-mode id an inline marker on this source line names.
## @param text The assertion's source line.
## @return The id, or None when the line carries no marker.
## @version 1
## @utility
def marker(text: str) -> str | None:
    """@brief Marker id. @return Id or None."""
    found = _MARKER.search(text)
    return found.group(1) if found else None


## @brief A test's flowchart nodes, in pass-path order.
## @param pins The test's pinned checks (`checkpins.pin_checks`), in body order.
## @param lines The test definition's source lines.
## @param first_line The file line of `lines[0]`.
## @param modes The failure modes the test's doc names with `@fails_when`.
## @return Start, then per assertion a step (when it observes a function) and a check, then passed.
## @version 1
## @req REQ-DDB-WIKI-043
def chart(pins: list[Any], lines: list[str], first_line: int, modes: list[str]) -> list[Node]:
    """@brief Derive the chart. @return Nodes."""
    only = modes[0] if len(modes) == 1 else None
    nodes = [Node("start", "start")]
    for pin in pins:
        if pin.target:
            nodes.append(Node("step", f"{pin.target}(…)", pin.bound_line or pin.line))
        index = (pin.line or 0) - first_line
        source = lines[index] if 0 <= index < len(lines) else ""
        nodes.append(Node("check", pin.statement, pin.line, marker(source) or only or UNASSIGNED))
    nodes.append(Node("passed", "passed"))
    return nodes


## @brief The flowchart as an inline SVG.
## @param nodes The chart (`chart`).
## @param meanings {mode id: meaning}, from the catalogue.
## @return HTML; "" when the chart has no check.
## @version 1
## @req REQ-DDB-WIKI-043
def flowchart_html(nodes: list[Node], meanings: dict[str, str]) -> str:
    """A MODE IS DRAWN ONCE, however many checks fail into it, so the right column reads as the
    test's distinct ways to fail. An undeclared id still draws, with its id and no meaning.

    @brief Render the chart.
    @return HTML.
    """
    if not any(n.kind == "check" for n in nodes):
        return ""
    ## EACH MODE BESIDE THE FIRST CHECK THAT FAILS INTO IT, so a fail edge runs across rather
    ## than climbing the chart (found looking at the first render).
    rows_of: dict[str, int] = {}
    for i, n in enumerate(nodes):
        if n.kind == "check":
            rows_of.setdefault(str(n.fails_into), i)
    parts = [_edges(nodes, rows_of)]
    parts += [_node(i, n) for i, n in enumerate(nodes)]
    parts += [_mode(row, m, meanings) for m, row in rows_of.items()]
    height = len(nodes) * _ROW + 20
    return (
        f'<figure class="flowchart"><svg viewBox="0 0 {_MX + _W // 2 + 20} {height}" '
        f'role="img" aria-label="test flowchart">{"".join(parts)}</svg></figure>'
    )


## @brief The failure modes the index holds: each test's, and every mode's meaning.
## @param conn Open index connection.
## @return ({test memberdef rowid: [mode ids]}, {mode id: meaning}); empty on an older index.
## @version 1
## @utility
def load_modes(conn: Any) -> tuple[dict[int, list[str]], dict[str, str]]:
    """@brief Load modes. @return Pair."""
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    meanings = (
        dict(conn.execute("SELECT mode_id, meaning FROM failure_modes"))
        if "failure_modes" in tables
        else {}
    )
    by_test: dict[int, list[str]] = {}
    if "test_failure_modes" in tables:
        for mode, rowid in conn.execute(
            "SELECT mode_id, test_memberdef_rowid FROM test_failure_modes ORDER BY mode_id"
        ):
            by_test.setdefault(int(rowid), []).append(str(mode))
    return by_test, meanings


## @brief A test's flowchart section, or "" when the test names no failure mode.
## @param pins Its pinned checks.
## @param lines Its source lines.
## @param first_line The file line of `lines[0]`.
## @param modes The modes its doc names.
## @param meanings {mode id: meaning}.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-043
def flowchart_section(
    pins: list[Any], lines: list[str], first_line: int, modes: list[str], meanings: dict[str, str]
) -> str:
    """DRAWN ONLY FOR A TEST THAT NAMES A MODE (in its doc or in a marker): on any other test
    every end would read "unassigned", which says nothing and costs a figure on every test page.
    A requirement's page lists its declared modes no test names.

    @brief Flowchart section.
    @return HTML.
    """
    nodes = chart(pins, lines, first_line, modes)
    if all(n.fails_into in (None, UNASSIGNED) for n in nodes):
        return ""
    return "<h2>How it can fail</h2>" + flowchart_html(nodes, meanings)


## @brief One pass-path node as SVG: an oval, a box or a diamond.
## @param i Its step number.
## @param node The node.
## @return SVG.
## @version 1
## @utility
def _node(i: int, node: Node) -> str:
    """@brief Node SVG. @return SVG."""
    y = 20 + i * _ROW + _H // 2
    label = node.text if len(node.text) <= _LABEL else node.text[: _LABEL - 1] + "…"
    text = f'<text x="{_X}" y="{y + 5}" text-anchor="middle">{escape(label)}</text>'
    if node.kind in ("start", "passed"):
        shape = f'<ellipse cx="{_X}" cy="{y}" rx="{_W // 3}" ry="{_H // 2}"/>'
    elif node.kind == "step":
        shape = f'<rect x="{_X - _W // 2}" y="{y - _H // 2}" width="{_W}" height="{_H}" rx="4"/>'
    else:
        hw, hh = _W // 2 + 10, _H // 2 + 6
        shape = f'<polygon points="{_X},{y - hh} {_X + hw},{y} {_X},{y + hh} {_X - hw},{y}"/>'
    where = f" (line {node.line})" if node.line else ""
    return (
        f'<g class="fc-{node.kind}" data-step="{i}"><title>{escape(node.text)}{where}</title>'
        f"{shape}{text}</g>"
    )


## @brief One failure-mode end as SVG, in the right-hand column.
## @param j Its row in that column.
## @param mode The mode id, or UNASSIGNED.
## @param meanings {mode id: meaning}.
## @return SVG.
## @version 1
## @utility
def _mode(j: int, mode: str, meanings: dict[str, str]) -> str:
    """@brief Mode SVG. @return SVG."""
    y = 20 + j * _ROW + _H // 2
    meaning = meanings.get(mode, "no mode is named here" if mode == UNASSIGNED else "")
    short = meaning if len(meaning) <= _LABEL else meaning[: _LABEL - 1] + "…"
    cls = "fc-unassigned" if mode == UNASSIGNED else "fc-mode"
    return (
        f'<g class="{cls}" data-mode="{escape(mode)}"><title>{escape(mode)}: {escape(meaning)}</title>'
        f'<rect x="{_MX - _W // 2}" y="{y - _H // 2 - 6}" width="{_W}" height="{_H + 12}" rx="10"/>'
        f'<text x="{_MX}" y="{y - 3}" text-anchor="middle">{escape(mode)}</text>'
        f'<text x="{_MX}" y="{y + 13}" text-anchor="middle" class="fc-meaning">'
        f"{escape(short)}</text></g>"
    )


## @brief The pass edges down the column, and each check's fail edge to its mode.
## @param nodes The chart.
## @param rows_of {mode: the row it is drawn on}.
## @return SVG lines.
## @version 1
## @utility
def _edges(nodes: list[Node], rows_of: dict[str, int]) -> str:
    """@brief Edge SVG. @return SVG."""
    out = []
    for i in range(len(nodes) - 1):
        y1, y2 = 20 + i * _ROW + _H, 20 + (i + 1) * _ROW
        out.append(f'<line class="fc-pass" x1="{_X}" y1="{y1}" x2="{_X}" y2="{y2}"/>')
    for i, node in enumerate(nodes):
        if node.kind != "check":
            continue
        y, my = 20 + i * _ROW + _H // 2, 20 + rows_of[str(node.fails_into)] * _ROW + _H // 2
        x1 = _X + _W // 2 + 10
        out.append(
            f'<line class="fc-fail" data-from="{i}" x1="{x1}" y1="{y}" '
            f'x2="{_MX - _W // 2}" y2="{my}"/>'
            f'<text class="fc-label" x="{x1 + 8}" y="{y - 6}">fail</text>'
        )
    return "".join(out)
