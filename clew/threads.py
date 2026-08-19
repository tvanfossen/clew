# SPDX-License-Identifier: MIT
"""R1 thread layer: spawn-site harvest, membership closure, boundary flags.

Three cooperating stages, all keyed on the same tree-sitter AST toolkit the
call-graph layers already use (`call_edges._ast_parse_one_file`,
`shared_key_edges._nth_call_argument` + `_resolve_literal_key` +
`_definition_preferring_name_index`):

  1. `extract_threads` — walk every indexed C/C++ file, key on the callee
     identifier of a spawn call, read the entry-fn identifier (and, when the
     convention carries one, the thread name literal) at fixed argument
     indices, and file a `threads` row. Primitive spawn shapes
     (`pthread_create`/`xTaskCreate`/`osThreadNew`) ship as
     `DEFAULT_SPAWN_PATTERNS` (POSIX/FreeRTOS/CMSIS zero-config); repo-specific
     spawn wrappers (`SYSTEM_TASKCREATE`, `svc_start_task`, ...) are
     added via an optional `--thread-patterns` YAML, mirroring the accessor and
     data-model manifest philosophy. Threads are `source='ast_spawn'`,
     `confidence='medium'`. The same pass then computes `thread_membership` as
     a per-entry forward BFS over `call_edges` (non-fuzzy) — REUSING
     `reachability._bfs_live_set`'s shape but writing a DIFFERENT table, so the
     call-edges-only liveness contract in `mark_reachability` is untouched.
     Spawn-is-not-a-call (a spawn primitive is unindexed libc, never a
     `call_edges` callee), so a BFS from entry A never leaks into entry B
     unless B is genuinely called — closures stay separated at spawn points.

  2. `annotate_thread_boundaries` — UPDATE `shared_key_edges.crosses_thread` /
     `to_thread_id` from the membership map. A hop crosses a thread boundary
     when the writer and reader share NO common thread; `to_thread_id` is set
     only when the reader's thread is unambiguous (exactly one). Both stay NULL
     when either endpoint has no thread membership (insufficient data — never
     guessed).

The `threads` / `thread_membership` tables are ALWAYS created (empty when no
spawns are found or tree_sitter is absent), so R2/R4 never branch on table
existence — the `requirements.py` precedent.

@brief Thread spawn harvest, membership closure, and shared-key boundary flags.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .declaration import SECTION_THREADS
from .harvest import Harvester, enclosing, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .pyast import (
    PyBindings,
    class_ranges,
    collect_bindings,
    dotted_name,
    enclosing_class,
    entry_names,
    is_python_tree,
    keyword_argument,
    positional_argument,
    string_value,
)
from .reachability import _bfs_live_set
from .shared_key_edges import (
    _definition_preferring_name_index,
    _ensure_shared_key_edges_table,
    _nth_call_argument,
    _resolve_literal_key,
)
from .treescan import manifest_key
from .vocabulary import (
    STAGE_THREADS,
    THREAD_KIND,
    THREAD_KIND_COROUTINE,
    THREAD_KIND_PROCESS,
    THREAD_KIND_WIN32,
    check,
    declaration_origin,
)

## The scope separators that qualify an entry-function name, per language. C++
## uses `::`; doxygen records a Python method's `definition` as a fully DOTTED
## path (`clew.threads._SpawnHarvester.harvest` — verified against a
## real self-index), so `.` is what delimits a Python class from its method.
SCOPE_SEP_CPP = "::"
SCOPE_SEP_PY = "."


## @brief One spawn-call convention: callee name + entry/name arg indices + kind.
## @version 1
class SpawnPattern:
    """One thread-spawn convention: a callee identifier keyed against
    call sites, the 0-indexed position of the entry-function argument, an
    optional 0-indexed position of a thread-name string literal (None when
    the convention carries no name — e.g. `pthread_create`), and the
    `threads.kind` to stamp on matches.

    @brief Thread-spawn call convention (callee + arg indices + kind).
    @version 1
    """

    __slots__ = (
        "entry_arg_index",
        "entry_kwarg",
        "kind",
        "name",
        "name_arg_index",
        "name_kwarg",
    )

    ## @brief Store the callee name, entry/name arg positions, and thread kind.
    ## @param name Callee identifier (C) or fully-qualified dotted name (Python).
    ## @param entry_arg_index 0-based POSITIONAL index of the entry-function argument.
    ## @param name_arg_index 0-based positional index of a thread-name literal, or None.
    ## @param kind The `threads.kind` to stamp on matches.
    ## @param entry_kwarg Keyword that carries the entry function, when the convention has one.
    ## @param name_kwarg Keyword that carries the thread name, when the convention has one.
    ## @version 2
    ## @dg_internal
    def __init__(
        self,
        name: str,
        entry_arg_index: int,
        name_arg_index: int | None,
        kind: str,
        entry_kwarg: str | None = None,
        name_kwarg: str | None = None,
    ) -> None:
        self.name = name
        self.entry_arg_index = entry_arg_index
        self.name_arg_index = name_arg_index
        self.kind = kind
        # Python passes the entry by KEYWORD essentially always (`target=`), so a
        # positional index alone would miss every real site. The keywords are
        # None for every C/C++ primitive, where the convention is positional, so
        # nothing in the existing path consults them.
        self.entry_kwarg = entry_kwarg
        self.name_kwarg = name_kwarg


# Primitive spawn shapes — repo-independent, so zero-config coverage of
# POSIX / FreeRTOS / CMSIS-RTOS / C++ std threads. Repo wrappers
# (SYSTEM_TASKCREATE, svc_start_task, sys_thread_create, ...)
# forward a param and are repo-specific → declared via --thread-patterns (see
# load_thread_patterns). `std::thread`/`std::jthread` are C++ LANGUAGE
# primitives, not a repo convention, so they ship as defaults exactly like
# pthread_create; their callee is a qualified_identifier and their entry arg is
# a `&Class::method` member-function pointer, both handled in _walk_spawn_sites.
DEFAULT_SPAWN_PATTERNS: list[SpawnPattern] = [
    # pthread_create(&tid, attr, entry_fn, arg) — no thread name.
    SpawnPattern("pthread_create", entry_arg_index=2, name_arg_index=None, kind="pthread"),
    # xTaskCreate(entry_fn, "name", stack, param, prio, &handle).
    SpawnPattern("xTaskCreate", entry_arg_index=0, name_arg_index=1, kind="task"),
    # osThreadNew(entry_fn, arg, attr) — CMSIS-RTOS v2; no plain-literal name.
    SpawnPattern("osThreadNew", entry_arg_index=0, name_arg_index=None, kind="task"),
    # std::thread(entry_fn, args...) / std::jthread(...) — assignment or
    # direct-init call form; entry is arg 0, no name argument.
    SpawnPattern("std::thread", entry_arg_index=0, name_arg_index=None, kind="pthread"),
    SpawnPattern("std::jthread", entry_arg_index=0, name_arg_index=None, kind="pthread"),
    # Rust: std::thread::spawn(entry_fn_or_closure) — a real OS thread, entry
    # arg 0, no name argument (`Builder::name` is a separate, declarable
    # convention if a repo uses it — not modeled here, same "language
    # primitive only" scope as the C/C++ entries above). BOTH spellings are
    # matched, keyed by the callee's FULL qualified text exactly as
    # "std::thread" is above: `use std::thread;` then `thread::spawn(...)` is
    # at least as common as writing the fully-qualified path, and this
    # matcher does no import-alias resolution (same limitation the C/C++
    # entries already accept — see _walk_spawn_sites).
    SpawnPattern("std::thread::spawn", entry_arg_index=0, name_arg_index=None, kind="pthread"),
    SpawnPattern("thread::spawn", entry_arg_index=0, name_arg_index=None, kind="pthread"),
    # WINDOWS. Absent entirely until now, which is not a small gap: a Win32 codebase's threads
    # were invisible while `_roster_meaning` told the reader to quote the count as the
    # repository's thread count. Measured on Mbed-TLS/mbedtls — 1 reported against 2 real, the
    # missing one being `_beginthread(TimerProc, 0, NULL)` at programs/test/benchmark.c:430.
    #
    # THE ENTRY INDEX IS NOT THE SAME FOR ALL THREE, and assuming it was would have been worse
    # than omitting them: harvesting `stack_size` as the entry produces a garbage thread row
    # rather than no row. Read off the documented signatures rather than recalled:
    #   _beginthread( start_address, stack_size, arglist )                       -> 0
    #   _beginthreadex( security, stack_size, start_address, arglist, ... )      -> 2
    #   CreateThread( lpThreadAttributes, dwStackSize, lpStartAddress, ... )     -> 2
    # index 0 is additionally confirmed against the real mbedtls call site above.
    #
    # None takes a thread NAME, so the row is named by its entry (see _resolve_spawn_site).
    # `&SecondThreadFunc` is the documented `_beginthreadex` idiom and `_named_entry` already
    # unwraps a pointer_expression, so no walker change is needed.
    SpawnPattern("_beginthread", entry_arg_index=0, name_arg_index=None, kind=THREAD_KIND_WIN32),
    SpawnPattern("_beginthreadex", entry_arg_index=2, name_arg_index=None, kind=THREAD_KIND_WIN32),
    SpawnPattern("CreateThread", entry_arg_index=2, name_arg_index=None, kind=THREAD_KIND_WIN32),
]

# Python's spawn primitives. Language/stdlib primitives exactly as pthread_create
# and std::thread are, so they ship as DEFAULTS with a declared override — not as
# a repo convention.
#
# Every `name` here is a FULLY-QUALIFIED dotted path, and the Python walker
# matches it against the callee RESOLVED through the file's own imports (see
# `pyast`). That is load-bearing, not stylistic: clew's own
# `query/symbols.py` constructs a dataclass called `Thread`, so a pattern keyed
# on the bare tail would fabricate a thread row there (and a second one in
# explorer's vendored copy). A dotted default can never match a bare callee.
#
# Positional indices come from the real signatures, read from the installed
# interpreter rather than recalled: `Thread(group=None, target=None, name=None,
# ...)` puts target at POSITION 1 and name at 2 (not 0 and 1);
# `run_in_executor(executor, func, *args)` puts the entry at 1; `submit(fn, ...)`
# and `create_task(coro, ...)` at 0.
DEFAULT_PY_SPAWN_PATTERNS: list[SpawnPattern] = [
    # A real OS thread — CPython on POSIX creates a pthread, so 'pthread' is
    # accurate rather than borrowed.
    SpawnPattern(
        "threading.Thread",
        entry_arg_index=1,
        name_arg_index=2,
        kind="pthread",
        entry_kwarg="target",
        name_kwarg="name",
    ),
    # A separate ADDRESS SPACE — see THREAD_KIND_PROCESS on why this is not
    # filed as a thread.
    SpawnPattern(
        "multiprocessing.Process",
        entry_arg_index=1,
        name_arg_index=2,
        kind=THREAD_KIND_PROCESS,
        entry_kwarg="target",
        name_kwarg="name",
    ),
    # Cooperative, on the SAME OS thread — 'coroutine', not 'pthread'.
    SpawnPattern(
        "asyncio.create_task",
        entry_arg_index=0,
        name_arg_index=None,
        kind=THREAD_KIND_COROUTINE,
        name_kwarg="name",
    ),
    SpawnPattern(
        "asyncio.ensure_future",
        entry_arg_index=0,
        name_arg_index=None,
        kind=THREAD_KIND_COROUTINE,
    ),
    SpawnPattern(
        "asyncio.TaskGroup.create_task",
        entry_arg_index=0,
        name_arg_index=None,
        kind=THREAD_KIND_COROUTINE,
        name_kwarg="name",
    ),
    # Pool work items. Reached only when the RECEIVER resolves to an executor
    # constructed in the same file (`with ThreadPoolExecutor() as ex`), so a
    # `self.submit(...)` or a `submit` on a function parameter never matches.
    SpawnPattern(
        "concurrent.futures.ThreadPoolExecutor.submit",
        entry_arg_index=0,
        name_arg_index=None,
        kind="task",
    ),
    SpawnPattern(
        "concurrent.futures.ProcessPoolExecutor.submit",
        entry_arg_index=0,
        name_arg_index=None,
        kind="task",
    ),
    SpawnPattern(
        "asyncio.AbstractEventLoop.run_in_executor",
        entry_arg_index=1,
        name_arg_index=None,
        kind="task",
    ),
]


## @brief Load --thread-patterns YAML, merged over the built-in defaults.
## @param path Path to the YAML file, or None to use only the defaults.
## @return Merged spawn-pattern list (loaded entries override defaults by name).
## @version 7
## @req REQ-DDB-SCHEMA-001
def load_thread_patterns(path: Path | dict | None) -> list[SpawnPattern]:
    """Merge an optional `--thread-patterns` YAML over `DEFAULT_SPAWN_PATTERNS`.

    Expected shape (mirrors the accessor/data-model manifests)::

        spawns:
          - name: "SYSTEM_TASKCREATE"
            entry_arg_index: 0
            name_arg_index: 1
            kind: "task"
          - name: "svc_start_task"
            entry_arg_index: 0
            name_arg_index: 1

    A loaded entry whose `name` matches a default replaces that default
    (override); other loaded entries are appended. `kind` defaults to
    `'task'`; `name_arg_index` is optional (None when omitted).

    An invalid declared `kind` raises `DeclarationError` naming the file, the
    token and the allowed set. It used to normalize to `'unknown'` with a
    warning; that is a fabrication — it labels a thread with an execution
    context its author never wrote, and the warning is one INFO-looking line in
    a several-hundred-line build log.

    @brief Merge declared spawn patterns over the built-in defaults.
    @version 5
    """
    merged: dict[str, SpawnPattern] = {
        p.name: p for p in (*DEFAULT_SPAWN_PATTERNS, *DEFAULT_PY_SPAWN_PATTERNS)
    }
    if path is None:
        return list(merged.values())
    if isinstance(path, dict):
        data = path
    else:
        import yaml

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    origin = declaration_origin(path, SECTION_THREADS)
    for entry in data.get("spawns", []) or []:
        name = entry.get("name")
        if not name:
            continue
        name_arg = entry.get("name_arg_index")
        entry_kwarg = entry.get("entry_kwarg")
        name_kwarg = entry.get("name_kwarg")
        merged[name] = SpawnPattern(
            name=name,
            entry_arg_index=int(entry.get("entry_arg_index", 0)),
            name_arg_index=None if name_arg is None else int(name_arg),
            kind=THREAD_KIND.validated(
                str(entry.get("kind", "task")),
                owner=f"{origin}: spawn pattern {name!r}",
                field="kind",
            ),
            entry_kwarg=None if entry_kwarg is None else str(entry_kwarg),
            name_kwarg=None if name_kwarg is None else str(name_kwarg),
        )
    return list(merged.values())


## @brief Create threads + thread_membership tables (+ indexes) if absent.
## @version 6
## @req REQ-DDB-SCHEMA-001
## @req REQ-DDB-SCHEMA-007
## @req REQ-DDB-QUERY-011
def _ensure_threads_tables(conn: sqlite3.Connection) -> None:
    """Create the `threads` and `thread_membership` tables and their
    indexes if they don't already exist. Always run (even when no spawns
    are found) so consumers never branch on table existence.

    `kind` JOINED the UNIQUE key (was `(name, entry_memberdef_rowid)`). Two
    spawns of the SAME entry through DIFFERENT primitives are two execution
    contexts, not one — and the old key silently kept whichever the AST walk
    popped first. Measured on the committed Python fixture: `worker` is spawned
    as `threading.Thread`, `multiprocessing.Process`, `asyncio.create_task` and
    a pool `submit`; all four fall back to the same qualified-entry name, three
    were discarded, and the survivor's `kind` was `task` purely because
    tree-sitter's DFS pops the last statement first. `kind` is exactly the column
    a consumer reads to decide whether two functions can race, so answering it
    from walk order is a wrong answer, not a missing one. Repeat spawns of one
    entry through ONE primitive still collapse, which is the dedup the key was
    added for (a `for i in ...: Thread(target=w, name="rx").start()` loop stays
    one row).

    THE SPAWN SITE IS RECORDED (gh#346), and it is what makes a thread ATTRIBUTABLE. A thread
    row used to be anchored only to its ENTRY symbol, which is legitimately NULL: the entry NAME
    is read off the spawn call, but `_insert_threads` refuses to resolve it when a
    member-function pointer names a class this index does not cover, or when a bare name is not
    uniquely indexed. A row with no entry has no file, so it cannot be tagged external, so a
    submodule's threads counted as FIRST PARTY. That inflates the one figure gh#335's invariance
    control rests on. Measured on entropic: 12 rows, 4 resolving into entropic, 6 into the
    submodule, and 2 to no file at all — those 2 being exactly the mis-attributed ones.

    (A multi-call lambda produces NO ROW rather than a NULL-entry row — that limitation is real
    but it is a DIFFERENT one, and stating it here as the source of NULL entries would send the
    next reader to the wrong mechanism. Checked against
    `test_extract_threads_std_thread_multicall_lambda_fail_closed`, which asserts zero rows.)

    THE SPAWN SITE ALWAYS HAS A FILE, because it is where the spawn construct was MATCHED, and
    it answers the question the tag actually asks: where is this thread CREATED. The entry
    symbol answers a different question — what the thread RUNS — and that one is sometimes
    unknowable. So this is the right anchor rather than a workaround for a NULL.

    IT IS DELIBERATELY NOT IN THE UNIQUE KEY. Adding it would un-collapse the loop case the key
    exists to collapse. When one entry is spawned through one primitive from several sites, the
    FIRST in path order wins — deterministic, because `run_harvest` walks paths in order, but
    still one site standing for several. `_insert_threads` says so.

    @brief Idempotent threads/thread_membership table creation.
    @version 5
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS threads (
            id                    INTEGER PRIMARY KEY,
            name                  TEXT NOT NULL,
            entry_memberdef_rowid INTEGER REFERENCES memberdef(rowid),
            kind                  TEXT NOT NULL {check("threads", "kind")},
            source                TEXT NOT NULL {check("threads", "source")},
            confidence            TEXT NOT NULL {check("threads", "confidence")},
            spawn_path_rowid      INTEGER REFERENCES path(rowid),
            spawn_line            INTEGER,
            -- WHO creates the thread, as TEXT. `spawn_path_rowid` + `spawn_line` say where; this
            -- says the name an agent can ask a follow-up about. Not a memberdef reference, because
            -- a spawn commonly sits in a function doxygen emitted no row for (a `static` helper in
            -- a sample program is exactly the mbedtls case), and requiring a rowid would drop the
            -- row this column exists to serve.
            spawn_function        TEXT,
            UNIQUE(name, entry_memberdef_rowid, kind)
        )
        """,
    )
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS thread_membership (
            memberdef_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            thread_id       INTEGER NOT NULL REFERENCES threads(id),
            source          TEXT NOT NULL {check("thread_membership", "source")},
            UNIQUE(memberdef_rowid, thread_id)
        )
        """,
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_thread_membership_thread ON thread_membership(thread_id)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_thread_membership_member "
        "ON thread_membership(memberdef_rowid)",
    )
    conn.commit()


