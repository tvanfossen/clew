# SPDX-License-Identifier: MIT
"""R1 lock layer, L2: which calls run WHILE a lock is held (task #52).

L1 says a lock exists and where it is taken. It cannot say what happens inside
the hold, so two questions stayed unanswerable: *what runs under this lock*, and
*which locks are held when X is called* — the second being the input any future
ordering/deadlock check needs. This module answers both by recording, per
acquisition, the call sites that fall inside its critical section.

WHY IT IS NOT A JOIN. `call_edges` carries no line number (`caller_rowid,
callee_rowid, source, confidence`), so membership cannot be derived from the
tables that already exist — the containment test needs a POSITION, and the only
place a position survives is the AST. L2 therefore rides the L1 harvest: one
parse, one cache entry, `_LockHarvester.stage_version` bumped.

MEASURED BEFORE BUILT — the numbers below sized this layer against two real repos
before a line of it existed, which is why the extent rule is "bounded or nothing"
rather than a guess. The one-off harness that produced them has been deleted; the
measurements are the durable part, and `tests/test_critical_sections.py` is now
the executable form of the same contract.

  C++ codebase      15 locks / 33 acquisitions, 100% RAII, 100% bounded, 70 calls
                 inside sections across 26 non-empty sections.
  C/POSIX IoT repo  7 locks / 29 acquisitions, 100% explicit pair, ~107 calls
                 inside sections.

So L2 is not a mostly-NULL layer; it is dense on both idioms. Lexical nesting
(two acquisitions held simultaneously WITHIN one function) measured ZERO on both
— which reproduces the observation L1 recorded. The nesting that matters is
CROSS-FUNCTION (f holds L1, calls g, g takes L2) and it is derivable the moment
this table exists: join `critical_section_calls.callee_rowid` against
`lock_acquisitions.holder_rowid`.

THE RULE, AND WHY A LEXICAL SPAN IS WRONG. The obvious implementation — "every
call between the acquire line and the release line" — FABRICATES membership, and
the reference source proves it rather than a thought experiment::

    pthread_mutex_lock(&cmd_queue_mutex);              // 2574
    if (cmd_id_queued_locked(id)) {                    // 2575  under the lock
        APP_LOG_INFO(...);                         // 2576  under the lock
        pthread_mutex_unlock(&cmd_queue_mutex);        // 2577
        cmd_send_response(...);                        // 2578  NOT under the lock
        return true;
    }
    ...
    pthread_mutex_unlock(&cmd_queue_mutex);            // 2590

Line 2578 sits lexically inside 2574..2590 and executes with the lock released.
A span-based layer would report `cmd_send_response` as running under
`cmd_queue_mutex` — a specific, false synchronization claim, and precisely the
kind this layer exists to refute.

So membership is decided per call site by BLOCK-CHAIN SHADOWING:

    A call C is under the lock iff no release of the same operand occurs
    lexically before C in ANY block on the ancestor chain from C up to the
    acquisition's own block.

That is exact on both reference idioms. In the example, 2578's enclosing block
is the `if` body, which contains the release at 2577 before it — shadowed. 2587
sits in the function body, whose only release is at 2590 (after) — held. RAII
has no release token at all, so nothing shadows and the hold runs to the end of
the enclosing block, which is what the language guarantees.

EXTENT (`lock_acquisitions.end_line`) uses the same facts, so L1 and L2 cannot
disagree: the section closes at the first release ON THE FALL-THROUGH PATH — the
earliest unshadowed release that is not sealed inside a jump-terminated branch.
An early-return `if (bad) { unlock; return; }` is skipped for exactly the reason
it is safe to skip: control leaves the block, so the lock is still held after it.
This also REPLACES L1's previous release search, which walked a DFS stack and
returned whichever matching unlock it reached first — an order-dependent answer
to a question with one right answer.

FAIL CLOSED. When no fall-through release exists the extent is NULL, confidence
is 'low', and NO membership rows are written. Two real shapes reach it: a lock
released only inside a branch that does NOT jump (state after the branch is
genuinely unknown), and a lock never released in its function at all. Both are
cases where any answer would be invented, and an invented critical section is
worse than an absent one — it asserts synchronization that is not there.

BOUNDED LIMITATIONS, stated rather than hidden:
  * A manual `guard.unlock()` on a `std::unique_lock` would end an RAII hold
    early and is not modelled. Measured across the C++ codebases checked: ZERO `.unlock()`,
    `.lock()` or `defer_lock` in the indexed scope, so the RAII extent there is
    unconditional in fact and not merely by assumption.
  * A call reached only through a loop back-edge is attributed lexically. The
    acquisition's own start byte is the floor, so a call BEFORE the acquisition
    in a loop body is correctly excluded.

@brief Critical-section membership: calls that run while a lock is held (L2).
@version 1
"""

