# SPDX-License-Identifier: MIT
"""Catch2 test cases are covering tests, linked by their tags (2.1, clew#74 item 1).

FOUND by entropic (clew 2.0.1): `dossier(REQ-LOOP-007)` returned `tests: []` for every
requirement. `req_test_edges` was filled only from test FUNCTIONS carrying `@req`, and Catch2's
`TEST_CASE("...", "[core][REQ-LOOP-007]")` gives no function to read a tag from: doxygen records
each one as a function NAMED `TEST_CASE`, 982 of them in entropic's tree.

A `TEST_CASE`, `SCENARIO`, `TEMPLATE_TEST_CASE` or `TEST_CASE_METHOD` in test code is linked to a
requirement when one of its Catch2 tags IS a catalog id, or when `@req` sits in the comment block
directly above it. The test's name is its title string, which is what ctest and Catch2's own
filter select on. A tag that names no catalog id links nothing.

@brief Tests Catch2 test-case coverage edges.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.catch2 import read_case

TESTS = """#include <catch2/catch_test_macros.hpp>
TEST_CASE("adds two numbers", "[core][REQ-A-001]") { REQUIRE(1 + 1 == 2); }

/// Covers the scenario path.
/// @req REQ-A-002
SCENARIO("a scenario linked by its comment",
         "[core]") {
}

TEST_CASE("names no catalog id", "[REQ-NOPE-9]") { }
"""


def test_a_case_reads_its_title_tags_and_comment_tags() -> None:
    """@brief Title, tags, and `@req` lines in the comment block directly above."""
    lines = TESTS.splitlines()
    first = read_case(lines, 2)
    assert first is not None
    assert (first.title, first.tags, first.reqs) == ("adds two numbers", ("core", "REQ-A-001"), ())
    second = read_case(lines, 6)
    assert second is not None
    assert second.title == "a scenario linked by its comment", (
        "a title on one line, tags on the next"
    )
    assert second.reqs == ("REQ-A-002",)


def _build(tmp_path: Path) -> Path:
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / ".clew.yaml").write_text("requirements:\n  file: reqs.yaml\n")
    (repo / "reqs.yaml").write_text(
        "requirements:\n  REQ-A-001:\n    title: adds\n  REQ-A-002:\n    title: scenario\n"
    )
    (repo / "src" / "add.cpp").write_text(
        "/// @brief Add.\n/// @req REQ-A-001\n/// @req REQ-A-002\nint add(int a, int b) { return a + b; }\n"
    )
    (repo / "tests" / "add_test.cpp").write_text(TESTS)
    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db


def test_the_index_links_catch2_cases_to_their_requirements(tmp_path: Path) -> None:
    """@brief `req_test_edges` holds each case by its title; an unknown tag links nothing."""
    db = _build(tmp_path)
    rows = (
        sqlite3.connect(db)
        .execute("SELECT req_id, test_name FROM req_test_edges ORDER BY req_id")
        .fetchall()
    )
    assert rows == [
        ("REQ-A-001", "adds two numbers"),
        ("REQ-A-002", "a scenario linked by its comment"),
    ]


def test_a_requirement_dossier_names_its_catch2_tests(tmp_path: Path) -> None:
    """@brief `dossier(REQ-A-001)` lists the case by title, never as `TEST_CASE`."""
    from clew.query.export import export_dossier

    db = _build(tmp_path)
    req = export_dossier(db, "REQ-A-001", repo_root=tmp_path / "repo")
    assert req["tests"] == ["adds two numbers"]
    add = export_dossier(db, "add", repo_root=tmp_path / "repo")
    assert add["covering_tests"] == ["a scenario linked by its comment", "adds two numbers"]


def test_a_case_is_never_listed_as_an_implementer(tmp_path: Path) -> None:
    """A case's comment `@req` reaches `req_edges` through doxygen, on a row named `SCENARIO`;
    with tests now served by title, the implementers must still leave that row out.

    @brief Implementers exclude Catch2 cases.
    """
    from clew.query.export import export_dossier

    db = _build(tmp_path)
    req = export_dossier(db, "REQ-A-002", repo_root=tmp_path / "repo")
    assert [i["name"] for i in req["implementers"]] == ["add"]
    assert req["tests"] == ["a scenario linked by its comment"]
