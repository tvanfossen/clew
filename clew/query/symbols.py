# SPDX-License-Identifier: MIT
"""Symbol-level R2 queries: resolve / callers / callees / search / threads /
requirement trace, plus the shared edge/thread row→dataclass builders that
`dossier` and `traversal` reuse (DRY).

SQL is ported from the retired walkthrough viz/dbview query layer
(dossier fan-out, definition-
preferring resolution) and extended with the R1 columns
(dispatch_mode / edge_triggered / crosses_thread / to_thread_id → name).
Endpoints are always resolved to NAMES; a name's canonical rowid rides
along via `resolve_rowid`.

`search` reads TWO corpora since gh#10 — indexed symbols and the file-level
documentation `corpus.file_doc_rows` serves — so the file-doc half is imported
from `corpus` rather than duplicated here.

@brief Symbol-level queries + shared edge/thread builders.
@version 2
"""

from __future__ import annotations

import re
import sqlite3

from ..vocabulary import (
    CALL_MATCH,
    CALL_MATCH_FUZZY,
    CALL_SOURCE,
    CALL_SOURCE_AST_MEMBER,
    EDGE_CLASS_CALL,
    EDGE_CLASS_KEY,
    EXTERNAL_ROOT_COLUMN,
    SEARCH_WEIGHT_EXACT_NAME,
    SEARCH_WEIGHT_NAME_SUBSTRING,
    SEARCH_WEIGHT_TOKEN_IN_BRIEF,
    SEARCH_WEIGHT_TOKEN_IN_NAME,
)
from ._common import (
    DbSource,
    candidate_rows,
    connect,
    documented_first,
    function_candidates,
    has_columns,
    identity_rowids,
    is_overloaded,
    liveness_of,
    name_of,
    qualified_name_of,
    resolve_rowid,
    rowids_for_name,
    strip_xml,
    symbol_provenance,
    table_exists,
    to_bool,
)
from .corpus import CLASS_KINDS, class_rows, file_doc_rows, gate_symbol_rows
from .macros import MACRO_KIND
from .models import (
    CallEdge,
    Implementer,
    KeyEdge,
    NameAmbiguity,
    OriginSplit,
    OverrideRef,
    ReqEdge,
    ReqTrace,
    SymbolHit,
    SymbolRef,
    Thread,
    ThreadInventory,
)


## @brief Resolve a name to a definition-preferring SymbolRef, or None.
## @param db Path, str or open connection to a built index.
## @param name Bare function name.
## @param qualified Optional identity from a prior `candidates.qualified`, selecting WHICH same-named function to resolve.
## @return SymbolRef with the function's canonical rowid, kind, and location, plus overload `candidates` when the name is ambiguous; None if no function of that name is indexed (or none of that identity).
## @version 6
## @req REQ-DDB-QUERY-003
## @req REQ-DDB-QUERY-010
def resolve_symbol(db: DbSource, name: str, qualified: str | None = None) -> SymbolRef | None:
    """Resolve a function name to its canonical rowid + location. None when
    no function of that name is indexed. When the name maps to MORE THAN ONE
    distinct signature (a genuine overload, not mere decl/def duality), the
    returned SymbolRef carries the alternatives in `candidates` (capped) so a
    consumer knows the primary pick was one of several and can re-query the
    specific one; unambiguous names return an empty `candidates`.

    `qualified` closes that loop (gh#37): pass a `candidates[i].qualified` back and
    this resolves THAT identity rather than the definition-preferring first. It
    remains OPTIONAL, and the bare-name path is byte-identical to what it was —
    the common case is a unique name, and requiring a selector there would break
    every existing caller to fix a case they do not have.

    `candidates` is still reported on a DISAMBIGUATED call, deliberately, because
    the name is still ambiguous — the reply says "you asked for this one, and these
    others exist". Suppressing it would make a narrowed answer look unique.

    @brief Resolve a function name to a SymbolRef, flagging overloads.
    @version 6
    """
    with connect(db) as conn:
        cands = function_candidates(conn, name, qualified)
        if not cands:
            return None
        rowid = cands[0][0]
        row = conn.execute(
            "SELECT m.name, m.kind, COALESCE(p.name,''), m.bodystart, m.bodyend "
            "FROM memberdef m LEFT JOIN path p ON p.rowid = m.file_id "
            "WHERE m.rowid=?",
            (rowid,),
        ).fetchone()
        ## Ambiguity is a property of the NAME, not of this call, so it is measured
        ## against every same-named row rather than against the filtered subset — a
        ## disambiguated call to a 3-way name must not report itself as unambiguous.
        all_cands = function_candidates(conn, name) if qualified is not None else cands
        overloads = candidate_rows(conn, name, all_cands) if is_overloaded(all_cands) else []
        provenance = symbol_provenance(conn, rowid)
    return SymbolRef(
        name=row[0],
        rowid=rowid,
        kind=row[1],
        file=row[2],
        line_start=row[3],
        line_end=row[4],
        candidates=overloads,
        provenance=provenance,
    )


## The R1 semantic columns `shared_key_edges` GREW after build_version 2. A
## database built by an older clew has the table with only the pre-R1 seven
## columns, so every query naming one of these has to be guarded.
_KEY_R1_COLUMNS = ("dispatch_mode", "edge_triggered", "crosses_thread", "to_thread_id")


## @brief The R1 projection + threads JOIN a database can actually support.
## @param conn Open connection.
## @return (select-list fragment for dispatch_mode/edge_triggered/crosses_thread/to_thread, threads JOIN clause).
## @version 2
## @dg_internal
def _key_r1_projection(conn: sqlite3.Connection) -> tuple[str, str]:
    """Two independent degradations, both silent-crash sources before this
    existed. A stale database predating R1 has no `dispatch_mode` at all — the
    query then selects the schema's OWN default, 'unknown', so a consumer reads
    "this hand-off's synchrony is unknown" instead of catching an
    `OperationalError`, which is exactly what that value means. A database with
    R1 columns but no `threads` table can still name the columns but has no
    thread to resolve, so only the name degrades to NULL.

    Fabricating nothing is the point: every degraded field lands on the value
    that already means "not known here", never on a plausible-looking one.

    @brief Choose the shared-key R1 select-list a given database supports.
    @version 1
    """
    if not has_columns(conn, "shared_key_edges", *_KEY_R1_COLUMNS):
        return "'unknown', NULL, NULL, NULL", ""
    if not table_exists(conn, "threads"):
        return "s.dispatch_mode, s.edge_triggered, s.crosses_thread, NULL", ""
    return (
        "s.dispatch_mode, s.edge_triggered, s.crosses_thread, t.name",
        "LEFT JOIN threads t ON t.id = s.to_thread_id",
    )


## @brief Raw shared-key rows for one focal function in one role.
## @param conn Open connection.
## @param fn Focal function name.
## @param as_writer True selects the rows where `fn` writes the key; False, where it reads.
## @return Rows of (other_name, key_name, edge_kind, source, confidence, dispatch_mode, edge_triggered, crosses_thread, to_thread_name); empty when the table is absent.
## @version 3
## @dg_internal
def _key_edge_rows(conn: sqlite3.Connection, fn: str, *, as_writer: bool) -> list[tuple]:
    """The ONE per-function shared-key JOIN. Three surfaces need the identical
    JOIN + R1 column list — `key_edges` (→ KeyEdge, for dossier's split
    writes/reads), `_call_edges` (→ a key-class CallEdge, for the #46 merge) and
    `traversal._key_hops` (→ Hop) — and it was written out twice before, so an R1
    column added to one shape was silently missing from the other.

    Returned as raw tuples deliberately: each caller maps them into a DIFFERENT
    dataclass, so materializing one here would force two of the three to unpack
    a shape they do not want.

    @brief Run the per-function shared-key JOIN once, for every consumer.
    @version 2
    """
    if not table_exists(conn, "shared_key_edges"):
        return []
    r1, tjoin = _key_r1_projection(conn)
    focal, other = ("w", "r") if as_writer else ("r", "w")
    sql = (
        f"SELECT DISTINCT {other}.name, s.key_name, s.edge_kind, s.source, "
        f"s.confidence, {r1} "
        "FROM shared_key_edges s "
        "JOIN memberdef w ON w.rowid = s.writer_rowid "
        "JOIN memberdef r ON r.rowid = s.reader_rowid "
        f"{tjoin} "
        f"WHERE {focal}.name=? ORDER BY s.key_name, s.source, {other}.name"
    )
    return conn.execute(sql, (fn,)).fetchall()


## @brief Shared-key neighbours of `fn`, shaped as key-class CallEdges.
## @param conn Open connection.
## @param fn Focal function name.
## @param as_writer True to list the readers of what `fn` writes; False, the writers of what it reads.
## @return List of CallEdge tagged `edge_class='key'`, carrying the R1 semantics.
## @version 2
## @dg_internal
def _dataflow_edges(conn: sqlite3.Connection, fn: str, *, as_writer: bool) -> list[CallEdge]:
    """Map the shared-key rows into the SAME dataclass the call rows use so the
    two can be merged into one neighbour list (#46). `confidence` is None and the
    row's certainty goes to `strength`: a key row's certainty is a `key_strength`
    (low/medium/high), not a `call_match` (exact/resolved/fuzzy), and putting it
    in `confidence` would make a consumer's `confidence != 'fuzzy'` filter admit
    every dataflow row unconditionally.

    @brief Build key-class CallEdge neighbours for one direction.
    @version 2
    """
    return [
        CallEdge(
            name=oname,
            rowid=resolve_rowid(conn, oname) or -1,
            source=src,
            confidence=None,
            edge_class=EDGE_CLASS_KEY,
            strength=conf,
            key_name=k,
            edge_kind=kind,
            dispatch_mode=dm,
            edge_triggered=to_bool(et),
            crosses_thread=to_bool(ct),
            to_thread=tthr,
        )
        for oname, k, kind, src, conf, dm, et, ct, tthr in _key_edge_rows(
            conn, fn, as_writer=as_writer
        )
    ]


## @brief Sort key ranking one layer's evidence for the same endpoint.
## @param source The extraction layer that produced the row.
## @param confidence The row's call_match value (may be None).
## @return (confidence rank, negated declared-layer position) — higher is stronger.
## @version 1
## @dg_internal
def _variant_rank(source: str, confidence: str | None) -> tuple[int, int]:
    """Ranks by resolution confidence first, then by the layer's position in the
    DECLARED `CALL_SOURCE` order as a deterministic tie-break. That order is the
    pipeline's own layer order, so an equal-confidence tie resolves to the
    earlier, more direct extractor rather than to whatever sorted first.

    An unregistered value ranks LAST rather than raising: this is a read path over
    a database that may predate a vocabulary addition, and refusing to describe an
    edge is worse than describing it as the weakest evidence.

    @brief Rank one (source, confidence) variant of an endpoint.
    @return Comparable rank tuple; higher wins.
    @version 1
    """
    order = (
        CALL_SOURCE.values.index(source)
        if source in CALL_SOURCE.values
        else len(CALL_SOURCE.values)
    )
    return (CALL_MATCH.rank.get(confidence or "", -1), -order)


