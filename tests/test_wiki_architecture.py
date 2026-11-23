# SPDX-License-Identifier: MIT
"""The Architecture tab: C4's four levels, derived from the index (round 5, P5.6).

OWNER (round 5): Architecture is a new tab using C4 levels. Owner Q/A 2026-11-20 approved the
derivation, everything from facts the index has:

| level | drawn from |
|---|---|
| L1 Context | the repository as one system; actors from its entry kinds; vendor areas as external |
| L2 Containers | each separately runnable entry point, said to be derived from entry points |
| L3 Components | the map's blocks and their links, declared and inferred kept apart |
| L4 Code | links to the map and the symbol pages |

What C4 asks for that cannot be derived — data stores, deployment, link protocols — is ABSENT and
said to be, never guessed. C4 is a practitioner framework (S. Brown, c4model.com), cited as such.

@brief Tests the C4 architecture page.
@version 1
"""

from __future__ import annotations

from clew.wiki.architecture import Entry, architecture_html

_GRAPH = {
    "components": [
        {"id": "API", "declared": True, "functions": 4, "files": 2},
        {"id": "pkg/core", "declared": False, "functions": 9, "files": 3},
        {"id": "vendor/zlib", "vendor": True, "functions": 40, "files": 12},
    ],
    "links": [
        {"from": "API", "to": "pkg/core", "calls": 5},
        {"from": "pkg/core", "to": "vendor/zlib", "calls": 2},
    ],
}
_ENTRIES = [
    Entry("script", "main", "pkg/cli.py", "demo", "flow-main"),
    Entry("main", "run", "tools/run.py", "", None),
    Entry("thread", "worker", "pkg/core/w.py", "", "flow-worker"),
]


def _level(html: str, n: int) -> str:
    """@brief One level's section. @return HTML."""
    return html.split(f'<section class="c4" id="c4-l{n}">', 1)[1].split("</section>", 1)[0]


def test_context_is_the_system_its_actors_and_its_external_systems() -> None:
    """@brief L1: one system box, actors from entry kinds, the vendor area external."""
    l1 = _level(architecture_html("Demo", _GRAPH, _ENTRIES), 1)
    assert ">Demo</text>" in l1
    assert ">command-line user</text>" in l1 and ">program launcher</text>" in l1
    assert ">vendor/zlib</text>" in l1 and 'class="c4-ext"' in l1


def test_containers_are_the_runnable_entry_points_said_to_be_derived() -> None:
    """@brief L2: one container per script / main, linked to its flow; threads are not containers."""
    l2 = _level(architecture_html("Demo", _GRAPH, _ENTRIES), 2)
    assert ">demo</text>" in l2 and ">run</text>" in l2 and ">worker</text>" not in l2
    assert 'href="flow-main.html"' in l2
    assert "derived from entry points" in l2 and "data stores" in l2


def test_components_are_the_blocks_declared_and_inferred_apart() -> None:
    """@brief L3: first-party blocks with their links; inferred drawn distinct; vendor not inside."""
    l3 = _level(architecture_html("Demo", _GRAPH, _ENTRIES), 3)
    assert 'class="c4-comp declared"' in l3 and 'class="c4-comp inferred"' in l3
    assert ">vendor/zlib</text>" not in l3
    assert 'data-link="API→pkg/core"' in l3


def test_code_level_links_down_to_the_map() -> None:
    """@brief L4: generated, so it is the map and the symbol pages."""
    l4 = _level(architecture_html("Demo", _GRAPH, _ENTRIES), 4)
    assert 'href="map.html"' in l4


def test_tooling_entry_points_are_listed_not_drawn_as_containers() -> None:
    """FOUND BY LOOKING (clew's own site): 27 of 30 containers were `main`s under `scripts/` and
    `acceptance/`, burying the three real ones. An entry the `tooling` globs classify is the
    repository's tooling, not a container of the system: listed below, folded, never drawn.

    @brief L2: tooling is listed, not drawn.
    """
    entries = [*_ENTRIES, Entry("main", "main", "scripts/probe.py", "", None, role="tooling")]
    l2 = _level(architecture_html("Demo", _GRAPH, entries), 2)
    svg = l2.split("</svg>", 1)[0]
    assert "scripts/probe.py" not in svg
    assert "1 tooling entry point" in l2 and "scripts/probe.py" in l2


def test_a_main_is_named_by_its_file_not_main() -> None:
    """L2: a `main` is named by its file, never a row of `main`s. SPEC CHANGED (UX review E-19,
    owner Q/A 2026-11-22): by its PATH (`tools/serve.py`) — `main.py` alone named nothing beside
    the console-script names.

    @brief L2: a main is named by its file's path.
    """
    entries = [Entry("main", "main", "tools/serve.py", "", None)]
    l2 = _level(architecture_html("Demo", _GRAPH, entries), 2)
    assert ">tools/serve.py</text>" in l2 and ">main</text>" not in l2


def test_a_long_component_name_is_never_cut() -> None:
    """FOUND BY LOOKING: "Build: concurrency and config layer" overflowed its box. The box is as
    wide as its longest label.

    @brief L3: labels fit their boxes.
    """
    long = "Build: concurrency and config layer, the long one"
    graph = {
        "components": [{"id": long, "declared": True, "functions": 1, "files": 1}],
        "links": [],
    }
    l3 = _level(architecture_html("Demo", graph, []), 3)
    width = float(
        l3.split('class="c4-comp declared"', 1)[1].split('width="', 1)[1].split('"', 1)[0]
    )
    assert width >= len(long) * 7, width


def test_l3_is_layered_by_who_calls_whom_with_directed_weighted_links() -> None:
    """UX review C-18 (owner Q/A 2026-11-22): L3 was a uniform grid with undirected crossing lines
    and its key below. Callers sit above what they call; a link is an arrow, thicker for more
    calls; the weaker links are faint; the key comes first.

    @brief L3 layered layout.
    """
    from clew.wiki.architecture import _components, _layers

    comps = [{"id": x, "functions": 1, "files": 1} for x in ("cli", "wiki", "query", "db")]
    links = [
        {"from": "cli", "to": "wiki", "calls": 9},
        {"from": "wiki", "to": "query", "calls": 4},
        {"from": "query", "to": "db", "calls": 1},
        {"from": "db", "to": "query", "calls": 1},
    ]
    assert _layers(comps, links) == {"cli": 0, "wiki": 1, "query": 2, "db": 3}
    html = _components(comps, links)
    assert 'marker-end="url(#c4-arrow)"' in html and '<marker id="c4-arrow"' in html
    assert html.index('class="note"') < html.index("<svg")
    assert 'class="c4-link weak"' in html