## @brief One harvested spawn site: thread name, entry-fn name, kind.
## @version 1
class _SpawnSite:
    """A single resolved spawn call: the thread's name, the entry function's
    identifier (as text — rowid resolution happens later), and the kind.

    @brief A resolved thread-spawn call site.
    @version 1
    """

    __slots__ = (
        "entry_name",
        "kind",
        "line",
        "name",
        "path_rowid",
        "qualified_entry",
        "separator",
        "spawn_function",
    )

    ## @brief Store the resolved thread name, entry-fn name, kind, qualified entry and separator.
    ## @param name The thread's name (a declared literal, else the qualified entry).
    ## @param entry_name The entry function's bare tail name.
    ## @param kind The `threads.kind` for this spawn.
    ## @param qualified_entry `Class::method` (C++) or `Class.method` (Python); defaults to entry_name.
    ## @param separator The scope separator delimiting `qualified_entry`.
    ## @param line 1-based line of the spawn call, or None when an older cached payload omitted it.
    ## @param path_rowid The spawning file's `path` rowid, filled in by the harvest flattener.
    ## @param spawn_function The name of the function the spawn call sits in, "" at file scope.
    ## @version 5
    ## @dg_internal
    def __init__(
        self,
        name: str,
        entry_name: str,
        kind: str,
        qualified_entry: str = "",
        separator: str = SCOPE_SEP_CPP,
        line: int | None = None,
        path_rowid: int | None = None,
        spawn_function: str = "",
    ) -> None:
        self.name = name
        self.entry_name = entry_name
        self.kind = kind
        ## WHO CREATES THE THREAD, which is not the same question as what the thread RUNS and was
        ## not answerable at all. A row carried `spawn_path_rowid` + `spawn_line`, so an agent
        ## could be told a thread is spawned at `programs/ssl/ssl_pthread_server.c:277` and still
        ## have no NAME to ask a follow-up about. Measured on mbedtls 2026-08-14: the enclosing
        ## function is `thread_create`, whose body holds the shared state, the `pthread_join`, and
        ## the guard — four graded marks — and `dossier('thread_create')` returns all of it. The
        ## only missing thing was a route from the thread row to that name, so the agent read the
        ## file instead.
        ##
        ## A NAME AND NOT A ROWID, deliberately. A spawn can sit in a function doxygen never
        ## emitted a `memberdef` for (a `static` helper in a program, exactly this case), so
        ## requiring a resolvable rowid would drop the row this exists to serve — the same
        ## fail-open trap `entry_name` avoids by being text.
        self.spawn_function = spawn_function
        # WHERE the spawn was matched, which is the anchor the external tag reads (gh#346). The
        # LINE comes from the AST node during the per-file walk; the PATH ROWID cannot, because
        # the walk is handed only a tree and its bytes — `run_harvest` is what knows which file
        # produced them, so the flattener fills it in. Both stay None only on a payload cached
        # by an older stage_version.
        self.line = line
        self.path_rowid = path_rowid
        # The `Class::method` form when the entry was a member pointer; else ==
        # entry_name. Used for exact-overload rowid resolution in _insert_threads.
        self.qualified_entry = qualified_entry or entry_name
        # Which separator qualifies the entry — `::` for C++, `.` for Python.
        # Carried per-site rather than sniffed, because `.` is AMBIGUOUS in C: an
        # entry argument `cfg.handler` (a struct field holding a function
        # pointer) also contains a dot, and treating that as a scope-qualified
        # name would send it down the `definition`-matching path and change the C
        # result. The site knows which language produced it; the resolver must not
        # guess.
        self.separator = separator


