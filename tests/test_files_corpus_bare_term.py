# SPDX-License-Identifier: MIT
"""Seven indexed source files, and the corpus that lists files said there were none.

**MEASURED ON A GRADED CELL.** Asked how deeply a C++ project depends on a vendored library, an
agent's second call was `search(corpus="files", text="llama")`. It got **count=0**. The repository
has seven indexed `llama_cpp_*` source files. The agent concluded the dependency was contained
inside one directory — the exact wrong conclusion the question was built to catch — and scored
38.5%.

The cause is a syntax mismatch no reply made visible in time: **this corpus's `text` is a path
GLOB, while every other corpus takes a substring.** `symbols`, `prose` and `config` all match
substrings, so a model passes one here too, and `llama` as a glob matches nothing because no file
is NAMED `llama`.

The note that came back led with the wrong explanation:

    "No indexed file matches 'llama'. This corpus holds INDEXED SOURCE FILES only, so a build
     script, a Doxyfile, a data file or anything else the index does not parse is absent here BY
     CONSTRUCTION ... Re-glob more broadly (`*.c`, `tests/*`) if you wanted files."

Every clause is true in general and the first one is FALSE HERE — the files are indexed source.
The actionable sentence is last, after a confident misdiagnosis. The same agent later used
`extern/*` correctly, so it could work globs; it just never doubted the `llama` zero.

**A BARE WORD IS NEVER A VALID PATH**, so retrying a metacharacter-free term as `*term*` cannot
change any answer that previously matched — it can only replace a false empty with the files.

@brief A bare term must find the files whose paths contain it.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.query.corpus import list_files


##
# @brief An index whose files carry a term in their path but not as a whole name.
# @param tmp_path Per-test temporary directory.
# @return Path to the built database.
# @version 1
@pytest.fixture()
def files_db(tmp_path: Path) -> Path:
    """Mirrors the entropic shape: several `llama_cpp_*` files under one directory, and an
    unrelated file so a passing test cannot be satisfied by returning everything.

    @brief Seed a path table with term-bearing files.
    @return Path to the database.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER, local INT, found INT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, file_id INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO path (rowid, name, type, local, found) VALUES (?, ?, 1, 1, 1)",
        [
            (1, "src/inference/llama_cpp_backend.cpp"),
            (2, "src/inference/llama_cpp_backend.h"),
            (3, "src/inference/llama_cpp_sampler.cpp"),
            (4, "src/core/response_generator.cpp"),
        ],
    )
    conn.commit()
    conn.close()
    return db


##
# @brief A bare term must list the files whose paths contain it.
# @param files_db The seeded database.
# @return None.
# @version 1
def test_a_bare_term_finds_the_files_containing_it(files_db: Path) -> None:
    """THE REGRESSION, NAMED. `llama` is not a path and never matches as a glob, so this returned
    nothing while three matching files sat in the table.

    @brief A bare term matches by substring.
    @return None.
    @version 1
    """
    names = [f.path for f in list_files(files_db, "llama")]

    assert len(names) == 3, f"a bare term found {len(names)} of 3 llama files: {names}"
    assert all("llama" in n for n in names), names


##
# @brief An explicit glob must keep working exactly as before.
# @param files_db The seeded database.
# @param glob The glob to apply.
# @param expected How many files it must match.
# @return None.
# @version 1
@pytest.mark.parametrize(
    ("glob", "expected"),
    [("src/core/*", 1), ("*.h", 1), ("src/inference/*", 3), ("*backend*", 2)],
)
def test_an_explicit_glob_is_unchanged(files_db: Path, glob: str, expected: int) -> None:
    """THE HALF THAT MUST NOT MOVE. Globbing is the documented behaviour and other callers depend
    on it; a fix that turned every glob into a substring search would trade one wrong answer for
    a broader one. A term containing `*`, `?` or `[` is taken at its word.

    @brief Globs are untouched.
    @param glob The glob.
    @param expected Expected match count.
    @return None.
    @version 1
    """
    assert len(list_files(files_db, glob)) == expected, (
        f"glob {glob!r} no longer matches {expected} file(s)"
    )


##
# @brief A term matching nothing must still return nothing.
# @param files_db The seeded database.
# @return None.
# @version 1
def test_a_term_that_matches_nothing_still_returns_nothing(files_db: Path) -> None:
    """THE PERMISSIVE FAILURE. A fix that returned every file when the term missed would make the
    corpus useless and would read as success against the test above.

    @brief A genuine miss is still a miss.
    @return None.
    @version 1
    """
    assert list_files(files_db, "no_such_thing_anywhere") == []
