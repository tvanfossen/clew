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
@version 2
"""

from __future__ import annotations

import fnmatch
from collections import defaultdict
from pathlib import Path
from typing import Any

from ..query._common import connect, table_exists
from ..vocabulary import EXTERNAL_ROOT_COLUMN

## The schema version of the graph JSON.
GRAPH_VERSION = 1
## The block holding every undeclared file inside a nested git tree (OWNER 2026-11-17).
VENDOR = "Vendor"
## Container layout geometry.
_BOX_W, _BOX_H, _GAP_X, _GAP_Y = 200, 120, 60, 70
## The band at the top of a box kept clear of points, for the component's name.
_HEAD = 34


## @brief The component a file belongs to.
## @param rel Repo-relative path.
## @param declared (name, globs) groupings from `wiki.components`, first match wins.
## @return The component id.
## v2: the package depth is wiki.component_depth (2.0.0, R5-CFG C7)
## @version 2
## @req REQ-DDB-WIKI-019
def component_of(
    rel: str, declared: tuple[tuple[str, tuple[str, ...]], ...] = (), depth: int = 2
) -> str:
    """A DECLARED GROUPING WINS; otherwise the package (`package_of`).

    @brief Component of a file.
    @return Component id.
    """
    for name, globs in declared:
        if any(fnmatch.fnmatch(rel, g) for g in globs):
            return name
    return package_of(rel, depth)


## @brief The package a file sits in: its first `depth` directories.
## @param rel Repo-relative path.
## @param depth How many leading directories name a package (`wiki.component_depth`).
## @return The package id, `(root)` for a root file.
## @version 1
## @req REQ-DDB-WIKI-019
def package_of(rel: str, depth: int = 2) -> str:
    """`clew/query/x.py` → `clew/query`, a top-level module `clew/cli.py` → `clew`, a root file →
    `(root)`. THE DEPTH IS DECLARED (R5-CFG C7, 2.0.0): two segments made every Maven/Gradle file
    (`src/main/java/com/acme/...`) one block `src/main`, and Go's `internal/x/y` one `internal/x`.

    @brief Package of a file.
    @return Package id.
    """
    parts = rel.split("/")
    if len(parts) == 1:
        return "(root)"
    dirs = parts[:-1]
    return "/".join(dirs[:depth])


## @brief Build the graph.
## @param db The index.
## @param evidence Requirement evidence rows (implementer sites, tiers, tests).
## @param impact clew-guard impact entries, or None when there is no report.
## @param declared `wiki.components` groupings.
## @param exclude_tests Leave test code out of the layout; count its calls as `tested_calls`.
## @return The graph as plain data.
## v2: `exclude_tests` (round 3, P1c: test code is a lens on the system, not boxes above it).
## v3 (round 4, R1): declared blocks win; undeclared files join by coupling (`inferred_files`).
## v4: the package depth is wiki.component_depth (2.0.0, R5-CFG C7)
## v5 (2.0.0, P5): a vendor area carries `vendor` and `calls_in`.
## @version 5
## @req REQ-DDB-WIKI-019
def build_graph(
    db: Path,
    evidence: list,
    impact: list[dict] | None,
    declared: tuple = (),
    component_depth: int = 2,
    exclude_tests: bool = False,
) -> dict[str, Any]:
    """@brief Aggregate and lay out. @return Graph."""
    with connect(db) as conn:
        funcs = _functions(conn)
        tested = _tested_calls(conn, funcs) if exclude_tests else None
        if exclude_tests:
            funcs = {r: f for r, f in funcs.items() if not f[2]}
        file_block, inferred = _blocks(conn, funcs, declared, component_depth)
        comp = {rowid: file_block[rel] for rowid, (_n, rel, _t) in funcs.items()}
        links = _links(conn, comp)
        threads = _threads(conn, comp)
        calls_in = _vendor_calls_in(conn, funcs, comp)
    components = _components(funcs, comp, evidence, impact, threads)
    for cid, node in components.items():
        node["declared"] = any(cid == name for name, _g in declared)
        node["inferred_files"] = sorted(inferred.get(cid, ()))
        if is_vendor(cid):
            ## A VENDOR AREA IS SIZED BY USE (P5): the calls into it from first-party code.
            node["vendor"] = True
            node["calls_in"] = calls_in.get(cid, 0)
    if tested is not None:
        for rowid, cid in comp.items():
            components[cid].setdefault("tested_calls", 0)
            components[cid]["tested_calls"] += tested.get(rowid, 0)
    order = _layout(components, links)
    return {
        "graph_version": GRAPH_VERSION,
        "components": [components[c] for c in order],
        "links": [{"from": a, "to": b, **w} for (a, b), w in sorted(links.items())],
        "symbols": _points(funcs, comp, components, evidence, impact),
        "file_block": dict(sorted(file_block.items())),
    }


## @brief Every file's block: declared, else Vendor, else joined by coupling, else Unassigned.
## @param conn Open connection.
## @param funcs rowid → (name, file, in test code).
## @param declared `wiki.components` groupings.
## @return ({file: block}, {block: files placed by coupling}).
## v2 (OWNER 2026-11-17, "Vendor code is a block of its own"): an undeclared file the index tags
## as inside a nested git tree is the Vendor block — never a package, never joined by coupling.
## v3: the package depth is wiki.component_depth (2.0.0, R5-CFG C7)
## v4 (2.0.0, P5): one Vendor block PER AREA (`Vendor: <root>`), not one for every vendored file.
## @version 4
## @req REQ-DDB-WIKI-019
def _blocks(
    conn: Any, funcs: dict, declared: tuple, depth: int = 2
) -> tuple[dict[str, str], dict[str, set[str]]]:
    """DECLARED BLOCKS WIN (round 4, R1; the reflexion method with clustering, Christl, Koschke &
    Storey, WCRE 2005). With nothing declared every file keeps its package and nothing is
    inferred. Otherwise an undeclared file joins the block it shares the most calls with, either
    direction, repeated until nothing moves, so a file coupled only through another undeclared
    file still lands. Ties go to the block declared first. A file coupled to none is Unassigned.

    @brief Assign blocks.
    @return Blocks and inferred placements.
    """
    files = {rel for _n, rel, _t in funcs.values()}
    named = {name for name, _g in declared}
    areas = vendor_areas(conn)
    owner = {
        rel: f"{VENDOR}: {areas[rel]}" if rel in areas and block not in named else block
        for rel, block in ((rel, component_of(rel, declared, depth)) for rel in files)
    }
    if not declared:
        return owner, {}
    loose = {rel for rel, b in owner.items() if b not in named and not is_vendor(b)}
    pairs = _file_calls(conn, funcs)
    order = {name: i for i, (name, _g) in enumerate(declared)}
    placed: dict[str, set[str]] = defaultdict(set)
    moved = True
    while loose and moved:
        moved = False
        for rel in sorted(loose):
            weight: dict[str, int] = defaultdict(int)
            for other, n in pairs.get(rel, {}).items():
                if owner.get(other) in named:
                    weight[owner[other]] += n
            if weight:
                best = min(weight, key=lambda b: (-weight[b], order[b]))
                owner[rel] = best
                placed[best].add(rel)
                loose.discard(rel)
                moved = True
    for rel in loose:
        owner[rel] = "Unassigned"
    return owner, dict(placed)


## @brief Whether a block id is a vendor area.
## @param block The block id.
## @return True for `Vendor` and `Vendor: <root>`.
## @version 1
## @utility
def is_vendor(block: str) -> bool:
    """@brief Vendor block? @return Bool."""
    return block == VENDOR or block.startswith(f"{VENDOR}: ")


## @brief Every vendored file's area: its nested git tree, or the declared root it is under.
## @param conn Open connection.
## @return {file: area root}.
## @version 1
## @utility
def vendor_areas(conn: Any) -> dict[str, str]:
    """ONE AREA PER TREE OR DECLARATION (OWNER, round 5: "one node per vendored area"). A file in a
    nested git tree belongs to that tree (`clew/external.py` stamps it on `path`); a file under a
    declared `vendored:` root belongs to that root (W5). An index built before gh#335 has no
    stamp, and there nothing nested was indexed at all.

    @brief Map vendored files to their areas.
    @return Areas.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(path)")}
    stamp = f"COALESCE({EXTERNAL_ROOT_COLUMN}, '')" if EXTERNAL_ROOT_COLUMN in columns else "''"
    roots = _declared_vendored_roots(conn)
    out: dict[str, str] = {}
    for name, tree in conn.execute(f"SELECT name, {stamp} FROM path WHERE type = 1"):  # noqa: S608
        rel = str(name)
        declared = next((r for r in roots if rel == r or rel.startswith(f"{r}/")), "")
        if tree or declared:
            out[rel] = str(tree) or declared
    return out