## @brief Text of a node's trailing simple name (identifier / qualified / field tail).
## @return The bare trailing name for an identifier, qualified_identifier (`a::b::c`->`c`) or field_expression (`this->m`->`m`), else None.
## @version 4
## @dg_internal
def _tail_identifier(node: Any, src_bytes: bytes) -> str | None:
    """Reduce a callee/entry node to its bare trailing name by first resolving
    WHICH node actually holds that name, then decoding once. Splitting the
    resolution from the decode keeps one exit here.

    @brief Return the bare trailing name of an identifier/qualified/field node.
    @version 4
    """
    named = _tail_identifier_node(node)
    if named is None:
        return None
    return src_bytes[named.start_byte : named.end_byte].decode("utf-8", errors="replace")


## @brief The node holding the trailing simple name, for the shapes we accept.
## @param node Candidate identifier / field_expression / qualified_identifier.
## @return The node whose text is the bare name, or None when there is none.
## @version 2
## @dg_internal
def _tail_identifier_node(node: Any) -> Any:
    """`this->run_loop` puts the name in the `field` child; `a::b::c` nests
    qualified_identifier until the final segment. Anything else has no simple
    trailing name and is refused rather than guessed at.

    `scoped_identifier` is Rust's own qualified-path node (`Type::method`,
    `module::func`) — its tail field is spelled the same ("name") as C++'s
    `qualified_identifier`, so `_qualified_tail` (generalized to walk either
    node type) handles both.

    @brief Locate the node carrying a trailing simple name.
    @return The naming node, or None.
    @version 2
    """
    handlers = {
        "identifier": lambda n: n,
        "field_identifier": lambda n: n,
        "field_expression": lambda n: n.child_by_field_name("field"),
        "qualified_identifier": _qualified_tail,
        "scoped_identifier": _qualified_tail,
    }
    handler = handlers.get(node.type)
    return handler(node) if handler is not None else None


## @brief Walk a nested qualified_identifier/scoped_identifier to its final segment.
## @param node A `qualified_identifier` (`a::b::c`) or Rust `scoped_identifier` node.
## @return The trailing identifier node, or None when it is not a simple name.
## @version 2
## @dg_internal
def _qualified_tail(node: Any) -> Any:
    """@brief Descend `a::b::c` to `c`, refusing anything not a simple name."""
    cur = node
    while cur is not None and cur.type in ("qualified_identifier", "scoped_identifier"):
        nxt = cur.child_by_field_name("name")
        if nxt is None:
            break
        cur = nxt
    return cur if cur is not None and cur.type in ("identifier", "type_identifier") else None


