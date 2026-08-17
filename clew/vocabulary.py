# SPDX-License-Identifier: MIT
"""The schema's enumerated vocabularies — ONE definition per value set.

Every enumerated column in clew.db used to spell its allowed values as a SQL
string literal at the CREATE TABLE site, and sometimes a SECOND time as a module
constant guarding the declared-config path. That is 25 literals across 8 modules
with nothing tying them together, and it had already drifted: `_VALID_KINDS` was
defined TWICE with DIFFERENT values (`threads.py`, a set of thread kinds;
`locks.py`, a tuple of lock kinds), so a cross-import would have produced a
silently wrong CHECK on whichever table lost the race.

This module is the single source. A column's allowed values live in exactly one
`Vocabulary`; the DDL asks it for a clause (`check(table, column)`) and the
declared-config loaders ask the SAME object to validate a token.

TRUE LEAF — zero intra-package imports, by design. `clew/_common.py`
pulls in `rich`, while `clew/query/_common.py` is deliberately
stdlib-only; importing either here would make one of those two layers
un-importable without the other's dependencies. The logger comes from `logging`
directly for exactly that reason.

FIVE VOCABULARIES SHARE THE TUPLE ('low','medium','high') AND ARE STILL FIVE
OBJECTS. They mean five different things — spawn-detection strength, inferred-
vs-declared provenance, lock-identity certainty, acquisition-resolution success,
and a constant on `external_boundaries`. Binding one object to all five would
mean that adding a value for one silently widens the CHECK on the other four,
while every test that compares the shipped schema to this registry stays green.

GENERATION NEVER USES `{tuple!r}`. The idiom this replaces (`locks.py`) emits
`CHECK(c IN ('x',))` for a one-value set — a SQLite SYNTAX ERROR — and
`CHECK(c IN ("it's",))` for a value containing an apostrophe. It survived only
by accident, because every set it was applied to happened to have >= 2 values;
`boundary_source` had exactly one until the declared-dispatch terminus kind
landed, which is precisely how a latent one-value case reaches production.
`values` is also a TUPLE, never a set: set iteration order is not part of any
contract, and a set here would make the shipped schema text vary between builds.

FAIL CLOSED on a declared value outside its vocabulary (`validated` raises
`DeclarationError`), rather than normalizing to 'unknown' as the loaders used
to. `acq_form`/`acq_role`/`acq_mode` have no 'unknown' member at all, so a
fallback has to invent a specific, real synchronization claim out of a typo. And
`locks.kind` is part of lock IDENTITY (`UNIQUE(name, scope, kind)`), so two
differently-typo'd kinds normalizing to one token COLLAPSE INTO ONE lock row —
fabricating shared synchronization, which is precisely the error the lock layer
documents itself as failing closed against.

@brief Central registry of the schema's enumerated value sets.
@version 3
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

# NOTE for anyone extending this module: it logs nothing on purpose — a pure
# registry has nothing to report, since validation RAISES and generation is
# deterministic. If that ever changes, take the logger from
# `logging.getLogger("clew")` directly and NOT from `._common`, which
# would pull `rich` into every importer (see the module docstring on leafness).


## @brief A declared config value outside its schema vocabulary.
## @version 1
class DeclarationError(ValueError):
    """Raised at declaration-load time when a repo's `.clew.yaml` (or a
    standalone manifest) names a token no vocabulary allows.

    Deliberately NOT normalized away: the alternative is a build that succeeds
    while asserting a synchronization or dispatch fact its author never wrote.
    The message carries the origin file, the offending token and the full
    allowed set, so the fix is mechanical.

    @brief Declared token outside its vocabulary — fail closed.
    @version 1
    """


## @brief Name the manifest a declared value came from, for an error message.
## @param source The manifest as a loader received it: a path, a mapping, or None.
## @param section The `.clew.yaml` section a mapping would have come from.
## @return The file path when the loader was given one, else the section name.
## @version 2
## @req REQ-DDB-SCHEMA-012
def declaration_origin(source: object, section: str) -> str:
    """A `DeclarationError` is only actionable if it names the file to edit, and
    the loaders receive either a standalone manifest path or an already-parsed
    `.clew.yaml` section — this collapses both into one label.

    @brief Label a declaration's origin for a fail-closed error message.
    @version 2
    """
    if isinstance(source, (str, Path)):
        return str(source)
    return f".clew.yaml [{section}]"


## @brief One enumerated value set: its members, meaning, and per-value rank.
## @version 1
@dataclass(frozen=True)
class Vocabulary:
    """An enumerated column's allowed values plus the semantics a consumer needs
    to read them.

    `values` is ORDERED and the order is part of the emitted schema text.
    `rank` is an EXPLICIT per-value map, never derived from position: `call_match`
    is ordered strongest-first (exact, resolved, fuzzy) while every strength
    vocabulary is ordered weakest-first (low, medium, high), so a positional
    ordinal would invert one of them.
    `reserved` marks values the CHECK permits but no code path writes — allowed
    so the schema stays forward-compatible, and flagged so a test asserting
    "every value is observed in data" does not have to fail.

    @brief One enumerated value set (members + meaning + rank).
    @version 1
    """

    id: str
    values: tuple[str, ...]
    means: str
    rank: dict[str, int] = field(default_factory=dict)
    reserved: frozenset[str] = frozenset()

    ## @brief SQL CHECK clause constraining a column to this vocabulary.
    ## @param column Name of the column the clause guards.
    ## @return A `CHECK(col IN (...))` fragment, valid for any arity >= 1.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-012
    def check(self, column: str) -> str:
        """Explicit quote-and-join, never `{tuple!r}` — a 1-tuple repr carries a
        trailing comma that SQLite rejects, and repr quotes an apostrophe-bearing
        value with double quotes, which SQLite reads as an identifier.

        @brief Generate this vocabulary's CHECK clause for one column.
        @version 1
        """
        inner = ", ".join("'" + v.replace("'", "''") + "'" for v in self.values)
        return f"CHECK({column} IN ({inner}))"

    ## @brief Membership test, so `token in vocabulary` reads naturally.
    ## @param value Candidate token.
    ## @return True when the token is one of this vocabulary's values.
    ## @version 1
    ## @dg_internal
    def __contains__(self, value: object) -> bool:
        """@brief True when `value` is a member of this vocabulary.

        @version 1
        """
        return value in self.values

    ## @brief Return a declared token when allowed, else raise DeclarationError.
    ## @param value The token as declared.
    ## @param owner Where it was declared (file + entry), for the message.
    ## @param field Field name it was declared under, for the message.
    ## @return The value, unchanged.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-012
    def validated(self, value: str, *, owner: str, field: str) -> str:
        """The single choke point every declared-enum path routes through. It
        raises rather than falling back because there is no honest fallback: see
        the module docstring on lock identity collapse.

        @brief Validate one declared token, failing closed.
        @version 1
        """
        if value in self.values:
            return value
        raise DeclarationError(
            f"{owner}: invalid {field} {value!r} — allowed: {', '.join(self.values)}"
        )


# ── The registry ─────────────────────────────────────────────────────────────
# One entry per distinct MEANING, even where two entries carry identical tuples.

## The six call-edge provenance layers, named because six sites already import
## three of them from `call_edges` (which re-exports these, keeping its own
## per-layer commentary next to the code that produces each). Spelling them once
## here is what stops a value from existing in the CHECK but not the constant, or
## the reverse.
CALL_SOURCE_DOXYGEN_SQLITE = "doxygen_sqlite"
CALL_SOURCE_AST = "ast"
CALL_SOURCE_AST_MEMBER = "ast_member"
CALL_SOURCE_FNPTR = "fnptr"
## The one provenance no call site names. Every other layer OBSERVES a call and
## argues about how precisely it resolved; this one is an author's declaration
## that an indirection (a virtual seam, a function-pointer table) connects two
## functions the source text keeps apart. Separable on purpose — a consumer must
## always be able to ask "would this edge exist without the manifest?".
CALL_SOURCE_DECLARED_DISPATCH = "declared_dispatch"
## A call the source text makes THROUGH A MACRO, composed from the two hops doxygen
## already records: `caller → macro definition` and `macro definition → callee`.
##
## Separate from `doxygen_sqlite` although it comes from the same `xrefs` table, because
## it is the only edge here whose two endpoints never appear together at any call site —
## the composition is ours, and a consumer must be able to ask "did doxygen say this
## directly, or did we join it?". Measured cause: a C accessor convention expressed
## entirely as function-like macros produced ZERO outgoing call edges for every macro-only
## caller, because both importers require BOTH endpoints to be `kind='function'` and a
## `#define` is `kind='macro definition'`. Turning on the preprocessor does NOT fix it —
## measured as a no-op on every metric; the hops were always there and we discarded them.
CALL_SOURCE_MACRO_HOP = "macro_hop"
## A function reference BOUND rather than called: `handler = do_work` or, in Python,
## `sub.set_defaults(func=cmd_rubric)`. The binding is plainly in the source text, but
## no layer that looks for a CALL can see it, so the caller side of every such
## dispatch was empty — argparse subcommands being the measured case (gh#1).
##
## Separable from `ast` on purpose, and the distinction is real rather than
## bookkeeping: `ast` means a call site was OBSERVED at that line, while this means a
## reference was handed to someone else who will call it, at a time and on a thread
## this edge says nothing about. A consumer summarising control flow must be able to
## tell "X calls Y here" from "X arranges for Y to be called later".
CALL_SOURCE_BINDING = "binding"

CALL_SOURCE = Vocabulary(
    id="call_source",
    values=(
        CALL_SOURCE_DOXYGEN_SQLITE,
        CALL_SOURCE_AST,
        CALL_SOURCE_AST_MEMBER,
        CALL_SOURCE_FNPTR,
        CALL_SOURCE_DECLARED_DISPATCH,
        CALL_SOURCE_MACRO_HOP,
        CALL_SOURCE_BINDING,
    ),
    means="which extraction layer produced this call edge",
    # Ranked ABOVE doxygen's own exact xrefs: the others are inferences graded by
    # how well a name resolved, while a declared edge is a statement of fact by
    # the person who wrote the indirection. That it is synthetic is carried by
    # the source VALUE, which a consumer reads directly — not by demoting it.
    ## `macro_hop` sits just BELOW doxygen's direct xrefs and above every name-resolving
    ## inference. Both of its hops are doxygen's own observations, so it is stronger than
    ## anything that matched on a name — but the COMPOSITION is ours, so it must not
    ## outrank an edge doxygen stated directly.
    ## Renumbered 0-6 when `macro_hop` was inserted, and 0-7 when `binding` was.
    ## Only the ORDER is load-bearing — `_collapse_variants` compares ranks to pick
    ## which layer's provenance a collapsed row reports — so the absolute values carry
    ## no meaning and gaps buy nothing.
    ##
    ## `binding` sits BELOW `ast` and above `ast_member`. Below `ast` because when a
    ## function is both called outright and bound somewhere, the observed call is the
    ## better description of the pair. Above `ast_member` because a binding names a
    ## bare identifier and so was never guessed from an unwrapped tail.
    rank={
        CALL_SOURCE_DECLARED_DISPATCH: 7,
        CALL_SOURCE_DOXYGEN_SQLITE: 6,
        CALL_SOURCE_MACRO_HOP: 4,
        CALL_SOURCE_AST: 3,
        CALL_SOURCE_BINDING: 2,
        CALL_SOURCE_AST_MEMBER: 1,
        CALL_SOURCE_FNPTR: 0,
    },
)

## The two tiers every NAME-resolving layer files an edge under — a single
## matching definition vs several candidates. Named because four producers now
## write them (AST Layer 3, the fnptr Layer 4, the ast_member recovery and the
## declared-dispatch Layer 6) and the weaker tier is load-bearing beyond
## provenance: `mark_reachability` and thread membership BOTH skip 'fuzzy', so
## mis-spelling it in a producer silently promotes a guess into the liveness BFS.
CALL_MATCH_EXACT = "exact"
CALL_MATCH_RESOLVED = "resolved"
CALL_MATCH_FUZZY = "fuzzy"

CALL_MATCH = Vocabulary(
    id="call_match",
    values=(CALL_MATCH_EXACT, CALL_MATCH_RESOLVED, CALL_MATCH_FUZZY),
    means="how precisely the callee rowid was resolved (NOT how likely the call is real)",
    rank={CALL_MATCH_EXACT: 2, CALL_MATCH_RESOLVED: 1, CALL_MATCH_FUZZY: 0},
)

KEY_SOURCE = Vocabulary(
    id="key_source",
    values=("shared_key_inferred", "shared_key_declared"),
    means="whether a dataflow edge came from accessor inference or a manifest",
    rank={"shared_key_declared": 1, "shared_key_inferred": 0},
)

KEY_STRENGTH = Vocabulary(
    id="key_strength",
    values=("low", "medium", "high"),
    means="confidence that a shared-key write/read pair really is a dataflow seam",
    rank={"low": 0, "medium": 1, "high": 2},
    reserved=frozenset({"low"}),
)

EDGE_KIND = Vocabulary(
    id="edge_kind",
    values=("state", "event", "unknown"),
    means="whether the key carries retained state or a fire-once event",
    rank={"state": 0, "event": 0, "unknown": 0},
)

DISPATCH_MODE = Vocabulary(
    id="dispatch_mode",
    values=("inline", "queued", "keyed", "unknown"),
    means="the synchrony class of the hand-off: same-thread, buffered, or topic-routed",
    rank={"inline": 0, "queued": 0, "keyed": 0, "unknown": 0},
)

## Python's spawn primitives forced TWO new members rather than reusing the
## nearest existing one, because this column is what a consumer reads to decide
## whether two functions can race.
##   - `process` (`multiprocessing.Process`): a separate ADDRESS SPACE. Filing it
##     as 'pthread' or 'task' would say the two share memory, so a consumer would
##     hunt for a lock on state that is copy-on-fork and cannot be shared at all.
##   - `coroutine` (`asyncio.create_task`): cooperative, on the SAME OS thread.
##     Filing it as 'pthread' invents a preemption boundary — a consumer would
##     report a data race between two coroutines that can only interleave at
##     `await`, which is the opposite of the truth.
## `threading.Thread` stays 'pthread' (CPython on POSIX really does create one),
## and a pool `submit` stays 'task' (a work item scheduled onto a pool).
THREAD_KIND_PROCESS = "process"
THREAD_KIND_COROUTINE = "coroutine"

## `win32` forced a new member for the SAME reason `process` and `coroutine` did: the two
## nearest existing values would each assert something untrue, and this column is what a
## consumer reads to decide whether two functions can race.
##   - 'pthread' names a POSIX primitive. `_beginthread` / `CreateThread` are not one, and a
##     reader who greps for `pthread_` on that label finds nothing and concludes the row is
##     wrong.
##   - 'task' names a work item scheduled onto an RTOS or a pool. A Win32 thread is a real
##     preemptible OS thread with its own stack, which is a stronger claim than 'task' makes.
## Both would still get the RACE question right; the label would simply be a lie about the
## API, and this project has already learned that a plausible label is quoted onward.
THREAD_KIND_WIN32 = "win32"

_THREAD_KINDS = (
    "task",
    "pthread",
    THREAD_KIND_WIN32,
    "timer",
    "isr",
    "main",
    "oneshot",
    THREAD_KIND_PROCESS,
    THREAD_KIND_COROUTINE,
    "unknown",
)

THREAD_KIND = Vocabulary(
    id="thread_kind",
    ## ONE TUPLE, read twice. `values` and `rank` were two hand-maintained copies of the same
    ## list, so adding a member meant remembering to edit both — and a value present in
    ## `values` but absent from `rank` is exactly the shape that produces a KeyError on a
    ## payload path rather than at import.
    values=_THREAD_KINDS,
    means="the execution-context primitive this thread was spawned as",
    rank=dict.fromkeys(_THREAD_KINDS, 0),
)

THREAD_SOURCE = Vocabulary(
    id="thread_source",
    values=("ast_spawn", "declared"),
    means="whether the thread was found at a spawn call site or declared",
    rank={"declared": 1, "ast_spawn": 0},
    reserved=frozenset({"declared"}),
)

THREAD_STRENGTH = Vocabulary(
    id="thread_strength",
    values=("low", "medium", "high"),
    means="confidence that the spawn site's entry function was identified correctly",
    rank={"low": 0, "medium": 1, "high": 2},
    reserved=frozenset({"low", "high"}),
)

MEMBERSHIP_SOURCE = Vocabulary(
    id="membership_source",
    values=("call_closure", "declared"),
    means="whether thread membership was computed by call closure or declared",
    rank={"declared": 1, "call_closure": 0},
    reserved=frozenset({"declared"}),
)

LOCK_KIND = Vocabulary(
    id="lock_kind",
    values=("mutex", "recursive_mutex", "shared_mutex", "semaphore", "spinlock", "unknown"),
    means="the synchronization primitive this lock is — PART OF ITS IDENTITY",
    rank={
        k: 0
        for k in ("mutex", "recursive_mutex", "shared_mutex", "semaphore", "spinlock", "unknown")
    },
)

LOCK_IDENTITY = Vocabulary(
    id="lock_identity",
    values=("low", "medium", "high"),
    means="certainty that two acquisitions naming this lock really take the SAME lock",
    rank={"low": 0, "medium": 1, "high": 2},
)

LOCK_SOURCE = Vocabulary(
    id="lock_source",
    values=("ast_decl", "ast_use", "declared"),
    means="whether the lock was seen as a member declaration, at a use site, or declared",
    rank={"declared": 2, "ast_decl": 1, "ast_use": 0},
    reserved=frozenset({"ast_decl", "declared"}),
)

ACQ_FORM = Vocabulary(
    id="acq_form",
    values=("call", "raii", "declared"),
    means="how the acquisition is written: an explicit call, an RAII guard, or declared",
    rank={"call": 0, "raii": 0, "declared": 0},
    reserved=frozenset({"declared"}),
)

ACQ_ROLE = Vocabulary(
    id="acq_role",
    values=("acquire", "try_acquire", "scoped"),
    means="whether the site blocks, may fail, or holds for the enclosing scope",
    rank={"acquire": 0, "try_acquire": 0, "scoped": 0},
)

ACQ_MODE = Vocabulary(
    id="acq_mode",
    values=("exclusive", "shared"),
    means="whether the hold excludes all others or only writers",
    rank={"exclusive": 0, "shared": 0},
)

ACQ_STRENGTH = Vocabulary(
    id="acq_strength",
    values=("low", "medium", "high"),
    means="confidence that the acquisition's extent (its critical section) was resolved",
    rank={"low": 0, "medium": 1, "high": 2},
)

## L2 records one row per CALL SITE inside a critical section, and a call site is
## a PHYSICAL LOCATION — it can only ever be one call. So a name matching several
## memberdefs must NOT fan out into several rows the way `call_edges` does:
## "what runs under this lock" would then answer with N functions where exactly
## one runs, and a reader has no way to tell the fabricated N-1 from the real
## one. The row stays single, its `callee_rowid` stays NULL (never borrow another
## symbol's rowid), and this column says WHY it is NULL.
##
## Deliberately not `call_match`. That vocabulary grades how a rowid resolved and
## has no member for "no memberdef exists at all" — the majority case here, since
## a critical section is full of stdlib, vendor and macro calls. Reusing it would
## have to file those as 'fuzzy', which claims an in-repo callee was ambiguous
## when in truth there was never a candidate. And 'exact' is unreachable for L2:
## it never sees doxygen's own xrefs, only the tree-sitter walk.
## `receiver_unverified` is the L2 twin of what `fd384e5` did to `ast_member` edges: the
## name pinned exactly one memberdef, but the call site was `x.f()` and the receiver was
## unwrapped away, so the match is a fact about the INDEX rather than about the call. It
## keeps the rowid — DEMOTE, DO NOT DROP — because dropping it made `lock_nestings` return
## ZERO on a codebase that genuinely has nestings, trading 13 false positives for a useless
## layer. Ranked below 'resolved' and above 'ambiguous': one candidate is still more than
## several, and a consumer weighing a deadlock argument needs to see the difference.
SECTION_MATCH_RESOLVED = "resolved"
SECTION_MATCH_RECEIVER_UNVERIFIED = "receiver_unverified"
SECTION_MATCH_AMBIGUOUS = "ambiguous"
SECTION_MATCH_EXTERNAL = "external"

SECTION_MATCH = Vocabulary(
    id="section_match",
    values=(
        SECTION_MATCH_RESOLVED,
        SECTION_MATCH_RECEIVER_UNVERIFIED,
        SECTION_MATCH_AMBIGUOUS,
        SECTION_MATCH_EXTERNAL,
    ),
    means="whether a call inside a critical section pinned exactly one in-repo callee",
    rank={
        SECTION_MATCH_RESOLVED: 3,
        SECTION_MATCH_RECEIVER_UNVERIFIED: 2,
        SECTION_MATCH_AMBIGUOUS: 1,
        SECTION_MATCH_EXTERNAL: 0,
    },
)

## The two terminus kinds a stage actually records. Named because the shapes are
## genuinely different and each has exactly one producer: `callback_edges` writes
## the forwarded-function-pointer kind, `dispatch_edges` the declared-interface
## kind. A consumer counting "termini" must be able to tell which it is looking
## at — a C/POSIX repo shows the first and none of the second, and an
## interface-HAL C++ codebase the reverse.
BOUNDARY_KIND_UNRESOLVED_CALLBACK = "unresolved_callback"
BOUNDARY_KIND_INTERFACE = "interface_boundary"
## The only strength a terminus row is ever written with, on both producers: the
## boundary is either observed forwarding out of repo or DECLARED by the author,
## so there is no resolution step left to be unsure about.
BOUNDARY_STRENGTH_HIGH = "high"

BOUNDARY_KIND = Vocabulary(
    id="boundary_kind",
    values=(BOUNDARY_KIND_UNRESOLVED_CALLBACK, "external_registration", BOUNDARY_KIND_INTERFACE),
    means="why the graph terminates here rather than continuing",
    # 'interface_boundary' is a SECOND terminus kind, not a repair of the first.
    # 'unresolved_callback' is a function pointer forwarded to an out-of-repo
    # registrar; this one is a virtual call whose implementor lives outside the
    # index (a HAL seam). A C/POSIX repo shows the first and none of the second;
    # an interface-HAL C++ codebase shows the reverse, which is why its terminus
    # layer measured 0 while the detector was working correctly.
    rank={"unresolved_callback": 0, "external_registration": 0, "interface_boundary": 0},
    reserved=frozenset({"external_registration"}),
)

BOUNDARY_SOURCE = Vocabulary(
    id="boundary_source",
    values=("callback_edges", "declared_dispatch"),
    means="which pipeline stage recorded this terminus",
    rank={"callback_edges": 0, "declared_dispatch": 0},
)

BOUNDARY_STRENGTH = Vocabulary(
    id="boundary_strength",
    values=("low", "medium", BOUNDARY_STRENGTH_HIGH),
    means="confidence that this really is an external boundary and not a missed resolution",
    rank={"low": 0, "medium": 1, "high": 2},
    reserved=frozenset({"low", "medium"}),
)

LIVENESS = Vocabulary(
    id="liveness",
    values=("live", "orphan"),
    means="whether the symbol is reachable from any entry-point seed",
    rank={"live": 1, "orphan": 0},
)

## The two neighbour classes an R2 edge can carry. Named because THREE surfaces
## now tag with them — `chain_trace`'s hops and both `callers`/`callees` — and a
## consumer that misreads a `key` row as a `call` reads "A calls B" out of "A
## writes a key B reads", which may be asynchronous and on another thread.
EDGE_CLASS_CALL = "call"
EDGE_CLASS_KEY = "key"

EDGE_CLASS = Vocabulary(
    id="edge_class",
    values=(EDGE_CLASS_CALL, EDGE_CLASS_KEY),
    means="wire-only tag: a synchronous same-thread call vs a shared-key dataflow hop",
    rank={EDGE_CLASS_CALL: 0, EDGE_CLASS_KEY: 0},
)

## DECLARATION-ONLY, like STAGE below: it constrains a token a repo writes in
## `.clew.yaml`, not a column. A `shared_key_wrappers` entry's `direction`
## picks WHICH accessor list the wrapper joins, and there is no third option — a
## typo'd 'wrtie' silently filed as a reader would invert the dataflow the entry
## exists to reveal, and the build would still succeed. Registered here so that
## refusal shares one spelling and one error shape with every other declared enum.
KEY_DIRECTION = Vocabulary(
    id="key_direction",
    values=("write", "read"),
    means="whether a declared key-wrapper produces the key or consumes it",
    rank={"write": 0, "read": 0},
)

## Which code generator's manifest set a declared data-model key was read from. BOTH VALUES
## ARE WRITTEN, so NEITHER is `reserved` any more — `udm` was reserved while the pipeline
## recognised that dialect's manifests and deliberately did not read them, and gh#351 added
## its parser. Reserving it now would tell a test asserting "every value appears in data" to
## exempt a value that really is produced, which is the opposite of what `reserved` is for.
## The two dialects carry DIFFERENT resolution guarantees rather than different columns: a
## `udm` row's `default_value` and `enum_name` are NULL BY DIALECT and its
## `unresolved_fields` says which fields the manifest declared — see `datamodel`.
DATA_MODEL_DIALECT = Vocabulary(
    id="data_model_dialect",
    values=("ingot", "udm"),
    means="which code generator's manifest set declared this data-model key",
    rank={"ingot": 0, "udm": 0},
)

## The extract_cache partitions. A stage string is part of the cache PRIMARY
## KEY and carries NO CHECK, so a typo here never raises — it silently produces a
## permanent cache miss for that harvester. Named so the sites share one
## spelling, and so `fnptr` (also a `call_source` VALUE) is visibly a different
## namespace. Changing one of these values invalidates every cached extraction
## for that stage, which is the same failure by another route.
STAGE_AST_CALLS = "ast_calls"
STAGE_FNPTR = "fnptr"
STAGE_THREADS = "threads"
STAGE_SHARED_KEY = "shared_key"
STAGE_MQTT = "mqtt"
STAGE_LOCKS = "locks"
STAGE_DISPATCH = "dispatch"
## Python reachability entry points (`__main__` guards, decorator registrations).
## Its own partition rather than a field on `ast_calls`: the two answer different
## questions and change on different schedules, so folding them together would
## make an entry-point fix re-harvest every call site in the repo.
STAGE_PY_ENTRIES = "py_entries"
## The function DEFINITIONS a file contains (gh#11), as opposed to the call sites
## inside them. Its own partition rather than a field on `ast_calls` for the reason
## given above: the two change on different schedules, and the symbol harvest runs
## EARLIER in the pipeline than the call harvest — it has to, because the rows it
## inserts are what the call layers then resolve their endpoints against.
STAGE_AST_SYMBOLS = "ast_symbols"
## The preprocessor conditionals that gate a line on a `CONFIG_*` symbol (gh#18
## part 3). Its own partition for the reason the two above give: it reads a part of
## the tree no other harvester looks at — `preproc_if`/`preproc_ifdef` nodes, which
## every other stage walks straight past — so folding it into `ast_calls` would make
## a gate-harvest change re-parse every call site in the repo.
STAGE_KCONFIG_GATES = "kconfig_gates"

STAGE = Vocabulary(
    id="stage",
    values=(
        STAGE_AST_CALLS,
        STAGE_FNPTR,
        STAGE_THREADS,
        STAGE_SHARED_KEY,
        STAGE_MQTT,
        STAGE_LOCKS,
        STAGE_PY_ENTRIES,
        STAGE_DISPATCH,
        STAGE_AST_SYMBOLS,
        STAGE_KCONFIG_GATES,
    ),
    means="extract_cache partition key — a typo is a permanent silent cache miss, not an error",
    rank={
        STAGE_AST_CALLS: 0,
        STAGE_FNPTR: 0,
        STAGE_THREADS: 0,
        STAGE_SHARED_KEY: 0,
        STAGE_MQTT: 0,
        STAGE_LOCKS: 0,
        STAGE_PY_ENTRIES: 0,
        STAGE_DISPATCH: 0,
        STAGE_AST_SYMBOLS: 0,
        STAGE_KCONFIG_GATES: 0,
    },
)

## WHERE A `memberdef` ROW CAME FROM (gh#11). `memberdef` is doxygen's OWN table —
## doxygen's sqlite3 backend creates it and we copy the file — so until this
## vocabulary existed every row in it was, by construction, doxygen's. That was the
## defect: tree-sitter walks every indexed file on every build and found 2,495
## function definitions inside files doxygen reported as empty (mbedtls
## `library/*.c`: doxygen 10 bodies, tree-sitter 2,507), and had nowhere to put
## them, so the parse was discarded when the build ended.
##
## Marked rather than merged silently, the way `call_edges` marks `source` and
## `confidence`. The two values do NOT differ only in origin, they differ in what
## the row can carry: a 'doxygen' row has a brief, a detailed description, its
## documented parameters and therefore its `@req` tags, while an 'ast' row has a
## name, a file, a line span and its static-ness AND NOTHING ELSE — a preprocessor
## that skipped the code skipped its doc comment too. A consumer that cannot tell
## the two apart would read a missing brief as an undocumented function rather than
## as an unparsed one.
##
## Ranked with 'doxygen' above 'ast' for the same reason `call_source` ranks
## doxygen's own xrefs above every inference: one is what the documenting tool
## stated, the other is what we recovered from the source text.
SYMBOL_SOURCE_DOXYGEN = "doxygen"
SYMBOL_SOURCE_AST = "ast"

## The COLUMN NAME is deliberately namespaced, and this is the one place it is
## spelled. `memberdef` belongs to doxygen: an unprefixed `source` would collide
## the day doxygen's own schema grows one, and the failure mode of that collision
## is not a loud `duplicate column name` — the idempotent ADD COLUMN would find a
## column already present and we would then read doxygen's semantics as ours.
## A prefix makes that impossible rather than unlikely.
SYMBOL_SOURCE_COLUMN = "dg_source"

## WHICH FOREIGN GIT TREE AN INDEXED FILE BELONGS TO (gh#335), or NULL for first
## party. Registered here and NOT as a `Vocabulary`, deliberately: its value set is
## the target repo's own submodule paths, which is data and not a vocabulary — a
## CHECK over it would be the hardcoded repo shape the mandate forbids.
##
## Namespaced for the same reason `dg_source` is: `path` is doxygen's own table, an
## unprefixed `external` would collide the day doxygen grows one, and the failure
## mode of that collision is not a loud `duplicate column name` but an idempotent
## ADD COLUMN finding a column already there and our reader interpreting doxygen's
## semantics as ours.
EXTERNAL_ROOT_COLUMN = "dg_external_root"

## WHETHER A `path` ROW IS A FILE OF THIS REPOSITORY AT ALL (gh#335). Doxygen
## registers a `path` row for every `#include` target it cannot resolve, spelled as
## a BARE FILENAME with no directory — `AEEStdDef.h`, `aclnn_add.h` — and those rows
## are neither first party nor attributable to a nested tree we can name.
##
## Measured on entropic: admitting the llama.cpp submodule added 324 such rows, all
## from its Ascend and Hexagon backends, and every one of them counted as FIRST
## PARTY because a bare filename matches no external root. That moved
## `indexed_files` from 488 to 804 on a change that must leave first-party figures
## untouched. The ratios held only because these files do not exist on disk, so the
## line count already excluded them from the substantive set — the invariance was
## being preserved by an accident one layer down, not by the partition.
##
## A separate column from EXTERNAL_ROOT_COLUMN rather than a sentinel value in it:
## "owned by a tree we can name" and "not in this repo" are different facts, and a
## sentinel would put a fake root into every `DISTINCT dg_external_root` listing.
UNRESOLVED_PATH_COLUMN = "dg_unresolved"

SYMBOL_SOURCE = Vocabulary(
    id="symbol_source",
    values=(SYMBOL_SOURCE_DOXYGEN, SYMBOL_SOURCE_AST),
    means="whether a memberdef row was documented by doxygen or recovered by the tree-sitter parser (an 'ast' row has NO brief, no documented parameters and no @req tags)",
    rank={SYMBOL_SOURCE_DOXYGEN: 1, SYMBOL_SOURCE_AST: 0},
)

## CLI-ONLY, like KEY_DIRECTION and STAGE above: these three constrain tokens the
## `clew init` surface accepts and reports, not a column. Registered here
## for the same reason every other enum is — `init` writes into a config file the
## user already owns, and "repo" vs "global" selects WHICH file, so a value
## spelled in two places is a value that can disagree about whose home directory
## gets written to.
INIT_SCOPE_REPO = "repo"
INIT_SCOPE_GLOBAL = "global"

INIT_SCOPE = Vocabulary(
    id="init_scope",
    values=(INIT_SCOPE_REPO, INIT_SCOPE_GLOBAL),
    means="which MCP client config `clew init` registers the server in",
    rank={INIT_SCOPE_REPO: 0, INIT_SCOPE_GLOBAL: 0},
)

## What a merge would do to the target config. 'unchanged' is a first-class
## outcome rather than an absence: re-running `init` on an already-registered
## repo must be observably a no-op, and 'update' is the ONE action that requires
## --force, so collapsing the four into a bool would lose the distinction the
## refusal is built on.
INIT_ACTION_CREATE = "create"
INIT_ACTION_ADD = "add"
INIT_ACTION_UPDATE = "update"
INIT_ACTION_UNCHANGED = "unchanged"

INIT_ACTION = Vocabulary(
    id="init_action",
    values=(INIT_ACTION_CREATE, INIT_ACTION_ADD, INIT_ACTION_UPDATE, INIT_ACTION_UNCHANGED),
    means="what registering the server would do to the target MCP config file",
    rank={
        INIT_ACTION_CREATE: 0,
        INIT_ACTION_ADD: 0,
        INIT_ACTION_UPDATE: 0,
        INIT_ACTION_UNCHANGED: 0,
    },
)

## A doctor check's verdict. Ranked so 'ok' is highest: the exit code is decided
## by the WORST status observed, and a positional ordinal over the declared order
## (ok, warn, fail — the order a human wants to read) would invert that.
CHECK_OK = "ok"
CHECK_WARN = "warn"
CHECK_FAIL = "fail"

CHECK_STATUS = Vocabulary(
    id="check_status",
    values=(CHECK_OK, CHECK_WARN, CHECK_FAIL),
    means="one `clew init` doctor check's verdict; only 'fail' sets a non-zero exit",
    rank={CHECK_OK: 2, CHECK_WARN: 1, CHECK_FAIL: 0},
)

## A Kconfig symbol's declared TYPE (gh#18). Spelled exactly as kconfiglib's own
## `TYPE_TO_STR` spells them, because the value is read straight out of the parser
## and a re-spelling here would be a second vocabulary pretending to be a
## translation. 'unknown' is kconfiglib's own token for a symbol referenced but
## never given a type — a real and common shape in a tree whose sourced files are
## not all present, and one that must be storable rather than dropped, because a
## dropped row is indistinguishable from a symbol that does not exist.
##
## The type is STRUCTURE, not instance. Nothing here records a symbol's RESOLVED
## value: that is a property of one configuration, and gh#18's whole premise is
## that the configuration space and the configuration a build used are different
## facts (the latter lives in `preprocessor.*` / `kconfig.*` build_meta). A
## `default` is part of the space; `y` for this build is not.
KCONFIG_TYPE_BOOL = "bool"
KCONFIG_TYPE_UNKNOWN = "unknown"

KCONFIG_TYPE = Vocabulary(
    id="kconfig_type",
    values=(KCONFIG_TYPE_BOOL, "tristate", "string", "int", "hex", KCONFIG_TYPE_UNKNOWN),
    means="a Kconfig symbol's declared type, as kconfiglib names it ('unknown' means referenced but never typed, not a parse failure)",
    rank={
        KCONFIG_TYPE_BOOL: 0,
        "tristate": 0,
        "string": 0,
        "int": 0,
        "hex": 0,
        KCONFIG_TYPE_UNKNOWN: 0,
    },
)

## HOW a `CONFIG_*` symbol gates a source line (gh#18 part 3). The three forms are
## kept apart because they do not mean the same thing to a consumer asking "what
## does this symbol switch on":
##   - 'ifdef'  — the code is present when the symbol is defined.
##   - 'ifndef' — the code is present when it is NOT, so a reader who conflates the
##     two gets the variant exactly backwards. This is the whole reason the column
##     exists rather than a single 'preprocessor' value.
##   - 'if_expr' — the symbol appears inside a `#if`/`#elif` EXPRESSION
##     (`defined(CONFIG_X)`, `IS_ENABLED(CONFIG_X)`, `CONFIG_X > 2`). The polarity
##     is a property of the expression, which this layer does NOT evaluate, so the
##     honest claim is "this line's presence depends on this symbol" and no more.
##
## Deliberately NOT modelled as a boolean `negated` flag: that would force
## 'if_expr' to pick a polarity it cannot know, which is the wrong-answer-wearing-
## the-shape-of-a-right-one failure this repo keeps finding.
KCONFIG_GATE_IFDEF = "ifdef"
KCONFIG_GATE_IFNDEF = "ifndef"
KCONFIG_GATE_IF_EXPR = "if_expr"

KCONFIG_GATE_FORM = Vocabulary(
    id="kconfig_gate_form",
    values=(KCONFIG_GATE_IFDEF, KCONFIG_GATE_IFNDEF, KCONFIG_GATE_IF_EXPR),
    means="how a preprocessor conditional gates a line on a CONFIG symbol; 'ifndef' inverts the sense and 'if_expr' asserts dependence without a polarity",
    rank={KCONFIG_GATE_IFDEF: 0, KCONFIG_GATE_IFNDEF: 0, KCONFIG_GATE_IF_EXPR: 0},
)

## WHERE A GATING SYMBOL'S NAME IS DECLARED — the gh#390 generalisation.
##
## The gate harvest used to match ONE hardcoded prefix, `CONFIG_`, justified as reading
## Kconfig's own universal convention rather than assuming a repo's shape. True for a
## Kconfig repo, and it made the layer INERT on the dominant C convention: mbedtls gates
## everything on `#if defined(MBEDTLS_THREADING_C)` and declares its space in a checked-in
## `mbedtls_config.h`, so the table existed with the right columns and held ZERO rows on a
## 500-file repository whose whole question is "what is compiled in".
##
## So the harvest records EVERY symbol a preprocessor conditional gates on, and this says
## how that name was accounted for. Classification, never filtering — a repository that has
## adopted nothing still gets a complete gate layer, which is the third-party case the
## declaration model exists to serve.
##   - 'kconfig'    — carries Kconfig's `CONFIG_` prefix.
##   - 'declared'   — named by the target's own preprocessor declaration (a config header
##     or an explicit predefined list). This is the variant the index REPRESENTS.
##   - 'undeclared' — gated on, and named by no declaration this build could see. NOT an
##     error and not noise: it is either a symbol the owner has yet to declare, or dead
##     code behind a symbol nobody can set. Both are findings, and filtering them out
##     would delete the evidence — the same argument the module already made for a gate
##     on a symbol no Kconfig declares.
GATE_ORIGIN_KCONFIG = "kconfig"
GATE_ORIGIN_DECLARED = "declared"
GATE_ORIGIN_UNDECLARED = "undeclared"

GATE_ORIGIN = Vocabulary(
    id="gate_origin",
    values=(GATE_ORIGIN_KCONFIG, GATE_ORIGIN_DECLARED, GATE_ORIGIN_UNDECLARED),
    means="where a gating symbol's name is accounted for; 'undeclared' is a finding about the target, not a defect in the harvest",
    rank={GATE_ORIGIN_KCONFIG: 0, GATE_ORIGIN_DECLARED: 0, GATE_ORIGIN_UNDECLARED: 0},
)

## WHAT AN AGGREGATE SAYS ABOUT ONE RICHNESS LAYER (gh#7). Three states, and the
## distinction between the last two is this project's most-repeated lesson written
## into a vocabulary: **"no rows" is a claim about the DETECTOR until you have read
## the source.**
##   - 'populated' — the table exists and holds rows.
##   - 'empty'     — the table exists and holds NONE. A MEASUREMENT: this index
##     looked and found nothing, which may be a correct negative (a Python repo has
##     no pthreads) or a blind detector (mbedtls's `STORE_SET_*` accessors are
##     macros, 1093 call sites, 0 `memberdef` rows). Either way the consumer knows
##     a detector ran.
##   - 'absent'    — the table is not in this index at all, because the build that
##     wrote it predates the layer. NOT a measurement of the repository, and a
##     consumer that reads it as one concludes a false negative about the code.
## Two states would collapse the last two into "no rows", which is exactly the
## inference gh#7 exists to make unnecessary.
LAYER_STATE_POPULATED = "populated"
LAYER_STATE_EMPTY = "empty"
LAYER_STATE_ABSENT = "absent"

LAYER_STATE = Vocabulary(
    id="layer_state",
    values=(LAYER_STATE_POPULATED, LAYER_STATE_EMPTY, LAYER_STATE_ABSENT),
    means="whether a richness layer holds rows, holds none (a measurement), or is not in this index at all (not a measurement)",
    rank={LAYER_STATE_POPULATED: 2, LAYER_STATE_EMPTY: 1, LAYER_STATE_ABSENT: 0},
)

## THE RICHNESS LAYERS AN AGGREGATE REPORTS ON, in the order a consumer reads them:
## the call graph, then dataflow, then concurrency, then traceability, then the
## derived and doxygen-supplied relations.
##
## These are OUR OWN table names, not a target repo's convention, so enumerating
## them breaks no part of the no-hardcoding mandate — the mandate forbids baking in
## a foreign repo's shape, and this is the shape of the schema this package writes.
## Enumerated HERE rather than in the query module for the reason every other list in
## this file is here: a layer added to the schema and forgotten in the inventory
## reports as `absent` on a current index, which is a false negative that looks like
## a fact. One list, one place to update.
##
## `reimplements` is doxygen's own table, not ours (gh#8) — included because a
## consumer asking "what else does this index hold" needs to see it, and because it
## sat populated and unreachable for as long as nothing enumerated it.
GRAPH_LAYERS: tuple[str, ...] = (
    "call_edges",
    "shared_key_edges",
    "threads",
    "thread_membership",
    "locks",
    "lock_acquisitions",
    "critical_section_calls",
    "external_boundaries",
    "req_edges",
    "req_test_edges",
    "requirements",
    "symbol_liveness",
    "reimplements",
    "file_docs",
    "kconfig_symbols",
    "kconfig_gates",
)

## Every vocabulary by id, so a test (or a generated doc) can enumerate them
## without importing each name.
VOCABULARIES: dict[str, Vocabulary] = {
    v.id: v
    for v in (
        CALL_SOURCE,
        CALL_MATCH,
        KEY_SOURCE,
        KEY_STRENGTH,
        EDGE_KIND,
        DISPATCH_MODE,
        THREAD_KIND,
        THREAD_SOURCE,
        THREAD_STRENGTH,
        MEMBERSHIP_SOURCE,
        LOCK_KIND,
        LOCK_IDENTITY,
        LOCK_SOURCE,
        ACQ_FORM,
        ACQ_ROLE,
        ACQ_MODE,
        ACQ_STRENGTH,
        SECTION_MATCH,
        BOUNDARY_KIND,
        BOUNDARY_SOURCE,
        BOUNDARY_STRENGTH,
        LIVENESS,
        EDGE_CLASS,
        KEY_DIRECTION,
        STAGE,
        INIT_SCOPE,
        INIT_ACTION,
        CHECK_STATUS,
        SYMBOL_SOURCE,
        KCONFIG_TYPE,
        KCONFIG_GATE_FORM,
        GATE_ORIGIN,
        LAYER_STATE,
        DATA_MODEL_DIALECT,
    )
}

## Every CHECK-constrained TEXT column in clew.db, bound to its vocabulary. The
## ONLY way a CREATE TABLE gets an enumerated clause — a raw literal anywhere
## else in the package is a gate failure (tests/test_vocabulary.py).
COLUMNS: dict[tuple[str, str], Vocabulary] = {
    ## The ONE registered column on a table this package does not create. It is added
    ## by `ast_symbols.ensure_symbol_provenance` with `ALTER TABLE ... ADD COLUMN`
    ## against OUR COPY of doxygen's output, carrying
    ## `NOT NULL DEFAULT 'doxygen'` — which retroactively and correctly labels every
    ## row doxygen wrote, with no UPDATE sweep and no window in which a row is
    ## unlabelled. SQLite rewrites the stored CREATE TABLE text, so the CHECK is
    ## visible in `sqlite_master` and the schema-reconcile test sees it like any other.
    ("memberdef", SYMBOL_SOURCE_COLUMN): SYMBOL_SOURCE,
    ("call_edges", "source"): CALL_SOURCE,
    ("call_edges", "confidence"): CALL_MATCH,
    ("symbol_liveness", "status"): LIVENESS,
    ("shared_key_edges", "edge_kind"): EDGE_KIND,
    ("shared_key_edges", "source"): KEY_SOURCE,
    ("shared_key_edges", "confidence"): KEY_STRENGTH,
    ("shared_key_edges", "dispatch_mode"): DISPATCH_MODE,
    ("threads", "kind"): THREAD_KIND,
    ("threads", "source"): THREAD_SOURCE,
    ("threads", "confidence"): THREAD_STRENGTH,
    ("thread_membership", "source"): MEMBERSHIP_SOURCE,
    ("locks", "kind"): LOCK_KIND,
    ("locks", "identity_confidence"): LOCK_IDENTITY,
    ("locks", "source"): LOCK_SOURCE,
    ("lock_acquisitions", "form"): ACQ_FORM,
    ("lock_acquisitions", "role"): ACQ_ROLE,
    ("lock_acquisitions", "mode"): ACQ_MODE,
    ("lock_acquisitions", "confidence"): ACQ_STRENGTH,
    ("critical_section_calls", "resolution"): SECTION_MATCH,
    ("external_boundaries", "kind"): BOUNDARY_KIND,
    ("external_boundaries", "source"): BOUNDARY_SOURCE,
    ("external_boundaries", "confidence"): BOUNDARY_STRENGTH,
    ("kconfig_symbols", "type"): KCONFIG_TYPE,
    ("kconfig_gates", "form"): KCONFIG_GATE_FORM,
    ("kconfig_gates", "origin"): GATE_ORIGIN,
    ("data_model_keys", "dialect"): DATA_MODEL_DIALECT,
}

## 0/1 integer columns. Registered separately because `validated()` is
## meaningless for them — they are ints, and Python's bool coercion, not a
## vocabulary, is what keeps them in range.
BOOL_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {
        ("shared_key_edges", "declared"),
        ("shared_key_edges", "edge_triggered"),
        ("shared_key_edges", "crosses_thread"),
        ("lock_acquisitions", "declared"),
        ("data_model_keys", "helpers"),
        ("data_model_keys", "listed"),
        ("data_model_keys", "observed"),
    }
)

## R2 wire fields (dataclass, field) → the vocabulary their value is drawn from,
## so R3 can surface `means` in a tool description. Keyed by dataclass because
## `COLUMNS` is keyed by DB table and the two namespaces do not coincide:
## `KeyEdge.source` carries `key_source` while a `call`-class row carries
## `call_source`.
##
## `CallEdge` and `Hop` are the two MERGED shapes (#46): one row carries either a
## call neighbour or a shared-key neighbour, discriminated by `edge_class`. Their
## `source` is therefore the ONE genuinely edge_class-conditional field —
## `call_source` on a 'call' row, `key_source` on a 'key' row — so it is
## deliberately NOT registered here rather than registered as half-true. Every
## other field is unconditional because the merge SPLIT the collision instead of
## overloading it: `confidence` (call_match) is None on a key row and `strength`
## (key_strength) is None on a call row, so each name maps to exactly one
## vocabulary. That split is why `("Hop","confidence"): CALL_MATCH` is now
## accurate — before it, a key hop put `key_strength` values in that same field.
FIELDS: dict[tuple[str, str], Vocabulary] = {
    ("CallEdge", "edge_class"): EDGE_CLASS,
    ("CallEdge", "confidence"): CALL_MATCH,
    ("CallEdge", "strength"): KEY_STRENGTH,
    ("CallEdge", "edge_kind"): EDGE_KIND,
    ("CallEdge", "dispatch_mode"): DISPATCH_MODE,
    ("KeyEdge", "source"): KEY_SOURCE,
    ("KeyEdge", "confidence"): KEY_STRENGTH,
    ("KeyEdge", "edge_kind"): EDGE_KIND,
    ("KeyEdge", "dispatch_mode"): DISPATCH_MODE,
    ("Hop", "edge_class"): EDGE_CLASS,
    ("Hop", "confidence"): CALL_MATCH,
    ("Hop", "strength"): KEY_STRENGTH,
    ("Hop", "edge_kind"): EDGE_KIND,
    ("Hop", "dispatch_mode"): DISPATCH_MODE,
}


## @brief The CHECK clause for one registered enumerated column.
## @param table Table the column belongs to.
## @param column Column name.
## @return A `CHECK(col IN (...))` fragment ready to splice into a CREATE TABLE.
## @version 1
## @req REQ-DDB-SCHEMA-012
def check(table: str, column: str) -> str:
    """Raises rather than returning an empty string for an unregistered column:
    a silently-absent CHECK is the exact hole this module exists to close.

    @brief Look up a column's vocabulary and generate its CHECK clause.
    @version 1
    """
    vocab = COLUMNS.get((table, column))
    if vocab is None:
        raise KeyError(f"no vocabulary registered for {table}.{column} — add it to COLUMNS")
    return vocab.check(column)


## @brief The CHECK clause for a 0/1 integer column.
## @param column Column name.
## @return A `CHECK(col IN (0,1))` fragment.
## @version 1
## @req REQ-DDB-SCHEMA-012
def bool_check(column: str) -> str:
    """Separate from `check` because booleans are ints with no vocabulary; the
    (table, column) pairs are still registered in `BOOL_COLUMNS` so the schema
    reconcile test can account for every CHECK the shipped database carries.

    @brief Generate the 0/1 CHECK clause for a boolean column.
    @version 1
    """
    return f"CHECK({column} IN (0,1))"


## THE SEARCH RANKING WEIGHTS — one definition, two consumers.
##
## `query.symbols._search_rank` scores a candidate with these, and the static
## explorer's client-side JavaScript has to score identically or the two surfaces
## disagree about relevance. Until this constant existed the JS carried its own
## hand-copied literals, and `htmlview_assets.py`'s own comment admitted the
## consequence: "issue #45 verbatim, reintroduced in JavaScript months after it was
## fixed in Python... Keep the two rankings in step by hand."
##
## Hand-keeping is exactly the discipline a gate is supposed to replace, and no test
## could catch the drift because nothing in this repo executes JavaScript. So the JS
## is now GENERATED from these values: a weight change reaches the artifact
## automatically, and there is no second place to forget.
##
## Lives in `vocabulary.py` because that is already where definitions both halves
## need are kept (the `VIEWER_*` constants above), and because it is a true leaf —
## `query/` and the view layer can both import it without either depending on the
## other.
SEARCH_WEIGHT_EXACT_NAME = 1000
SEARCH_WEIGHT_NAME_SUBSTRING = 200
SEARCH_WEIGHT_TOKEN_IN_NAME = 50
SEARCH_WEIGHT_TOKEN_IN_BRIEF = 5
