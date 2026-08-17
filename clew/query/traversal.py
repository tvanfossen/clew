# SPDX-License-Identifier: MIT
"""D6 — unified causal traversal (`chain_trace`) over the enriched db.

`chain_trace` walks the UNION of the non-fuzzy call graph (`call_edges`,
including the `fnptr` layer) and the shared-key dataflow graph
(`shared_key_edges`), annotating every hop with the R1 semantics that ride
directly on the `shared_key_edges` row (dispatch_mode / edge_kind /
edge_triggered / crosses_thread / to_thread) and terminating a branch at an
`external_boundaries` terminus.

INVARIANT this traversal depends on: **queue/async hops live ONLY in
`shared_key_edges`**. A `call_edges` hop is therefore always synchronous
and stays on the caller's thread — call-hop thread continuity is
*implicit-same-thread*, never re-derived. Only a `key` hop can cross a
thread boundary, and when it does the crossing is already computed and
stored (`crosses_thread` / `to_thread_id`) at build time. This is why D6 is
a plain per-hop annotator and not a thread-inference pass.

Bounds: **cycles** are bounded by PATH membership (a frozenset carried per
BFS path — NOT a global visited set, so diamonds are still explored), and a
back-edge to an ancestor is recorded as a hop but not expanded. **Depth** is
bounded by `max_depth`; **fan-out** is bounded by the ported `_cap_at_depth`
taper (halve the neighbor cap each level, min 1). A per-rowid best-depth
guard keeps a DAG's shared nodes from re-expanding without suppressing the
minimum-depth reach.

@brief D6 causal-chain traversal + shared terminus/req helpers.
@version 1
"""

from __future__ import annotations

import sqlite3
from collections import deque
from dataclasses import replace

from ..vocabulary import EDGE_CLASS_CALL, EDGE_CLASS_KEY
from ._common import (
    DbSource,
    candidate_rows,
    connect,
    function_candidates,
    is_overloaded,
    resolve_rowid,
    table_exists,
    to_bool,
)
from .models import Chain, ChainNode, Hop, Terminus
from .symbols import _collapse_variants, _key_edge_rows


## @brief Per-depth neighbor cap: halve each level outward, min 1.
## @return Integer neighbor cap for the given depth: max_neighbors halved per level below depth 1, floored at 1.
## @version 2
## @req REQ-DDB-QUERY-002
def _cap_at_depth(max_neighbors: int, depth: int) -> int:
    """Base cap at depth 1; halved for each deeper level, floored at 1.
    Ported verbatim from the explorer docs_server taper.

    @brief Taper the neighbor cap as chain depth increases.
    @version 2
    """
    return max(max_neighbors // (2 ** (depth - 1)), 1)


## @brief External-boundary termini registered against one memberdef rowid.
## @return List of Terminus (external global name, kind, registering function) for the rowid's external boundaries.
## @version 2
## @req REQ-DDB-QUERY-002
def termini_for(conn: sqlite3.Connection, rowid: int) -> list[Terminus]:
    """@brief Return the Terminus rows for an in-repo function's external globals."""
    if not table_exists(conn, "external_boundaries"):
        return []
    rows = conn.execute(
        "SELECT e.global_name, e.kind, rb.name FROM external_boundaries e "
        "LEFT JOIN memberdef rb ON rb.rowid = e.registered_by_rowid "
        "WHERE e.memberdef_rowid=? ORDER BY e.global_name",
        (rowid,),
    ).fetchall()
    return [Terminus(global_name=g, registered_by=rb, kind=k) for g, k, rb in rows]


## @brief Requirement ids linked to one function name.
## @return List of requirement id strings @req-linked to the function name, in id order.
## @version 2
## @req REQ-DDB-QUERY-005
def _reqs_for(conn: sqlite3.Connection, name: str) -> list[str]:
    """@brief Return the requirement ids @req-linked to a function name."""
    if not table_exists(conn, "req_edges"):
        return []
    return [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT r.req_id FROM req_edges r "
            "JOIN memberdef m ON m.rowid = r.memberdef_rowid "
            "WHERE m.name=? ORDER BY r.req_id",
            (name,),
        )
    ]


