# SPDX-License-Identifier: MIT
"""Where a function calls a primitive that can PARK IT, and under what timeout.

gh#47 part 2 needs to answer "does anything this interrupt handler reaches block". Nothing in
the index could answer it, for two reasons measured at the pinned trees:

  * **The callee is not in the index.** `call_edges.callee_rowid` is NOT NULL, so a call to
    `k_sleep` or `vTaskDelay` produces no edge at all. Zephyr's are worse than absent: they are
    `__syscall` declarations whose wrappers are GENERATED into `<zephyr/syscalls/*.h>` at build
    time (`git ls-files include/zephyr/syscalls` -> 0 files), so there is no
    `k_sem_take -> z_impl_k_sem_take -> z_pend_curr` chain to follow even in principle. The
    blocking set has to be seeded by NAME.
  * **Blocking is argument-conditional for about half of them.** `k_sem_take(&s, K_NO_WAIT)` and
    `xQueueReceive(q, &x, 0)` are LEGAL in an interrupt; the same calls with `K_FOREVER` or
    `portMAX_DELAY` are the bug. The index records no argument text anywhere — `ast_calls`
    carries the callee name and an argument COUNT (call_edges.py) and `external_callees` is
    recomputed at query time with no arguments at all.

So this stage records the call site with its timeout argument VERBATIM, classifies the wait, and
keeps the enclosing condition text so a runtime context guard is visible rather than guessed at.
It rides the shared parse pass like every other per-file harvester; it does not re-parse.

WHAT IT DELIBERATELY DOES NOT DO: evaluate the guard's polarity. `if (k_is_in_isr()) { ... }`
may take the safe branch or the unsafe one, and choosing would be a guess. The condition is
recorded, the site is reported as guarded, and the count says how many were withheld.

@brief Blocking-primitive call sites with their timeout and guard text.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, enclosing, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .vocabulary import BLOCKING_WAIT, STAGE_BLOCKING, check

## How a wait argument reads. `none` is the legal-in-an-ISR case and is why the operand is read
## at all; `undecidable` is what an opaque expression gets, because promoting it to a conflict
## fabricates one and dropping it silently makes an empty conflict list a lie.
WAIT_NONE = "none"
WAIT_FOREVER = "forever"
WAIT_BOUNDED = "bounded"
WAIT_UNCONDITIONAL = "unconditional"
WAIT_UNDECIDABLE = "undecidable"

## Runtime predicates that answer "am I in interrupt context". A call whose enclosing condition
## — or whose own timeout expression — mentions one is guarded: RIOT `irq_is_in()`, Zephyr
## `k_is_in_isr()`/`arch_is_in_isr()`, FreeRTOS `xPortIsInsideInterrupt()`, and the ESP shim.
ISR_PREDICATES = (
    "irq_is_in",
    "k_is_in_isr",
    "arch_is_in_isr",
    "xPortIsInsideInterrupt",
    "xPortInIsrContext",
    "in_interrupt",
    "in_irq",
    "in_atomic",
)

## Timeout spellings that mean "do not wait" and "wait forever". Read off the trees rather than
## recalled: K_NO_WAIT/K_FOREVER (Zephyr kernel.h), portMAX_DELAY (FreeRTOS projdefs.h),
## osWaitForever (CMSIS-RTOS).
_NO_WAIT_TOKENS = frozenset({"K_NO_WAIT", "0", "0U", "0u", "0UL", "0ul", "osWaitNone", "pdFALSE"})
_FOREVER_TOKENS = frozenset(
    {"K_FOREVER", "portMAX_DELAY", "osWaitForever", "-1", "0xFFFFFFFF", "portMAX_DELAY_TICKS"}
)
## Macro spellings that turn a duration into a timeout: a BOUNDED wait, which still blocks.
_BOUNDED_PREFIXES = ("K_MSEC", "K_SECONDS", "K_MINUTES", "K_HOURS", "K_TICKS", "K_USEC", "pdMS_TO_TICKS")


## @brief One blocking primitive: its name and where its timeout argument sits.
## @version 1
class BlockingPattern:
    """`timeout_arg_index` is None for a primitive that blocks whatever its arguments say —
    `k_sleep`, `vTaskDelay`, `pthread_mutex_lock`, RIOT's `mutex_lock`, and the Zephyr calls
    whose own assertion forbids interrupt context regardless of timeout (`k_mutex_lock`,
    kernel/mutex.c:115; `k_poll`, kernel/poll.c:293).

    @brief A call that can park its caller.
    @version 1
    """

    __slots__ = ("name", "timeout_arg_index")

    ## @brief Store one blocking convention.
    ## @param name The callee identifier as written at the call site.
    ## @param timeout_arg_index 0-based index of the timeout argument, or None.
    ## @version 1
    ## @dg_internal
    def __init__(self, name: str, timeout_arg_index: int | None = None) -> None:
        self.name = name
        self.timeout_arg_index = timeout_arg_index


## The shipped set. Every entry was read at a pinned commit with the line that forbids interrupt
## context beside it: Zephyr v4.4.2 kernel/*.c asserts, FreeRTOS-Kernel V11.3.1 queue.h/task.h
## ("This function must not be called from an interrupt service routine"), RIOT 50ae2eba
## core/include/*.h ("@pre Must be called in thread context").
DEFAULT_BLOCKING_PATTERNS: list[BlockingPattern] = [
    # Zephyr — unconditional (the assert does not look at the timeout).
    BlockingPattern("k_sleep"),
    BlockingPattern("k_msleep"),
    BlockingPattern("k_usleep"),
    BlockingPattern("k_yield"),
    BlockingPattern("k_mutex_lock"),
    BlockingPattern("k_condvar_wait"),
    BlockingPattern("k_thread_create"),
    BlockingPattern("k_timer_status_sync"),
    BlockingPattern("k_work_flush"),
    BlockingPattern("k_work_cancel_sync"),
    BlockingPattern("k_work_flush_delayable"),
    BlockingPattern("k_work_cancel_delayable_sync"),
    # Zephyr — legal from an ISR only with K_NO_WAIT, which is exactly why the operand is read.
    BlockingPattern("k_sem_take", timeout_arg_index=1),
    BlockingPattern("k_msgq_get", timeout_arg_index=2),
    BlockingPattern("k_msgq_put", timeout_arg_index=2),
    BlockingPattern("k_queue_get", timeout_arg_index=1),
    BlockingPattern("k_fifo_get", timeout_arg_index=1),
    BlockingPattern("k_lifo_get", timeout_arg_index=1),
    BlockingPattern("k_stack_pop", timeout_arg_index=2),
    BlockingPattern("k_mem_slab_alloc", timeout_arg_index=2),
    BlockingPattern("k_heap_alloc", timeout_arg_index=2),
    BlockingPattern("k_heap_aligned_alloc", timeout_arg_index=3),
    BlockingPattern("k_event_wait", timeout_arg_index=3),
    BlockingPattern("k_event_wait_all", timeout_arg_index=3),
    BlockingPattern("k_thread_join", timeout_arg_index=1),
    BlockingPattern("k_poll", timeout_arg_index=2),
    BlockingPattern("k_mbox_get", timeout_arg_index=2),
    BlockingPattern("k_pipe_read", timeout_arg_index=3),
    BlockingPattern("k_pipe_write", timeout_arg_index=3),
    # FreeRTOS — the non-FromISR API. Every one of these has a FromISR counterpart, which is
    # the whole design of the kernel's interrupt story, so a plain call from an ISR is the bug.
    BlockingPattern("vTaskDelay"),
    BlockingPattern("vTaskDelayUntil"),
    BlockingPattern("xTaskDelayUntil"),
    BlockingPattern("vTaskSuspendAll"),
    BlockingPattern("xQueueReceive", timeout_arg_index=2),
    BlockingPattern("xQueuePeek", timeout_arg_index=2),
    BlockingPattern("xQueueSend", timeout_arg_index=2),
    BlockingPattern("xQueueSendToBack", timeout_arg_index=2),
    BlockingPattern("xQueueSendToFront", timeout_arg_index=2),
    BlockingPattern("xQueueGenericSend", timeout_arg_index=2),
    BlockingPattern("xQueueSemaphoreTake", timeout_arg_index=1),
    BlockingPattern("xSemaphoreTake", timeout_arg_index=1),
    BlockingPattern("xSemaphoreGive"),
    BlockingPattern("ulTaskNotifyTake", timeout_arg_index=1),
    BlockingPattern("xTaskNotifyWait", timeout_arg_index=3),
    BlockingPattern("xEventGroupWaitBits", timeout_arg_index=4),
    BlockingPattern("xStreamBufferReceive", timeout_arg_index=3),
    BlockingPattern("xStreamBufferSend", timeout_arg_index=3),
    BlockingPattern("xMessageBufferReceive", timeout_arg_index=3),
    BlockingPattern("xMessageBufferSend", timeout_arg_index=3),
    BlockingPattern("xTimerReset", timeout_arg_index=1),
    BlockingPattern("xTimerStart", timeout_arg_index=1),
    BlockingPattern("xTimerStop", timeout_arg_index=1),
    # RIOT — "@pre Must be called in thread context", or an assert(!irq_is_in()).
    BlockingPattern("mutex_lock"),
    BlockingPattern("mutex_lock_cancelable"),
    BlockingPattern("rmutex_lock"),
    BlockingPattern("msg_receive"),
    BlockingPattern("msg_send_receive"),
    BlockingPattern("thread_sleep"),
    BlockingPattern("ztimer_sleep"),
    BlockingPattern("ztimer_msleep"),
    BlockingPattern("xtimer_sleep"),
    BlockingPattern("xtimer_usleep"),
    BlockingPattern("xtimer_msleep"),
    BlockingPattern("sema_wait"),
    BlockingPattern("sema_inv_wait"),
    BlockingPattern("cond_wait"),
    BlockingPattern("mbox_get"),
    BlockingPattern("event_wait"),
    BlockingPattern("thread_flags_wait_any"),
    BlockingPattern("thread_flags_wait_all"),
    BlockingPattern("thread_flags_wait_one"),
    BlockingPattern("i2c_acquire"),
    BlockingPattern("spi_acquire"),
    # POSIX, for the userspace analogue (a signal handler is the same rule).
    BlockingPattern("pthread_mutex_lock"),
    BlockingPattern("pthread_cond_wait"),
    BlockingPattern("pthread_join"),
    BlockingPattern("sem_wait"),
    BlockingPattern("sleep"),
    BlockingPattern("usleep"),
    BlockingPattern("nanosleep"),
]


## @brief Classify one timeout argument's text.
## @param operand The argument text as written, or "" when the pattern takes none.
## @param has_timeout Whether the pattern declares a timeout argument at all.
## @return A BLOCKING_WAIT member.
## @version 1
## @dg_internal
def classify_wait(operand: str, has_timeout: bool) -> str:
    """Read off the TEXT, never off the callee name: the same primitive is legal or illegal in
    an interrupt depending on this one argument.

    @brief Classify a wait argument.
    @return The wait class.
    @version 1
    """
    if not has_timeout:
        return WAIT_UNCONDITIONAL
    token = operand.replace(" ", "")
    if not token:
        return WAIT_UNDECIDABLE
    if token in _NO_WAIT_TOKENS:
        return WAIT_NONE
    if token in _FOREVER_TOKENS:
        return WAIT_FOREVER
    if token.startswith(_BOUNDED_PREFIXES):
        return WAIT_BOUNDED
    if token.isdigit():
        return WAIT_NONE if int(token) == 0 else WAIT_BOUNDED
    return WAIT_UNDECIDABLE


## @brief The nearest enclosing condition text for a node, up to a few levels.
## @param node The call node.
## @param src The file's raw bytes.
## @return The condition source text, or "".
## @version 1
## @dg_internal
def _enclosing_condition(node: Any, src: bytes) -> str:
    """Three levels up at most. A guard further away than that is not a guard a reader would
    call one, and the point is to SHOW the condition rather than to evaluate it.

    @brief Read the nearest enclosing `if` condition.
    @return The condition text, or "".
    @version 1
    """
    current = node
    for _ in range(3):
        statement = enclosing(current, ("if_statement",))
        if statement is None:
            return ""
        condition = statement.child_by_field_name("condition")
        text = (
            src[condition.start_byte : condition.end_byte].decode("utf-8", errors="replace")
            if condition is not None
            else ""
        )
        if any(predicate in text for predicate in ISR_PREDICATES):
            return text
        current = statement
    return ""


## @brief Harvest one file's blocking-primitive call sites.
## @param tree The parsed tree.
## @param src_bytes The file's raw bytes.
## @param patterns_by_name Blocking patterns keyed by callee name.
## @return A list of [primitive, line, wait, wait_operand, guard] records.
## @version 1
## @req REQ-DDB-SCHEMA-011
def walk_blocking_sites(tree: Any, src_bytes: bytes, patterns_by_name: dict) -> list[list[Any]]:
    """Rowid-free like every harvest payload: the holder is resolved by LINE at insert time,
    exactly as a lock acquisition's is.

    @brief Walk one file for blocking call sites.
    @return The site records.
    @version 1
    """
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call_expression":
            continue
        callee = node.child_by_field_name("function")
        if callee is None or callee.type != "identifier":
            continue
        name = src_bytes[callee.start_byte : callee.end_byte].decode("utf-8", errors="replace")
        pattern = patterns_by_name.get(name)
        if pattern is None:
            continue
        arguments = node.child_by_field_name("arguments")
        named = [child for child in arguments.named_children] if arguments is not None else []
        operand = ""
        if pattern.timeout_arg_index is not None and len(named) > pattern.timeout_arg_index:
            argument = named[pattern.timeout_arg_index]
            operand = src_bytes[argument.start_byte : argument.end_byte].decode(
                "utf-8", errors="replace"
            )
        guard = _enclosing_condition(node, src_bytes)
        ## THE GUARD CAN LIVE IN THE ARGUMENT ITSELF. Zephyr's power-management path writes
        ## `k_sem_take(&pm->lock, k_is_in_isr() ? K_NO_WAIT : K_FOREVER)`
        ## (subsys/pm/device_runtime.c:71) — ten interrupt handlers reach it.
        if not guard and any(predicate in operand for predicate in ISR_PREDICATES):
            guard = operand
        sites.append(
            [
                name,
                node.start_point[0] + 1,
                classify_wait(operand, pattern.timeout_arg_index is not None),
                operand,
                guard,
            ]
        )
    return sites


## @brief Per-file harvester for blocking-primitive call sites.
## @version 1
class _BlockingHarvester(Harvester):
    """Its own stage rather than a widening of `ast_calls`: that payload is version 7 and feeds
    every call-edge consumer, so adding argument text to it would cold-parse every file in
    every index to answer a question about ~80 names.

    @brief Blocking-call per-file harvester.
    @version 1
    """

    stage = STAGE_BLOCKING
    stage_version = 1
    label = "blocking calls"

    ## @brief Store the pattern map.
    ## @version 1
    ## @dg_internal
    def __init__(self, patterns_by_name: dict, extra_key: str = "") -> None:
        super().__init__(extra_key)
        self.patterns_by_name = patterns_by_name

    ## @brief Harvest one file's blocking call sites.
    ## @return List of site records.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-011
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return walk_blocking_sites(tree, src_bytes, self.patterns_by_name)


## @brief The blocking-call stage's harvester.
## @return A Harvester over the built-in blocking primitives.
## @version 1
## @req REQ-DDB-SCHEMA-011
def blocking_harvester() -> Harvester:
    """@brief Build this stage's harvester.

    @return The harvester.
    @version 1
    """
    return _BlockingHarvester({p.name: p for p in DEFAULT_BLOCKING_PATTERNS})


## @brief Create the blocking_calls table.
## @param conn Open connection.
## @return None.
## @version 1
## @req REQ-DDB-SCHEMA-011
def ensure_blocking_table(conn: sqlite3.Connection) -> None:
    """Created unconditionally, like the lock tables, so a repository with no blocking call —
    or a build without tree_sitter — yields an EMPTY table rather than an absent one and no
    consumer has to branch on existence.

    @brief Create blocking_calls if it does not exist.
    @return None.
    @version 1
    """
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS blocking_calls (
          id INTEGER PRIMARY KEY,
          holder_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
          path_rowid INTEGER NOT NULL REFERENCES path(rowid),
          line INTEGER NOT NULL,
          primitive TEXT NOT NULL,
          wait TEXT NOT NULL {check("blocking_calls", "wait")},
          wait_operand TEXT NOT NULL,
          guard TEXT NOT NULL,
          UNIQUE(holder_rowid, line, primitive)
        );
        CREATE INDEX IF NOT EXISTS idx_blocking_holder ON blocking_calls(holder_rowid);
        """
    )


