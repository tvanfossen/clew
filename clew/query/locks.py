# SPDX-License-Identifier: MIT
"""R2 accessors over the R1 lock layer (L1 identity + L2 membership).

Four questions, and the first two are the ones L2 exists to make answerable:

  `locks_held_when(db, fn)`  — which locks are held when `fn` is called. The
                               input a deadlock or race argument starts from.
  `runs_under_lock(db, name)`— what runs inside a named lock's critical
                               sections. The inverse view, per lock.
  `sections_in(db, fn)`      — every hold `fn` itself takes, with its extent.
  `lock_nestings(db)`        — outer→inner pairs observed across a call, i.e.
                               the two-lock holdings that only exist because a
                               section spans a call. FOLDED INTO `lock_roster`
                               for the MCP surface (round-3 tool cull) and kept
                               here for direct R2 consumers: the round trip it
                               cost is a cost of the MCP boundary, not of the
                               library, exactly as the response byte cap is.
  `lock_roster(db)`          — the whole layer in one answer: every lock, the
                               mutex count that is not the row count, the origin
                               split, and the nestings with what a zero means.

SCOPE TRAVELS WITH THE NAME, always. `mutex_` is a real member name in many C++
classes, so a bare lock name is not an identity — every model here carries
`lock_scope` beside it, and `runs_under_lock` accepts an optional scope to
disambiguate rather than silently unioning unrelated mutexes.

Every accessor degrades to `[]` on a database that predates the layer (#41): the
lock tables are created unconditionally by a current build, but a consumer may
be pointed at an older artifact and must get an empty answer, not an
`OperationalError`.

@brief Query accessors for locks, critical sections, lock nesting and the roster.
@version 2
"""

from __future__ import annotations

import sqlite3
from collections.abc import Sequence

from ..vocabulary import EXTERNAL_ROOT_COLUMN
from ._common import DbSource, connect, has_columns, rowids_for_name, table_exists
from .models import (
    CriticalSection,
    LockEntry,
    LockInventory,
    LockNesting,
    LockNestingPair,
    OriginSplit,
    SectionCall,
)

## Columns every section query selects, in the order `_build_section` reads
## them. Spelled once because three queries share the shape and a column added
## to one SELECT but not another would silently shift the whole tuple unpack.
_SECTION_COLUMNS = """
    a.id, COALESCE(l.name, ''), COALESCE(l.scope, ''), COALESCE(l.kind, ''),
    COALESCE(h.name, ''), COALESCE(p.name, ''),
    a.start_line, a.end_line, a.form, a.mode, a.confidence
"""

_SECTION_FROM = """
    FROM lock_acquisitions a
    LEFT JOIN locks l ON l.id = a.lock_id
    LEFT JOIN memberdef h ON h.rowid = a.holder_rowid
    LEFT JOIN path p ON p.rowid = a.path_rowid
"""


## @brief True when both lock-layer tables the accessors need are present.
## @param conn Open connection.
## @return True when L1 and L2 tables both exist.
## @version 1
## @dg_internal
def _layer_present(conn: sqlite3.Connection) -> bool:
    """Checks BOTH tables, not just one. A database built between L1 and L2
    carries `lock_acquisitions` and no `critical_section_calls`, and a query
    that guarded on the first alone would raise on the join — the exact
    partial-schema failure #41 was about.

    @brief Guard the accessors against a pre-L2 database.
    @version 1
    """
    return table_exists(conn, "lock_acquisitions") and table_exists(conn, "critical_section_calls")


## @brief The calls recorded inside one acquisition's critical section.
## @param conn Open connection.
## @param acquisition_id The `lock_acquisitions` row id.
## @return Ordered SectionCall tuple; empty when the extent was unresolved.
## @version 1
## @dg_internal
def _calls_for(conn: sqlite3.Connection, acquisition_id: int) -> tuple[SectionCall, ...]:
    """@brief Load one section's member calls, in source order."""
    rows = conn.execute(
        "SELECT callee_name, call_line, resolution FROM critical_section_calls "
        "WHERE acquisition_id=? ORDER BY call_line, callee_name",
        (acquisition_id,),
    ).fetchall()
    return tuple(SectionCall(callee=n, line=line, resolution=r) for n, line, r in rows)