from __future__ import annotations

import sqlite3
from typing import Any

from .harvest import enclosing
from .pyast import node_text
from .vocabulary import (
    SECTION_MATCH_AMBIGUOUS,
    SECTION_MATCH_EXTERNAL,
    SECTION_MATCH_RECEIVER_UNVERIFIED,
    SECTION_MATCH_RESOLVED,
    check,
)

## The one node type that introduces a scope in C/C++. Both the RAII extent and
## the shadowing chain are expressed entirely in terms of it.
BLOCK_TYPES = ("compound_statement",)

## Statements that leave the enclosing block. A conditional release sealed behind
## one of these cannot reach the code that follows the branch, which is what
## makes the ubiquitous `if (bad) { unlock; return; }` guard safe to walk past
## instead of treating as an unknown lock state.
_JUMPS = ("return_statement", "break_statement", "continue_statement", "goto_statement")

## Extent-confidence tiers, spelled against `ACQ_STRENGTH`'s documented meaning —
## "confidence that the acquisition's extent was resolved". L1 used to write this
## column from `lock_id is not None`, which is IDENTITY confidence and already
## carried by `locks.identity_confidence`; the column named for the extent said
## nothing about the extent.
EXTENT_EXACT = "high"
EXTENT_INFERRED = "medium"
EXTENT_UNRESOLVED = "low"


## @brief One acquisition's resolved critical section.
## @version 1
class Section:
    """The extent plus the calls that run inside it.

    `calls` is EMPTY whenever `end_line` is None — an unresolved extent yields no
    membership at all, never a partial guess (see the module's fail-closed note).

    @brief Resolved critical section: extent, contained calls, confidence.
    @version 1
    """

    __slots__ = ("calls", "confidence", "end_line")

    ## @brief Store one resolved section.
    ## @param end_line 1-based line the hold ends on, or None when unresolved.
    ## @param calls `[callee_name, line]` pairs running inside the hold.
    ## @param confidence An `ACQ_STRENGTH` member describing the extent.
    ## @version 1
    ## @dg_internal
    def __init__(self, end_line: int | None, calls: list[list[Any]], confidence: str) -> None:
        self.end_line = end_line
        self.calls = calls
        self.confidence = confidence


## @brief Create the L2 membership table if it does not exist.
## @param conn Open connection to the database being built.
## @return None.
## @version 1
## @req REQ-DDB-SCHEMA-011
def ensure_section_table(conn: sqlite3.Connection) -> None:
    """Created unconditionally alongside the L1 tables — including on a build
    with no tree_sitter and on a repo with no locks — so R2 and R4 never branch
    on table existence. That is the same contract `locks`/`lock_acquisitions`
    already give, and the requirements-table precedent both follow.

    `callee_rowid` is NULLABLE and deliberately outside the UNIQUE key: a call
    site is a physical location, identified by (acquisition, line, name), and
    letting an unresolved rowid participate in dedup would file the same site
    twice under two different resolutions.

    @brief Create critical_section_calls.
    @version 1
    """
    conn.executescript(
        f"""
        CREATE TABLE IF NOT EXISTS critical_section_calls (
            id             INTEGER PRIMARY KEY,
            acquisition_id INTEGER NOT NULL REFERENCES lock_acquisitions(id),
            callee_rowid   INTEGER REFERENCES memberdef(rowid),
            callee_name    TEXT NOT NULL,
            call_line      INTEGER NOT NULL,
            resolution     TEXT NOT NULL {check("critical_section_calls", "resolution")},
            UNIQUE(acquisition_id, call_line, callee_name)
        );
        CREATE INDEX IF NOT EXISTS idx_section_calls_acq
            ON critical_section_calls(acquisition_id);
        CREATE INDEX IF NOT EXISTS idx_section_calls_callee
            ON critical_section_calls(callee_rowid);
        """
    )