## @brief The sole called function inside a lambda body, if there is exactly one.
## @param lambda_node A `lambda_expression` AST node.
## @param src_bytes The file's raw source bytes.
## @return The trailing name of the single call's callee, or None when the body has zero or several calls (ambiguous ⇒ fail-closed).
## @version 2
## @dg_internal
def _lambda_single_call_entry(lambda_node: Any, src_bytes: bytes) -> str | None:
    """Capture the ubiquitous `std::thread([this]{ method(); })` idiom: a lambda
    whose body contains EXACTLY ONE call is that thread's entry. More than one
    call is ambiguous (which is the loop?) and stays fail-closed, so a thread is
    never attributed to an arbitrary helper (e.g. a leading `sleep()`).

    @brief Resolve a single-call lambda body to its callee name.
    @version 1
    """
    calls = _lambda_body_calls(lambda_node)
    if len(calls) != 1:
        return None
    callee = calls[0].child_by_field_name("function")
    return _tail_identifier(callee, src_bytes) if callee is not None else None


## @brief Call expressions in a lambda body, stopping once ambiguity is certain.
## @param lambda_node A `lambda_expression` AST node.
## @return The body's call nodes; at most two, since two already means ambiguous.
## @version 1
## @dg_internal
def _lambda_body_calls(lambda_node: Any) -> list[Any]:
    """Collecting at most two is deliberate: the caller only needs to know
    "exactly one" versus "not exactly one", so the walk stops as soon as a
    second call proves ambiguity.

    @brief Collect a lambda body's call expressions (capped at two).
    @return List of call nodes.
    @version 1
    """
    body = lambda_node.child_by_field_name("body")
    calls: list[Any] = []
    stack = [body] if body is not None else []
    while stack and len(calls) < 2:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == "call_expression":
            calls.append(node)
    return calls


## @brief Resolve an entry argument to (qualified, bare-tail) function names.
## @return (qualified_text, tail_name) for identifier / qualified_identifier / &-member-pointer / single-call lambda or closure, else None.
## @version 5
## @dg_internal
def _entry_names(call_node: Any, index: int, src_bytes: bytes) -> tuple[str, str] | None:
    """Read the entry-function argument, unwrapping a `pointer_expression`
    (`&Class::method`) and reading a `qualified_identifier` down to its tail, OR
    a `lambda_expression`/Rust `closure_expression` whose body is a single call
    (`[this]{ poll_loop(); }`, `|| { poll_loop(); }` — the ubiquitous
    modern-C++/Rust thread idiom) down to that callee. Returns the qualified
    text (`Class::method`, used to name the thread and resolve the exact
    overload) and the bare tail (`method`, the name-index fallback); for a
    lambda/closure both are the called function's name. Anything else — a bare
    name it is not, a multi-call body — is not AST-resolvable, fail-closed None.

    Rust's `closure_expression` shares `lambda_expression`'s field name
    ("body") for its body, so `_lambda_single_call_entry`/`_lambda_body_calls`
    need no separate Rust path — only this dispatch needed to recognize the
    node type.

    @brief Extract (qualified, tail) entry-function names from a spawn arg.
    @version 4
    """
    arg = _nth_call_argument(call_node, index)
    if arg is not None and arg.type in ("lambda_expression", "closure_expression"):
        name = _lambda_single_call_entry(arg, src_bytes)
        return (name, name) if name else None
    return _named_entry(arg, src_bytes)


## @brief (qualified, tail) names for a NON-lambda entry argument.
## @param arg The spawn call's entry argument, or None.
## @param src_bytes The file's raw source bytes.
## @return (qualified text, bare tail), or None when the arg names no function.
## @version 1
## @dg_internal
def _named_entry(arg: Any, src_bytes: bytes) -> tuple[str, str] | None:
    """Unwraps `&Class::method` to the inner name before reading it, so the
    qualified text used to name the thread does not carry the `&`.

    @brief Read a named entry argument's qualified + tail names.
    @return (qualified, tail) or None.
    @version 1
    """
    if arg is None:
        return None
    if arg.type == "pointer_expression":
        inner = next(
            (c for c in arg.named_children if c.type in ("identifier", "qualified_identifier")),
            None,
        )
        arg = inner if inner is not None else arg
    tail = _tail_identifier(arg, src_bytes)
    qualified = src_bytes[arg.start_byte : arg.end_byte].decode("utf-8", errors="replace")
    return (qualified, tail) if tail is not None else None


## @brief Resolve one spawn call site into a _SpawnSite, if it resolves.
## @version 3
## @dg_internal
def _resolve_spawn_site(
    call_node: Any,
    src_bytes: bytes,
    pattern: SpawnPattern,
) -> _SpawnSite | None:
    """Extract the entry-fn name (required) and thread-name literal (optional
    per convention) from one matched spawn call. The thread name is the name
    literal when the convention carries one, else the entry function's
    QUALIFIED name (`Class::method`), which distinguishes two threads sharing a
    bare entry name (`LinkOwner::rx_loop` vs `SensorRuntime::rx_loop`). The
    bare tail rides along for name-index fallback resolution. Returns None when
    the entry argument isn't an (optionally &-prefixed) plain/qualified name.

    @brief Resolve a matched spawn call into name + entry + kind.
    @version 2
    """
    names = _entry_names(call_node, pattern.entry_arg_index, src_bytes)
    if names is None:
        return None
    qualified_entry, entry_tail = names
    thread_name: str | None = None
    if pattern.name_arg_index is not None:
        name_arg = _nth_call_argument(call_node, pattern.name_arg_index)
        if name_arg is not None:
            thread_name = _resolve_literal_key(name_arg, src_bytes)
    if not thread_name:
        thread_name = qualified_entry
    return _SpawnSite(thread_name, entry_tail, pattern.kind, qualified_entry)


## @brief The name of the function a node sits inside, or "" at file scope.
## @param node The AST node to walk up from.
## @param src The file's raw bytes.
## @return The enclosing function's declarator name, or "" when there is none.
## @version 2
## @dg_internal
def _enclosing_function_name(node: Any, src: bytes) -> str:
    """REUSES `harvest.enclosing` and `locks.py`'s declarator-text reading rather than adding a
    third way to answer "which function is this in". Those two already agree, and a spawn site's
    enclosing function is the same question a lock site's scope asks.

    THE DECLARATOR TEXT UP TO THE FIRST `(`, which handles the shapes that matter without
    special-casing them: `thread_create` in C, `Owner::run` for an out-of-line C++ method, and
    `*make_thread` for a pointer return (the sigil sits INSIDE the declarator — the trap that
    split one entropic mutex into two lock rows). Leading `*&` and whitespace are stripped for
    that reason.

    EMPTY AT FILE SCOPE rather than a placeholder, so a spawn in a static initialiser reads as
    "no enclosing function" instead of naming one that does not exist.

    `function_item` is Rust's own function node (tree-sitter-rust never uses
    `function_definition`), with its name under the same "name" field
    `function_definition` uses in Python — so it needs only adding to the
    search set, not a second name-reader.

    @brief Name the function containing a node.
    @return The name, or "".
    @version 2
    """
    fn = enclosing(node, ("function_definition", "function_item"))
    if fn is None:
        return ""
    ## BOTH GRAMMARS THROUGH ONE HELPER. `function_definition` is the node type in
    ## tree-sitter-c/cpp AND tree-sitter-python, but the name hangs off a different field:
    ## `declarator` there, `name` here. The Python walk's own comment already warns that two
    ## arities would be "two places for the spawn site to go missing, and only one of them would
    ## have a test" — the same argument applies to two name-readers, so there is one.
    named = fn.child_by_field_name("declarator") or fn.child_by_field_name("name")
    if named is None:
        return ""
    text = src[named.start_byte : named.end_byte].decode("utf-8", errors="replace")
    return text.split("(")[0].strip().lstrip("*& \t")


