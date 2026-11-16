# SPDX-License-Identifier: MIT
"""The wiki's system graph (round 3, P1a): one typed model at several zoom levels.

Components are packages (or a declared grouping); links aggregate calls and shared keys between
them; each component carries its lens facts (requirements by tier, threads, changed functions);
the code level is a point cloud inside the boxes. Layout is deterministic: callers above callees.
A lens whose source is absent is absent — no impact report, no `changed` key at all.

@brief Tests for clew.wiki.graph.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.graph import build_graph, component_of

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
    root = tmp_path_factory.mktemp("graph")
    repo = root / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out


def test_a_file_belongs_to_its_package_unless_a_grouping_is_declared() -> None:
    """@brief Component rules."""
    assert component_of("clew/query/x.py") == "clew/query"
    assert component_of("clew/cli.py") == "clew"
    assert component_of("setup.py") == "(root)"
    assert component_of("clew/query/x.py", (("Query layer", ("clew/query/*",)),)) == "Query layer"


def test_components_links_and_layout(db: Path) -> None:
    """CALLERS ABOVE CALLEES: pkg/api calls pkg/core, so it sits in a higher layer.

    @brief Container level.
    """
    graph = build_graph(db, [], None)
    comps = {c["id"]: c for c in graph["components"]}
    assert {"pkg/api", "pkg/core", "tests"} <= set(comps)
    link = next(
        edge for edge in graph["links"] if (edge["from"], edge["to"]) == ("pkg/api", "pkg/core")
    )
    assert link["calls"] == 1
    assert comps["pkg/api"]["y"] < comps["pkg/core"]["y"]
    assert comps["tests"]["test"] is True and comps["pkg/core"]["test"] is False


def test_lens_facts_ride_on_components_and_absent_sources_stay_absent(db: Path) -> None:
    """NO IMPACT REPORT, NO `changed` KEY; an empty report is a measured zero everywhere.

    @brief Lens facts.
    """
    evidence = [_Row("R-1", "PASS", (("save", "pkg/core/store.py", 1),))]
    plain = {c["id"]: c for c in build_graph(db, evidence, None)["components"]}
    assert plain["pkg/core"]["requirements"] == {"PASS": 1}
    assert "requirements" not in plain["pkg/api"]
    assert all("changed" not in c for c in plain.values())
    impact = [{"req_id": "R-1", "functions": [{"name": "save", "file": "pkg/core/store.py"}]}]
    measured = {c["id"]: c for c in build_graph(db, evidence, impact)["components"]}
    assert measured["pkg/core"]["changed"] == 1 and measured["pkg/api"]["changed"] == 0


def test_the_point_cloud_places_every_function_inside_its_box(db: Path) -> None:
    """@brief Code level."""
    graph = build_graph(db, [_Row("R-1", "PASS", (("save", "pkg/core/store.py", 1),))], None)
    comps = {c["id"]: c for c in graph["components"]}
    for point in graph["symbols"]:
        box = next(
            c
            for c in comps.values()
            if c["x"] <= point["x"] <= c["x"] + c["w"] and c["y"] <= point["y"] <= c["y"] + c["h"]
        )
        assert box is not None
    save = next(p for p in graph["symbols"] if p["name"] == "save")
    assert save["tier"] == "PASS" and "changed" not in save
