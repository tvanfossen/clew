# SPDX-License-Identifier: MIT
"""The repository web: every function in one zoomable, walkable view (round 4, R3).

OWNER 2026-11-16: "full repo web, zoomable, interactive, and animatable single viewpoint -
different selections simply jump the camera position to the according position, zooming out past
a threshold collapses functions to blocks accordingly". It replaces the box map.

THE GEOMETRY IS COMPUTED HERE, deterministically:

  * SPOKES — one wedge per block (`graph.build_graph`'s declared-or-coupled blocks), in the order
    the repository declared them, its angle growing with its function count (a floor keeps a small
    block legible);
  * RINGS — a function's call depth from the entry points (a function no non-test code calls is
    ring 0, at the centre); each call takes its callee one ring out, capped at `MAX_RING`;
  * inside a wedge and ring, functions are ordered by file then name, so a file's functions are
    neighbours, and spread over sub-rows when a ring is crowded.

The page's script (`web.js`) only draws, pans, zooms and moves the camera: below a zoom threshold
it draws the blocks and their weighted links (semantic zoom, Perlin & Fox 1993); above it, the
functions; selecting one draws its callers and callees and lets the reader walk them. Camera moves
follow a smooth zoom-and-pan path (van Wijk & Nuij 2003) unless the reader prefers reduced motion.
The same blocks are written as a table under the canvas, for anyone the canvas does not serve.

@brief Lay out and render the repository web.
@version 1
"""

from __future__ import annotations

import json
import math
from collections import defaultdict, deque
from html import escape
from pathlib import Path
from typing import Any

from ..query._common import connect, table_exists

## The page script, shipped beside clew.js and loaded only by the web page.
WEB_JS = (Path(__file__).parent / "themes" / "clew" / "static" / "web.js").read_text(
    encoding="utf-8"
)
## The deepest ring drawn; deeper calls share it.
## The default; `wiki.web.max_ring` states it (R5-CFG C8, 2.0.0).
MAX_RING = 8
## Geometry, in world units: the innermost ring's radius, the band per ring, the gap between
## wedges (radians), the least spacing between two functions on one row, rows per band.
_R0, _BAND, _GAP, _SPACING, _ROWS = 70.0, 80.0, 0.025, 7.0, 6
## The least share of the turn a block gets, so a small block stays clickable.
_FLOOR = 0.025


## @brief The web's data: blocks, functions with positions, edges, block links.
## @param db The index.
## @param graph `build_graph(..., exclude_tests=True)` output.
## @param order Block ids in the order the repository declared them; others follow in graph order.
## @return Plain data for the page.
## v2: the ring cap is wiki.web.max_ring (2.0.0, R5-CFG C8)
## v3: owners overlay and vendor areas (2.0.0, P5)
## v4: vendor areas outside the boundary (2.0.0, P5, owner round-5 ruling)
## v5: requirement overlay (2.0.0, P5.4)
## @version 5
## @req REQ-DDB-WIKI-019
def web_data(
    db: Path,
    graph: dict[str, Any],
    order: list[str] | None = None,
    max_ring: int = MAX_RING,
    owners: bool = True,
) -> dict[str, Any]:
    """@brief Compute the web. @return Data."""
    ## THE OWNER'S RULING (round 5): vendor sits OUTSIDE the boundary. First-party blocks share the
    ## whole circle; each vendor area is one node beyond the outer ring, and calls into it end there.
    every = _ordered(graph["components"], order or [])
    blocks = [b for b in every if not b.get("vendor")]
    vendors = [b for b in every if b.get("vendor")]
    index = {b["id"]: i for i, b in enumerate(blocks)}
    owner = graph.get("file_block") or {}
    facts = {(p["name"], p["file"]): p for p in graph.get("symbols") or []}
    with connect(db) as conn:
        all_funcs = _functions(conn, owner)
        all_edges = _edges(conn, all_funcs)
        first_owner = _first_owners(conn) if owners else {}
    funcs = {r: f for r, f in all_funcs.items() if owner[f[1]] in index}
    edges = {(a, b) for a, b in all_edges if a in funcs and b in funcs}
    ring = _rings(funcs, edges, max_ring)
    _wedges(blocks, funcs, owner)
    nodes, slot = _place(blocks, index, funcs, owner, ring, facts)
    boundary, crossing = _boundary(vendors, all_funcs, all_edges, owner, nodes, slot, ring)
    ## P5 (2.0.0): THE OWNERS OVERLAY: each node carries its file's first owner, unless the
    ## audience withholds them (`exclude_owners`), in which case no node carries one.
    for node in nodes:
        if node["file"] in first_owner:
            node["owner"] = first_owner[node["file"]]
    req_ids = _index_requirements(nodes, facts)
    return {
        "req_ids": req_ids,
        "blocks": [_block_row(b) for b in blocks],
        "nodes": nodes,
        "edges": sorted({(slot[a], slot[b]) for a, b in edges if a in slot and b in slot}),
        "links": [
            {"from": link["from"], "to": link["to"], "calls": link["calls"]}
            for link in graph["links"]
            if link.get("calls")
        ],
        "max_ring": max(ring.values(), default=0),
        "geometry": {"r0": _R0, "band": _BAND},
        "boundary": boundary,
        "boundary_edges": crossing,
    }