## @brief Every node of a type within a subtree, in source order.
## @param root Subtree root to search.
## @param wanted Node type to collect.
## @param floor Minimum start byte; earlier nodes are skipped.
## @return Matching nodes sorted by start byte.
## @version 1
## @dg_internal
def _nodes_of_type(root: Any, wanted: str, floor: int) -> list[Any]:
    """@brief Collect same-typed nodes at or after a byte floor, in source order."""
    found = []
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type == wanted and node.start_byte >= floor:
            found.append(node)
    return sorted(found, key=lambda n: n.start_byte)


## @brief The release call sites for one operand inside a subtree.
## @param root Subtree to search (the acquisition's enclosing block).
## @param src Source bytes.
## @param releaser Release primitive name, or None for an RAII hold.
## @param operand Mutex operand name the release must name.
## @param floor Minimum start byte (the acquisition's end).
## @return Release call nodes in source order; empty for an RAII hold.
## @version 1
## @dg_internal
def _releases(root: Any, src: bytes, releaser: str | None, operand: str, floor: int) -> list[Any]:
    """An RAII guard has NO release token — its hold ends with the block, by
    language rule — so `releaser=None` yields an empty list and every shadowing
    test below trivially passes. That is what makes one walk serve both idioms
    instead of two near-copies.

    The operand must match: releasing a DIFFERENT mutex inside this section is
    not the end of this hold, and treating it as one would truncate the section
    at an unrelated statement.

    @brief Find an operand's release sites after the acquisition.
    @version 1
    """
    if releaser is None:
        return []
    out = []
    for node in _nodes_of_type(root, "call_expression", floor):
        if node_text(node.child_by_field_name("function"), src) != releaser:
            continue
        args = node.child_by_field_name("arguments")
        if args is not None and operand in _operand_texts(args, src):
            out.append(node)
    return out


## @brief Bare operand names in an argument list.
## @param args Argument-list node.
## @param src Source bytes.
## @return Argument texts with address-of/dereference sigils stripped.
## @version 1
## @dg_internal
def _operand_texts(args: Any, src: bytes) -> list[str]:
    """@brief Argument names with `&`/`*` stripped, for operand matching."""
    return [node_text(child, src).strip().lstrip("&*").strip() for child in args.named_children]


## @brief Group release nodes by the block that directly contains them.
## @param releases Release call nodes.
## @return Mapping of block node id to the releases at that block's own level.
## @version 1
## @dg_internal
def _by_block(releases: list[Any]) -> dict[int, list[Any]]:
    """Keyed by `node.id`, never by object identity: the tree-sitter bindings
    return a FRESH wrapper on every `.parent` access, so `is` between two reads
    of the same node is False. That exact mistake made a first measurement report
    32 of 32 releases as deeper-nested when the true count was 5.

    @brief Index releases by their immediately enclosing block.
    @version 1
    """
    grouped: dict[int, list[Any]] = {}
    for release in releases:
        block = enclosing(release, BLOCK_TYPES)
        if block is not None:
            grouped.setdefault(block.id, []).append(release)
    return grouped


## @brief True when a release earlier in the chain already ended the hold.
## @param node Call (or release) node under test.
## @param acquire_block Block the acquisition itself sits in.
## @param by_block Releases indexed by their enclosing block.
## @return True when the lock is no longer held at this node.
## @version 1
## @dg_internal
def _shadowed(node: Any, acquire_block: Any, by_block: dict[int, list[Any]]) -> bool:
    """The membership rule. Walks the block chain from the node up to the
    acquisition's block; at each level, a release of the same operand appearing
    BEFORE the node means the hold ended on this path.

    Comparing against the node's own start byte is sufficient: a release at a
    given block's own level is a SIBLING of the statement containing the node, so
    their spans are disjoint and "before the node" and "before that statement"
    coincide.

    @brief Decide whether a node still runs under the hold.
    @version 1
    """
    block = enclosing(node, BLOCK_TYPES)
    while block is not None:
        if any(r.start_byte < node.start_byte for r in by_block.get(block.id, ())):
            return True
        if block.id == acquire_block.id:
            return False
        block = enclosing(block, BLOCK_TYPES)
    return False


