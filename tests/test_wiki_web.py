# SPDX-License-Identifier: MIT
"""The repository web: one zoomable, walkable view of every function (round 4, R3).

OWNER 2026-11-16: "the spiderweb should be full repo web, zoomable, interactive, and animatable
single viewpoint - different selections simply jump the camera position to the according position,
zooming out past a threshold collapses functions to blocks accordingly". It replaces the box map
and the per-page ego-graphs.

THE LAYOUT IS COMPUTED HERE, in Python, so it is deterministic and testable: one wedge per block
(spokes), functions on rings by call depth from the entry points (the web's threads), files kept
contiguous inside a wedge. The page's script only draws, pans, zooms and moves the camera.

Grounding (references: .claude/tmp/wiki-round4-references.md, to be published with the docs):
overview first, zoom and filter, details on demand (Shneiderman 1996); semantic zoom — what is drawn
changes with scale, not only its size (Perlin & Fox 1993, Pad); smooth zoom-and-pan camera paths
(van Wijk & Nuij 2003); camera animation is for keeping the mental map, not for speed (Bederson &
Boltman 1999) — so it honours `prefers-reduced-motion`; a table view of the same blocks exists for
anyone the canvas does not serve.

@brief Tests for the repository web.
@version 1
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.graph import build_graph
from clew.wiki.web import WEB_JS, web_data, web_html

_FILES = {
    "pkg/__init__.py": "",
    "pkg/api/__init__.py": "",
    "pkg/core/__init__.py": "",
    "pkg/api/handlers.py": (
        "from pkg.core import store\n\n\n"
        "def handle(x):\n"
        '    """Handle a request."""\n'
        "    return store.save(x)\n"
    ),
    "pkg/core/store.py": (
        'from pkg import util\n\n\ndef save(x):\n    """Save."""\n    return util.clean(x)\n'
    ),
    "pkg/util.py": 'def clean(x):\n    """Clean."""\n    return x\n',
    "tests/test_store.py": (
        "from pkg.core.store import save\n\n\n"
        'def test_save():\n    """Covers save."""\n    assert save(1) == 1\n'
    ),
}
_DECLARED = (("API", ("pkg/api/*",)), ("Core", ("pkg/core/*",)))


## @brief The fixture repository, indexed.
## @param tmp_path_factory Pytest's factory.
## @return The index.
## @version 1
@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief Build. @return Index."""
    root = tmp_path_factory.mktemp("web")
    repo = root / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out


def _data(db: Path) -> dict:
    graph = build_graph(db, [], None, _DECLARED, exclude_tests=True)
    return web_data(db, graph)


def test_every_block_is_a_wedge_and_wedges_do_not_overlap(db: Path) -> None:
    """@brief Spokes: one angular range per block, in declared order, disjoint, inside one turn."""
    blocks = _data(db)["blocks"]
    assert [b["id"] for b in blocks] == ["API", "Core"]
    spans = [(b["a0"], b["a1"]) for b in blocks]
    assert all(0 <= a0 < a1 <= 2 * math.pi + 1e-9 for a0, a1 in spans)
    assert all(spans[i][1] <= spans[i + 1][0] for i in range(len(spans) - 1))


def test_functions_sit_in_their_block_on_rings_by_call_depth(db: Path) -> None:
    """THE WEB'S THREADS: an entry point (no non-test caller) is ring 0 at the centre; each call
    takes its callee one ring out. Test code is not drawn — it is a lens, not a block.

    @brief Rings by depth; every point inside its wedge.
    """
    data = _data(db)
    nodes = {n["name"]: n for n in data["nodes"]}
    assert "test_save" not in nodes
    assert (nodes["handle"]["ring"], nodes["save"]["ring"], nodes["clean"]["ring"]) == (0, 1, 2)
    blocks = {b["id"]: b for b in data["blocks"]}
    for n in data["nodes"]:
        block = data["blocks"][n["block"]]
        angle = math.atan2(n["y"], n["x"]) % (2 * math.pi)
        assert block["a0"] - 1e-6 <= angle <= block["a1"] + 1e-6, n["name"]
    assert nodes["clean"]["block"] == [b["id"] for b in data["blocks"]].index("Core")
    assert blocks["Core"]["inferred_files"] == ["pkg/util.py"]


