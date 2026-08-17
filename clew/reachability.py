# SPDX-License-Identifier: MIT
"""Symbol-liveness BFS over call_edges from entry-point seeds.

Functions reachable from a seed are tagged 'live'; the rest become
'orphan'. The researcher tier surfaces the tag so downstream
consumers can deprioritize orphans without dropping them entirely.

Two seed sources, unioned:
  - Pattern seeds: function names matching SQL LIKE patterns
    (main, *_init, *_task, *_isr, *_handler, ...).
  - Zero-incoming seeds: functions with no non-fuzzy callers — likely
    library APIs or callbacks dispatched through function pointers,
    which doxygen + AST can't track. Conservative: a few dead
    functions might be marked live, but no live functions get marked
    dead.

@brief Reachability BFS for symbol_liveness.
@version 3
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ._common import logger
from .vocabulary import check

# LIKE is case-insensitive for ASCII in SQLite; substring forms (%X%)
# catch CamelCase too (Initialize, TaskHandler, ISR_Entry, ...).
#
# THE SET IS SPLIT BY TIER (gh#319), because it was MIXED and that made it the one
# constant where a stated tier could silently destroy a fact. `--entry-patterns`
# REPLACED the whole list, so naming one repo-specific pattern dropped `main` too,
# reachability collapsed, and nothing reported it. Under `tiers.resolve_layered`
# the facts accumulate and only the guesses are displaceable.

## TIER 3 — LANGUAGE AND PLATFORM ENTRY POINTS. Not guesses and not conventions:
## the C standard names `main` as the program entry point, and ESP-IDF names
## `app_main` as the application entry point its bootloader calls. Both are facts
## someone else wrote down, so no declaration and no flag removes them.
##
## The accepted cost, weighed and settled: a repo where `main` is a test fixture
## cannot say "do not seed it". Deliberately no escape hatch — a false live symbol
## is the same class of error the zero-incoming seed already accepts, and an
## un-discoverable fact is worse.
ENTRY_PATTERN_FACTS: tuple[str, ...] = ("main", "app_main")

## TIER 5 — NAME-SHAPE GUESSES, and provisional by construction. Every one of these
## asserts that a function whose NAME contains a word is an entry point, which is
## true often enough to be useful and false often enough that a target must be able
## to state its own vocabulary instead. `%handler%` in particular matches any
## error-handling helper in any codebase.
ENTRY_PATTERN_HEURISTICS: tuple[str, ...] = (
    "%init%",
    "%task%",
    "%handler%",
    "%thread%",
    "%isr%",
    "%entry%",
    "%_cb",
    "%callback%",
)

## The whole built-in set, in the order it has always had. Kept as the ONE name for
## "what a target that states nothing gets", so the CLI help text, the proposer's
## mirror in `propose/notindexed.py` and the resolver's success path cannot drift
## into three different answers. `resolve_layered` places the accumulating layers
## first precisely so its no-statement result equals this list exactly.
DEFAULT_ENTRY_PATTERNS: list[str] = [*ENTRY_PATTERN_FACTS, *ENTRY_PATTERN_HEURISTICS]


## @brief Return (pattern_seeds, zero_incoming_seeds).
## @version 2
## @req REQ-DDB-PIPE-004
def _gather_reachability_seeds(
    conn: sqlite3.Connection,
    entry_patterns: list[str],
) -> tuple[set[int], set[int]]:
    """Return (pattern_seeds, zero_incoming_seeds)."""
    seed_clauses = " OR ".join(["name LIKE ?"] * len(entry_patterns))
    pattern_seeds = {
        r[0]
        for r in conn.execute(
            f"SELECT rowid FROM memberdef WHERE kind = 'function' AND ({seed_clauses})",
            entry_patterns,
        ).fetchall()
    }
    zero_incoming_seeds = {
        r[0]
        for r in conn.execute(
            """
            SELECT m.rowid FROM memberdef m
            WHERE m.kind = 'function'
              AND NOT EXISTS (
                SELECT 1 FROM call_edges ce
                WHERE ce.callee_rowid = m.rowid AND ce.confidence != 'fuzzy'
              )
            """,
        ).fetchall()
    }
    return pattern_seeds, zero_incoming_seeds


## @brief BFS over call_edges (non-fuzzy) from seeds.
## @version 2
## @req REQ-DDB-PIPE-004
## @return Set of memberdef rowids reachable from the seeds via non-fuzzy call_edges.
def _bfs_live_set(conn: sqlite3.Connection, seeds: set[int]) -> set[int]:
    """BFS over call_edges (non-fuzzy) from seeds. Return set of live rowids."""
    live: set[int] = set()
    frontier = list(seeds)
    while frontier:
        batch = frontier
        frontier = []
        for src in batch:
            live.add(src)
        placeholders = ",".join(["?"] * len(batch))
        callees = conn.execute(
            f"""
            SELECT DISTINCT callee_rowid FROM call_edges
            WHERE caller_rowid IN ({placeholders}) AND confidence != 'fuzzy'
            """,
            list(batch),
        ).fetchall()
        for (dst,) in callees:
            if dst not in live:
                frontier.append(dst)
    return live


## @brief Populate symbol_liveness from `live`.
## @version 2
## @req REQ-DDB-PIPE-004
def _write_symbol_liveness(
    conn: sqlite3.Connection,
    live: set[int],
) -> tuple[int, int]:
    """Populate symbol_liveness from `live`. Return (live_count, total)."""
    candidates = conn.execute(
        "SELECT rowid FROM memberdef WHERE kind = 'function'",
    ).fetchall()
    rows = [(rid, "live" if rid in live else "orphan") for (rid,) in candidates]
    conn.executemany(
        "INSERT INTO symbol_liveness (memberdef_rowid, status) VALUES (?, ?)",
        rows,
    )
    live_count = sum(1 for _, status in rows if status == "live")
    return live_count, len(rows)


## @brief Compute symbol liveness via BFS over call_edges from entry seeds.
## @param db_path Path to the clew.db being built.
## @param entry_patterns Name LIKE patterns seeding the BFS.
## @param extra_seeds Rowids seeded from a source no name pattern can express.
## @version 6
## @req REQ-DDB-PIPE-004
def mark_reachability(
    db_path: Path,
    entry_patterns: list[str] | None = None,
    extra_seeds: set[int] | None = None,
) -> None:
    """Compute symbol liveness via BFS over call_edges from entry seeds.

    Skips fuzzy-confidence edges (they add false-positive liveness).
    Bails out early when call_edges has no non-fuzzy rows.

    A THIRD seed source joins the two the module docstring describes:
    `extra_seeds`, rowids identified structurally rather than by name. It exists
    because neither existing source can see a Python `if __name__ ==
    "__main__":` entry. Measured on the Python real codebase: doxygen attributes the
    guard's `_main()` call to `_main` ITSELF, so the function has a non-fuzzy
    incoming edge (excluding it from the zero-incoming source), its only caller
    is itself, and nothing reaches it — a real entry point reported dead. The
    parameter defaults to None, so a C/C++ build's seed set is unchanged.

    @brief Walk call_edges BFS and tag symbols live/orphan.
    @version 6
    """
    if entry_patterns is None:
        entry_patterns = DEFAULT_ENTRY_PATTERNS

    conn = sqlite3.connect(str(db_path))
    edge_count = conn.execute(
        "SELECT COUNT(*) FROM call_edges WHERE confidence != 'fuzzy'",
    ).fetchone()[0]
    if edge_count == 0:
        logger.warning(
            "call_edges has no non-fuzzy rows — skipping reachability pass",
        )
        conn.close()
        return

    conn.execute("DROP TABLE IF EXISTS symbol_liveness")
    conn.execute(
        f"""
        CREATE TABLE symbol_liveness (
            memberdef_rowid INTEGER PRIMARY KEY,
            status TEXT {check("symbol_liveness", "status")} NOT NULL
        )
        """,
    )

    pattern_seeds, zero_incoming_seeds = _gather_reachability_seeds(
        conn,
        entry_patterns,
    )
    structural_seeds = extra_seeds or set()
    seeds = pattern_seeds | zero_incoming_seeds | structural_seeds
    logger.info(
        "Reachability seeds: pattern=%d zero_incoming=%d structural=%d union=%d",
        len(pattern_seeds),
        len(zero_incoming_seeds),
        len(structural_seeds),
        len(seeds),
    )

    live = _bfs_live_set(conn, seeds)
    live_count, total = _write_symbol_liveness(conn, live)
    conn.commit()
    conn.close()

    orphan_count = total - live_count
    logger.info(
        "Reachability: live=%d orphan=%d total=%d (seeds=%d, edges=%d)",
        live_count,
        orphan_count,
        total,
        len(seeds),
        edge_count,
    )
    if total > 0 and orphan_count / total > 0.8:
        logger.warning(
            "More than 80%% of functions/variables are orphan (%d/%d). "
            "Entry-point seeds may be wrong for this repo — consider "
            "passing --entry-patterns with repo-specific patterns.",
            orphan_count,
            total,
        )
