# SPDX-License-Identifier: MIT
"""The wiki's system map (round 3, P1c): `graph.build_graph` drawn as one inline SVG.

Owner 2026-11-15: "a core system block diagram that cross-talks through the wiki", topography "at
several layers". Two zoom levels share one drawing:

  * CONTAINER — a box per component (callers above callees, the graph's layout) and an arrow per
    link, its width growing with the number of calls;
  * CODE — every function as a point inside its box (tint only, no edges).

LENSES re-tint the same drawing and are switched by a class on the block, so nothing is
recomputed in the browser: requirements (a tier bar per box), tests (calls from test code), and —
only when their sources exist — concurrency (threads) and change (functions in the last impact
report). A lens whose source is absent has no button.

Every box opens the site's shared modal: its files, the requirements it implements (each linked to
its row on the requirements page), the flows passing through it and its threads.

@brief Render the system map page.
@version 1
"""

from __future__ import annotations

import math
from html import escape
from pathlib import Path
from typing import Any

from .htmltable import tag
from .modal import modal_template

## Tier order of the requirement bar, worst last so a gap reads at the right edge.
_TIERS = ("PASS", "NOT_RUN", "TARGET", "GAP", "MISSING")
_MARGIN = 24
## The longest component name drawn in a box before it is shortened.
_NAME_CHARS = 26

## {flow page: (title, files it passes through)}.
Flows = dict[str, tuple[str, set[str]]]


## @brief The map block: controls, the SVG and one modal template per box.
## @param graph `build_graph`'s output.
## @param flows {flow page: (title, files)}.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-021
def map_html(graph: dict[str, Any], flows: Flows) -> str:
    """@brief Draw the map. @return HTML."""
    comps = graph["components"]
    keys = {c["id"]: f"comp-{i}" for i, c in enumerate(comps)}
    by_id = {c["id"]: c for c in comps}
    ports = _ports(graph["links"], by_id)
    width = max((c["x"] + c["w"] for c in comps), default=0) + 2 * _MARGIN
    height = max((c["y"] + c["h"] for c in comps), default=0) + 2 * _MARGIN
    svg = [
        f'<svg class="map" xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="System map">',
        f'<g transform="translate({_MARGIN},{_MARGIN})">',
        '<defs><marker id="map-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="9" '
        'markerHeight="9" markerUnits="userSpaceOnUse" orient="auto-start-reverse">'
        '<path d="M0 0L10 5L0 10z"/></marker></defs>',
        *(_link(link, by_id, ports) for link in graph["links"]),
        *(_box(c, keys[c["id"]]) for c in comps),
        '<g class="cloud">',
        *(_point(p) for p in graph["symbols"]),
        "</g></g></svg>",
    ]
    templates = "".join(modal_template(keys[c["id"]], c["id"], _box_body(c, flows)) for c in comps)
    return (
        f'<div class="map-block" data-lens-current="requirements" data-level="container">'
        f'{_controls(comps)}<div class="map-wrap" data-pz>{"".join(svg)}</div>{templates}</div>'
    )


## @brief Write the map page.
## @param graph The graph.
## @param flows {flow page: (title, files)}.
## @param source The Sphinx source directory.
## @return The page name, or "" when the graph has no component.
## @version 1
## @req REQ-DDB-WIKI-021
def map_page(graph: dict[str, Any], flows: Flows, source: Path) -> str:
    """@brief Write map.md. @return Page name."""
    if not graph["components"]:
        return ""
    lead = (
        "The system as the index sees it: a box per component, callers above callees, an arrow "
        "per dependency (wider = more calls). Switch the lens to re-tint it, switch to Code to "
        "see every function as a point, and click a box for its files, requirements and flows."
    )
    text = ["# Map", "", lead, "", "```{raw} html", map_html(graph, flows), "```", ""]
    (Path(source) / "map.md").write_text("\n".join(text), encoding="utf-8")
    return "map"


