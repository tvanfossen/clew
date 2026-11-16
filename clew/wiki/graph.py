# SPDX-License-Identifier: MIT
"""The system graph every visual view of the wiki reads: one typed model, several zoom levels.

Round 3, P1a (owner 2026-11-15: "topography at several layers — system block diagram, requirements
level — rather than just function-to-function hops"). The index is aggregated ONCE into a graph at
the zoom levels C4 names (owner-recognisable vocabulary):

  * CONTAINER — components (a package: the first two path segments under a package root, or a
    `wiki.components` grouping the repository declares) with the calls, shared keys and threads
    between them;
  * COMPONENT — the files of each component;
  * CODE — every function as a point inside its component's box (a point cloud: position and
    tint only, no edges — edges at this scale are a hairball).

Each component carries its LENS facts, so a view switches lens without recomputing: requirements
implemented there by tier, tests reaching it, threads running in it, functions changed by the last
impact report. A lens whose source is absent is absent (`changed` without an impact report), never
zero.

LAYOUT IS COMPUTED HERE, deterministically (layered by call direction, ordered by barycentre), so
tests and screenshots are reproducible and the page's script only toggles classes.

@brief Build the wiki's system graph with its layout.
@version 1
"""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..query._common import connect, table_exists

## The schema version of the graph JSON.
GRAPH_VERSION = 1
## Container layout geometry.
_BOX_W, _BOX_H, _GAP_X, _GAP_Y = 200, 120, 60, 70


## @brief The component a file belongs to.
## @param rel Repo-relative path.
## @param declared (name, globs) groupings from `wiki.components`, first match wins.
## @return The component id.
## @version 1
## @req REQ-DDB-WIKI-019
def component_of(rel: str, declared: tuple[tuple[str, tuple[str, ...]], ...] = ()) -> str:
    """A DECLARED GROUPING WINS; otherwise the package: `clew/query/x.py` → `clew/query`, a
    top-level module `clew/cli.py` → `clew`, a root file → `(root)`.

    @brief Component of a file.
    @return Component id.
    """
    for name, globs in declared:
        if any(fnmatch.fnmatch(rel, g) for g in globs):
            return name
    parts = rel.split("/")
    if len(parts) == 1:
        return "(root)"
    return "/".join(parts[:2]) if len(parts) > 2 else parts[0]


## @brief Build the graph.
## @param db The index.
## @param evidence Requirement evidence rows (implementer sites, tiers, tests).
## @param impact clew-guard impact entries, or None when there is no report.
## @param declared `wiki.components` groupings.
## @return The graph as plain data.
## @version 1
## @req REQ-DDB-WIKI-019
def build_graph(
    db: Path, evidence: list, impact: list[dict] | None, declared: tuple = ()
) -> dict[str, Any]:
    """@brief Aggregate and lay out. @return Graph."""
    with connect(db) as conn:
        funcs = _functions(conn)
        comp = {rowid: component_of(rel, declared) for rowid, (_n, rel, _t) in funcs.items()}
        links = _links(conn, comp)
        threads = _threads(conn, comp)
    components = _components(funcs, comp, evidence, impact, threads)
    order = _layout(components, links)
    return {
        "graph_version": GRAPH_VERSION,
        "components": [components[c] for c in order],
        "links": [{"from": a, "to": b, **w} for (a, b), w in sorted(links.items())],
        "symbols": _points(funcs, comp, components, evidence, impact),
    }


## @brief Every function: rowid → (name, file, in test code).
## @param conn Open connection.
## @return The map.
## @version 1
## @dg_internal
def _functions(conn: Any) -> dict[int, tuple[str, str, bool]]:
    """@brief Read functions. @return Map."""
    tests = set()
    if table_exists(conn, "test_scope"):
        tests = {r for (r,) in conn.execute("SELECT path_rowid FROM test_scope")}
    rows = conn.execute(
        "SELECT m.rowid, m.name, p.name, p.rowid FROM memberdef m JOIN path p "
        "ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function'"
    )
    return {int(r): (str(n), str(rel), int(pr) in tests) for r, n, rel, pr in rows}


