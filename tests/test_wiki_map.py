# SPDX-License-Identifier: MIT
"""The system graph's components, as the repository web reads them (round 3, P1c-1; round 4).

ROUND 4, R3 (owner 2026-11-16): the box map these tests once drew is replaced by the repository
web (`tests/test_wiki_web.py` holds its drawing, lenses and flows). What stays here is the graph
the web is built from: test code is a lens, not a block; `wiki.components` declares blocks; a
package lane is the graph's component.

@brief Tests for the graph's components and test exclusion.
@version 2
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.graph import build_graph

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


def test_package_lanes_are_the_maps_components(db: Path) -> None:
    """THE SAME RULE AS THE MAP: `pkg/api/handlers.py` is in lane `pkg/api`, not `pkg` — a flow
    inside one top-level package no longer collapses to a single lane.

    @brief P1e: package lanes.
    """
    from clew.wiki.flow import derive_flow

    repo = db.parent / "repo"
    flow = derive_flow(db, repo, "handle", depth=1, lanes="packages")
    assert [lane.id for lane in flow.lanes] == ["pkg/api", "pkg/core"]
