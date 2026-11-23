# SPDX-License-Identifier: MIT
"""A covering test is a function in TEST CODE, as the index's test scope defines it (round 4, R9).

OWNER 2026-11-16, on the clew demo's 94 "absent" tests. Two of them were not tests at all:
`mark_test_scope` (clew/testscope.py) and `test_id` (clew/wiki/imports.py), both production
functions tagged `@req`. `_looks_like_test_function` accepted the first because its PATH contains
the substring "test", the second because its NAME starts with `test_`. They landed in
`req_test_edges`, so the wiki graded them as tests with no result and every dossier listed
`mark_test_scope` as its own `covering_tests`.

The index already knows which files are test code — `test_scope`, from the resolved test-path
patterns. Given those patterns, a test is a function in a file they match; nothing else.

@brief Tests for scope-based covering-test classification.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.requirements import import_req_edges, import_req_test_edges
from clew.testscope import TEST_PATH_FACTS


def _db(tmp_path: Path) -> Path:
    db = tmp_path / "doxy.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE path (name TEXT);
            CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,
                file_id INTEGER, briefdescription TEXT, detaileddescription TEXT);
            INSERT INTO path (rowid, name) VALUES
                (1, 'clew/testscope.py'), (2, 'clew/wiki/imports.py'),
                (3, 'tests/test_scope.py'), (4, 'pkg/foo_test.go');
            INSERT INTO memberdef VALUES
                (1, 'function', 'mark_test_scope', 1, '', '@req REQ-1'),
                (2, 'function', 'test_id', 2, '', '@req REQ-1'),
                (3, 'function', 'test_marks_scope', 3, '', '@req REQ-1'),
                (4, 'function', 'checks_foo', 4, '', '@req REQ-1');
            """
        )
    return db


def _linked(db: Path) -> list[str]:
    with sqlite3.connect(db) as conn:
        return [
            n
            for (n,) in conn.execute(
                "SELECT m.name FROM req_test_edges t JOIN memberdef m "
                "ON m.rowid = t.test_memberdef_rowid ORDER BY m.name"
            )
        ]


def test_with_test_patterns_only_functions_in_test_code_are_tests(tmp_path: Path) -> None:
    """@brief A `test`-substring path or a `test_` name outside test code is not a test."""
    db = _db(tmp_path)
    import_req_edges(db)
    import_req_test_edges(db, test_patterns=TEST_PATH_FACTS)
    assert _linked(db) == ["checks_foo", "test_marks_scope"]


def test_without_patterns_the_legacy_heuristic_still_applies(tmp_path: Path) -> None:
    """@brief Callers that pass no patterns keep the old behaviour (its own tests pin it)."""
    db = _db(tmp_path)
    import_req_edges(db)
    import_req_test_edges(db)
    assert "test_marks_scope" in _linked(db)
