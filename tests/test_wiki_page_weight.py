# SPDX-License-Identifier: MIT
"""The published site carries pages, not Sphinx's build cache or source copies (P5, item 1; 2.0.0).

MEASURED on clew's own site before this change (worktree at 8909ecc7, the gate's junit.xml as
evidence, `clew wiki build`): 191 MB apparent across 9,430 files, of which
  * 87.1 MB was `html/.doctrees/`: sphinx-build was given no `-d`, so its pickled doctrees landed
    INSIDE the published directory;
  * 37.6 MB was `html/_sources/`: `html_copy_source` defaulted on, a markdown copy of every page;
  * the remaining 62 MB the pages themselves (3,111 HTML files).
A rebuild also kept every page the previous build wrote, so a removed test's page stayed online.

Symbol bodies are drawn collapsed (`<details>`): a closed `<details>` is parsed but not laid out,
so a 459-symbol file page no longer lays out every body on load. Not fetched separately: the site
is opened as a FILE (`clew wiki open`, "reading never needs a server"), where fetch is refused.

@brief Tests the published site's weight.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_SRC = '"""A module."""\n\n\ndef helper(x):\n    """Help."""\n    return x + 1\n\n\ndef run():\n    """Run."""\n    return helper(2)\n'
_WIKI = "wiki:\n  title: Weight\n  docs: [README.md]\n  flows:\n    - entry: run\n      depth: 1\n"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """@brief Build a small site twice, a stale page planted between. @return The html dir."""
    from clew.wiki.build import build_wiki

    root = tmp_path_factory.mktemp("weight")
    repo = root / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg/__init__.py").write_text("")
    (repo / "pkg/mod.py").write_text(_SRC)
    (repo / "README.md").write_text("# Weight\n")
    (repo / ".clew.yaml").write_text(_WIKI)
    db = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    html = build_wiki(repo, db, root / "out")
    (html / "stale-page.html").write_text("<p>from an earlier build</p>")
    return build_wiki(repo, db, root / "out")


def test_no_source_copies_are_published(built: Path) -> None:
    """@brief html_copy_source is off: no _sources directory, no "Show source" links."""
    assert not (built / "_sources").exists()


def test_the_build_cache_is_not_published(built: Path) -> None:
    """@brief Doctrees live beside the site, never inside it."""
    assert not (built / ".doctrees").exists()


def test_a_rebuild_removes_pages_the_previous_build_wrote(built: Path) -> None:
    """@brief A page nothing generates any more is gone after the next build."""
    assert not (built / "stale-page.html").exists()
    assert (built / "index.html").is_file()


def test_symbol_bodies_are_collapsed(built: Path) -> None:
    """@brief Each body is inside a closed <details>, its line count on the summary."""
    page = next(p for p in built.glob("sym-*mod-py.html")).read_text()
    assert '<details class="body">' in page
    assert "<summary>" in page and 'class="body"' in page
