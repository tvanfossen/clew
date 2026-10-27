# SPDX-License-Identifier: MIT
"""A NEIGHBOUR THE REPLY NAMED AND THE CALLER COULD NOT FOLLOW (C2 of the 1.1.0 review).

`dossier` answers a function with its `callers` and `callees`, and the whole value of that list
is that each row is the next call. It was not, for any endpoint whose bare name is shared.

MEASURED on the frozen 1.1.0 transcripts: `dossier('execute')` was called four times in one
cell for a function the index holds as `ServerManager::execute`. The bare name returns the
`ambiguous` block, the model picks from `candidates`, and that round trip is spent on every
followed neighbour whose name collides — ~30 weight across the graded grid.

THE IDENTITY WAS ALREADY COMPUTED AND THEN DISCARDED. `_endpoint_identities` groups endpoint
rows by `(bare name, qualified name)` — its own docstring says so — and `_call_edges` reads
`identity[0]` and drops `identity[1]`. So the fix is not a new lookup or a new column; it is
publishing a value the function had in hand, derived by `qualified_name_of`, which is the same
rule the `qualified` selector accepts. Deriving the two from different rules is how the served
text came to advertise `signature`.

WHY `rowid` DID NOT ALREADY SOLVE THIS. `CallEdge.rowid` is the endpoint's memberdef rowid and
is a perfectly good identity — for a caller that can address a rowid. Nothing on the served
surface can: `dossier` takes `subject` and `qualified`, by design, because a rowid is not
stable across builds. An identity a reply carries in a form no tool accepts is not reachable.

@brief A neighbour row carries the identity needed to follow it.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import clew.query as q
from clew.query._common import identity_rowids


##
# @brief An index where one bare name is two different class members.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def colliding(tmp_path: Path) -> Path:
    """Two `execute`s under different owners, both called by one `app_run`, which is the shape
    the traced cell had: a caller list naming `execute` twice with nothing to tell them apart.

    @brief Seed an index with a collided endpoint name.
    @return Path to the database.
    @version 1
    """
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
        """
    )
    conn.execute("INSERT INTO path (rowid, name, type) VALUES (1, 'src/app.cpp', 1)")
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 1, 1, ?, ?, ?, '()', '', '', 0)",
        [
            (1, "app_run", 10, 20, "void app_run"),
            (2, "execute", 30, 40, "int ServerManager::execute"),
            (3, "execute", 50, 60, "int ClientSession::execute"),
        ],
    )
    conn.executemany(
        "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, 'doxygen_sqlite', 'exact')",
        [(1, 2), (1, 3)],
    )
    conn.commit()
    conn.close()
    return db


## @brief Each colliding callee row carries the qualified name that selects it.
## @version 1
def test_a_collided_callee_row_carries_its_qualified_identity(colliding: Path) -> None:
    """THE ASSERTION IS ON FOLLOWABILITY, NOT ON A FIELD EXISTING. Two rows share the bare
    name `execute`; what makes the list usable is that the two carry DIFFERENT qualified
    names, so a reader can tell which is which and pass one back.
    """
    built = q.dossier(colliding, "app_run")
    callees = {e.name: e for e in built.function.callees}
    assert set(callees) == {"execute"} or len(built.function.callees) == 2

    quals = sorted(e.qualified for e in built.function.callees)
    assert quals == ["ClientSession::execute", "ServerManager::execute"], (
        f"two distinct identities sharing a bare name must be distinguishable: {quals}"
    )


## @brief The published identity is one the `qualified` selector accepts.
## @version 1
def test_the_published_identity_is_accepted_by_the_selector(colliding: Path) -> None:
    """THE DEFECT THIS GUARDS AGAINST BY NAME. The served `qualified` description advertised
    `candidates[i].signature` for a parameter the code compares against the QUALIFIED NAME,
    so obeying the instruction failed 87.5% of the time it was tried. A hint or a row derived
    by one rule and accepted by another reproduces that defect in a new place.

    So this asserts the round trip rather than the string, through `identity_rowids` — which is
    the function `dossier(subject, qualified=...)` actually passes the selector to, not merely
    one that agrees with it today.
    """
    built = q.dossier(colliding, "app_run")
    conn = sqlite3.connect(str(colliding))
    try:
        for edge in built.function.callees:
            assert edge.qualified, f"{edge.name} published no identity to follow"
            ids = identity_rowids(conn, edge.name, edge.qualified)
            assert len(ids) == 1, (
                f"{edge.qualified!r} selected {len(ids)} identities; a neighbour row must name "
                f"exactly one, or following it reproduces the ambiguity it was meant to resolve"
            )
    finally:
        conn.close()


## @brief Following a published identity reaches the endpoint the row meant.
## @version 1
def test_following_the_row_reaches_that_endpoint_and_not_its_namesake(colliding: Path) -> None:
    """THE ROUND TRIP END TO END, which is the only assertion that proves the saved call. A
    field that round-trips through `matching_identity` but lands on the wrong body would pass
    the test above and still cost the cell its mark.
    """
    built = q.dossier(colliding, "app_run")
    by_qualified = {e.qualified: e for e in built.function.callees}

    followed = q.dossier(colliding, "execute", qualified="ServerManager::execute")
    assert followed is not None
    assert followed.function.rowid == by_qualified["ServerManager::execute"].rowid, (
        "the identity a row publishes must resolve to the row's own endpoint"
    )


## @brief An unqualified free function publishes no identity rather than a fabricated one.
## @version 1
def test_a_free_function_publishes_an_empty_identity(colliding: Path) -> None:
    """`qualified_name_of` returns nothing for a definition carrying no owner, and that must
    reach the wire as an empty string rather than as the bare name repeated.

    A field echoing the bare name would read as "this IS the qualified form", which would send
    a caller to pass `qualified="app_run"` — a selector value the index does not hold, and a
    refusal where there was never any ambiguity. `absence is not emptiness` on a scalar: a free
    function HAS no qualified name, and saying so costs nothing while guessing costs a call.
    """
    built = q.dossier(colliding, "execute", qualified="ServerManager::execute")
    callers = built.function.callers
    assert [c.name for c in callers] == ["app_run"]
    assert callers[0].qualified == "", (
        f"a free function has no qualified name; echoing the bare one invents a selector value "
        f"the index does not hold: {callers[0].qualified!r}"
    )