## @brief Collapse one endpoint's per-layer rows into its strongest evidence.
## @param variants Non-empty list of (source, confidence) for ONE endpoint.
## @return (strongest source, its confidence).
## @version 4
## @dg_internal
def _collapse_variants(variants: list[tuple[str, str | None]]) -> tuple[str, str | None]:
    """The #38 fix, in ONE place because both the per-function surface
    (`_direct_call_edges`) and the traversal surface (`traversal._call_hops`) must
    collapse identically — a neighbour list and a chain through that neighbour
    would otherwise disagree about the same edge's provenance, and the reason
    `_key_edge_rows` exists is that this exact JOIN was once written out twice and
    drifted.

    `call_edges` stores one row per LAYER by design
    (`UNIQUE(caller_rowid, callee_rowid, source)`), so a single logical edge found
    by two layers was surfaced twice. Measured on clew's own index: 520 rows for
    260 distinct pairs — every neighbour list inflated exactly 2x, and every depth
    cap therefore truncating half as many real edges as intended.

    `source` stays a single vocabulary-registered value and must NOT become a
    joined string — that would write an unregistered value into a
    vocabulary-checked field.

    @brief Reduce an endpoint's layer variants to one row.
    @return Strongest source and its confidence.
    @version 4
    """
    return max(variants, key=lambda v: _variant_rank(*v))


## @brief Bucket raw endpoint rows by (bare name, qualified name) identity.
## @param rows Endpoint rows as (name, definition, rowid, has_body, source, confidence).
## @return (name, qualified) -> (definition-preferring rowid, layer variants).
## @version 1
## @dg_internal
def _endpoint_identities(
    rows: list[tuple[str, str, int, int, str, str | None]],
) -> dict[tuple[str, str], tuple[int, list[tuple[str, str | None]]]]:
    """Group raw endpoint rows into ONE bucket per (bare name, qualified name),
    so two unrelated functions sharing a bare name stay separate while a single
    function's declaration and definition rows merge (gh#26).

    The reported rowid is the identity's definition-preferring one — ordered
    `has_body DESC, rowid` to match `resolve_rowid`, so this surface and
    `resolve_symbol` name the same row for the same function. A caller handed a
    declaration rowid could not look up a body.

    Keyed on the bare name as well as the qualified one because the bare name is
    what every other tool on this surface accepts as input, and it must
    round-trip.

    @brief Bucket endpoint rows by (name, qualified name) identity.
    @return (name, qualified) -> (reported rowid, layer variants).
    @version 2
    """
    ranked: dict[tuple[str, str], tuple[int, int]] = {}
    variants: dict[tuple[str, str], list[tuple[str, str | None]]] = {}
    for name, definition, rowid, has_body, source, conf in rows:
        key = (name, qualified_name_of(name, definition))
        # Sort key: body rows first (0 < 1), then lowest rowid.
        rank = (0 if has_body else 1, rowid)
        if key not in ranked or rank < ranked[key]:
            ranked[key] = rank
        variants.setdefault(key, []).append((source, conf))
    return {key: (ranked[key][1], variants[key]) for key in variants}


## @brief Collapse call rows into one call-class CallEdge per endpoint IDENTITY.
## @param conn Open connection.
## @param fn Focal function name.
## @param want_callers True for the functions that call `fn`; False for the ones it calls.
## @param qualified Optional identity selector for the FOCAL side (gh#37).
## @return List of CallEdge tagged `edge_class='call'`, ONE per distinct endpoint identity, each annotated with its known implementors.
## @version 13
## @dg_internal
def _direct_call_edges(
    conn: sqlite3.Connection, fn: str, want_callers: bool, qualified: str | None = None
) -> list[CallEdge]:
    """ONE CallEdge per distinct endpoint IDENTITY (#38 — it used to be one per
    (name, source, confidence), which duplicated every edge that two layers
    found; gh#26 then narrowed "endpoint" from a NAME to an identity).
    `want_callers` selects the functions that call `fn`; otherwise the functions
    `fn` calls.

    NOTE the deliberate divergence from `traversal._call_hops`, which appends
    `AND e.confidence!='fuzzy'`: this surface does NOT filter fuzzy edges. The
    tool descriptions instruct a model to WEIGH `confidence`, and fuzzy edges are
    not a rounding error: **21.3% of this repo's own call edges, and 79.8% of a
    real C++ codebase's** (entropic, 26,101 of 32,720 — re-measured 2026-07-30 after the #75 demotion).
    Filtering here would make the description reference a value that can never
    appear, and on a C++ target would discard three quarters of the graph —
    including the member-call edges (#48) that are mostly fuzzy by construction. chain_trace filters because it EXPANDS
    each hop, where a fuzzy edge multiplies into a wrong subtree; a flat
    neighbour list has no such amplification.

    Each row carries `implementors` (gh#8) when doxygen's `reimplements` relation
    names concrete overrides of the endpoint. It is an ANNOTATION on the existing
    edge, never a new edge and never a confidence upgrade — see `CallEdge`.

    gh#37 THREADS THE SELECTOR ONTO THE FOCAL SIDE, which is where it belongs: the
    focal side is already resolved by IDENTITY (see below), so naming the identity
    outright rather than guessing it from the definition-preferring first row is a
    one-argument change with no new mechanism. The ENDPOINT side keeps its own
    identity bucketing — a caller cannot narrow the far end of an edge, nor should
    they, since that is the answer they asked for.

    @brief Build call-class CallEdge rows for one direction of one function.
    @version 12
    """
    if not table_exists(conn, "call_edges"):
        return []
    # gh#26: the focal side is filtered by ROWID over the resolved IDENTITY, not
    # by name. Filtering by name unioned every same-named function's edges onto
    # whichever one the dossier described -- on this repo's own index
    # `dossier("_classify")` reported 4 callers of which 3 belonged to two OTHER
    # modules' `_classify`, including a self-edge that is genuine recursion in
    # `scope._classify` and pure fabrication in `guidance._classify`. Every
    # fabricated row read `confidence: exact`, because all three extraction
    # layers resolve by name and so all three reached the same wrong function.
    focal_rowids = identity_rowids(conn, fn, qualified)
    if not focal_rowids:
        return []
    endpoint, focal = ("c", "x") if want_callers else ("x", "c")
    marks = ", ".join("?" for _ in focal_rowids)
    ## `''` for an index predating gh#350, so a stale index degrades instead of raising. It is
    ## selected as a SEVENTH column and dropped from the row tuple below, keeping `rows` the
    ## shape `_endpoint_identities` and `_implementors_by_identity` already read.
    via = "e.via_macro_rowid" if has_columns(conn, "call_edges", "via_macro_rowid") else "NULL"
    sql = (
        f"SELECT DISTINCT {endpoint}.name, COALESCE({endpoint}.definition,''), "
        f"{endpoint}.rowid, ({endpoint}.file_id = {endpoint}.bodyfile_id), "
        f"e.source, e.confidence, {via} "
        "FROM call_edges e "
        "JOIN memberdef c ON c.rowid = e.caller_rowid "
        "JOIN memberdef x ON x.rowid = e.callee_rowid "
        f"WHERE {focal}.rowid IN ({marks}) "
        f"ORDER BY {endpoint}.name, {endpoint}.rowid, e.source, e.confidence"
    )
    raw = conn.execute(sql, focal_rowids).fetchall()
    rows = [
        (name, definition, rowid, int(bool(has_body)), source, conf)
        for name, definition, rowid, has_body, source, conf, _via in raw
    ]
    macro_by_identity = _macros_by_identity(conn, raw)
    # Grouped in a dict rather than by SQL aggregation because the collapse rule
    # is a ranking over a vocabulary, not something SQL should encode. Insertion
    # order follows the query's ORDER BY, so (name, rowid) order survives the
    # grouping -- which matters now that two distinct identities can share a bare
    # name and would otherwise be ordered arbitrarily against each other.
    edges: list[CallEdge] = []
    implementors = _implementors_by_identity(conn, rows)
    for identity, (rowid, variants) in _endpoint_identities(rows).items():
        source, conf = _collapse_variants(variants)
        macro_name, expansion = macro_by_identity.get(identity, ("", ""))
        edges.append(
            CallEdge(
                name=identity[0],
                rowid=rowid,
                source=source,
                confidence=conf,
                edge_class=EDGE_CLASS_CALL,
                implementors=implementors.get(identity, ()),
                via_macro=macro_name,
                via_macro_expansion=expansion,
            )
        )
    return edges


## @brief The macro witnessing each endpoint identity's hop, with its expansion.
## @param conn Open connection.
## @param raw Endpoint rows including the trailing via_macro_rowid.
## @return (name, qualified) -> (macro name, expansion text).
## @version 1
## @dg_internal
def _macros_by_identity(
    conn: sqlite3.Connection,
    raw: list[tuple],
) -> dict[tuple[str, str], tuple[str, str]]:
    """THE EXPANSION IS READ, NOT STORED (gh#350). doxygen already records every `#define`'s
    expansion in `memberdef.initializer` — measured populated for 82.9% of Mbed-TLS/mbedtls's
    2,582 macro rows and 80.2% of entropic's 111, byte-identical to doxygen's own database — and
    the pipeline issued ZERO reads against that column. Copying the text onto the edge would
    create a second place for it to go stale; the edge stores the macro's rowid and this joins.

    ATTACHED WHENEVER A MACRO-HOP ROW EXISTS FOR THE PAIR, independently of which layer won the
    confidence collapse. A pair found by both doxygen's direct xref and the macro hop reports the
    stronger `source`, and the macro is still a true statement about how the call is written —
    suppressing it because a stronger layer also saw the pair would hide the only field that
    explains an edge with no matching text in the caller's body.

    An empty expansion is a MACRO WITH NO RECORDED EXPANSION, not a missing macro: the name is
    still returned, because "this hop goes through THIS macro and doxygen recorded no body for
    it" is a different and more useful answer than silence.

    @brief Resolve each identity's witnessing macro and expansion.
    @return Identity -> (macro name, expansion).
    @version 1
    """
    wanted: dict[tuple[str, str], int] = {}
    for name, definition, _rowid, _has_body, _source, _conf, via in raw:
        if via is None:
            continue
        wanted.setdefault((name, qualified_name_of(name, definition)), via)
    if not wanted:
        return {}
    marks = ", ".join("?" for _ in set(wanted.values()))
    lookup = {
        rid: (mname or "", initializer or "")
        for rid, mname, initializer in conn.execute(
            f"SELECT rowid, name, COALESCE(initializer, '') FROM memberdef "
            f"WHERE rowid IN ({marks})",
            tuple(set(wanted.values())),
        )
    }
    return {key: lookup[rid] for key, rid in wanted.items() if rid in lookup}


