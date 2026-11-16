# SPDX-License-Identifier: MIT
"""Symbol pages and the ego-graph (round 3, P1f).

Owner 2026-11-15: links should be DOSSIER REFERENCES — a symbol's own page, which in turn links
its source — and the dossier drawn as a "spiderweb" of its links, a way of WALKING SOURCE. Every
symbol the site references (a requirement's implementers, a flow's functions) gets a section on
its FILE's page (`sym-<path>.html#s-<name>`), holding every definition of that name in the file:

  * signature and brief, and a source permalink when one resolves;
  * a radial EGO-GRAPH: callers on the left, callees on the right, and one more hop outward; a
    fan-out larger than the ring holds is folded into one "+N more" node, never dropped silently;
    a neighbour with a section of its own links to it, so the graph can be walked;
  * the requirements it implements and the flows it is on;
  * its body, bundled from the file (withheld under `exclude_bodies`).

THE INDEX IS READ DIRECTLY (signature, body extent, resolved call edges) rather than through
`export_dossier`: that engine costs ~76 ms a symbol (measured on clew's own index, 64 symbols,
single and batched), and a site references ~900 — over a minute before rendering starts. A
binding is not a call and a fuzzy edge is a guess, as on the map.

@brief Write symbol pages with their ego-graphs.
@version 1
"""

from __future__ import annotations

import math
import re
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from ..query._common import connect, table_exists

## Neighbours drawn on the first ring, per side, before folding.
_RING1 = 10
## Neighbours drawn per first-ring node on the second ring, before folding.
_RING2 = 3
## The most calls a test-to-implementer path is searched across.
_PATH_DEPTH = 5
## The most body lines a section bundles.
_BODY_LINES = 120
_W = 960
## First- and second-ring radii.
_R1, _R2 = 160, 300


## @brief One definition of a referenced symbol.
## @version 1
@dataclass(frozen=True)
class Definition:
    """@brief Rowid, name, file, signature, brief, body extent. @version 1"""

    rowid: int
    name: str
    file: str
    signature: str
    brief: str
    start: int
    end: int


## @brief The page a file's symbols live on.
## @param rel Repo-relative path.
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-025
def page_for(rel: str) -> str:
    """@brief Page name. @return Name."""
    return "sym-" + re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-")


## @brief A symbol's section link.
## @param name The function.
## @param rel Its file.
## @return The href.
## @version 1
## @req REQ-DDB-WIKI-025
def symbol_href(name: str, rel: str) -> str:
    """ONE SECTION PER NAME PER FILE, holding every definition of it — so a link never needs to
    know which of several same-named definitions it means.

    @brief Href.
    @return Href.
    """
    return f"{page_for(rel)}.html#{anchor(name)}"


## @brief A section's id.
## @param name The function.
## @return The id.
## @version 1
## @dg_internal
def anchor(name: str) -> str:
    """@brief Anchor id. @return Id."""
    return "s-" + re.sub(r"[^\w.-]", "_", name)


## @brief Write a page per file holding the referenced symbols.
## @param db The index.
## @param repo_root The repository (bodies are read from it).
## @param keys (function, file) pairs the site references.
## @param ctx req_of, flows (FlowPage list), rules (Audience), template, commit.
## @param source The Sphinx source directory.
## @return {(function, file): href} of the sections written.
## v2: test functions the evidence names get sections too (P2a).
## @version 2
## @req REQ-DDB-WIKI-025
def symbol_pages(
    db: Path, repo_root: Path, keys: set[tuple[str, str]], ctx: dict[str, Any], source: Path
) -> dict[tuple[str, str], str]:
    """@brief Write sym-*.md. @return Hrefs."""
    with connect(db) as conn:
        tests = _test_functions(conn, set(ctx.get("tests") or {}))
        defs = _definitions(conn, keys | tests)
        graph = _Edges(conn)
    ctx = {**ctx, "test_keys": tests}
    by_file: dict[str, dict[str, list[Definition]]] = defaultdict(lambda: defaultdict(list))
    for d in defs:
        by_file[d.file][d.name].append(d)
    written = {(n, f) for f, names in by_file.items() for n in names}
    for rel, names in sorted(by_file.items()):
        sections = [
            _section(name, names[name], graph, written, ctx, Path(repo_root))
            for name in sorted(names)
        ]
        text = [
            "---",
            "orphan: true",
            "---",
            "",
            f"# `{rel}`",
            "",
            "```{raw} html",
            *sections,
            "```",
            "",
        ]
        (Path(source) / f"{page_for(rel)}.md").write_text("\n".join(text), encoding="utf-8")
    return {key: symbol_href(*key) for key in written}