## @brief True when a block's last statement leaves the block.
## @param block Block node to inspect.
## @return True when the block ends in return/break/continue/goto.
## @version 1
## @dg_internal
def _jump_terminated(block: Any) -> bool:
    """@brief Whether control cannot fall out of the bottom of this block."""
    named = list(block.named_children)
    return bool(named) and named[-1].type in _JUMPS


## @brief True when a release is sealed inside a branch that never falls through.
## @param release Release node.
## @param acquire_block Block the acquisition sits in.
## @return True when some block between the release and the acquisition jumps away.
## @version 1
## @dg_internal
def _sealed_in_branch(release: Any, acquire_block: Any) -> bool:
    """`if (bad) { unlock; return; }` releases the lock on ONE path and then
    leaves the block, so the code after the `if` still runs under the hold. Such
    a release must not be mistaken for the end of the section — which is the
    difference between reporting a two-line critical section and the real
    sixteen-line one.

    @brief Whether a release is confined to a non-falling-through branch.
    @version 1
    """
    block = enclosing(release, BLOCK_TYPES)
    while block is not None and block.id != acquire_block.id:
        if _jump_terminated(block):
            return True
        block = enclosing(block, BLOCK_TYPES)
    return False


## @brief The release that ends the hold on the fall-through path.
## @param releases Candidate release nodes in source order.
## @param acquire_block Block the acquisition sits in.
## @param by_block Releases indexed by their enclosing block.
## @return The closing release node, or None when the extent is unresolved.
## @version 2
## @dg_internal
def _closing_release(
    releases: list[Any], acquire_block: Any, by_block: dict[int, list[Any]]
) -> Any:
    """Deterministic by construction — the FIRST qualifying release in source
    order. L1 previously popped a DFS stack and took whichever matching unlock it
    happened to reach, so a function with two releases had an extent that
    depended on traversal order rather than on the code.

    Only a release in the acquisition's OWN block closes the section, because
    only that one is guaranteed to run on the fall-through path. A nested block
    is entered CONDITIONALLY (an `if`, a bounded `for`), and there is no way to
    know statically that it was entered. Two nested cases, and the difference is
    the whole reason `_jump_terminated` exists:

      * `if (bad) { unlock; return; }` — the branch LEAVES the block, so the code
        after it still runs under the hold. Skip the release and keep looking.
      * `if (x) { unlock; }` — control falls out of the branch and the lock is
        held on one path and not the other. There is NO honest extent; refuse
        rather than pick either answer.

    The second case is where fail-closed differs from merely conservative: the
    detector can SEE a release and still declines to use it, because using it
    would assert a specific synchronization state that only half the paths have.

    @brief First release that actually closes the section, or None.
    @version 2
    """
    for release in releases:
        if _shadowed(release, acquire_block, by_block):
            continue
        block = enclosing(release, BLOCK_TYPES)
        if block is not None and block.id == acquire_block.id:
            return release
        if not _sealed_in_branch(release, acquire_block):
            return None
    return None


## @brief Resolve one acquisition's critical section from the AST.
## @param acquire The acquiring declaration (RAII) or call node.
## @param src Source bytes.
## @param releaser Release primitive name, or None for an RAII hold.
## @param operand Mutex operand name.
## @param primitives Lock primitive names to exclude from membership.
## @return The resolved Section; empty and unresolved when it fails closed.
## @version 2
## @req REQ-DDB-SCHEMA-011
def resolve_section(
    acquire: Any,
    src: bytes,
    releaser: str | None,
    operand: str,
    primitives: frozenset[str] = frozenset(),
) -> Section:
    """The single entry point L1 calls, so extent and membership are two outputs
    of ONE analysis and cannot drift apart.

    An RAII hold ends with its block, by language rule, and is reported 'high'.
    An explicit pair ends at its fall-through release: 'high' when nothing had to
    be reasoned past, 'medium' when a jump-terminated branch release was walked
    over — that inference is load-bearing there and a consumer should be able to
    see it. No fall-through release means 'low', a NULL extent and no rows.

    @brief Resolve extent + membership for one acquisition.
    @version 1
    """
    block = enclosing(acquire, BLOCK_TYPES)
    if block is None or not operand:
        return Section(None, [], EXTENT_UNRESOLVED)
    floor = acquire.end_byte
    releases = _releases(block, src, releaser, operand, floor)
    by_block = _by_block(releases)
    closing = _closing_release(releases, acquire_block=block, by_block=by_block)
    if releaser is not None and closing is None:
        return Section(None, [], EXTENT_UNRESOLVED)
    if closing is not None:
        ceiling, end_line = closing.start_byte, closing.start_point[0] + 1
    else:
        ceiling, end_line = block.end_byte, block.end_point[0] + 1
    calls = _member_calls(block, src, (floor, ceiling), by_block, primitives)
    return Section(end_line, calls, _extent_confidence(releaser, releases))