## @brief Walk one parsed file, harvesting spawn call sites.
## @return List of [thread_name, entry_name, kind, qualified_entry, separator, spawn_line, spawn_function] septets.
## @version 7
## @dg_internal
def _walk_spawn_sites(
    tree: Any,
    src_bytes: bytes,
    patterns_by_name: dict[str, SpawnPattern],
) -> list[list[Any]]:
    """Iterative parse-tree walk keying every `call_expression`'s callee
    identifier against the spawn-pattern map. Spawn sites are already
    rowid-free (entry functions are recorded by NAME), so the harvest is
    directly cacheable — keyed additionally on the --thread-patterns content,
    which decides what matches at all.

    A Python tree is delegated to `_walk_py_spawn_sites`, whose matching rule is
    genuinely different (resolve the callee through the file's imports first) and
    whose entry argument is usually a keyword.

    @brief Harvest spawn call sites from one file's AST.
    @version 4
    """
    if is_python_tree(tree):
        return _walk_py_spawn_sites(tree, src_bytes, patterns_by_name)
    ## `Any` and not `str` since gh#346: the sixth element is the spawn LINE, an int. The payload
    ## is a heterogeneous positional row on its way through the cache, so annotating it `str`
    ## would be describing the shape it stopped having.
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call_expression":
            continue
        callee = node.child_by_field_name("function")
        # A plain-identifier callee (`pthread_create`) OR a qualified one
        # (`std::thread`, or Rust's `scoped_identifier` for `std::thread::spawn`
        # / `thread::spawn`) — the latter is matched by its full text so a
        # pattern keys on "std::thread", never a bare "thread" that would
        # false-match.
        if callee is None or callee.type not in (
            "identifier",
            "qualified_identifier",
            "scoped_identifier",
        ):
            continue
        callee_name = src_bytes[callee.start_byte : callee.end_byte].decode(
            "utf-8",
            errors="replace",
        )
        pattern = patterns_by_name.get(callee_name)
        if pattern is None:
            continue
        site = _resolve_spawn_site(node, src_bytes, pattern)
        if site is not None:
            sites.append(
                [
                    site.name,
                    site.entry_name,
                    site.kind,
                    site.qualified_entry,
                    site.separator,
                    ## The spawn CALL's own line, not the entry function's — the point of gh#346
                    ## is to record where the thread is created. `start_point` is 0-based.
                    node.start_point[0] + 1,
                    ## And WHO creates it. The line alone gave an agent a coordinate with no name
                    ## to ask a follow-up about, so it read the file instead.
                    _enclosing_function_name(node, src_bytes),
                ]
            )
    return sites


## @brief Walk one Python file, harvesting spawn call sites.
## @param tree The parsed Python tree.
## @param src_bytes The file's raw bytes.
## @param patterns_by_name Spawn patterns keyed by callee name.
## @return List of [thread_name, entry_name, kind, qualified_entry, separator, spawn_line, spawn_function] septets.
## @version 4
## @dg_internal
def _walk_py_spawn_sites(
    tree: Any,
    src_bytes: bytes,
    patterns_by_name: dict[str, SpawnPattern],
) -> list[list[Any]]:
    """Resolves each callee through the file's OWN import bindings before
    matching, so `threading.Thread`, `th.Thread` and `from threading import
    Thread` all match one dotted pattern while a same-named import from
    somewhere else (clew's own `Thread` dataclass) matches nothing.

    Raw callee text is tried ONLY when the name has no binding at all — a
    module-local spawn wrapper a repo declares in `--thread-patterns`. Every
    built-in default is a dotted stdlib path, so the raw fallback can never
    reach one, and an imported name never reaches it either.

    @brief Harvest Python spawn call sites via import-resolved callee names.
    @return Rowid-free spawn-site quints.
    @version 3
    """
    bindings = collect_bindings(tree, src_bytes)
    classes = class_ranges(tree, src_bytes)
    ## `Any`, not `str` — the sextet's last element is the spawn LINE. Same reason as the C++ walk.
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call":
            continue
        pattern = _py_matched_pattern(node, src_bytes, bindings, patterns_by_name)
        if pattern is None:
            continue
        site = _resolve_py_spawn_site(node, src_bytes, pattern, classes)
        if site is not None:
            sites.append(
                [
                    site.name,
                    site.entry_name,
                    site.kind,
                    site.qualified_entry,
                    site.separator,
                    ## Same sixth element as the C++ walk (gh#346), so ONE flattener folds both
                    ## payload shapes. Two arities here would be two places for the spawn site
                    ## to go missing, and only one of them would have a test.
                    node.start_point[0] + 1,
                    ## And the same SEVENTH, for the same reason. `_enclosing_function_name` reads
                    ## `name` here where the C grammar has `declarator`, so one helper serves both.
                    _enclosing_function_name(node, src_bytes),
                ]
            )
    return sites


## @brief The spawn pattern matching one Python call, if any.
## @param node A Python `call` node.
## @param src_bytes The file's raw bytes.
## @param bindings The file's import/receiver bindings.
## @param patterns_by_name Spawn patterns keyed by callee name.
## @return The matched SpawnPattern, or None.
## @version 1
## @dg_internal
def _py_matched_pattern(
    node: Any,
    src_bytes: bytes,
    bindings: PyBindings,
    patterns_by_name: dict[str, SpawnPattern],
) -> SpawnPattern | None:
    """@brief Match a Python callee (import-resolved, else raw) to a spawn pattern.

    @return Matched pattern or None.
    @version 1
    """
    dotted = dotted_name(node.child_by_field_name("function"), src_bytes)
    if dotted is None:
        return None
    resolved = bindings.resolve(dotted)
    # An unbound name falls back to raw text so a declared local wrapper matches;
    # a BOUND name does not, so an import from elsewhere is refused outright.
    return patterns_by_name.get(resolved if resolved is not None else dotted)


## @brief Resolve one matched Python spawn call into a _SpawnSite.
## @param node The matched `call` node.
## @param src_bytes The file's raw bytes.
## @param pattern The matched spawn pattern.
## @param classes Class byte ranges, to qualify a `self.method` entry.
## @return The resolved spawn site, or None when the entry is not resolvable.
## @version 1
## @dg_internal
def _resolve_py_spawn_site(
    node: Any,
    src_bytes: bytes,
    pattern: SpawnPattern,
    classes: list[tuple[int, int, str]],
) -> _SpawnSite | None:
    """The entry comes from the pattern's keyword when the call passes one
    (`target=`, the near-universal real form), else from its positional index.
    The thread name is a `name=` literal when present, else the QUALIFIED entry —
    so five classes' `target=self._run` become five distinct threads rather than
    one collision.

    @brief Resolve a matched Python spawn call into name + entry + kind.
    @return The spawn site, or None.
    @version 1
    """
    arg = _py_entry_argument(node, pattern)
    class_name = enclosing_class(classes, node.start_byte)
    names = entry_names(arg, src_bytes, class_name)
    if names is None:
        return None
    qualified_entry, entry_tail = names
    thread_name = _py_thread_name(node, src_bytes, pattern) or qualified_entry
    return _SpawnSite(thread_name, entry_tail, pattern.kind, qualified_entry, SCOPE_SEP_PY)


## @brief The entry-function argument node of a Python spawn call.
## @param node The `call` node.
## @param pattern The matched spawn pattern.
## @return The entry argument node, or None when the call passes none.
## @version 1
## @dg_internal
def _py_entry_argument(node: Any, pattern: SpawnPattern) -> Any | None:
    """@brief Read the entry argument by keyword, falling back to position.

    @return Argument node or None.
    @version 1
    """
    if pattern.entry_kwarg:
        by_keyword = keyword_argument(node, pattern.entry_kwarg)
        if by_keyword is not None:
            return by_keyword
    return positional_argument(node, pattern.entry_arg_index)


## @brief The declared thread-name literal of a Python spawn call, if any.
## @param node The `call` node.
## @param src_bytes The file's raw bytes.
## @param pattern The matched spawn pattern.
## @return The name literal, or None when the call names the thread nothing.
## @version 1
## @dg_internal
def _py_thread_name(node: Any, src_bytes: bytes, pattern: SpawnPattern) -> str | None:
    """A non-literal name (`name=f"rx-{i}"`) resolves to None and the caller falls
    back to the qualified entry, rather than recording a template as a name.

    @brief Read a Python spawn call's thread-name literal.
    @return The name, or None.
    @version 1
    """
    candidates = []
    if pattern.name_kwarg:
        candidates.append(keyword_argument(node, pattern.name_kwarg))
    if pattern.name_arg_index is not None:
        candidates.append(positional_argument(node, pattern.name_arg_index))
    for candidate in candidates:
        value = string_value(candidate, src_bytes) if candidate is not None else None
        if value:
            return value
    return None


