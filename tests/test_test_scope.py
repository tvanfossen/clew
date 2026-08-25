# SPDX-License-Identifier: MIT
"""A bare ambiguous name must prefer the library definition over a test helper.

MEASURED ON A PINNED TARGET (tvanfossen/entropic). `run_turn` has four definitions: two rows
for `entropic::AgentEngine` declared in `include/entropic/core/engine.h` and defined out of
line in `src/core/engine.cpp`, and two file-local helpers in `tests/model/*.cpp`. The resolver
picked a TEST HELPER, because its leading term was `file_id == bodyfile_id` — right for C's
decl/def duality, and backwards here: the real method is out of line so that term is FALSE for
it and TRUE for both helpers. 337 function names on that target have more than one row.

WHAT IS ASSERTED HERE, AND WHAT DELIBERATELY IS NOT. The ranking is a POLICY the owner chose
(deprioritise test paths, with declarable patterns and sensible defaults), so these tests pin
the policy's mechanics: the defaults match what a reader would expect, a DECLARATION DISPLACES
them rather than extending them, and an index built before the stage existed keeps its previous
ordering instead of raising. They do NOT assert that any particular repo's layout is "test",
which is the part that must stay declarable.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.query import _common
from clew.testscope import TEST_PATH_FACTS, is_test_path, mark_test_scope

LIBRARY = 20
HELPER = 10


##
# @brief Build an index with one library definition and one same-named test helper.
# @param tmp_path Pytest scratch directory.
# @param mark Whether to run the test-scope stage.
# @return Open connection to the fixture database.
# @version 1
def _fixture(tmp_path: Path, mark: bool) -> sqlite3.Connection:
    """Shaped on the real entropic rows: the LIBRARY definition is out of line
    (`file_id` = header, `bodyfile_id` = the .cpp) and the TEST helper is in place
    (`file_id == bodyfile_id`). That is what makes the in-place term favour the helper, so a
    fixture without this asymmetry could not reproduce the defect.

    The helper also gets the LOWER rowid, since `rowid` ascending is the final tie-break.

    @brief Seed the library-versus-test-helper fixture.
    @return The connection.
    @version 1
    """
    conn = sqlite3.connect(str(tmp_path / f"index-{mark}.db"))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """
    )
    conn.executemany(
        "INSERT INTO path (rowid, type, name) VALUES (?, 1, ?)",
        [
            (1, "include/lib/engine.h"),
            (2, "src/lib/engine.cpp"),
            (3, "tests/model/engine_test.cpp"),
        ],
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', 'run_turn', ?, ?, ?, ?, ?, '(x)', '', '', 0)",
        [
            (HELPER, 3, 3, 173, 240, "TurnResult run_turn"),
            (LIBRARY, 1, 2, 2826, 2841, "std::vector<Message> lib::Engine::run_turn"),
        ],
    )
    if mark:
        mark_test_scope(conn, list(TEST_PATH_FACTS))
    conn.commit()
    return conn


##
# @brief The defaults must match the conventions a reader would expect, and nothing else.
# @return None.
# @version 1
def test_the_default_patterns_match_the_common_layouts() -> None:
    """Both families are asserted, because they mean different things and an implementation
    matching only one would look like it worked: `tests/*` is about LOCATION and `*_test.*` is
    about the FILE. C++ and Go routinely colocate `foo_test.cpp` beside the code, so a
    directory-only rule would miss every repo that does.

    The negative half matters as much: an ordinary source path must NOT match, or the term
    demotes everything equally and changes no ordering at all.

    @brief Defaults cover directory and filename conventions without over-matching.
    @return None.
    @version 1
    """
    for path in (
        "tests/model/engine_test.cpp",
        "test/unit/foo.c",
        "pytest/conftest.py",
        "ctest/harness.c",
        "src/nested/tests/thing.cpp",
        "src/engine_test.cpp",
        "src/test_engine.py",
        "src/EngineTests.java",
    ):
        assert is_test_path(path, TEST_PATH_FACTS), f"{path} should read as test code"

    for path in (
        "src/main.c",
        "include/lib/engine.h",
        "src/latest/thing.c",
        "src/contest.c",
        "src/protest/handler.c",
    ):
        assert not is_test_path(path, TEST_PATH_FACTS), (
            f"{path} is ordinary source and must not be demoted — over-matching would demote "
            f"everything equally and change no ordering at all"
        )