## @brief The test functions the evidence names, found in test code.
## @param conn Open connection.
## @param names Test names.
## @return (function, file) pairs.
## @version 1
## @dg_internal
def _test_functions(conn: Any, names: set[str]) -> set[tuple[str, str]]:
    """A NAME OUTSIDE TEST CODE is not that test: a scenario title or a Catch2 string name has no
    function of that name, and a namesake in product code is not the test.

    @brief Resolve tests.
    @return Keys.
    """
    if not names or not table_exists(conn, "test_scope"):
        return set()
    scope = {r for (r,) in conn.execute("SELECT path_rowid FROM test_scope")}
    out = set()
    for name, rel, prow in conn.execute(
        "SELECT m.name, p.name, p.rowid FROM memberdef m JOIN path p ON p.rowid = "
        "COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function'"
    ):
        if name in names and int(prow) in scope:
            out.add((str(name), str(rel)))
    return out


## @brief Every definition of each referenced (function, file).
## @param conn Open connection.
## @param keys (function, file) pairs.
## @return Definitions.
## @version 1
## @dg_internal
def _definitions(conn: Any, keys: set[tuple[str, str]]) -> list[Definition]:
    """@brief Resolve keys. @return Definitions."""
    out = []
    for name, rel in sorted(keys):
        rows = conn.execute(
            "SELECT m.rowid, m.definition, m.argsstring, m.briefdescription, m.bodystart, "
            "m.bodyend, m.line FROM memberdef m JOIN path p ON p.rowid = "
            "COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
            "WHERE m.kind = 'function' AND m.name = ? AND p.name = ? ORDER BY m.line",
            (name, rel),
        ).fetchall()
        for rowid, definition, args, brief, start, end, line in rows:
            out.append(
                Definition(
                    int(rowid),
                    name,
                    rel,
                    f"{definition or ''}{args or ''}".strip(),
                    " ".join(re.sub(r"<[^>]+>", " ", str(brief or "")).split()),
                    int(start or line or 0),
                    int(end or 0),
                )
            )
    return out


## @brief The resolved call graph, loaded once.
## @version 1
class _Edges:
    """@brief Callers, callees and names of every function. @version 1"""

    ## @brief Load edges and names.
    ## @param conn Open connection.
    ## @version 1
    ## @dg_internal
    def __init__(self, conn: Any) -> None:
        """A BINDING IS NOT A CALL and a fuzzy edge is a guess: neither is drawn.

        @brief Load.
        @return None.
        """
        self.callers: dict[int, set[int]] = defaultdict(set)
        self.callees: dict[int, set[int]] = defaultdict(set)
        self.names: dict[int, tuple[str, str]] = {}
        self.by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
        for rowid, name, rel in conn.execute(
            "SELECT m.rowid, m.name, p.name FROM memberdef m JOIN path p ON p.rowid = "
            "COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function'"
        ):
            self.names[int(rowid)] = (str(name), str(rel))
            self.by_key[(str(name), str(rel))].append(int(rowid))
        if table_exists(conn, "call_edges"):
            for a, b in conn.execute(
                "SELECT DISTINCT caller_rowid, callee_rowid FROM call_edges "
                "WHERE source != 'binding' AND confidence != 'fuzzy'"
            ):
                if int(a) != int(b):
                    self.callees[int(a)].add(int(b))
                    self.callers[int(b)].add(int(a))

    ## @brief Named neighbours of a function in one direction, sorted.
    ## @param rowid The function.
    ## @param side `callers` or `callees`.
    ## @return (name, file) pairs.
    ## @version 1
    ## @dg_internal
    def around(self, rowid: int, side: str) -> list[tuple[str, str]]:
        """@brief Neighbours. @return Pairs."""
        edges = self.callers if side == "callers" else self.callees
        return sorted({self.names[r] for r in edges.get(rowid, ()) if r in self.names})

    ## @brief The rowids a (name, file) pair names.
    ## @param key (function, file).
    ## @return Rowids.
    ## @version 1
    ## @dg_internal
    def rowids(self, key: tuple[str, str]) -> list[int]:
        """@brief Look up. @return Rowids."""
        return self.by_key.get(key, [])


