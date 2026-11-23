# SPDX-License-Identifier: MIT
"""The incremental-refresh invariance check compares EVERY table, not the nine doxygen ones.

1.3.3, Track 2 (LSP-speed refresh). `scripts/incremental_probe.py compare` is the release check
that an incremental refresh reproduces a full rebuild. It counted nine doxygen-side tables, so a
derived layer (threads, locks, code text, requirement mentions, reachability) could drop or
duplicate rows on the incremental path and the check would still say AGREEMENT. The in-place
delta build planned next rewrites exactly those layers, so the check has to see them first.

ROWIDS ARE NOT STABLE BETWEEN TWO BUILDS, so a table whose columns reference rowids is compared
by row count; a table with no rowid column is compared by CONTENT (a sorted-row digest), which
catches a changed value at an unchanged count.

@brief Tests for incremental_probe.whole_db_diff.
@version 1
"""

from __future__ import annotations

import importlib.util
import sqlite3
from pathlib import Path
from types import ModuleType


## @brief Import the probe from scripts/ rather than restating its rule here.
## @return The module.
## @version 1
def _probe() -> ModuleType:
    """@brief Load scripts/incremental_probe.py. @return Module."""
    path = Path(__file__).resolve().parent.parent / "scripts" / "incremental_probe.py"
    spec = importlib.util.spec_from_file_location("incremental_probe", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


## @brief Write a small index-shaped database.
## @param path Where.
## @param threads Rows for a derived table no doxygen-side count covers.
## @param mention Text of the one mention row.
## @return The path.
## @version 1
def _db(path: Path, threads: int, mention: str) -> Path:
    """@brief Build a fixture DB. @return Path."""
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE threads (name TEXT, entry_rowid INTEGER)")
    conn.execute("CREATE TABLE req_mentions (req_id TEXT, file TEXT, line INT, text TEXT)")
    conn.execute("CREATE TABLE build_meta (key TEXT, value TEXT)")
    conn.executemany("INSERT INTO memberdef (name) VALUES (?)", [("a",), ("b",)])
    conn.executemany("INSERT INTO threads VALUES (?, ?)", [(f"t{i}", i) for i in range(threads)])
    conn.execute("INSERT INTO req_mentions VALUES ('REQ-1', 'a.md', 3, ?)", (mention,))
    conn.execute("INSERT INTO build_meta VALUES ('refresh.duration_ms', ?)", (str(threads),))
    conn.commit()
    conn.close()
    return path


def test_identical_indexes_agree(tmp_path: Path) -> None:
    """@brief Two identical databases produce no divergence.
    @return None.
    @version 1
    """
    a, b = _db(tmp_path / "a.db", 2, "x"), _db(tmp_path / "b.db", 2, "x")
    assert _probe().whole_db_diff(a, b) == []


def test_a_derived_table_losing_rows_is_caught(tmp_path: Path) -> None:
    """THE GAP THIS CLOSES: `threads` is in none of the nine doxygen-side counts.

    @brief A row-count change in a derived table diverges.
    @return None.
    @version 1
    """
    a, b = _db(tmp_path / "a.db", 2, "x"), _db(tmp_path / "b.db", 1, "x")
    assert any("threads" in d for d in _probe().whole_db_diff(a, b))


def test_a_changed_value_at_the_same_count_is_caught(tmp_path: Path) -> None:
    """@brief A rowid-free table is compared by content, not only by count.
    @return None.
    @version 1
    """
    a, b = _db(tmp_path / "a.db", 2, "x"), _db(tmp_path / "b.db", 2, "y")
    assert any("req_mentions" in d for d in _probe().whole_db_diff(a, b))


def test_build_metadata_is_not_compared(tmp_path: Path) -> None:
    """TIMINGS DIFFER BETWEEN ANY TWO BUILDS; comparing them would make the check always fail,
    which is a check nobody runs. `build_meta` is excluded by name.

    @brief build_meta differences are ignored.
    @return None.
    @version 1
    """
    a, b = _db(tmp_path / "a.db", 2, "x"), _db(tmp_path / "b.db", 2, "x")
    conn = sqlite3.connect(b)
    conn.execute("UPDATE build_meta SET value = '999'")
    conn.commit()
    conn.close()
    assert _probe().whole_db_diff(a, b) == []