## @brief The thread stage's cacheable per-file spawn harvester.
## @version 1
class _SpawnHarvester(Harvester):
    """Records `[thread_name, entry_name, kind]` triples per file.

    @brief Thread-spawn per-file harvester.
    @version 1
    """

    stage = STAGE_THREADS
    # Bump when _walk_spawn_sites' extraction changes. v2: payload gained the
    # qualified_entry field and std::thread/qualified-callee support. v3: payload
    # gained the scope SEPARATOR (a quint) and Python spawn primitives. v4: payload
    # gained the SPAWNING FUNCTION's name (a septet), so a thread row names who creates
    # it and not only where. The bump is what makes v3 payloads cold — they fold
    # tolerantly to "" rather than raising, but an index served from them would answer
    # the new question with silence, which is the state this field exists to remove.
    stage_version = 4
    label = "thread spawns"

    ## @brief Store the spawn-pattern map plus the manifest-derived cache key.
    ## @version 1
    ## @dg_internal
    def __init__(self, patterns_by_name: dict[str, SpawnPattern], extra_key: str) -> None:
        super().__init__(extra_key)
        self.patterns_by_name = patterns_by_name

    ## @brief Harvest one file's spawn call sites.
    ## @return List of [thread_name, entry_name, kind] triples.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-001
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return _walk_spawn_sites(tree, src_bytes, self.patterns_by_name)


## @brief The thread stage's harvester for one declared spawn vocabulary.
## @param thread_patterns_path Declared `threads:` section, a YAML path, or None.
## @return A Harvester keyed on the declaration's content hash.
## @version 1
## @req REQ-DDB-SCHEMA-001
def spawn_harvester(thread_patterns_path: Path | dict | None = None) -> Harvester:
    """The ONE construction site, so gh#358's shared parse pass and this stage key on
    the same `(stage, stage_version, extra_key)` by construction. A declaration that
    raises `DeclarationError` still raises — earlier in the build now, which is the
    right direction for a refusal.

    @brief Build this stage's harvester.
    @version 1
    """
    patterns = load_thread_patterns(thread_patterns_path)
    return _SpawnHarvester({p.name: p for p in patterns}, manifest_key(thread_patterns_path))


## @brief Harvest every spawn call site across all indexed files, each with its spawning file.
## @return Flat list of _SpawnSite in path order.
## @version 7
## @dg_internal
def _harvest_all_spawn_sites(
    conn: sqlite3.Connection,
    repo_root: Path,
    harvester: Harvester,
    ts_classes: tuple[Any, Any],
    cache: IndexCache | None = None,
) -> list[_SpawnSite]:
    """Drive the cached per-file harvest and flatten it back into _SpawnSite.

    A payload row is a SEPTET (…, separator, spawn line, spawning function); a shorter row from an older
    extraction still folds — as C++ when it lacks the separator, with no spawn line when it
    lacks that — rather than raising, mirroring how `_fold_call_payload` tolerates a legacy
    two-element call site. The stage_version bump makes those paths cold in practice.

    THIS IS WHERE THE PATH ROWID STOPS BEING THROWN AWAY (gh#346). `run_harvest` has always
    yielded it and this comprehension always discarded it as `_path_rowid`, so the spawning
    file was computed on every build and dropped — the same shape as the scope provenance
    gh#319 persisted and the macro hop doxygen was already emitting. The per-file walk cannot
    supply it (it sees only a tree and bytes), and it must not be re-derived from the entry
    symbol, because the entry is exactly what can be NULL.

    It now RECEIVES the harvester instead of rebuilding one from the patterns and a
    separately-passed `extra_key`: gh#358's shared parse pass builds it, warms the
    cache with it, and hands the same object here, so the two keys cannot disagree.

    @brief Per-file AST walk collecting thread-spawn sites.
    @version 7
    """
    return [
        _SpawnSite(
            row[0],
            row[1],
            row[2],
            row[3],
            row[4] if len(row) > 4 else SCOPE_SEP_CPP,
            row[5] if len(row) > 5 else None,
            path_rowid,
            ## Absent on a payload cached by an older stage_version, which reads as "no enclosing
            ## function recorded" — the same tolerant fold the separator and line already use.
            row[6] if len(row) > 6 else "",
        )
        for path_rowid, payload in run_harvest(conn, repo_root, harvester, ts_classes, cache)
        for row in payload
    ]


_IDENT_CHARS = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_")


## @brief True when `qualified` sits at an identifier boundary in `definition`.
## @param definition The full doxygen `definition` string.
## @param qualified The `Class::method` entry text to locate.
## @return True if SOME occurrence of `qualified` is delimited by a non-identifier char (or the string edge) on BOTH sides — so `Owner::run` matches neither `CoOwner::run` (bad prefix) nor `Owner::run_t` (bad suffix).
## @version 2
## @dg_internal
def _qualified_at_boundary(definition: str, qualified: str) -> bool:
    """A bare `%Class::method` SQL LIKE also matches a class whose name merely
    ENDS with `Class` (`Owner::run` inside `CoOwner::run`), OR the qualified name
    embedded in a longer identifier (`Owner::run` inside a param type
    `Owner::run_t`). Accept only a real token: SOME occurrence must be bounded by
    start/end-of-string or a non-identifier char (space, `:`, `*`, `&`, `(`, `<`)
    on BOTH sides. Scans every occurrence — `rfind` alone can land on a
    param-type mention while the true method-name match sits earlier (or vice
    versa), so a single-position check is not enough.

    @brief Guard a qualified-name match against prefix/suffix collisions.
    @version 2
    """
    n = len(qualified)
    start = 0
    while True:
        idx = definition.find(qualified, start)
        if idx < 0:
            return False
        before_ok = idx == 0 or definition[idx - 1] not in _IDENT_CHARS
        after = idx + n
        after_ok = after >= len(definition) or definition[after] not in _IDENT_CHARS
        if before_ok and after_ok:
            return True
        start = idx + 1


## @brief Resolve a qualified entry (`Class::method` / `Class.method`) to a rowid.
## @param conn Open connection.
## @param qualified The `Class::method` (or deeper) entry text.
## @param separator The scope separator that must be present to attempt this.
## @return The definition-preferring memberdef rowid whose `definition` contains the qualified entry at a token boundary, or None when none does.
## @version 6
## @dg_internal
def _resolve_qualified_entry(
    conn: sqlite3.Connection, qualified: str, separator: str = SCOPE_SEP_CPP
) -> int | None:
    """Resolve a member-pointer entry (`LinkOwner::rx_loop`) to the exact
    memberdef whose `definition` carries that qualified name — the precision a
    bare tail cannot give when two classes share a method name. The SQL LIKE is
    a coarse prefilter; `_qualified_at_boundary` then rejects a suffix collision
    (`Owner::run` must not resolve to `CoOwner::run`). Definition rows
    (`file_id == bodyfile_id`) are preferred, then lowest rowid.

    `separator` is supplied by the CALL SITE rather than sniffed from the text.
    Python's separator is `.`, which also appears in perfectly ordinary C entry
    arguments (`cfg.handler`, a struct field holding a function pointer), so
    accepting either separator unconditionally would divert those C sites from
    the name index onto this path and change the C result. `_qualified_at_boundary`
    needs no change: `.` and `:` are both outside `_IDENT_CHARS`, so both already
    count as token delimiters.

    @brief Resolve a scope-qualified entry to a definition rowid.
    @version 4
    """
    # `definition` is always present in a doxygen-built DB but absent from
    # minimal/partial DBs — degrade to the name-index fallback there.
    cols = {r[1] for r in conn.execute("PRAGMA table_info(memberdef)")}
    if separator not in qualified or "definition" not in cols:
        return None
    rows = conn.execute(
        "SELECT rowid, definition FROM memberdef WHERE kind='function' "
        "AND (definition LIKE ? OR definition LIKE ?) "
        "ORDER BY (file_id = bodyfile_id) DESC, rowid",
        (f"%{qualified}", f"%{qualified}(%"),
    ).fetchall()
    return next(
        (rid for rid, defn in rows if _qualified_at_boundary(defn or "", qualified)),
        None,
    )