## @brief Known implementors of each endpoint identity, from doxygen's override relation.
## @param conn Open connection.
## @param rows Raw endpoint rows as (name, definition, rowid, has_body, source, confidence).
## @return (name, qualified) identity → implementor function names; {} when nothing is reimplemented.
## @version 2
## @req REQ-DDB-QUERY-009
def _implementors_by_identity(
    conn: sqlite3.Connection,
    rows: list[tuple[str, str, int, int, str, str | None]],
) -> dict[tuple[str, str], tuple[str, ...]]:
    """gh#8's answer to "what actually runs when this dispatches". A call to a virtual
    base method is, in the index, one edge to the BASE — and for a C++ target that edge
    is usually `fuzzy` besides, because `memberdef.name` is unqualified. The override
    relation is the only thing that says which concrete bodies that call can reach, and
    nothing outside `dispatch_edges.py` read it.

    ONE query for the whole neighbour list, keyed on EVERY rowid the raw rows mention
    rather than on the one reported rowid per identity. That is not defensive padding:
    doxygen records the relation against whichever memberdef it saw the `override` on,
    and `_endpoint_identities` reports the definition-preferring rowid — so keying on
    the reported rowid alone drops the relation exactly when the declaration carried it,
    which is the decl/def duality biting in its usual place.

    Empty when the table is absent, which it is on a C-only or Python target: doxygen
    creates `reimplements` itself, so absence here means the index predates that output
    rather than that the code has no overrides.

    @brief Map endpoint identities to the functions that reimplement them.
    @return identity → implementor names, sorted.
    @version 2
    """
    if not rows or not table_exists(conn, "reimplements"):
        return {}
    identity_of = {
        rowid: (name, qualified_name_of(name, definition)) for name, definition, rowid, *_ in rows
    }
    marks = ", ".join("?" for _ in identity_of)
    found: dict[tuple[str, str], set[str]] = {}
    for base_rowid, impl_name in conn.execute(
        "SELECT r.reimplemented_rowid, m.name FROM reimplements r "
        f"JOIN memberdef m ON m.rowid = r.memberdef_rowid "
        f"WHERE r.reimplemented_rowid IN ({marks})",
        list(identity_of),
    ):
        found.setdefault(identity_of[base_rowid], set()).add(impl_name)
    return {identity: tuple(sorted(names)) for identity, names in found.items()}


## @brief One side of the override relation for a function, name-resolved.
## @param conn Open connection.
## @param fn Focal function name.
## @param want_bases True for what `fn` reimplements; False for what reimplements `fn`.
## @param qualified Optional identity selector for the focal side.
## @return OverrideRef list, ordered by name then rowid; empty when the relation is absent or unmatched.
## @version 3
## @req REQ-DDB-QUERY-009
## @req REQ-DDB-QUERY-010
def _override_refs(
    conn: sqlite3.Connection, fn: str, *, want_bases: bool, qualified: str | None = None
) -> list[OverrideRef]:
    """Both directions from one query, because they differ only in which column of
    `reimplements` is the focal side — and two near-identical SQL strings in one module
    is the drift condition that produced gh#26.

    The focal side is filtered by the resolved IDENTITY's rowids (`identity_rowids`),
    not by name, for the reason gh#26 established: a bare name can denote several
    unrelated functions, and unioning their override relations onto whichever one a
    dossier described would fabricate polymorphism. It is also what makes the decl/def
    duality harmless here — doxygen may record the relation against the declaration and
    the dossier may have chosen the definition.

    AND THIS IS THE SURFACE gh#37 MADE LOAD-BEARING. A virtual base shares its bare
    name with every override BY CONSTRUCTION — that is what `override` means — so
    `overridden_by` on the base, the direction a consumer actually wants, is exactly
    the direction a bare name cannot reach. Measured on this repo's own index: ten
    `reimplements` rows name `Harvester.harvest` as the base and eleven memberdef
    rows are named `harvest`, so the definition-preferring guess picks a SUBCLASS and
    reports `overridden_by: []` — a confident empty answer about the one function
    that has ten. `qualified` is what makes the base addressable.

    @brief Read one direction of the override relation.
    @return OverrideRef list.
    @version 3
    """
    if not table_exists(conn, "reimplements"):
        return []
    focal_rowids = identity_rowids(conn, fn, qualified)
    if not focal_rowids:
        return []
    ## `focal` is the side we KNOW; `other` is the side we are asking for.
    focal, other = (
        ("memberdef_rowid", "reimplemented_rowid")
        if want_bases
        else ("reimplemented_rowid", "memberdef_rowid")
    )
    marks = ", ".join("?" for _ in focal_rowids)
    return [
        OverrideRef(
            name=name,
            rowid=rowid,
            signature=f"{definition or ''}{args or ''}",
            file=path,
            line_start=line_start,
        )
        for name, rowid, definition, args, path, line_start in conn.execute(
            f"SELECT DISTINCT m.name, m.rowid, COALESCE(m.definition,''), "
            "COALESCE(m.argsstring,''), COALESCE(p.name,''), m.bodystart "
            f"FROM reimplements r JOIN memberdef m ON m.rowid = r.{other} "
            "LEFT JOIN path p ON p.rowid = m.file_id "
            f"WHERE r.{focal} IN ({marks}) ORDER BY m.name, m.rowid",
            focal_rowids,
        )
    ]


## @brief The base methods a function reimplements (what it overrides).
## @param db Path, str or open connection to a built index.
## @param fn Focal function name.
## @param qualified Optional identity from a prior `candidates.qualified`, selecting WHICH same-named function to ask about.
## @return OverrideRef list; empty for a non-virtual function or an index without the relation.
## @version 2
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-009
## @req REQ-DDB-QUERY-010
def overrides_of(db: DbSource, fn: str, qualified: str | None = None) -> list[OverrideRef]:
    """Takes a `DbSource` rather than a bare connection, unlike the private
    `_override_refs` it delegates to, because it is EXPORTED — and every public
    accessor on this surface accepts `Path | str | sqlite3.Connection`. `connect`
    yields a caller-supplied connection unchanged, so `dossier` composing this inside
    its own `with connect(...)` block costs nothing.

    @brief What this function overrides.
    @return OverrideRef list.
    @version 2
    """
    with connect(db) as conn:
        return _override_refs(conn, fn, want_bases=True, qualified=qualified)


## @brief The derived methods that reimplement a function (what may run instead).
## @param db Path, str or open connection to a built index.
## @param fn Focal function name.
## @param qualified Optional identity from a prior `candidates.qualified`; USUALLY REQUIRED HERE — see below.
## @return OverrideRef list; empty for a leaf or non-virtual function.
## @version 2
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-009
## @req REQ-DDB-QUERY-010
def overridden_by(db: DbSource, fn: str, qualified: str | None = None) -> list[OverrideRef]:
    """The direction a consumer asking "what actually runs here" wants. See
    `overrides_of` on why this takes a `DbSource`.

    `qualified` IS OPTIONAL IN THE SIGNATURE AND USUALLY NECESSARY IN PRACTICE on
    this direction specifically, which is worth stating rather than leaving to be
    discovered: a base and its overrides share a bare name, so a bare call resolves
    to whichever of them the definition-preferring order puts first, and that is a
    subclass more often than not. See `_override_refs` for the measured case.

    @brief What overrides this function.
    @return OverrideRef list.
    @version 2
    """
    with connect(db) as conn:
        return _override_refs(conn, fn, want_bases=False, qualified=qualified)


## @brief Causal neighbours of `fn` in one direction — calls, optionally + dataflow.
## @param conn Open connection.
## @param fn Focal function name.
## @param want_callers True for inbound neighbours (callers / writers-into), False for outbound.
## @param include_dataflow True to merge the shared-key neighbours in, tagged `edge_class='key'`.
## @param qualified Optional identity selector for the focal side; narrows the CALL half only (see body).
## @return List of CallEdge sorted by (name, edge_class, key_name) — byte-identical to the traversal layer's neighbour order.
## @version 3
## @dg_internal
def _call_edges(
    conn: sqlite3.Connection,
    fn: str,
    want_callers: bool,
    *,
    include_dataflow: bool = False,
    qualified: str | None = None,
) -> list[CallEdge]:
    """The neighbour builder both `callers`/`callees` and `dossier` use.

    `include_dataflow` is the #46 merge. The polarity `want_callers=True ⟺
    as_writer=False` is the causal analogue, not a typo: the "callers" of a
    reader are the functions whose WRITES it observes.

    `dossier` leaves it False because it already composes `writes`/`reads`
    separately — merging there would report every dataflow edge TWICE in one
    payload, in two different shapes.

    The union is sorted by exactly the key `traversal._neighbors` uses, so the
    flat per-function view and the traversal view order the same neighbours the
    same way instead of merely overlapping. Sorting is a no-op on the call-only
    path: the SQL already returns name-ordered rows and Python's sort is stable.

    `qualified` NARROWS THE CALL HALF AND NOT THE DATAFLOW HALF, and that boundary is
    stated rather than hidden. `_direct_call_edges` filters its focal side by rowid
    over the resolved identity, so the selector applies exactly. `_key_edge_rows`
    joins on `memberdef.name` — a pre-existing gh#26-shaped gap in the shared-key
    layer, untouched here — so its rows are still the union over every same-named
    function. Every such row is tagged `edge_class='key'`, which is the field a
    consumer already has to read, and this repo's own index holds zero of them.
    Narrowing one half and silently leaving the other would be the same class of
    unkept promise gh#37 is about, so it is documented on the tools instead of
    quietly shipped.

    @brief Build one direction's causal neighbour list for a function.
    @version 3
    """
    edges = _direct_call_edges(conn, fn, want_callers, qualified)
    if include_dataflow:
        edges = edges + _dataflow_edges(conn, fn, as_writer=not want_callers)
    return sorted(edges, key=lambda e: (e.name, e.edge_class, e.key_name or ""))


## @brief Causal neighbours INTO `fn`: its callers plus the writers it reads from.
## @param qualified Optional identity from a prior `candidates.qualified`, selecting WHICH same-named function's callers to list.
## @return List of CallEdge — `edge_class='call'` for a direct caller, `'key'` for a function whose shared-key write `fn` reads.
## @version 4
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-010
def callers(db: DbSource, fn: str, qualified: str | None = None) -> list[CallEdge]:
    """Everything that causally precedes `fn`, in one list: direct call edges
    AND the shared-key writers whose values `fn` reads. Check `edge_class` on
    every row — a `'key'` neighbour does NOT call `fn` and may run on another
    thread.

    `qualified` (gh#37) selects among same-named functions; it narrows the `'call'`
    rows and not the `'key'` rows, for the reason `_call_edges` gives.

    @brief Return the causal predecessors of `fn` (calls + dataflow).
    @version 4
    """
    with connect(db) as conn:
        return _call_edges(conn, fn, want_callers=True, include_dataflow=True, qualified=qualified)


## @brief Causal neighbours OUT of `fn`: its callees plus the readers of its writes.
## @param qualified Optional identity from a prior `candidates.qualified`, selecting WHICH same-named function's callees to list.
## @return List of CallEdge — `edge_class='call'` for a direct callee, `'key'` for a function that reads a key `fn` writes.
## @version 4
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-010
def callees(db: DbSource, fn: str, qualified: str | None = None) -> list[CallEdge]:
    """Everything `fn` causally reaches in one hop, in one list: direct call
    edges AND the shared-key readers of the values it writes. Check `edge_class`
    on every row — a `'key'` neighbour is not called by `fn`; it observes a key
    `fn` wrote, possibly asynchronously and on another thread.

    `qualified` (gh#37) selects among same-named functions; it narrows the `'call'`
    rows and not the `'key'` rows, for the reason `_call_edges` gives.

    @brief Return the causal successors of `fn` (calls + dataflow).
    @version 4
    """
    with connect(db) as conn:
        return _call_edges(conn, fn, want_callers=False, include_dataflow=True, qualified=qualified)