## @brief Extent confidence for one acquisition.
## @param releaser Release primitive name, or None for an RAII hold.
## @param releases Every candidate release found after the acquisition.
## @return An `ACQ_STRENGTH` member.
## @version 1
## @dg_internal
def _extent_confidence(releaser: str | None, releases: list[Any]) -> str:
    """'medium' exactly when more than one release was in play, i.e. when the
    jump-termination inference decided which one closes the hold. A single
    balanced pair needs no inference and stays 'high'.

    @brief Grade how much reasoning the extent required.
    @version 1
    """
    if releaser is None or len(releases) <= 1:
        return EXTENT_EXACT
    return EXTENT_INFERRED


## @brief Call sites inside one section, shadowed and primitive calls excluded.
## @param block The acquisition's own block — both the scan root and the shadow chain's top.
## @param src Source bytes.
## @param window (start byte, end byte) of the section.
## @param by_block Releases indexed by their enclosing block.
## @param primitives Lock primitive names to exclude.
## @return `[callee_name, line]` pairs, in source order.
## @version 4
## @dg_internal
def _member_calls(
    block: Any,
    src: bytes,
    window: tuple[int, int],
    by_block: dict[int, list[Any]],
    primitives: frozenset[str],
) -> list[list[Any]]:
    """The byte window is the cheap filter; SHADOWING is the correct one, and
    both are applied. Naming goes through the same callee unwrapping
    `call_edges` uses, so an L2 row's `callee_name` is the token a `call_edges`
    row would carry for the same site and the two layers join on equal terms.

    LOCK PRIMITIVES ARE NOT MEMBERS. `pthread_mutex_unlock` of an unrelated
    mutex, or a nested acquire, is lexically inside the section and answering
    "what runs under this lock" with it is noise — measured as 8 such rows on
    a C/POSIX codebase before this filter. A nested acquisition is
    already a `lock_acquisitions` row in its own right, so listing it here would
    also duplicate it. The excluded set is derived from the ACTIVE patterns
    (defaults plus whatever the repo declared), never a fixed name list.

    @brief Collect the calls a section really contains.
    @version 4
    """
    from .call_edges import _callee_name_node

    floor, ceiling = window
    out: list[list[Any]] = []
    for node in _nodes_of_type(block, "call_expression", floor):
        if node.start_byte >= ceiling:
            break
        raw_callee = node.child_by_field_name("function")
        name_node = _callee_name_node(raw_callee)
        if name_node is None or _shadowed(node, block, by_block):
            continue
        name = node_text(name_node, src)
        if name not in primitives:
            ## Carry whether the callee was a BARE identifier. A bare `f()` IS the whole
            ## call, so a unique indexed `f` really is it; `x.f()` had its receiver
            ## unwrapped away, so a unique indexed `f` is a fact about the INDEX, not the
            ## call. `_resolve_callee` cannot tell them apart without this and was stamping
            ## both `resolved` — see its docstring for what that cost.
            bare = raw_callee is not None and raw_callee.type == "identifier"
            out.append([name, node.start_point[0] + 1, bare])
    return out


