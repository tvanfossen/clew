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

import re
import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, enclosing, run_harvest
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
_BOUNDED_PREFIXES = (
    "K_MSEC",
    "K_SECONDS",
    "K_MINUTES",
    "K_HOURS",
    "K_TICKS",
    "K_USEC",
    "pdMS_TO_TICKS",
)


## @brief The regex for a call of any of these ISR predicates, as a whole identifier (W7).
## @param predicates The predicate names.
## @return The compiled regex.
## @version 1
## @dg_internal
def _isr_call(predicates: tuple[str, ...]) -> re.Pattern[str]:
    """@brief Compile the predicate-call regex. @return Regex."""
    return re.compile(r"(?<![A-Za-z0-9_])(?:" + "|".join(map(re.escape, predicates)) + r")\s*\(")


## A call of any built-in ISR predicate.
_ISR_CALL = _isr_call(ISR_PREDICATES)


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


## @brief The words one build reads blocking calls with: the built-ins plus a declaration.
## @version 1
class BlockingVocabulary:
    """R5-CORE C1 (2.0.0): `blocking:` ADDS to the built-in primitives, ISR predicates and wait
    tokens, which are facts about the RTOSes they come from — a declaration widens the set, it
    never removes Zephyr's `K_FOREVER`.

    @brief A blocking vocabulary.
    @version 1
    """

    ## @brief Build the vocabulary from the built-ins and a declaration.
    ## @param declared The `blocking:` section, or None.
    ## @version 1
    ## @dg_internal
    def __init__(self, declared: dict | None = None) -> None:
        declared = _checked_blocking(declared or {})
        tokens = declared.get("wait_tokens") or {}
        self.patterns_by_name = {p.name: p for p in DEFAULT_BLOCKING_PATTERNS}
        for entry in declared.get("primitives") or []:
            self.patterns_by_name[entry["name"]] = BlockingPattern(
                entry["name"], entry.get("timeout_arg_index")
            )
        self.isr_call = _isr_call((*ISR_PREDICATES, *(declared.get("isr_predicates") or [])))
        self.none_tokens = _NO_WAIT_TOKENS | set(tokens.get("none") or [])
        self.forever_tokens = _FOREVER_TOKENS | set(tokens.get("forever") or [])
        self.bounded_prefixes = (*_BOUNDED_PREFIXES, *(tokens.get("bounded_prefixes") or []))


## The keys of the `blocking:` section and of its `wait_tokens`.
BLOCKING_KEYS = frozenset({"primitives", "isr_predicates", "wait_tokens"})
_WAIT_TOKEN_KEYS = frozenset({"none", "forever", "bounded_prefixes"})
_PRIMITIVE_KEYS = frozenset({"name", "timeout_arg_index"})


## @brief Refuse a malformed `blocking:` section by name.
## @param declared The section.
## @return The section; raises DeclarationError naming what is wrong.
## @version 1
## @dg_internal
def _checked_blocking(declared: dict) -> dict:
    """AN UNKNOWN KEY OR A WRONG SHAPE IS REFUSED, never defaulted: a misspelled
    `timeout_arg` would silently make a timed wait read as unconditional.

    @brief Validate the blocking declaration.
    @return The section.
    """
    from .vocabulary import DeclarationError

    problems = [f"unknown key {k!r}" for k in declared if k not in BLOCKING_KEYS]
    for i, entry in enumerate(declared.get("primitives") or []):
        if not isinstance(entry, dict) or not entry.get("name"):
            problems.append(f"primitives[{i}] needs a `name`")
            continue
        problems += [
            f"primitives[{i}]: unknown key {k!r}" for k in entry if k not in _PRIMITIVE_KEYS
        ]
        index = entry.get("timeout_arg_index")
        if index is not None and (
            not isinstance(index, int) or isinstance(index, bool) or index < 0
        ):
            problems.append(f"primitives[{i}].timeout_arg_index must be a non-negative integer")
    preds = declared.get("isr_predicates")
    if preds is not None and (
        not isinstance(preds, list) or not all(isinstance(p, str) for p in preds)
    ):
        problems.append("isr_predicates must be a list of names")
    tokens = declared.get("wait_tokens") or {}
    if not isinstance(tokens, dict):
        problems.append("wait_tokens must map none / forever / bounded_prefixes to lists")
        tokens = {}
    problems += [f"wait_tokens: unknown key {k!r}" for k in tokens if k not in _WAIT_TOKEN_KEYS]
    if problems:
        raise DeclarationError(
            f"blocking: {'; '.join(problems)} — allowed: {', '.join(sorted(BLOCKING_KEYS))}"
        )
    return declared


