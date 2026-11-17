# SPDX-License-Identifier: MIT
"""Functional blocks: declared blocks win, the rest join them by coupling (round 4, R1).

OWNER 2026-11-16, on the clew map: "clew/query, clew/mcp_server dont seem like logical separations
of blocks" — a box per directory is the file system, not the system. Ruled: BOTH — blocks a repo
declares in `wiki.components` win; a file no declaration names joins the declared block it is most
coupled to (calls either way), and the block says that file was placed by coupling, not declared.
A file coupled to no declared block is UNASSIGNED, shown as such, never silently dropped.

This is the reflexion method with automated clustering (Christl, Koschke & Storey, WCRE 2005):
the architect's mapping is authoritative, clustering only proposes for what it left unmapped.
Automated clustering alone is often inaccurate against expert ground truth (Garcia et al., ASE
2013), so an inferred placement is always labelled as one.

@brief Tests for declared + coupling blocks.
@version 1
"""

from __future__ import annotations

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
    "pkg/core/store.py": (
        'from pkg import util\n\n\ndef save(x):\n    """Save."""\n    return util.clean(x)\n'
    ),
    "pkg/util.py": 'def clean(x):\n    """Clean."""\n    return x\n',
    "pkg/lonely.py": 'def alone():\n    """Nobody calls me."""\n    return 0\n',
}

_DECLARED = (("API", ("pkg/api/*",)), ("Core", ("pkg/core/*",)))


## @brief The fixture repository, indexed.
## @param tmp_path_factory Pytest's factory.
## @return The index.
## @version 1
@pytest.fixture(scope="module")
def db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief Build. @return Index."""
    root = tmp_path_factory.mktemp("blocks")
    repo = root / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out


def test_an_undeclared_file_joins_the_block_it_is_most_coupled_to(db: Path) -> None:
    """@brief pkg/util.py is called only from Core, so it joins Core — labelled as inferred."""
    blocks = {c["id"]: c for c in build_graph(db, [], None, _DECLARED)["components"]}
    assert "pkg/util.py" in blocks["Core"]["paths"]
    assert blocks["Core"]["inferred_files"] == ["pkg/util.py"]
    assert blocks["API"]["inferred_files"] == []


def test_a_file_coupled_to_no_declared_block_is_unassigned(db: Path) -> None:
    """@brief pkg/lonely.py has no calls either way: it is Unassigned, never dropped."""
    blocks = {c["id"]: c for c in build_graph(db, [], None, _DECLARED)["components"]}
    assert blocks["Unassigned"]["paths"] == ["pkg/lonely.py"]


def test_with_nothing_declared_blocks_are_packages(db: Path) -> None:
    """@brief No declaration: package blocks, and nothing is labelled inferred."""
    blocks = build_graph(db, [], None)["components"]
    assert all(c["inferred_files"] == [] for c in blocks)
    assert "Unassigned" not in {c["id"] for c in blocks}