## @brief One name's section: every definition of it in the file.
## @param name The function.
## @param defs Its definitions.
## @param graph The call graph.
## @param written Keys that have sections (graph nodes link to them).
## @param ctx The page context.
## @param repo_root The repository.
## @return HTML.
## v2: a test's section adds what it tests (round 3, P2a).
## @version 2
## @dg_internal
def _section(
    name: str,
    defs: list[Definition],
    graph: _Edges,
    written: set[tuple[str, str]],
    ctx: dict[str, Any],
    repo_root: Path,
) -> str:
    """@brief Section. @return HTML."""
    from .htmltable import md_title, source_url

    key = (name, defs[0].file)
    reqs = sorted(set(ctx["req_of"].get(key, ())))
    flows = sorted((p for p in ctx["flows"] if key in p.functions), key=lambda p: p.title)
    parts = [f'<section class="symbol" id="{anchor(name)}"><h2><code>{escape(name)}</code></h2>']
    for d in defs:
        url = source_url(ctx["template"], ctx["commit"], d.file, max(d.start, 1))
        where = f"{escape(d.file)}:{d.start}"
        if url:
            where = f'<a href="{escape(url)}">{where}</a>'
        parts.append(
            f'<pre class="sig">{escape(d.signature or name)}</pre>'
            + (f"<p>{escape(d.brief)}</p>" if d.brief else "")
            + f'<p class="where">{where}</p>'
            + _ego(d, graph, written)
        )
        if key in ctx.get("test_keys", ()):
            parts.append(_test_block(d, graph, ctx, repo_root))
        if not ctx["rules"].exclude_bodies:
            parts.append(_body(repo_root, d))
    if reqs:
        parts.append(
            "<h4>Requirements</h4><p>"
            + " ".join(
                f'<a class="req-badge" href="requirements.html#{escape(r)}">{escape(r)}</a>'
                for r in reqs
            )
            + "</p>"
        )
    if flows:
        parts.append(
            '<h4>Flows</h4><ul class="modal-list">'
            + "".join(
                f'<li><a href="{escape(p.name)}.html">{md_title(p.title)}</a></li>' for p in flows
            )
            + "</ul>"
        )
    return "".join(parts) + "</section>"


## @brief What a test tests: its assertions, result, verified requirements and call paths.
## @param d The test's definition.
## @param graph The call graph.
## @param ctx The page context (tests, implementers, rules).
## @param repo_root The repository.
## @return HTML.
## @version 1
## @dg_internal
def _test_block(d: Definition, graph: _Edges, ctx: dict[str, Any], repo_root: Path) -> str:
    """ASSERTIONS ARE SOURCE TEXT, withheld under `exclude_bodies`; the verified requirements and
    paths are the index's facts and stay.

    @brief Test block.
    @return HTML.
    """
    from .testfacts import assertions, verifies_block

    facts = ctx["tests"][d.name]
    paths = {
        req: _path(graph, d.rowid, ctx["implementers"].get(req, set()))
        for req, _kind in facts.verifies
    }
    out = verifies_block(facts, {r: p for r, p in paths.items() if p})
    lines = _lines(repo_root, d)
    if lines and not ctx["rules"].exclude_bodies:
        found = assertions(lines)
        if found:
            items = "".join(f"<li><code>{escape(a)}</code></li>" for a in found)
            out = f'<h4>Checks</h4><ul class="asserts">{items}</ul>' + out
    return f'<div class="test-facts">{out}</div>'


## @brief The shortest call path from a test to any implementer of a requirement.
## @param graph The call graph.
## @param start The test's rowid.
## @param targets The implementers' (function, file) pairs.
## @return Function names along the path, or [] when none is found within the depth.
## @version 1
## @dg_internal
def _path(graph: _Edges, start: int, targets: set[tuple[str, str]]) -> list[str]:
    """BREADTH-FIRST over resolved calls, at most `_PATH_DEPTH` hops: the path a reader can walk
    from the test to the code it reaches.

    @brief Path.
    @return Names.
    """
    goal = {r for key in targets for r in graph.rowids(key)}
    prev: dict[int, int] = {start: start}
    frontier = [start]
    for _ in range(_PATH_DEPTH):
        nxt = []
        for node in frontier:
            for callee in sorted(graph.callees.get(node, ())):
                if callee in prev:
                    continue
                prev[callee] = node
                if callee in goal:
                    return _unwind(graph, prev, callee)
                nxt.append(callee)
        frontier = nxt
    return []