## @brief The vendor areas as boundary nodes outside the circle, and the calls that end at them.
## @param vendors The vendor blocks (with `calls_in`).
## @param funcs Every drawn-or-vendor function: rowid → (name, file, line).
## @param edges Every call between them.
## @param owner file → block.
## @param nodes The placed first-party nodes.
## @param slot rowid → node index.
## @param ring rowid → ring, for the outer radius.
## @return (boundary rows, [[caller node, boundary index], ...]).
## @version 1
## @utility
def _boundary(
    vendors, funcs, edges, owner, nodes, slot, ring
) -> tuple[list[dict], list[list[int]]]:
    """EACH AREA SITS AT THE MEAN ANGLE OF ITS CALLERS, one band beyond the outer ring, so the calls
    into it are short and do not cross the circle; one with no first-party caller sits at angle 0.
    SIZED BY USE: the radius grows with the square root of `calls_in`, as link widths do.

    @brief Place boundary nodes.
    @return Rows and edges.
    """
    at = {b["id"]: i for i, b in enumerate(vendors)}
    crossing: set[tuple[int, int]] = set()
    for a, b in edges:
        j = at.get(owner.get(funcs[b][1], ""))
        if j is not None and a in slot:
            crossing.add((slot[a], j))
    outer = _R0 + (max(ring.values(), default=0) + 2.5) * _BAND
    rows = []
    for j, v in enumerate(vendors):
        callers = [nodes[i] for i, k in crossing if k == j]
        sx = sum(n["x"] for n in callers)
        sy = sum(n["y"] for n in callers)
        angle = math.atan2(sy, sx) if callers else 0.0
        rows.append(
            {
                "id": v["id"],
                "calls_in": int(v.get("calls_in") or 0),
                "files": v.get("files", 0),
                "functions": v.get("functions", 0),
                "x": round(outer * math.cos(angle), 1),
                "y": round(outer * math.sin(angle), 1),
                "r": round(10 + 6 * math.sqrt(int(v.get("calls_in") or 0)), 1),
            }
        )
    return rows, [list(e) for e in sorted(crossing)]


## @brief Each file's first owner, in rule order, from the index's owners layer.
## @param conn Open connection.
## @return {file: owner}; empty when the layer is absent.
## @version 1
## @utility
def _first_owners(conn: Any) -> dict[str, str]:
    """@brief Read owners. @return Map."""
    if not table_exists(conn, "owners"):
        return {}
    out: dict[str, str] = {}
    for rel, who in conn.execute(
        "SELECT p.name, o.owner FROM owners o JOIN path p ON p.rowid = o.path_rowid ORDER BY o.rowid"
    ):
        out.setdefault(str(rel), str(who))
    return out


## @brief Blocks in declared order, then the rest in graph order.
## @param comps The graph's components.
## @param order Declared block ids.
## @return Components, ordered.
## @version 1
## @utility
def _ordered(comps: list[dict], order: list[str]) -> list[dict]:
    """@brief Order blocks. @return Blocks."""
    rank = {name: i for i, name in enumerate(order)}
    pos = {c["id"]: i for i, c in enumerate(comps)}
    return sorted(
        (dict(c) for c in comps), key=lambda c: (rank.get(c["id"], len(rank)), pos[c["id"]])
    )