## @brief Assemble one CriticalSection from a `_SECTION_COLUMNS` row.
## @param conn Open connection.
## @param row A row shaped by `_SECTION_COLUMNS`.
## @return The populated CriticalSection.
## @version 1
## @dg_internal
def _build_section(conn: sqlite3.Connection, row: tuple) -> CriticalSection:
    """@brief Build one section model, loading its member calls."""
    acq_id, name, scope, kind, holder, path, start, end, form, mode, confidence = row
    return CriticalSection(
        lock=name,
        lock_scope=scope,
        lock_kind=kind,
        holder=holder,
        file=path,
        start_line=start,
        end_line=end,
        form=form,
        mode=mode,
        confidence=confidence,
        calls=_calls_for(conn, acq_id),
    )


## @brief Sections opened by any of the given holder rowids.
## @param conn Open connection.
## @param rowids Holder memberdef rowids — an IDENTITY's rowids, or a name's.
## @return Sections those holders open, in source order; empty when the layer is absent.
## @version 1
## @req REQ-DDB-SCHEMA-011
def sections_for_rowids(conn: sqlite3.Connection, rowids: list[int]) -> list[CriticalSection]:
    """The rowid-scoped half of `sections_in`, split out so the dossier can ask the
    SAME question about a resolved identity rather than about a bare name.

    That distinction is the whole reason this exists rather than the caller reusing
    `sections_in`: `rowids_for_name` unions every function sharing a name, which is
    right for a tool a human typed a name into and wrong inside a payload that has
    already committed to one identity (gh#26).

    @brief Sections opened by a given set of holder rowids.
    @version 1
    """
    if not _layer_present(conn) or not rowids:
        return []
    marks = ",".join("?" * len(rowids))
    rows = conn.execute(
        f"SELECT {_SECTION_COLUMNS} {_SECTION_FROM} "
        f"WHERE a.holder_rowid IN ({marks}) ORDER BY p.name, a.start_line",
        rowids,
    ).fetchall()
    return [_build_section(conn, r) for r in rows]


## @brief Sections that hold a lock across a call to any of the given rowids.
## @param conn Open connection.
## @param rowids Callee memberdef rowids — an IDENTITY's rowids, or a name's.
## @return Sections whose membership calls one of those rowids, in source order.
## @version 1
## @req REQ-DDB-SCHEMA-011
def locks_held_for_rowids(conn: sqlite3.Connection, rowids: list[int]) -> list[CriticalSection]:
    """The rowid-scoped half of `locks_held_when`, split out for the dossier on the
    same grounds as `sections_for_rowids`.

    @brief Sections holding a lock across a call to one of these rowids.
    @version 1
    """
    if not _layer_present(conn) or not rowids:
        return []
    marks = ",".join("?" * len(rowids))
    rows = conn.execute(
        f"SELECT DISTINCT {_SECTION_COLUMNS} {_SECTION_FROM} "
        f"JOIN critical_section_calls c ON c.acquisition_id = a.id "
        f"WHERE c.callee_rowid IN ({marks}) ORDER BY p.name, a.start_line",
        rowids,
    ).fetchall()
    return [_build_section(conn, r) for r in rows]


## @brief Every critical section a function itself opens.
## @param db Path | str | sqlite3.Connection to the clew.db.
## @param fn Function name, bare or class-qualified.
## @return Sections held by `fn`, in source order; empty when it takes no lock.
## @version 3
## @req REQ-DDB-SCHEMA-011
def sections_in(db: DbSource, fn: str) -> list[CriticalSection]:
    """Resolved over EVERY rowid the name denotes, via `rowids_for_name` — the
    same correction #42 applied to `thread_of`. A qualified name out of another
    accessor (`SerialLinkPort::transmit`) matches no bare `memberdef.name`,
    and a bare ambiguous name denotes several real functions; resolving to one
    canonical rowid answers confidently for the wrong one.

    @brief List the locks a function takes and what runs inside each.
    @version 3
    """
    with connect(db) as conn:
        return sections_for_rowids(conn, rowids_for_name(conn, fn))