## @brief The level and lens buttons; a lens appears only when its source exists.
## @param comps The components.
## @return HTML.
## @version 1
## @dg_internal
def _controls(comps: list[dict[str, Any]]) -> str:
    """THE LENS SET IS READ FROM THE DATA: `tested_calls` exists only when test code was split
    out, `threads` only where a thread runs, `changed` only with an impact report.

    @brief Controls.
    @return HTML.
    """
    lenses = ["requirements"]
    if any("tested_calls" in c for c in comps):
        lenses.append("tests")
    if any(c.get("threads") for c in comps):
        lenses.append("concurrency")
    if any("changed" in c for c in comps):
        lenses.append("change")
    lens = "".join(
        f'<button type="button" data-lens="{n}" aria-pressed="{str(i == 0).lower()}">{n}</button>'
        for i, n in enumerate(lenses)
    )
    level = "".join(
        f'<button type="button" data-level-set="{n}" aria-pressed="{str(i == 0).lower()}">'
        f"{label}</button>"
        for i, (n, label) in enumerate((("container", "Components"), ("code", "Code")))
    )
    return (
        f'<div class="map-controls"><span class="ctl-label">Zoom</span>{level}'
        f'<span class="ctl-label">Lens</span>{lens}</div>'
    )


## @brief One component box with every lens's overlay.
## @param c The component.
## @param key Its modal key.
## @return SVG.
## @version 1
## @dg_internal
def _box(c: dict[str, Any], key: str) -> str:
    """@brief Draw a box. @return SVG."""
    x, y, w, h = c["x"], c["y"], c["w"], c["h"]
    name = c["id"] if len(c["id"]) <= _NAME_CHARS else "…" + c["id"][-(_NAME_CHARS - 1) :]
    attrs = f' data-changed="{c["changed"]}"' if "changed" in c else ""
    tested = " untested" if c.get("tested_calls") == 0 else ""
    return (
        f'<g class="comp{tested}" data-comp="{escape(c["id"])}" data-modal="{key}"{attrs} '
        f'tabindex="0" role="button" aria-label="{escape(c["id"])}">'
        f"<title>{escape(c['id'])}</title>"
        f'<rect class="box" x="{x}" y="{y}" width="{w}" height="{h}" rx="10"/>'
        f'<text class="name" x="{x + 12}" y="{y + 24}">{escape(name)}</text>'
        f'<text class="sub" x="{x + 12}" y="{y + 44}">{c["functions"]} functions · '
        f"{c['files']} files</text>"
        f"{_req_bar(c)}{_lens_text(c)}</g>"
    )


## @brief The requirements lens: a tier bar along the box's foot.
## @param c The component.
## @return SVG.
## @version 1
## @dg_internal
def _req_bar(c: dict[str, Any]) -> str:
    """@brief Tier bar. @return SVG."""
    tiers = c.get("requirements") or {}
    total = sum(tiers.values())
    x, y, w = c["x"] + 12, c["y"] + c["h"] - 24, c["w"] - 24
    if not total:
        return (
            f'<g class="lens lens-requirements"><text class="sub" x="{x}" y="{y + 10}">'
            "no requirement implemented here</text></g>"
        )
    parts, at = [], float(x)
    for tier in _TIERS:
        n = tiers.get(tier, 0)
        if n:
            seg = w * n / total
            parts.append(
                f'<rect class="c-{tier}" x="{at:.1f}" y="{y}" width="{seg:.1f}" height="10">'
                f"<title>{tier} {n}</title></rect>"
            )
            at += seg
    label = f'<text class="sub" x="{x}" y="{y - 4}">{total} requirements</text>'
    return f'<g class="lens lens-requirements">{label}{"".join(parts)}</g>'


## @brief The tests, concurrency and change lenses' text lines.
## @param c The component.
## @return SVG.
## @version 1
## @dg_internal
def _lens_text(c: dict[str, Any]) -> str:
    """@brief Lens lines. @return SVG."""
    x, y = c["x"] + 12, c["y"] + c["h"] - 14
    out = []
    if "tested_calls" in c:
        out.append(("tests", f"{c['tested_calls']} calls from tests"))
    if c.get("threads"):
        out.append(("concurrency", "threads: " + ", ".join(c["threads"])))
    if "changed" in c:
        out.append(("change", f"{c['changed']} functions changed"))
    return "".join(
        f'<g class="lens lens-{lens}"><text class="sub" x="{x}" y="{y}">{escape(t)}</text></g>'
        for lens, t in out
    )