## @brief The non-test functions the graph placed: rowid → (name, file, line).
## @param conn Open connection.
## @param owner file → block.
## @return The map.
## @version 1
## @utility
def _functions(conn: Any, owner: dict[str, str]) -> dict[int, tuple[str, str, int]]:
    """@brief Read functions. @return Map."""
    rows = conn.execute(
        "SELECT m.rowid, m.name, p.name, COALESCE(m.bodystart, m.line, 0) FROM memberdef m "
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        "WHERE m.kind = 'function'"
    )
    return {int(r): (str(n), str(f), int(line or 0)) for r, n, f, line in rows if str(f) in owner}


## @brief Call edges between drawn functions.
## @param conn Open connection.
## @param funcs The drawn functions.
## @return (caller, callee) rowid pairs.
## @version 1
## @utility
def _edges(conn: Any, funcs: dict) -> set[tuple[int, int]]:
    """A BINDING IS NOT A CALL and a fuzzy edge is a guess, as for the graph's links.

    @brief Read edges.
    @return Pairs.
    """
    if not table_exists(conn, "call_edges"):
        return set()
    return {
        (int(a), int(b))
        for a, b in conn.execute(
            "SELECT DISTINCT caller_rowid, callee_rowid FROM call_edges "
            "WHERE source != 'binding' AND confidence != 'fuzzy'"
        )
        if int(a) in funcs and int(b) in funcs and int(a) != int(b)
    }


## @brief Each function's ring: its call depth from the entry points.
## @param funcs The drawn functions.
## @param edges Call edges.
## @return rowid → ring.
## v2: the ring cap is wiki.web.max_ring (2.0.0, R5-CFG C8)
## @version 2
## @utility
def _rings(funcs: dict, edges: set[tuple[int, int]], max_ring: int = MAX_RING) -> dict[int, int]:
    """BREADTH FIRST from every function nothing drawn calls. A function reached only around a
    cycle has no entry point; the lowest rowid of what is left seeds another walk, so every
    function gets a ring and the result does not depend on set order.

    @brief Call depth.
    @return Rings.
    """
    out_of: dict[int, list[int]] = defaultdict(list)
    called = set()
    for a, b in sorted(edges):
        out_of[a].append(b)
        called.add(b)
    ring: dict[int, int] = {}
    seeds = sorted(set(funcs) - called)
    while len(ring) < len(funcs):
        if not seeds:
            seeds = [min(set(funcs) - set(ring))]
        queue = deque((s, 0) for s in seeds if s not in ring)
        for s in seeds:
            ring.setdefault(s, 0)
        while queue:
            node, depth = queue.popleft()
            for nxt in out_of[node]:
                if nxt not in ring:
                    ring[nxt] = min(depth + 1, max_ring)
                    queue.append((nxt, depth + 1))
        seeds = []
    return ring


## @brief Each block's angular range, written into it.
## @param blocks Ordered blocks; `a0` / `a1` written.
## @param funcs The drawn functions.
## @param owner file → block.
## @return None.
## v2: owners overlay and vendor areas (2.0.0, P5)
## v3: vendor areas outside the boundary (2.0.0, P5, owner round-5 ruling)
## @version 3
## @utility
def _wedges(blocks: list[dict], funcs: dict, owner: dict[str, str]) -> None:
    """@brief Angles. @return None."""
    count: dict[str, int] = defaultdict(int)
    for _n, rel, _l in funcs.values():
        count[owner[rel]] += 1
    total = max(1, sum(count.values()))
    shares = [max(count[b["id"]] / total, _FLOOR) for b in blocks]
    usable = 2 * math.pi - _GAP * len(blocks)
    angle = 0.0
    for block, share in zip(blocks, shares):
        span = usable * share / sum(shares)
        block["a0"], block["a1"] = angle, angle + span
        angle += span + _GAP


