# SPDX-License-Identifier: MIT
"""Declared failure modes: in the catalog per requirement, named by tests with `@fails_when` (2.2).

OWNER Q/A 2026-11-25 (the test-flowchart design pass). A requirement declares the ways it can
fail, each with an id and a one-line meaning:

    REQ-A-001:
      title: adds
      failure_modes:
        FM-A-001-1: overflow wraps silently

A test names the modes it guards with `@fails_when FM-A-001-1` in its docstring (or, for a
Catch2 case, the comment block directly above it). The ids are defined ONCE, in the catalog:
guard refuses an id the catalog does not declare, as it refuses an unknown `@req`, and the index
links each test to the modes it names, which the requirement's dossier serves. The flowchart
(F2) ends each failing assertion at one of these modes.

@brief Tests declared failure modes.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.failuremodes import fails_when_ids, modes_of

CATALOG = """requirements:
  REQ-A-001:
    title: adds
    failure_modes:
      FM-A-001-1: overflow wraps silently
      FM-A-001-2: negative input accepted
  REQ-A-002:
    title: no modes declared
"""

PY_TEST = '''"""@brief Tests."""


## @brief Overflow is refused.
## @req REQ-A-001
## @fails_when FM-A-001-1
def test_add_overflow():
    """@brief Overflow is refused."""


## @brief Names an id no requirement declares.
## @fails_when FM-NOPE-9
def test_unknown_mode():
    """@brief Unknown."""
'''

CPP_TEST = """#include <catch2/catch_test_macros.hpp>
/// @fails_when FM-A-001-2
TEST_CASE("negative input is refused", "[REQ-A-001]") { }
"""


def test_a_catalog_entry_declares_its_modes() -> None:
    """@brief `failure_modes` is a mapping of id to meaning; anything else is refused by name."""
    assert [
        (m.req_id, m.mode_id, m.meaning)
        for m in modes_of("REQ-A-001", {"failure_modes": {"FM-A-001-1": "overflow wraps silently"}})
    ] == [("REQ-A-001", "FM-A-001-1", "overflow wraps silently")]
    assert modes_of("REQ-A-002", {"title": "x"}) == []
    import pytest

    with pytest.raises(ValueError, match="REQ-A-003.*failure_modes"):
        modes_of("REQ-A-003", {"failure_modes": ["FM-1"]})


def test_fails_when_ids_are_read_from_doc_text() -> None:
    """@brief `@fails_when ID` and `\\fails_when ID`, ended by whitespace or markup."""
    assert fails_when_ids("x @fails_when FM-A-001-1\n@fails_when FM-2<br>") == [
        "FM-A-001-1",
        "FM-2",
    ]
    assert fails_when_ids(None) == []


def _build(tmp_path: Path) -> Path:
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / ".clew.yaml").write_text("requirements:\n  file: reqs.yaml\n")
    (repo / "reqs.yaml").write_text(CATALOG)
    (repo / "src" / "add.py").write_text(
        '"""@brief Add."""\n\n\n## @brief Add.\n## @req REQ-A-001\ndef add(a, b):\n'
        '    """@brief Add."""\n    return a + b\n'
    )
    (repo / "tests" / "test_add.py").write_text(PY_TEST)
    (repo / "tests" / "add_test.cpp").write_text(CPP_TEST)
    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db


def test_the_index_holds_modes_and_the_tests_that_name_them(tmp_path: Path) -> None:
    """@brief `failure_modes` from the catalog; `test_failure_modes` from docstrings and Catch2."""
    db = _build(tmp_path)
    conn = sqlite3.connect(db)
    assert conn.execute(
        "SELECT req_id, mode_id, meaning FROM failure_modes ORDER BY mode_id"
    ).fetchall() == [
        ("REQ-A-001", "FM-A-001-1", "overflow wraps silently"),
        ("REQ-A-001", "FM-A-001-2", "negative input accepted"),
    ]
    assert conn.execute(
        "SELECT mode_id, test_name FROM test_failure_modes ORDER BY mode_id"
    ).fetchall() == [
        ("FM-A-001-1", "test_add_overflow"),
        ("FM-A-001-2", "negative input is refused"),
    ], "FM-NOPE-9 names no catalog mode, so nothing links"


def test_a_requirement_dossier_serves_its_modes_with_their_tests(tmp_path: Path) -> None:
    """@brief Each declared mode, its meaning, and the tests that guard it; absent when none."""
    from clew.query.export import export_dossier

    db = _build(tmp_path)
    repo = tmp_path / "repo"
    req = export_dossier(db, "REQ-A-001", repo_root=repo)
    assert req["failure_modes"] == [
        {"id": "FM-A-001-1", "meaning": "overflow wraps silently", "tests": ["test_add_overflow"]},
        {
            "id": "FM-A-001-2",
            "meaning": "negative input accepted",
            "tests": ["negative input is refused"],
        },
    ]
    assert "failure_modes" not in export_dossier(db, "REQ-A-002", repo_root=repo)


def test_guard_knows_the_tag_and_refuses_an_undeclared_id(tmp_path: Path) -> None:
    """@brief `@fails_when` is no unknown tag; an id the catalog does not declare is a violation."""
    from clew.guard.checks import check_fails_when_exists, check_unknown_tags
    from clew.guard.config import load_config, parse_source_file

    path = tmp_path / "test_add.py"
    path.write_text(PY_TEST)
    config = load_config(tmp_path / "no-such.yaml")
    funcs = {f.name: f for f in parse_source_file(str(path), config)}
    assert not [
        v
        for f in funcs.values()
        for v in check_unknown_tags(f, str(path), config)
        if "fails_when" in v.message
    ]
    modes = {"FM-A-001-1", "FM-A-001-2"}
    assert check_fails_when_exists(funcs["test_add_overflow"], str(path), config, modes) == []
    (bad,) = check_fails_when_exists(funcs["test_unknown_mode"], str(path), config, modes)
    assert "FM-NOPE-9" in bad.message and "failure_modes" in bad.message