## @brief Files the index tags as belonging to a nested git tree (gh#335), or the repo declares vendored.
## @param conn Open connection.
## @return Repo-relative paths of vendored files.
## v2 (2.0.0, W5): and every file under a declared `vendored:` root the build found.
## v3 (2.0.0, P5): the keys of `vendor_areas`.
## @version 3
## @utility
def _vendored(conn: Any) -> set[str]:
    """@brief Vendored files. @return Paths."""
    return set(vendor_areas(conn))


## @brief The `vendored:` roots the build found present (`scope.vendored_roots`).
## @param conn Open connection.
## @return Repo-relative roots, without a trailing slash.
## @version 1
## @utility
def _declared_vendored_roots(conn: Any) -> list[str]:
    """W5 (2.0.0): the build records a declared `vendored:` here, and this module read only the
    nested-git-tree stamp, so a copied-in library the repository calls vendored was drawn as
    first-party code.

    @brief Read declared vendored roots.
    @return Roots.
    """
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'build_meta'").fetchone():
        return []
    row = conn.execute("SELECT value FROM build_meta WHERE key = 'scope.vendored_roots'").fetchone()
    return [r.strip().rstrip("/") for r in str(row[0] if row else "").split(",") if r.strip()]


## @brief Per vendor area, the distinct first-party functions-to-its-functions calls.
## @param conn Open connection.
## @param funcs rowid → (name, file, in test code).
## @param comp rowid → component.
## @return {vendor block: distinct (caller, callee) function pairs crossing into it}.
## @version 1
## @utility
def _vendor_calls_in(conn: Any, funcs: dict, comp: dict[int, str]) -> dict[str, int]:
    """BY FUNCTION, NOT BY ROW: doxygen writes a declaration row and a definition row for one C
    function, so one call reads as several rowid pairs. A pair is (name, file) on each side.

    @brief Count calls into vendor areas.
    @return Counts.
    """
    if not table_exists(conn, "call_edges"):
        return {}
    pairs: dict[str, set] = defaultdict(set)
    for a, b in conn.execute(
        "SELECT DISTINCT caller_rowid, callee_rowid FROM call_edges "
        "WHERE source != 'binding' AND confidence != 'fuzzy'"
    ):
        into, out_of = comp.get(int(b)), comp.get(int(a))
        if into and out_of and is_vendor(into) and not is_vendor(out_of):
            pairs[into].add((funcs[int(a)][:2], funcs[int(b)][:2]))
    return {block: len(p) for block, p in pairs.items()}


