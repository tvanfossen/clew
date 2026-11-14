# SPDX-License-Identifier: MIT
"""A walk seeded by a qualified identity follows that identity's edges, not its namesakes'.

1.4.0 Track 4 (clew wiki), W1. `chain_trace` resolved every hop by BARE NAME, so a walk from
`ServerManager::execute` also walked `ClientSession::execute`'s callees — its own docstring
refused the `qualified` selector for exactly that reason. A derived sequence diagram is a walk,
and a diagram that drew a namesake's calls as this function's would be confidently wrong. With
`qualified` the walk is identity-scoped: the seed and every call hop resolve by identity rowids.

Without `qualified` the walk is unchanged (name-scoped), so nothing already relying on it moves.

@brief Tests for the identity-scoped traversal.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import clew.query as q
from clew.query.traversal import chain_trace


@pytest.fixture()
def namesakes(tmp_path: Path) -> Path:
    """@brief Two `execute`s, each calling a different helper. @return DB path."""
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
        INSERT INTO path VALUES (1, 'src/app.cpp', 1);
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?, ?, '()', '', '', 0)",
        [
            (1, "execute", 10, 20, "int ServerManager::execute"),
            (2, "execute", 30, 40, "int ClientSession::execute"),
            (3, "helper_a", 50, 55, "void helper_a"),
            (4, "helper_b", 60, 65, "void helper_b"),
        ],
    )
    conn.executemany(
        "INSERT INTO call_edges VALUES (?, ?, 'doxygen_sqlite', 'exact')", [(1, 3), (2, 4)]
    )
    conn.commit()
    conn.close()
    return db


def test_a_qualified_walk_follows_only_that_identity(namesakes: Path) -> None:
    """@brief The ServerManager walk reaches helper_a and not ClientSession's helper_b.
    @return None.
    @version 1
    """
    chain = chain_trace(namesakes, "execute", qualified="ServerManager::execute", max_depth=2)
    reached = {n.name for n in chain.nodes}
    assert "helper_a" in reached and "helper_b" not in reached, reached
    seed = next(n for n in chain.nodes if n.depth == 0)
    assert seed.rowid == 1 and seed.qualified == "ServerManager::execute"


def test_a_bare_walk_is_unchanged(namesakes: Path) -> None:
    """@brief Without `qualified` the walk stays name-scoped, as before.
    @return None.
    @version 1
    """
    reached = {n.name for n in chain_trace(namesakes, "execute", max_depth=2).nodes}
    assert {"helper_a", "helper_b"} <= reached


def test_the_dossier_depth_walk_honours_qualified(namesakes: Path) -> None:
    """THE SURFACE TAKES IT TOO: `dossier(subject, qualified=..., depth=2)`'s chain is the
    identity-scoped one.

    @brief dossier passes `qualified` to its walk.
    @return None.
    @version 1
    """
    built = q.dossier(namesakes, "execute", qualified="ServerManager::execute", depth=2)
    assert built is not None and built.chain is not None
    assert {n.name for n in built.chain.nodes} == {"execute", "helper_a"}


def test_an_unknown_identity_walks_nothing(namesakes: Path) -> None:
    """@brief A qualified name the index does not hold yields an empty chain, never the union.
    @return None.
    @version 1
    """
    assert chain_trace(namesakes, "execute", qualified="Nope::execute", max_depth=2).nodes == []
