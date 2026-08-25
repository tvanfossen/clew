# SPDX-License-Identifier: MIT
"""Which indexed files are TEST code, so a bare name prefers the library over a helper.

THE DEFECT THIS SETTLES. A bare function name can denote several real definitions, and
`resolve_rowid` had no principled way to choose. Measured on tvanfossen/entropic:
`run_turn` has four rows —

    entropic::AgentEngine                   include/entropic/core/engine.h   (out of line)
    entropic::AgentEngine                   include/entropic/core/engine.h   (overload)
    anonymous_namespace{...benchmark.cpp}   tests/model/...benchmark.cpp     (file-local)
    anonymous_namespace{...feasibility.cpp} tests/model/...feasibility.cpp   (file-local)

— and the resolver picked a TEST HELPER, because its first term is `file_id == bodyfile_id`
("the body is in the same file as the declaration"). That term is exactly right for C's
decl/def duality and exactly backwards here: the real method is declared in a header and
defined out of line, so it loses to two file-local helpers that happen to be self-contained.
The consequence is not cosmetic — `dossier`'s primary subject was a test helper, and the
facade-to-core call edge could not land on the real method at all.

337 function names on that one target have more than one row, so this is not a corner.

BUILT-IN DEFAULT PLUS A DECLARED OVERRIDE, WHICH IS THE ONLY SANCTIONED SHAPE. A
hardcoded-only notion of "test path" is exactly what this project forbids: `tests/` is a
convention, and repos legitimately use `test/`, `spec/`, `t/` or something else entirely. So
the defaults below are HEURISTICS in the layered sense — a repo that declares `test_paths:`
displaces them rather than adding to them, because a repo naming its own layout is stating that
layout rather than annotating ours.

THE DECISION IS BAKED INTO THE INDEX, and that is forced rather than chosen. `resolve_rowid`
runs against a database with no access to `.clew.yaml` and no repo root, so a pattern list
resolved at build time cannot be re-derived at query time. This module therefore stamps the
matching `path` rowids into a table the resolver joins. An index built before this stage
existed simply has no table, and the resolver degrades to its previous ordering rather than
failing — a missing table is missing knowledge, not a reason to refuse an answer.

MATCHED ON THE REPO-RELATIVE PATH, never an absolute one. Anything reachable over MCP is
published, and a `path.name` once carried the builder's home directory in every row.
"""

from __future__ import annotations

import fnmatch
import sqlite3
from pathlib import PurePosixPath

from ._common import logger

## The built-in guesses, at the HEURISTIC tier so a declaration displaces them entirely.
##
## Directory segments first — the four the owner named plus the two that show up as often in
## the wild — then file-name conventions, because C++ and Go both routinely put `foo_test.cpp`
## and `foo_test.go` NEXT TO the code rather than under a test directory. Omitting those would
## make the feature look like it worked while missing every repo that colocates its tests.
TEST_PATH_FACTS: tuple[str, ...] = (
    "tests/*",
    "test/*",
    "pytest/*",
    "ctest/*",
    "spec/*",
    "testing/*",
    "*/tests/*",
    "*/test/*",
    "*/pytest/*",
    "*/ctest/*",
    "*/spec/*",
    "*/testing/*",
    "test_*",
    "*_test.*",
    "*_tests.*",
    "*_spec.*",
    "*Test.*",
    "*Tests.*",
)

_DDL = """
CREATE TABLE IF NOT EXISTS test_scope (
    path_rowid INTEGER PRIMARY KEY
);
"""


##
# @brief Whether one repo-relative path is test code under the given patterns.
# @param rel Repo-relative path.
# @param patterns Glob patterns, matched against the whole path and against the basename.
# @return True when any pattern matches.
# @version 1
# @dg_internal
def is_test_path(rel: str, patterns: tuple[str, ...] | list[str]) -> bool:
    """Matched against BOTH the full relative path and the basename, because the two pattern
    families in `TEST_PATH_FACTS` mean different things: `tests/*` is about location and
    `*_test.*` is about the file itself. Requiring one form to serve both would silently drop
    whichever family lost.

    A leading `./` is stripped so a path spelled either way matches the same patterns.

    @brief Test whether a path is test code.
    @return True when it matches any pattern.
    @version 1
    """
    candidate = rel.lstrip("./")
    name = PurePosixPath(candidate).name
    return any(fnmatch.fnmatch(candidate, pat) or fnmatch.fnmatch(name, pat) for pat in patterns)


##
# @brief Stamp the indexed files that are test code, for the resolver to join against.
# @param conn Open connection to the index being built.
# @param patterns The resolved test-path patterns.
# @return Number of files marked.
# @version 1
# @req REQ-DDB-QUERY-003
def mark_test_scope(conn: sqlite3.Connection, patterns: tuple[str, ...] | list[str]) -> int:
    """WRITES THE TABLE EVEN WHEN NOTHING MATCHES, and that is the load-bearing detail. An
    ABSENT table means "this index predates the stage" and the resolver keeps its old ordering;
    an EMPTY table means "this stage ran and found no test code", which is a real answer about
    a repo that has none. Collapsing the two would make an old index and a test-free repo
    indistinguishable, and the resolver would silently behave differently on each.

    Rebuilt from scratch on every build rather than merged, because the pattern set can shrink
    as well as grow and a stale mark is worse than no mark: it would demote a library
    definition on the strength of a rule the operator has since withdrawn.

    @brief Record which path rows are test code.
    @return The count marked.
    @version 1
    """
    conn.executescript(_DDL)
    conn.execute("DELETE FROM test_scope")
    rows = [
        (rowid,)
        for rowid, name in conn.execute("SELECT rowid, name FROM path WHERE type = 1")
        if is_test_path(str(name), patterns)
    ]
    conn.executemany("INSERT OR IGNORE INTO test_scope(path_rowid) VALUES (?)", rows)
    total = conn.execute("SELECT COUNT(*) FROM path WHERE type = 1").fetchone()[0]
    logger.info(
        "test scope: %d of %d indexed file(s) are test code under %d pattern(s); a bare "
        "ambiguous name now prefers a definition outside them",
        len(rows),
        total,
        len(patterns),
    )
    return len(rows)