## @brief Build KeyEdges for one function as writer (writes) or reader (reads).
## @return List of KeyEdge for `fn` in the selected role, including R1 dispatch/thread columns and the counterpart function name.
## @version 3
## @req REQ-DDB-QUERY-004
def key_edges(conn: sqlite3.Connection, fn: str, as_writer: bool) -> list[KeyEdge]:
    """Shared-key edges where `fn` is the writer (`as_writer=True`, → the
    reads-from list of `writes`) or the reader. `other` is the counterpart
    function. Includes the R1 dispatch/thread columns; `to_thread` is the
    reader thread's NAME (LEFT JOIN threads).

    @brief Build KeyEdge rows for one function in one role.
    @version 3
    """
    return [
        KeyEdge(
            key_name=k,
            edge_kind=kind,
            other=oname,
            other_rowid=resolve_rowid(conn, oname) or -1,
            source=src,
            confidence=conf,
            dispatch_mode=dm,
            edge_triggered=to_bool(et),
            crosses_thread=to_bool(ct),
            to_thread=tthr,
        )
        for oname, k, kind, src, conf, dm, et, ct, tthr in _key_edge_rows(
            conn, fn, as_writer=as_writer
        )
    ]


## @brief Every requirement-traceability edge as an absolute fn → req_id pair.
## @param db Path | str | sqlite3.Connection to the clew.db.
## @return List of ReqEdge (fn/req_id/confidence), ordered by fn/req_id; empty when the table is absent.
## @version 2
## @req REQ-DDB-QUERY-004
def all_req_edges(db: DbSource) -> list[ReqEdge]:
    """The bulk requirement-traceability view: every implementer edge as an
    absolute fn → req_id pair, deterministically ordered. The HTML db-explorer
    consumes this so the req_edges JOIN lives once in R2.

    @brief List every requirement-traceability edge as fn → req_id.
    @version 2
    """
    with connect(db) as conn:
        if not table_exists(conn, "req_edges"):
            return []
        rows = conn.execute(
            "SELECT DISTINCT m.name, r.req_id FROM req_edges r "
            "JOIN memberdef m ON m.rowid = r.memberdef_rowid "
            "ORDER BY m.name, r.req_id",
        ).fetchall()
    return [ReqEdge(fn=fn, req_id=rid) for fn, rid in rows]


## The six columns every threads row has had since the layer shipped, plus the two gh#346 added.
## Spelled ONCE because three call sites select them and a divergence between two spellings is
## how `_build_thread` would start unpacking a differently-shaped row — silently, since the
## unpack is positional.
_THREAD_COLUMNS = "t.id, t.name, t.kind, t.entry_memberdef_rowid, t.source, t.confidence"
_THREAD_SITE_COLUMNS = f"{_THREAD_COLUMNS}, t.spawn_path_rowid, t.spawn_line"
## And the NINTH column, which names who creates the thread rather than only where. Kept a
## separate list from `_THREAD_SITE_COLUMNS` for the reason that one exists at all: an index built
## before build 48 has the file and line and not this, and selecting a missing column raises
## rather than degrading.
_THREAD_SPAWNER_COLUMNS = f"{_THREAD_SITE_COLUMNS}, t.spawn_function"


## @brief The threads column list this index can actually supply.
## @param conn Open connection.
## @return The column list, with the spawn-site and spawner columns only when they exist.
## @version 2
## @dg_internal
def _thread_columns(conn: sqlite3.Connection) -> str:
    """An index predating build version 35 has no spawn-site columns, and one predating build 48
    has no `spawn_function`; selecting either raises `OperationalError` rather than degrading —
    the contract `has_columns` exists to keep. THREE tiers now, widest first, so a current index
    is never served the narrower list.

    @brief Choose the threads column list for this schema.
    @return SQL column list.
    @version 2
    """
    if has_columns(conn, "threads", "spawn_path_rowid", "spawn_line", "spawn_function"):
        return _THREAD_SPAWNER_COLUMNS
    if has_columns(conn, "threads", "spawn_path_rowid", "spawn_line"):
        return _THREAD_SITE_COLUMNS
    return _THREAD_COLUMNS


## @brief Assemble a Thread dataclass from a threads row (+ member count).
## @return Thread built from the row, with the entry function name resolved, its spawn site and spawning function attributed and its membership count populated.
## @version 3
## @dg_internal
def _build_thread(conn: sqlite3.Connection, row: tuple) -> Thread:
    """A SHORT ROW IS FOLDED, NOT REJECTED. The spawn-site columns arrive at build version 35,
    so a six-element row is a pre-35 index rather than a bug — and its threads really are
    unattributable, which is what an empty `spawn_file` says.

    @brief Resolve a threads row's entry name, spawn site, spawner and membership count into a Thread.
    @version 3
    """
    tid, name, kind, entry_rowid, source, conf = row[:6]
    spawn_path_rowid = row[6] if len(row) > 6 else None
    spawn_line = row[7] if len(row) > 7 else None
    ## The ninth element arrives at build 48; an eight-element row is a pre-48 index whose
    ## threads really do have no recorded spawner, which is what an empty `spawn_function` says.
    spawn_function = (row[8] if len(row) > 8 else None) or ""
    entry = name_of(conn, entry_rowid) if entry_rowid is not None else None
    member_count = (
        conn.execute(
            "SELECT COUNT(*) FROM thread_membership WHERE thread_id=?",
            (tid,),
        ).fetchone()[0]
        if table_exists(conn, "thread_membership")
        else 0
    )
    spawn_file, external_root = _spawn_attribution(conn, spawn_path_rowid)
    return Thread(
        id=tid,
        name=name,
        kind=kind,
        entry=entry,
        source=source,
        confidence=conf,
        member_count=member_count,
        spawn_file=spawn_file,
        spawn_line=spawn_line,
        spawn_function=spawn_function,
        external_root=external_root,
    )


## @brief The spawning file's repo-relative path and its external root.
## @param conn Open connection.
## @param path_rowid The spawn site's `path` rowid, or None.
## @return (repo-relative path or '', external root or '').
## @version 1
## @dg_internal
def _spawn_attribution(conn: sqlite3.Connection, path_rowid: int | None) -> tuple[str, str]:
    """Two values from one lookup, because they come from the same row and a caller that had to
    ask twice could get an external root for a file it did not resolve.

    A rowid that resolves to no `path` row returns ('', ''), which lands in the UNRESOLVED
    bucket rather than the first-party one — "we do not know whose this is" is not "it is ours".

    @brief Resolve a spawn site's file and owner.
    @return Path and external root, each '' when unknown.
    @version 1
    """
    if path_rowid is None:
        return "", ""
    tagged = has_columns(conn, "path", EXTERNAL_ROOT_COLUMN)
    column = f"p.{EXTERNAL_ROOT_COLUMN}" if tagged else "''"
    row = conn.execute(
        f"SELECT p.name, COALESCE({column}, '') FROM path p WHERE p.rowid=?",
        (path_rowid,),
    ).fetchone()
    if row is None:
        return "", ""
    return row[0] or "", row[1] or ""


## @brief Threads whose call-closure membership contains one rowid.
## @return List of Thread the memberdef rowid belongs to (by membership), in thread-id order.
## @version 3
## @req REQ-DDB-QUERY-004
def threads_for(conn: sqlite3.Connection, rowid: int) -> list[Thread]:
    """Selects through `_thread_columns` rather than its own literal list, so this and the roster
    cannot drift into asking for differently-shaped rows — `_build_thread` unpacks POSITIONALLY,
    so a divergence between two spellings would misread a column rather than raise.

    @brief Return the Threads a memberdef rowid belongs to (by membership).
    @version 3
    """
    if not (table_exists(conn, "threads") and table_exists(conn, "thread_membership")):
        return []
    rows = conn.execute(
        f"SELECT DISTINCT {_thread_columns(conn)} FROM thread_membership tm "
        "JOIN threads t ON t.id = tm.thread_id "
        "WHERE tm.memberdef_rowid=? ORDER BY t.id",
        (rowid,),
    ).fetchall()
    return [_build_thread(conn, r) for r in rows]


## @brief Union thread membership over several memberdef rowids.
## @param conn Open connection.
## @param rowids Memberdef rowids to union membership across.
## @return Threads containing ANY of the rowids, deduped by thread id.
## @version 1
## @req REQ-DDB-QUERY-004
def threads_for_rowids(conn: sqlite3.Connection, rowids: list[int]) -> list[Thread]:
    """`thread_membership` is keyed per rowid, so any question phrased about a
    NAME must union across the rowids that name denotes — otherwise a function
    whose membership was recorded against its declaration row (or against a
    sibling overload) reports no thread at all.

    @brief Union thread membership across rowids.
    @return Deduped Threads in thread-id order.
    @version 1
    """
    seen: set[int] = set()
    found: list[Thread] = []
    for rowid in rowids:
        for thread in threads_for(conn, rowid):
            if thread.id not in seen:
                seen.add(thread.id)
                found.append(thread)
    return sorted(found, key=lambda t: t.id)


## @brief Threads one function belongs to.
## @return List of Thread whose membership includes function `fn` (empty if `fn` is not indexed).
## @version 5
## @req REQ-DDB-QUERY-001
def thread_of(db: DbSource, fn: str) -> list[Thread]:
    """Union membership over EVERY rowid the name denotes.

    Previously this resolved one canonical rowid, which broke both ways on
    in practice: a QUALIFIED name straight out of `thread_roster`
    (`LinkOwner::rx_loop`) matched no unqualified `memberdef.name` and
    returned empty for 11 of 12 threads, while a bare ambiguous name (`run`)
    silently answered for one of two real threads. Both produced a confident
    empty-or-partial answer to "which thread does this run on".

    @brief Return every Thread whose membership includes function `fn`.
    @version 4
    """
    with connect(db) as conn:
        return threads_for_rowids(conn, rowids_for_name(conn, fn))


## What `row_meaning` says when the table is not in this index at all. Distinct from "this repo
## spawns no threads", and the distinction is the standing lesson: an absent table is a fact
## about the BUILD, never evidence about the code.
_THREADS_ABSENT_MEANING = (
    "the `threads` table is not present in this index, which predates the thread layer — "
    "this is a fact about the BUILD and is NOT evidence that the repo spawns no threads. "
    "Rebuild to answer the question."
)

## What it says when the layer is present but carries no spawn site, i.e. a pre-35 index.
_THREADS_UNATTRIBUTED_MEANING = (
    "this index predates build version 35, so no thread carries its SPAWN SITE and none can be "
    "attributed to a repository — the split below is not a measurement of this repo. Rebuild "
    "before quoting a first-party thread count."
)


