# SPDX-License-Identifier: MIT
"""gh#47 part 2: what an interrupt handler reaches that it may not reach.

The rule is only as good as its EXCLUSIONS. Three of them decide whether the layer is usable on
a real firmware tree, and each was read off a pinned tree rather than reasoned about:

  * masking interrupts is what an interrupt handler is SUPPOSED to do — RIOT's `core/**/*.c`
    alone holds 43 `irq_disable()` holds, and spelling them `mutex` would make every one a
    conflict with itself;
  * `k_sem_take(&s, K_NO_WAIT)` is legal in an interrupt and `k_sem_take(&s, K_FOREVER)` is the
    bug — same callee, decided entirely by an argument no other layer records;
  * a deferral is the CORRECT pattern: an interrupt binds a work handler that then runs on a
    workqueue thread and blocks there (Zephyr ships 720 `k_work_init` sites).

@brief Tests for clew.context.
@version 1
"""

from __future__ import annotations

import sqlite3

from clew.blocking import ensure_blocking_table
from clew.context import VERDICT_CONFLICT, VERDICT_UNDECIDABLE, extract_context_conflicts
from clew.locks import _ensure_lock_tables
from clew.threads import _ensure_threads_tables


## @brief Build a database holding one interrupt handler and everything it reaches.
## @param tmp_path Pytest temporary directory.
## @return Path to the database.
## @version 1
def _context_db(tmp_path) -> "object":
    """The shape is RIOT's and Zephyr's, reduced: a handler, a helper it calls, a deferred
    worker it only BINDS, and one of each site the rule has to judge.

    @brief Hand-build the four layers the conflict rule joins.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (name TEXT, kind TEXT);
        CREATE TABLE call_edges (
          caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT);
        INSERT INTO path (name) VALUES ('src/drv.c');
        INSERT INTO memberdef (name, kind) VALUES
          ('uart_isr', 'function'),      -- rowid 1, the handler
          ('drain', 'function'),         -- rowid 2, called by the handler
          ('deferred_work', 'function'), -- rowid 3, BOUND by the handler, run later
          ('task_loop', 'function');     -- rowid 4, not interrupt-reachable at all
        INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) VALUES
          (1, 2, 'ast', 'resolved'),
          (1, 3, 'binding', 'resolved'),
          (4, 2, 'ast', 'resolved');
        """
    )
    _ensure_threads_tables(conn)
    _ensure_lock_tables(conn)
    ensure_blocking_table(conn)
    conn.executescript(
        """
        INSERT INTO threads
          (name, entry_memberdef_rowid, kind, source, confidence, spawn_path_rowid, spawn_line)
          VALUES ('uart_isr', 1, 'isr', 'ast_isr_name', 'medium', 1, 12);
        INSERT INTO locks (name, scope, kind, identity_confidence, source) VALUES
          ('bus_lock', 'unknown', 'mutex', 'low', 'ast_use'),          -- id 1: blocks
          ('irq_disable', 'global', 'interrupt_mask', 'high', 'ast_use'), -- id 2: does not
          ('ring', 'unknown', 'spinlock', 'low', 'ast_use');           -- id 3: does not
        INSERT INTO lock_acquisitions
          (lock_id, holder_rowid, path_rowid, form, role, mode, start_line, end_line,
           pattern_name, declared, confidence)
          VALUES
          (1, 2, 1, 'call', 'acquire', 'exclusive', 40, 44, 'pthread_mutex_lock', 0, 'high'),
          (2, 2, 1, 'call', 'acquire', 'exclusive', 50, 52, 'irq_disable', 0, 'high'),
          (3, 2, 1, 'call', 'acquire', 'exclusive', 60, 62, 'k_spin_lock', 0, 'high'),
          (NULL, 2, 1, 'call', 'acquire', 'exclusive', 70, NULL, 'pthread_mutex_lock', 0, 'low'),
          (1, 4, 1, 'call', 'acquire', 'exclusive', 90, 94, 'pthread_mutex_lock', 0, 'high');
        INSERT INTO blocking_calls
          (holder_rowid, path_rowid, line, primitive, wait, wait_operand, guard)
          VALUES
          (2, 1, 41, 'k_sem_take', 'forever', 'K_FOREVER', ''),
          (2, 1, 42, 'k_sem_take', 'none', 'K_NO_WAIT', ''),
          (2, 1, 43, 'k_sem_take', 'undecidable', 'cfg->wait', ''),
          (2, 1, 45, 'k_sleep', 'unconditional', '', 'k_is_in_isr()'),
          (3, 1, 80, 'k_sem_take', 'forever', 'K_FOREVER', ''),
          (4, 1, 95, 'vTaskDelay', 'unconditional', '', '');
        """
    )
    conn.commit()
    conn.close()
    return db


