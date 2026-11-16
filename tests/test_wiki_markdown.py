# SPDX-License-Identifier: MIT
"""The wiki as Markdown for GitHub and Azure DevOps wikis (round 3, P5b).

Owner 2026-11-15: serve the wiki directly on GH or ADO, replacing the doxygen-to-Pages pipeline
entropic runs today. A wiki host renders Markdown and Mermaid, not a site, so `clew wiki build
--format markdown --flavor github|ado` writes pages a wiki takes as they are: Home, Requirements,
Flows (one page per flow, its sequence diagram in Mermaid) and Change impact — without Sphinx.
The flavours differ only where the hosts do: GitHub fences ```mermaid, keeps `_Sidebar.md` and
links pages without an extension; Azure DevOps takes `::: mermaid` blocks, orders pages with
`.order` and links `./Page.md`. The map, lenses and ego-graphs are the HTML site's and Home says
so. The audience rules apply here as everywhere.

@brief Tests for the Markdown wiki output.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.test_wiki_site import repo  # noqa: F401  (module fixture reused)


def _build(
    site_repo: tuple[Path, Path], out: Path, flavor: str, audience: str | None = None
) -> dict[str, str]:
    from clew.wiki.markdown import build_markdown

    build_markdown(site_repo[0], site_repo[1], out, flavor, audience=audience)
    return {p.relative_to(out).as_posix(): p.read_text() for p in out.rglob("*") if p.is_file()}


def test_github_flavour_pages_and_diagrams(repo: tuple[Path, Path], tmp_path: Path) -> None:  # noqa: F811
    """@brief GitHub: Home, Requirements, a page per flow with ```mermaid, `_Sidebar.md`."""
    pages = _build(repo, tmp_path / "gh", "github")
    assert {"Home.md", "Requirements.md", "Flows.md", "_Sidebar.md"} <= set(pages)
    assert not any(name.endswith(".html") for name in pages)
    flow = pages["Flow-load.md"]
    assert "```mermaid\nsequenceDiagram" in flow and ": parse" in flow
    assert "[Requirements](Requirements)" in pages["_Sidebar.md"]
    req = pages["Requirements.md"]
    assert "| REQ-W-001 |" in req and "Load the data" in req and "PASS" in req
    assert "map" in pages["Home.md"].lower() and "HTML" in pages["Home.md"]


def test_ado_flavour_blocks_order_and_links(repo: tuple[Path, Path], tmp_path: Path) -> None:  # noqa: F811
    """@brief Azure DevOps: `::: mermaid` blocks, `.order`, `./Page.md` links."""
    pages = _build(repo, tmp_path / "ado", "ado")
    assert (
        "::: mermaid\nsequenceDiagram" in pages["Flow-load.md"]
        and "```mermaid" not in pages["Flow-load.md"]
    )
    order = pages[".order"].split()
    assert order[:3] == ["Home", "Requirements", "Flows"]
    assert "[load](./Flow-load.md)" in pages["Flows.md"]


def test_the_markdown_obeys_the_audience(repo: tuple[Path, Path], tmp_path: Path) -> None:  # noqa: F811
    """@brief `exclude_requirement_text` and `exclude_bodies` reach the Markdown."""
    public = _build(repo, tmp_path / "pub", "github", audience="public")
    assert (
        "Load the data" not in public["Requirements.md"]
        and "REQ-W-001" in public["Requirements.md"]
    )
    partner = _build(repo, tmp_path / "par", "github", audience="partner")
    assert not any("SECRET_CALL_ARG" in t or "SECRET_BODY_MARKER" in t for t in partner.values())


def test_the_cli_writes_markdown_without_sphinx(repo: tuple[Path, Path], tmp_path: Path) -> None:  # noqa: F811
    """@brief `clew wiki build --format markdown --flavor ado` writes the pages into `--out`."""
    from clew.wiki.command import wiki_main

    out = tmp_path / "cli"
    code = wiki_main(
        [
            "build",
            "--format",
            "markdown",
            "--flavor",
            "ado",
            "--out",
            str(out),
            "--index",
            str(repo[1]),
            "--repo-root",
            str(repo[0]),
        ]
    )
    assert code == 0 and (out / "Home.md").is_file() and (out / ".order").is_file()


def test_an_unknown_flavour_is_refused() -> None:
    """@brief Two hosts, named; anything else refused rather than guessed."""
    from clew.wiki.markdown import build_markdown

    with pytest.raises(ValueError, match="github, ado"):
        build_markdown(Path("."), Path("x.db"), Path("out"), "gitlab")