## @brief Every thread in the DB, with member counts and the origin split.
## @param db Database path or open connection.
## @return The inventory; empty and consistent on a database predating the layer.
## @version 3
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-011
def thread_roster(db: DbSource) -> ThreadInventory:
    """AN ENVELOPE SINCE gh#346, not a bare list, because this roster could not previously
    express whose threads it was listing. A thread row was anchored to its ENTRY symbol, which is
    legitimately NULL whenever the entry name does not resolve to a rowid — a member-function
    pointer naming an unindexed class, or a bare name that is not unique — and a row with no
    entry has no file, so it could not be tagged, so a submodule's threads counted as FIRST PARTY.
    That inflates the one figure gh#335's invariance control rests on (admitting a submodule
    must raise the total and leave every first-party figure IDENTICAL). Measured on entropic:
    12 rows, 4 resolving into entropic, 6 into the vendored submodule, 2 to no file at all —
    and those 2 were exactly the mis-attributed ones.

    THE SPAWN SITE IS THE ANCHOR because it always exists and because it answers the question
    the tag asks: where is this thread CREATED. The entry answers what it RUNS, which is
    sometimes unknowable.

    A PRE-35 INDEX SAYS SO IN `row_meaning` rather than reporting a zeroed split as a
    measurement. An index that cannot attribute its threads and an index whose threads are all
    first party would otherwise produce identical numbers.

    @brief Return every thread with its entry, spawn site, member count and the origin split.
    @return ThreadInventory; `threads` empty when the layer is absent.
    @version 3
    """
    with connect(db) as conn:
        if not table_exists(conn, "threads"):
            return ThreadInventory(
                threads=(), rows=0, row_meaning=_THREADS_ABSENT_MEANING, origin=OriginSplit.of(())
            )
        attributable = has_columns(conn, "threads", "spawn_path_rowid", "spawn_line")
        rows = conn.execute(
            f"SELECT {_thread_columns(conn)} FROM threads t ORDER BY t.id",
        ).fetchall()
        threads = tuple(_build_thread(conn, r) for r in rows)
    origin = OriginSplit.of(_thread_origins(threads))
    return ThreadInventory(
        threads=threads,
        rows=len(threads),
        row_meaning=_roster_meaning(origin, attributable=attributable),
        origin=origin,
    )


## @brief One origin per thread, keyed on its SPAWN SITE.
## @param threads The roster.
## @return Origins: the external root, '' first party, None when the spawn site did not resolve.
## @version 1
## @dg_internal
def _thread_origins(threads: tuple[Thread, ...]) -> list[str | None]:
    """`spawn_file` EMPTY MEANS UNRESOLVED, not first party, and that distinction is the whole
    point of gh#346 — the rows it separates are the ones that used to inflate the first-party
    count by defaulting into it.

    @brief Classify each thread by its spawn site.
    @return One origin per thread.
    @version 1
    """
    return [(t.external_root or "") if t.spawn_file else None for t in threads]


## @brief The sentence stating both the count and whose threads it counts.
## @param origin The computed split.
## @param attributable False when this index carries no spawn sites at all.
## @return The `row_meaning` text.
## @version 4
## @dg_internal
def _roster_meaning(origin: OriginSplit, attributable: bool) -> str:
    """The sentence is what a model QUOTES, so a correct `origin` field beside a sentence naming
    only the total would preserve the wrong attribution — the lesson `lock_roster.row_meaning`
    already carries.

    IT SAID "Quote origin.first_party as the repository's thread count", AND THAT IS AN
    OVERSTATEMENT THAT WAS QUOTED. On Mbed-TLS/mbedtls it reads 1 against a true 2:
    `pthread_create` in the sample TLS server matches a default pattern, and
    `_beginthread(TimerProc, 0, NULL)` in the benchmark program matches nothing, because no
    Windows spawn primitive is in `DEFAULT_SPAWN_PATTERNS` at all. A graded answer wrote
    "consistent with the index's count of exactly one first-party thread" — confident
    incompleteness authored by this payload, not by the agent, which is instructed to trust the
    index absolutely.

    THE COUNT IS OF SPAWN SITES THE PATTERN SET MATCHED, which is a fact about the BUILD. Saying
    so costs one clause and is simply true. And because the pattern set is DECLARABLE, the
    sentence can route to the fix — `thread_patterns` — rather than hedge: a reader told "this may
    be incomplete" has nowhere to go, a reader told the section name has a one-line change.

    @brief Build the roster's row_meaning.
    @return The sentence.
    @version 4
    """
    if not attributable:
        return f"{origin.total} thread(s), and {_THREADS_UNATTRIBUTED_MEANING}"
    roots = f" ({', '.join(origin.external_roots)})" if origin.external_roots else ""
    return (
        f"{origin.total} thread(s), of which {origin.first_party} are spawned by THIS "
        f"repository, {origin.external} by a vendored submodule{roots}, and "
        f"{origin.unresolved} from a spawn site this index could not resolve to a file. "
        f"Quote origin.first_party as the repository's spawn sites THIS BUILD'S PATTERNS "
        f"MATCHED — not as its thread count. THAT IS AN EXACT FIGURE, not an estimate, and "
        f"stating it with its scope ('N spawn sites, across the primitives this build searches') "
        f"is a COMPLETE answer rather than a hedged one. A spawn primitive outside the pattern "
        f"set is "
        f"invisible here rather than reported as absent, so a platform this build does not know "
        f"(a Windows `_beginthread`, an RTOS wrapper, a project's own spawn helper) contributes "
        f"nothing to this number: widen it by declaring a `thread_patterns` section. "
        f"status.diagnostics may name a candidate, but only for a primitive this repository "
        f"DECLARES — an external platform API it merely calls cannot be hinted at, so the "
        f"absence of a hint is not evidence of coverage. Attribution is by SPAWN "
        f"SITE, not by entry symbol: `entry` is null whenever the entry name did not resolve to "
        f"an indexed function, and those rows are still attributable because the spawn call "
        f"itself always has a file."
    )


## Default cap on returned hits. The previous implementation had NO limit, so a
## common single token returned every match in alphabetical order — the useful
## hit could be anywhere in hundreds of rows.
DEFAULT_SEARCH_LIMIT = 25


## @brief Rank one candidate against the query tokens (higher is better).
## @param name Function name.
## @param brief Markup-stripped brief text.
## @param query Whole lower-cased query string.
## @param tokens Lower-cased query tokens.
## @return Sort score; larger means a better match.
## @version 2
## @dg_internal
def _search_rank(name: str, brief: str, query: str, tokens: list[str]) -> int:
    """Order by how much of the match landed in the NAME, which is what a
    caller actually asked about — a token found only in prose is weaker
    evidence than the same token in the identifier.

    @brief Score a search candidate.
    @return Relevance score.
    @version 2
    """
    lname = name.lower()
    score = 0
    if lname == query:
        score += SEARCH_WEIGHT_EXACT_NAME
    if query and query in lname:
        score += SEARCH_WEIGHT_NAME_SUBSTRING
    score += SEARCH_WEIGHT_TOKEN_IN_NAME * sum(1 for t in tokens if t in lname)
    score += SEARCH_WEIGHT_TOKEN_IN_BRIEF * sum(1 for t in tokens if t in brief.lower())
    return score


## How much of a file's documentation a search hit carries. A module docstring runs
## to thousands of characters and 25 of them would swamp the reply; the full text is
## reachable through `search_prose` (ranked, with its own snippet) and `source`. The
## cut is at a word boundary and marked with an ellipsis, so a truncated brief never
## reads as a complete sentence the file did not write.
FILE_BRIEF_CHARS = 240

## Ranking tier for a symbol hit versus a file hit. Score dominates the sort; this
## only breaks a TIE, and it breaks it toward the symbol — a caller asking `search`
## wants code, and gh#10's file hits are there to make a concept findable, not to
## displace the function that implements it.
_TIER_SYMBOL = 0
_TIER_FILE = 1

## Tie-break tier for a compound hit (gh#315). Classes sit with functions rather than
## with files because both are SYMBOLS — a class name in an identifier is exactly as
## strong evidence as a function name in one, and putting compounds in their own lower
## tier would have re-created the bug in weaker form: a class outscored by a file whose
## prose happens to mention it would never be seen. The tier only breaks score ties.
_TIER_CLASS = 0

## Tie-break tier for a VARIABLE hit (gh#372). Deliberately the LOWEST tier, below
## files: a caller who types a name that is both a function and a global wants the
## function, and this is the one corpus whose rows can be added to an existing index
## without changing any function's rank. The tier only breaks a score TIE — a variable
## whose name the query spells exactly still outranks a function that merely contains
## the token, which is the whole point of the change (`mbedtls_threading_key_slot_mutex`
## must win over anything that only mentions "mutex").
_TIER_VARIABLE = 2

## Tie-break tier for a MACRO hit (gh#373). Level with variables and for the same
## reason: a name that is both a function and a macro should show the function first,
## and macros are the corpus most likely to collide with one — a `#define FOO(x)`
## wrapper and the `FOO_impl` it forwards to habitually share tokens. It breaks a TIE
## only, so an exact-name macro still wins, which is the case that motivated the corpus.
_TIER_MACRO = 2

## Tie-break tier for a TYPE hit — a `typedef` or an `enumeration`. Lowest tier, with
## variables and macros: a name that is both a function and a type should show the
## function first, and the `_t`-suffixed typedef of a context struct habitually shares
## every token with the functions that operate on it.
_TIER_TYPE = 2

## Tie-break tier for a CONFIG SYMBOL hit (gh#394). Lowest tier, with variables, macros and
## types: a gating symbol habitually shares every token with the function it gates
## (`MBEDTLS_THREADING_C` and `mbedtls_threading_set_alt`), and the function is what a caller
## can read a body for. It breaks a TIE only, so a query spelling the symbol exactly still
## puts it first — which is the case the corpus exists for.
_TIER_CONFIG = 2

## `kind` on a config-symbol hit. NOT 'config', which is `resolve_subject`'s kind for the
## same thing: this string reaches a model in a search reply and has to say what the row IS
## without being mistaken for a file or a function it could ask for a body.
CONFIG_SYMBOL_KIND = "config symbol"

## THE MEMBERDEF CORPORA `search` READS, kind → tie-break tier. SINGLE SOURCE OF TRUTH:
## `search` iterates this table and `mcp_server.emptiness` words its reply from it, so a
## corpus cannot be added to the searcher and left out of what the tool SAYS it searched.
## That divergence is not hypothetical — it had already happened twice by the time this
## table was written, with variables (gh#372) and macros (gh#373) both searched while the
## tool description and the empty-result note still named "function names, briefs and file
## docs" only.
##
## `typedef` and `enumeration` are gh#374 and they are the FOURTH instance of the one
## defect: a kind present in `memberdef` that `search` never read, so its names came back
## a confident zero rather than being outranked. Measured on the mbedtls index: of 7,717
## distinct `memberdef.name` values, 282 (239 typedef, 43 enumeration) existed ONLY under
## an unsearched kind — `mbedtls_ssl_mode_t`, `mbedtls_x509_buf`,
## `psa_key_derivation_step_t`, `mbedtls_entropy_f_source_ptr` and 278 more, every one of
## them a name a caller would plausibly type first.
##
## A kind carries an optional SECOND prose column (`extra_prose`); only macros have one,
## their expansion. See `_memberdef_candidates`.
SEARCHED_MEMBERDEF_KINDS: tuple[tuple[str, int], ...] = (
    ("function", _TIER_SYMBOL),
    ("variable", _TIER_VARIABLE),
    (MACRO_KIND, _TIER_MACRO),
    ("typedef", _TIER_TYPE),
    ("enumeration", _TIER_TYPE),
)

