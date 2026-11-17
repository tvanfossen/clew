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
from gitfixture import repo_with_submodules
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


## OWNER 2026-11-17, on sassafras-class's web (vendored SDL filled half of it): "Vendor code is a
## block of its own". VENDORED IS A FACT THE INDEX ALREADY RECORDS, not a directory-name guess:
## gh#335 stamps every file inside a nested git tree with its external root, and a copied-in file
## with no git tree of its own is first party (clew/external.py). An undeclared vendored file is
## therefore never folded into a first-party block by coupling, and never split into packages: it
## is the Vendor block. A declaration still wins — a repo may name its vendored block itself.
_VENDORED = {
    **_FILES,
    "deps/zlib/inflate.py": 'def inflate(x):\n    """Inflate."""\n    return x\n',
    "deps/zlib/sub/crc.py": 'def crc(x):\n    """Crc."""\n    return x\n',
    "pkg/core/codec.py": (
        "from deps.zlib.inflate import inflate\nfrom deps.zlib.sub.crc import crc\n\n\n"
        'def decode(x):\n    """Decode."""\n    return inflate(crc(x))\n'
    ),
}


## @brief A fixture repository vendoring a nested git tree, indexed.
## @param tmp_path_factory Pytest's factory.
## @return The index.
## @version 1
@pytest.fixture(scope="module")
def vendored_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief Build with a nested git tree. @return Index."""
    root = tmp_path_factory.mktemp("vendored")
    ## A REAL GITLINK, not a `.git` directory: vendored means the parent DECLARES the tree as a
    ## dependency (gh#352), and a fixture of `.git` directories tests a world nobody asks about.
    repo = repo_with_submodules(root / "repo", "deps/zlib")
    for rel, text in _VENDORED.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    out = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return out


def test_vendored_code_is_one_block_never_joined_by_coupling(vendored_db: Path) -> None:
    """@brief deps/zlib is called only from Core, yet it is the Vendor block, not part of Core."""
    blocks = {c["id"]: c for c in build_graph(vendored_db, [], None, _DECLARED)["components"]}
    assert blocks["Vendor"]["paths"] == ["deps/zlib/inflate.py", "deps/zlib/sub/crc.py"]
    assert not any(p.startswith("deps/") for p in blocks["Core"]["paths"])
    assert blocks["Vendor"]["inferred_files"] == []


def test_vendored_code_is_one_block_with_nothing_declared(vendored_db: Path) -> None:
    """@brief No declaration: packages for first party, but one Vendor block, not deps/zlib."""
    ids = {c["id"] for c in build_graph(vendored_db, [], None)["components"]}
    assert "Vendor" in ids and not any(i.startswith("deps") for i in ids)


def test_a_declared_block_still_wins_over_vendor(vendored_db: Path) -> None:
    """@brief A repo that names its vendored block keeps its own name for it."""
    declared = (*_DECLARED, ("Third-party", ("deps/*",)))
    ids = {c["id"] for c in build_graph(vendored_db, [], None, declared)["components"]}
    assert "Third-party" in ids and "Vendor" not in ids