## @brief Insert harvested spawn sites as threads rows, each with its spawn site.
## @version 6
## @dg_internal
def _insert_threads(
    conn: sqlite3.Connection,
    sites: list[_SpawnSite],
    name_index: dict[str, list[int]],
) -> int:
    """Resolve each spawn site's entry function to a memberdef rowid and insert
    a `threads` row (`ast_spawn`/`medium`). A qualified member-pointer entry
    (`Class::method`) resolves against `definition` for exact-overload
    precision; a bare entry falls back to the definition-preferring name index
    (NULL when the name isn't uniquely indexed). Duplicate (name, entry) pairs
    collapse via the UNIQUE constraint.

    THE SPAWN SITE RIDES ALONG (gh#346) and is what makes the row attributable, because
    `entry_rowid` above is legitimately NULL — both branches can produce it, and a row with no
    entry has no file to tag. `INSERT OR IGNORE` means that when one entry is
    spawned through one primitive from several sites, the FIRST wins — deterministic, since
    `run_harvest` walks paths in order, but one site standing for several. The alternative was
    joining the site to the UNIQUE key, which would un-collapse the `for` loop the key exists
    to collapse.

    @brief Insert threads rows from harvested spawn sites, each with its spawn site.
    @version 6
    """
    rows: list[tuple[str, int | None, str, int | None, int | None, str | None]] = []
    for site in sites:
        if site.separator in site.qualified_entry:
            # A member-pointer entry must resolve to ITS OWN class or stay NULL;
            # falling back to the bare tail would borrow a same-named method on
            # a different class (e.g. an unindexed TxPump::run stealing
            # DispatchLoop::run's rowid). NULL entry = thread present, no closure.
            # Python needs this MORE than C++, not less: `target=self._run` occurs
            # 5 times in 5 unrelated classes in one real codebase, so a bare
            # `_run` would be a 5-way collision.
            entry_rowid = _resolve_qualified_entry(conn, site.qualified_entry, site.separator)
        else:
            candidates = name_index.get(site.entry_name, [])
            entry_rowid = candidates[0] if len(candidates) == 1 else None
        rows.append(
            (
                site.name,
                entry_rowid,
                site.kind,
                site.path_rowid,
                site.line,
                ## NULL rather than "" when there is no enclosing function, so "not recorded" and
                ## "recorded as file scope" stay distinguishable — the same three-state discipline
                ## the emptiness notes elsewhere depend on.
                site.spawn_function or None,
            )
        )
    return conn.executemany(
        "INSERT OR IGNORE INTO threads (name, entry_memberdef_rowid, kind, "
        "source, confidence, spawn_path_rowid, spawn_line, spawn_function) "
        "VALUES (?, ?, ?, 'ast_spawn', 'medium', ?, ?, ?)",
        rows,
    ).rowcount


## @brief Compute + insert thread_membership via per-entry BFS over call_edges.
## @return The number of thread_membership rows actually inserted (executemany rowcount).
## @version 2
## @req REQ-DDB-SCHEMA-001
def _populate_membership(conn: sqlite3.Connection) -> int:
    """For every thread with a resolved entry rowid, forward-BFS over
    `call_edges` (non-fuzzy — reusing `reachability._bfs_live_set`) and file
    each reached function as a `call_closure` member. Multi-membership is
    expected (a hot shared helper belongs to every thread that reaches it);
    the UNIQUE(memberdef_rowid, thread_id) constraint dedups within a thread.

    @brief Populate thread_membership from per-entry call-edge closures.
    @version 2
    """
    threads = conn.execute(
        "SELECT id, entry_memberdef_rowid FROM threads WHERE entry_memberdef_rowid IS NOT NULL",
    ).fetchall()
    membership_rows: list[tuple[int, int]] = []
    for thread_id, entry_rowid in threads:
        live = _bfs_live_set(conn, {entry_rowid})
        for member_rowid in live:
            membership_rows.append((member_rowid, thread_id))
    return conn.executemany(
        "INSERT OR IGNORE INTO thread_membership "
        "(memberdef_rowid, thread_id, source) VALUES (?, ?, 'call_closure')",
        membership_rows,
    ).rowcount


## @brief R1 thread stage: harvest spawns → threads + thread_membership.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root (for resolving indexed relative paths).
## @param thread_patterns_path Optional --thread-patterns YAML, or None.
## @param cache Optional incremental index cache; None disables caching.
## @param harvester Pre-built harvester from the shared parse pass; built here when omitted.
## @version 5
## @req REQ-DDB-SCHEMA-001
def extract_threads(
    db_path: Path,
    repo_root: Path,
    thread_patterns_path: Path | dict | None = None,
    cache: IndexCache | None = None,
    harvester: Harvester | None = None,
) -> None:
    """Harvest thread-spawn sites into `threads` and compute
    `thread_membership` as a per-entry call-edge closure. Tables are always
    created (empty when tree_sitter is absent or no spawn matches), so
    consumers never branch on existence. Runs after the call-edge layers so
    membership sees the complete non-fuzzy call graph (including fnptr edges).

    `harvester` is the pre-built one from gh#358's shared parse pass; omitted, it is
    built here from `thread_patterns_path` exactly as before.

    @brief Import threads + thread_membership (spawn harvest + BFS closure).
    @version 3
    """
    conn = sqlite3.connect(str(db_path))
    _ensure_threads_tables(conn)

    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.info("tree_sitter not available — threads table left empty")
        conn.commit()
        conn.close()
        return

    name_index = _definition_preferring_name_index(conn)
    sites = _harvest_all_spawn_sites(
        conn,
        repo_root,
        harvester or spawn_harvester(thread_patterns_path),
        ts_classes,
        cache,
    )
    inserted_threads = _insert_threads(conn, sites, name_index)
    conn.commit()
    inserted_members = _populate_membership(conn)
    conn.commit()
    conn.close()
    logger.info(
        "threads: harvested %d spawn sites, inserted %d threads, %d membership rows",
        len(sites),
        inserted_threads,
        inserted_members,
    )


## @brief Build a memberdef_rowid -> set(thread_id) membership map.
## @return A dict mapping each member function's rowid to the set of thread ids it belongs to.
## @version 1
## @dg_internal
def _membership_map(conn: sqlite3.Connection) -> dict[int, set[int]]:
    """@brief Load thread_membership into an in-memory rowid -> thread-ids map."""
    mapping: dict[int, set[int]] = {}
    for member_rowid, thread_id in conn.execute(
        "SELECT memberdef_rowid, thread_id FROM thread_membership",
    ):
        mapping.setdefault(member_rowid, set()).add(thread_id)
    return mapping


## @brief Compute (crosses_thread, to_thread_id) for one writer/reader pair.
## @version 1
## @dg_internal
def _boundary_flags(
    writer_threads: set[int],
    reader_threads: set[int],
) -> tuple[int | None, int | None]:
    """crosses_thread is NULL when either endpoint has no membership
    (insufficient data); else 0 when they share any thread (the dataflow
    can be same-thread) and 1 when their thread sets are disjoint (a genuine
    boundary crossing). to_thread_id is the reader's thread only when it is
    unambiguous (exactly one), else NULL.

    @brief Derive crosses_thread / to_thread_id from membership sets.
    @version 1
    """
    if not writer_threads or not reader_threads:
        return None, None
    crosses = 0 if (writer_threads & reader_threads) else 1
    to_thread = next(iter(reader_threads)) if len(reader_threads) == 1 else None
    return crosses, to_thread


## @brief UPDATE shared_key_edges crosses_thread/to_thread_id from membership.
## @param db_path Path to the clew.db being built.
## @version 2
## @req REQ-DDB-SCHEMA-001
def annotate_thread_boundaries(db_path: Path) -> None:
    """For every `shared_key_edges` row, set `crosses_thread` and
    `to_thread_id` from the writer's and reader's thread membership. Ensures
    the shared_key_edges table exists first (so the full pipeline always has
    the enriched schema even when no shared-key stage produced rows).

    @brief Annotate shared-key edges with thread-boundary flags.
    @version 2
    """
    conn = sqlite3.connect(str(db_path))
    _ensure_shared_key_edges_table(conn)
    membership = _membership_map(conn)
    edges = conn.execute(
        "SELECT rowid, writer_rowid, reader_rowid FROM shared_key_edges",
    ).fetchall()
    updates: list[tuple[int | None, int | None, int]] = []
    for edge_rowid, writer_rowid, reader_rowid in edges:
        crosses, to_thread = _boundary_flags(
            membership.get(writer_rowid, set()),
            membership.get(reader_rowid, set()),
        )
        updates.append((crosses, to_thread, edge_rowid))
    conn.executemany(
        "UPDATE shared_key_edges SET crosses_thread = ?, to_thread_id = ? WHERE rowid = ?",
        updates,
    )
    conn.commit()
    conn.close()
    annotated = sum(1 for c, _t, _r in updates if c is not None)
    logger.info(
        "threads: annotated %d/%d shared-key edges with boundary flags",
        annotated,
        len(updates),
    )