## Ranked candidate: (negated score, tier, name, hit).
_Candidate = tuple[int, int, str, SymbolHit]


## @brief Shorten a file's documentation to a brief, at a word boundary.
## @param doc Full file-level documentation text.
## @return Text of at most FILE_BRIEF_CHARS characters, ellipsised when cut.
## @version 1
## @dg_internal
def _doc_brief(doc: str) -> str:
    """@brief Trim file-level documentation to brief length.
    @return Possibly-ellipsised brief text.
    @version 1
    """
    if len(doc) <= FILE_BRIEF_CHARS:
        return doc
    head = doc[:FILE_BRIEF_CHARS]
    cut = head.rsplit(" ", 1)[0] if " " in head else head
    return f"{cut} …"


## @brief Collapse whitespace and line continuations, then trim to brief length.
## @param text Raw non-XML prose (a macro expansion), or None.
## @return One-line text of at most FILE_BRIEF_CHARS characters, ellipsised when cut.
## @version 1
## @dg_internal
def _one_line(text: str | None) -> str:
    """gh#373. A macro expansion is C source and routinely spans several lines glued
    by trailing backslashes, so pasting it into a `brief` slot verbatim would put
    newlines and `\\` in a field every consumer renders as one line. The backslashes
    go first, then the whitespace runs collapse — the other order leaves a stranded
    `\\` mid-line for a continuation whose newline has already been eaten.

    Reuses `_doc_brief`'s cap rather than declaring a second one: "how long is a brief
    on this surface" should have one answer, and a macro's expansion is competing for
    the same slot as a file's documentation.

    @brief Flatten a multi-line expansion to a single trimmed brief.
    @return One-line, length-capped text.
    @version 1
    """
    flat = re.sub(r"\s+", " ", (text or "").replace("\\\n", " ")).strip()
    return _doc_brief(flat)


## @brief Ranked memberdef candidates of one kind whose name or brief carries every token.
## @param conn Open connection.
## @param query Whole lower-cased query string.
## @param tokens Lower-cased query tokens.
## @param kind The `memberdef.kind` to search ('function', 'variable' or 'macro definition').
## @param tier Tie-break tier for the hits produced.
## @param extra_prose SQL expression for a NON-XML prose column to match and to fall back to when the brief is empty; `''` for none.
## @return Ranked candidate tuples, one per distinct name, each disclosing a provenance-crossing drop.
## @version 3
## @dg_internal
def _memberdef_candidates(
    conn: sqlite3.Connection,
    query: str,
    tokens: list[str],
    kind: str,
    tier: int,
    extra_prose: str = "''",
) -> list[_Candidate]:
    """Parametrised by KIND when gh#372 added the variable corpus, so both corpora are
    matched by one clause builder, ranked by one weight table and collapsed by one
    per-name rule. Copying this body for variables would have been the DRY violation
    that lets the two corpora drift — and drift here means one of them silently stops
    honouring `documented_first` or the conjunction.

    `extra_prose` is gh#373's addition and it is a SECOND prose column, not a
    replacement: a macro's own documentation is its EXPANSION, which lives in
    `memberdef.initializer` and which almost no macro duplicates in a brief (441 of
    mbedtls's 2,504 macro rows have no expansion recorded at all, and most of the rest
    have no brief). Matching it means `search('private_##member')` finds the macro that
    produces it, which is the reverse lookup a reader of generated field names needs.

    It is NOT run through `strip_xml`, deliberately and unlike a brief. A brief is
    doxygen markup; an expansion is C source, and `strip_xml`'s `<[^>]+>` would eat the
    middle of `((x) < 0 ? 0 : (x) > 1 ? 1 : (x))`. Two prose columns, two treatments,
    because they are two different languages.

    @brief Match and rank indexed names, briefs and non-XML prose for one memberdef kind.
    @return Ranked candidates.
    @version 2
    """
    if not table_exists(conn, "memberdef"):
        return []
    clause = " AND ".join(
        [
            "(LOWER(m.name) LIKE ? OR LOWER(COALESCE(m.briefdescription,'')) LIKE ? "
            f"OR LOWER({extra_prose}) LIKE ?)"
        ]
        * len(tokens)
    )
    params: list[str] = []
    for token in tokens:
        params += [f"%{token}%"] * 3
    # `documented_first` makes doxygen's own row win the per-name collapse
    # below, so a parser-recovered row can never displace a documented one and
    # take its brief off this surface. See `_common.documented_first`.
    rows = conn.execute(
        f"SELECT m.name, m.kind, COALESCE(p.name,''), m.briefdescription, m.rowid, {extra_prose} "
        "FROM memberdef m LEFT JOIN path p ON p.rowid = m.file_id "
        f"WHERE m.kind=? AND {clause} "
        f"ORDER BY m.name, {documented_first(conn, 'm')}m.rowid",
        [kind, *params],
    ).fetchall()
    ## TWO PASSES, because the disclosure needs a fact the first pass has not finished
    ## collecting: which OTHER files declare each surviving name. gh#392 — the collapse
    ## keeps doxygen's row over a recovered one, which is right in general and was measured
    ## wrong once: after gh#395 recovered mbedtls's guarded `mbedtls_threading_mutex_t`, the
    ## kept row was the TEST FIXTURE and the dropped one was the shipping type.
    ##
    ## ONLY WHEN PROVENANCE DIFFERS, and my first cut got this wrong in the way this repo
    ## warns about most. Disclosing every dropped file made `mbedtls_ctr_drbg_random` report
    ## `also_in: library/ctr_drbg.c` — the ORDINARY decl/def duality, present on nearly every
    ## C function. A guard that fires on the ordinary case is worse than no guard: it buries
    ## the one case that matters in noise on every row.
    ##
    ## The ordering rule here is `documented_first`, so the interesting event is exactly when
    ## THAT rule discarded a row of different provenance — doxygen's kept, the parser's
    ## dropped. Decl/def pairs are both doxygen's and stay silent.
    elsewhere: dict[str, list[str]] = {}
    kept: dict[str, tuple] = {}
    for row in rows:
        name, file, rowid = row[0], row[2], row[4]
        if name in kept:
            differs = symbol_provenance(conn, rowid) != symbol_provenance(conn, kept[name][4])
            if differs and file and file != kept[name][2] and file not in elsewhere[name]:
                elsewhere[name].append(file)
            continue
        kept[name] = row
        elsewhere[name] = []

    candidates: list[_Candidate] = []
    for name, (_n, row_kind, file, brief, rowid, extra) in kept.items():
        clean = strip_xml(brief) or _one_line(extra)
        candidates.append(
            (
                -_search_rank(name, clean, query, tokens),
                tier,
                name,
                SymbolHit(
                    name=name,
                    kind=row_kind,
                    file=file,
                    brief=clean,
                    provenance=symbol_provenance(conn, rowid),
                    also_in=tuple(elsewhere[name]),
                ),
            )
        )
    return candidates


## @brief SQL for a macro's expansion, degrading to '' on a schema without the column.
## @param conn Open connection.
## @return `COALESCE(m.initializer,'')`, or `''` when `memberdef` has no `initializer`.
## @version 1
## @dg_internal
def _expansion_sql(conn: sqlite3.Connection) -> str:
    """Degrades to the empty literal rather than to no macro corpus at all: a database
    without the column can still match a macro BY NAME, and losing the reverse
    (expansion) lookup is a smaller loss than losing the whole corpus. Interpolated
    into the statement text and therefore chosen from two FIXED strings, never built
    from anything a caller supplies.

    @brief Pick the expansion expression this schema supports.
    @return A SQL scalar expression.
    @version 1
    """
    return "COALESCE(m.initializer,'')" if has_columns(conn, "memberdef", "initializer") else "''"


## @brief Ranked candidates from EVERY searched memberdef corpus, in one list.
## @param conn Open connection.
## @param query Whole lower-cased query string.
## @param tokens Lower-cased query tokens.
## @return Ranked candidate tuples across all kinds in SEARCHED_MEMBERDEF_KINDS.
## @version 1
## @dg_internal
def _memberdef_corpora(conn: sqlite3.Connection, query: str, tokens: list[str]) -> list[_Candidate]:
    """ONE LOOP OVER ONE TABLE, replacing the three one-line wrappers this file grew as
    corpora were added a gh at a time (`_symbol_candidates`, `_variable_candidates`,
    `_macro_candidates`). Their histories are kept where the decision lives — on
    `SEARCHED_MEMBERDEF_KINDS` for what is read and why, and on `_memberdef_candidates`
    for how a row is matched and ranked.

    The wrappers were the mechanism by which the SAME defect shipped four times: adding
    a corpus meant writing a new function and remembering to call it, and there was no
    place a reader could look to see the whole covered set. Now there is one, and
    `mcp_server.emptiness` reads it to word the reply, so what `search` covers and what
    it CLAIMS to cover cannot drift apart.

    Only macros take a second prose column — a macro's real documentation is its
    expansion. Nothing else has one, so the extra argument is supplied for that kind
    alone rather than made a column of the table for one true row.

    @brief Match and rank every searched memberdef kind.
    @return Ranked candidates from all memberdef corpora.
    @version 1
    """
    candidates: list[_Candidate] = []
    for kind, tier in SEARCHED_MEMBERDEF_KINDS:
        extra = _expansion_sql(conn) if kind == MACRO_KIND else "''"
        candidates += _memberdef_candidates(conn, query, tokens, kind, tier, extra)
    return candidates


## @brief Ranked file candidates whose path or file-level documentation carries every token.
## @param conn Open connection.
## @param query Whole lower-cased query string.
## @param tokens Lower-cased query tokens.
## @return Ranked candidate tuples with kind 'file'.
## @version 1
## @dg_internal
def _file_candidates(conn: sqlite3.Connection, query: str, tokens: list[str]) -> list[_Candidate]:
    """gh#10. The file's PATH is scored where a symbol's name is scored and its
    documentation where a brief is, so one weight table serves both corpora and a
    conceptual token in prose stays weaker evidence than the same token in an
    identifier — the property `_search_rank` exists to enforce.

    `provenance` is `'file_doc'` so a consumer can tell at a glance that this row
    came from prose the author wrote about the FILE, not from a symbol record.

    @brief Match and rank file-level documentation.
    @return Ranked candidates.
    @version 1
    """
    return [
        (
            -_search_rank(path, doc, query, tokens),
            _TIER_FILE,
            path,
            SymbolHit(
                name=path,
                kind="file",
                file=path,
                brief=_doc_brief(doc),
                provenance="file_doc",
            ),
        )
        for path, doc in file_doc_rows(conn, tokens)
    ]