## @brief Call counts between files, both directions.
## @param conn Open connection.
## @param funcs rowid → (name, file, in test code).
## @return {file: {other file: calls}}.
## @version 1
## @utility
def _file_calls(conn: Any, funcs: dict) -> dict[str, dict[str, int]]:
    """A BINDING IS NOT A CALL and a fuzzy edge is a guess, as for links.

    @brief File coupling.
    @return Counts.
    """
    out: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    if not table_exists(conn, "call_edges"):
        return {}
    for a, b in conn.execute(
        "SELECT DISTINCT caller_rowid, callee_rowid FROM call_edges "
        "WHERE source != 'binding' AND confidence != 'fuzzy'"
    ):
        fa, fb = funcs.get(int(a)), funcs.get(int(b))
        if fa and fb and fa[1] != fb[1]:
            out[fa[1]][fb[1]] += 1
            out[fb[1]][fa[1]] += 1
    return out


## @brief Every function: rowid → (name, file, in test code).
## @param conn Open connection.
## @return The map.
## @version 1
## @utility
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


## @brief Calls from test code into each non-test function.
## @param conn Open connection.
## @param funcs rowid → (name, file, in test code).
## @return {callee rowid: distinct test callers}.
## @version 1
## @utility
def _tested_calls(conn: Any, funcs: dict[int, tuple[str, str, bool]]) -> dict[int, int]:
    """A BINDING IS NOT A CALL and a fuzzy edge is a guess, as for links.

    @brief Count test calls.
    @return Counts.
    """
    out: dict[int, int] = defaultdict(int)
    if table_exists(conn, "call_edges"):
        for a, b in conn.execute(
            "SELECT DISTINCT caller_rowid, callee_rowid FROM call_edges "
            "WHERE source != 'binding' AND confidence != 'fuzzy'"
        ):
            caller, callee = funcs.get(int(a)), funcs.get(int(b))
            if caller and callee and caller[2] and not callee[2]:
                out[int(b)] += 1
    return dict(out)