## @brief Where each link leaves and enters its boxes: spread along the edge, ordered by the
## other end's position, so arrows fan out instead of meeting at one point.
## @param links The links.
## @param comps {id: component}.
## @return {(from, to): (x offset at the caller, x offset at the callee)}.
## @version 1
## @dg_internal
def _ports(
    links: list[dict[str, Any]], comps: dict[str, dict[str, Any]]
) -> dict[tuple[str, str], tuple[float, float]]:
    """@brief Spread attachment points. @return Offsets."""
    outs: dict[str, list[tuple[float, str]]] = {}
    ins: dict[str, list[tuple[float, str]]] = {}
    for link in links:
        a, b = comps.get(link["from"]), comps.get(link["to"])
        if a is None or b is None:
            continue
        outs.setdefault(a["id"], []).append((b["x"], b["id"]))
        ins.setdefault(b["id"], []).append((a["x"], a["id"]))
    at_out = {
        (cid, o): _spread(i, len(v), comps[cid]["w"])
        for cid, v in outs.items()
        for i, (_x, o) in enumerate(sorted(v))
    }
    at_in = {
        (cid, o): _spread(i, len(v), comps[cid]["w"])
        for cid, v in ins.items()
        for i, (_x, o) in enumerate(sorted(v))
    }
    return {
        (link["from"], link["to"]): (
            at_out.get((link["from"], link["to"]), 0.0),
            at_in.get((link["to"], link["from"]), 0.0),
        )
        for link in links
    }


## @brief The i-th of n points spread over the middle 70% of an edge, as an offset from centre.
## @param i Index.
## @param n Count.
## @param width Edge width.
## @return Offset.
## @version 1
## @dg_internal
def _spread(i: int, n: int, width: float) -> float:
    """@brief Spread. @return Offset."""
    return 0.0 if n < 2 else (i / (n - 1) - 0.5) * width * 0.7


## @brief An arrow between two boxes, its width growing with the calls.
## @param link The link.
## @param comps {id: component}.
## @param ports Attachment offsets.
## @return SVG.
## @version 1
## @dg_internal
def _link(
    link: dict[str, Any],
    comps: dict[str, dict[str, Any]],
    ports: dict[tuple[str, str], tuple[float, float]],
) -> str:
    """FOOT OF THE CALLER TO HEAD OF THE CALLEE; an upward call (a cycle the layout broke) runs
    head to foot, so it still reads as a call and not as the layout's direction.

    @brief Draw a link.
    @return SVG.
    """
    a, b = comps.get(link["from"]), comps.get(link["to"])
    if a is None or b is None:
        return ""
    down = b["y"] > a["y"]
    off_a, off_b = ports.get((link["from"], link["to"]), (0.0, 0.0))
    x1, y1 = a["x"] + a["w"] / 2 + off_a, a["y"] + (a["h"] if down else 0)
    x2, y2 = b["x"] + b["w"] / 2 + off_b, b["y"] + (0 if down else b["h"])
    bend = (y2 - y1) / 2 if down else -60
    width = 1 + math.log2(1 + link.get("calls", 0))
    what = f"{link['from']} → {link['to']}: {link.get('calls', 0)} calls"
    if link.get("keys"):
        what += f", {link['keys']} shared keys"
    return (
        f'<path class="link" data-from="{escape(link["from"])}" data-to="{escape(link["to"])}" '
        f'd="M{x1:.0f} {y1:.0f}C{x1:.0f} {y1 + bend:.0f} {x2:.0f} {y2 - bend:.0f} {x2:.0f} '
        f'{y2:.0f}" stroke-width="{width:.1f}" marker-end="url(#map-arrow)">'
        f"<title>{escape(what)}</title></path>"
    )


