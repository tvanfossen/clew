# SPDX-License-Identifier: MIT
"""An entry point is named by the file that DEFINES it (round 4).

FOUND BUILDING ENTROPIC: a thread entry `accept_loop` was discovered with its header
(`include/.../external_bridge.h`, where doxygen files the declaration), while the flow deriver picks
an identity by the file its BODY is in, so the discovered flow named a function "not in this index"
and the build failed. Discovery now reads the body's file, as every other wiki reader does.

@brief Tests for entry-point discovery by definition file.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.wiki.entrypoints import entry_point_flows


def test_a_main_declared_in_a_header_is_found_at_its_definition(tmp_path: Path) -> None:
    """@brief main's spec names main.c (its body), not main.h (its declaration)."""
    db = tmp_path / "clew.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
            CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,
                file_id INTEGER, bodyfile_id INTEGER);
            CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, source TEXT,
                confidence TEXT);
            INSERT INTO path VALUES (1, 'src/main.h', 1), (2, 'src/main.c', 1);
            INSERT INTO memberdef VALUES (1, 'function', 'main', 1, 2), (2, 'function', 'run', 2, 2);
            INSERT INTO call_edges VALUES (1, 2, 'ast', 'resolved');
            """
        )
    specs = entry_point_flows(db, tmp_path, 2)
    assert [(s.entry, s.file) for s in specs] == [("main", "src/main.c")]
