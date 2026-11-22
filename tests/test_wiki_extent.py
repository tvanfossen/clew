# SPDX-License-Identifier: MIT
"""A function's bundled body starts at its declaration, not at its first statement (W-11, 2.0.0).

OWNER REVIEW 2026-11-22 of the d3a32e2c wiki: `sym-clew-wiki-flow-py.html#s-derive_flow` had "the
clickable but not the visual". 598 sections on 194 pages read "The index is older than this file"
and bundled neither body nor activity diagram, though the index was current (derive_flow recorded
at line 127, as in the file). The extent began at `bodystart` (142, past a 15-line signature), and
the staleness check wants the name in the extent's first four lines.

@brief Tests the extent a symbol page bundles.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.wiki.symbols import _body, _definitions

_SRC = (
    "def derive_flow(\n"
    "    db,\n"
    "    repo_root,\n"
    "    entry,\n"
    "    *,\n"
    "    depth=3,\n"
    "):\n"
    '    """Derive."""\n'
    "    return depth\n"
)


def _conn(
    tmp_path: Path, line: int, bodystart: int, bodyfile: int | None = None
) -> sqlite3.Connection:
    """@brief A minimal index with one function. @return Connection."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);"
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,"
        " argsstring TEXT, briefdescription TEXT, bodystart INT, bodyend INT, line INT,"
        " file_id INT, bodyfile_id INT);"
        "INSERT INTO path VALUES (1, 'm.py'), (2, 'm.h');"
    )
    conn.execute(
        "INSERT INTO memberdef VALUES (1, 'function', 'derive_flow', 'def derive_flow', '(...)', '',"
        " ?, 9, ?, ?, ?)",
        (bodystart, line, 2 if bodyfile else 1, bodyfile),
    )
    (tmp_path / "m.py").write_text(_SRC, encoding="utf-8")
    return conn


def test_a_long_signature_still_bundles_its_body(tmp_path: Path) -> None:
    """@brief Declared at 1, body from 8: the section shows the def line and is not called stale."""
    (d,) = _definitions(_conn(tmp_path, line=1, bodystart=8), {("derive_flow", "m.py")})
    html = _body(tmp_path, d)
    assert "older than this file" not in html, html
    assert "def derive_flow(" in html


def test_an_out_of_line_definition_keeps_its_body_start(tmp_path: Path) -> None:
    """@brief Declared in a header (another file), defined in m.py: the extent stays the body's."""
    (d,) = _definitions(
        _conn(tmp_path, line=40, bodystart=1, bodyfile=1), {("derive_flow", "m.py")}
    )
    assert d.start == 1
