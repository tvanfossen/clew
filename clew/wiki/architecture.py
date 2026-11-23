# SPDX-License-Identifier: MIT
"""The Architecture tab: C4's four levels, derived from the index (round 5, P5.6).

OWNER (round 5): Architecture is a new tab using C4 levels — S. Brown's C4 model (c4model.com), a
practitioner framework, cited as such. Owner Q/A 2026-11-20 approved the derivation; every level is
drawn from facts the index already has:

| level | drawn from |
|---|---|
| L1 Context | the repository as one system; actors from its entry kinds; vendor areas as external systems |
| L2 Containers | each separately runnable entry point (console script, main) — derived, and said to be |
| L3 Components | the map's first-party blocks and their call links; declared and inferred drawn apart |
| L4 Code | the map and the symbol pages — C4's own advice is that this level is generated |

WHAT CANNOT BE DERIVED IS ABSENT AND SAID: data stores, deployment units, the protocols on a link.
A repository's own declaration of them is later work; nothing here guesses one. Inferred blocks are
drawn distinct from declared ones because automated recovery is often wrong against expert ground
truth (Garcia, Ivkovic & Medvidovic, ASE 2013).

Static SVG with the shared pan/zoom wrapper: no script of its own.

@brief The C4 architecture page.
@version 1
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path

## Who uses an entry of each kind, in the words the page shows (L1's actors).
_ACTOR = {"script": "command-line user", "main": "program launcher"}
_W, _H, _GAP = 190, 52, 26


## @brief One entry point, as the architecture levels read it.
## @version 1
@dataclass(frozen=True)
class Entry:
    """@brief Kind (`script`, `main`, `thread`), function, file, label, and its flow page or None."""

    kind: str
    function: str
    file: str
    label: str
    flow: str | None
    ## `tooling` when the `tooling` globs classify it: listed under L2, never drawn as a container.
    role: str = ""

    ## @brief What a box shows: a script's name, else the file a `main` is in.
    ## @return The name.
    ## v2: UX review E-19
    ## @version 2
    ## @utility
    def shown(self) -> str:
        """FOUND BY LOOKING: a row of boxes all reading `main` named nothing. @brief Name."""
        ## E-19 (UX review, owner Q/A 2026-11-22): a `main` shows its file's PATH — `main.py` alone
        ## named nothing beside console-script names.
        return self.label or (self.file if self.function == "main" else self.function)


## The content column a diagram fits in without panning (px).
_COLUMN_W, _COLUMN_H = 1000, 640


## @brief Write the Architecture page.
## @param title The repository's title (the system's name).
## @param graph The block graph (`components`, `links`).
## @param entries The entry points.
## @param source The Sphinx source directory.
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-046
def architecture_page(title: str, graph: dict, entries: list[Entry], source: Path) -> str:
    """@brief Write architecture.md. @return Page name."""
    lines = [
        "# Architecture",
        "",
        "The system at C4's four levels (S. Brown's C4 model), each drawn from the index. Anything "
        "C4 asks for that the index cannot show is left out and named as missing, not guessed.",
        "",
        "```{raw} html",
        architecture_html(title, graph, entries),
        "```",
        "",
    ]
    (Path(source) / "architecture.md").write_text("\n".join(lines), encoding="utf-8")
    return "architecture"


## @brief The four levels' HTML.
## @param title The system's name.
## @param graph The block graph.
## @param entries The entry points.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-046
def architecture_html(title: str, graph: dict, entries: list[Entry]) -> str:
    """@brief L1 → L4, a section each. @return HTML."""
    comps = graph.get("components") or []
    first = [c for c in comps if not c.get("vendor")]
    vendor = [c for c in comps if c.get("vendor")]
    return "".join(
        (
            _section(1, "Context", _context(title, entries, vendor)),
            _section(2, "Containers", _containers(title, entries)),
            _section(3, "Components", _components(first, graph.get("links") or [])),
            _section(4, "Code", _code()),
        )
    )


## @brief One level's section.
## @param n The level.
## @param name Its C4 name.
## @param body Its body.
## @return HTML.
## @version 1
## @utility
def _section(n: int, name: str, body: str) -> str:
    """@brief Section. @return HTML."""
    return f'<section class="c4" id="c4-l{n}"><h2>L{n} · {name}</h2>{body}</section>'


## @brief L1: the system, its actors and its external systems.
## @param title The system's name.
## @param entries The entry points.
## @param vendor The vendor areas.
## @return HTML.
## @version 1
## @utility
def _context(title: str, entries: list[Entry], vendor: list[dict]) -> str:
    """ACTORS FROM ENTRY KINDS: a console script is used from a command line, a `main` is launched
    as a program. A thread is the system's own, not an actor.

    @brief Context diagram.
    @return HTML.
    """
    actors = sorted({_ACTOR[e.kind] for e in entries if e.kind in _ACTOR})
    rows = max(len(actors), len(vendor), 1)
    height = rows * (_H + _GAP) + _GAP
    mid = height / 2 - _H / 2
    sx = _W + 2 * _GAP + 60
    parts = [_box(sx, mid, title, "c4-system")]
    for i, actor in enumerate(actors):
        y = _GAP + i * (_H + _GAP)
        parts += [_line(_W, y + _H / 2, sx, mid + _H / 2), _box(0, y, actor, "c4-actor")]
    ex = sx + _W + 2 * _GAP + 60
    for i, area in enumerate(vendor):
        y = _GAP + i * (_H + _GAP)
        parts += [_line(sx + _W, mid + _H / 2, ex, y + _H / 2), _box(ex, y, area["id"], "c4-ext")]
    note = (
        ""
        if vendor
        else '<p class="none">No vendored area: no external system is in the index.</p>'
    )
    return _svg(ex + _W + 10, height, parts, f"context of {title}") + note


## @brief L2: the runnable entry points, inside the system boundary.
## @param title The system's name.
## @param entries The entry points.
## @return HTML.
## @version 1
## @utility
def _containers(title: str, entries: list[Entry]) -> str:
    """@brief Container diagram, with what it cannot show said. @return HTML."""
    runnable = [e for e in entries if e.kind in _ACTOR and e.role != "tooling"]
    tooling = [e for e in entries if e.kind in _ACTOR and e.role == "tooling"]
    w = _fit([e.shown() for e in runnable] + [e.file for e in runnable])
    cols = 3
    rows = max(1, -(-len(runnable) // cols))
    width = cols * (w + _GAP) + _GAP
    height = rows * (_H + _GAP) + _GAP + 24
    parts = [
        f'<rect class="c4-boundary" x="4" y="4" width="{width - 8}" height="{height - 8}" rx="10"/>'
        f'<text class="c4-boundary-name" x="16" y="22">{escape(title)}</text>'
    ]
    for i, e in enumerate(runnable):
        x, y = _GAP + (i % cols) * (w + _GAP), 34 + (i // cols) * (_H + _GAP)
        parts.append(_box(x, y, e.shown(), "c4-container", e.flow, e.file, w))
    said = (
        '<p class="note">Containers here are derived from entry points (console scripts and '
        "mains), each separately runnable. The index does not show data stores, deployment units "
        "or the protocols between containers, so none is drawn.</p>"
    )
    body = (
        _svg(width, height, parts, f"containers of {title}")
        if runnable
        else ('<p class="none">No runnable entry point was found, so no container is drawn.</p>')
    )
    return body + said + _tooling(tooling)


## @brief The tooling entry points, listed and folded (L2).
## @param tooling Entries the `tooling` globs classify.
## @return HTML, or "" when there are none.
## @version 1
## @utility
def _tooling(tooling: list[Entry]) -> str:
    """THE REPOSITORY'S TOOLING IS NOT A CONTAINER OF THE SYSTEM, but it is not hidden either: it
    is named, under the `tooling` globs that classify it.

    @brief Tooling list.
    @return HTML.
    """
    if not tooling:
        return ""
    n = len(tooling)
    items = "".join(
        f"<li><code>{escape(e.file)}</code></li>" for e in sorted(tooling, key=lambda e: e.file)
    )
    return (
        f'<details class="c4-tooling"><summary>{n} tooling entry point{"s" if n != 1 else ""}, '
        f"not drawn (the <code>tooling</code> globs classify them)</summary><ul>{items}</ul></details>"
    )


## At most this many links drawn strong on L3 (the stronger half); the rest are faint (C-18).
_STRONG = 8


## @brief L3: the first-party blocks, layered by who calls whom, and their directed call links.
## @param comps The first-party components.
## @param links Component links (`from`, `to`, `calls`).
## @return HTML.
## v2: UX review C-18 (owner Q/A 2026-11-22) — the uniform grid with undirected crossing lines
##     became layers (callers above what they call), arrows weighted by calls, the weaker links
##     faint, the key before the diagram.
## @version 2
## @utility
def _components(comps: list[dict], links: list[dict]) -> str:
    """@brief Component diagram: layered, directed. @return HTML."""
    if not comps:
        return '<p class="none">No block was formed, so no component is drawn.</p>'
    w = _fit([c["id"] for c in comps])
    at, width, height = _layered_positions(comps, _layers(comps, links), w)
    parts = [
        '<defs><marker id="c4-arrow" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="7" '
        'markerHeight="7" orient="auto-start-reverse"><path d="M0,0L10,5L0,10z" '
        'class="c4-arrowhead"/></marker></defs>'
    ]
    parts += _links_svg(links, at, w)
    for c in comps:
        kind = "declared" if c.get("declared") else "inferred"
        sub = f"{c.get('functions', 0)} functions · {c.get('files', 0)} files"
        parts.append(_box(*at[c["id"]], c["id"], f"c4-comp {kind}", None, sub, w))
    key = (
        '<p class="note">Callers sit above what they call; an arrow is calls, thicker for more, the '
        f"weaker half faint (at most {_STRONG} drawn strong). Solid: a block the repository declares. "
        "Dashed: a block inferred from coupling, which can be wrong — read it as a hint, not the "
        "architecture.</p>"
    )
    return key + _svg(width, height, parts, "components")


## @brief Each component's layer: its call distance from the blocks nothing calls.
## @param comps The components, in order.
## @param links Component links.
## @return {id: layer from 0}.
## @version 1
## @utility
def _layers(comps: list[dict], links: list[dict]) -> dict[str, int]:
    """SHORTEST, NOT LONGEST: a longest-path layering stacked clew's tightly coupled blocks into
    one column ten deep (found by looking). Breadth-first from the blocks nothing else calls (the
    first block when every block is called) keeps the drawing shallow; a block no root reaches sits
    one layer below the rest.

    @brief Layers.
    @return Map.
    """
    ids = [c["id"] for c in comps]
    out: dict[str, list[str]] = {i: [] for i in ids}
    for link in links:
        if link["from"] in out and link["to"] in out and link["from"] != link["to"]:
            out[link["from"]].append(link["to"])
    called = {b for a in ids for b in out[a]}
    frontier = [i for i in ids if i not in called] or ids[:1]
    layer = dict.fromkeys(frontier, 0)
    while frontier:
        nxt = []
        for a in frontier:
            for b in out[a]:
                if b not in layer:
                    layer[b] = layer[a] + 1
                    nxt.append(b)
        frontier = nxt
    deepest = max(layer.values(), default=-1)
    return {i: layer.get(i, deepest + 1) for i in ids}


## @brief Box positions per layer, each layer centred.
## @param comps The components.
## @param layer Their layers.
## @param w Box width.
## @return (positions, width, height).
## @version 1
## @utility
def _layered_positions(
    comps: list[dict], layer: dict[str, int], w: float
) -> tuple[dict, float, float]:
    """@brief Positions. @return Triple."""
    rows: dict[int, list[str]] = defaultdict(list)
    for c in comps:
        rows[layer[c["id"]]].append(c["id"])
    widest = max(len(r) for r in rows.values())
    width = widest * (w + _GAP) + _GAP
    at = {}
    for depth, ids in rows.items():
        left = (width - len(ids) * (w + _GAP) + _GAP) / 2
        for j, cid in enumerate(ids):
            at[cid] = (left + j * (w + _GAP), _GAP + depth * (_H + 3 * _GAP))
    return at, width, len(rows) * (_H + 3 * _GAP) + _GAP


## @brief Directed links, width by calls, the weaker faint.
## @param links Component links.
## @param at Box positions.
## @param w Box width.
## @return SVG elements.
## @version 1
## @utility
def _links_svg(links: list[dict], at: dict, w: float) -> list[str]:
    """An arrow leaves the caller's bottom edge for the callee's top edge (or the reverse when the
    callee sits higher — a back edge).

    @brief Links.
    @return Elements.
    """
    drawn = [lk for lk in links if lk["from"] in at and lk["to"] in at and lk["from"] != lk["to"]]
    top = max((lk.get("calls", 0) for lk in drawn), default=1) or 1
    strong = {
        id(lk)
        for lk in sorted(drawn, key=lambda lk: -lk.get("calls", 0))[
            : min(_STRONG, -(-len(drawn) // 2))
        ]
    }
    out = []
    for lk in drawn:
        (ax, ay), (bx, by) = at[lk["from"]], at[lk["to"]]
        down = by > ay
        y1, y2 = (ay + _H, by) if down else (ay, by + _H)
        cls = "c4-link" if id(lk) in strong else "c4-link weak"
        sw = 1 + 4 * (lk.get("calls", 0) / top) ** 0.5
        out.append(
            f'<line class="{cls}" data-link="{escape(lk["from"])}→{escape(lk["to"])}" '
            f'x1="{ax + w / 2:.0f}" y1="{y1:.0f}" x2="{bx + w / 2:.0f}" y2="{y2:.0f}" '
            f'style="stroke-width:{sw:.1f}px" marker-end="url(#c4-arrow)"><title>{lk.get("calls", 0)} calls'
            "</title></line>"
        )
    return out


## @brief L4: the generated level — the map and the symbol pages.
## @return HTML.
## @version 1
## @utility
def _code() -> str:
    """@brief Links down. @return HTML."""
    return (
        '<p>Code is the generated level: every function on the <a href="map.html">map</a>, each '
        "linking to its own page with its body, callers, callees and activity diagram.</p>"
    )


## @brief A labelled box, optionally linked, with an optional second line.
## @param x Left.
## @param y Top.
## @param label The name.
## @param cls Its class.
## @param href A page to link, or None.
## @param sub A second, smaller line, or "".
## @param w Its width (`_fit` of the diagram's labels).
## @return SVG.
## @version 2
## @utility
def _box(
    x: float, y: float, label: str, cls: str, href: str | None = None, sub: str = "", w: float = _W
) -> str:
    """@brief Box. @return SVG."""
    text = f'<text x="{x + 12:.0f}" y="{y + (22 if sub else 31):.0f}">{escape(label)}</text>'
    if sub:
        text += f'<text class="c4-sub" x="{x + 12:.0f}" y="{y + 40:.0f}">{escape(sub)}</text>'
    shape = (
        f'<rect class="{cls}" x="{x:.0f}" y="{y:.0f}" width="{w:.0f}" height="{_H}" rx="8"/>{text}'
    )
    return f'<a href="{escape(href)}.html">{shape}</a>' if href else shape


## @brief A box width that fits the longest label: NEVER CUT (found by looking at clew's own L3).
## @param labels The diagram's labels.
## @return Width.
## @version 1
## @utility
def _fit(labels: list[str]) -> float:
    """@brief Longest label at the label font's advance, plus padding. @return Width."""
    return max(_W, max((len(s) for s in labels), default=0) * 7.4 + 28)


