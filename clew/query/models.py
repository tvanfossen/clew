# SPDX-License-Identifier: MIT
"""R2 query-library return types: frozen, JSON-serializable dataclasses.

Every public query function in this package returns one of these (or a
list of them), NEVER a raw sqlite row and NEVER rendered HTML. R3 (MCP)
serializes them with `dataclasses.asdict`; R4 (HTML) renders them. Edge
endpoints are always resolved to NAMES here — consumers want names, not
rowids. The `rowid` field is INTERNAL and is stripped at the wire boundary: nothing
on the tool surface accepts one as input, and published beside real line numbers it produced
a fabricated `file:2244` citation in a graded answer.

@brief Frozen dataclass return types for the R2 query library.
@version 1
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field

from ..vocabulary import (
    GATE_ORIGIN_UNDECLARED,
    LAYER_STATE_ABSENT,
)

## WHAT `provenance` MEANS ON EVERY SYMBOL-SHAPED ROW BELOW (gh#11).
##
## `None`/absent — doxygen documented this symbol, which is the norm, so the field
## says nothing and `wire._absent` elides it.
##
## `'ast'` — the tree-sitter parser recovered this symbol from the source text
## because doxygen never emitted it (its code sat behind an unsatisfied
## preprocessor guard). The row's name, file, line span and static-ness are real.
## Its brief, its documented parameters and its `@req` tags DO NOT EXIST, because a
## preprocessor that skipped the code skipped its doc comment too — an empty brief
## on such a row means "unparsed", not "undocumented", and that distinction is the
## whole reason the field is here.
##
## On a composite payload (`Dossier`) the field describes the row whose LOCATION is
## reported. A non-empty `brief` beside `provenance: 'ast'` is not a contradiction:
## it means doxygen documented the DECLARATION in a header it could read, and the
## parser recovered the DEFINITION doxygen could not. See `dossier._identity`.


## @brief One of several same-named function definitions (overload/duality).
## @version 2
@dataclass(frozen=True)
class Candidate:
    """A single memberdef row backing a name that resolves ambiguously. The
    signature (doxygen's `definition`) is what distinguishes overloads a bare
    name cannot — e.g. `react` maps to 37 distinct FSM-state signatures.

    `qualified` IS THE FIELD A CONSUMER PASSES BACK (gh#37), as the `qualified=`
    argument of `resolve_symbol` / `dossier` / `callers` / `callees` / `source` /
    `overrides_of` / `overridden_by`. This docstring used to name the `file`
    substring instead, and no accessor accepted one — a promise in a docstring the
    API did not keep, which is the whole of gh#37. It says `qualified` now because
    `qualified` is what those accessors take; do not reword this to name a field
    without checking that the accessors still accept it.

    Why the qualified name and not `rowid` or `file`, and what it cannot select:
    see `_common.matching_identity`. `file` and `line_start` remain what they always
    were — where to LOOK — and stay useful for a human reading the list.

    @brief One same-named function candidate (signature + identity + location).
    @version 3
    """

    rowid: int
    signature: str
    file: str
    line_start: int | None
    has_body: bool
    provenance: str | None = None
    ## Defaulted so a hand-constructed Candidate in a test stays valid, NOT because an
    ## empty value is acceptable on a real row: `candidate_rows` always sets it, and
    ## `_common.candidate_rows` takes the bare name as a required argument precisely so
    ## it cannot be forgotten.
    qualified: str = ""


## @brief Definition-preferring reference to one resolved symbol.
## @version 2
@dataclass(frozen=True)
class SymbolRef:
    """A function resolved definition-preferring (decl/def duality): its
    canonical rowid, name, kind, and source location. When the name maps to
    MORE THAN ONE distinct signature, `candidates` is non-empty and lists the
    alternatives (capped) so the consumer knows the primary pick was one of
    several and can re-query a specific one; it stays empty for unambiguous
    names, so existing single-result behaviour is unchanged.

    @brief Resolved symbol reference (rowid + name + location + overloads).
    @version 3
    """

    name: str
    rowid: int
    kind: str
    file: str
    line_start: int | None
    line_end: int | None
    candidates: list[Candidate] = field(default_factory=list)
    provenance: str | None = None


## @brief A name+brief search hit.
## @version 2
@dataclass(frozen=True)
class SymbolHit:
    """One search result: symbol name, kind, file, and (stripped) brief.

    A hit whose `provenance` is 'ast' has an EMPTY brief by construction and still
    ranks — `_search_rank` scores the name too — so a parser-recovered symbol is
    findable by name without pretending to have prose.

    `also_in` NAMES THE OTHER FILES THAT DECLARE THE SAME NAME, and it exists because a
    silent pick is only safe when the caller can tell a pick was made. `search` collapses
    per NAME, keeping doxygen's row over a recovered one so a bare recovered row can never
    hide a documented one — correct in general, and MEASURED WRONG in one real case:
    after gh#395 recovered mbedtls's guarded `mbedtls_threading_mutex_t`, the surviving row
    was the TEST FIXTURE at `tests/include/alt-dummy/threading_alt.h` and the dropped one
    was the shipping type at `include/mbedtls/threading.h`.

    Disclosing rather than re-ranking, deliberately. Inverting the order would let every
    bare recovered row hide a documented one, which is the defect the order prevents; and
    "prefer a non-test path" would hardcode a convention this project forbids assuming.
    Empty when the name is unambiguous, so the common reply is unchanged.

    @brief Search hit (name / kind / file / brief / other files with the same name).
    @version 3
    """

    name: str
    kind: str
    file: str
    brief: str
    provenance: str | None = None
    also_in: tuple[str, ...] = ()


## @brief One causal neighbour of a function (a call OR a dataflow endpoint).
## @version 4
@dataclass(frozen=True)
class CallEdge:
    """One neighbour of a focal function, in ONE of two classes, discriminated
    by `edge_class` (#46):

    - `'call'` — a direct call edge. `source` is a `call_source` layer,
      `confidence` is a `call_match`, and every key-only field is None. A call
      is ALWAYS synchronous and stays on the caller's thread.
    - `'key'` — a shared-key dataflow edge: this function writes a key that
      neighbour reads (or vice versa) with NO call connecting them. `source` is
      a `key_source`, `confidence` is None and the row's certainty lives in
      `strength` (a `key_strength`), and `key_name`/`edge_kind`/`dispatch_mode`/
      `edge_triggered`/`crosses_thread`/`to_thread` carry the R1 semantics.
      Such a hop may be asynchronous and may land on another thread.

    `edge_class` is REQUIRED and has no default on purpose: a defaulted tag
    means any future construction site that forgets it silently claims `'call'`,
    which is exactly the misreading the tag exists to prevent.

    `confidence` and `strength` are SPLIT rather than sharing one field because
    they are different vocabularies — `exact/resolved/fuzzy` vs `low/medium/high`
    — and a consumer filtering on `confidence != 'fuzzy'` would otherwise
    silently admit or reject every dataflow row depending on how it compared.

    ONE ROW PER ENDPOINT (#38), because one logical edge is genuinely stored once
    per layer — `UNIQUE(caller_rowid, callee_rowid, source)` makes `source` part
    of the key by design. On clew's own index every call edge is found by
    both doxygen layers (520 rows / 260 distinct pairs), so before the collapse
    every neighbour list was inflated 2x and every depth cap truncated half as
    many real edges as intended. `source`/`confidence` describe the STRONGEST
    evidence found for the endpoint.

    @brief Name-resolved causal neighbour (call edge or shared-key dataflow).
    @version 5
    """

    name: str
    rowid: int
    source: str
    confidence: str | None
    edge_class: str
    strength: str | None = None
    key_name: str | None = None
    edge_kind: str | None = None
    dispatch_mode: str | None = None
    edge_triggered: bool | None = None
    crosses_thread: bool | None = None
    to_thread: str | None = None
    ## THE KNOWN IMPLEMENTORS OF A VIRTUAL ENDPOINT (gh#8), from doxygen's own
    ## `reimplements` relation. Present only on a `'call'` row whose endpoint is
    ## reimplemented by something; empty everywhere else, and an empty tuple is a
    ## truthful statement — the relation names no override.
    ##
    ## An ANNOTATION, NOT A SYNTHETIC EDGE, and the distinction is deliberate. This
    ## repo's rule is that a synthetic edge inherits the WEAKEST link, so minting a
    ## `declared_dispatch`-style row from a fuzzy call plus an override relation would
    ## have to be graded down and would then propagate through the reachability and
    ## thread BFS as a premise. Naming the implementors beside the existing edge makes
    ## no claim about which one runs — it says "if this dispatches virtually, these are
    ## the bodies it can reach" — and asserts nothing the relation does not already
    ## state. `confidence` therefore describes the CALL, exactly as before, and is not
    ## upgraded by the presence of this field.
    implementors: tuple[str, ...] = ()
    ## THE MACRO THAT MAKES THIS HOP EXIST, and its expansion (gh#350). Set only when a
    ## `macro_hop` row was composed for this pair — the one layer whose edge corresponds to NO
    ## text in the caller's body, because the call is written as a macro invocation. Without it a
    ## caller sees an edge at confidence `resolved` and cannot see what produced it.
    ##
    ## PUBLISHED, NOT INTERPRETED. The expansion is doxygen's own `memberdef.initializer`, quoted
    ## verbatim; nothing here infers what the macro is FOR. That is the deliberate opposite of the
    ## rejected auto-discovery direction, which tried to derive a role from the expansion and
    ## could not — `do { } while (0)` is a disabled trace macro AND a compiler hint AND a
    ## portability stub, and only the reader can tell which.
    ##
    ## `via_macro` set with `via_macro_expansion` EMPTY means doxygen recorded no expansion for
    ## that macro (17-20% of macro rows on the measured targets), which is a different answer from
    ## "no macro" and is why the two fields are separate.
    ##
    ## ONE WITNESS, NOT THE ONLY ONE: `UNIQUE(caller_rowid, callee_rowid, source)` holds one
    ## macro-hop row per pair, so a pair reachable through two macros names the lowest-rowid one.
    via_macro: str = ""
    via_macro_expansion: str = ""


## @brief One end of doxygen's `reimplements` relation, name-resolved.
## @version 1
@dataclass(frozen=True)
class OverrideRef:
    """A virtual-dispatch counterpart (gh#8): the base method a function
    reimplements, or a derived method that reimplements it.

    `reimplements` is doxygen's OWN table — it is signature-aware and it is the only
    thing in the index that knows which concrete implementation a virtual call can
    reach. It was populated and read by nothing outside `dispatch_edges.py`, so a
    consumer could not answer the question C++ polymorphism makes unavoidable: what
    actually runs when this dispatches.

    `signature` is doxygen's `definition` string, which is what distinguishes two
    overrides of the same name on different classes — the whole reason a bare name is
    not enough here. `file`/`line_start` locate the implementation so a consumer can
    read it without a second lookup.

    @brief Override counterpart (base reimplemented, or derived reimplementing).
    @version 1
    """

    name: str
    rowid: int
    signature: str
    file: str
    line_start: int | None


## @brief One shared-key dataflow edge, name-resolved, with R1 semantics.
## @version 1
@dataclass(frozen=True)
class KeyEdge:
    """A shared-key write/read relationship as seen from one focal function:
    `other` is the counterpart (the reader for a write, the writer for a
    read). Carries the full R1 semantic label set: dispatch_mode / edge_kind
    / edge_triggered plus the computed thread-boundary flags.

    @brief Shared-key dataflow edge with R1 dispatch/thread semantics.
    @version 1
    """

    key_name: str
    edge_kind: str
    other: str
    other_rowid: int
    source: str
    confidence: str
    dispatch_mode: str
    edge_triggered: bool | None
    crosses_thread: bool | None
    to_thread: str | None


## @brief One function→requirement edge (an @req-tagged implementer link).
## @version 1
@dataclass(frozen=True)
class ReqEdge:
    """A requirement-traceability edge as an absolute fn -> req_id pair — the
    whole-graph form the HTML db-explorer consumes.

    NO confidence field. `[inferred]` was retired 2026-07-30 (owner: "they should
    simply be the stated ID, inferred is noise"), so every edge is an author-written
    tag and a column that can hold only one value states nothing.

    @brief Absolute fn → requirement traceability edge.
    @version 1
    """

    fn: str
    req_id: str


## @brief A thread (spawn-harvested or declared) with member count.
## @version 1
@dataclass(frozen=True)
class Thread:
    """One thread: id, name, kind, its entry function name (None when the
    entry is macro-hidden / unresolved), provenance, confidence, and the
    number of functions in its call-closure membership.

    @brief Thread record (identity + entry + member count).
    @version 1
    """

    id: int
    name: str
    kind: str
    entry: str | None
    source: str
    confidence: str
    member_count: int
    ## WHERE THE THREAD IS CREATED, which is a different question from what it RUNS (gh#346).
    ## `entry` answers the second and is legitimately None: the entry NAME is read off the spawn
    ## call, but resolving it to a rowid fails closed when a member-function pointer names a
    ## class this index does not cover (`&TxPump::run` with TxPump unindexed) or when a bare
    ## entry name is not uniquely indexed — NULL beats borrowing a same-named method on another
    ## class. The spawn site is never unknown, because it is where the spawn construct was
    ## matched, so it is the anchor that makes a thread attributable at all. Empty only on an
    ## index predating build version 35.
    spawn_file: str = ""
    spawn_line: int | None = None
    ## WHO creates the thread — the name of the function the spawn call sits in, "" when the index
    ## predates build 48 or the spawn is at file scope. `spawn_file`+`spawn_line` gave an agent a
    ## COORDINATE and no name to ask a follow-up about, so it read the file instead: measured on
    ## mbedtls, the answer is `thread_create`, and `dossier('thread_create')` returns the shared
    ## state, the `pthread_join` and the guard that four graded marks ask for.
    spawn_function: str = ""
    ## '' for first party, else the external root owning the SPAWN SITE. Defaults first party
    ## for the same reason `LockEntry.external_root` does.
    external_root: str = ""


## @brief Every thread in the index, with the origin split beside it.
## @version 1
@dataclass(frozen=True)
class ThreadInventory:
    """AN ENVELOPE RATHER THAN A BARE LIST, so the roster can REPORT its split instead of
    merely making it derivable (gh#346 + REQ-DDB-QUERY-011). `lock_roster` already carried a
    file on every row, so a caller could at least do the arithmetic by hand; `threads` could
    not, because a row with a NULL entry had no file at all — and those NULL-entry rows were
    exactly the mis-attributed ones. Measured on entropic: 12 rows, 2 of them anchored to
    nothing.

    THE SPLIT IS OVER THREADS, one member per row, because a thread IS the unit here — there is
    no collapse of the kind that makes `lock_roster` split `distinct_mutexes` instead of `rows`.

    @brief The thread roster plus its first-party/external/unresolved split.
    @version 1
    """

    threads: tuple[Thread, ...]
    rows: int
    row_meaning: str
    origin: OriginSplit = field(
        default_factory=lambda: OriginSplit(total=0, first_party=0, external=0, unresolved=0)
    )


## @brief One call site inside a critical section.
## @version 1
@dataclass(frozen=True)
class SectionCall:
    """A call that runs while a lock is held.

    `callee` is always the name; `resolution` says whether it pinned a single
    in-repo function ('resolved'), matched several ('ambiguous') or has no
    memberdef at all ('external' — stdlib, vendor or macro). An ambiguous name
    is ONE row with no rowid, never one row per candidate: a call site is a
    physical location and fanning it out would answer "what runs under this
    lock" with several functions where one runs.

    @brief A call inside a lock hold, with how well its callee resolved.
    @version 1
    """

    callee: str
    line: int
    resolution: str


## @brief One critical section: an acquisition plus what runs inside it.
## @version 1
@dataclass(frozen=True)
class CriticalSection:
    """A hold of one lock by one function, with the calls that run inside it.

    `end_line` is None exactly when the extent could not be resolved, and
    `calls` is then EMPTY — L2 fails closed rather than reporting a partial
    membership under an unknown extent. `confidence` grades the EXTENT (an
    `acq_strength` member), not the lock's identity, which travels separately on
    `lock_scope`: a bare `mutex_` recurs across many classes, so the scope is
    part of the answer rather than decoration.

    @brief A lock hold: where, how far, and what runs inside.
    @version 1
    """

    lock: str
    lock_scope: str
    lock_kind: str
    holder: str
    file: str
    start_line: int
    end_line: int | None
    form: str
    mode: str
    confidence: str
    calls: tuple[SectionCall, ...]


## @brief A lock held while another is taken, across a call.
## @version 1
@dataclass(frozen=True)
class LockNesting:
    """Two locks held simultaneously because a critical section spans a call
    into a function that takes a second lock.

    This is the observation L1 could not make. Within a single function the
    real codebases showed ZERO simultaneous two-lock holdings; the real ones
    are CROSS-FUNCTION and only become visible once membership exists. Reported
    as an ordered pair (outer taken first) because that order — not the mere
    fact of nesting — is what a future deadlock check compares across sites.

    @brief An outer→inner lock pair observed across a call.
    @version 1
    """

    outer: str
    outer_scope: str
    inner: str
    inner_scope: str
    via: str
    holder: str
    file: str
    line: int
    ## HOW MUCH THE `via` CALL IS WORTH, and the reason this field exists rather than the
    ## nesting being filtered. A nesting is only as good as the call that creates it: when
    ## `via` was `x.f()`, the receiver was unwrapped away and one indexed `f` is a fact about
    ## the index, not the call. Measured on the public entropic index: 13 of 17 nestings rest
    ## on such a call — `router_dirty_.store(...)` is `std::atomic::store` read as
    ## `PromptCache::store`. Dropping them was tried and took the layer to ZERO rows, because
    ## the one GENUINE nesting is a member call too. So they are reported WITH their weakness
    ## and the consumer weighs them: 'resolved' means the call site named it outright.
    via_resolution: str = ""


## @brief One outer→inner lock pair, collapsed across every site that creates it.
## @version 1
@dataclass(frozen=True)
class LockNestingPair:
    """A nesting IDENTITY: the ordered pair, with how many call sites produce it and one
    exemplar site to read.

    THE SAME ROW-COUNT-IS-NOT-IDENTITY-COUNT TRAP `LockInventory` EXISTS TO FIX, one layer
    over. Measured on the public entropic index, `lock_nestings` returns 26 rows over
    **12 distinct (outer, inner) pairs** — four sites for the busiest pair — and a caller
    told "26 nestings" will report 26 where the honest figure is 12. The deadlock question
    is about PAIRS: a risk is two sites taking the SAME pair in OPPOSITE orders, so the
    pair set is the answer and the site list is supporting evidence.

    IT IS ALSO WHAT MAKES THE FOLD FIT. `lock_roster` on entropic is already near the
    response cap, so carrying 26 site rows would have trimmed the payload and lost pairs;
    carrying 12 pair rows loses none. A collapse that saves a round trip by dropping the
    answer would be a regression dressed as an optimisation — this drops duplicate
    evidence for a pair the caller still receives, and says how many it dropped.

    `resolved_sites` IS CARRIED PER PAIR because the weakness does not distribute evenly.
    A nesting is only as good as the call that creates it, and measured on entropic 19 of
    26 sites rest on a member call whose receiver was never verified. A pair with four
    sites of which none are resolved is a different claim from one with a resolved site,
    and collapsing to a bare pair count would erase that distinction. The full site list
    stays available from the query library's `lock_nestings`.

    @brief An outer→inner pair with its site count, evidence strength and one exemplar.
    @version 1
    """

    outer: str
    outer_scope: str
    inner: str
    inner_scope: str
    ## How many call sites produce this pair. 1 is the common case; >1 is corroboration.
    sites: int
    ## How many of those sites named the callee outright (`via_resolution == 'resolved'`).
    ## ZERO IS THE INTERESTING VALUE and it is an int rather than a bool so it survives
    ## `_absent` — `0` is a measurement, and a pair resting entirely on unverified
    ## receivers is exactly what a caller must not quote as a confirmed nesting.
    resolved_sites: int
    ## One site to go and read. Chosen as the first RESOLVED site when the pair has one,
    ## so the exemplar is the strongest evidence rather than an arbitrary row.
    via: str
    holder: str
    file: str
    line: int


## @brief One lock in the inventory, with how much of the layer rests on it.
## @version 1
@dataclass(frozen=True)
class LockEntry:
    """A row of the lock inventory: an identity, where it is declared, and how
    many acquisition sites it has.

    ONE ROW IS ONE IDENTITY, WHICH IS NOT ONE MUTEX. The `locks` table is keyed
    `UNIQUE(name, scope, kind)`, so a `std::shared_mutex` taken with both
    `lock_guard` and `shared_lock` occupies TWO rows — the split errs toward
    over-counting on purpose, because a fabricated shared lock is
    indistinguishable from real synchronisation while a split one is merely
    redundant. `LockInventory` carries the collapsed count beside the rows for
    exactly this reason; see the note there.

    `acquisitions` is included because it is the field that makes the inventory
    ACTIONABLE rather than merely complete. "Which mutex is heavily used" is the
    normal follow-up to "list the mutexes", and without a count per lock a
    caller answers it by calling `runs_under_lock` once per lock — trading one
    round trip for N, which is the shape this model exists to remove.

    @brief One lock identity with its declaration site and acquisition count.
    @version 1
    """

    name: str
    scope: str
    kind: str
    identity_confidence: str
    source: str
    file: str
    line: int | None
    acquisitions: int
    ## DEFAULTS TO FIRST PARTY, and `path_resolved` defaults True, for the same reason
    ## `coverage.FileRow` does: a hand-built row and an index predating gh#335 must both read as
    ## "this is ours" rather than as an accidental external tag. An index below build version 32
    ## has no such column AND excluded nested trees outright, so first party is not merely the
    ## safe default there — it is the correct answer.
    external_root: str = ""
    ## False when the lock's declaring file did not resolve to a `path` row. Kept SEPARATE from
    ## `file == ''`, because an empty file string is also what a missing declaration line looks
    ## like, and the origin split needs "unknown whose" to be distinguishable from "ours".
    path_resolved: bool = True


## @brief One roster's population, decomposed by whose code it is.
## @version 1
@dataclass(frozen=True)
class OriginSplit:
    """THE ONE CONTRACT EVERY ROSTER REPORTS (gh#352). `first_party` + `external` +
    `unresolved` == `total`, always, and the sum is asserted rather than assumed.

    WHY A ROSTER'S HEADLINE NUMBER IS NOT USABLE WITHOUT THIS. Measured on the public
    [tvanfossen/entropic](https://github.com/tvanfossen/entropic) index: `lock_roster` reported
    97 distinct mutexes and told the caller to quote that as the mutex count, while 52 of the 97
    belong to the vendored `extern/llama.cpp` submodule. So the tool's own payload instructed a
    caller to attribute the majority of another repository's locks to entropic. The rubric had
    started COMPENSATING for it — widening a mark to accept 97 "when attributed and split" — which
    is the tool teaching the grader to accept its defect.

    NOTHING IS FILTERED. The split is reported BESIDE the full roster, never applied to it. An
    answer that silently omitted external rows would be the filtered-answer-that-reads-as-an-
    empty-answer failure, which is the thing the emptiness notes exist to prevent, and it would
    also make a `chain_trace` into a submodule inexplicable.

    `unresolved` is its own bucket and not folded into either side, because "we do not know whose
    this is" is a different claim from "it is ours". Folding it into `first_party` is how a
    coverage figure comes to look healthier than the evidence supports.

    @brief A roster population split into first-party, external and unresolved.
    @version 1
    """

    total: int
    first_party: int
    external: int
    unresolved: int
    external_roots: tuple[str, ...] = ()

    ## @brief Classify roster members by whose code they are.
    ## @param origins One entry per member: the external root, '' for first party, None when the
    ##        member has no resolved file at all.
    ## @return The three buckets plus the external roots seen.
    ## @version 1
    ## @req REQ-DDB-QUERY-011
    @classmethod
    def of(cls, origins: Iterable[str | None]) -> OriginSplit:
        """ONE PLACE THAT DECIDES THE BUCKETS, because gh#352 is a contract rather than a fix to
        one roster. A second roster computing its own split is how two payloads come to disagree
        about the same index, and that disagreement would read as a data problem rather than as a
        duplicated rule. It lives ON the type instead of in `_common` because `_common` is
        stdlib-only by design and this needs the dataclass at runtime.

        THE ARITHMETIC IS CHECKED, NOT ASSUMED. A caller's whole reason to trust a split is that
        the buckets account for the total; a silently lossy classification would report plausible
        thirds that omit rows, which is worse than no split at all because it reads as a
        measurement. The check costs nothing and cannot be phrased around.

        THE THREE-WAY DISTINCTION MAPS ONTO THE SCHEMA. `''` is a resolved first-party file; a
        non-empty string is the external root that owns it; `None` is a member whose file is not
        resolved at all — doxygen's bare-filename `#include`s — and it stays its own bucket,
        because "unknown" is not "ours".

        @brief Build a split from per-member origins.
        @return The split.
        @version 1
        """
        seen = list(origins)
        external = [o for o in seen if o]
        unresolved = [o for o in seen if o is None]
        split = cls(
            total=len(seen),
            first_party=len(seen) - len(external) - len(unresolved),
            external=len(external),
            unresolved=len(unresolved),
            external_roots=tuple(sorted(set(external))),
        )
        if split.first_party + split.external + split.unresolved != split.total:
            raise AssertionError(
                f"OriginSplit lost rows: {split.first_party}+{split.external}+"
                f"{split.unresolved} != {split.total} — a split that does not account for the "
                f"whole roster is worse than none, because it reads as a measurement"
            )
        return split


## @brief Every lock in the database, the count that is NOT the row count, and the nestings.
## @version 2
@dataclass(frozen=True)
class LockInventory:
    """The whole lock layer in one answer, and the arithmetic a consumer needs
    in order not to misreport it.

    THIS TYPE EXISTS BECAUSE THE OBVIOUS SHAPE IS A TRAP. A bare list of rows
    invites "the codebase has len(rows) mutexes", and that is wrong whenever any
    lock is taken with two guard kinds — measured on a real C++ target, 56 rows
    stood for 52 distinct mutexes. An acceptance rubric grades refusing that
    conflation, so a tool returning only rows would have made its own graded
    error easier to commit, not harder.

    So both numbers ship, named for what they mean: `rows` is the identity count
    and `distinct_mutexes` collapses on (name, scope). `row_meaning` states both
    in one sentence, so a figure quoted out of this payload arrives with its
    qualifier attached — the same device `graph_stats.row_meaning` uses, for the
    same reason.

    IT CARRIES THE NESTINGS TOO, AND THAT IS A ROUND-TRIP DECISION RATHER THAN A
    MODELLING ONE. `lock_nestings` was a separate MCP tool reading the SAME two
    tables — a derived view of this inventory's own acquisitions, joined to itself
    across a call. Measured on the acceptance mbedtls index it returned ZERO rows and
    was called anyway in 3 of 3 observed runs, because nothing in the roster said the
    follow-up was pointless. Now the roster says so: `nestings` is present and empty,
    and `nesting_meaning` states what empty means. An inventory question costs one
    call.

    THE BYTES ARE NOT WHY. Measured: the fold adds 2 bytes on mbedtls and 6,975 on
    entropic, against a call that cost those same bytes plus a round trip. The saving
    is the round trip — at the observed 33,069 tokens per tool call, one deterministic
    call is worth ~275x the entropic payload growth.

    @brief The lock inventory plus the collapsed mutex count and the nestings.
    @version 2
    """

    locks: tuple[LockEntry, ...]
    rows: int
    distinct_mutexes: int
    row_meaning: str
    ## Outer -> inner pairs held simultaneously because a section spans a call, COLLAPSED ON
    ## IDENTITY the way `distinct_mutexes` collapses the locks — see `LockNestingPair`, which
    ## says why the pair and not the site is the unit here. PRESENT AND EMPTY when there are
    ## none, never elided: `wire.one` keeps every envelope key, and an absent key would read
    ## as "not measured" — which is the state that made the separate call look worth paying
    ## for. Defaulted so a hand-built inventory stays constructible.
    nestings: tuple[LockNestingPair, ...] = ()
    ## What the nesting count means, including what ZERO means. Same device as `row_meaning`:
    ## a figure lifted out of this payload arrives with its qualifier attached.
    nesting_meaning: str = ""
    ## Splits `distinct_mutexes` — the number `row_meaning` tells a caller to quote — not `rows`.
    ## Defaults to an empty split so a hand-built inventory stays constructible.
    origin: OriginSplit = field(
        default_factory=lambda: OriginSplit(total=0, first_party=0, external=0, unresolved=0)
    )


## @brief The out-of-repo causal terminus a chain dead-ends at.
## @version 1
@dataclass(frozen=True)
class Terminus:
    """An external boundary: an in-repo function invokes `global_name`, a
    callback registered (typically at `registered_by`) but bound to an
    out-of-repo supplier — the library boundary a causal chain completes at.

    @brief External-boundary terminus (global + registrar + kind).
    @version 1
    """

    global_name: str
    registered_by: str | None
    kind: str


## @brief A requirement id + human title.
## @version 1
@dataclass(frozen=True)
class ReqRef:
    """A requirement reference: its id and (possibly empty) title.

    @brief Requirement id + title.
    @version 1
    """

    req_id: str
    title: str


## @brief One requirement implementer with its liveness.
## @version 1
@dataclass(frozen=True)
class Implementer:
    """A function implementing a requirement: name, canonical rowid, the
    @req tag confidence, and its symbol-liveness status ('' when unknown).

    @brief Requirement implementer (name + confidence + liveness).
    @version 1
    """

    name: str
    rowid: int
    liveness: str


## @brief Requirement traceability result.
## @version 1
@dataclass(frozen=True)
class ReqTrace:
    """One requirement's full trace: its metadata, the functions that
    implement it (with liveness), and the covering test functions.

    @brief Requirement trace (metadata + implementers + tests).
    @version 1
    """

    req_id: str
    block: str
    title: str
    acceptance: str
    priority: str
    implementers: list[Implementer] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)


## @brief A bounded verbatim excerpt of one function's body.
## @version 2
@dataclass(frozen=True)
class BodyExcerpt:
    """The function's own source text, carried INSIDE the dossier so that
    "what does it actually do" does not cost a second call.

    Deliberately NOT a `SourceListing`: that model repeats the name, the
    overload candidates and the provenance, all of which the enclosing dossier
    already states, and a one-shot payload cannot afford to say anything twice.

    `truncated` is the load-bearing field. A silently clipped body is worse than
    no body at all — a reader who cannot see that lines were dropped will reason
    about a function it has only half read — so `total_lines` reports the body's
    FULL extent beside the `start_line`..`end_line` actually included, and
    `truncated` is a measurement that survives being `false`.

    @brief Bounded function body with explicit truncation and anchor measurements.
    @version 2
    """

    file: str
    start_line: int
    end_line: int
    total_lines: int
    truncated: bool
    lines: tuple[str, ...] = ()

    ## THE SECOND LOAD-BEARING FIELD, and it exists because a body LOOKS LIKE PROOF. The lines
    ## are read from the LIVE working tree at the span the index recorded, so a file edited since
    ## the build hands back whatever now occupies those line numbers — another function's source,
    ## under this function's heading, with `start_line`/`end_line` self-consistent and
    ## `total_lines` matching. Nothing in the payload contradicted it.
    ##
    ## Measured while fixing something else: a dossier reported `line_start: 896` and returned 55
    ## lines of a DIFFERENT function, and the reader went and read the file instead — which is a
    ## miss the tool caused and then concealed.
    ##
    ## `false` IS A MEASUREMENT AND ALWAYS TRAVELS. The lines are still returned when this is
    ## true, because withholding evidence is worse than labelling it; what must never happen is
    ## returning them unlabelled. A stale-index warning elsewhere in the envelope does not
    ## substitute for this: it says the index may describe code that moved, while this says THIS
    ## EXCERPT no longer matches the function it is filed under.
    anchor_mismatch: bool = False


## @brief One callee named at a call site that resolves to nothing in the index.
## @version 1
@dataclass(frozen=True)
class ExternalCallee:
    """A name this function CALLS that the index holds no function for — a libc
    or platform primitive, a vendored symbol outside the indexed scope, or a
    macro whose definition never reached doxygen.

    IT IS NOT A `CallEdge` AND NEVER BECOMES ONE. `callees` rows are resolved to
    a `memberdef` rowid by contract, and both the reachability and the thread BFS
    traverse resolved edges — a synthetic edge to an unresolvable name would
    inherit the weakest link and then propagate as fact. This is the weaker,
    honestly-labelled claim instead: the call site exists in the source text and
    the index cannot say what it reaches.

    Measured need (mbedtls): all four `threading_mutex_*_pthread` wrappers have an
    EMPTY `callees` list, because `pthread_mutex_lock` is not an indexed function.
    "This wrapper calls the pthread primitive" was therefore only obtainable by
    reading the body.

    @brief An unresolvable callee name observed in this function's source.
    @version 1
    """

    name: str
    call_lines: tuple[int, ...] = ()


## @brief One `#define` site: its parameters, its expansion and where it is written.
## @version 1
@dataclass(frozen=True)
class MacroDef:
    """A PREPROCESSOR DEFINITION, which is not a function and has no body, no
    callers and no callees — every one of those layers filters `kind='function'`.
    What a macro HAS is an expansion, and doxygen records it in
    `memberdef.initializer`: 2,063 of mbedtls's 2,504 macro rows carry one.

    gh#373. Until this existed the expansion was indexed and UNREACHABLE. Measured
    on the mbedtls Q2 cell: `MBEDTLS_PRIVATE` is a macro, `dossier` resolved the
    bare name to one of the 2,000-odd STRUCT MEMBERS doxygen records under that same
    name (`int mbedtls_aes_context::MBEDTLS_PRIVATE(nr)`, `kind='function'`), and
    `search('MBEDTLS_ALLOW_PRIVATE_ACCESS')` returned a confident zero while three
    rows for it sat in `memberdef`. The agent spent 20 index calls, fell back to
    `Read` four times and to `Grep` once, and then reported the macro layer as an
    index gap — the standing lesson in its purest form: "no rows" was a claim about
    the QUERY, not about the database.

    ONE ROW PER DEFINITION SITE, deliberately. A macro conditionally redefined in
    several translation units has several rows and they may DISAGREE — mbedtls
    defines `MBEDTLS_ALLOW_PRIVATE_ACCESS` in `library/common.h` and in two
    `programs/ssl/` mains, which is the whole answer to "when does the library see
    the private name and when does an application". Collapsing them to one would
    delete the fact worth having.

    THE BRANCH DOXYGEN NEVER SEES IS NOW RECOVERED (gh#403), and this paragraph used to
    state its absence as a permanent limit: "doxygen preprocesses, so an
    `#ifndef X / #define M a / #else / #define M b / #endif` pair yields the row for the
    branch doxygen took and NOT the other. The definition site is exact; the set of
    branches is not exhaustive." That was true and it was half of Q2's answer. The parser
    reads source text, so `ast_symbols.harvest_macro_definitions` recovers the other
    branch and `provenance` on the row says which layer found it.

    WHAT REMAINS TRUE: the set of sites is exhaustive only over INDEXED FILES, and a
    definition inside a file the scope excluded is still absent — the ordinary property
    of every layer here, not a macro-specific one.

    `gated_by` IS WHAT MAKES TWO SITES AN ANSWER RATHER THAN A CONTRADICTION. Two rows
    for one name reporting different expansions read as a disagreement until something
    says which branch each sits in; with the gates attached, `[ifndef X]` on one and
    `[ifdef X]` on the other IS the "who gets which" half of the question. It is per-SITE
    and not on the dossier, because the whole point is that the sites DIFFER — a single
    dossier-level gate list could only describe one of them.

    @brief One preprocessor definition: parameters, expansion, location, gating branch.
    @version 2
    """

    name: str
    rowid: int
    file: str
    line: int | None
    ## `(member)` for a function-like macro, built from `param.defname` — NOT from
    ## `memberdef.argsstring`, which is NULL on every macro row. '' means doxygen
    ## recorded no parameters, which is an object-like `#define` in the cases checked
    ## (273 of mbedtls's 2,504 macro rows carry parameters, and every function-like
    ## macro probed by hand was among them) but is stated as "none recorded" rather
    ## than as "takes no arguments", because those are two different claims and only
    ## the first is measured.
    params: str = ""
    expansion: str = ""
    brief: str = ""
    ## Names doxygen recorded as referencing this macro (`xrefs`), capped. Empty is
    ## common and does NOT mean unused: doxygen records a cross-reference from a
    ## function BODY, so a macro used only inside struct declarations — which is
    ## exactly what `MBEDTLS_PRIVATE` is — has none.
    referenced_by: tuple[str, ...] = ()

    ## Which layer produced this row: absent for doxygen's own, `'ast'` for a site the
    ## parser recovered from a branch the preprocessor dropped. It is the field that keeps
    ## a two-site answer legible — the `#else` spelling is not something doxygen declined
    ## to document, it is something doxygen structurally could not see.
    provenance: str | None = None

    ## The configuration gates whose branch covers THIS definition's line. On the
    ## motivating case the two sites come back `[ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS]` and
    ## `[ifdef MBEDTLS_ALLOW_PRIVATE_ACCESS]`, which is the whole of "who gets which
    ## spelling": a translation unit that has not defined the symbol gets the first.
    ##
    ## Each gate keeps its own `form` for the reason `gates_covering` records — an `#else`
    ## is its own row with the polarity inverted, and collapsing the pair to "gated by X"
    ## would delete the half that says which branch is live.
    gated_by: tuple[KconfigGate, ...] = ()

    ## How many gates in this site's FILE carry no recorded extent. Carried per site rather
    ## than once per dossier because sites live in different files, and a zero here is a
    ## measurement: it says an empty `gated_by` means ungated rather than "this index
    ## cannot tell". Reporting one file's count against another file's site is the
    ## substitution the field exists to prevent.
    gates_unplaceable: int = 0


## @brief The full multi-layer dossier for one function.
## @version 5
@dataclass(frozen=True)
class Dossier:
    """Everything the schema knows about one function: identity, liveness,
    thread membership, terminus status, requirements + covering tests, and
    its call-graph + shared-key fan-out (both directions). `candidates` is
    non-empty ONLY when the requested name is a genuine overload — it lists the
    alternatives this dossier could equally have described, so a consumer that
    reached dossier with a bare ambiguous name learns the pick was one of
    several and can re-query a specific file.

    `overrides` and `overridden_by` are the virtual-dispatch relation (gh#8), and the
    asymmetry in how they read matters: `overrides` is what THIS function replaces
    when called through a base pointer, `overridden_by` is what may run INSTEAD of it.
    Both are empty for an ordinary non-virtual function, which is the common case and
    is why they are lists rather than optionals — an empty list is the measurement
    "doxygen recorded no override relation for this symbol", not a missing field.

    THE ONE-SHOT FIELDS (`body`, `sections`, `locks_held`, `external_callees`) exist
    because the follow-up calls they replace were MEASURED: on one graded question the
    agent called `dossier` twice and then made fifteen more calls, seven of them
    `source` and four of those only to learn which platform primitive a wrapper calls.
    Each is scoped to the RESOLVED IDENTITY's rowids, never to the bare name — gh#26
    means three unrelated `_classify` functions share one name in this very repo, and a
    dossier that attributed one identity's locks or body to another would be worse than
    the follow-up call it saves.

    Each is empty/None when it says nothing, and the MCP layer elides it there: an
    absent `sections` means "this function opens no critical section", which is the
    common case and not worth a key.

    @brief Composite per-function dossier.
    @version 6
    """

    name: str
    rowid: int
    signature: str
    file: str
    line_start: int | None
    line_end: int | None
    brief: str
    version: str
    kind: str
    static: bool
    liveness: str
    ## The function's `@details` PROSE, which was fetched on every dossier and thrown away —
    ## `_identity` has always selected `detaileddescription` and read only the version tag out of
    ## it. Measured on mbedtls 2026-08-14: the warning about reaching past
    ## `MBEDTLS_ALLOW_PRIVATE_ACCESS` lives in `mbedtls_ssl_handshake_step`'s detail, two graded
    ## marks turn on it, and the agent reached it by grepping and then READING
    ## `include/mbedtls/ssl.h` — because this reply carried one sentence of `brief`.
    ##
    ## CAPPED WITH AN EXPLICIT NOTICE, never silently. 4,268 mbedtls rows carry detail averaging
    ## 1,052 characters, so the common case is small; the 14,804-character tail is what the cap is
    ## for, and a truncated reply that does not say so reads as a complete one.
    detail: str = ""
    provenance: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    threads: list[Thread] = field(default_factory=list)
    is_terminus: bool = False
    termini: list[Terminus] = field(default_factory=list)
    requirements: list[ReqRef] = field(default_factory=list)
    covering_tests: list[str] = field(default_factory=list)
    callers: list[CallEdge] = field(default_factory=list)
    callees: list[CallEdge] = field(default_factory=list)
    writes: list[KeyEdge] = field(default_factory=list)
    reads: list[KeyEdge] = field(default_factory=list)
    overrides: list[OverrideRef] = field(default_factory=list)
    overridden_by: list[OverrideRef] = field(default_factory=list)
    ## The one-shot additions. Last, so every existing positional construction of a
    ## Dossier keeps meaning what it meant.
    body: BodyExcerpt | None = None
    sections: list[CriticalSection] = field(default_factory=list)
    locks_held: list[CriticalSection] = field(default_factory=list)
    external_callees: list[ExternalCallee] = field(default_factory=list)
    ## gh#373. Every `#define` of this NAME, with its expansion. Present on two
    ## different kinds of dossier and it means the same thing in both: when the name
    ## also denotes a function, this is the macro that shares it; when it denotes
    ## ONLY a macro, this is the subject and `kind` is 'macro definition'. Populated
    ## by name rather than by the resolved identity, because a macro has no identity
    ## to resolve — `qualified_name_of` is a token scan over a function signature.
    macros: list[MacroDef] = field(default_factory=list)

    ## THE PRECONDITION OF EVERY OTHER FIELD IN THIS RECORD: the configuration gates whose branch
    ## covers this function's definition line. A caller reading `callers` and `locks_held` off a
    ## row learns what the code does; without this it cannot learn whether the build it is
    ## reasoning about contains that code at all. `grep` has the same blind spot and cannot fix
    ## it — the text is there whether or not the flag is set.
    ##
    ## Each gate keeps its own `form`, so `[ifdef X]` and `[ifndef X]` are different answers about
    ## the same symbol. Collapsing them into "gated by X" would discard the half that says whether
    ## the code is present.
    ##
    ## NAMED `gated_by`, NOT `gates`, because `gates` is ALREADY the config-symbol subject's key for
    ## the OPPOSITE direction — the lines that symbol decides. Two questions with two join
    ## directions get two names, exactly as `sections` (what this function locks) and `locks_held`
    ## (what is already locked when it runs) do. One key meaning two things depending on `kind` is
    ## how a consumer reads a symbol's gated lines as a function's preconditions.
    gated_by: list[KconfigGate] = field(default_factory=list)

    ## HOW MANY GATES IN THIS FILE COULD NOT BE PLACED, because they carry no recorded extent —
    ## an index built before the extent column stores `end_line = 0`. Reported rather than
    ## swallowed: with rows unplaceable, an empty `gates` list means "this index cannot tell",
    ## which is a different answer from "this function is ungated", and answering the first as the
    ## second is the substitution this project keeps finding in its own detectors.
    gates_unplaceable: int = 0

    ## gh#403, and LAST for the reason the one-shot block above states: a field appended cannot
    ## change what any existing positional construction means.
    ##
    ## NON-EMPTY WHEN THIS RECORD'S OWN IDENTITY IS SUSPECT: the chosen row has no body extent
    ## and the subject name is also `#define`d, which is the shape doxygen produces for a macro
    ## appearing in a declarator — `MBEDTLS_PRIVATE` yields ~2,000 `kind='function'` rows, one
    ## per wrapped struct field, and a bare-name lookup picks one of them.
    ##
    ## A NOTE AND NOT A RE-RANK, and not a boolean either. `dossier.MACRO_COLLISION_NOTE` carries
    ## the reasoning; the short form is that the only structural demotion rule available also
    ## fires on a function DECLARED and never defined in scope whose name is a macro, which is
    ## how the C standard library is written. A boolean would need the reader to already know
    ## what it implies, and the measured failure was a reader who did not.
    ##
    ## '' for every ordinary function, because a defined function has a body extent — and the
    ## MCP layer elides it there, so the common payload does not grow a key.
    macro_collision: str = ""


## @brief A verbatim, line-capped source body for one function.
## @version 3
@dataclass(frozen=True)
class SourceListing:
    """The actual source text of a function, read from the working tree at
    the body extent doxygen recorded (`bodystart`..`bodyend`). `lines` is
    CAPPED: when the body is longer than the caller's cap only the first
    `max_lines` are carried, `truncated` is True, and `end_line` is the last
    line actually included (so `file:start_line`..`end_line` always describes
    exactly what is in `lines`). `candidates` is non-empty ONLY when the name
    is a genuine overload — the body shown is the definition-preferring pick,
    and the alternatives are listed so a bare ambiguous name never silently
    reads the wrong function's body.

    A listing whose `provenance` is 'ast' shows a body doxygen never recorded —
    the line span came from the parser — which is the case that used to return
    nothing at all.

    @brief Verbatim function body with an explicit truncation flag.
    @version 3
    """

    name: str
    file: str
    start_line: int
    end_line: int
    lines: list[str] = field(default_factory=list)
    truncated: bool = False
    candidates: list[Candidate] = field(default_factory=list)
    provenance: str | None = None


## @brief One indexed source file with its documented-symbol count.
## @version 2
@dataclass(frozen=True)
class FileEntry:
    """A repo-relative source path known to the database, plus how many
    distinct documented symbols it contains — the cheap "what is in this
    repo / how big is this file" signal.

    `external_root` names the nested git tree that owns this file (gh#335), or is
    `''` for a file this repo owns. IT IS AN ANNOTATION AND NEVER A FILTER —
    `list_files` returns external files like any other, because hiding them would
    make an inventory that says "this repo contains 400 files" while the index holds
    900, which is the filtered-answer-that-looks-like-an-empty-answer failure applied
    to the one tool whose whole job is saying what is in here.

    @brief Indexed file (repo-relative path + symbol count + owning tree).
    @version 2
    """

    path: str
    symbol_count: int
    external_root: str = ""


## @brief What was indexed, and the declaration that decided it.
## @version 1
@dataclass(frozen=True)
class IndexScope:
    """The compact answer to "what did you actually look at", which gh#21 needed
    an EMPTY result to carry. `source` and `reason` are the build-time derivation
    (`declared` / `doxygen-guard` / `doxyfile`); `top_levels` and `extensions` are
    capped summaries of the covered file set, not the full inventory.

    `source` and `reason` are `""` — not absent — on an index built before the
    provenance was stamped. Empty reads honestly as "not recorded", where a
    fabricated value would read as a decision that was made.

    @brief Indexed-scope summary (provenance + covered shape).
    @version 1
    """

    source: str
    reason: str
    file_count: int
    top_levels: tuple[str, ...]
    extensions: tuple[str, ...]


## @brief One full-text hit in the supplementary prose corpus.
## @version 1
@dataclass(frozen=True)
class ProseHit:
    """A markdown chunk matching a full-text query: its source file, the
    heading of the chunk, and an FTS5 `snippet()` of the matching context.

    @brief Prose search hit (file + heading + snippet).
    @version 1
    """

    file_path: str
    heading: str
    snippet: str


## @brief A prose search, with the matching mode that produced it.
## @version 1
@dataclass(frozen=True)
class ProseSearch:
    """WHY THE MODE TRAVELS WITH THE HITS. FTS5 joins a bare token list with an implicit
    AND, so one word the author did not use empties an otherwise perfect query: measured on
    mbedtls, `private accessor` returns the migration guide and `private members accessor`
    returns NOTHING, because that document says "fields". A benchmark agent hit exactly this
    five times in one cell, was told the empty result was definitive, and read the file with
    grep instead — the corpus had held it the whole time.

    So the query widens to an OR when the AND is empty, and a widened result is a DIFFERENT
    KIND of answer: these documents matched SOME of the terms, not all. Returning the hits
    without saying so would trade a false negative for a false positive, which is not an
    improvement. `widened` is a property of the QUERY, not of any one row, which is why it
    lives here rather than on `ProseHit`.

    @brief Prose hits plus whether the query had to be widened to find them.
    @version 1
    """

    hits: list[ProseHit]
    widened: bool
    tokens: tuple[str, ...]


## @brief One member of a class/struct.
## @version 1
@dataclass(frozen=True)
class ClassMember:
    """A member of a compound: its name, kind (function/variable/...), the
    reassembled signature, and the line it is declared on.

    @brief Class member (name + kind + signature + line).
    @version 1
    """

    name: str
    kind: str
    signature: str
    line: int | None


## @brief One same-named compound a class lookup could have returned instead.
## @version 1
@dataclass(frozen=True)
class ClassCandidate:
    """A compound whose name also matched the lookup. `qualified` IS THE FIELD A
    CONSUMER PASSES BACK, as `lookup_class`'s `name` argument — it is the fully
    qualified compound name, so it selects exactly one compound where the bare name
    the caller typed did not.

    The field is called `qualified` and not `name` for one reason: REQ-DDB-QUERY-010
    is that a candidate publishes its selector VERBATIM under that name across the
    whole API, so a consumer who has learned the reflex once applies it everywhere.
    Calling it `name` here would have made this the single candidate list whose
    selector lived under a different key — and this type was written with `name`
    first, which is exactly how such an exception gets in.

    Deliberately NOT the function `Candidate`: that carries a `signature` and a
    `has_body`, which a compound has neither of, and a shared type would have left
    two of its fields permanently empty. What disambiguates an overload is the
    signature; what disambiguates a class is the namespace. Note that `lookup_class`
    needs no new parameter to honour a selection — its existing `name` argument
    already accepts a qualified string, so link 1 of the chain was always there.

    @brief One rejected class-lookup candidate (qualified name + kind + location).
    @version 1
    """

    qualified: str
    kind: str
    file: str
    line: int | None


## @brief A class/struct with its members and inheritance neighbours.
## @version 2
@dataclass(frozen=True)
class ClassEntry:
    """One compound definition: identity, declaring file, brief, its members,
    and its immediate base/derived compounds (both by name).

    `candidates` is non-empty when the requested name matched more than one compound
    (gh#315): this entry describes ONE of them, the best-ranked, and the list names
    the others. It stays EMPTY on an unambiguous name, like every other candidate
    list on this API — a list that is always populated disambiguates nothing.

    @brief Class/struct entry (identity + members + hierarchy + candidates).
    @version 2
    """

    name: str
    kind: str
    file: str
    line: int | None
    brief: str
    members: list[ClassMember] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)
    derived: list[str] = field(default_factory=list)
    candidates: list[ClassCandidate] = field(default_factory=list)


## @brief One annotated hop in a causal chain (a call or key edge).
## @version 3
@dataclass(frozen=True)
class Hop:
    """A single edge traversed by `chain_trace`, in causal orientation
    (from = caller/writer, to = callee/reader). `edge_class` is 'call' or
    'key'; the key-only fields are None for call hops.

    `confidence` and `strength` are SPLIT for the same reason `CallEdge` splits
    them, and here the collision was live: a key hop used to put a
    `key_strength` value ('low'/'medium'/'high') into the same `confidence`
    field a call hop fills with a `call_match` ('exact'/'resolved'/'fuzzy'), so
    one field carried two vocabularies with nothing on the wire saying which.

    `source`/`confidence` report the STRONGEST evidence found for this hop, which
    removes a DETERMINISM bug rather than only an inflation one: `_record_neighbor`
    dedupes hops on (edge_class, from_name, to_name, key_name) — deliberately
    excluding `source` — and kept whichever row arrived first, so which layer's
    `source`/`confidence` a hop reported depended on SQLite's row order within a
    name. Collapsing by strongest evidence first makes the reported value a
    property of the data instead of the scan order.

    @brief Annotated causal-chain hop (call or shared-key edge).
    @version 4
    """

    edge_class: str
    from_name: str
    to_name: str
    source: str
    confidence: str | None
    strength: str | None = None
    key_name: str | None = None
    edge_kind: str | None = None
    dispatch_mode: str | None = None
    edge_triggered: bool | None = None
    crosses_thread: bool | None = None
    to_thread: str | None = None


## @brief One node reached during a causal-chain traversal.
## @version 1
@dataclass(frozen=True)
class ChainNode:
    """A function reached by `chain_trace`: its name, canonical rowid, the
    minimum depth it was reached at, the requirements it is linked to, and
    whether it is an external-boundary terminus (with the terminus records).

    @brief Causal-chain node (identity + depth + reqs + terminus).
    @version 1
    """

    name: str
    rowid: int
    depth: int
    requirements: list[str] = field(default_factory=list)
    is_terminus: bool = False
    termini: list[Terminus] = field(default_factory=list)
    ## How many neighbours the FAN-OUT TAPER dropped at this node (#134).
    ##
    ## `chain_trace` halves its neighbour cap at each level and floors it at 1, which is
    ## what keeps a deep trace from exploding. It used to apply that with a bare `[:cap]`
    ## and record nothing, so a node with 131 callers and a cap of 8 reported 8 and looked
    ## complete. A consumer could not derive the gap either: the dropped neighbours leave
    ## no trace anywhere in the payload, so "is this all of them?" was unanswerable from
    ## the reply.
    ##
    ## 0 means the taper dropped nothing at this node — a MEASUREMENT, not a placeholder,
    ## and the reason it is not elided on the wire.
    omitted: int = 0


## @brief A complete causal-chain traversal result.
## @version 2
@dataclass(frozen=True)
class Chain:
    """The result of a D6 traversal: the seed, direction, depth bound, the
    set of reached nodes, and the annotated hops between them. `candidates` is
    non-empty ONLY when the SEED name is a genuine overload — the trace started
    from the definition-preferring pick, and the alternatives are listed so a
    consumer knows a bare ambiguous seed may have traced the wrong function.

    @brief Causal-chain traversal result (nodes + hops).
    @version 2
    """

    seed: str
    direction: str
    max_depth: int
    nodes: list[ChainNode] = field(default_factory=list)
    hops: list[Hop] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)


## @brief How much of a neighbour list is shared with same-named functions.
## @version 1
@dataclass(frozen=True)
class NameAmbiguity:
    """Why a function can appear to have hundreds of callers it does not have.

    An `ast_member` call edge's callee is an UNQUALIFIED tail, recovered by unwrapping
    `obj.method()` — the receiver's type is never checked. So when a bare name matches
    several functions, every call site emits an edge to ALL of them, and each of those
    functions inherits every one of those callers. Measured on the public entropic index:
    `Get` matches **33** functions and accumulates **162** callers, of which at most one
    per call site can be real; `size` matches 9 and shows 394. Both looked like ordinary
    well-populated caller lists.

    `confidence='fuzzy'` already warns that the specific function was never confirmed, but
    it is a THREE-VALUE enum over a quantity that is a NUMBER — a 2-candidate fuzzy edge
    and a 33-candidate one are not the same claim, and nothing a consumer read
    distinguished them. This carries the number.

    DERIVED, never stored: `COUNT` over same-named `memberdef` rows plus a count of the
    focal function's fuzzy `ast_member` neighbours. No schema change, so every existing
    index gains the signal without a rebuild.

    `shared_rows` counts the neighbours that arrive through the ambiguous name and are
    therefore shared with the other `candidates - 1` functions. It is NOT a claim that
    they are wrong — one of them is right — only that this function cannot be told apart
    from its namesakes on the available evidence.

    @brief The ambiguity behind a function's neighbour list.
    @version 1
    """

    name: str
    candidates: int
    shared_rows: int


## @brief One declared Kconfig symbol, as the query layer surfaces it.
## @version 1
@dataclass(frozen=True)
class KconfigEntry:
    """A symbol from the repo's CONFIGURATION SPACE (gh#18) — never from one
    configuration's resolved values. `default_expr` is the Kconfig expression the
    author wrote, conditions included, because `default FOO if BAR` and `default FOO`
    say different things about which variant is the unstated one.

    `choice` is the group's human identity (its prompt, or its name when it has one)
    or None. A symbol in a group is one of a set of MUTUALLY EXCLUSIVE alternatives,
    which is the distinction a consumer reasoning about reachability needs: two
    grouped variants are never both present.

    `help` is the field this whole layer exists for. A `help` block routinely carries
    the only statement of a known limitation in a repository.

    @brief One Kconfig symbol with its prompt, help, default and group.
    @version 1
    """

    name: str
    type: str
    prompt: str
    help: str
    default_expr: str
    choice: str | None
    file_path: str
    line: int
    gate_count: int = 0


## @brief One source line a CONFIG symbol gates.
## @version 1
@dataclass(frozen=True)
class KconfigGate:
    """A preprocessor conditional that decides whether a line EXISTS.

    `form` is load-bearing and must not be collapsed to a boolean: 'ifdef' means the
    code is present when the symbol is set, 'ifndef' means the opposite, and 'if_expr'
    means the line depends on the symbol through an expression this layer does not
    evaluate — so its polarity is genuinely unknown rather than assumed.

    `origin` says how the symbol's NAME is accounted for — Kconfig's prefix, the target's
    own declared preprocessor configuration, or nothing this build could see. Defaulted so
    an index built before gh#390 reads back as `undeclared`, which is exactly what a
    pre-declaration index knew.

    `end_line` CLOSES THE RANGE THIS ROW'S OWN `form` DESCRIBES, not the whole conditional: an
    `#ifdef` row stops where its `#else` begins, and that `#else` is a separate row with the
    polarity inverted. Measured: a `preproc_ifdef` node spans through its `#endif`, so a range
    join over the node's extent reports else-branch code as present when the symbol is SET — the
    inverse of the truth, stated confidently.

    `0` MEANS EXTENT UNKNOWN, which is what an index built before this column knew. It must not
    be read as "covers nothing" or as "covers everything"; `gates_covering` skips such rows and
    reports how many it skipped.

    @brief A CONFIG-gated source location.
    @version 3
    """

    symbol: str
    macro: str
    form: str
    file_path: str
    line: int
    origin: str = GATE_ORIGIN_UNDECLARED
    end_line: int = 0


## @brief A repo's configuration space, with the provenance of the answer.
## @version 1
@dataclass(frozen=True)
class KconfigSpace:
    """`found` and `error` are why this is a wrapper rather than a bare list.

    A repo with no Kconfig, a repo whose Kconfig declares nothing, and a repo whose
    Kconfig could not be parsed all present as zero symbols. They are three different
    facts, and this repo's standing lesson is that "no rows" is a claim about the
    detector until you have checked whether the detector could look — so the reply
    says which of the three it is instead of leaving a consumer to assume the
    flattering one.

    `configured_macros` is the bridge to gh#17: the space says which variants EXIST,
    that says which one this index was built in. Reporting them together is what stops
    a `default` being read as a fact about the build.

    THERE IS A FOURTH STATE AND IT IS THE COMMON ONE (gh#404). `found` says whether a KCONFIG was
    found and parsed — which is exactly what it means and is why it reads False on mbedtls. But a
    caller reads `found: false` as "this repository has no configuration space", and on mbedtls the
    index holds 12,096 gating sites over 1,107 symbols harvested from `#if` directives. Kconfig is
    a Zephyr/Linux convention; a header of `#define`s is the dominant C one, and reporting the
    dominant case as absence is the same misreport this class was built to prevent, one level up.

    So `gate_state` says what the GATE HARVEST measured, in `layer_state`'s existing vocabulary
    rather than a second spelling of the same three ideas: `populated` when the harvest found
    gating sites, `empty` when it ran and found none, `absent` when the layer was never built.
    A consumer wanting "does this repo have a configuration space" reads `found OR gate_state ==
    populated`; one wanting "does it use Kconfig" reads `found`. Those were never the same
    question and the reply no longer forces them to be.

    @brief A queried configuration space plus how the discovery and parse went.
    @version 2
    """

    found: bool
    source: str
    root: str
    symbols: tuple[KconfigEntry, ...]
    gates: tuple[KconfigGate, ...]
    error: str = ""
    configured_macros: str = ""
    ## WHERE THE MACRO LIST CAME FROM, because without it the list argues for a false answer.
    ## `declared` = an operator stated it for this build; `config_header` = it was read out of
    ## the repository's own header; `declared+config_header` = both. On mbedtls the acceptance
    ## build states `MBEDTLS_THREADING_C` so doxygen can reach the guarded bodies, while the
    ## repository ships it COMMENTED OUT — so the unqualified list pointed at the opposite of
    ## the truth on two graded marks, through `search` and `dossier` alike.
    configured_macros_source: str = ""
    ## The repository's OWN configuration header, repo-relative, when it is known. This is the
    ## route rather than the disclaimer: "these may not be the defaults" leaves an agent to hunt,
    ## naming the file collapses the follow-up to one read.
    config_header: str = ""
    ## The sentence that says what `configured_macros` is and is NOT evidence of. Same idiom as
    ## `LockInventory.row_meaning`, and here for the same reason: a number a reader inverts is
    ## worse than no number, and the correction has to travel WITH the value.
    macros_meaning: str = ""
    ## `layer_state` for `kconfig_gates`: populated / empty / absent. Defaulted to `absent` so an
    ## index built before this field reads as "the layer was never built", which is the honest
    ## answer for a database that carries no such measurement rather than a claim of emptiness.
    gate_state: str = LAYER_STATE_ABSENT
    ## Distinct symbols the gate harvest saw. A COUNT rather than a boolean, because "1,107
    ## symbols gate code here" and "at least one does" are different facts to act on.
    gate_symbols: int = 0
    ## The gating symbol NAMES, which is what "which configurations exist" actually asks for and
    ## what this reply could not previously answer: the inventory route returned every gate SITE
    ## instead — 12,096 rows and 2.1 MB on mbedtls — while a caller wanting the names had nowhere
    ## to look, since `kconfig_symbols` is empty for a repo configured by a header rather than
    ## Kconfig. Capped, and `gates_meaning` says so when it is.
    gate_symbol_names: tuple[str, ...] = ()
    ## What the `gates` list holds and where the omitted per-site detail is. Present because an
    ## empty `gates` must never read as "nothing gates code here" — the same ambiguity `found`,
    ## `source` and `error` exist to prevent, one field over.
    gates_meaning: str = ""


## @brief One richness layer's population state, distinguishing empty from absent.
## @version 1
@dataclass(frozen=True)
class LayerStat:
    """`state` is a `layer_state` value and it is the whole point of this row.

    `rows: 0` alone is ambiguous in the way this project keeps getting caught by: a
    table that EXISTS and holds nothing is a measurement (a detector ran and found
    none), while a table that is not in the index at all is a statement about the
    BUILD and not about the repository. Reported as `'empty'` and `'absent'`
    respectively so a consumer never has to infer which it got — and so the third
    possibility, a blind detector, stays visible as a question worth asking rather
    than being read as a correct negative.

    @brief A layer's name, state ('populated'/'empty'/'absent') and row count.
    @version 1
    """

    layer: str
    state: str
    rows: int


## @brief Aggregate call-graph counts, with the row-vs-pair distinction spelled out.
## @version 2
@dataclass(frozen=True)
class EdgeCounts:
    """THE TRAP THIS DATACLASS EXISTS TO DISARM: `call_edges` stores ONE ROW PER
    EXTRACTION LAYER — `UNIQUE(caller_rowid, callee_rowid, source)` makes `source`
    part of the key by design — so its row count is NOT the number of call
    relationships. Reporting a single "edge count" is how `callees('_run_pipeline')`
    came to return 8 rows for four real callees (#38), and a bare aggregate would
    republish that same misreading at whole-graph scale.

    So both numbers ship, under names that cannot be confused, plus `row_meaning`: a
    sentence carrying BOTH figures, so a consumer that quotes one number quotes the
    sentence that says which one it is. That is the self-describing-payload shape
    gh#2's staleness notices established — a flag alone under-determines what to do
    with it.

    `logical_pairs` counts DISTINCT `(caller_rowid, callee_rowid)`. It is a ROWID
    pair, deliberately, and NOT a (name, qualified-name) identity pair: rowids are
    what the table stores and what the UNIQUE constraint is over, so this count is
    exactly "rows, minus the per-layer duplication". Under the decl/def duality one
    function owns several rowids, so two rowid pairs can describe one
    source-level relationship; a name-identity count would be a third, smaller
    number and is not claimed here.

    `pairs_without_nonfuzzy` is the number gh#7 asks for by name — logical pairs for
    which EVERY row is `fuzzy`, i.e. no layer resolved the endpoint outright. It is
    the honest denominator for "how much of this graph should I trust", and it is
    routinely large: measured 87.8% on one target.

    @brief Call-edge rows vs logical pairs, confidence/source distributions, trust shares.
    @version 2
    """

    rows: int
    logical_pairs: int
    row_inflation: float
    pairs_without_nonfuzzy: int
    pairs_without_nonfuzzy_share: float
    rows_by_confidence: dict[str, int]
    rows_by_source: dict[str, int]
    row_meaning: str


## @brief How much of the indexed file set yielded symbols and bodies.
## @version 2
@dataclass(frozen=True)
class FileCounts:
    """The file half of gh#7, and it is READ rather than re-measured: the
    `substantive`/`barren`/`undocumented` figures are gh#6's, persisted into
    `build_meta` at build time by `coverage.IndexCoverage.as_meta`. Recomputing them
    here would be a second mechanism for one question — and the two would disagree
    the first time the barren rule changed on one side only.

    `coverage_recorded` says whether that section was there to read. False leaves the
    four derived figures at zero, which is honest as "not recorded" and must not be
    read as "measured and healthy" — an index built before build 18 has no coverage
    section at all.

    `files_with_bodies` is the one number gh#6 does not persist, and its definition
    needs stating because the decl/def duality makes "a file that yielded a body"
    ambiguous: it is the count of DISTINCT non-null `memberdef.bodyfile_id` values —
    files holding at least one function BODY. `files_with_symbols` unions `file_id`
    with `bodyfile_id`, so a header that only DECLARES counts there and not here, and
    the gap between the two is the header/implementation split rather than a defect.

    FIRST PARTY BY DEFAULT, EXTERNAL COUNTED BESIDE IT (gh#335). `indexed_files`,
    `files_with_symbols` and `files_with_bodies` count files this repo owns; a file
    inside a nested git tree is counted in `external_files` instead, and
    `external_roots` names those trees. Both are needed because they answer different
    questions: a reader deciding whether an index is thin wants the first-party
    ratio, and a reader wondering why `chain_trace` reached a symbol they do not
    recognise wants the roots. Reporting one merged count would make a repo look
    larger the moment it added a submodule, with no way to see which half moved.

    NOTHING HERE IS A FILTER ON THE GRAPH. Traversal crosses the boundary freely;
    this is the aggregate saying which side of it each row sits on.

    `external_files` is 0 both for a repo that vendors nothing and for an index built
    before gh#335 — `external_recorded` is what separates them, for the same reason
    `coverage_recorded` exists: an unmeasured zero must not read as a measured one.

    @brief Indexed files vs files yielding symbols vs files yielding bodies, plus gh#6's coverage.
    @version 2
    """

    indexed_files: int
    files_with_symbols: int
    files_with_bodies: int
    coverage_recorded: bool
    substantive_files: int = 0
    barren_files: int = 0
    barren_ratio: float = 0.0
    undocumented_files: int = 0
    undocumented_ratio: float = 0.0
    external_files: int = 0
    external_roots: tuple[str, ...] = ()
    external_recorded: bool = False
    ## `path` rows naming no file in this repository — doxygen's record of an
    ## `#include` it could not resolve, spelled as a bare filename. Excluded from
    ## `indexed_files` because they are neither this repo's nor a named tree's, and
    ## reported so the exclusion is visible instead of silent.
    unresolved_files: int = 0


## @brief Whole-graph aggregate: how much of this index a consumer should trust.
## @version 1
@dataclass(frozen=True)
class GraphStats:
    """The one payload that is about the GRAPH rather than about a symbol or a seed
    (gh#7). Every other query on this surface is per-symbol or per-seed, so a
    consumer that had been told to weigh `confidence` on every edge had no way to
    learn how much of the graph carries which value — it either sampled neighbour
    lists or stated a chain with unearned confidence.

    `symbol_provenance` is gh#11's distribution: `memberdef` rows by `dg_source`.
    A 'doxygen' row can carry a brief, its documented parameters and its `@req`
    tags; an 'ast' row is a name, a file, a line span and nothing else, because a
    preprocessor that skipped the code skipped its doc comment too. The mix is
    therefore how much of this index can be READ as opposed to merely traversed. An
    index predating the column reports `{}`, not an invented all-doxygen split.

    @brief Whole-graph trust aggregate (edges, files, layers, symbol provenance).
    @version 1
    """

    build_version: int | None
    symbol_rows: int
    calls: EdgeCounts
    files: FileCounts
    layers: tuple[LayerStat, ...]
    symbol_provenance: dict[str, int]


## @brief One declaration site of a variable subject.
## @version 1
@dataclass(frozen=True)
class VariableSite:
    """A variable is routinely declared twice — `extern` in a header and defined in a
    translation unit — and the two sites answer DIFFERENT questions. The header says
    what the name means to a caller; the definition says what it is bound to. Reporting
    only one of them, whichever the definition-preferring pick happened to land on,
    would answer "where is this?" with half the truth.

    `declaration` is the source text AT the site, which is where an initializer lives
    when doxygen did not record one. Measured on mbedtls: every one of the four
    `mbedtls_mutex_*` function pointers has `initializer` NULL in `memberdef` while the
    declaration line itself reads `= threading_mutex_lock_pthread`. The index knows
    where to look; only the bytes were missing.

    @brief One site where a variable is declared, with its source text.
    @version 1
    """

    file: str
    line: int
    signature: str
    static: bool
    extern: bool
    ## Doxygen's own `initializer` column when it recorded one, '' otherwise. Kept
    ## BESIDE `declaration` rather than merged into it: one is a database fact and the
    ## other is bytes read off disk, and a consumer weighing them should be able to see
    ## which is which.
    initializer: str = ""
    declaration: BodyExcerpt | None = None


## @brief A variable subject: identity, every declaration site, no call graph.
## @version 1
@dataclass(frozen=True)
class VariableSubject:
    """WHAT A VARIABLE HAS, AND WHAT IT DOES NOT. It has a type, a set of declaration
    sites and — where the working tree is available — the text of each. It has NO body,
    NO callers and NO callees, and this type says so BY ABSENCE: those fields do not
    exist here rather than existing and being empty. An empty `callers: []` on a
    variable would be a measurement of something that was never measurable.

    THIS TYPE IS WHY `dossier` STOPPED BEING FUNCTION-ONLY. Measured on the public
    mbedtls index: `mbedtls_mutex_lock` — the symbol every locking question in that
    repository runs through — is `kind='variable'`, so `function_candidates` returned
    nothing and `dossier` answered `found: false` for a name `search` had just listed.
    A tool that cannot be pointed at the subject a question is about is the reason
    there were nineteen tools.

    `sites` is ordered definition-first, matching every other identity resolution on
    this surface, so the first entry is the one that carries the binding.

    @brief A variable's identity and its declaration sites.
    @version 1
    """

    name: str
    rowid: int
    type: str
    brief: str
    version: str
    provenance: str | None = None
    sites: tuple[VariableSite, ...] = ()


## @brief A lock subject: its roster row plus every critical section it guards.
## @version 1
@dataclass(frozen=True)
class LockSubject:
    """The two lock questions in one payload: WHICH lock is this (the roster row, with
    its identity caveat intact) and WHAT runs under it (`sections`).

    THE ROSTER ROW TRAVELS WITH THE SECTIONS on purpose. `LockEntry` carries
    `identity_confidence` and a `(name, scope, kind)` identity that is NOT one mutex,
    and the sections alone would strip that qualifier off — which is the precise
    misreport `LockInventory.row_meaning` exists to prevent, reintroduced one level
    down. `siblings` names the other rows sharing this bare name, so a caller can see
    that it asked about one of several identities before quoting a count.

    @brief One lock identity with its critical sections and its same-name siblings.
    @version 1
    """

    lock: LockEntry
    sections: tuple[CriticalSection, ...] = ()
    siblings: tuple[LockEntry, ...] = ()


## The subject kinds `resolve_subject` can classify a name as, in PROBE ORDER. The order
## decides which section a BARE name gets, and `SubjectDossier.also` names the ones it did
## not get — so the order is a default, never a silent pick.
##
## `function` FIRST because it is the overwhelmingly common case: a name that is a function
## takes the same path the function-only `dossier` took, so the hot path is unchanged.
##
## `macro` second rather than first, because doxygen writes a `kind='function'` memberdef
## row for a struct field wrapped in a function-like macro — ~2,000 mbedtls member rows
## share a macro's name — so probing macros first would describe the `#define` when the
## caller meant the member.
##
## THE RICHNESS LAYERS OUTRANK THE GENERIC ROW, which is why `lock` and `thread` come
## before `variable`. A name reaches the `locks` table only because the lock detector
## identified it as playing that role, and the lock subject then carries every critical
## section under it — real adjacency. The variable row for the same name carries a
## declaration line. Both are true; the richer one is the better default. Measured on this
## repo's own fixture: `dm_mutex` is a `static pthread_mutex_t` AND a lock row, and under
## the reverse order a question about the lock returned its `#define`-less declaration and
## nothing else.
##
## `requirement` and `config` last because their ids are namespaced (`REQ-…`, `CONFIG_…`)
## and cannot collide with an ordinary identifier in practice, so their position costs
## nothing.
SUBJECT_KINDS: tuple[str, ...] = (
    "function",
    "macro",
    "lock",
    "thread",
    "class",
    "variable",
    "requirement",
    "config",
)


## @brief Whatever the index knows about ONE named subject, whatever kind it is.
## @version 1
@dataclass(frozen=True)
class SubjectDossier:
    """ONE ENVELOPE, ONE POPULATED SECTION. `kind` says which, and every other section
    is None — not empty, absent — because a requirement has no signature and a variable
    has no callees, and inventing the field to hold a null would make "does not apply"
    indistinguishable from "measured, found nothing". `wire.one` keeps envelope keys, so
    the MCP layer prunes the unpopulated ones by name.

    `also` NAMES THE OTHER KINDS THE SAME STRING RESOLVES TO. One name really can be
    two subjects — a macro and a member, a lock and the variable that declares it — and
    a payload that silently picked one would be the `_classify` failure recorded in this
    repo's own notes, one level up: an arbitrary pick reported as the answer. It is a
    LIST OF KINDS, not of payloads, so disclosing the ambiguity costs a handful of bytes
    and the caller re-asks with `kind=` when it wants the other one.

    `chain` IS PRESENT ONLY WHEN `depth > 1`. Depth 1 is adjacency, which the populated
    section already carries; depth 2+ is traversal, which is `chain_trace`'s bounded
    walk and not a second implementation of it.

    @brief One subject of any kind, with the adjacency that kind has.
    @version 1
    """

    subject: str
    kind: str
    also: tuple[str, ...] = ()
    function: Dossier | None = None
    variable: VariableSubject | None = None
    compound: ClassEntry | None = None
    requirement: ReqTrace | None = None
    lock: LockSubject | None = None
    thread: Thread | None = None
    config: KconfigSpace | None = None
    chain: Chain | None = None

    ## @brief The one populated section, whatever kind it is.
    ## @return The section dataclass, or None when nothing resolved.
    ## @version 1
    ## @req REQ-DDB-QUERY-001
    @property
    def section(self) -> object | None:
        """A CONSUMER SHOULD NOT HAVE TO MAP KIND TO FIELD NAME, because two of the eight
        do not match (`class` -> `compound`, `macro` -> `function`) and a consumer that
        guessed would read `None` off a populated dossier. The mapping lives here, once,
        beside the fields it maps.

        Reads the fields rather than a lookup table keyed on `kind`, so a section added
        to this dataclass is found without a second edit somewhere else.

        @brief Return whichever section this dossier populated.
        @return The populated section, or None.
        @version 1
        """
        for value in (
            self.function,
            self.variable,
            self.compound,
            self.requirement,
            self.lock,
            self.thread,
            self.config,
        ):
            if value is not None:
                return value
        return None


## @brief One top-level directory's INDEXED file inventory.
## @version 1
@dataclass(frozen=True)
class DirectoryEntry:
    """The rollup that made Q4 spend six `find … | wc` shell calls, and the reason it is
    labelled so heavily rather than presented as a directory listing.

    `indexed_files` IS NOT A COUNT OF THE DIRECTORY'S FILES. It counts what this index holds,
    and the gap between the two can be enormous: mbedtls's `tests/` has 310 tracked files and
    44 indexed ones, because most are `.function` / `.data` fixtures that no grammar handles.
    So "which directory is largest HERE" and "which is largest in the REPOSITORY" have
    different answers — `library` and `tests` respectively — and a reply that offered the first
    as the second would argue for a wrong answer, which is the failure this project keeps
    paying for. `DirectoryInventory.rollup_meaning` says it in the reply.

    @brief A top-level directory with its indexed file and symbol counts.
    @version 1
    """

    directory: str
    indexed_files: int
    symbols: int
    ## Files whose only rows come from a nested git tree this repo does not own. An ANNOTATION,
    ## never a filter, for the reason `FileEntry.external_root` documents.
    external_files: int = 0
    ## Files the index KNOWS OF but could not resolve to content — most often a `#include` doxygen
    ## recorded without finding the header. Reported per directory because it is a CONTRIBUTOR to
    ## why this rollup's total exceeds `coverage.indexed_files` (527 against 443 on mbedtls), and a
    ## reader comparing two same-sounding figures with no explanation concludes one is wrong.
    ##
    ## IT IS NOT THE WHOLE DIFFERENCE, and saying so cost two wrong attempts: 527-41 and then
    ## 527-41-259 both failed to reconcile, because coverage ALSO drops prose and documentation and
    ## those categories overlap with each other. `rollup_meaning` therefore states the two
    ## DEFINITIONS rather than an arithmetic — a stated sum that does not add up is worse than none.
    unresolved_files: int = 0


## @brief The per-directory rollup of the indexed file set, with what it is not.
## @version 1
@dataclass(frozen=True)
class DirectoryInventory:
    """WHAT IS IN HERE, BY DIRECTORY — the question the query library could already answer per
    FILE (`list_files`) and that no MCP surface could reach, because the `list_files` tool was
    deleted in the four-tool consolidation. Measured on mbedtls 2026-08-14: Q4 replaced it with
    six `find … | wc -l` shell calls and still missed the marks it was computing them for.

    @brief Per-directory indexed inventory plus the sentence saying what it counts.
    @version 1
    """

    directories: tuple[DirectoryEntry, ...]
    indexed_files: int
    ## What `indexed_files` counts and — load-bearing — what it does NOT. Never omitted.
    rollup_meaning: str = ""