## @brief Which locks are held at the moment a function is called.
## @param db Path | str | sqlite3.Connection to the clew.db.
## @param fn Function name, bare or class-qualified.
## @return Sections whose membership contains a call to `fn`, in source order.
## @version 2
## @req REQ-DDB-SCHEMA-011
def locks_held_when(db: DbSource, fn: str) -> list[CriticalSection]:
    """The question L1 could not answer at all. Matches on the RESOLVED callee
    rowid, never on the name: a name-only match would report every same-named
    function's holds as this one's, which is the fabricated-synchronization
    error the whole layer is built to avoid. A call site whose callee was
    ambiguous therefore does NOT contribute here — it is still recorded, with
    `resolution='ambiguous'`, and visible through `runs_under_lock`.

    The returned sections carry their FULL membership, not just the matching
    call, because "what else runs under the lock I am about to contend for" is
    the next question every caller asks.

    @brief List the locks held whenever this function is called.
    @version 2
    """
    with connect(db) as conn:
        return locks_held_for_rowids(conn, rowids_for_name(conn, fn))


## @brief Every critical section of one named lock.
## @param db Path | str | sqlite3.Connection to the clew.db.
## @param lock Lock name as it appears in the source (e.g. "mutex_").
## @param scope Optional owning scope ("class:EventQueue") to disambiguate.
## @return Sections of the matching lock(s), in source order.
## @version 2
## @req REQ-DDB-SCHEMA-011
def runs_under_lock(db: DbSource, lock: str, scope: str | None = None) -> list[CriticalSection]:
    """`scope` is optional but rarely optional in practice: `mutex_` names a
    different mutex in each class that declares one, so omitting it unions
    unrelated locks. It is left optional rather than required because a
    file-scope C mutex (`shadow_msg_mutex`) genuinely is unique by name, and
    every returned section carries `lock_scope` so a caller can always tell
    which it got.

    @brief List every hold of a lock and what runs inside each.
    @version 2
    """
    with connect(db) as conn:
        if not _layer_present(conn) or not table_exists(conn, "locks"):
            return []
        clause = "l.name = ?" + (" AND l.scope = ?" if scope is not None else "")
        params = (lock, scope) if scope is not None else (lock,)
        rows = conn.execute(
            f"SELECT {_SECTION_COLUMNS} {_SECTION_FROM} "
            f"WHERE {clause} ORDER BY l.scope, p.name, a.start_line",
            params,
        ).fetchall()
        return [_build_section(conn, r) for r in rows]


## Two locks held at once because a section SPANS a call into a function that
## takes another lock. Deliberately joined on `callee_rowid` (never a name) and
## filtered to distinct lock IDENTITIES, so a recursive re-entry into the same
## lock is not reported as a nesting. `lock_id IS NOT` rather than `!=` because
## SQL's `!=` is NULL-propagating: an acquisition with no resolved identity
## would otherwise vanish from the comparison rather than being excluded.
## DISTINCT, not GROUP BY: the callee may take the same inner lock at several
## sites of its own, and each would otherwise repeat one outer call site.
_NESTING_SQL = """
    SELECT DISTINCT lo.name, lo.scope, li.name, li.scope,
           COALESCE(callee.name, ''), COALESCE(h.name, ''), COALESCE(p.name, ''), c.call_line,
           c.resolution
    FROM critical_section_calls c
    JOIN lock_acquisitions a ON a.id = c.acquisition_id
    JOIN lock_acquisitions inner_acq ON inner_acq.holder_rowid = c.callee_rowid
    JOIN locks lo ON lo.id = a.lock_id
    JOIN locks li ON li.id = inner_acq.lock_id
    LEFT JOIN memberdef callee ON callee.rowid = c.callee_rowid
    LEFT JOIN memberdef h ON h.rowid = a.holder_rowid
    LEFT JOIN path p ON p.rowid = a.path_rowid
    WHERE c.callee_rowid IS NOT NULL AND lo.id IS NOT li.id
    ORDER BY lo.scope, lo.name, li.scope, li.name, p.name, c.call_line
"""


