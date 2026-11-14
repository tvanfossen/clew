# SPDX-License-Identifier: MIT
"""A function's calls in source order, each with the control-flow frames that enclose it.

1.4.0 Track 4 (clew wiki), W2. A sequence diagram derived from the index needs two things the
index does not store: the ORDER of a function's calls, and the FRAMES (loop, if/else, try/catch,
switch case) around each one. `call_edges` holds one row per (caller, callee, source) with no
site at all. So this reads the caller's own source at QUERY time, through the same parser and the
same call-site harvester the index is built with, and attaches the control structures whose line
span contains each site.

QUERY-TIME, NOT STORED, AND THAT IS THE DESIGN DECISION. Storing sites would mean a new table, a
`CLEW_BUILD_VERSION` bump and a cold rebuild of every index, for a consumer — the wiki generator —
that runs offline and can afford to parse the handful of caller files a flow touches.

LINE GRANULARITY, stated rather than hidden: a frame contains a site when the site's line is in
the frame's line span. Two calls on one line in different branches (`if (x) a(); else b();`) share
that line's frames. A call inside a nested function or closure belongs to that function, not to
this one, and is excluded by the spans the index records.

@brief Ordered call sites with enclosing frames, read from source at query time.
@version 1
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ._common import DbSource, connect, identity_rowids

## Control-structure node types → frame kind. A frame whose BODY is a named child is measured by
## that child's span (an `if`'s consequence, a `try`'s body), so a call in the `else` branch is not
## also inside the `if` frame.
_FRAME_KINDS: dict[str, tuple[str, str | None]] = {
    "if_statement": ("if", "consequence"),
    "elif_clause": ("elif", "consequence"),
    "else_clause": ("else", None),
    "for_statement": ("loop", None),
    "for_in_statement": ("loop", None),
    "for_range_loop": ("loop", None),
    "while_statement": ("loop", None),
    "do_statement": ("loop", None),
    "try_statement": ("try", "body"),
    "catch_clause": ("catch", None),
    "except_clause": ("catch", None),
    "finally_clause": ("finally", None),
    "switch_case": ("case", None),
    "case_statement": ("case", None),
}


## @brief One control-flow frame around a call: its kind and line span.
## @version 1
@dataclass(frozen=True)
class Frame:
    """@brief A loop / if / else / try / catch / case span. @version 1"""

    kind: str
    line: int
    end_line: int


## @brief One call site in a function's body, with the frames enclosing it, outermost first.
## @version 1
@dataclass(frozen=True)
class CallSite:
    """@brief A call by bare callee name at a line, inside frames. @version 1"""

    callee: str
    line: int
    frames: tuple[Frame, ...] = field(default_factory=tuple)


## @brief A function's call sites in source order, each with its enclosing frames.
## @param db The index.
## @param repo_root The working tree the source is read from.
## @param name The function's bare name.
## @param qualified Optional identity selector, as `dossier` takes it.
## @return The sites in line order; [] when the function calls nothing; None when the index
##         holds no such function, no body extent for it, or the source cannot be parsed.
## @version 1
## @req REQ-DDB-QUERY-015
def call_sequence(
    db: DbSource, repo_root: Path | str, name: str, qualified: str | None = None
) -> list[CallSite] | None:
    """NONE IS NOT EMPTY. "This function calls nothing" is a measured `[]`; an unknown function, a
    declaration with no body, or a file the parser cannot read is None — the sequence was never
    looked at, and the caller must not draw an empty lane for it.

    @brief Ordered call sites with frames.
    @return Sites or None.
    @version 1
    """
    with connect(db) as conn:
        located = _body_of(conn, name, qualified)
    if located is None:
        return None
    rel, start, end, nested = located
    parsed = _parse(Path(repo_root), rel)
    if parsed is None:
        return None
    tree, src = parsed
    from ..call_edges import _ast_harvest_calls

    lines = sorted(
        {
            (str(site[0]), int(site[1]))
            for site in _ast_harvest_calls(tree, src)
            if start <= int(site[1]) <= end and not _in_any(int(site[1]), nested)
        },
        key=lambda s: (s[1], s[0]),
    )
    frames = _frames(tree.root_node, start, end)
    return [
        CallSite(
            callee=callee,
            line=line,
            frames=tuple(f for f in frames if f.line <= line <= f.end_line),
        )
        for callee, line in lines
    ]


## @brief The function's file, body span, and the spans of functions nested inside it.
## @param conn Open connection.
## @param name Bare name.
## @param qualified Optional selector.
## @return (repo-relative file, body start, body end, nested spans) or None.
## @version 1
## @dg_internal
def _body_of(
    conn: sqlite3.Connection, name: str, qualified: str | None
) -> tuple[str, int, int, list[tuple[int, int]]] | None:
    """THE DEFINITION ROW: the identity's row that carries a body extent.

    @brief Locate the body.
    @return Location or None.
    """
    rowids = identity_rowids(conn, name, qualified)
    if not rowids:
        return None
    marks = ",".join("?" for _ in rowids)
    row = conn.execute(
        "SELECT p.rowid, p.name, m.bodystart, m.bodyend FROM memberdef m "
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        f"WHERE m.rowid IN ({marks}) AND m.bodystart > 0 AND m.bodyend >= m.bodystart "
        "ORDER BY m.bodyend - m.bodystart DESC LIMIT 1",
        rowids,
    ).fetchone()
    if row is None:
        return None
    path_rowid, rel, start, end = int(row[0]), str(row[1]), int(row[2]), int(row[3])
    nested = [
        (int(s), int(e))
        for s, e in conn.execute(
            "SELECT bodystart, bodyend FROM memberdef WHERE kind = 'function' "
            "AND COALESCE(NULLIF(bodyfile_id, 0), file_id) = ? AND bodystart > ? AND bodyend <= ?",
            (path_rowid, start, end),
        )
    ]
    return rel, start, end, nested


## @brief Whether a line is inside any of the given spans.
## @param line The line.
## @param spans (start, end) spans.
## @return True when contained.
## @version 1
## @dg_internal
def _in_any(line: int, spans: list[tuple[int, int]]) -> bool:
    """@brief Span membership. @return True when inside one."""
    return any(s <= line <= e for s, e in spans)


## @brief Parse one file with the index's own parser.
## @param repo_root The working tree.
## @param rel The repo-relative file.
## @return (tree, source bytes) or None.
## @version 1
## @dg_internal
def _parse(repo_root: Path, rel: str) -> tuple[Any, bytes] | None:
    """@brief Parse a file. @return Tree and bytes, or None."""
    from ..harvest import _ast_parse_one_file

    return _ast_parse_one_file(rel, repo_root / rel, {})


## @brief Every control-flow frame whose span overlaps a line range, outermost first.
## @param root The parse tree's root node.
## @param start First line of interest.
## @param end Last line of interest.
## @return Frames sorted outermost first (by start line, then by length descending).
## @version 1
## @dg_internal
def _frames(root: Any, start: int, end: int) -> list[Frame]:
    """@brief Collect frames in a span. @return Frames."""
    found: list[Frame] = []
    stack = [root]
    while stack:
        node = stack.pop()
        first, last = node.start_point[0] + 1, node.end_point[0] + 1
        if last < start or first > end:
            continue
        spec = _FRAME_KINDS.get(node.type)
        if spec is not None:
            body = node.child_by_field_name(spec[1]) if spec[1] else None
            span = body if body is not None else node
            found.append(Frame(spec[0], span.start_point[0] + 1, span.end_point[0] + 1))
        stack.extend(node.children)
    return sorted(found, key=lambda f: (f.line, -(f.end_line - f.line)))
