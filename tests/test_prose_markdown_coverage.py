# SPDX-License-Identifier: MIT
"""Every markdown file the build scanned is prose, not only the ten paths a list named.

1.1.0, sumac's ask. `SUPPLEMENTARY_PATTERNS` held ten root-anchored globs — `README.md`,
`CHANGELOG.md`, `docs/*.md`, `docs/**/*.md` and a few siblings — so a design note at
`src/notes.md`, an ADR at `architecture/decisions/0003-x.md` or a subsystem README one
level too deep was invisible to `search_prose` while sitting in the repository the index
claims to cover.

WHY THE SCANNED FILE SET AND NOT A WIDER GLOB. `**/*.md` from the repo root would ingest
every vendored and build-output markdown file on the machine's disk: `node_modules`, a
cargo registry copy, `.venv/share/doc`. The scanned set is the build's OWN answer to which
files are in scope — it already honours the declared scope, the operator's excludes, the
toolchain's ignores and binary classification (1.1.0 blockers B2 and B3) — so taking
markdown from it means prose coverage and symbol coverage cannot disagree about what is in
this repository.

The ten globs stay: they also name `README` with no extension, `README.rst` and
`README.txt`, which are prose and are not markdown.

@brief Markdown prose coverage follows the scanned file set.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.prose import ingest_supplementary_docs


## @brief Write a file, making its parents.
## @version 1
def _write(root: Path, rel: str, text: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


## @brief The file paths the prose table holds.
## @version 1
def _ingested(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        return {r[0] for r in conn.execute("SELECT DISTINCT file_path FROM supplementary_docs")}
    finally:
        conn.close()


def test_a_markdown_file_the_old_globs_never_named_is_ingested(tmp_path: Path) -> None:
    """The exact gap sumac reported: markdown outside `docs/` and not called README.

    @brief A scanned `.md` anywhere in the tree becomes prose. @version 1
    """
    root = tmp_path / "repo"
    _write(root, "README.md", "# Repo\n\nTop level.\n")
    _write(root, "src/notes.md", "# Notes\n\nWhy the cache keys on content.\n")
    _write(root, "architecture/decisions/0003-split.md", "# ADR 3\n\nSplit the index.\n")
    db = tmp_path / "clew.db"
    db.touch()

    ingest_supplementary_docs(
        db,
        root,
        files=["README.md", "src/notes.md", "architecture/decisions/0003-split.md"],
    )

    assert _ingested(db) == {
        "README.md",
        "src/notes.md",
        "architecture/decisions/0003-split.md",
    }


def test_markdown_outside_the_scanned_set_is_not_ingested(tmp_path: Path) -> None:
    """THE REASON THIS IS NOT A WIDER GLOB. Both files are markdown on disk and inside the
    repository; one is in scope and one was excluded. A `**/*.md` would take both.

    @brief Prose coverage honours the build's scope and excludes. @version 1
    """
    root = tmp_path / "repo"
    _write(root, "docs/design.md", "# Design\n\nOurs.\n")
    _write(root, "node_modules/left-pad/README.md", "# left-pad\n\nTheirs.\n")
    db = tmp_path / "clew.db"
    db.touch()

    ingest_supplementary_docs(db, root, files=["docs/design.md"])

    assert _ingested(db) == {"docs/design.md"}


def test_the_dotmarkdown_spelling_counts(tmp_path: Path) -> None:
    """@brief `.markdown` is markdown. @version 1"""
    root = tmp_path / "repo"
    _write(root, "notes.markdown", "# Notes\n\nBody.\n")
    db = tmp_path / "clew.db"
    db.touch()

    ingest_supplementary_docs(db, root, files=["notes.markdown"])

    assert _ingested(db) == {"notes.markdown"}


def test_the_named_globs_still_hold_when_no_file_set_is_given(tmp_path: Path) -> None:
    """Back-compat, and the reason the glob list is kept: `README` with no extension and
    `README.rst` are prose that no markdown rule would find.

    @brief A caller passing no file set gets the previous behaviour. @version 1
    """
    root = tmp_path / "repo"
    _write(root, "README", "# Plain\n\nNo extension.\n")
    _write(root, "CONTRIBUTING.md", "# Contributing\n\nHow.\n")
    _write(root, "src/notes.md", "# Notes\n\nNot named by any glob.\n")
    db = tmp_path / "clew.db"
    db.touch()

    ingest_supplementary_docs(db, root)

    assert _ingested(db) == {"README", "CONTRIBUTING.md"}


def test_a_file_both_a_glob_and_the_scan_name_is_ingested_once(tmp_path: Path) -> None:
    """`README.md` is named by the glob list AND is markdown in the scanned set, so it is
    offered twice. Each section must appear once.

    Both headings carry a body: `chunk_markdown` drops a heading with no content on
    purpose, so a heading-only section would be absent for a reason unrelated to deduping.

    @brief The union dedupes. @version 1
    """
    root = tmp_path / "repo"
    _write(root, "README.md", "# Repo\n\nTop.\n\n## One\n\nA.\n")
    db = tmp_path / "clew.db"
    db.touch()

    ingest_supplementary_docs(db, root, files=["README.md"])

    conn = sqlite3.connect(str(db))
    try:
        headings = [r[0] for r in conn.execute("SELECT heading FROM supplementary_docs")]
    finally:
        conn.close()
    assert sorted(headings) == ["One", "Repo"], headings
