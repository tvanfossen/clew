# SPDX-License-Identifier: MIT
"""The wiki's system map (round 3, P1c-1): the graph drawn at the Container and Code levels.

Owner 2026-11-15: "consider a core system block diagram that cross-talks through the wiki", and
"topography at several layers". The map draws `graph.build_graph`'s components as boxes (callers
above callees) and the calls between them as weighted arrows; the Code level is the point cloud
inside the boxes. LENSES re-tint the same drawing — requirements by tier, tests, concurrency,
change — and a lens whose source is absent has NO BUTTON (no impact report, no change lens).
Clicking a box opens the shared modal: its files, the requirements it implements (linked to the
requirements page), the flows that pass through it and its threads.

Test code is not a component of the system: it is drawn as the tests lens — how many calls from
test code reach each box — not as boxes on top of everything.

@brief Tests for the map page renderer and the graph's test exclusion.
@version 1
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.graph import build_graph
from clew.wiki.mappage import map_html

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
    "pkg/core/store.py": 'def save(x):\n    """Save."""\n    return x\n',
    "tests/test_store.py": (
        "from pkg.core.store import save\n\n\n"
        "def test_save():\n"
        '    """Covers save."""\n'
        "    assert save(1) == 1\n"
    ),
}


@dataclass(frozen=True)
class _Row:
    req_id: str
    tier: str
    implementer_sites: tuple


## @brief The fixture repository, indexed.
## @param tmp_path_factory Pytest's factory.
## @return The index.
## @version 1
@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief Build. @return Index."""
    root = tmp_path_factory.mktemp("map")
    repo = root / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out


_EVIDENCE = [_Row("R-1", "PASS", (("save", "pkg/core/store.py", 1),))]


def test_test_code_is_a_lens_not_a_box(db: Path) -> None:
    """`exclude_tests` drops test-only components from the layout and counts the calls test code
    makes into each remaining component as `tested_calls`.

    @brief Graph: test exclusion.
    """
    graph = build_graph(db, _EVIDENCE, None, exclude_tests=True)
    comps = {c["id"]: c for c in graph["components"]}
    assert set(comps) == {"pkg/api", "pkg/core"}
    assert comps["pkg/core"]["tested_calls"] == 1 and comps["pkg/api"]["tested_calls"] == 0
    assert all(p["file"].startswith("pkg/") for p in graph["symbols"])
    assert comps["pkg/api"]["y"] == 0 and comps["pkg/core"]["y"] > 0


def test_the_map_draws_boxes_arrows_and_the_point_cloud(db: Path) -> None:
    """@brief Container level: a box per component, a weighted arrow per link; Code level: one
    point per function."""
    graph = build_graph(db, _EVIDENCE, None, exclude_tests=True)
    html = map_html(graph, {})
    assert html.count('class="comp') == 2
    assert 'data-from="pkg/api"' in html and 'data-to="pkg/core"' in html
    assert len(re.findall(r'<circle class="pt', html)) == len(graph["symbols"])
    assert 'viewBox="' in html and "data-pz" in html


def test_lenses_appear_only_with_their_source(db: Path) -> None:
    """NO IMPACT REPORT, NO CHANGE LENS; no threads anywhere, no concurrency lens. With a report,
    the change lens exists and a changed box is marked.

    @brief Lens buttons follow their sources.
    """
    plain = map_html(build_graph(db, _EVIDENCE, None, exclude_tests=True), {})
    lenses = re.findall(r'data-lens="(\w+)"', plain)
    assert lenses == ["requirements", "tests"]
    impact = [{"req_id": "R-1", "functions": [{"name": "save", "file": "pkg/core/store.py"}]}]
    measured = map_html(build_graph(db, _EVIDENCE, impact, exclude_tests=True), {})
    assert "change" in re.findall(r'data-lens="(\w+)"', measured)
    assert 'data-changed="1"' in measured


def test_a_box_opens_its_files_requirements_and_flows(db: Path) -> None:
    """CROSS-TALK: the box's modal links each requirement to its row on the requirements page and
    each flow passing through it to that flow's page.

    @brief Component modal.
    """
    graph = build_graph(db, _EVIDENCE, None, exclude_tests=True)
    html = map_html(
        graph, {"flow-handle": ("Handle", {"pkg/api/handlers.py", "pkg/core/store.py"})}
    )
    core = re.search(
        r'<template id="modal-(comp-\d+)" data-title="pkg/core">(.*?)</template>', html, re.S
    )
    assert core is not None
    body = core.group(2)
    assert "pkg/core/store.py" in body
    assert 'href="requirements.html#R-1"' in body
    assert 'href="flow-handle.html"' in body
    assert f'data-modal="{core.group(1)}"' in html


def test_components_are_declared_in_the_wiki_section(tmp_path: Path) -> None:
    """@brief `wiki.components`: name → globs, order kept; a malformed entry is a problem."""
    from clew.wiki.config import load_wiki_config

    (tmp_path / ".clew.yaml").write_text(
        "wiki:\n  components:\n    Query layer: [clew/query/*]\n    Server: [clew/mcp_server/*]\n"
    )
    config, problems = load_wiki_config(tmp_path)
    assert not problems
    assert config.components == (
        ("Query layer", ("clew/query/*",)),
        ("Server", ("clew/mcp_server/*",)),
    )
    (tmp_path / ".clew.yaml").write_text("wiki:\n  components: [a, b]\n")
    assert load_wiki_config(tmp_path)[1]