## @brief Build a ChainNode (reqs + terminus status) for one reached function.
## @return ChainNode for the function at the given depth, carrying its linked requirements and any terminus records.
## @version 2
## @req REQ-DDB-QUERY-005
def _make_node(conn: sqlite3.Connection, name: str, rowid: int, depth: int) -> ChainNode:
    """@brief Assemble a ChainNode with linked reqs + terminus records."""
    termini = termini_for(conn, rowid)
    return ChainNode(
        name=name,
        rowid=rowid,
        depth=depth,
        requirements=_reqs_for(conn, name),
        is_terminus=bool(termini),
        termini=termini,
    )


## @brief Non-fuzzy call-graph hops out of / into one function name.
## @return List of (neighbor_name, call Hop) pairs, one per neighbour, excluding fuzzy-confidence edges.
## @version 6
## @req REQ-DDB-QUERY-002
def _call_hops(conn: sqlite3.Connection, name: str, forward: bool) -> list[tuple[str, Hop]]:
    """The `confidence!='fuzzy'` filter is deliberate and is NOT shared with
    `symbols._direct_call_edges`, which keeps fuzzy rows. A traversal EXPANDS
    every hop, so one fuzzy edge (a name matched without confirming the class)
    multiplies into a whole wrong subtree; a flat neighbour list has no such
    amplification and lets the caller weigh the row itself.

    Collapsed per neighbour through `symbols._collapse_variants` (#38). Unlike the
    flat surfaces this was never an INFLATION bug — `_record_neighbor` already
    deduped hops on (edge_class, from_name, to_name, key_name), excluding `source`
    — it was a DETERMINISM bug: that dedup keeps the FIRST hop it sees, and this
    query ordered only by neighbour name, so which layer's `source`/`confidence`
    a hop reported depended on SQLite's row order. Collapsing by strongest
    evidence makes it a property of the data.

    @brief Build (neighbor_name, call-Hop) pairs for one traversal direction.
    @version 6
    """
    if not table_exists(conn, "call_edges"):
        return []
    endpoint, focal = ("x", "c") if forward else ("c", "x")
    sql = (
        f"SELECT DISTINCT {endpoint}.name, e.source, e.confidence FROM call_edges e "
        "JOIN memberdef c ON c.rowid = e.caller_rowid "
        "JOIN memberdef x ON x.rowid = e.callee_rowid "
        f"WHERE {focal}.name=? AND e.confidence!='fuzzy' ORDER BY {endpoint}.name"
    )
    by_name: dict[str, list[tuple[str, str | None]]] = {}
    for nname, src, conf in conn.execute(sql, (name,)):
        by_name.setdefault(nname, []).append((src, conf))
    out: list[tuple[str, Hop]] = []
    for nname, variants in by_name.items():
        src, conf = _collapse_variants(variants)
        frm, to = (name, nname) if forward else (nname, name)
        out.append(
            (
                nname,
                Hop(
                    edge_class=EDGE_CLASS_CALL,
                    from_name=frm,
                    to_name=to,
                    source=src,
                    confidence=conf,
                ),
            ),
        )
    return out


## @brief Shared-key dataflow hops out of / into one function name.
## @return List of (neighbor_name, key Hop) pairs for the direction, each annotated with the R1 dispatch/thread semantics.
## @version 3
## @req REQ-DDB-QUERY-002
def _key_hops(conn: sqlite3.Connection, name: str, forward: bool) -> list[tuple[str, Hop]]:
    """The JOIN lives in `symbols._key_edge_rows`, shared with `key_edges` and
    the merged neighbour list, so an R1 column can never be added to one shape
    and forgotten in another. A forward hop asks for `name` as the WRITER.

    A key hop's certainty is a `key_strength`, so it goes to `strength` and
    `confidence` stays None — a call hop's `confidence` is a `call_match` and the
    two vocabularies do not compare.

    @brief Build (neighbor_name, key-Hop) pairs with full R1 annotations.
    @version 3
    """
    out: list[tuple[str, Hop]] = []
    for nname, k, kind, src, conf, dm, et, ct, tthr in _key_edge_rows(
        conn, name, as_writer=forward
    ):
        frm, to = (name, nname) if forward else (nname, name)
        out.append(
            (
                nname,
                Hop(
                    edge_class=EDGE_CLASS_KEY,
                    from_name=frm,
                    to_name=to,
                    source=src,
                    confidence=None,
                    strength=conf,
                    key_name=k,
                    edge_kind=kind,
                    dispatch_mode=dm,
                    edge_triggered=to_bool(et),
                    crosses_thread=to_bool(ct),
                    to_thread=tthr,
                ),
            ),
        )
    return out