## @brief Calls and shared keys between components.
## @param conn Open connection.
## @param comp rowid → component.
## @return {(from, to): {calls, keys}}.
## @version 1
## @dg_internal
def _links(conn: Any, comp: dict[int, str]) -> dict[tuple[str, str], dict[str, int]]:
    """A BINDING IS NOT A CALL and a fuzzy edge is a guess: neither weighs a component link.

    @brief Aggregate links.
    @return Links.
    """
    out: dict[tuple[str, str], dict[str, int]] = defaultdict(lambda: {"calls": 0, "keys": 0})
    if table_exists(conn, "call_edges"):
        for a, b in conn.execute(
            "SELECT DISTINCT caller_rowid, callee_rowid FROM call_edges "
            "WHERE source != 'binding' AND confidence != 'fuzzy'"
        ):
            _bump(out, comp.get(int(a)), comp.get(int(b)), "calls")
    if table_exists(conn, "shared_key_edges"):
        for a, b in conn.execute(
            "SELECT DISTINCT writer_rowid, reader_rowid FROM shared_key_edges"
        ):
            _bump(out, comp.get(int(a)), comp.get(int(b)), "keys")
    return dict(out)


## @brief Count one link between two different components.
## @param out The accumulator.
## @param a From component.
## @param b To component.
## @param kind `calls` or `keys`.
## @return None.
## @version 1
## @dg_internal
def _bump(out: dict, a: str | None, b: str | None, kind: str) -> None:
    """@brief Count. @return None."""
    if a and b and a != b:
        out[(a, b)][kind] += 1


## @brief The threads each component's functions run on.
## @param conn Open connection.
## @param comp rowid → component.
## @return {component: thread names}.
## @version 1
## @dg_internal
def _threads(conn: Any, comp: dict[int, str]) -> dict[str, set[str]]:
    """@brief Thread membership. @return Map."""
    out: dict[str, set[str]] = defaultdict(set)
    if table_exists(conn, "thread_membership") and table_exists(conn, "threads"):
        for rowid, name in conn.execute(
            "SELECT tm.memberdef_rowid, t.name FROM thread_membership tm "
            "JOIN threads t ON t.id = tm.thread_id"
        ):
            if int(rowid) in comp:
                out[comp[int(rowid)]].add(str(name))
    return out


## @brief Per-component facts for every lens.
## @param funcs Functions.
## @param comp rowid → component.
## @param evidence Requirement evidence.
## @param impact Impact entries or None.
## @param threads Threads per component.
## @return {component: node}.
## @version 1
## @dg_internal
def _components(funcs, comp, evidence, impact, threads) -> dict[str, dict[str, Any]]:
    """@brief Component nodes. @return Nodes."""
    nodes: dict[str, dict[str, Any]] = {}
    file_comp: dict[str, str] = {}
    for rowid, (_n, rel, is_test) in funcs.items():
        cid = comp[rowid]
        node = nodes.setdefault(cid, {"id": cid, "files": set(), "functions": 0, "test": True})
        node["files"].add(rel)
        node["functions"] += 1
        node["test"] = node["test"] and is_test
        file_comp[rel] = cid
    _requirements_into(nodes, file_comp, evidence)
    if impact is not None:
        _impact_into(nodes, file_comp, impact)
    for name, node in nodes.items():
        node["files"] = len(node["files"])
        if threads.get(name):
            node["threads"] = sorted(threads[name])
    return nodes


## @brief Requirement tiers per component, from implementer sites.
## @param nodes Component nodes; updated.
## @param file_comp file → component.
## @param evidence Requirement evidence.
## @return None.
## @version 1
## @dg_internal
def _requirements_into(nodes: dict, file_comp: dict[str, str], evidence: list) -> None:
    """A REQUIREMENT COUNTS ONCE PER COMPONENT, however many of its implementers live there.

    @brief Tier counts.
    @return None.
    """
    for row in evidence:
        for cid in {file_comp.get(rel) for _n, rel, _l in row.implementer_sites} - {None}:
            tiers = nodes[cid].setdefault("requirements", {})
            tiers[row.tier] = tiers.get(row.tier, 0) + 1


## @brief Functions changed by the last impact report, per component.
## @param nodes Component nodes; updated.
## @param file_comp file → component.
## @param impact Impact entries.
## @return None.
## @version 1
## @dg_internal
def _impact_into(nodes: dict, file_comp: dict[str, str], impact: list[dict]) -> None:
    """MEASURED ZERO when the report exists: every component gets `changed`.

    @brief Change counts.
    @return None.
    """
    for node in nodes.values():
        node["changed"] = 0
    for entry in impact:
        for fn in entry.get("functions") or []:
            cid = file_comp.get(str(fn.get("file") or ""))
            if cid is not None:
                nodes[cid]["changed"] += 1