## @brief One function of the point cloud.
## @param p The point.
## @return SVG.
## @version 1
## @dg_internal
def _point(p: dict[str, Any]) -> str:
    """@brief Draw a point. @return SVG."""
    cls = "pt"
    if p.get("tier"):
        cls += f" c-{p['tier']} req"
    if p.get("changed"):
        cls += " chg"
    return (
        f'<circle class="{cls}" cx="{p["x"]:.1f}" cy="{p["y"]:.1f}" r="2.4">'
        f"<title>{escape(p['name'])} — {escape(p['file'])}</title></circle>"
    )


## @brief A box's modal: files, requirements, flows, threads.
## @param c The component.
## @param flows {flow page: (title, files)}.
## @return HTML.
## @version 1
## @dg_internal
def _box_body(c: dict[str, Any], flows: Flows) -> str:
    """@brief Modal body. @return HTML."""
    paths = set(c.get("paths") or ())
    reqs = "".join(
        f'<li><a href="requirements.html#{escape(rid)}">{escape(rid)}</a> {tag(tier)}</li>'
        for rid, tier in sorted(c.get("req_ids") or [])
    )
    through = "".join(
        f'<li><a href="{escape(page)}.html">{_title(title)}</a></li>'
        for page, (title, files) in sorted(flows.items())
        if files & paths
    )
    files = "".join(f"<li><code>{escape(p)}</code></li>" for p in sorted(paths))
    sections = [
        ("Requirements implemented here", reqs),
        ("Flows through it", through),
        ("Threads", "".join(f"<li>{escape(t)}</li>" for t in c.get("threads") or [])),
        (f"Files ({len(paths)})", files),
    ]
    return "".join(
        f'<h4>{h}</h4><ul class="modal-list">{body}</ul>' for h, body in sections if body
    )


## @brief A flow title (Markdown with inline code) as HTML.
## @param title The title.
## @return HTML.
## @version 1
## @dg_internal
def _title(title: str) -> str:
    """@brief Inline code spans become <code>. @return HTML."""
    parts = escape(title).split("`")
    return "".join(f"<code>{s}</code>" if i % 2 else s for i, s in enumerate(parts))


## @brief The sidebar's block diagram: every component as a small box linked to its map modal.
## @param graph The graph.
## @param width The drawing's width in CSS pixels.
## @return SVG, with `@MAP@` where the page-relative path to map.html goes; "" without components.
## @version 1
## @req REQ-DDB-WIKI-021
def minimap_svg(graph: dict[str, Any], width: int = 220) -> str:
    """ONE DRAWING FOR EVERY PAGE: the page lights its own components with a CSS rule on
    `[data-comp]`, so the markup is the same everywhere and its size does not grow with the page.

    @brief Draw the minimap.
    @return SVG.
    """
    comps = graph["components"]
    if not comps:
        return ""
    full_w = max(c["x"] + c["w"] for c in comps)
    full_h = max(c["y"] + c["h"] for c in comps)
    scale = width / full_w
    by_id = {c["id"]: c for c in comps}
    lines = []
    for link in graph["links"]:
        a, b = by_id.get(link["from"]), by_id.get(link["to"])
        if a and b:
            lines.append(
                f'<line x1="{(a["x"] + a["w"] / 2) * scale:.1f}" y1="{(a["y"] + a["h"]) * scale:.1f}" '
                f'x2="{(b["x"] + b["w"] / 2) * scale:.1f}" y2="{b["y"] * scale:.1f}"/>'
            )
    boxes = [
        f'<a href="@MAP@#m=comp-{i}"><rect data-comp="{escape(c["id"])}" x="{c["x"] * scale:.1f}" '
        f'y="{c["y"] * scale:.1f}" width="{c["w"] * scale:.1f}" height="{c["h"] * scale:.1f}" '
        f'rx="3"><title>{escape(c["id"])}</title></rect></a>'
        for i, c in enumerate(comps)
    ]
    height = full_h * scale
    return (
        f'<svg class="minimap" xmlns="http://www.w3.org/2000/svg" width="{width}" '
        f'height="{height:.0f}" viewBox="0 0 {width} {height:.0f}" role="img" '
        f'aria-label="System map">{"".join(lines)}{"".join(boxes)}</svg>'
    )