## @brief Every function's position.
## @param blocks Blocks with angles.
## @param index block id → position in `blocks`.
## @param funcs The drawn functions.
## @param owner file → block.
## @param ring rowid → ring.
## @param facts (name, file) → the graph's point (tier, changed).
## @return (node rows, rowid → node index).
## @version 1
## @utility
def _place(blocks, index, funcs, owner, ring, facts) -> tuple[list[dict], dict[int, int]]:
    """FILE THEN NAME along each ring of a wedge; a crowded ring spreads over sub-rows inside its
    band rather than overlapping, so every function stays a distinct target.

    @brief Positions.
    @return Nodes and slots.
    """
    groups: dict[tuple[int, int], list[int]] = defaultdict(list)
    for rowid in sorted(funcs, key=lambda r: (funcs[r][1], funcs[r][2], funcs[r][0])):
        groups[(index[owner[funcs[rowid][1]]], ring[rowid])].append(rowid)
    nodes, slot = [], {}
    for (bi, r), rowids in sorted(groups.items()):
        block = blocks[bi]
        for rowid, (x, y) in zip(rowids, _arc(block["a0"], block["a1"], r, len(rowids))):
            name, rel, line = funcs[rowid]
            node = {"name": name, "file": rel, "line": line, "block": bi, "ring": r}
            node["x"], node["y"] = round(x, 1), round(y, 1)
            fact = facts.get((name, rel)) or {}
            for key in ("tier", "changed"):
                if key in fact:
                    node[key] = fact[key]
            slot[rowid] = len(nodes)
            nodes.append(node)
    return nodes, slot


## @brief Give each implementing node indices into one sorted table of requirement ids.
## @param nodes The placed nodes (gain `r`).
## @param facts (name, file) → the graph's point, carrying `reqs`.
## @return The table: every requirement id a node implements, sorted.
## @version 1
## @req REQ-DDB-WIKI-022
def _index_requirements(nodes: list[dict], facts: dict) -> list[str]:
    """COMPACT: one id table and small integers per node, rather than the id strings repeated on
    every function that implements them (P5.1's weight budget; clew's own map has ~3,000 nodes).

    @brief Requirement overlay data.
    @return Ids.
    """
    table = sorted({r for p in facts.values() for r in p.get("reqs") or ()})
    at = {r: i for i, r in enumerate(table)}
    for node in nodes:
        reqs = (facts.get((node["name"], node["file"])) or {}).get("reqs")
        if reqs:
            node["r"] = [at[r] for r in reqs]
    return table


## @brief Positions for n functions on one ring of one wedge.
## @param a0 The wedge's first angle.
## @param a1 Its last angle.
## @param r The ring.
## @param n How many.
## @return (x, y) per function.
## @version 1
## @utility
def _arc(a0: float, a1: float, r: int, n: int) -> list[tuple[float, float]]:
    """@brief Spread on the arc. @return Points."""
    pad = min(0.01, (a1 - a0) / 6)
    lo, hi = a0 + pad, a1 - pad
    base = _R0 + r * _BAND
    rows = max(1, min(_ROWS, math.ceil(n * _SPACING / max(1.0, (hi - lo) * base))))
    per = math.ceil(n / rows)
    out = []
    for i in range(n):
        row, col = divmod(i, per)
        radius = base + (row - (rows - 1) / 2) * (_BAND * 0.7 / max(1, rows))
        theta = lo + (hi - lo) * (col + 0.5) / per
        out.append((radius * math.cos(theta), radius * math.sin(theta)))
    return out


## @brief The block fields the page reads.
## @param b A block.
## @return The row.
## v2: owners overlay and vendor areas (2.0.0, P5)
## @version 2
## @utility
def _block_row(b: dict) -> dict:
    """@brief Block row. @return Row."""
    keep = ("id", "a0", "a1", "functions", "files", "declared", "inferred_files", "requirements")
    row = {k: b[k] for k in keep if k in b}
    row["a0"], row["a1"] = round(row["a0"], 5), round(row["a1"], 5)
    for key in ("req_ids", "threads", "changed", "tested_calls", "vendor", "calls_in"):
        if key in b:
            row[key] = b[key]
    return row