## @brief All UNION neighbors of one function, deterministically ordered.
## @return List of (neighbor_name, Hop) pairs merging call and key hops, sorted by (name, edge_class, key_name) for cap-stable order.
## @version 2
## @req REQ-DDB-QUERY-002
def _neighbors(conn: sqlite3.Connection, name: str, forward: bool) -> list[tuple[str, Hop]]:
    """@brief Merge + sort call and key hops for one node (cap-stable order)."""
    hops = _call_hops(conn, name, forward) + _key_hops(conn, name, forward)
    return sorted(hops, key=lambda t: (t[0], t[1].edge_class, t[1].key_name or ""))


## @brief Immutable BFS state threaded through chain expansion.
## @version 1
class _ChainState:
    """Accumulators for the chain BFS: reached nodes (min depth), deduped
    hops, and the per-rowid best-depth guard.

    @brief Chain BFS accumulator state.
    @version 1
    """

    __slots__ = ("best_depth", "hops", "nodes", "omitted")

    ## @brief Initialize empty chain-BFS accumulators (nodes, hops, best-depth guard).
    ## @version 2
    ## @dg_internal
    def __init__(self) -> None:
        self.nodes: dict[int, ChainNode] = {}
        self.hops: dict[tuple, Hop] = {}
        self.best_depth: dict[int, int] = {}
        ## Per-rowid count of neighbours the fan-out taper DROPPED (#134). Accumulated
        ## here rather than written onto the node because `ChainNode` is frozen and is
        ## built before its neighbours are known — the counts are folded in with
        ## `dataclasses.replace` when the result is assembled.
        ##
        ## Accumulates with `+=` rather than assigning: a node can be dequeued more than
        ## once across different paths, and each expansion drops its own neighbours.
        self.omitted: dict[int, int] = {}


## @brief Record one discovered neighbor: hop, node, and (maybe) enqueue.
## @version 1
## @dg_internal
def _expand_neighbor(
    conn: sqlite3.Connection,
    nname: str,
    hop: Hop,
    parent: tuple[int, frozenset[int]],
    state: _ChainState,
    queue: deque,
) -> None:
    """Dedup the hop, resolve the neighbor's canonical rowid, record/refresh
    its node at the child depth, and enqueue it for further expansion unless
    it closes a cycle (rowid already on this path) or fails to improve on its
    best known depth (DAG re-expansion guard).

    @brief Record + conditionally enqueue one chain neighbor.
    @version 1
    """
    parent_depth, path = parent
    child_depth = parent_depth + 1
    state.hops.setdefault(
        (hop.edge_class, hop.from_name, hop.to_name, hop.key_name),
        hop,
    )
    nrowid = resolve_rowid(conn, nname)
    if nrowid is None:
        return
    if nrowid not in state.nodes or child_depth < state.nodes[nrowid].depth:
        state.nodes[nrowid] = _make_node(conn, nname, nrowid, child_depth)
    if nrowid in path:
        return  # cycle: hop + node recorded, but never expanded
    prev = state.best_depth.get(nrowid)
    if prev is None or child_depth < prev:
        state.best_depth[nrowid] = child_depth
        queue.append((nname, nrowid, child_depth, path | {nrowid}))


_FORWARD_ALIASES = frozenset({"forward", "forwards", "downstream"})
_BACKWARD_ALIASES = frozenset({"backward", "backwards", "upstream"})


## @brief Normalize a caller-supplied traversal direction to its canonical form.
## @param direction Caller-supplied direction (case- and alias-tolerant).
## @return Canonical "forward" or "backward".
## @version 1
## @dg_internal
def _normalize_direction(direction: str) -> str:
    """Map a direction word onto its canonical form, REFUSING anything else.

    This was previously `forward = direction != "backward"`, which failed OPEN:
    only the exact lowercase "backward" traced backward, so `upstream`,
    `backwards`, `BACKWARD` and every typo silently produced a FORWARD trace —
    and the Chain echoed the caller's own word back, labelling the result with
    the direction that was asked for while carrying the opposite data. On a
    causal-reasoning tool that is a silent wrong answer, the one failure a
    consumer cannot detect. A model that asks the wrong way should get a
    correctable error, never a confident inversion.

    @brief Canonicalize a traversal direction, rejecting unknown words.
    @return "forward" or "backward".
    @version 1
    """
    token = str(direction).strip().lower()
    if token in _FORWARD_ALIASES:
        return "forward"
    if token in _BACKWARD_ALIASES:
        return "backward"
    raise ValueError(
        f"unknown direction {direction!r} — expected one of "
        f"{sorted(_FORWARD_ALIASES | _BACKWARD_ALIASES)}"
    )