## @brief Ranked compound candidates whose name or brief carries every token.
## @param conn Open connection.
## @param query Whole lower-cased query string.
## @param tokens Lower-cased query tokens.
## @return Ranked candidate tuples whose kind is 'class', 'struct', 'union' or 'interface'.
## @version 1
## @dg_internal
def _class_candidates(conn: sqlite3.Connection, query: str, tokens: list[str]) -> list[_Candidate]:
    """gh#315. A compound's NAME is scored where a function's name is scored and its
    BRIEF where a function's brief is, so the single weight table in `_search_rank`
    governs all three corpora and no corpus can win by being ranked on its own scale.

    `provenance` stays None: every compound row is doxygen's, and `symbol_provenance`
    reports only the surprising case. A compound has no tree-sitter recovery path.

    @brief Match and rank indexed classes, structs, unions and interfaces.
    @return Ranked candidates.
    @version 1
    """
    return [
        (
            -_search_rank(name, brief, query, tokens),
            _TIER_CLASS,
            name,
            SymbolHit(name=name, kind=kind, file=file, brief=brief),
        )
        for name, kind, file, brief in class_rows(conn, tokens)
    ]


## @brief Ranked configuration-symbol candidates whose name carries every token.
## @param conn Open connection.
## @param query Whole lower-cased query string.
## @param tokens Lower-cased query tokens.
## @return Ranked candidate tuples whose kind is 'config symbol'.
## @version 1
## @dg_internal
def _config_candidates(conn: sqlite3.Connection, query: str, tokens: list[str]) -> list[_Candidate]:
    """gh#394. Scored through the SAME `_search_rank` as every other corpus so no corpus
    can win by being ranked on its own scale — with an empty brief, because a gate row is a
    location and not a documented entity (see `corpus.gate_symbol_rows`).

    THE BRIEF IS SYNTHESISED FROM THE MEASUREMENT, not from prose the row does not have:
    "gates 151 site(s) in 31 file(s)" is the useful fact about a config symbol and it comes
    from the count, so it cannot drift from the rows. It is built AFTER ranking for exactly
    that reason — scoring against it would let a query for "site" match every config symbol
    in the repository.

    @brief Match and rank the configuration symbols a repo gates on.
    @return Ranked candidates.
    @version 1
    """
    return [
        (
            -_search_rank(symbol, "", query, tokens),
            _TIER_CONFIG,
            symbol,
            SymbolHit(
                name=symbol,
                kind=CONFIG_SYMBOL_KIND,
                file=file,
                brief=f"gates {sites} site(s); origin {origin or 'unknown'}",
            ),
        )
        for symbol, sites, file, origin in gate_symbol_rows(conn, tokens)
    ]


## @brief Multi-token, ranked search over symbol names, briefs and file-level documentation.
## @param db Database path or open connection.
## @param text Query; whitespace-separated tokens must ALL match.
## @param limit Maximum hits to return (default DEFAULT_SEARCH_LIMIT).
## @return Ranked SymbolHit list, best match first; check `kind` — 'file' is a whole file, and 'variable', 'macro definition', 'typedef', 'enumeration' and 'config symbol' have no body, callers or callees.
## @version 12
## @req REQ-DDB-QUERY-001
## @req REQ-DDB-QUERY-012
def search(db: DbSource, text: str, limit: int = DEFAULT_SEARCH_LIMIT) -> list[SymbolHit]:
    """Every whitespace-separated token must appear in ONE searchable unit; results
    are then RANKED, name matches ahead of prose matches.

    This replaces a single literal `LIKE '%<whole query>%'`, which made any
    multi-word query return nothing at all: `'%lock acquisition%'` is a literal
    substring that no identifier contains. Verified on clew's own index —
    `search("lock")` gave 9 hits while `search("lock acquisition")` gave ZERO,
    and the empty envelope then told the caller "This is a definitive empty
    result ... Do not retry", which is the confidently-wrong failure mode.
    Search is the discovery entry point: if it answers nothing for a natural
    phrase, a consumer never reaches dossier or chain_trace at all.

    gh#10 adds the SECOND searchable unit: a file's module docstring or file-level
    doxygen comment, returning the FILE as the hit (`kind='file'`). Without it a
    query phrased as a concept missed code that is entirely about that concept —
    `search("deadlock")` was zero on this repository while `query/locks.py` is a
    module about lock nesting, because implementations are named for mechanics
    (`lock_nestings`, `_harvest_registration`) and that is correct naming.

    This is NOT a fallback to `search_prose`, which was considered and rejected:
    a tool that silently changes corpus on a miss has two meanings and the caller
    cannot tell which one answered. The file-level corpus is searched ALWAYS, with
    the same conjunction and the same weights, and every row says which it is.
    Markdown documentation remains `search_prose`'s alone.

    gh#372 adds the FOURTH: a global or file-scope VARIABLE. See
    `_variable_candidates` for the measurement — mbedtls's five global mutex objects
    and its function-pointer lock primitive were all unfindable, and the only route to
    the repo's mutex list was reading a function body. Variables sit in the LOWEST
    tie-break tier, so no function's rank changes; a variable only outranks a function
    by scoring strictly higher, which is what an exact name match should do.

    gh#315 adds the THIRD searchable unit: a class/struct/union/interface, from
    `compounddef`. Until then `search` looked only at `memberdef WHERE kind='function'`
    and the file docs, so a class name was not outranked or filtered — it was ABSENT
    FROM THE SEARCHED SET, and the reply was a confident empty result indistinguishable
    from a measured negative. Reproduced on this repository: `search("WritePlan")`
    returned the `mcp_config.py` file doc while the class sits in that same file. That
    failure mode costs a graded agent marks silently, because there is nothing in the
    answer to suggest a second look. See `corpus.class_rows` for why STL compounds are
    excluded from this corpus while `lookup_class` still reaches them.

    gh#373 adds the FIFTH: a preprocessor `#define`, matched on its name, its brief
    AND its expansion. See `_macro_candidates` for the measurement — the graded
    mbedtls question is about a macro, and the gating macro it turns on came back a
    confident zero with three rows for it in the index.

    gh#394 adds the EIGHTH: a CONFIGURATION SYMBOL the repo gates code on. Same defect
    shape as the four before it, measured after gh#390 gave the mbedtls index 10,861
    gating sites — `search("MBEDTLS_THREADING_PTHREAD")` returned NOTHING while `dossier`
    answered for the same name, so discovery failed for the exact symbols two graded
    questions are about and the agent searched for them nine times in one run. It is NOT
    part of `SEARCHED_MEMBERDEF_KINDS`: gates live in their own table, not in `memberdef`,
    and folding them into that tuple would claim doxygen emitted them.

    gh#374 adds the SIXTH and SEVENTH: a `typedef` and an `enumeration`. The corpora
    are no longer added one wrapper at a time — `SEARCHED_MEMBERDEF_KINDS` is the
    covered set, `_memberdef_corpora` iterates it and `mcp_server.emptiness` words the
    empty reply from it, because the recurring defect was never any single missing kind
    but the absence of one place that says which kinds are read. Measured on mbedtls:
    282 of 7,717 distinct `memberdef` names lived only under an unsearched kind.

    WHAT IS STILL NOT READ is reported rather than assumed away: `unsearched_corpora`
    counts the rows a query WOULD have matched in a corpus this function does not
    cover, and an empty result that has such rows behind it is graded down instead of
    being called definitive.

    @brief Search functions, variables, classes, macros, types, config symbols and file docs, ranked.
    @version 12
    """
    tokens = [t.lower() for t in text.split() if t]
    if not tokens:
        return []
    query = text.strip().lower()
    with connect(db) as conn:
        ranked = (
            _memberdef_corpora(conn, query, tokens)
            + _class_candidates(conn, query, tokens)
            + _config_candidates(conn, query, tokens)
            + _file_candidates(conn, query, tokens)
        )
    # Negated score, then symbols ahead of files on a tie, then name: best first,
    # ties alphabetical so results are stable across builds rather than dependent
    # on rowid order.
    ranked.sort(key=lambda r: (r[0], r[1], r[2]))
    return [hit for _score, _tier, _name, hit in ranked[: max(1, limit)]]


## Cap on tokens diagnosed after a zero-result search. The diagnosis costs one COUNT
## per token, so the worst case has to be bounded rather than left to the length of
## whatever sentence a caller pasted in. Eight is well past the point where naming the
## guilty token still helps: a query that over-specifies by six tokens needs rephrasing,
## not a per-token audit.
MAX_DIAGNOSED_TOKENS = 8


## @brief How many symbols and files each token matches ON ITS OWN.
## @param db Database path or open connection.
## @param tokens Lower-cased query tokens.
## @return Mapping of token to its independent hit count, in the given order.
## @version 1
## @req REQ-DDB-QUERY-007
def token_hit_counts(db: DbSource, tokens: list[str]) -> dict[str, int]:
    """gh#31. `search("roots target resolution")` returned a definitive-sounding
    zero while `_target_from_roots` was indexed, because the conjunction is over
    name+brief and that brief has `roots` and neither `target` nor `resolution`.
    Ranking behaved as specified; the NOTE was the defect, telling the caller not
    to retry when dropping a token was the one correct next move.

    Per-token counts name the token that emptied the query, which turns a wasted
    call into an answer. COST: one COUNT per token, so this is computed ONLY when
    the result is already zero and only up to `MAX_DIAGNOSED_TOKENS`. Paid exactly
    where the alternative is a call that returned nothing at all, and never on the
    common path.

    @brief Count each token's independent matches.
    @return {token: count}.
    @version 1
    """
    counts: dict[str, int] = {}
    with connect(db) as conn:
        for token in tokens:
            counts[token] = _one_token_count(conn, token)
    return counts


## @brief Independent match count for one token across both search corpora.
## @param conn Open connection.
## @param token One lower-cased token.
## @return Number of distinct symbol names, variables, macros, types, classes and files the token alone matches.
## @version 5
## @dg_internal
def _one_token_count(conn: sqlite3.Connection, token: str) -> int:
    """Counts over EVERY corpus `search` reads, because a token matching only a
    file's documentation is still a token that did not empty the query, and saying
    otherwise would send the caller to drop the one token that was working.

    That argument is why gh#315's class corpus had to be added here in the same
    change and not later: a token matching a class and nothing else would have been
    counted 0 and named as the guilty token, which is gh#31's exact defect
    reintroduced through the new corpus. A corpus that `search` reads and the
    diagnosis does not is a diagnosis that lies about a widened tool.

    gh#372's variable corpus is here for the SAME reason and was added in the SAME
    change, deliberately: `mutex` matches five mbedtls globals and — on a repo whose
    functions do not spell it — nothing else, so leaving variables out would have
    named `mutex` as the token that emptied a query it was the only one answering.

    gh#373's macro corpus, third time, same change. It also has to match the
    EXPANSION, because that is what the macro corpus matches: counting it on
    name-and-brief alone would under-count exactly the reverse lookups
    (`private_##member`) the expansion was added for, and name the working token as
    the guilty one.

    gh#374 stops the fourth instance by CONSTRUCTION: the kind list is read from
    `SEARCHED_MEMBERDEF_KINDS` instead of being spelled out again here. This statement
    had the three kinds hardcoded, so the typedef and enumeration corpora would have
    been searched and not counted — a token matching only a type name would have been
    reported as matching nothing and named as the one to drop.

    @brief Count one token's matches in every searched memberdef corpus, classes and file docs.
    @return Combined count.
    @version 5
    """
    like = f"%{token}%"
    symbols = 0
    if table_exists(conn, "memberdef"):
        kinds = [kind for kind, _tier in SEARCHED_MEMBERDEF_KINDS]
        placeholders = ",".join("?" * len(kinds))
        symbols = conn.execute(
            "SELECT COUNT(DISTINCT m.name) FROM memberdef m "
            f"WHERE m.kind IN ({placeholders}) "
            "AND (LOWER(m.name) LIKE ? OR LOWER(COALESCE(m.briefdescription,'')) LIKE ? "
            f"OR (m.kind=? AND LOWER({_expansion_sql(conn)}) LIKE ?))",
            (*kinds, like, like, MACRO_KIND, like),
        ).fetchone()[0]
    return symbols + len(class_rows(conn, [token])) + len(file_doc_rows(conn, [token]))


