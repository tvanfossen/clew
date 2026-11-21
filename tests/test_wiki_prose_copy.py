# SPDX-License-Identifier: MIT
"""Prose is copied so Sphinx can link it and resolve what it links (P6 findings, 2.0.0).

OWNER Q/A 2026-11-20, after P6, "fix all 5":

- sassafras-class's 8 release notes (`docs/releases/v0.7.0.md`, …) have no heading. Sphinx found no
  title, generated NO LINK in the Docs toctree, and warned once per page that renders the
  navigation: 1,040 of the site's 1,128 warnings, and the notes unreachable.
- clew's own OVERVIEW links `[docs/wire-keys.json](wire-keys.json)`. The page was copied without
  the file it links, so MyST reported a missing cross-reference and the link went nowhere.

@brief Tests prose copying.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.wiki.build import copy_prose


def test_untitled_markdown_gets_its_file_name_as_title(tmp_path: Path) -> None:
    """@brief A Markdown file with no heading is titled by its file name; a titled one is unchanged."""
    root, source = tmp_path / "repo", tmp_path / "src"
    (root / "docs" / "releases").mkdir(parents=True)
    (root / "docs" / "releases" / "v0.7.0.md").write_text("- Install once.\n", encoding="utf-8")
    (root / "docs" / "guide.md").write_text("Intro.\n\n## Usage\n", encoding="utf-8")
    copy_prose(root, "docs/releases/v0.7.0.md", source)
    copy_prose(root, "docs/guide.md", source)
    assert (source / "prose/docs/releases/v0.7.0.md").read_text().startswith("# v0.7.0\n")
    assert (source / "prose/docs/guide.md").read_text() == "Intro.\n\n## Usage\n"


def test_a_local_file_the_prose_links_is_copied_beside_it(tmp_path: Path) -> None:
    """@brief A relative link to an existing non-prose repo file brings the file along."""
    root, source = tmp_path / "repo", tmp_path / "src"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "wire-keys.json").write_text("{}\n", encoding="utf-8")
    (root / "docs" / "OVERVIEW.md").write_text(
        "# O\n\nSee [keys](wire-keys.json), [web](https://x.invalid/a.json) and [gone](no.json).\n",
        encoding="utf-8",
    )
    copy_prose(root, "docs/OVERVIEW.md", source)
    assert (source / "prose/docs/wire-keys.json").read_text() == "{}\n"
    assert not (source / "prose/docs/no.json").exists()


def test_a_github_style_heading_anchor_resolves(tmp_path: Path, capfd) -> None:
    """P6: OVERVIEW's `[Programmatic use](#programmatic-use)` and `GUARD.md#files-the-gate-skips`
    work on GitHub but MyST reported "target not found" / "local id not found" (and 7 more on
    sassafras-class): MyST makes heading anchors only when told to. A real render, judged by the
    warning MyST emits and by the cross-document link landing on the section.

    @brief Same-page and cross-document heading anchors resolve.
    """
    from clew.wiki.build import _render
    from clew.wiki.config import WikiConfig

    source, html = tmp_path / "src", tmp_path / "out" / "html"
    source.mkdir()
    (source / "index.md").write_text(
        "# Top\n\n```{toctree}\nguard\n```\n\nSee [use](#programmatic-use) and "
        "[skips](guard.md#files-the-gate-skips).\n\n## Programmatic use\n\nText.\n",
        encoding="utf-8",
    )
    (source / "guard.md").write_text(
        "# Guard\n\n## Files the gate skips\n\nText.\n", encoding="utf-8"
    )
    _render(source, html, WikiConfig(), tmp_path)
    err = capfd.readouterr().err
    assert "xref_missing" not in err, err
    assert 'href="guard.html#files-the-gate-skips"' in (html / "index.html").read_text(
        encoding="utf-8"
    )