def test_edges_and_block_links_are_carried_for_walking_and_the_overview(db: Path) -> None:
    """@brief Function edges by node index (walking source); block links weighted (overview)."""
    data = _data(db)
    names = [n["name"] for n in data["nodes"]]
    edges = {(names[a], names[b]) for a, b in data["edges"]}
    assert ("handle", "save") in edges and ("save", "clean") in edges
    assert {"from": "API", "to": "Core", "calls": 1} in data["links"]


def test_the_page_embeds_the_data_a_canvas_and_a_table_view(db: Path) -> None:
    """@brief Canvas + inline JSON + the same blocks as a table; web.js local and budgeted."""
    html = web_html(_data(db))
    assert "<canvas" in html and 'class="web"' in html
    payload = re.search(r'<script type="application/json" id="web-data">(.*?)</script>', html, re.S)
    assert payload and json.loads(payload.group(1))["blocks"]
    assert "<table" in html and "Core" in html.split("<table", 1)[1]
    assert "http://" not in WEB_JS and "https://" not in WEB_JS
    assert len(WEB_JS.encode()) <= 16384
    assert "prefers-reduced-motion" in WEB_JS


def test_the_change_lens_exists_only_with_an_impact_report(db: Path) -> None:
    """NO IMPACT REPORT, NO CHANGE LENS (ported from the box map, which the web replaced): with a
    report the lens exists and a changed function carries `changed`.

    @brief Lens options follow their sources.
    """
    plain = build_graph(db, [], None, _DECLARED, exclude_tests=True)
    assert "Change</option>" not in web_html(web_data(db, plain))
    impact = [{"req_id": "R-1", "functions": [{"name": "save", "file": "pkg/core/store.py"}]}]
    measured = build_graph(db, [], impact, _DECLARED, exclude_tests=True)
    data = web_data(db, measured)
    assert "Change</option>" in web_html(data)
    assert {n["name"]: n.get("changed") for n in data["nodes"]}["save"] is True


def test_a_flow_is_played_by_its_functions_in_call_order(db: Path) -> None:
    """OWNER 2026-11-15: "an animated core flow traced across the map". A flow's steps are its
    functions in call order (caller, then callee, each once in a row); a step whose function is
    not drawn is skipped, never invented.

    @brief Flow steps on the web.
    """
    from types import SimpleNamespace

    from clew.wiki.web import _flow

    data = _data(db)
    slot = {(n["name"], n["file"]): i for i, n in enumerate(data["nodes"])}
    page = SimpleNamespace(
        name="flow-handle",
        title="Handle",
        calls=(("handle", "save"), ("save", "clean"), ("clean", "nowhere")),
        hops=(
            ("pkg/api/handlers.py", "pkg/core/store.py"),
            ("pkg/core/store.py", "pkg/util.py"),
            ("pkg/util.py", "elsewhere.py"),
        ),
    )
    steps = [data["nodes"][i]["name"] for i in _flow(page, slot)["steps"]]
    assert steps == ["handle", "save", "clean"]


