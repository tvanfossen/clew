# SPDX-License-Identifier: MIT
"""What an interrupt handler reaches that it is not allowed to reach.

gh#47 part 2. Two layers already hold the facts and neither could be asked the question:
`threads` says which functions run in interrupt context (part 1), `lock_acquisitions` says who
takes a lock that can park the caller, and `blocking_calls` says who calls a primitive that
waits. This stage joins them once, at build time, so the number a build prints and the list a
dossier serves come from the SAME rows rather than from two derivations free to disagree.

THREE OUTCOMES, AND THE THIRD IS THE POINT. A site is a conflict, or it is clean, or this index
cannot tell — and the third is recorded rather than silently folded into either neighbour:

  * an operand this layer will not evaluate (`k_sem_take(&s, cfg->wait)`) — promoting it
    fabricates a conflict, dropping it makes an empty list a lie;
  * a call guarded by a runtime context predicate (`if (k_is_in_isr())`, RIOT's `irq_is_in()`,
    the `k_is_in_isr() ? K_NO_WAIT : K_FOREVER` idiom at Zephyr subsys/pm/device_runtime.c:71) —
    the branch's polarity is not evaluated here, because choosing would be a guess;
  * an acquisition whose lock identity never resolved, so its kind cannot be read.

THE CLOSURE IS NOT THREAD MEMBERSHIP. It re-walks `call_edges` for one reason: membership
traverses `source='binding'`, whose own vocabulary entry says the reference is called "at a time
and on a thread this edge says nothing about". A work handler bound inside an interrupt and run
later on a workqueue thread is entitled to block — that is the CORRECT pattern Zephyr documents
(720 `k_work_init` sites at v4.4.2) — and reporting it as an interrupt-context violation would
discredit every other row. Membership rows are left exactly as they are; the refusals are
counted and logged.

@brief Interrupt-context conflicts, derived from threads x locks x blocking calls.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ._common import logger
from .vocabulary import BLOCKING_LOCK_KINDS, check

## A row either states a violation or states that the index could not decide. Nothing here is
## ever written to mean "clean": clean is the ABSENCE of a row against a thread that exists.
VERDICT_CONFLICT = "conflict"
VERDICT_UNDECIDABLE = "undecidable"

## Why the row exists. Two conflict reasons, three undecidable ones.
REASON_BLOCKING_LOCK = "blocking_lock"
REASON_BLOCKING_CALL = "blocking_call"
REASON_UNDECIDABLE_TIMEOUT = "undecidable_timeout"
REASON_GUARDED = "guarded_by_isr_predicate"
REASON_UNRESOLVED_LOCK = "unresolved_lock_identity"

## Edge sources that carry a real call. `binding` is excluded by name (see the module docstring)
## and `fuzzy` confidence is excluded with it, as everywhere else in the pipeline.
_EXCLUDED_EDGE_SOURCE = "binding"

## Edge sources that make a path an INFERENCE about indirection rather than a call the source
## states. A path through one of these is reported at lower confidence, not withheld.
_INDIRECT_SOURCES = frozenset({"fnptr", "declared_dispatch"})

## Waits that still block when the call is reached. `none` is legal in an interrupt by
## construction and produces no row at all; `undecidable` produces an undecidable row.
_BLOCKING_WAITS = ("unconditional", "forever", "bounded")


## @brief Create the context_conflicts table.
## @param conn Open connection.
## @return None.
## @version 1
## @req REQ-DDB-SCHEMA-011
def ensure_context_table(conn: sqlite3.Connection) -> None:
    """Created unconditionally, like every other layer's tables, so "this repository has no
    interrupt handler" and "this index predates the layer" stay distinguishable: the first is
    an empty table, the second is no table.

    @brief Create context_conflicts if it does not exist.
    @return None.
    @version 1
    """
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS context_conflicts (
          id INTEGER PRIMARY KEY,
          thread_id INTEGER NOT NULL REFERENCES threads(id),
          member_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
          verdict TEXT NOT NULL {check("context_conflicts", "verdict")},
          reason TEXT NOT NULL {check("context_conflicts", "reason")},
          evidence TEXT NOT NULL,
          detail TEXT NOT NULL,
          path_rowid INTEGER REFERENCES path(rowid),
          line INTEGER,
          depth INTEGER NOT NULL,
          confidence TEXT NOT NULL {check("context_conflicts", "confidence")},
          UNIQUE(thread_id, member_rowid, reason, evidence, line)
        );
        CREATE INDEX IF NOT EXISTS idx_context_member ON context_conflicts(member_rowid);
        CREATE INDEX IF NOT EXISTS idx_context_thread ON context_conflicts(thread_id);
        """
    )