## @brief A connector.
## @param x1 Start x.
## @param y1 Start y.
## @param x2 End x.
## @param y2 End y.
## @return SVG.
## @version 1
## @utility
def _line(x1: float, y1: float, x2: float, y2: float) -> str:
    """@brief Line. @return SVG."""
    return f'<line class="c4-rel" x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}"/>'


## @brief An SVG in the shared pan/zoom wrapper.
## @param width Width.
## @param height Height.
## @param parts Its elements.
## @param label Its accessible label.
## @return HTML.
## v2: UX review E-19
## @version 2
## @utility
def _svg(width: float, height: float, parts: list[str], label: str) -> str:
    """E-19 (UX review, owner Q/A 2026-11-22): PAN AND ZOOM ONLY WHERE THERE IS SOMETHING TO PAN — a
    diagram wider or taller than the content column; a small one is drawn as it is.

    @brief Wrapped SVG.
    @return HTML.
    """
    pz = ' class="pz" data-pz' if width > _COLUMN_W or height > _COLUMN_H else ' class="c4-fit"'
    return (
        f'<div{pz}><svg class="c4-diagram" role="img" aria-label="{escape(label)}" '
        f'viewBox="0 0 {width:.0f} {height:.0f}" width="{width:.0f}" height="{height:.0f}">'
        + "".join(parts)
        + "</svg></div>"
    )
