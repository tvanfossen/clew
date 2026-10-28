# SPDX-License-Identifier: MIT
"""THE LAST UNFIXED CAPABILITY ITEM IN THE NEGATIVE-GAP SET.

All thirteen clusters where `index_only` scored below the shell-only arm on the 1.1.0 grid have
now been traced call-by-call. Twelve are accounted for: eleven have a landed fix touching their
actual misses, `self` Q6 was a grader defect (18 of 18 judge calls errored and the cell was scored
0.0), and `self` Q4 has no retrieval failure at all — 2 to 3 calls, zero misses, every reply
landed, and the agent simply stopped on a fifteen-mark question.

The thirteenth is this. mbedtls Q5 (−16.67) has two failed marks. One — "the PUBLIC API surface
is a single function, `mbedtls_ct_memcmp`, while the rest of the primitives are library-internal"
— became a two-call answer when a file became a subject: `include/mbedtls/constant_time.h` lists
one function, `library/constant_time_internal.h` lists twenty-two. The other is:

    "conveys that the primitives are consumed broadly across the library — on the order of
     twenty modules — rather than being confined to one or two"

THE INDEX CAN ANSWER THAT IN ONE QUERY AND THE SURFACE CANNOT ASK IT. One SQL join counts the
distinct files containing callers of a symbol. `CallEdge` carries `name`, `qualified`, `rowid`,
`source`, `confidence` — and no file. So "how broadly is this consumed" costs one `dossier` per
caller: 62 of them for `table_exists` on clew's own index, measured. A model will guess instead,
and the mark is about the magnitude.

SAME SHAPE AS C2, WHICH PUBLISHED THE QUALIFIED IDENTITY ON THE SAME ROW FOR THE SAME REASON: a
neighbour row that names a thing without carrying what you need to act on it is a row that costs
a round trip. The file is one join away from rows already being read.

@brief A neighbour row says which file its endpoint lives in.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import clew.query as q


##
# @brief An index where one function is called from three different files.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def spread(tmp_path: Path) -> Path:
    """The breadth shape at minimum size: one callee, three callers, in three files. The count
    that matters is DISTINCT FILES (3), not callers (3) — a file with two callers must not count
    twice, which is why one file here holds two of them.

    @brief Seed a callee consumed across several files.
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
    conn.executemany(
        "INSERT INTO path (rowid, name, type) VALUES (?, ?, 1)",
        [(1, "library/ct.c"), (2, "library/aes.c"), (3, "library/rsa.c")],
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, ?, ?, ?, ?, ?, '()', '', '', 0)",
        [
            (1, "mbedtls_ct_memcmp", 1, 1, 10, 20, "int mbedtls_ct_memcmp"),
            (2, "aes_crypt", 2, 2, 30, 40, "int aes_crypt"),
            (3, "aes_verify", 2, 2, 50, 60, "int aes_verify"),
            (4, "rsa_check", 3, 3, 70, 80, "int rsa_check"),
        ],
    )
    conn.executemany(
        "INSERT INTO call_edges VALUES (?, 1, 'doxygen_sqlite', 'exact')", [(2,), (3,), (4,)]
    )
    conn.commit()
    conn.close()
    return db


## @brief Each caller row names the file its caller lives in.
## @version 1
def test_a_caller_row_names_its_file(spread: Path) -> None:
    """RED BEFORE THE FIX: `CallEdge` has no `file`, so counting the modules that consume a
    symbol costs one `dossier` per caller.
    """
    built = q.dossier(spread, "mbedtls_ct_memcmp")
    files = {c.name: c.file for c in built.function.callers}

    assert files == {
        "aes_crypt": "library/aes.c",
        "aes_verify": "library/aes.c",
        "rsa_check": "library/rsa.c",
    }, files


## @brief Breadth is countable from one reply.
## @version 1
def test_breadth_is_countable_without_a_second_call(spread: Path) -> None:
    """THE MARK IS ABOUT A MAGNITUDE — "on the order of twenty modules" — so what has to be
    cheap is the COUNT of distinct files, not the list of callers. Two callers in one file is one
    module, which is the case this fixture plants and the one a caller-count would get wrong.
    """
    built = q.dossier(spread, "mbedtls_ct_memcmp")
    callers = built.function.callers

    assert len(callers) == 3, "three callers"
    assert len({c.file for c in callers}) == 2, (
        "two DISTINCT files — a caller count is not a module count"
    )


## @brief An endpoint whose file is unknown says so by absence.
## @version 1
def test_an_endpoint_with_no_resolvable_file_reports_empty(tmp_path: Path) -> None:
    """`''` AND NOT A GUESS. A caller row whose `file_id` resolves to no `path` row has no file to
    report, and inventing one would put a path nobody can open into a reply whose value is that
    its paths are real. The same rule `FileSubject.harvested` follows one module over.
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
    conn.execute("INSERT INTO path (rowid, name, type) VALUES (1, 'library/ct.c', 1)")
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, ?, ?, ?, ?, ?, '()', '', '', 0)",
        [(1, "callee", 1, 1, 10, 20, "int callee"), (2, "orphan", 99, 99, 30, 40, "int orphan")],
    )
    conn.execute("INSERT INTO call_edges VALUES (2, 1, 'doxygen_sqlite', 'exact')")
    conn.commit()
    conn.close()

    built = q.dossier(db, "callee")
    assert [c.file for c in built.function.callers] == [""], (
        "an unresolvable file must be empty, never invented"
    )