## Tokens that make a name a plausible SPAWN primitive. A subject word plus a creation verb,
## required TOGETHER — which is this heuristic's answer to the same problem
## `detect_undeclared_lock_primitives` solves by pairing acquire with release.
##
## NEITHER HALF IS SUFFICIENT ALONE, and that is the whole design. "thread" alone matches
## `thread_local`, `pthread_mutex_lock`, `thread_id`, `threading_mutex_free`. "create" alone
## matches `CreateFileA`, `mbedtls_pk_create`, `create_context`. Requiring one of each is what
## makes `_beginthread`, `CreateThread`, `xTaskCreate`, `osThreadNew` and a project's own
## `sys_thread_create` all land while the noise does not.
## THE KINDS A SPAWN PRIMITIVE CAN ACTUALLY BE. A primitive is something you CALL, so it is a
## function or a macro that wraps one. `xTaskCreate` is a real ESP-IDF primitive and
## `SYSTEM_TASKCREATE` is this file's standing ILLUSTRATIVE stand-in for a vendor task-create
## wrapper; both shapes spell `macro definition`, so the macro kind cannot be dropped.
##
## MEASURED: without this filter, clew's own index reported `_THREAD_SPAWNER_COLUMNS`, a
## SQL column-list constant of kind `variable`. `THREAD` and `SPAWNER` are adjacent, so
## `_spawn_shaped` cannot reject it — no naming heuristic can, because the name genuinely is about
## thread spawning. What disqualifies it is that a variable is not callable.
##
## WHAT THIS DOES NOT FIX, said plainly so the next reader does not assume it did: a firmware
## index reports `CREATE_THREAD_ERROR` and `CREATE_THREAD_FAILED`, which are `macro definition`
## exactly like the genuine primitives beside them. Separating those needs an outcome-suffix
## blocklist, which is the thing this detector's docstring argues against.
_CALLABLE_KINDS: tuple[str, str] = ("function", "macro definition")

_SPAWN_SUBJECTS: tuple[str, ...] = ("thread", "task", "fiber", "worker")
_SPAWN_VERBS: tuple[str, ...] = ("create", "new", "begin", "spawn", "start", "launch", "fork")


## @brief Suggest spawn primitives a build should declare, because none of its patterns cover them.
## @param conn Open database connection.
## @param patterns The spawn patterns this build actually used.
## @return Candidate primitive names, sorted.
## @version 3
## @req REQ-DDB-CONFIG-007
def detect_undeclared_spawn_primitives(
    conn: sqlite3.Connection, patterns: list[SpawnPattern]
) -> list[str]:
    """THE THREAD LAYER'S COUNTERPART TO `detect_undeclared_lock_primitives`, and it exists
    because the same gap was found here one issue later. `diagnostics.py` already records the
    lock hint as existing "because that counterpart was missing"; this closes the third instance.

    IT IS ALSO A PROMISE THE PAYLOAD NOW MAKES. `_roster_meaning` was rewritten to stop calling
    its matched-pattern count the repository's thread count, and to route a reader to
    `status.diagnostics` for families the build did not cover. Shipping that sentence without
    this function would have been the exact defect the rewrite fixed: a tool asserting something
    it cannot deliver.

    WHY NOT `propose_thread_patterns`. That detector is SEEDED on `DEFAULT_SPAWN_PATTERNS` —
    it finds wrappers that forward into a primitive already known — so an unknown primitive is
    not a wrapper of anything and can never be proposed by it. The gap it leaves is precisely
    the one that made mbedtls's `_beginthread` invisible.

    PURELY ADVISORY, and deliberately biased toward missing a hint rather than inventing one:
    a missed hint costs an operator nothing they were not already paying, while a false hint
    costs real time chasing a primitive that does not exist. Same asymmetry `AccessorFamily`
    records.

    WHAT IT CANNOT SEE, MEASURED AGAINST ITS OWN MOTIVATING CASE AND NAMED HERE BECAUSE THE
    ANSWER IS UNCOMFORTABLE. It reads `memberdef`, which holds the names this repository
    DECLARES. Run against mbedtls with the pattern list emptied — i.e. asked to find what a
    build with no Windows coverage was missing — it returns `thread_create` and NOT
    `_beginthread`, because `_beginthread` is declared in `<process.h>` and mbedtls only CALLS
    it. So this hint would not have found the very gap that prompted it.

    That is a real limit, not a rounding error, and it splits the space cleanly:
      * A repo's OWN spawn wrapper (`sys_thread_create`, `SYSTEM_TASKCREATE`) is declared here
        and IS found — a genuine and common class, and the one `propose_thread_patterns` cannot
        reach because it only recognises wrappers of already-known primitives.
      * An EXTERNAL platform API that is only called is invisible to this query. Finding those
        needs unresolved CALLEE names, which no table carries — `critical_section_calls` has
        one but only inside an already-detected critical section, which is the same shape of
        chicken-and-egg the lock hint documents.

    The lock hint escapes this because mbedtls DECLARES `mbedtls_mutex_lock` itself, as an
    extern pointer in its own header. The asymmetry is a property of the two repos, not of the
    two detectors, and assuming the lock hint's success would transfer is what made this worth
    checking rather than believing.

    The payload wording is bounded to match: `_roster_meaning` leads with the DECLARABLE fix
    (`thread_patterns`) and offers diagnostics as the secondary route, rather than promising a
    hint that a whole class of primitive cannot produce.

    @brief Suggest spawn primitives this build's patterns did not cover.
    @return Candidate names, sorted.
    @version 3
    """
    covered = {p.name.lower() for p in patterns}
    ## A declared or default pattern may be dotted (`threading.Thread`) or qualified
    ## (`std::thread`); a bare `memberdef` name never is, so compare on the TAIL too or every
    ## Python default would leave its own primitive looking undeclared.
    covered |= {name.rsplit(".", 1)[-1].rsplit("::", 1)[-1] for name in covered}
    try:
        names = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT name FROM memberdef WHERE name<>'' AND kind IN (?, ?)",
                _CALLABLE_KINDS,
            )
        }
    except sqlite3.Error:
        return []
    return [name for name in sorted(names) if name.lower() not in covered and _spawn_shaped(name)]


## @brief Whether a name is SHAPED like a spawn primitive rather than merely mentioning one.
## @param name The candidate name.
## @return True when a subject and a creation verb sit adjacent in it.
## @version 1
## @dg_internal
def _spawn_shaped(name: str) -> bool:
    """ADJACENCY, NOT CO-OCCURRENCE, and the first version got this wrong in a way only a real
    repository showed. "a subject word AND a creation verb, anywhere in the name" is satisfied by
    `test_extract_threads_always_creates_empty_tables` — and on clew's own index that
    heuristic reported SIX candidates, every one of them a test function name describing spawn
    behaviour. 100% noise, on the first real corpus it ever saw, from a detector whose docstring
    argued that a false hint costs an operator real time.

    The unit test passed throughout, because it fed four curated names. That is the failure this
    repo keeps re-finding under different names — the fixture matched the DETECTOR rather than
    the world — committed here in the very change that cited it.

    A primitive puts its subject and verb TOGETHER: `_beginthread`, `CreateThread`, `xTaskCreate`,
    `osThreadNew`, `sys_thread_create`, `pthread_create`. Prose puts words between them:
    `threads_always_creates`, `thread_is_attributed_by_its_spawn_site`. One optional separator is
    allowed, which is what carries `thread_create` and `Thread New` while rejecting three words.

    `test_`-prefixed names are excluded outright as a second term, because `new_thread` IS
    adjacent and a test named for it is still not a primitive. Cheap, and it removed the last
    false positive rather than most of them.

    @brief Decide whether a name is shaped like a spawn primitive.
    @return True when it plausibly is one.
    @version 1
    """
    lowered = name.lower()
    if lowered.startswith("test_"):
        return False
    for subject in _SPAWN_SUBJECTS:
        for verb in _SPAWN_VERBS:
            for joiner in ("", "_"):
                if f"{subject}{joiner}{verb}" in lowered or f"{verb}{joiner}{subject}" in lowered:
                    return True
    return False