## @brief Every outer→inner lock pair observed across a call, on an open connection.
## @param conn Open connection.
## @return Nesting records, deterministically ordered; empty when the layer is absent.
## @version 1
## @req REQ-DDB-SCHEMA-011
def nestings_on(conn: sqlite3.Connection) -> list[LockNesting]:
    """SPLIT OUT SO `lock_roster` CAN FOLD THE NESTINGS IN WITHOUT A SECOND CONNECTION.
    The roster and the nestings read the same two tables — the nestings are a derived
    view of the roster's own acquisitions, self-joined across a call — so answering both
    from one open connection is the natural shape, and it is what lets the MCP surface
    drop `lock_nestings` as a separate round trip.

    The connection-taking half is public rather than `_`-private because
    `sections_for_rowids` and `locks_held_for_rowids` above set that precedent for the
    same reason: a caller that already holds a connection should not be forced through
    `connect` again.

    @brief Load the nestings from an already-open connection.
    @return Nesting records; empty when the lock tables are absent.
    @version 1
    """
    if not _layer_present(conn) or not table_exists(conn, "locks"):
        return []
    rows = conn.execute(_NESTING_SQL).fetchall()
    return [
        LockNesting(
            outer=outer,
            outer_scope=outer_scope,
            inner=inner,
            inner_scope=inner_scope,
            via=via,
            holder=holder,
            file=path,
            line=line,
            via_resolution=via_resolution,
        )
        for outer, outer_scope, inner, inner_scope, via, holder, path, line, via_resolution in rows
    ]


## @brief Every outer→inner lock pair observed across a call.
## @param db Path | str | sqlite3.Connection to the clew.db.
## @return Nesting records, deterministically ordered; empty when none exist.
## @version 6
## @req REQ-DDB-SCHEMA-011
def lock_nestings(db: DbSource) -> list[LockNesting]:
    """KEPT AS A LIBRARY FUNCTION AFTER THE MCP TOOL WAS DELETED, deliberately. What the
    tool cull removed is a ROUND TRIP in a model's prompt, and a round trip is a cost that
    exists only at the MCP boundary — the same reason the response byte cap lives there and
    nowhere else. A direct R2 consumer has no context window and must keep being able to
    ask this question on its own; `lock_roster().nestings` is the same rows for a caller
    that wants the whole layer.

    The measurement L1 recorded as impossible. Within a single function both
    real codebases showed ZERO simultaneous two-lock holdings, which is why
    ordering was deferred; the real ones are cross-function and appear only once
    membership exists. Measured after L2 landed: a real C++ codebase has 3 (verified against
    source — `SerialLinkPort::transmit` holds `tx_mutex_` and calls
    `tap_record`, which takes `tap_mutex_`), a C/POSIX codebase has 0.

    This reports OBSERVATIONS, not a verdict. A cycle over these pairs is what a
    deadlock check would look for, and it is deliberately still absent: three
    pairs with no opposing order is not evidence of a cycle, and inventing a
    ranking from it would be the same guess this layer refuses everywhere else.

    EVERY ROW CARRIES `via_resolution`, AND MOST ROWS ARE WEAK. A nesting is only as good as
    the call that creates it. Measured on the public entropic index at build version 16: 17
    nestings, of which **13 rest on a member call whose receiver was never verified** —
    `router_dirty_.store(...)` is `std::atomic::store`, unindexed, matched to the single
    indexed `store` (`PromptCache::store`). Only `auth_mutex_ -> key_mutex_` is confirmed
    against source.

    Filtering them out was tried and is WRONG: it takes this function to zero rows, because
    the one genuine nesting is a member call too (`it->second.has_access(...)` on an
    `MCPKeySet`). The false and the true are syntactically identical; only the receiver's
    TYPE separates them, which is the field-receiver problem #75 deferred. So they are
    reported with their weakness attached rather than silently kept or silently dropped.

    @brief List the two-lock holdings that span a call, each with its evidence strength.
    @version 6
    """
    with connect(db) as conn:
        return nestings_on(conn)


## What `row_meaning` says when the table is not in this index at all. Distinct from
## "this repo has no locks", and the distinction is the standing lesson: an absent table
## is a fact about the BUILD, never evidence about the code. A caller that cannot tell
## the two apart will report a threadless index and a pre-layer index identically.
_ABSENT_MEANING = (
    "the `locks` table is not present in this index, which predates the lock layer — "
    "this is a fact about the BUILD and is NOT evidence that the repo has no mutexes. "
    "Rebuild to answer the question."
)