## @brief Persist one acquisition's membership rows.
## @param conn Open connection.
## @param acquisition_id The `lock_acquisitions` row these calls run under.
## @param calls `[callee_name, line]` pairs from the harvest payload.
## @param name_to_rowids Function-name index from `_build_function_indexes`.
## @return Number of rows inserted.
## @version 2
## @req REQ-DDB-SCHEMA-011
def insert_section_calls(
    conn: sqlite3.Connection,
    acquisition_id: int,
    calls: list[list[Any]],
    name_to_rowids: dict[str, list[int]],
) -> int:
    """A NAME matching several memberdefs does NOT fan out into several rows the
    way `call_edges` does. A call site is one physical call, so N rows would
    answer "what runs under this lock" with N functions where one runs, and
    nothing would mark the N-1 as invented. The row stays single, `callee_rowid`
    stays NULL, and `resolution` records that the name was ambiguous — the same
    never-borrow-another-symbol's-rowid rule the thread layer follows.

    @brief Insert membership rows, resolving callee names conservatively.
    @return Rows inserted.
    @version 2
    """
    inserted = 0
    for call in calls:
        callee_name, call_line = call[0], call[1]
        ## Tolerate a 2-element payload: an index cached before the shape gained the
        ## bare flag replays as member-ish, which is the conservative reading.
        bare = bool(call[2]) if len(call) > 2 else False
        candidates = name_to_rowids.get(callee_name, [])
        rowid, resolution = _resolve_callee(candidates, bare=bare)
        inserted += conn.execute(
            "INSERT OR IGNORE INTO critical_section_calls "
            "(acquisition_id, callee_rowid, callee_name, call_line, resolution) "
            "VALUES (?, ?, ?, ?, ?)",
            (acquisition_id, rowid, callee_name, call_line, resolution),
        ).rowcount
    return inserted


## @brief Pin a callee name to a rowid, or record why it could not be.
## @param candidates Every memberdef rowid the name denotes.
## @param bare True when the call site wrote a BARE identifier, not `x.f()` / `A::f()`.
## @return (rowid or None, a `SECTION_MATCH` member).
## @version 2
## @dg_internal
def _resolve_callee(candidates: list[int], *, bare: bool = False) -> tuple[int | None, str]:
    """Three genuinely different outcomes, and the third is the majority: a
    critical section is full of stdlib, vendor and macro calls that have no
    memberdef at all. Filing those as 'fuzzy' — `call_match`'s nearest member —
    would claim an in-repo callee was ambiguous when there was never a candidate.

    A UNIQUE NAME IS NOT EVIDENCE ABOUT A RECEIVER — the same rule `fd384e5` applied to
    `ast_member` call edges, which this resolver did not follow, so the defect survived in a
    second place. `len(candidates) == 1` used to mean RESOLVED unconditionally. For a bare
    `f()` that is right: the name is the whole call. For `x.f()` the receiver was unwrapped
    away, so one indexed `f` is a fact about the INDEX, not about the call — and the stdlib
    method it really named has no memberdef to compete with it.

    Measured on the public entropic index at build version 15, before this: of 17
    cross-function two-lock holdings reported by `lock_nestings`, **13 were fabrications**.
    `router_dirty_.store(true, std::memory_order_release)` is `std::atomic::store`, which is
    not indexed, so it matched the single indexed `store` — `PromptCache::store` — and the
    layer reported `IdentityManager`'s mutex nesting inside `PromptCache`'s. One `swap` row
    was `std::vector::swap` read as `AdapterManager::swap` the same way.

    That is worse than the `ast_member` fan-out it mirrors, because `lock_nestings` is
    described to models as the raw material for a deadlock argument, and 76% of its rows were
    invented. The entropic rubric's Q2 marks 6-8 name these exact rows, and BOTH benchmark
    arms missed all three — nobody rediscovered it from the output.

    DEMOTE, DO NOT DROP, and that was measured rather than assumed. Nulling the rowid for
    member calls took `lock_nestings` from 17 rows to **ZERO** — because the one GENUINE
    nesting is a member call too: `it->second.has_access(...)` on an `MCPKeySet`. The false
    `store` and the true `has_access` are syntactically identical; only the receiver's TYPE
    separates them, which is the field-receiver problem #75 deferred as a much larger job.
    Trading 13 false positives for a layer that returns nothing is a worse answer, and it is
    the same conclusion `fd384e5` reached: keep the rowid, record the weakness, let the
    consumer weigh it.

    @brief Resolve one callee name conservatively.
    @version 3
    """
    if len(candidates) == 1:
        return candidates[0], SECTION_MATCH_RESOLVED if bare else SECTION_MATCH_RECEIVER_UNVERIFIED
    if candidates:
        return None, SECTION_MATCH_AMBIGUOUS
    return None, SECTION_MATCH_EXTERNAL