## @brief Walk the call graph from one entry, excluding deferral edges.
## @param conn Open connection.
## @param entry_rowid The handler's memberdef rowid.
## @return {rowid: (depth, weakest source on the path)} including the entry itself.
## @version 1
## @dg_internal
def _isr_closure(conn: sqlite3.Connection, entry_rowid: int) -> dict[int, tuple[int, str]]:
    """Breadth-first so `depth` is the SHORTEST hop count from the handler, which is what a
    reader following the path back has to walk. The weakest source seen on the way in decides
    the row's confidence: a hop recovered through a function pointer is a real edge and an
    inference about indirection at the same time.

    @brief Reachability from one interrupt entry, with depth and edge strength.
    @return The closure.
    @version 1
    """
    seen: dict[int, tuple[int, str]] = {entry_rowid: (0, "")}
    frontier = [entry_rowid]
    depth = 0
    while frontier:
        depth += 1
        rows = conn.execute(
            "SELECT caller_rowid, callee_rowid, source FROM call_edges "
            f"WHERE caller_rowid IN ({','.join('?' * len(frontier))}) "
            "AND confidence != 'fuzzy' AND source != ?",
            (*frontier, _EXCLUDED_EDGE_SOURCE),
        ).fetchall()
        nxt: list[int] = []
        for caller, callee, source in rows:
            if callee in seen:
                continue
            inherited = seen[caller][1]
            weakest = source if source in _INDIRECT_SOURCES else inherited
            seen[callee] = (depth, weakest)
            nxt.append(callee)
        frontier = nxt
    return seen


## @brief How much to trust a conflict found at this depth through these edges.
## @param depth Hops from the interrupt entry.
## @param weakest The weakest edge source on the path.
## @return A context_conflicts.confidence value.
## @version 1
## @dg_internal
def _confidence(depth: int, weakest: str) -> str:
    """@brief Grade a witness path.

    @return The confidence.
    @version 1
    """
    if weakest in _INDIRECT_SOURCES:
        return "low"
    return "high" if depth == 0 else "medium"


## @brief Rows for the locks an interrupt-reachable function takes.
## @param conn Open connection.
## @param closure The handler's closure.
## @param thread_id The interrupt thread's id.
## @return Row tuples ready for insertion.
## @version 2
## @dg_internal
def _lock_rows(
    conn: sqlite3.Connection, closure: dict[int, tuple[int, str]], thread_id: int
) -> list[tuple]:
    """A spinlock and an interrupt-mask critical section are EXCLUDED rather than reported: they
    are what interrupt code is supposed to use. That exclusion is the whole reason gh#47 part 3
    gave interrupt masking its own kind — spelled `mutex`, as a declaration with no kind still
    defaults to, every critical section in a firmware tree would be a conflict with itself.

    @brief Blocking acquisitions inside the closure.
    @return Row tuples.
    @version 1
    """
    members = list(closure)
    placeholders = ",".join("?" * len(members))
    rows = conn.execute(
        "SELECT a.holder_rowid, a.path_rowid, a.start_line, a.pattern_name, a.role, "
        "       a.lock_id, COALESCE(l.name, ''), COALESCE(l.kind, '') "
        "FROM lock_acquisitions a LEFT JOIN locks l ON l.id = a.lock_id "
        f"WHERE a.holder_rowid IN ({placeholders})",
        members,
    ).fetchall()
    out: list[tuple] = []
    for holder, path_rowid, line, pattern, role, lock_id, lock_name, kind in rows:
        depth, weakest = closure[holder]
        confidence = _confidence(depth, weakest)
        if lock_id is None:
            out.append(
                (
                    thread_id,
                    holder,
                    VERDICT_UNDECIDABLE,
                    REASON_UNRESOLVED_LOCK,
                    pattern,
                    "the acquisition's operand did not resolve to a lock identity",
                    path_rowid,
                    line,
                    depth,
                    confidence,
                )
            )
        elif kind in BLOCKING_LOCK_KINDS and role != "try_acquire":
            out.append(
                (
                    thread_id,
                    holder,
                    VERDICT_CONFLICT,
                    REASON_BLOCKING_LOCK,
                    lock_name or pattern,
                    f"{kind} taken by {pattern}",
                    path_rowid,
                    line,
                    depth,
                    confidence,
                )
            )
    return out


