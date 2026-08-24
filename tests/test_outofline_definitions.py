# SPDX-License-Identifier: MIT
"""An out-of-line C++ definition IS a definition, and must be labelled as one.

THE DEFECT. `resolve_rowid` and `function_candidates` both tested "is this a definition"
with `file_id == bodyfile_id`. That is true for a free function defined in the same file it
is declared in, and FALSE for the dominant C++ idiom: a method declared in a header and
defined out of line in a `.cpp`. doxygen keys that memberdef to the HEADER (`file_id`) and
points `bodyfile_id` at the `.cpp`, so the real definition failed the test while any
same-named in-place function passed it.

MEASURED ON A PUBLIC TARGET (tvanfossen/entropic). `entropic::AgentEngine::run_turn` has two
memberdef rows with `file_id = include/entropic/core/engine.h`,
`bodyfile_id = src/core/engine.cpp` and `bodystart` 2826 and 2988. Two unrelated
anonymous-namespace test helpers also named `run_turn` sit in `tests/model/*.cpp` with
`file_id == bodyfile_id`. So the test helpers ranked as definitions, the real method ranked
as a declaration, and:

  - a bare `run_turn` lookup resolved to a TEST HELPER;
  - `dossier` reported `has_body: false` for a row whose body spans lines 2826-2841;
  - the facade -> core call edge `entropic_run -> run_turn` could not land on the real
    target at all, so a depth-5 `chain_trace` never reached the engine.

995 rows on that one target have the out-of-line shape against 5656 in-place, so this is not
an edge case — it is most of the C++ class methods in a normal codebase.

WHY NO EXISTING TEST CAUGHT IT, which is the part worth keeping. Every fixture in
`test_disambiguation.py` builds a declaration as `bodyfile_id = 0` and a definition as
`bodyfile_id == file_id`; its own comment says "bodyfile_id == file_id marks a body row".
The real third shape — both ids set, DIFFERENT, with a body span — appears in no fixture. The
suite matched the detector rather than the world, exactly as the `.git`-directory fixtures did
for the submodule walk, and a mutation control could not have seen it either: it would have
tested the code against the same wrong fixtures.

The correct predicate is "does this row carry a body", i.e. a non-null `bodyfile_id` with a
positive `bodystart` — never "is the body in the same file as the declaration".
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.query import _common

## Rowids chosen so the in-place helper is the LOWER one, which is what the surviving
## `rowid` tie-break selects for a bare name. Kept that way on purpose: it keeps the
## unresolved ranking question visible in the fixture rather than hidden behind a lucky order.
OUT_OF_LINE = 20
TEST_HELPER = 10


##
# @brief Build an index holding one out-of-line definition and one in-place homonym.
# @param tmp_path Pytest scratch directory.
# @return Open connection to the fixture database.
# @version 1
def _fixture(tmp_path: Path) -> sqlite3.Connection:
    """The shape no existing fixture built: `file_id != bodyfile_id`, both set, body span
    positive — a header-declared method defined in a `.cpp`.

    @brief Seed the out-of-line versus in-place fixture.
    @return The connection.
    @version 1
    """
    conn = sqlite3.connect(str(tmp_path / "index.db"))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO path (rowid, name) VALUES (?, ?)",
        [(1, "include/lib/engine.h"), (2, "src/lib/engine.cpp"), (3, "tests/helper_test.cpp")],
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', 'run_turn', ?, ?, ?, ?, ?, '(const std::string&)', '', '', 0)",
        [
            ## The in-place test helper: an anonymous-namespace free function.
            (TEST_HELPER, 3, 3, 173, 240, "TurnResult run_turn"),
            ## The real method: declared in the header, defined in the .cpp.
            (OUT_OF_LINE, 1, 2, 2826, 2841, "std::vector<Message> lib::Engine::run_turn"),
        ],
    )
    conn.commit()
    return conn


##
# @brief A qualified lookup must reach the out-of-line definition.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_a_qualified_lookup_reaches_an_out_of_line_definition(tmp_path: Path) -> None:
    """WHAT IS NOT ASSERTED HERE, AND WHY. A BARE `run_turn` still resolves to the in-place
    test helper, because once both rows are correctly recognised as definitions they TIE and
    `rowid` ascending decides. Making the class method win would need a new preference — "not
    under tests/", or "prefer a qualified definition" — and that is a policy choice, not
    something the measurement settles. Inventing it here would be this repo's own
    anti-pattern: a heuristic whose real purpose is to make an assertion pass.

    What the fix does establish is that the out-of-line definition is no longer MISLABELLED
    as bodiless, so it is a real candidate at all, and that naming it qualified reaches it.

    @brief A qualified name resolves to the real method.
    @return None.
    @version 1
    """
    conn = _fixture(tmp_path)
    try:
        got = _common.resolve_rowid(conn, "run_turn", "lib::Engine::run_turn")
    finally:
        conn.close()
    assert got == OUT_OF_LINE, (
        "a qualified lookup could not reach the out-of-line definition, so there is no way "
        "to name the real method at all"
    )


##
# @brief `has_body` must be true for a body that lives in another file.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_candidates_report_a_body_that_lives_in_another_file(tmp_path: Path) -> None:
    """`has_body` is published in `dossier`'s `candidates`, so a wrong value does not merely
    mis-sort — it TELLS the reader the real method has no body. Observed on entropic:
    `has_body: false` for a row whose body spans lines 2826-2841.

    ORDER IS DELIBERATELY NOT ASSERTED. Both rows are genuine definitions once labelled
    correctly, so which one leads is the unresolved policy question recorded on the sibling
    test — pinning an order here would freeze a choice nobody has made.

    @brief Candidates label an out-of-line body correctly and surface both meanings.
    @return None.
    @version 1
    """
    conn = _fixture(tmp_path)
    try:
        rows = _common.function_candidates(conn, "run_turn")
    finally:
        conn.close()

    by_rowid = {row[0]: row for row in rows}
    assert OUT_OF_LINE in by_rowid, "the out-of-line definition is missing from candidates"
    assert by_rowid[OUT_OF_LINE][-1], (
        "the out-of-line definition is reported as having NO body, so a reader is told the "
        "real method is a declaration when its body spans 2826-2841 of another file"
    )
    ## BOTH must be listed. Silently collapsing to one is the failure `candidates` exists to
    ## prevent, and it is what let a test helper stand in for the real method unremarked.
    assert {row[0] for row in rows} == {OUT_OF_LINE, TEST_HELPER}, (
        f"candidates did not surface both meanings of the name: {rows}"
    )
    assert by_rowid[TEST_HELPER][-1], "the in-place helper genuinely has a body too"