## @brief The web's HTML: toolbar, canvas, side panel, inline data, and the block table.
## @param data `web_data` output, optionally with `flows` and node `href`s added.
## @return HTML.
## v2: owners overlay and vendor areas (2.0.0, P5)
## @version 2
## @req REQ-DDB-WIKI-021
def web_html(data: dict[str, Any]) -> str:
    """THE DATA IS INLINE (`application/json`, never executed) and the script is local: the page
    works from file://, a Pages site or an ADO wiki with nothing fetched.

    @brief Render.
    @return HTML.
    """
    payload = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
    flows = "".join(
        f'<option value="{i}">{escape(f["title"])}</option>'
        for i, f in enumerate(data.get("flows") or [])
    )
    picker = (
        f'<label>Play a flow <select data-web-flow><option value="">none</option>{flows}</select>'
        "</label>"
        if flows
        else ""
    )
    return (
        '<div class="web" data-web>'
        '<div class="web-bar"><input type="search" data-web-search placeholder="Find a function" '
        'aria-label="Find a function"><button type="button" data-web-zoom="1.6">+</button>'
        '<button type="button" data-web-zoom="0.625">&minus;</button>'
        '<button type="button" data-web-fit>Whole system</button>'
        '<label>Lens <select data-web-lens><option value="tier">Requirements</option>'
        '<option value="block">Blocks</option>'
        + ('<option value="changed">Change</option>' if _has(data, "changed") else "")
        + ('<option value="owner">Owners</option>' if _has(data, "owner") else "")
        + f"</select></label>{picker}</div>"
        '<div class="web-stage"><canvas class="web-canvas" aria-label="Repository web: blocks '
        'as wedges, functions on rings by call depth"></canvas>'
        '<aside class="web-panel" data-web-panel hidden></aside>'
        '<div class="web-tip" data-web-tip hidden></div></div>'
        f'<script type="application/json" id="web-data">{payload}</script>'
        "</div>" + _table(data) + '<script src="_static/web.js"></script>'
    )


## @brief Whether any node carries a key.
## @param data The web.
## @param key The key.
## @return True when one does.
## @version 1
## @utility
def _has(data: dict, key: str) -> bool:
    """@brief Probe. @return Bool."""
    return any(key in n for n in data["nodes"])