## @brief Deterministic layered layout: callers above callees, barycentre ordering.
## @param components The nodes; x / y / w / h are written into each.
## @param links The component links.
## @return Component ids in drawing order.
## @version 1
## @dg_internal
def _layout(components: dict[str, dict], links: dict) -> list[str]:
    """Layer = longest path from a source over the de-cycled call direction; within a layer,
    components are ordered by the mean position of their callers, ties by name.

    @brief Layout.
    @return Order.
    """
    down = _downward(links)
    rows = _layers(sorted(components), down)
    pos: dict[str, float] = {}
    order = []
    for depth in sorted(rows):
        rows[depth].sort(key=lambda c: (_barycentre(c, down, pos), c))
        for i, c in enumerate(rows[depth]):
            pos[c] = float(i)
            components[c].update(
                x=i * (_BOX_W + _GAP_X), y=depth * (_BOX_H + _GAP_Y), w=_BOX_W, h=_BOX_H
            )
            order.append(c)
    return order


## @brief The call direction between components with every cycle broken by weight.
## @param links Component links.
## @return {component: components it points down to}.
## @version 1
## @dg_internal
def _downward(links: dict) -> dict[str, set[str]]:
    """OF TWO COMPONENTS CALLING EACH OTHER, the heavier direction is "down"; a tie goes to the
    alphabetically earlier caller, so the result never depends on dict order.

    @brief De-cycle.
    @return Direction.
    """
    down: dict[str, set[str]] = defaultdict(set)
    for (a, b), w in links.items():
        back = links.get((b, a), {"calls": 0})["calls"]
        if w["calls"] and (w["calls"] > back or (w["calls"] == back and a < b)):
            down[a].add(b)
    return down


## @brief Longest-path layers over the downward graph, bounded so a residual cycle terminates.
## @param names Component ids, sorted.
## @param down The downward direction.
## @return {layer: component ids}.
## @version 1
## @dg_internal
def _layers(names: list[str], down: dict[str, set[str]]) -> dict[int, list[str]]:
    """@brief Assign layers. @return Rows."""
    layer = dict.fromkeys(names, 0)
    for _ in range(len(names)):
        moved = False
        for a in names:
            for b in down.get(a, ()):
                if b in layer and layer[b] < layer[a] + 1 <= len(names):
                    layer[b], moved = layer[a] + 1, True
        if not moved:
            break
    rows: dict[int, list[str]] = defaultdict(list)
    for c in names:
        rows[layer[c]].append(c)
    return rows


## @brief The mean position of a component's callers already placed (or last when none).
## @param c The component.
## @param down The downward direction.
## @param pos Placed positions.
## @return The barycentre.
## @version 1
## @dg_internal
def _barycentre(c: str, down: dict[str, set[str]], pos: dict[str, float]) -> float:
    """@brief Mean caller position. @return Value."""
    callers = [pos[a] for a in pos if c in down.get(a, ())]
    return sum(callers) / len(callers) if callers else float("inf")


## @brief The code-level point cloud: each function placed inside its component's box.
## @param funcs Functions.
## @param comp rowid → component.
## @param components Laid-out components.
## @param evidence Requirement evidence (tint by tier).
## @param impact Impact entries or None.
## @return Points.
## @version 1
## @dg_internal
def _points(funcs, comp, components, evidence, impact) -> list[dict[str, Any]]:
    """A GRID PER BOX, by file then name, so neighbours in the cloud are neighbours in the source.

    @brief Point cloud.
    @return Points.
    """
    tier_of: dict[tuple[str, str], str] = {}
    for row in evidence:
        for name, rel, _line in row.implementer_sites:
            tier_of[(name, rel)] = row.tier
    changed = {
        (f.get("name"), f.get("file")) for e in impact or [] for f in e.get("functions") or []
    }
    by_comp: dict[str, list[int]] = defaultdict(list)
    for rowid in sorted(funcs, key=lambda r: (funcs[r][1], funcs[r][0])):
        by_comp[comp[rowid]].append(rowid)
    points = []
    for cid, rowids in by_comp.items():
        box = components[cid]
        cols = max(1, int((len(rowids) * box["w"] / box["h"]) ** 0.5))
        for i, rowid in enumerate(rowids):
            name, rel, _t = funcs[rowid]
            point = {
                "id": rowid,
                "name": name,
                "file": rel,
                "x": box["x"] + 6 + (i % cols) * (box["w"] - 12) / cols,
                "y": box["y"] + 6 + (i // cols) * (box["h"] - 12) / max(1, -(-len(rowids) // cols)),
            }
            if (name, rel) in tier_of:
                point["tier"] = tier_of[(name, rel)]
            if impact is not None:
                point["changed"] = (name, rel) in changed
            points.append(point)
    return points
