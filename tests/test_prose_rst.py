# SPDX-License-Identifier: MIT
"""reStructuredText is prose, chunked by the sections its grammar finds.

Before this, a scanned `.rst` file outside the named globs was not prose at all, and the
one `.rst` file a glob did name (`README.rst`) was chunked as MARKDOWN: a title underlined
with `~` or `^` did not split, an overlined title read as a thematic break, and nothing
knew that reStructuredText levels follow the order a document first uses each style.

RST IS PROSE, LIKE MARKDOWN, AND NOT A SOURCE OF SYMBOLS. A section title or a `.. _label:`
target written as a `memberdef` row would land in the namespace that answers
`dossier("my_function")`, which is the reason YAML keys are not symbols either (see
docs/languages/SCRIPT_INTEGRATION.md). The file gets no `path` row, exactly as markdown
gets none.

@brief reStructuredText prose coverage and section chunking.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import substrate
from clew.prose import chunk_rst, ingest_supplementary_docs


## @brief Write a file, making its parents.
## @version 1
def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


## @brief (file_path, heading) for every chunk the prose table holds.
## @version 1
def _chunks(db_path: Path) -> list[tuple[str, str]]:
    conn = sqlite3.connect(str(db_path))
    try:
        return conn.execute(
            "SELECT file_path, heading FROM supplementary_docs ORDER BY rowid"
        ).fetchall()
    finally:
        conn.close()


## @brief The headings `chunk_rst` produces for a text.
## @version 1
def _headings(text: str) -> list[str]:
    return [heading for heading, _ in chunk_rst(text, "docs/guide.rst")]


def test_a_scanned_rst_file_is_ingested_as_prose(tmp_path: Path) -> None:
    """The gap: `docs/install.rst` sits in the scanned set and no glob names it.

    @brief A scanned `.rst` anywhere in the tree becomes prose. @version 1
    """
    root = tmp_path / "repo"
    _write(root, "docs/install.rst", "Install\n=======\n\nRun the installer.\n")
    db = tmp_path / "clew.db"
    db.touch()

    ingest_supplementary_docs(db, root, files=["docs/install.rst"])

    assert _chunks(db) == [("docs/install.rst", "Install")]


def test_readme_rst_is_split_by_the_rst_grammar_not_markdown(tmp_path: Path) -> None:
    """`README.rst` was always globbed, and was chunked as markdown. A `~` underline is no
    markdown heading at all, so the second section never split.

    @brief README.rst splits at an rst-only title style. @version 1
    """
    root = tmp_path / "repo"
    _write(root, "README.rst", "Tool\n~~~~\n\nIntro.\n\nUsage\n^^^^^\n\nRun it.\n")
    db = tmp_path / "clew.db"
    db.touch()

    ingest_supplementary_docs(db, root, files=[])

    assert _chunks(db) == [("README.rst", "Tool"), ("README.rst", "Usage")]


def test_levels_follow_the_order_styles_first_appear() -> None:
    """docutils' rule: `~` used first is level 1, whatever the character. Level 4 (`-`
    here) stays inside its parent's chunk, as a markdown `####` does.

    @brief Order of appearance, not character, decides a level. @version 1
    """
    text = (
        "Top\n~~~\n\nA.\n\nTwo\n===\n\nB.\n\nThree\n^^^^^\n\nC.\n\n"
        "Four\n----\n\nD.\n\nAgain two\n=========\n\nE.\n"
    )
    chunks = chunk_rst(text, "docs/guide.rst")
    assert [h for h, _ in chunks] == ["Top", "Two", "Three", "Again two"]
    assert "Four" in dict(chunks)["Three"]


def test_an_overlined_title_is_its_own_style() -> None:
    """An overlined `=` title and an underlined `=` title are two styles, so two levels;
    the overlined one appears first and is the document title.

    @brief Overline distinguishes a style. @version 1
    """
    text = "=====\nTitle\n=====\n\nIntro.\n\nPart\n====\n\nBody.\n"
    assert _headings(text) == ["Title", "Part"]


def test_a_title_shaped_line_inside_a_literal_block_does_not_split() -> None:
    """The grammar knows a literal block; a regex over `====` lines would not.

    @brief Literal blocks are not titles. @version 1
    """
    text = "Real\n====\n\nExample::\n\n    Fake\n    ====\n\nDone.\n"
    chunks = chunk_rst(text, "docs/guide.rst")
    assert [h for h, _ in chunks] == ["Real"]
    assert "Fake" in chunks[0][1]


def test_content_before_the_first_title_is_headed_by_the_file_name() -> None:
    """@brief The preamble chunk, as `chunk_markdown` names it. @version 1"""
    chunks = chunk_rst(":Author: someone\n\nTitle\n=====\n\nBody.\n", "docs/guide.rst")
    assert chunks[0] == ("guide.rst", ":Author: someone")


def test_a_named_target_opens_the_section_it_labels() -> None:
    """`.. _install:` above a title is that section's label (`:ref:`install``), so it is the
    first line of the section's chunk and not the last line of the one before.

    @brief A label travels with its section. @version 1
    """
    text = "Intro\n=====\n\nHello.\n\n.. _install:\n\nInstall\n=======\n\nSteps.\n"
    chunks = dict(chunk_rst(text, "docs/guide.rst"))
    assert ".. _install:" in chunks["Install"]
    assert ".. _install:" not in chunks["Intro"]


def test_an_anonymous_target_stays_with_the_paragraph_it_serves() -> None:
    """`__ http://...` is a link destination for the text before it, not a section label.

    @brief Anonymous targets are not labels. @version 1
    """
    text = "Intro\n=====\n\nSee `docs`__.\n\n__ http://example.org\n\nNext\n====\n\nMore.\n"
    chunks = dict(chunk_rst(text, "docs/guide.rst"))
    assert "__ http://example.org" in chunks["Intro"]
    assert "__ http" not in chunks["Next"]


def test_without_the_grammar_the_file_is_one_chunk(monkeypatch: pytest.MonkeyPatch) -> None:
    """A substrate built without `lang-rst` must not crash the build, and must not split by
    a guess. The file is still searchable, whole, under its name.

    @brief Degrade to one chunk when the grammar is absent. @version 1
    """
    monkeypatch.setattr(substrate, "compiled_languages", lambda: frozenset({"markdown"}))
    text = "Title\n=====\n\nBody.\n"
    assert chunk_rst(text, "docs/guide.rst") == [("guide.rst", text.strip())]


def test_an_rst_file_gets_no_path_row(tmp_path: Path) -> None:
    """Prose, not source: like markdown, an `.rst` file is not registered in `path`, so it
    adds no symbols and is not counted as an indexed source file.

    @brief The parse front end does not claim `.rst`. @version 1
    """
    from clew.synth import claims

    assert not claims("docs/install.rst")


@pytest.mark.parametrize(
    "target", [".. _ext: https://example.com", ".. _a: b_"], ids=["external", "indirect"]
)
def test_a_target_with_a_link_stays_with_the_paragraph_it_serves(target: str) -> None:
    """docutils labels a section only with an INTERNAL target: a name and nothing after
    it. An external (`.. _ext: https://...`) or indirect (`.. _a: b_`) target is a link
    destination for the text that references it, and must not move into the next section.

    @brief Only internal targets label a section. @version 1
    """
    text = f"Intro\n=====\n\nSee ext_ and a_.\n\n{target}\n\nSub\n===\n\nBody.\n"
    chunks = dict(chunk_rst(text, "docs/guide.rst"))
    assert target in chunks["Intro"]
    assert target not in chunks["Sub"]