## The built-in vocabulary, for callers that state no declaration.
_BUILT_IN = None


## @brief The built-in vocabulary, built once.
## @return The vocabulary.
## @version 1
## @dg_internal
def _built_in() -> BlockingVocabulary:
    """@brief Built-in vocabulary. @return It."""
    global _BUILT_IN
    if _BUILT_IN is None:
        _BUILT_IN = BlockingVocabulary()
    return _BUILT_IN


## @brief Classify one timeout argument's text.
## @param operand The argument text as written, or "" when the pattern takes none.
## @param has_timeout Whether the pattern declares a timeout argument at all.
## @param vocab The build's vocabulary, or None for the built-ins.
## @return A BLOCKING_WAIT member.
## v2 (2.0.0, C1): the wait tokens come from the vocabulary (built-ins plus a declaration).
## @version 2
## @dg_internal
def classify_wait(operand: str, has_timeout: bool, vocab: BlockingVocabulary | None = None) -> str:
    """Read off the TEXT, never off the callee name: the same primitive is legal or illegal in
    an interrupt depending on this one argument.

    @brief Classify a wait argument.
    @return The wait class.
    @version 1
    """
    vocab = vocab or _built_in()
    if not has_timeout:
        return WAIT_UNCONDITIONAL
    token = operand.replace(" ", "")
    if not token:
        return WAIT_UNDECIDABLE
    if token in vocab.none_tokens:
        return WAIT_NONE
    if token in vocab.forever_tokens:
        return WAIT_FOREVER
    if token.startswith(vocab.bounded_prefixes):
        return WAIT_BOUNDED
    if token.isdigit():
        return WAIT_NONE if int(token) == 0 else WAIT_BOUNDED
    return WAIT_UNDECIDABLE


## @brief Whether a condition CALLS an ISR predicate (a whole name followed by `(`).
## @param text Condition or operand text.
## @return True when a predicate is called in it.
## @version 1
## @dg_internal
def _names_isr_predicate(text: str, vocab: BlockingVocabulary | None = None) -> bool:
    """A SUBSTRING IS NOT A CALL (agent C's W7): `in_irq` sits inside `within_irq_window(dev)`, and
    reading that as a guard downgraded a real blocking-in-ISR conflict to "guarded".

    @brief Predicate call.
    @return Bool.
    """
    return (vocab.isr_call if vocab else _ISR_CALL).search(text) is not None


## @brief The nearest enclosing condition text for a node, up to a few levels.
## @param node The call node.
## @param src The file's raw bytes.
## @return The condition source text, or "".
## @param vocab The build's vocabulary, or None for the built-ins.
## v2 (W7): a predicate counts only when CALLED (`_names_isr_predicate`).
## v3 (2.0.0, C1): the predicates come from the vocabulary.
## @version 3
## @dg_internal
def _enclosing_condition(node: Any, src: bytes, vocab: BlockingVocabulary | None = None) -> str:
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
        if _names_isr_predicate(text, vocab):
            return text
        current = statement
    return ""