## @brief Calls and shared keys between components.
## @param conn Open connection.
## @param comp rowid → component.
## @return {(from, to): {calls, keys}}.
## @version 1
## @utility
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
## @utility
def _bump(out: dict, a: str | None, b: str | None, kind: str) -> None:
    """@brief Count. @return None."""
    if a and b and a != b:
        out[(a, b)][kind] += 1


## @brief The threads each component's functions run on.
## @param conn Open connection.
## @param comp rowid → component.
## @return {component: thread names}.
## @version 1
## @utility
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
## v2: `paths` — the component's files, listed (the map's box modal names them).
## @version 2
## @utility
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
        node["paths"] = sorted(node["files"])
        node["files"] = len(node["files"])
        if threads.get(name):
            node["threads"] = sorted(threads[name])
    return nodes


## @brief Requirement tiers per component, from implementer sites.
## @param nodes Component nodes; updated.
## @param file_comp file → component.
## @param evidence Requirement evidence.
## @return None.
## v2: `req_ids` — each requirement with its tier, for links from the map.
## @version 2
## @utility
def _requirements_into(nodes: dict, file_comp: dict[str, str], evidence: list) -> None:
    """A REQUIREMENT COUNTS ONCE PER COMPONENT, however many of its implementers live there.

    @brief Tier counts.
    @return None.
    """
    for row in evidence:
        for cid in {file_comp.get(rel) for _n, rel, _l in row.implementer_sites} - {None}:
            tiers = nodes[cid].setdefault("requirements", {})
            tiers[row.tier] = tiers.get(row.tier, 0) + 1
            nodes[cid].setdefault("req_ids", []).append([row.req_id, row.tier])


## @brief Functions changed by the last impact report, per component.
## @param nodes Component nodes; updated.
## @param file_comp file → component.
## @param impact Impact entries.
## @return None.
## @version 1
## @utility
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
## @utility
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
## @utility
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
## @utility
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
## @utility
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
## v2: points start below the name band, so the Code level keeps the box's name legible.
## v3 (2.0.0, P5.4): a point carries the ids of the requirements it implements (`reqs`).
## @version 3
## @utility
def _points(funcs, comp, components, evidence, impact) -> list[dict[str, Any]]:
    """A GRID PER BOX, by file then name, so neighbours in the cloud are neighbours in the source.

    @brief Point cloud.
    @return Points.
    """
    tier_of: dict[tuple[str, str], str] = {}
    reqs_of: dict[tuple[str, str], set[str]] = defaultdict(set)
    for row in evidence:
        for name, rel, _line in row.implementer_sites:
            tier_of[(name, rel)] = row.tier
            reqs_of[(name, rel)].add(row.req_id)
    changed = {
        (f.get("name"), f.get("file")) for e in impact or [] for f in e.get("functions") or []
    }
    by_comp: dict[str, list[int]] = defaultdict(list)
    for rowid in sorted(funcs, key=lambda r: (funcs[r][1], funcs[r][0])):
        by_comp[comp[rowid]].append(rowid)
    points = []
    for cid, rowids in by_comp.items():
        box = components[cid]
        cols = max(1, int((len(rowids) * box["w"] / (box["h"] - _HEAD)) ** 0.5))
        rows = max(1, -(-len(rowids) // cols))
        for i, rowid in enumerate(rowids):
            name, rel, _t = funcs[rowid]
            point = {
                "id": rowid,
                "name": name,
                "file": rel,
                "x": box["x"] + 6 + (i % cols) * (box["w"] - 12) / cols,
                "y": box["y"] + _HEAD + (i // cols) * (box["h"] - _HEAD - 6) / rows,
            }
            if (name, rel) in tier_of:
                point["tier"] = tier_of[(name, rel)]
                point["reqs"] = sorted(reqs_of[(name, rel)])
            if impact is not None:
                point["changed"] = (name, rel) in changed
            points.append(point)
    return points
