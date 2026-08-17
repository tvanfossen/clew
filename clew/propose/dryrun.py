# SPDX-License-Identifier: MIT
"""Measure a candidate declaration by RUNNING it — never by projecting it.

This is the accept/reject gate for both detectors and it is the one part of the
design that turns an argument into a fact. Copy the index, apply the candidate
section, call the pipeline's OWN import function, count the delta.

It exists because projection was measured wrong by every reviewer who tried it.
On a C/POSIX library's headline shared-key candidate the two independent projections
were 607 and 682 edges; the real number is 364. Both were confidently derived
from correct-looking per-family counts, and both were 67-87% high — because
`_MAX_KEY_PARTICIPANTS` suppression, the definition-preferring rowid index and
the writer x reader cross product interact in ways a count of call sites does
not capture. The dry run has no such gap: it IS the pipeline.

It also discriminates perfectly on the only two candidates anyone has measured
end to end. The `STORE_SET_`/`GET_` pair yields 364 edges with 3.6%
self-loops; the accessor families the build-time diagnostic reports for the same
repo yield exactly 0. No heuristic decides between those — the gate does.

The original database is only ever READ. Every run happens on a throwaway copy
in a temp directory, which is also what makes it safe to measure against a
target another process may be querying.

@brief Copy-the-index dry runs measuring a candidate section's real yield.
@version 1
"""

from __future__ import annotations

import contextlib
import shutil
import sqlite3
import tempfile
from collections.abc import Iterator
from pathlib import Path
from typing import Any


## @brief A throwaway copy of a database, deleted on exit.
## @param db_path Database to copy.
## @return Context manager yielding the copy's path.
## @version 3
## @req REQ-DDB-CONFIG-001
@contextlib.contextmanager
def db_copy(db_path: Path) -> Iterator[Path]:
    """`copy2` rather than a sqlite backup: the pipeline databases are not in
    WAL mode, so the file IS the database, and a plain copy cannot disturb a
    concurrent reader of the original.

    @brief Copy a database into a temp directory for the duration of a block.
    @version 3
    """
    with tempfile.TemporaryDirectory(prefix="clew-dryrun-") as tmp:
        copy = Path(tmp) / "clew.db"
        shutil.copy2(db_path, copy)
        yield copy


## @brief Why a database cannot be dry-run against, if it cannot.
## @param db_path Path to the candidate index.
## @return A one-line defect description, or "" when the index is usable.
## @version 2
## @req REQ-DDB-CONFIG-001
def index_defect(db_path: Path) -> str:
    """Checked BEFORE any measurement, because the pipeline importers a dry run
    calls are not defensive about their inputs: `_build_function_indexes` selects
    straight from `memberdef` and raises `OperationalError` on a database that
    does not have it. A zero-byte `clew.db` left in a repo is enough to reach that
    — and the discovery order can pick one up on its own, so the crash is not a
    hypothetical.

    An index with the table but NO rows is refused too. It would measure 0 for
    every candidate, and every candidate would then be rejected with the gate's
    own wording ("never a key across two functions") — a specific, false claim
    about the repo, where the truth is that nothing was indexed.

    @brief Validate that an index can be measured against.
    @version 2
    """
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:
        return f"cannot be opened ({exc})"
    try:
        count = _count(conn, "SELECT COUNT(*) FROM memberdef")
        has_table = bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memberdef'"
            ).fetchone()
        )
    except sqlite3.Error as exc:
        return f"is not a readable SQLite database ({exc})"
    finally:
        conn.close()
    return _defect_reason(has_table, count)


## @brief Turn a memberdef presence/row count into a defect reason.
## @param has_table Whether the `memberdef` table exists.
## @param count Rows in `memberdef` (0 when the table is absent).
## @return The defect reason, or "" when the index is usable.
## @version 2
## @dg_internal
def _defect_reason(has_table: bool, count: int) -> str:
    """@brief Describe what is wrong with an index, if anything."""
    if not has_table:
        return "has no `memberdef` table — it is not a clew index"
    if count == 0:
        return "has an empty `memberdef` — no functions were indexed"
    return ""


## @brief Count rows in a table, tolerating its absence.
## @param conn Open connection.
## @param sql Full COUNT statement to run.
## @return The count, or 0 when the table does not exist.
## @version 1
## @dg_internal
def _count(conn: sqlite3.Connection, sql: str) -> int:
    """@brief Run one COUNT, degrading to 0 on a table-less database."""
    try:
        return int(conn.execute(sql).fetchone()[0])
    except sqlite3.Error:
        return 0


## @brief Every (name, entry rowid) pair currently in the threads table.
## @param conn Open connection.
## @return Set of (thread name, entry memberdef rowid or None).
## @version 1
## @dg_internal
def _thread_keys(conn: sqlite3.Connection) -> set[tuple[str, int | None]]:
    """@brief Snapshot the threads table for a before/after diff."""
    try:
        return {
            (r[0], r[1]) for r in conn.execute("SELECT name, entry_memberdef_rowid FROM threads")
        }
    except sqlite3.Error:
        return set()