def test_each_function_carries_the_requirements_it_implements(db: Path) -> None:
    """OWNER (round 5, P5.4): the requirement overlay. A requirement page's "Show on the map"
    opens `map.html#req=<id>`, which lights that requirement's implementing functions. The map
    data carries ONE table of ids and, per function, indices into it: a site of thousands of
    functions does not repeat each id string on every node it implements.

    @brief P5.4: per-function requirement ids, compact, and the `#req=` hash.
    """
    from types import SimpleNamespace

    rows = [
        SimpleNamespace(
            req_id="R-2", tier="PASS", implementer_sites=(("save", "pkg/core/store.py", 4),)
        ),
        SimpleNamespace(
            req_id="R-1",
            tier="UNTESTED",
            implementer_sites=(("save", "pkg/core/store.py", 4), ("clean", "pkg/util.py", 1)),
        ),
    ]
    data = web_data(db, build_graph(db, rows, None, _DECLARED, exclude_tests=True))
    assert data["req_ids"] == ["R-1", "R-2"]
    by_name = {n["name"]: n.get("r") for n in data["nodes"]}
    assert by_name["save"] == [0, 1] and by_name["clean"] == [0] and by_name["handle"] is None
    assert "req=" in WEB_JS, "the map reads the overlay's hash"


def test_source_and_dossier_open_in_the_page_modal() -> None:
    """W-2 (owner review 2026-11-22): "Source and dossier link on a map item should open a modal,
    not another page". The link names a `frame-<node>` modal key; web.js registers that builder on
    the page's one modal, which frames the symbol section (a frame works over file://, where a fetch
    is refused, and keeps one source for the section's content).

    @brief The map's symbol link opens a framed modal.
    """
    assert 'data-modal=\\"frame-' in WEB_JS or 'data-modal="frame-' in WEB_JS
    assert "register('frame-'" in WEB_JS and "iframe" in WEB_JS


def test_a_map_node_says_what_its_function_does() -> None:
    """X-4 (owner review 2, 2026-11-22): "I cant derive what each function is doing at a glance"
    from the map's pop-out. Each node carries its function's brief (the index's own plain-text
    summary), and the panel prints it under the name.

    @brief Map nodes carry briefs; the panel shows them.
    """
    from clew.wiki.web import _with_briefs

    nodes = [{"name": "derive_flow", "file": "clew/wiki/flow.py"}, {"name": "x", "file": "a.py"}]
    _with_briefs(
        nodes, {("derive_flow", "clew/wiki/flow.py"): "Derive the flow from an entry function."}
    )
    assert (
        nodes[0]["brief"] == "Derive the flow from an entry function." and "brief" not in nodes[1]
    )
    assert 'class="web-brief"' in WEB_JS and "n.brief" in WEB_JS


def test_zoomed_out_blocks_and_a_legend_show_the_lens() -> None:
    """OWNER MAP NOTES (2026-11-22): change impact → map showed the changed dots but nothing zoomed
    out, and there was no colour legend. Owner Q/A: a folded block is drawn as the active lens's
    status pie (sub-arcs in proportion), and a legend names each colour with its count. One
    category function (`cat`) serves the dots, the pies and the legend, so they cannot disagree.

    @brief Wedge pies and the lens legend.
    """
    assert (
        "function cat(n)" in WEB_JS
        and "function pies()" in WEB_JS
        and "function legend()" in WEB_JS
    )
    assert "data-web-legend" in web_html({"nodes": [], "blocks": [], "links": []})


def test_the_map_is_the_home_page(tmp_path) -> None:
    """Owner Q/A 2026-11-22: "the map is home". The map's block is written ONCE, as
    `_map_block.html`, and both map.md and the home page include it by `{raw} html :file:`.

    @brief The home page includes the map block.
    """
    from clew.wiki.web import MAP_BLOCK

    assert MAP_BLOCK == "_map_block.html"


def test_a_lens_link_opens_on_the_whole_system_and_a_rare_value_stays_visible() -> None:
    """Owner map notes: arriving from Change impact showed "the individual dots, but doesnt show the
    larger view zoomed out". A lens link (`#lens=change`) opens on the whole system, and a category a
    block holds is at least a sliver of its wedge (2 changed of 3,096 would otherwise vanish); the
    legend keeps the exact counts.

    @brief Lens links fit the system; minority slices have a floor.
    """
    assert "lens=l;lensSel.value=l;fit();" in WEB_JS
    assert "MINF" in WEB_JS