## @brief D6 unified causal traversal from a seed function.
## @param db Path | str | sqlite3.Connection to the clew.db.
## @param seed Seed function name to trace from.
## @param direction 'forward'/'downstream' or 'backward'/'upstream' (alias- and case-tolerant; unknown words raise).
## @param max_depth Maximum hop depth from the seed.
## @param max_neighbors Base fan-out cap at depth 1 (tapered by _cap_at_depth).
## @version 7
## @req REQ-DDB-QUERY-002
def chain_trace(
    db: DbSource,
    seed: str,
    direction: str = "forward",
    max_depth: int = 6,
    max_neighbors: int = 8,
) -> Chain:
    """Breadth-first walk of UNION(non-fuzzy call_edges incl. fnptr,
    shared_key_edges) from `seed`, annotating each hop and terminating a
    branch at an `external_boundaries` terminus. Cycles are path-bounded;
    depth is `max_depth`-bounded; fan-out tapers via `_cap_at_depth`. Returns
    an empty Chain when the seed resolves to no indexed function.

    DELIBERATELY DOES NOT TAKE gh#37's `qualified` SELECTOR, and this is the one
    accessor returning `candidates` that refuses it. The walk resolves every hop by
    BARE NAME — `_call_hops` and `_key_hops` both filter `memberdef.name=?`, unlike
    the flat `symbols._direct_call_edges` which filters by identity rowid. So a
    disambiguated seed would give an identity-correct root node sitting on top of a
    name-scoped traversal: the chain's own edges would still be the union over every
    namesake from depth 1 onward, and the reply would carry no signal that only the
    seed had been narrowed.

    That is precisely the shape gh#37 was filed about — an argument whose effect the
    surface cannot deliver — so accepting it here to look complete would create a
    second instance of the defect while closing the first. `candidates` on the seed
    stays ADVISORY here on purpose: read it, then narrow with `dossier`/`callers`/
    `callees`, which do resolve by identity. Making the traversal identity-scoped is
    the separate piece of work that would let this argument mean something.

    @brief Trace a bounded, annotated causal chain from a seed function.
    @version 7
    """
    direction = _normalize_direction(direction)
    forward = direction == "forward"
    with connect(db) as conn:
        seed_cands = function_candidates(conn, seed)
        if not seed_cands:
            return Chain(seed=seed, direction=direction, max_depth=max_depth)
        seed_rowid = seed_cands[0][0]
        overloads = candidate_rows(conn, seed, seed_cands) if is_overloaded(seed_cands) else []
        state = _ChainState()
        state.nodes[seed_rowid] = _make_node(conn, seed, seed_rowid, 0)
        state.best_depth[seed_rowid] = 0
        queue: deque = deque([(seed, seed_rowid, 0, frozenset({seed_rowid}))])
        while queue:
            name, rowid, depth, path = queue.popleft()
            if depth >= max_depth or state.nodes[rowid].is_terminus:
                continue
            cap = _cap_at_depth(max_neighbors, depth + 1)
            neighbours = _neighbors(conn, name, forward)
            ## RECORD WHAT THE TAPER DROPS (#134). The slice below is the whole reason a
            ## deep trace terminates, but applying it silently made a capped node
            ## indistinguishable from an exhausted one — 8 of 131 callers reported as 8,
            ## with nothing in the payload from which the gap could be derived.
            if len(neighbours) > cap:
                state.omitted[rowid] = state.omitted.get(rowid, 0) + len(neighbours) - cap
            for nname, hop in neighbours[:cap]:
                _expand_neighbor(conn, nname, hop, (depth, path), state, queue)
        nodes = sorted(
            (
                replace(node, omitted=state.omitted.get(rowid, 0))
                for rowid, node in state.nodes.items()
            ),
            key=lambda n: (n.depth, n.name),
        )
        hops = sorted(
            state.hops.values(),
            key=lambda h: (h.edge_class, h.from_name, h.to_name, h.key_name or ""),
        )
    return Chain(
        seed=seed,
        direction=direction,
        max_depth=max_depth,
        nodes=nodes,
        hops=hops,
        candidates=overloads,
    )