## @brief Run extract_threads with a candidate spawn list and measure the delta.
## @param db_path Database to measure against (copied, never written).
## @param repo_root Repo root the index's paths are relative to.
## @param spawns Candidate `thread_patterns.spawns` entries.
## @param param_names Parameter identifiers of the candidate wrappers.
## @return Measured counters (threads/membership before and after, fabrication metrics).
## @version 4
## @req REQ-DDB-CONFIG-001
def measure_threads(
    db_path: Path,
    repo_root: Path,
    spawns: list[dict],
    param_names: frozenset[str] = frozenset(),
) -> dict[str, int]:
    """`param_named` is the fabrication metric that matters. A wrapper whose own
    call sites forward a parameter rather than naming a function produces a
    thread named after that parameter, with a NULL entry and therefore no
    closure — measured at 1 such row for a C/POSIX library's out-of-scope
    `SYSTEM_TASKCREATE` and 0 for the wrapper that is proposed.

    @brief Measure a candidate spawn declaration's real yield.
    @version 3
    """
    from ..threads import extract_threads

    with db_copy(db_path) as copy:
        conn = sqlite3.connect(str(copy))
        before = _thread_keys(conn)
        measured = {
            "threads_before": len(before),
            "membership_before": _count(conn, "SELECT COUNT(*) FROM thread_membership"),
        }
        conn.close()
        extract_threads(copy, repo_root, {"spawns": spawns}, None)
        conn = sqlite3.connect(str(copy))
        measured.update(_thread_metrics(conn, before, param_names))
        conn.close()
    return measured


## @brief Post-run thread counters, including the fabrication metrics.
## @param conn Open connection to the measured copy.
## @param before Thread keys present before the run.
## @param param_names Parameter identifiers of the candidate wrappers.
## @return Counter mapping.
## @version 1
## @dg_internal
def _thread_metrics(
    conn: sqlite3.Connection, before: set[tuple[str, int | None]], param_names: frozenset[str]
) -> dict[str, int]:
    """@brief Compute the after-state thread metrics for a dry run."""
    after = _thread_keys(conn)
    new = after - before
    return {
        "threads_after": len(after),
        "threads_new": len(new),
        "membership_after": _count(conn, "SELECT COUNT(*) FROM thread_membership"),
        "distinct_fns_after": _count(
            conn, "SELECT COUNT(DISTINCT memberdef_rowid) FROM thread_membership"
        ),
        "multi_thread_fns_after": _count(
            conn,
            "SELECT COUNT(*) FROM (SELECT memberdef_rowid FROM thread_membership "
            "GROUP BY memberdef_rowid HAVING COUNT(DISTINCT thread_id) > 1)",
        ),
        "unresolved_entry_new": sum(1 for _name, entry in new if entry is None),
        "param_named_new": sum(1 for name, _entry in new if name in param_names),
    }


## @brief Run the inferred shared-key pass with a section and read the result.
## @param db_path Database to measure against (copied, never written).
## @param repo_root Repo root the index's paths are relative to.
## @param section A `shared_key_patterns` section mapping, or None for defaults only.
## @return Edge count, self-loop count, and per-key counts after the run.
## @version 2
## @req REQ-DDB-CONFIG-001
def measure_shared_key(db_path: Path, repo_root: Path, section: dict | None) -> dict[str, Any]:
    """Callers diff two of these — one with the candidate, one with `None` — so
    the yield attributed to a candidate excludes whatever the built-in ingot
    defaults would have produced on their own.

    @brief Measure the inferred shared-key layer under one candidate section.
    @version 2
    """
    from ..shared_key_edges import (
        import_shared_key_edges_inferred,
    )

    with db_copy(db_path) as copy:
        import_shared_key_edges_inferred(copy, repo_root, section, None)
        conn = sqlite3.connect(str(copy))
        measured: dict[str, Any] = {
            "edges": _count(conn, "SELECT COUNT(*) FROM shared_key_edges"),
            "self_loops": _count(
                conn, "SELECT COUNT(*) FROM shared_key_edges WHERE writer_rowid = reader_rowid"
            ),
            "by_key": _key_counts(conn),
        }
        conn.close()
    return measured


## @brief Per-key edge counts in the shared_key_edges table.
## @param conn Open connection.
## @return Mapping of key name to edge count.
## @version 1
## @dg_internal
def _key_counts(conn: sqlite3.Connection) -> dict[str, int]:
    """@brief Read the per-key shared-key edge distribution."""
    try:
        rows = conn.execute(
            "SELECT key_name, COUNT(*) FROM shared_key_edges GROUP BY key_name"
        ).fetchall()
    except sqlite3.Error:
        return {}
    return {str(key): int(count) for key, count in rows}