## @brief The names along a found path.
## @param graph The call graph.
## @param prev Predecessors.
## @param end The last node.
## @return Names, first to last.
## @version 1
## @dg_internal
def _unwind(graph: _Edges, prev: dict[int, int], end: int) -> list[str]:
    """@brief Unwind. @return Names."""
    out = [end]
    while prev[out[-1]] != out[-1]:
        out.append(prev[out[-1]])
    return [graph.names[r][0] for r in reversed(out)]


## @brief A definition's ego-graph, its neighbours linked when they have sections.
## @param d The definition.
## @param graph The call graph.
## @param written Keys with sections.
## @return SVG.
## @version 1
## @dg_internal
def _ego(d: Definition, graph: _Edges, written: set[tuple[str, str]]) -> str:
    """@brief Ego-graph. @return SVG."""

    def linked(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
        return [(n, symbol_href(n, f) if (n, f) in written else "") for n, f in pairs]

    callers = graph.around(d.rowid, "callers")
    callees = graph.around(d.rowid, "callees")
    second: dict[str, list[tuple[str, str]]] = {}
    for side, ring in (("callers", callers[:_RING1]), ("callees", callees[:_RING1])):
        for key in ring:
            outward = {p for r in graph.rowids(key) for p in graph.around(r, side)}
            outward.discard((d.name, d.file))
            second[key[0]] = linked(sorted(outward))
    return ego_svg(d.name, linked(callers), linked(callees), second)


## @brief Draw an ego-graph: callers left, callees right, one more hop outward.
## @param center The function's name.
## @param callers (name, href) of its callers.
## @param callees (name, href) of its callees.
## @param second {first-ring name: [(name, href)] one hop further out}.
## @return SVG.
## @version 1
## @req REQ-DDB-WIKI-025
def ego_svg(
    center: str,
    callers: list[tuple[str, str]],
    callees: list[tuple[str, str]],
    second: dict[str, list[tuple[str, str]]],
) -> str:
    """DETERMINISTIC, RADIAL: the first ring holds at most `_RING1` per side and the second
    `_RING2` per first-ring node; what does not fit is ONE "+N more" node, so a fold is visible.
    The view is cropped to the nodes drawn, so a small neighbourhood is a small drawing.

    @brief Draw.
    @return SVG.
    """
    cx, cy = _W / 2, 0.0
    edges: list[str] = []
    nodes: list[str] = [_node(cx, cy, center, "", "center")]
    for side, ring, base in (("caller", callers, math.pi), ("callee", callees, 0.0)):
        for (name, href), angle in _arc(ring, _RING1, base, math.radians(140)):
            x, y = cx + _R1 * math.cos(angle), cy + _R1 * math.sin(angle)
            edges.append(_edge(cx, cy, x, y, side))
            nodes.append(_node(x, y, name, href, side))
            outward = second.get(name, [])
            for (n2, h2), a2 in _arc(outward, _RING2, angle, math.radians(26)):
                x2, y2 = cx + _R2 * math.cos(a2), cy + _R2 * math.sin(a2) * 0.72
                edges.append(_edge(x, y, x2, y2, side + " far"))
                nodes.append(_node(x2, y2, n2, h2, side + " far"))
    ys = [float(y) for y in re.findall(r'<circle cx="[^"]+" cy="([^"]+)"', "".join(nodes))]
    top, height = min(ys) - 40, max(ys) - min(ys) + 70
    return (
        f'<svg class="ego" xmlns="http://www.w3.org/2000/svg" width="{_W}" height="{height:.0f}" '
        f'viewBox="0 {top:.0f} {_W} {height:.0f}" role="img" '
        f'aria-label="Callers and callees of {escape(center)}">'
        f"{''.join(edges)}{''.join(nodes)}</svg>"
    )


## @brief Spread a ring's members over an arc, folding the overflow into one node.
## @param members (name, href) pairs.
## @param cap The most drawn before folding.
## @param centre The arc's centre angle.
## @param span The arc's width.
## @return ((name, href), angle) pairs; a fold is ("+N more", "").
## @version 1
## @dg_internal
def _arc(
    members: list[tuple[str, str]], cap: int, centre: float, span: float
) -> list[tuple[tuple[str, str], float]]:
    """@brief Place on an arc. @return Placements."""
    shown = list(members[:cap])
    if len(members) > cap:
        shown.append((f"+{len(members) - cap} more", ""))
    n = len(shown)
    return [
        (m, centre + (0.0 if n == 1 else (i / (n - 1) - 0.5) * span)) for i, m in enumerate(shown)
    ]


## @brief One node: a dot and its label, linked when it has a section.
## @param x Centre x.
## @param y Centre y.
## @param name The label.
## @param href The section link, or "".
## @param cls Classes.
## @return SVG.
## @version 1
## @dg_internal
def _node(x: float, y: float, name: str, href: str, cls: str) -> str:
    """@brief Node. @return SVG."""
    fold = " fold" if name.startswith("+") and name.endswith(" more") else ""
    anchor_side = "end" if "caller" in cls else "start"
    if "center" in cls:
        anchor_side = "middle"
    dx = -9 if anchor_side == "end" else (9 if anchor_side == "start" else 0)
    dy = -14 if anchor_side == "middle" else 4
    label = (
        f'<circle cx="{x:.0f}" cy="{y:.0f}" r="{9 if "center" in cls else 5}"/>'
        f'<text x="{x + dx:.0f}" y="{y + dy:.0f}" text-anchor="{anchor_side}">{escape(name)}</text>'
    )
    inner = f'<a href="{escape(href)}">{label}</a>' if href else label
    return f'<g class="node {cls}{fold}">{inner}</g>'


## @brief One edge.
## @param x1 From x.
## @param y1 From y.
## @param x2 To x.
## @param y2 To y.
## @param cls Classes.
## @return SVG.
## @version 1
## @dg_internal
def _edge(x1: float, y1: float, x2: float, y2: float, cls: str) -> str:
    """@brief Edge. @return SVG."""
    return f'<line class="edge {cls}" x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"/>'


## @brief A definition's body, bundled from the file, cut at `_BODY_LINES` with the cut said.
## @param repo_root The repository.
## @param d The definition.
## @return HTML ("" when the file cannot be read or the extent is unknown).
## v2: the extent read and checked by `_lines`, shared with the test block.
## @version 2
## @dg_internal
def _body(repo_root: Path, d: Definition) -> str:
    """END 0 IS EXTENT UNKNOWN, never "covers nothing": no body is bundled rather than a guess.
    A STALE EXTENT IS SAID: when the recorded lines no longer name the function (the file changed
    after the index was built), the section says so instead of bundling someone else's code.

    @brief Body.
    @return HTML.
    """
    lines = _lines(repo_root, d)
    if lines is None:
        return ""
    if not lines:
        return (
            '<p class="not-measured">The index is older than this file: the lines it records '
            "no longer hold this function. Refresh the index to bundle its body.</p>"
        )
    body = lines[:_BODY_LINES]
    more = d.end - d.start + 1 - len(body)
    note = f'<p class="none">{more} more lines, not shown</p>' if more > 0 else ""
    return f'<pre class="body">{escape(chr(10).join(body))}</pre>{note}'


## @brief A definition's lines: None when unknown or unreadable, [] when stale.
## @param repo_root The repository.
## @param d The definition.
## @return Lines, [] or None.
## @version 1
## @dg_internal
def _lines(repo_root: Path, d: Definition) -> list[str] | None:
    """THE RECORDED EXTENT MUST STILL NAME THE FUNCTION in its first lines, else the file changed
    after the index was built and the lines are someone else's.

    @brief Read the extent.
    @return Lines.
    """
    if not d.start or not d.end or d.end < d.start:
        return None
    try:
        lines = (repo_root / d.file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    body = lines[d.start - 1 : d.end]
    if not any(re.search(rf"\b{re.escape(d.name)}\b", line) for line in body[:4]):
        return []
    return body