## SQL for the inventory. LEFT JOIN, not JOIN: a lock that is DECLARED and never
## ACQUIRED must appear with zero acquisitions rather than vanish. Measured on a real
## C++ target there is exactly one such mutex, and "declared but never taken" is a
## finding — an inner join would have silently answered "that lock does not exist".
## `{external}` is INTERPOLATED and not bound, because a column name cannot be a bound
## parameter — and it is either the vocabulary constant or the literal `''`, never caller text.
## An index predating gh#335 has no such column, and selecting it would raise
## `OperationalError` rather than degrade, which is the contract `has_columns` exists to keep.
_ROSTER_SQL = """
    SELECT l.name, l.scope, l.kind, l.identity_confidence, l.source,
           COALESCE(p.name, ''), l.decl_line, COUNT(a.id), {external}, p.rowid
      FROM locks l
      LEFT JOIN path p ON p.rowid = l.decl_path_rowid
      LEFT JOIN lock_acquisitions a ON a.lock_id = l.id
     GROUP BY l.id
     ORDER BY COUNT(a.id) DESC, l.name, l.scope
"""


## @brief The roster SQL, with the external column selected only when the index carries it.
## @param conn Open connection.
## @return Executable SQL text.
## @version 1
## @dg_internal
def _roster_sql(conn: sqlite3.Connection) -> str:
    """`''` for a pre-gh#335 index, which reads as "every lock is first party" — TRUE for such an
    index, because it excluded nested trees outright rather than tagging them. The same
    substitution `coverage._file_rows` makes, for the same reason and stated the same way.

    @brief Build the roster SQL for this index's schema.
    @return SQL text.
    @version 1
    """
    tagged = has_columns(conn, "path", EXTERNAL_ROOT_COLUMN)
    return _ROSTER_SQL.format(external=f"p.{EXTERNAL_ROOT_COLUMN}" if tagged else "''")


## What `nesting_meaning` says when NO section spans a call into another lock holder. The
## definitive-negative wording the deleted `lock_nestings` tool's empty envelope carried, kept
## verbatim in substance because it is the sentence that makes the follow-up call pointless:
## a caller has to be told that zero is an ANSWER, not a gap it should go probing for.
_NO_NESTING_MEANING = (
    "0 two-lock holdings: no critical section in this index spans a call into a function that "
    "takes a second lock. This is a definitive empty result from the database, not an error and "
    "not a missing layer — it is the common case for flat C code with file-scope mutexes. It is "
    "NOT a proof of deadlock-freedom, and there is no further query to run for it."
)


## @brief Collapse nesting SITES onto nesting IDENTITIES, keeping the strongest exemplar.
## @param nestings Every site, as `nestings_on` returns them.
## @return One pair per distinct (outer, outer_scope, inner, inner_scope), site counts kept.
## @version 1
## @dg_internal
def _nesting_pairs(nestings: list[LockNesting]) -> tuple[LockNestingPair, ...]:
    """THE EXEMPLAR IS THE FIRST RESOLVED SITE WHEN THE PAIR HAS ONE, and that is the whole
    reason this is not a plain `dict` insertion. `nestings_on` orders by scope and name, not
    by evidence, so keeping the first row seen would hand a caller an unverified-receiver
    site to go and read while a confirmed one sat behind it in the same group. Measured on
    the public entropic index, 19 of 26 sites are unverified, so first-seen would pick a weak
    exemplar most of the time.

    ORDER IS PRESERVED from the SQL, which is already deterministic, so two builds of the
    same index produce the same payload — the property the ORDER BY in `_NESTING_SQL` exists
    for, and one a `set` would have destroyed.

    @brief Group sites by pair identity, counting them and picking the best exemplar.
    @return One LockNestingPair per identity, in first-seen order.
    @version 1
    """
    grouped: dict[tuple[str, str, str, str], list[LockNesting]] = {}
    for n in nestings:
        grouped.setdefault((n.outer, n.outer_scope, n.inner, n.inner_scope), []).append(n)
    pairs = []
    for (outer, outer_scope, inner, inner_scope), sites in grouped.items():
        resolved = [s for s in sites if s.via_resolution == "resolved"]
        best = resolved[0] if resolved else sites[0]
        pairs.append(
            LockNestingPair(
                outer=outer,
                outer_scope=outer_scope,
                inner=inner,
                inner_scope=inner_scope,
                sites=len(sites),
                resolved_sites=len(resolved),
                via=best.via,
                holder=best.holder,
                file=best.file,
                line=best.line,
            )
        )
    return tuple(pairs)


