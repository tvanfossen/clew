# SPDX-License-Identifier: MIT
"""A file prose links or embeds — a PDF, a video — is published with the site (#72 item 8, 2.1).

MEASURED on v2.0.0 (a scratch repository, `clew wiki build`): a Markdown `[x](docs/guide.pdf)`
link worked, but a raw `<video src="docs/demo.mp4">`, a reStructuredText `` `x <guide.pdf>`_ ``
link and a `` :download:`x <demo.mp4>` `` all pointed at files the site did not hold (the last
also warned "download file not readable"). Only Markdown link syntax was read, and only for
Markdown pages.

@brief Tests prose asset copying.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.wiki.build import copy_prose


def _repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    (root / "docs").mkdir(parents=True)
    for name in ("docs/guide.pdf", "docs/demo.mp4", "docs/shot.png", "secret.txt"):
        (root / name).write_bytes(b"x")
    (root / "README.md").write_text(
        '# R\n\n[g](docs/guide.pdf)\n\n<video src="docs/demo.mp4" controls></video>\n'
        '<a href="https://example.com/x.pdf">ext</a> [out](../outside.pdf)\n'
    )
    (root / "docs" / "procedure.rst").write_text(
        "P\n=\n\nThe `guide <guide.pdf>`_ and :download:`demo <demo.mp4>`.\n\n.. image:: shot.png\n"
    )
    return root


def test_markdown_raw_html_sources_are_copied_and_published(tmp_path: Path) -> None:
    """@brief `src=`/`href=` in raw HTML count as links; each file lands beside the page and in the site."""
    root, source = _repo(tmp_path), tmp_path / "src"
    copy_prose(root, "README.md", source)
    for rel in ("docs/guide.pdf", "docs/demo.mp4"):
        assert (source / "prose" / rel).is_file(), rel
        assert (source / "_extra" / "prose" / rel).is_file(), rel


def test_rst_links_downloads_and_images_are_copied(tmp_path: Path) -> None:
    """@brief `` `x <file>`_ ``, `:download:` and `.. image::` targets in a `.rst` page."""
    root, source = _repo(tmp_path), tmp_path / "src"
    copy_prose(root, "docs/procedure.rst", source)
    for name in ("guide.pdf", "demo.mp4", "shot.png"):
        assert (source / "prose" / "docs" / name).is_file(), name
        assert (source / "_extra" / "prose" / "docs" / name).is_file(), name


def test_nothing_outside_the_tree_or_remote_is_copied(tmp_path: Path) -> None:
    """@brief A URL or a path out of the repository is not the wiki's to publish."""
    root, source = _repo(tmp_path), tmp_path / "src"
    (tmp_path / "outside.pdf").write_bytes(b"x")
    copy_prose(root, "README.md", source)
    assert not list(source.rglob("outside.pdf")) and not list(source.rglob("x.pdf"))


def test_a_linked_page_outside_the_docs_globs_is_copied_as_an_orphan(tmp_path: Path) -> None:
    """2.1 roadmap: clew's own build warned `cross-reference target not found` 9 times — OVERVIEW
    linking `languages/*.md`, AGENTS.md linking `skills/*/SKILL.md` and `agents/*.md`, none under
    the docs globs. A linked in-repo page is copied as an orphan (no toctree entry, no warning).

    @brief Linked pages copied.
    """
    root, source = tmp_path / "repo", tmp_path / "src"
    (root / "docs" / "languages").mkdir(parents=True)
    (root / "docs" / "OVERVIEW.md").write_text("# O\n\nSee [Rust](languages/RUST.md).\n")
    (root / "docs" / "languages" / "RUST.md").write_text(
        "# Rust\n\nBack to [the overview](../OVERVIEW.md).\n"
    )
    copy_prose(root, "docs/OVERVIEW.md", source)
    page = source / "prose" / "docs" / "languages" / "RUST.md"
    assert page.is_file() and page.read_text().startswith("---\norphan: true\n---\n")
    assert not (source / "prose" / "docs" / "OVERVIEW.md").read_text().startswith("---")


def test_the_mermaid_lexer_is_registered_as_plain_text() -> None:
    """@brief ```mermaid fences highlight as text instead of warning (9 warnings in clew's build)."""
    from types import SimpleNamespace

    from clew.wiki import _sphinxsymbols

    added: dict = {}
    app = SimpleNamespace(
        add_domain=lambda d: None, add_lexer=lambda name, lexer: added.setdefault(name, lexer)
    )
    _sphinxsymbols.setup(app)
    assert "mermaid" in added


def test_a_linked_page_with_front_matter_gets_orphan_inside_it(tmp_path: Path) -> None:
    """FOUND in clew's own build: SKILL.md opens with YAML front matter, and a second, prepended
    block made the first read as a heading ("Document headings start at H2"). `orphan` goes INSIDE
    the page's own front matter.

    @brief One front-matter block.
    """
    root, source = tmp_path / "repo", tmp_path / "src"
    (root / "skills" / "x").mkdir(parents=True)
    (root / "AGENTS.md").write_text("# A\n\n[skill](skills/x/SKILL.md)\n")
    (root / "skills" / "x" / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\n\n# X\n")
    copy_prose(root, "AGENTS.md", source)
    text = (source / "prose" / "skills" / "x" / "SKILL.md").read_text()
    assert text.startswith("---\norphan: true\nname: x\n") and text.count("---\n") == 2
