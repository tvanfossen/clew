# SPDX-License-Identifier: MIT
"""gh#10 — file-level documentation as an indexed, searchable unit.

Two layers, tested separately on purpose. The EXTRACTION is a pure function over
a string and needs no database; the INGEST is an ordering-sensitive pipeline
stage whose two ordering constraints are the part that will break silently if
anyone reorders `cli._build_stages`, so both are pinned here.

@brief Tests for module-docstring / file-doxygen extraction and ingest.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.filedocs import (
    CFamilyFileDoc,
    PythonFileDoc,
    extract_file_doc,
    ingest_file_docs,
)
from clew.query import file_doc_rows, has_file_docs, search

PY_SOURCE = '''# SPDX-License-Identifier: MIT
"""Resolve function-pointer calls to the handler actually bound.

A callback assignment binds a pointer; the call site is elsewhere.

@brief Callback edge resolution.
@version 3
"""

from __future__ import annotations


def go() -> None:
    """Do it."""
'''

C_SOURCE = """/* Copyright 2026 Nobody. All rights reserved. */
/**
 * @file mutex_order.c
 * @brief Detect lock-ordering inversions that can deadlock.
 */
#include <stdio.h>

void go(void) {}
"""

C_LINE_SOURCE = """// SPDX-License-Identifier: MIT
/// @file ring.c
/// A lock-free ring buffer, single producer.
#include <stddef.h>
"""

C_LICENSE_ONLY = """/*
 * Copyright 2026 Nobody. Licensed under the Apache License, Version 2.0.
 */
#include <stdio.h>

void go(void) {}
"""


## @brief A Python module docstring is extracted, its own `#` header ignored.
## @return None.
## @version 1
def test_python_module_docstring_is_the_file_documentation() -> None:
    """Uses the AST rather than a regex, so the SPDX comment above the docstring and
    the `from __future__` import below it are both non-events."""
    doc = extract_file_doc("clew/callback_edges.py", PY_SOURCE)
    assert "function-pointer calls" in doc
    assert "callback assignment" in doc
    assert "SPDX" not in doc, "a `#` comment is not the module docstring"
    assert "Do it." not in doc, "a FUNCTION docstring is not the file's documentation"
    ## One line, so a multi-line block is searchable as one string.
    assert "\n" not in doc


## @brief A C file's leading doxygen block is found past a plain license header.
## @return None.
## @version 1
def test_c_family_doxygen_block_is_found_past_a_license_header() -> None:
    """The `/* Copyright */` line must be SKIPPED OVER rather than terminating the
    search — the same shape as the `#`-divider trap that used to make doxygen-guard
    read the wrong block."""
    doc = extract_file_doc("src/mutex_order.c", C_SOURCE)
    assert "deadlock" in doc
    assert "Copyright" not in doc
    ## The `*` gutter each continuation line carries is furniture, not content.
    assert not doc.startswith("*")


## @brief A run of `///` line comments is the file documentation too.
## @return None.
## @version 1
def test_c_family_line_comment_run_is_extracted() -> None:
    """Doxygen accepts both forms and a repo may use either; supporting only the
    block form would make the corpus silently empty for a codebase using `///`."""
    doc = extract_file_doc("src/ring.h", C_LINE_SOURCE)
    assert "lock-free ring buffer" in doc


## @brief A license-only header never becomes searchable documentation.
## @return None.
## @version 1
def test_a_plain_comment_header_is_not_documentation() -> None:
    """THE CONTROL ON THE WHOLE CORPUS. A bare `/*` block is excluded by construction
    — only `/**`, `/*!`, `///` and `//!` count — because if a copyright notice entered
    the corpus then `search("copyright")` would return every file in the repository and
    the new surface would be pure noise on its first query. Deciding by CONTENT would
    need a heuristic about what a license looks like; the marker the author already
    wrote answers it exactly.

    TWO mechanisms enforce this and the test covers the pair, which a mutation control
    is what proved: `_PLAIN_BLOCK` SKIPS a bare block as preamble, and `_CXX_BLOCK_DOC`
    would not accept one anyway. Loosening either alone leaves the other holding, so a
    single-edit mutation could not break this and the assertion looked stronger than it
    was until both were mutated together."""
    assert extract_file_doc("src/thing.c", C_LICENSE_ONLY) == ""
    ## And the copyright text must not arrive via the license block sitting ABOVE a
    ## real doc block, which is the common real-world layout.
    assert "Copyright" not in extract_file_doc("src/mutex_order.c", C_SOURCE)


## @brief A suffix no extractor claims yields nothing, silently and correctly.
## @return None.
## @version 1
def test_an_unclaimed_suffix_yields_no_documentation() -> None:
    """A `.json` fixture has no file-level documentation to find, and inventing one
    would put noise on a search surface."""
    assert extract_file_doc("tests/data/schema_vocabulary.json", '{"a": 1}') == ""


## @brief Unparseable Python yields "" rather than failing the build.
## @return None.
## @version 1
def test_unparseable_python_is_skipped_not_fatal() -> None:
    """This stage ANNOTATES an index doxygen already built successfully. One file that
    will not parse must not undo that."""
    assert extract_file_doc("broken.py", "def (:\n") == ""


## @brief The extractors claim disjoint suffix sets.
## @return None.
## @version 1
def test_extractor_suffix_sets_do_not_overlap() -> None:
    """Dispatch is first-match, so an overlap would make which extractor runs depend
    on declaration order — the sort of thing that works until someone sorts a tuple."""
    py = set(PythonFileDoc.EXTENSIONS)
    cxx = set(CFamilyFileDoc.EXTENSIONS)
    assert py & cxx == set()
    assert py and cxx


## @brief An index with source files, ready for the ingest stage.
## @param tmp_path Pytest temporary directory.
## @return (db path, repo root).
## @version 1
@pytest.fixture
def indexed(tmp_path: Path) -> tuple[Path, Path]:
    """Builds the MINIMUM the stage reads: a `path` table naming indexed files, plus
    those files on disk. Deliberately not a full pipeline run — the stage's contract is
    "read the indexed inventory", and a fixture that globbed the tree instead would not
    catch it widening the scope."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "cb.py").write_text(PY_SOURCE, encoding="utf-8")
    (repo / "src" / "mutex_order.c").write_text(C_SOURCE, encoding="utf-8")
    (repo / "src" / "plain.c").write_text(C_LICENSE_ONLY, encoding="utf-8")
    ## On disk and NOT in the index: the stage must not pick it up.
    (repo / "src" / "unindexed.py").write_text(
        '"""Secret prose about widgets."""\n', encoding="utf-8"
    )
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE path (rowid_ INTEGER, name TEXT, type INTEGER)")
    conn.executemany(
        "INSERT INTO path (name, type) VALUES (?, ?)",
        [
            ("src/cb.py", 1),
            ("src/mutex_order.c", 1),
            ("src/plain.c", 1),
            ("[STL]", 1),
            ("src", 2),
        ],
    )
    conn.commit()
    conn.close()
    return db, repo