## @brief State the nesting count, the pair semantics and the evidence weakness in one sentence.
## @param pairs The collapsed pairs folded into this inventory.
## @param sites How many call sites those pairs were collapsed from.
## @return The sentence for `LockInventory.nesting_meaning`.
## @version 2
## @dg_internal
def _nesting_meaning(pairs: tuple[LockNestingPair, ...], sites: int) -> str:
    """THE WEAK-EVIDENCE COUNT IS STATED, NOT FILTERED, and stating it is the whole reason this
    sentence exists rather than a bare count. A nesting is only as good as the call that creates
    it: measured on the public entropic index, most rows rest on a member call whose receiver was
    never verified. Dropping those was tried and takes the layer to ZERO, because the one genuine
    nesting is a member call too — so the count ships with its weakness attached, in the same
    payload, rather than a caller having to read `via_resolution` row by row to discover it.

    @brief Build the nesting qualifier sentence.
    @return The sentence.
    @version 2
    """
    if not pairs:
        return _NO_NESTING_MEANING
    weak = sum(1 for p in pairs if p.resolved_sites == 0)
    return (
        f"{len(pairs)} distinct two-lock holding(s) over {sites} call site(s). Quote "
        f"{len(pairs)}: each row is an ORDERED pair (outer taken first) and `sites` says how "
        f"many call sites produce it, so the site total counts evidence, not nestings. A "
        f"deadlock risk is two sites taking the SAME pair in OPPOSITE orders; compare the pairs, "
        f"because the database reports observations and makes no deadlock claim. {weak} pair(s) "
        f"have resolved_sites=0 — every site resting on a call whose receiver was never verified "
        f"— so do not quote those as confirmed. The full per-site list is lock_nestings in the "
        f"query library."
    )


## @brief Build the inventory rows from the roster SQL result.
## @param rows Rows shaped by `_ROSTER_SQL`.
## @return One LockEntry per row, in the SQL's order.
## @version 1
## @dg_internal
def _entries(rows: list[tuple]) -> tuple[LockEntry, ...]:
    """Split out of `lock_roster` when the nestings folded in, purely to keep that function
    at one readable job. The unpack is spelled out rather than positional-sliced because
    `_ROSTER_SQL` selects ten columns and a column added to the SELECT without a name here
    would silently shift every field after it.

    @brief Convert roster rows to LockEntry models.
    @return The entries.
    @version 1
    """
    return tuple(
        LockEntry(
            name=name,
            scope=scope,
            kind=kind,
            identity_confidence=identity_confidence,
            source=source,
            file=path,
            line=line,
            acquisitions=acquisitions,
            external_root=external_root or "",
            path_resolved=path_rowid is not None,
        )
        for (
            name,
            scope,
            kind,
            identity_confidence,
            source,
            path,
            line,
            acquisitions,
            external_root,
            path_rowid,
        ) in rows
    )