## @brief Read every conflict row back, keyed by (reason, evidence, line).
## @param db The database path.
## @return Mapping of key to (verdict, detail, depth, confidence).
## @version 1
def _rows(db) -> dict:
    """@brief Read context_conflicts back."""
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT reason, evidence, line, verdict, detail, depth, confidence FROM context_conflicts"
    ).fetchall()
    conn.close()
    return {(r[0], r[1], r[2]): (r[3], r[4], r[5], r[6]) for r in rows}


def test_a_blocking_lock_and_a_blocking_call_in_the_closure_are_conflicts(tmp_path) -> None:
    """The two arms of the rule, one hop from the handler. `drain` is not itself an interrupt
    handler — it is reachable from one, which is the whole question a firmware engineer asks.

    @brief Both conflict reasons are found, with the path depth recorded.
    @version 1
    """
    db = _context_db(tmp_path)
    extract_context_conflicts(db)
    rows = _rows(db)

    lock = rows[("blocking_lock", "bus_lock", 40)]
    assert lock[0] == VERDICT_CONFLICT
    assert lock[2] == 1, f"drain is one hop from the handler, got depth {lock[2]}"
    assert lock[3] == "medium", f"a one-hop path through an ast edge is medium, got {lock[3]}"

    call = rows[("blocking_call", "k_sem_take", 41)]
    assert call[0] == VERDICT_CONFLICT
    assert "K_FOREVER" in call[1], f"the detail must carry the timeout as written, got {call[1]}"


def test_what_an_interrupt_handler_is_supposed_to_do_is_not_a_conflict(tmp_path) -> None:
    """Masking interrupts, taking a spinlock, and taking a semaphore with a zero timeout are all
    correct interrupt code. A rule that flags them is worse than no rule: it buries the two real
    findings above in noise proportional to the size of the tree.

    @brief Interrupt-mask, spinlock and K_NO_WAIT sites produce no row.
    @version 1
    """
    rows = _rows(_run(tmp_path))

    assert ("blocking_lock", "irq_disable", 50) not in rows, "masking interrupts is the point"
    assert ("blocking_lock", "ring", 60) not in rows, "a spinlock does not park the caller"
    assert not [key for key in rows if key[2] == 42], "K_NO_WAIT is legal in an interrupt"


def test_the_index_says_when_it_cannot_decide(tmp_path) -> None:
    """THE THIRD OUTCOME. An opaque timeout and a runtime context guard are recorded as
    UNDECIDABLE, never as clean and never as a conflict: promoting either fabricates a finding,
    dropping it makes an empty conflict list a claim the index has not earned.

    Branch polarity is deliberately not evaluated — `if (k_is_in_isr())` may guard the safe path
    or the unsafe one — so the condition is reported and the reader decides.

    @brief Undecidable sites are counted with their reason.
    @version 1
    """
    rows = _rows(_run(tmp_path))

    opaque = rows[("undecidable_timeout", "k_sem_take", 43)]
    assert opaque[0] == VERDICT_UNDECIDABLE
    assert opaque[1] == "cfg->wait", f"the operand is kept verbatim, got {opaque[1]}"

    guarded = rows[("guarded_by_isr_predicate", "k_sleep", 45)]
    assert guarded[0] == VERDICT_UNDECIDABLE
    assert "k_is_in_isr" in guarded[1], f"the guard is shown, not evaluated; got {guarded[1]}"

    unresolved = rows[("unresolved_lock_identity", "pthread_mutex_lock", 70)]
    assert unresolved[0] == VERDICT_UNDECIDABLE


def test_a_deferred_handler_is_not_inside_the_interrupt(tmp_path) -> None:
    """`binding` means "a reference someone else will call later, at a time and on a thread this
    edge says nothing about". Getting work OUT of an interrupt by binding a handler is the
    pattern every RTOS documents, so traversing that edge would report the correct pattern as
    the violation — and thread membership traverses it, which is why this closure does not.

    `task_loop` is the control: it takes the same mutex and is not interrupt-reachable at all.

    @brief A binding edge is not an interrupt-context path.
    @version 1
    """
    rows = _rows(_run(tmp_path))

    assert ("blocking_call", "k_sem_take", 80) not in rows, (
        "deferred_work runs on a workqueue thread, where blocking is legal"
    )
    assert ("blocking_call", "vTaskDelay", 95) not in rows, "task_loop is not an interrupt path"
    assert ("blocking_lock", "bus_lock", 90) not in rows, "task_loop is not an interrupt path"


## @brief Build the fixture and run the stage.
## @param tmp_path Pytest temporary directory.
## @return The database path.
## @version 1
def _run(tmp_path) -> "object":
    """@brief Build and derive, for the tests that only read rows back."""
    db = _context_db(tmp_path)
    extract_context_conflicts(db)
    return db