## @brief Harvest and persist every blocking-primitive call site.
## @param db_path Database being built.
## @param repo_root Working tree to scan.
## @param cache Live index cache, or None.
## @param harvester Pre-built harvester from the shared parse pass, or None.
## @return None.
## @version 1
## @req REQ-DDB-SCHEMA-011
def extract_blocking_calls(
    db_path: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
    harvester: Harvester | None = None,
) -> None:
    """Runs after the call-edge layers for the same reason the lock stage does: the holder is
    resolved from the function extents those layers build.

    @brief Populate blocking_calls.
    @return None.
    @version 1
    """
    from .call_edges import _ast_caller_at_line, _build_function_indexes

    conn = sqlite3.connect(str(db_path))
    ensure_blocking_table(conn)
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.info("blocking: tree_sitter unavailable — skipping (table still created)")
        conn.commit()
        conn.close()
        return
    _name_to_rowids, file_funcs = _build_function_indexes(conn)
    harvester = harvester or blocking_harvester()
    inserted = 0
    for path_rowid, payload in run_harvest(conn, repo_root, harvester, ts_classes, cache):
        for record in payload:
            holder = _ast_caller_at_line(file_funcs.get(path_rowid, []), record[1])
            if holder is None:
                continue
            inserted += conn.execute(
                "INSERT OR IGNORE INTO blocking_calls "
                "(holder_rowid, path_rowid, line, primitive, wait, wait_operand, guard) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (holder, path_rowid, record[1], record[0], record[2], record[3], record[4]),
            ).rowcount
    conn.commit()
    waits = dict(
        conn.execute("SELECT wait, COUNT(*) FROM blocking_calls GROUP BY wait").fetchall()
    )
    conn.close()
    logger.info(
        "blocking: %d call sites (%s)",
        inserted,
        ", ".join(f"{count} {wait}" for wait, count in sorted(waits.items())) or "none",
    )


## Re-exported so a reader of the vocabulary finds the classifier beside the values it returns.
__all__ = [
    "BLOCKING_WAIT",
    "DEFAULT_BLOCKING_PATTERNS",
    "BlockingPattern",
    "blocking_harvester",
    "classify_wait",
    "ensure_blocking_table",
    "extract_blocking_calls",
    "walk_blocking_sites",
]