## @brief Every lock in the index, with the mutex count, the origin split and the nestings.
## @param db Database path or open connection.
## @return The inventory; empty and consistent on a database predating the layer.
## @version 4
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-011
def lock_roster(db: DbSource) -> LockInventory:
    """THE ENUMERATION THE LAYER DID NOT ANSWER. Every other accessor here needs a
    name the caller must already hold — `runs_under_lock` a lock name, the rest a
    function name — while `thread_roster` in the sibling layer takes no argument and
    lists every thread. Same shape of data, and only one of the two had an inventory.

    Measured cost of the gap, from a live acceptance run against a question whose
    first instruction was "enumerate the mutexes it uses": one cell spent 47 of its 64
    tool calls on `lookup_class`, walking classes hoping to find mutex members, and
    another 26 on `runs_under_lock` guessing names. The 56 rows it wanted sat in one
    table. That cost lands in a matrix as "the index arm is expensive" rather than
    "one round trip is missing", so a usability defect reads as a capability gap.

    ORDERED BY ACQUISITION COUNT, descending. "Enumerate the mutexes, then report what
    runs inside a heavily-used one" is the actual question, so the lock a caller most
    likely wants second is the first row rather than something to sort for.

    AND `distinct_mutexes` ALONE STEERED CALLERS INTO A WRONG ATTRIBUTION (gh#352). This payload
    used to end with "Quote distinct_mutexes as the mutex count" full stop, and on the public
    [tvanfossen/entropic](https://github.com/tvanfossen/entropic) index that number is 97 — of
    which 52 belong to the vendored `extern/llama.cpp` submodule. So the tool instructed a caller
    to attribute the majority of another repository's locks to entropic, and the rubric had begun
    compensating by widening a mark to accept 97 "when attributed and split". `origin` now ships
    the decomposition beside the count, and the sentence names the first-party figure first.

    NOTHING IS FILTERED. Every lock is still returned; the split is reported next to them. A
    roster that dropped submodule locks would make a `chain_trace` into that submodule
    inexplicable, and an omission that reads as an empty answer is the failure mode this project
    keeps paying for.

    AND IT ANSWERS THE NESTING QUESTION IN THE SAME CALL (round-3 tool cull). `lock_nestings`
    was a separate MCP tool over the SAME two tables — the nestings are this inventory's own
    acquisitions self-joined across a call, not a second layer. Measured on the acceptance
    mbedtls index it returned ZERO rows, and three of three observed runs called it anyway,
    because a roster that says nothing about nesting gives a caller no way to know the follow-up
    is pointless. It now says so: `nestings` is always present, and `nesting_meaning` states what
    a zero means in the words that stop a retry.

    THE THREAD ROSTER DELIBERATELY DID NOT FOLD IN. It reads a different table, answers a
    different question, and the merge tax is asymmetric — measured, a caller wanting entropic's
    3,183-byte thread roster would have paid 32,258 bytes to get it, while the lock question pays
    12% to carry the threads. A fold is only cheap in one direction, and `thread_roster` is
    called when the QUESTION mentions threads rather than as a reflex, so there is no
    deterministic call to remove there.

    @brief List every lock with its declaration site, acquisition count, origin split and nestings.
    @return LockInventory; `locks` empty when the layer is absent.
    @version 4
    """
    with connect(db) as conn:
        if not table_exists(conn, "locks"):
            return LockInventory(
                locks=(),
                rows=0,
                distinct_mutexes=0,
                row_meaning=_ABSENT_MEANING,
                origin=OriginSplit.of(()),
                nestings=(),
                nesting_meaning=_ABSENT_MEANING,
            )
        entries = _entries(conn.execute(_roster_sql(conn)).fetchall())
        sites = nestings_on(conn)
    nestings = _nesting_pairs(sites)
    ## COLLAPSED ON (name, scope) AND NOT ON name ALONE. `mutex_` is a real member name
    ## in many C++ classes, so collapsing on the bare name would merge unrelated mutexes
    ## from different classes into one — under-counting, which is the opposite error and
    ## the harder one to notice.
    distinct = len({(e.name, e.scope) for e in entries})
    origin = OriginSplit.of(_origin_per_mutex(entries))
    return LockInventory(
        locks=entries,
        rows=len(entries),
        distinct_mutexes=distinct,
        row_meaning=(
            f"{len(entries)} row(s) over {distinct} distinct lock identity(ies). AN IDENTITY IS "
            "NOT AN OBJECT: it is (name, scope, kind) where `name` is the SPELLING of the "
            "operand at an acquisition site, so one object reached by two spellings is two "
            "rows, and one spelling reached from unrelated types is one row. "
            f"Of those {distinct} identities, {origin.first_party} are THIS repository's and "
            f"{origin.external} belong to a vendored submodule"
            + (f" ({', '.join(origin.external_roots)})" if origin.external_roots else "")
            + f", {origin.unresolved} declared in a file this index could not resolve. Quote "
            f"origin.first_party as the count of the repository's own lock IDENTITIES — never "
            f"as its mutex count. The field is still spelled `distinct_mutexes` for "
            f"compatibility and holds that identity count, including other repositories'; "
            f"`rows` is the un-collapsed row count. " + _object_route(entries)
        ),
        origin=origin,
        nestings=nestings,
        nesting_meaning=_nesting_meaning(nestings, len(sites)),
    )


