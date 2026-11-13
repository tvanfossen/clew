# SPDX-License-Identifier: MIT
"""A neighbour row's `qualified` is the SHORTEST separator-aligned suffix that is still unique.

1.3.7, Track 3 (token cost). Measured on the 1.3.0-final transcripts, `qualified` was 29% of
mattermost's neighbour-row bytes: a TypeScript identity spells the module path in full
(`app.database.operator.server_data_operator.handlers.post.PostHandler._createOrUpdateScheduledPost`)
and the row's `file` spells it again. The rule that keeps the field followable — `test_edge_identity`:
the published value must select exactly one identity — holds for any suffix that is unique among
the identities sharing the bare name, so the row publishes the shortest such suffix, aligned to a
`.` or `::` boundary, and the selector accepts it.

A VALUE CHANGE, NOT A KEY CHANGE: the key is unchanged and the selector still accepts the full
spelling, so a consumer holding a full name keeps working (semver-covered wire keys, owner
2026-11-12: no major increment).

@brief Tests for the shortest-unique-suffix `qualified`.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import clew.query as q
from clew.query._common import identity_rowids, short_qualified


@pytest.mark.parametrize(
    ("full", "others", "short"),
    [
        ("ns::ServerManager::execute", {"ns::ClientSession::execute"}, "ServerManager::execute"),
        ("app.a.Handler.run", {"app.b.Other.run"}, "Handler.run"),
        ("app.a.Handler.run", {"app.b.Handler.run"}, "a.Handler.run"),
        ("app.a.Handler.run", set(), "Handler.run"),
        ("run", {"app.b.Handler.run"}, "run"),
        ## NOT A STRING SUFFIX: `Monitor.run` ends `HealthMonitor.run` as text but not at a boundary.
        ("x.Monitor.run", {"y.HealthMonitor.run"}, "Monitor.run"),
    ],
)
def test_the_shortest_unique_suffix(full: str, others: set[str], short: str) -> None:
    """A QUALIFIED NAME KEEPS AT LEAST ITS OWNER: a bare name is what `name` already says, so the
    shortest form still carries one qualifier when the full name had one.

    @brief short_qualified picks the shortest boundary-aligned unique suffix.
    @return None.
    @version 1
    """
    assert short_qualified(full, others) == short


@pytest.fixture()
def nested(tmp_path: Path) -> Path:
    """@brief Two `run`s whose owners share a class name in different modules. @return DB path."""
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT
        );
        INSERT INTO path VALUES (1, 'src/app.ts', 1);
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?, ?, '()', '', '', 0)",
        [
            (1, "main", 1, 5, "main"),
            (2, "run", 10, 12, "app.alpha.Handler.run"),
            (3, "run", 20, 22, "app.beta.Handler.run"),
        ],
    )
    conn.executemany("INSERT INTO call_edges VALUES (?, ?, 'ast', 'resolved')", [(1, 2), (1, 3)])
    conn.commit()
    conn.close()
    return db


def test_a_callee_row_publishes_the_short_form_and_the_selector_follows_it(nested: Path) -> None:
    """THE ROUND TRIP, through `identity_rowids` — what `dossier(subject, qualified=...)` uses.

    @brief Short published identities each select exactly their own function.
    @return None.
    @version 1
    """
    built = q.dossier(nested, "main")
    quals = sorted(e.qualified for e in built.function.callees)
    assert quals == ["alpha.Handler.run", "beta.Handler.run"]
    conn = sqlite3.connect(str(nested))
    try:
        for edge in built.function.callees:
            assert identity_rowids(conn, edge.name, edge.qualified) == [
                2 if edge.qualified.startswith("alpha") else 3
            ]
        ## The FULL spelling still selects, so a consumer holding one keeps working.
        assert identity_rowids(conn, "run", "app.alpha.Handler.run") == [2]
    finally:
        conn.close()
