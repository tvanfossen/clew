# SPDX-License-Identifier: MIT
"""A symbol was in the index and no natural query could find it.

**MEASURED ON A REAL GRADED CELL.** An agent was asked how a Python package reaches a C++ engine.
The answer it needed was `_candidate_paths` in `python/src/entropic/_loader.py`, whose brief reads
*"Yield candidate librentropic.so paths in resolution order"*, and `__getattr__`, whose brief reads
*"PEP 562 lazy attribute lookup importing _bindings on demand"*. Both were indexed. The agent made
eleven calls — `search("ctypes")`, `search("entropic.h")`, `search("hook lifetime")`, dossiers on
the files it did find — and was never shown either one. It scored 35.3% and its own caveat
correctly guessed that the index had not given it the loader.

    search("ctypes")          ->  8 rows, none of them the loader
    search("loader")          -> 24 rows, none of them _candidate_paths  <- defined in _loader.py
    search("manifest")        -> 12 rows, none of them _bindings_manifest
    search("resolution order")->        _candidate_paths                  <- only this worked
    search("PEP 562")         ->        __getattr__

The content was reachable ONLY by searching a phrase already inside its docstring. An agent that
knew to search "resolution order" would already know the answer.

**THE CAUSE IS ONE OMISSION IN ONE CLAUSE.** `_ranked_candidates` LEFT JOINs `path` and SELECTS
`p.name`, then matches on `m.name`, `briefdescription` and prose — never on the path it just
joined. `query/corpus.py:_matches` already globs a path and its basename for the FILES corpus;
the symbols corpus simply never used it.

**A PATH MATCH IS THE WEAKEST EVIDENCE AND RANKS LAST.** Living in `loader.py` says less about a
symbol than being named `loader` or described as one, so the new weight sits below
`SEARCH_WEIGHT_TOKEN_IN_BRIEF`. Without that, `search("src")` would promote every symbol in
`src/` above the one actually named `src`.

@brief A symbol must be findable by the file it lives in.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.query.symbols import search


##
# @brief An index whose answer lives in a file nothing else names.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def loader_db(tmp_path: Path) -> Path:
    """Models the entropic case exactly: the symbol's name and brief contain NEITHER the word
    "loader" nor "manifest", so only the containing file can connect a natural query to it. A
    decoy symbol named `loader_unrelated` sits in another file, so a passing test cannot be
    satisfied by name matching alone.

    @brief Seed a memberdef/path DB whose answer is reachable only by path.
    @return Path to the database.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO path (rowid, name) VALUES (?, ?)",
        [(1, "python/src/entropic/_loader.py"), (2, "python/src/other/helpers.py")],
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, ?, ?, 10, 20, ?, '()', ?, '', 0)",
        [
            (
                10,
                "_candidate_paths",
                1,
                1,
                "list _candidate_paths",
                "Yield candidate librentropic.so paths in resolution order.",
            ),
            (11, "loader_unrelated", 2, 2, "void loader_unrelated", "A decoy named for the query."),
        ],
    )
    conn.commit()
    conn.close()
    return db


##
# @brief Searching the file's name must find the symbol defined in it.
# @param loader_db The seeded database.
# @return None.
# @version 1
def test_a_symbol_is_findable_by_the_file_it_lives_in(loader_db: Path) -> None:
    """THE REGRESSION, NAMED. `_candidate_paths` contains neither "loader" nor "manifest" in its
    name or brief; `_loader.py` is the only connection a natural query has to it.

    @brief A path match surfaces the symbol.
    @return None.
    @version 1
    """
    names = [row.name for row in search(loader_db, "loader", 25)]

    assert "_candidate_paths" in names, (
        f"searching 'loader' did not surface the symbol defined in _loader.py; got {names}"
    )


##
# @brief A name match must still outrank a mere path match.
# @param loader_db The seeded database.
# @return None.
# @version 1
def test_a_name_match_still_outranks_a_path_match(loader_db: Path) -> None:
    """THE OVER-EAGER FIX IS THE REAL RISK. Weighting a path like a name would let `search("src")`
    promote every symbol under `src/` above the one actually called `src`, which is a worse surface
    than the one this replaces. `loader_unrelated` is NAMED for the query; `_candidate_paths` only
    lives in a file named for it, so the named one must come first.

    @brief Name beats path.
    @return None.
    @version 1
    """
    names = [row.name for row in search(loader_db, "loader", 25)]

    assert names.index("loader_unrelated") < names.index("_candidate_paths"), (
        f"a path match outranked a name match, which would bury named symbols: {names}"
    )