##
# @brief A declaration must DISPLACE the built-in guesses, not extend them.
# @return None.
# @version 1
def test_a_declaration_displaces_the_default_patterns() -> None:
    """THE TIER RULE, and the reason `TEST_PATH_FACTS` enters as heuristics rather than facts.
    If a declaration accumulated on top, declaring `t/*` would leave `tests/*` in force and an
    operator could only ever WIDEN the rule — never narrow it, and never correct a default that
    is wrong for their layout. Contrast `entry_patterns`, whose built-ins are facts that
    accumulate beneath a statement because reachability wants every plausible seed.

    @brief A declared pattern set replaces the defaults.
    @return None.
    @version 1
    """
    declared = ["t/*"]
    assert is_test_path("t/foo.c", declared)
    assert not is_test_path("tests/foo.c", declared), (
        "a declared pattern set must REPLACE the defaults; leaving `tests/*` in force means a "
        "repo can never narrow the rule, only widen it"
    )
    assert is_test_path("tests/foo.c", TEST_PATH_FACTS), "the default still applies by itself"


##
# @brief With the stage run, the library definition outranks the test helper.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_the_library_definition_outranks_a_test_helper(tmp_path: Path) -> None:
    """@brief A bare name resolves to the library definition.
    @return None.
    @version 1
    """
    conn = _fixture(tmp_path, mark=True)
    try:
        got = _common.resolve_rowid(conn, "run_turn")
        rows = _common.function_candidates(conn, "run_turn")
    finally:
        conn.close()

    assert got == LIBRARY, (
        f"resolved to rowid {got}: the test helper won. It is IN PLACE while the real method "
        f"is declared in a header and defined out of line, so the in-place term favours it — "
        f"the test-scope term has to sort ahead of that one"
    )
    assert rows[0][0] == LIBRARY, f"candidates ranked the test helper first: {rows}"
    ## STILL LISTED, never filtered. A test-code definition is a real definition: a repo whose
    ## only definition of a name lives in a test must still resolve to it.
    assert {r[0] for r in rows} == {LIBRARY, HELPER}, (
        f"a test-code definition was dropped rather than demoted: {rows}"
    )


##
# @brief An index built before the stage existed keeps its previous ordering.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_an_index_without_the_table_still_resolves(tmp_path: Path) -> None:
    """FORWARD COMPATIBILITY IS THE POINT. Every index built before this stage has no
    `test_scope` table, and the query layer must not raise on one — a missing table is missing
    knowledge, not a reason to refuse an answer. The old ordering is asserted explicitly
    (the helper wins) so this test says WHICH behaviour the fallback is, rather than merely
    that it does not crash.

    @brief A pre-stage index degrades to the old ranking without raising.
    @return None.
    @version 1
    """
    conn = _fixture(tmp_path, mark=False)
    try:
        assert not _common.table_exists(conn, "test_scope")
        got = _common.resolve_rowid(conn, "run_turn")
        rows = _common.function_candidates(conn, "run_turn")
    finally:
        conn.close()

    assert got == HELPER, (
        "without the table the resolver must fall back to the in-place ordering, which picks "
        "the helper here — if this changed, the fallback is not the old behaviour"
    )
    assert len(rows) == 2, "candidates must still list every meaning"


##
# @brief The stage writes an EMPTY table rather than none when nothing matches.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_a_repo_with_no_tests_gets_an_empty_table_not_a_missing_one(tmp_path: Path) -> None:
    """THE DISTINCTION THE FALLBACK DEPENDS ON. An ABSENT table means "this index predates the
    stage"; an EMPTY one means "the stage ran and this repo has no test code". Collapsing them
    would make an old index and a test-free repo indistinguishable, and the resolver would
    silently behave differently on each while both looked the same to a reader.

    @brief Running the stage always creates the table.
    @return None.
    @version 1
    """
    conn = sqlite3.connect(str(tmp_path / "notests.db"))
    conn.executescript("CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);")
    conn.execute("INSERT INTO path (rowid, type, name) VALUES (1, 1, 'src/main.c')")
    try:
        marked = mark_test_scope(conn, list(TEST_PATH_FACTS))
        assert marked == 0, "src/main.c is not test code"
        assert _common.table_exists(conn, "test_scope"), (
            "the stage ran and found nothing, but wrote no table — so this index is now "
            "indistinguishable from one built before the stage existed"
        )
        assert conn.execute("SELECT COUNT(*) FROM test_scope").fetchone()[0] == 0
    finally:
        conn.close()