## @brief Ingest writes one row per documented indexed file, and no others.
## @param indexed The prepared index and repo.
## @return None.
## @version 1
def test_ingest_covers_the_indexed_set_and_only_that(indexed: tuple[Path, Path]) -> None:
    """Four claims in one pass, because they share a fixture and each is a different way
    the stage could be wrong: the documented files are in, the license-only file is out,
    the synthetic `[STL]` row and the directory row are out, and a file on disk that the
    index does not know about STAYS OUT — the stage must not widen the build's scope
    decision by globbing."""
    db, repo = indexed
    count = ingest_file_docs(db, repo)
    assert count == 2

    conn = sqlite3.connect(db)
    paths = {row[0] for row in conn.execute("SELECT file_path FROM file_docs")}
    headings = {row[0] for row in conn.execute("SELECT heading FROM supplementary_docs")}
    conn.close()

    assert paths == {"src/cb.py", "src/mutex_order.c"}
    assert "src/plain.c" not in paths, "a license header is not documentation"
    assert "src/unindexed.py" not in paths, "the stage must read the INDEX, not the tree"
    ## The FTS5 mirror is what `search_prose` reads; a row per file, headed by its path.
    assert any("src/cb.py" in h for h in headings)


## @brief A synthetic path row is filtered before anything tries to open it.
## @param indexed The prepared index and repo.
## @param caplog Pytest log capture.
## @return None.
## @version 1
def test_a_synthetic_path_row_produces_no_warning(
    indexed: tuple[Path, Path], caplog: pytest.LogCaptureFixture
) -> None:
    """A MUTATION CONTROL FOUND THIS TEST, by finding that the version before it was
    vacuous. Asserting `[STL]` produces no `file_docs` row passes with the filter
    REMOVED, because doxygen's synthetic row names no openable file and `_read_text`
    drops it anyway — two mechanisms, one observable, so the assertion tested nothing.

    What the filter actually buys is silence: without it every build logs a spurious
    `could not read [STL]` warning, which trains a reader to ignore that warning for
    the files where it means something real. So the log is what gets asserted."""
    db, repo = indexed
    with caplog.at_level("WARNING"):
        ingest_file_docs(db, repo)
    assert not [r for r in caplog.records if "[STL]" in r.getMessage()], (
        "a synthetic path row must be filtered, not opened and warned about"
    )


## @brief Ingest is idempotent across repeated runs.
## @param indexed The prepared index and repo.
## @return None.
## @version 1
def test_ingest_is_idempotent(indexed: tuple[Path, Path]) -> None:
    """A rebuild of the same database must not double the corpus. `DELETE` then insert,
    the same shape `ingest_supplementary_docs` uses."""
    db, repo = indexed
    ingest_file_docs(db, repo)
    ingest_file_docs(db, repo)
    conn = sqlite3.connect(db)
    total = conn.execute("SELECT COUNT(*) FROM file_docs").fetchone()[0]
    conn.close()
    assert total == 2


## @brief A conceptual query reaches the file, as a hit whose kind is 'file'.
## @param indexed The prepared index and repo.
## @return None.
## @version 1
def test_search_reaches_a_file_by_concept(indexed: tuple[Path, Path]) -> None:
    """gh#10's whole point, at unit scale: 'deadlock' appears in NO function name and
    in no `@brief`, only in a file's own documentation, and `search` must still find it.
    `kind == 'file'` so a consumer can tell a file hit from a symbol hit rather than
    having to infer it."""
    db, repo = indexed
    ingest_file_docs(db, repo)
    hits = search(db, "deadlock")
    assert [h.name for h in hits] == ["src/mutex_order.c"]
    assert hits[0].kind == "file"
    assert hits[0].provenance == "file_doc"

    ## The conjunction still applies across the file corpus.
    assert search(db, "deadlock nosuchtoken") == []


## @brief The corpus's ABSENCE is detectable, so an empty search can say so.
## @param indexed The prepared index and repo.
## @return None.
## @version 1
def test_absent_corpus_is_reported_as_absent(indexed: tuple[Path, Path]) -> None:
    """An index built before build 23 has no `file_docs` table. A detector that cannot
    look must not report a negative — this repo's most-repeated lesson, applied to its
    newest table."""
    db, repo = indexed
    assert has_file_docs(db) is False
    assert file_doc_rows(sqlite3.connect(db), ["anything"]) == []
    ingest_file_docs(db, repo)
    assert has_file_docs(db) is True