## The only compound kind a zero-result search must NOT count as unread: a `dir` is a
## directory, not a symbol, and no phrasing of `search` promises one.
##
## `file` IS COUNTED, which was a decision and nearly went the other way. The tempting
## reasoning is "files are covered — `corpus.file_doc_rows` is a search corpus". But
## that corpus is `file_docs`, one row per DOCUMENTED file, so an indexed file carrying
## no module docstring and no `@file` comment is not reachable through `search` by any
## route. Excluding `file` here would have asserted coverage the searcher does not have
## — the same assumption, one table over, that this whole change exists to remove. When
## the file IS documented the question never arises, because then `search` returns it
## and there is no empty result to grade.
_COVERED_COMPOUND_KINDS = ("dir",)


## @brief Rows a zero-result query WOULD have matched in a corpus `search` does not read.
## @param db Path, str or open connection to a built index.
## @param tokens Lower-cased query tokens (the same conjunction `search` applies).
## @return Mapping of unread corpus name to the number of distinct names in it matching every token; empty when the index holds no such corpus or none of it matches.
## @version 1
## @req REQ-DDB-QUERY-007
def unsearched_corpora(db: DbSource, tokens: list[str]) -> dict[str, int]:
    """THE POINT OF THIS FUNCTION IS TO MAKE A NEGATIVE HONEST, not to find rows. An
    empty `search` used to assert "This IS a definitive empty result ... Do not retry
    this query or fall back to guessing" whenever a single token matched nothing, and
    that sentence is a claim about the REPOSITORY made from evidence about three or five
    corpora. Four times now the two have differed and the sentence was simply false:
    classes (gh#315), variables (gh#372), macros (gh#373), typedefs and enumerations
    (gh#374). Each time the reply was maximally confident and maximally wrong, and the
    graded consequence is on record — one cell answered a macro question with fifteen
    consecutive searches and a fall back to `Grep`.

    Adding the missing corpus fixes the instance. This fixes the CLASS, because it does
    not enumerate what is missing: it derives the unread set by SUBTRACTION, from the
    kinds actually present in this database minus the kinds `search` reads. A corpus
    nobody has thought of yet — a kind a future doxygen emits, a layer a later pipeline
    stage adds — downgrades the verdict the day it first appears, with no edit here.
    That is the difference between a fix and a guard.

    It is computed ONLY on a query that already returned nothing, alongside the
    per-token diagnosis and under the same argument: two COUNTs on a call whose
    alternative is a reply with no content at all.

    @brief Count matches in corpora `search` does not read, to grade an empty result.
    @return {corpus name: distinct matching names}.
    @version 1
    """
    if not tokens:
        return {}
    found: dict[str, int] = {}
    with connect(db) as conn:
        searched = {kind for kind, _tier in SEARCHED_MEMBERDEF_KINDS}
        if table_exists(conn, "memberdef"):
            found |= _unread_kind_counts(conn, "memberdef", tokens, searched)
        if table_exists(conn, "compounddef"):
            covered = set(CLASS_KINDS) | set(_COVERED_COMPOUND_KINDS)
            found |= _unread_kind_counts(conn, "compounddef", tokens, covered)
    return {kind: n for kind, n in sorted(found.items()) if n}


## @brief Per-kind match counts for the kinds of one table that `search` does not read.
## @param conn Open connection.
## @param table `memberdef` or `compounddef`.
## @param tokens Lower-cased query tokens, all of which must match.
## @param searched The kinds of that table `search` DOES read.
## @return Mapping of unread kind to distinct matching names.
## @version 1
## @dg_internal
def _unread_kind_counts(
    conn: sqlite3.Connection, table: str, tokens: list[str], searched: set[str]
) -> dict[str, int]:
    """The kind list comes from the DATABASE (`SELECT DISTINCT kind`), never from a
    literal here, which is what makes the caller's subtraction cover a kind nobody
    wrote down. `table` is one of two fixed strings chosen by the caller and is
    interpolated; every value a caller supplies is bound.

    Matching mirrors `_memberdef_candidates` — the same conjunction over name and
    brief — because a count that used looser matching would grade a result down on
    rows `search` would not have returned even with the corpus added.

    @brief Count matching distinct names per unread kind of one table.
    @return {kind: distinct matching names}.
    @version 1
    """
    clause = " AND ".join(
        ["(LOWER(name) LIKE ? OR LOWER(COALESCE(briefdescription,'')) LIKE ?)"] * len(tokens)
    )
    params: list[str] = []
    for token in tokens:
        params += [f"%{token}%"] * 2
    rows = conn.execute(
        f"SELECT kind, COUNT(DISTINCT name) FROM {table} WHERE {clause} GROUP BY kind",
        params,
    ).fetchall()
    return {kind: n for kind, n in rows if kind not in searched}


## @brief Implementers of a requirement (excluding covering test functions).
## @return List of Implementer @req-linked to the requirement (with rowid, confidence, liveness), minus any names in `tests`.
## @version 2
## @dg_internal
def _req_implementers(conn: sqlite3.Connection, req_id: str, tests: set[str]) -> list[Implementer]:
    """@brief Build Implementer rows for a req, minus its covering tests."""
    if not table_exists(conn, "req_edges"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT m.name FROM req_edges r "
        "JOIN memberdef m ON m.rowid = r.memberdef_rowid "
        "WHERE r.req_id=? ORDER BY m.name",
        (req_id,),
    ).fetchall()
    return [
        Implementer(
            name=name,
            rowid=resolve_rowid(conn, name) or -1,
            liveness=liveness_of(conn, name),
        )
        for (name,) in rows
        if name not in tests
    ]


## @brief Requirement traceability: metadata + implementers + covering tests.
## @return ReqTrace bundling the requirement's metadata (empty strings when absent), its implementing functions, and covering test names.
## @version 2
## @req REQ-DDB-QUERY-001
def req_trace(db: DbSource, req_id: str) -> ReqTrace:
    """Trace one requirement to its implementing functions (with liveness)
    and covering test functions. Metadata fields are '' when the
    requirements table has no matching row (a bare @req literal still traces).

    @brief Build a ReqTrace for one requirement id.
    @version 2
    """
    with connect(db) as conn:
        meta = None
        if table_exists(conn, "requirements"):
            meta = conn.execute(
                "SELECT block, title, acceptance, priority FROM requirements WHERE id=?",
                (req_id,),
            ).fetchone()
        tests = (
            [
                r[0]
                for r in conn.execute(
                    "SELECT DISTINCT m.name FROM req_test_edges t "
                    "JOIN memberdef m ON m.rowid = t.test_memberdef_rowid "
                    "WHERE t.req_id=? ORDER BY m.name",
                    (req_id,),
                )
            ]
            if table_exists(conn, "req_test_edges")
            else []
        )
        implementers = _req_implementers(conn, req_id, set(tests))
    block, title, acceptance, priority = meta if meta else ("", "", "", "")
    return ReqTrace(
        req_id=req_id,
        block=block,
        title=title,
        acceptance=acceptance,
        priority=priority,
        implementers=implementers,
        tests=tests,
    )


## @brief The name-ambiguity behind one function's neighbour list, or None when clean.
## @param db Database path or open connection.
## @param fn Focal function name.
## @param want_callers True to measure the inbound side, False for outbound.
## @return NameAmbiguity when the name is ambiguous AND fuzzy member edges arrive through it, else None.
## @version 1
## @req REQ-DDB-QUERY-001
def name_ambiguity(db: DbSource, fn: str, *, want_callers: bool = True) -> NameAmbiguity | None:
    """Quantify why a function can appear to have neighbours it does not have.

    Returns None on the common path — an unambiguous name, or an ambiguous one with no
    fuzzy `ast_member` neighbours — so a consumer treats a present value as a warning
    rather than having to compare a number against 1 on every call.

    ADDITIVE, deliberately: `callers`/`callees` keep returning `list[CallEdge]` and no
    existing signature moves. The alternative was a field on `CallEdge`, which would have
    changed the literal wire-key set that `test_neighbour_wire_keys_are_pinned_literally`
    exists to gate — worth doing for a per-ROW fact, but this is a property of the focal
    NAME, so a separate accessor states it in the right place.

    BOTH SURFACES get this, because it is LOSSLESS — it adds a number and removes nothing.
    Capping the rows themselves is lossy and therefore lives at the MCP boundary only,
    alongside `RESPONSE_BUDGET_BYTES`, on the reasoning that a local viewer has no context
    window to protect.

    @brief Measure the same-name ambiguity behind a neighbour list.
    @return NameAmbiguity, or None when the list is not shared with namesakes.
    @version 1
    """
    with connect(db) as conn:
        candidates, shared = _ambiguity_counts(conn, fn, want_callers=want_callers)
    return NameAmbiguity(name=fn, candidates=candidates, shared_rows=shared) if shared else None


## @brief Distinct same-named signatures, and how many neighbours arrive through the name.
## @param conn Open connection.
## @param fn Focal function name.
## @param want_callers True to count the inbound side, False for outbound.
## @return (candidate signature count, shared neighbour count); shared is 0 when unambiguous.
## @version 2
## @dg_internal
def _ambiguity_counts(conn: sqlite3.Connection, fn: str, *, want_callers: bool) -> tuple[int, int]:
    """Split out from `name_ambiguity` to keep both inside the max-3-returns standard,
    which the combined form breached at four — and the split is the better shape anyway,
    since it separates COUNTING from deciding whether the counts are worth reporting.

    Counts DISTINCT SIGNATURES, not memberdef rows: decl/def duality gives one function
    several rows, so a row count would call every documented header declaration an
    overload. `is_overloaded` draws the same distinction for the same reason.

    @brief Count same-name candidates and the neighbours shared through the name.
    @return (candidates, shared).
    @version 2
    """
    if not table_exists(conn, "call_edges"):
        return 0, 0
    candidates = len({sig for _, sig, _, _, _ in function_candidates(conn, fn)})
    if candidates < 2:
        return candidates, 0
    endpoint, focal = ("c", "x") if want_callers else ("x", "c")
    shared = conn.execute(
        f"SELECT COUNT(DISTINCT {endpoint}.name) FROM call_edges e "
        "JOIN memberdef c ON c.rowid = e.caller_rowid "
        "JOIN memberdef x ON x.rowid = e.callee_rowid "
        f"WHERE {focal}.name=? AND e.source=? AND e.confidence=?",
        (fn, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
    ).fetchone()[0]
    return candidates, int(shared or 0)