## @brief The blocks as a table: the same facts without the canvas.
## @param data The web.
## @return HTML.
## v2: vendor areas outside the boundary (2.0.0, P5, owner round-5 ruling)
## @version 2
## @utility
def _table(data: dict) -> str:
    """@brief Table view. @return HTML."""
    rows = []
    for i, b in enumerate(data["blocks"]):
        tiers = ", ".join(f"{t} {n}" for t, n in sorted((b.get("requirements") or {}).items()))
        placed = len(b.get("inferred_files") or [])
        how = (
            "declared"
            if b.get("declared")
            else "unassigned"
            if b["id"] == "Unassigned"
            else "package"
        )
        rows.append(
            f'<tr><td><a href="#b={i}">{escape(b["id"])}</a></td><td>{how}</td>'
            f'<td class="n">{b.get("functions", 0)}</td><td class="n">{b.get("files", 0)}</td>'
            f'<td class="n">{placed}</td><td>{escape(tiers) or "—"}</td></tr>'
        )
    for b in data.get("boundary") or []:
        rows.append(
            f"<tr><td>{escape(b['id'])}</td><td>vendor, outside the boundary</td>"
            f'<td class="n">{b.get("functions", 0)}</td><td class="n">{b.get("files", 0)}</td>'
            f'<td class="n">{b["calls_in"]} calls in</td><td>—</td></tr>'
        )
    return (
        '<h2 id="blocks">Blocks</h2><p>The same blocks as the web, as a table. Files a block was '
        "given by coupling (not declared) are counted as placed. A vendor area is drawn outside the "
        "circle, sized by the calls into it.</p>"
        '<table class="clew web-table"><thead><tr><th>block</th><th>how</th><th>functions</th>'
        "<th>files</th><th>placed by coupling</th><th>requirements by tier</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


## @brief Attach each node's brief, its function's one-line summary from the index.
## @param nodes Map nodes ({name, file, ...}); changed in place.
## @param briefs (function, file) → brief.
## @return None.
## @version 1
## @utility
def _with_briefs(nodes: list[dict], briefs: dict) -> None:
    """ABSENT, NOT EMPTY: a function with no brief gets no key, and the panel prints nothing.

    @brief Briefs onto nodes.
    @return None.
    """
    for n in nodes:
        brief = briefs.get((n["name"], n["file"]))
        if brief:
            n["brief"] = brief


## @brief Write the map page: the web, with source links and playable flows.
## @param db The index.
## @param graph `build_graph(..., exclude_tests=True)` output.
## @param order Declared block ids, in declaration order.
## @param pages The flow pages (their calls and hops, in call order).
## @param hrefs (function, file) → its symbol page section.
## @param source The Sphinx source directory.
## @return The page name, or "" when nothing is drawn.
## v2: the ring cap is wiki.web.max_ring (2.0.0, R5-CFG C8)
## v3: owners overlay and vendor areas (2.0.0, P5)
## v4: node briefs (X-4)
## @version 4
## @req REQ-DDB-WIKI-021
def web_page(
    db: Path,
    graph: dict[str, Any],
    order: list[str],
    pages: list,
    hrefs: dict[tuple[str, str], str],
    source: Path,
    max_ring: int = MAX_RING,
    owners: bool = True,
) -> str:
    """A FLOW IS PLAYED BY ITS FUNCTIONS IN CALL ORDER: the camera visits each step; a step whose
    function is not drawn (test code, or outside the index) is skipped, never invented.

    @brief Write map.md.
    @return Page name.
    """
    if not graph["components"]:
        return ""
    data = web_data(db, graph, order, max_ring, owners)
    ## X-4 (owner review 2, 2026-11-22): what each function does, at a glance in the pop-out.
    from ..query._common import connect
    from .entities import _briefs

    with connect(db) as conn:
        _with_briefs(data["nodes"], _briefs(conn))
    slot = {(n["name"], n["file"]): i for i, n in enumerate(data["nodes"])}
    for n in data["nodes"]:
        href = hrefs.get((n["name"], n["file"]))
        if href:
            n["href"] = href
    data["flows"] = [f for f in (_flow(p, slot) for p in pages) if len(f["steps"]) > 1]
    lead = (
        "Every function in the repository, in one view. Each wedge is a block of the system; rings "
        "run outward by call depth from the entry points at the centre. Zoom in to see functions, "
        "click one to see what it calls and what calls it, and walk from there; zoom out and the "
        "functions fold back into their blocks. Pick a flow to watch it travel."
    )
    text = ["# Map", "", lead, "", "```{raw} html", web_html(data), "```", ""]
    (Path(source) / "map.md").write_text("\n".join(text), encoding="utf-8")
    return "map"


## @brief One flow's steps as node indices, in call order.
## @param page A flow page.
## @param slot (function, file) → node index.
## @return {title, page, steps}.
## @version 1
## @utility
def _flow(page: Any, slot: dict[tuple[str, str], int]) -> dict[str, Any]:
    """@brief Flow steps. @return Flow."""
    steps: list[int] = []
    for (caller, callee), (cfile, efile) in zip(page.calls, page.hops):
        for key in ((caller, cfile), (callee, efile)):
            i = slot.get(key)
            if i is not None and (not steps or steps[-1] != i):
                steps.append(i)
    return {"title": page.title, "page": page.name, "steps": steps}


## @brief The sidebar's labelled block list: the web's blocks, in its order, each a link to it.
## @param graph The graph.
## @param order Declared block ids.
## @return HTML with `@MAP@` for the map page's path, or "" with no blocks.
## @version 1
## @req REQ-DDB-WIKI-021
def minimap_html(graph: dict[str, Any], order: list[str]) -> str:
    """ROUND 4, R2 (owner: the unlabelled sidebar boxes were "easier to simply click into map"):
    one labelled row per block with its size, ordered as the web draws them, so a block's link
    (`#b=<index>`) lands on that block. ONE STRING FOR EVERY PAGE: a page lights its own blocks
    with a CSS rule on `[data-comp]`, so the markup never varies.

    @brief Labelled minimap.
    @return HTML.
    """
    blocks = _ordered(graph["components"], order)
    if not blocks:
        return ""
    top = max(b.get("functions", 0) for b in blocks) or 1
    rows = "".join(
        f'<a href="@MAP@#b={i}" data-comp="{escape(b["id"])}" title="{escape(b["id"])}">'
        f'<span class="mm-name">{escape(b["id"])}</span>'
        f'<span class="mm-size" style="--w:{max(4, round(100 * b.get("functions", 0) / top))}%">'
        f'</span><span class="mm-n">{b.get("functions", 0)}</span></a>'
        for i, b in enumerate(blocks)
    )
    return f'<nav class="minimap" aria-label="System blocks">{rows}</nav>'