## @brief Harvest one file's blocking-primitive call sites.
## @param tree The parsed tree.
## @param src_bytes The file's raw bytes.
## @param patterns_by_name Blocking patterns keyed by callee name.
## @return A list of [primitive, line, wait, wait_operand, guard] records.
## @param vocab The build's vocabulary (predicates, wait tokens), or None for the built-ins.
## v3 (W7): a guard in the operand counts only when a predicate is CALLED.
## v4 (2.0.0, C1): predicates and wait tokens from the vocabulary.
## @version 4
## @req REQ-DDB-SCHEMA-011
def walk_blocking_sites(
    tree: Any, src_bytes: bytes, patterns_by_name: dict, vocab: BlockingVocabulary | None = None
) -> list[list[Any]]:
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
        ## A COMMENT IS A NAMED CHILD. tree-sitter-c makes `comment` an extra, so
        ## `xEventGroupWaitBits(eg, BIT0, /* xClearOnExit */ pdTRUE, pdFALSE, portMAX_DELAY)`
        ## shifts every argument after it by one and the timeout index lands on `pdFALSE` — a
        ## zero token — which classifies a K_FOREVER wait as legal in an interrupt and drops the
        ## conflict silently. Vendor headers and demo code comment their arguments constantly.
        named = (
            [child for child in arguments.named_children if child.type != "comment"]
            if arguments is not None
            else []
        )
        operand = ""
        if pattern.timeout_arg_index is not None and len(named) > pattern.timeout_arg_index:
            argument = named[pattern.timeout_arg_index]
            operand = src_bytes[argument.start_byte : argument.end_byte].decode(
                "utf-8", errors="replace"
            )
        guard = _enclosing_condition(node, src_bytes, vocab)
        ## THE GUARD CAN LIVE IN THE ARGUMENT ITSELF. Zephyr's power-management path writes
        ## `k_sem_take(&pm->lock, k_is_in_isr() ? K_NO_WAIT : K_FOREVER)`
        ## (subsys/pm/device_runtime.c:71) — ten interrupt handlers reach it.
        if not guard and _names_isr_predicate(operand, vocab):
            guard = operand
        sites.append(
            [
                name,
                node.start_point[0] + 1,
                classify_wait(operand, pattern.timeout_arg_index is not None, vocab),
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
    ## v2 (2.0.0, C1): and the vocabulary.
    ## @version 2
    ## @dg_internal
    def __init__(
        self, patterns_by_name: dict, extra_key: str = "", vocab: BlockingVocabulary | None = None
    ) -> None:
        super().__init__(extra_key)
        self.patterns_by_name = patterns_by_name
        self.vocab = vocab

    ## @brief Harvest one file's blocking call sites.
    ## @return List of site records.
    ## v2 (2.0.0, C1): reads with the vocabulary.
    ## @version 2
    ## @req REQ-DDB-SCHEMA-011
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return walk_blocking_sites(tree, src_bytes, self.patterns_by_name, self.vocab)


## @brief The blocking harvester a repository's own `.clew.yaml` configures.
## @param repo_root The repository.
## @return The harvester (built-in vocabulary when nothing is declared or the file is unreadable).
## @version 1
## @dg_internal
def declared_blocking_harvester(repo_root: Path) -> Harvester:
    """THE FAST TIER'S CONSTRUCTION SITE (2.0.0, C1): it must read an edited file with the same
    vocabulary the full build used, or a save would drop the declared sites of that file. A
    declaration that cannot be read falls back to the built-ins here; the full build refuses it.

    @brief Harvester from the declaration.
    @return Harvester.
    """
    from .declaration import load_declaration
    from .vocabulary import DeclarationError

    try:
        declared = load_declaration(repo_root).get("blocking")
    except DeclarationError:
        declared = None
    return blocking_harvester(declared if isinstance(declared, dict) else None)


## @brief The blocking-call stage's harvester.
## @param declared The `blocking:` section, or None.
## @return A Harvester over the built-in blocking primitives plus any declared ones.
## v2 (2.0.0, R5-CORE C1): a declared vocabulary accumulates over the built-ins.
## @version 2
## @req REQ-DDB-SCHEMA-011
def blocking_harvester(declared: dict | None = None) -> Harvester:
    """THE DECLARATION IS IN THE CACHE KEY (`manifest_key`), so a payload harvested with the
    built-in vocabulary is never served for a declared one. With nothing declared the key is the
    built-in one and every cached payload still applies.

    @brief Build this stage's harvester.
    @return The harvester.
    @version 2
    """
    from .treescan import manifest_key

    vocab = BlockingVocabulary(declared)
    return _BlockingHarvester(vocab.patterns_by_name, manifest_key(declared or None), vocab)


## @brief Create the blocking_calls table.
## @param conn Open connection.
## @return None.
## @version 2
## @req REQ-DDB-SCHEMA-011
def ensure_blocking_table(conn: sqlite3.Connection) -> None:
    """Created unconditionally, like the lock tables, so a repository with no blocking call
    yields an EMPTY table rather than an absent one and no
    consumer has to branch on existence.

    @brief Create blocking_calls if it does not exist.
    @return None.
    @version 2
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
## @version 3
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
    @version 2
    """
    from .call_edges import _ast_caller_at_line, _build_function_indexes

    conn = sqlite3.connect(str(db_path))
    ensure_blocking_table(conn)
    _name_to_rowids, file_funcs = _build_function_indexes(conn)
    harvester = harvester or blocking_harvester()
    inserted = 0
    for path_rowid, payload in run_harvest(conn, repo_root, harvester, cache):
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
    waits = dict(conn.execute("SELECT wait, COUNT(*) FROM blocking_calls GROUP BY wait").fetchall())
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