## @brief Route a caller to the lock OBJECTS this layer cannot enumerate.
## @param entries The roster rows.
## @return A sentence naming where the objects are, or how to reach them.
## @version 2
## @dg_internal
def _object_route(entries: Sequence[LockEntry]) -> str:
    """ROUTING, NOT A DISCLAIMER, and the difference is measured in round trips. "This layer does
    not model lock objects" leaves a reader to hunt or — worse, and this is what happened — to
    quote the row count anyway. Naming WHICH spellings are member expressions says the objects are
    struct members and points at the files holding the acquisitions, which collapses the
    follow-up to one grep.

    Derived from the spelling shape, which is all this layer has:

      * `a->b` / `a.b` / `a::b` is a MEMBER expression, so the object is a struct or class
        member. Those are not modelled at all — no member-declaration harvest exists — and the
        same spelling may denote different objects at different call sites.
      * a bare identifier is a variable, and the variable layer often DOES hold it, so `dossier`
        on that name returns its type and declaration sites.

    The repo already answers this way for graded emptiness (name the corpora that DO hold the
    token) and for refused subject kinds (name the alternative). The rosters never got it.

    @brief Compose the object-enumeration route.
    @return The sentence.
    @version 2
    """
    names = [e.name for e in entries]
    members = sorted({n for n in names if any(sep in n for sep in ("->", ".", "::"))})
    bare = sorted({n for n in names if n not in members})
    if not members:
        return (
            "Every identity here is a bare name, so `dossier` on it returns the variable's type "
            "and declaration sites; the objects and the identities coincide."
        )
    shown = ", ".join(members[:4]) + (" …" if len(members) > 4 else "")
    route = (
        f"{len(members)} identity(ies) are MEMBER expressions ({shown}), so each names a struct "
        f"or class member that THIS LAYER does not model — to enumerate those objects, dossier the "
        f"owning type and read its members. "
    )
    if bare:
        ## SAYS WHAT IS SUPPORTED, NOT ONLY WHAT IS NOT. Measured on mbedtls: an agent quoted the
        ## older wording of this note in its Gaps section as its reason for declining to claim the
        ## per-context mutexes are distinct objects — a claim `dossier(kind='variable')` fully
        ## supports for exactly these bare names, and which it had already half-made. The caveat
        ## was true of the LAYER and was read as true of the INDEX, and it cost two graded marks.
        ##
        ## So the limit and the route now sit in one sentence, and the route names the ARGUMENT.
        ## "`dossier` on those" is not actionable when the caller has just been told a lookup does
        ## not model this; `dossier(name, kind='variable')` is.
        route += (
            f"The remaining {len(bare)} ARE separately identifiable: `dossier(<name>, "
            f"kind='variable')` returns each one's type and every declaration site, which is "
            f"enough to state that they are distinct objects."
        )
    return route


## @brief One origin per DISTINCT mutex, so the split matches the headline count.
## @param entries Every roster row.
## @return One origin per (name, scope): the external root, '' first party, None unresolved.
## @version 1
## @dg_internal
def _origin_per_mutex(entries: tuple[LockEntry, ...]) -> list[str | None]:
    """SPLIT THE NUMBER THE PAYLOAD TELLS CALLERS TO QUOTE, which is `distinct_mutexes` and not
    `rows`. Splitting rows instead would produce buckets that sum to a total nobody quotes, and a
    mutex taken with two guard kinds would count twice on one side — a split that is arithmetically
    valid and answers a different question is worse than none.

    A MUTEX WITH ROWS ON BOTH SIDES RESOLVES TO FIRST PARTY. It should not happen — one identity
    is declared in one place — but `(name, scope)` is a collapse, so it is expressible, and a
    collapse that could silently pick either side needs a stated rule. Fail-closed here means
    OURS, the same asymmetry `scope._is_dependency_of_parent` argues: tagging this repo's own
    mutex as somebody else's removes it from the figure an operator acts on, while the reverse
    merely leaves it visible and correctable.

    @brief Reduce rows to one origin per distinct mutex.
    @return Origins, one per distinct mutex.
    @version 1
    """
    per_mutex: dict[tuple[str, str], set[str | None]] = {}
    for entry in entries:
        origin = entry.external_root if entry.path_resolved else None
        per_mutex.setdefault((entry.name, entry.scope), set()).add(origin)
    return ["" if "" in origins else sorted(origins, key=str)[0] for origins in per_mutex.values()]
