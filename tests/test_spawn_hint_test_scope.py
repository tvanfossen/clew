# SPDX-License-Identifier: MIT
"""The undeclared-spawn hint skips names defined only in test files (R5-CORE D3; 2.0.0).

FOUND BY THE 2.0.0 CORE AUDIT (agent C, vetted: threads.py:2001): the hint excluded test code by
the `test_` NAME PREFIX alone — a Python and C convention — so a gtest body, a mocha
`it_creates_thread` or a `spawn_thread_new` helper in `tests/` was offered as a spawn primitive.
The index already knows which files are tests (`test_scope`, from the declared `tests.paths`).

@brief Tests the spawn hint's test-file exclusion.
@version 1
"""

from __future__ import annotations

import sqlite3

from clew.threads import detect_undeclared_spawn_primitives


def _conn(with_scope: bool = True) -> sqlite3.Connection:
    """@brief Two spawn-shaped names, one defined only under tests/. @return conn."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, file_id INTEGER);
        INSERT INTO path VALUES (1, 'src/os.c'), (2, 'tests/fake_os.cpp');
        INSERT INTO memberdef VALUES (10, 'sys_thread_create', 'function', 1);
        INSERT INTO memberdef VALUES (11, 'fake_thread_create', 'function', 2);
        """
    )
    if with_scope:
        conn.executescript(
            "CREATE TABLE test_scope (path_rowid INTEGER PRIMARY KEY); INSERT INTO test_scope VALUES (2);"
        )
    return conn


def test_a_name_defined_only_in_a_test_file_is_not_offered() -> None:
    """@brief `fake_thread_create` lives in a test file; `sys_thread_create` does not."""
    assert detect_undeclared_spawn_primitives(_conn(), []) == ["sys_thread_create"]


def test_without_a_test_scope_table_both_are_offered() -> None:
    """@brief No table means no test files are known: nothing is dropped on that account."""
    assert detect_undeclared_spawn_primitives(_conn(with_scope=False), []) == [
        "fake_thread_create",
        "sys_thread_create",
    ]
