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