## @brief Rows for the blocking primitives an interrupt-reachable function calls.
## @param conn Open connection.
## @param closure The handler's closure.
## @param thread_id The interrupt thread's id.
## @return Row tuples ready for insertion.
## @version 2
## @dg_internal
def _call_rows(
    conn: sqlite3.Connection, closure: dict[int, tuple[int, str]], thread_id: int
) -> list[tuple]:
    """The timeout decides, and it is read off the argument TEXT: `k_sem_take(&s, K_NO_WAIT)` is
    what correct interrupt code looks like, and the same call with `K_FOREVER` is the bug.

    @brief Blocking calls inside the closure.
    @return Row tuples.
    @version 1
    """
    members = list(closure)
    placeholders = ",".join("?" * len(members))
    rows = conn.execute(
        "SELECT holder_rowid, path_rowid, line, primitive, wait, wait_operand, guard "
        f"FROM blocking_calls WHERE holder_rowid IN ({placeholders})",
        members,
    ).fetchall()
    out: list[tuple] = []
    for holder, path_rowid, line, primitive, wait, operand, guard in rows:
        depth, weakest = closure[holder]
        confidence = _confidence(depth, weakest)
        if guard:
            out.append(
                (
                    thread_id,
                    holder,
                    VERDICT_UNDECIDABLE,
                    REASON_GUARDED,
                    primitive,
                    guard,
                    path_rowid,
                    line,
                    depth,
                    confidence,
                )
            )
        elif wait == "undecidable":
            out.append(
                (
                    thread_id,
                    holder,
                    VERDICT_UNDECIDABLE,
                    REASON_UNDECIDABLE_TIMEOUT,
                    primitive,
                    operand,
                    path_rowid,
                    line,
                    depth,
                    confidence,
                )
            )
        elif wait in _BLOCKING_WAITS:
            detail = f"{primitive}({operand})" if operand else f"{primitive} blocks unconditionally"
            out.append(
                (
                    thread_id,
                    holder,
                    VERDICT_CONFLICT,
                    REASON_BLOCKING_CALL,
                    primitive,
                    detail,
                    path_rowid,
                    line,
                    depth,
                    confidence,
                )
            )
    return out


## @brief Derive every interrupt-context conflict in the index.
## @param db_path Database being built.
## @return None.
## @version 2
## @req REQ-DDB-SCHEMA-011
def extract_context_conflicts(db_path: Path) -> None:
    """Runs after the thread stage, which is the first point at which the call graph, the lock
    layer and interrupt membership are all final.

    @brief Populate context_conflicts and log the count.
    @return None.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    ensure_context_table(conn)
    handlers = conn.execute(
        "SELECT id, entry_memberdef_rowid FROM threads "
        "WHERE kind = 'isr' AND entry_memberdef_rowid IS NOT NULL"
    ).fetchall()
    rows: list[tuple] = []
    for thread_id, entry_rowid in handlers:
        closure = _isr_closure(conn, entry_rowid)
        rows.extend(_lock_rows(conn, closure, thread_id))
        rows.extend(_call_rows(conn, closure, thread_id))
    inserted = conn.executemany(
        "INSERT OR IGNORE INTO context_conflicts "
        "(thread_id, member_rowid, verdict, reason, evidence, detail, path_rowid, line, "
        " depth, confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    ).rowcount
    conn.commit()
    split = dict(
        conn.execute("SELECT reason, COUNT(*) FROM context_conflicts GROUP BY reason").fetchall()
    )
    conflicts = conn.execute(
        "SELECT COUNT(*) FROM context_conflicts WHERE verdict = ?", (VERDICT_CONFLICT,)
    ).fetchone()[0]
    conn.close()
    logger.info(
        "context: %d conflicts across %d interrupt handlers, %d undecided (%s)",
        conflicts,
        len(handlers),
        inserted - conflicts,
        ", ".join(f"{count} {reason}" for reason, count in sorted(split.items())) or "none",
    )
