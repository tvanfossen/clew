# SPDX-License-Identifier: MIT
"""Build-pipeline robustness to imperfect real-world source.

Moved here from `tests/test_robustness.py` when `sample/` was deleted. The claim
under test — "a garbage-tailed C file must not fail the whole build" — is a claim
about what doxygen and tree-sitter actually DO with malformed bytes. A synthetic
database cannot express it: there is no parser in the loop.

Its sibling in `tests/test_robustness.py`
(`test_build_produces_valid_empty_db_for_sourceless_repo`) stays there — it
writes its own two-file repo and needs no fixture project at all.

**This is the tier's only C/C++ build**, and its only build driven by a
repo-supplied Doxyfile. Both properties are deliberate: the pinned target's C
files live under `tests/fixtures/`, which its doxygen-guard hook excludes from
the GATE, so `--scope from-guard` would index Python only. Writing a Doxyfile
that names `tests/fixtures` as INPUT is what a repo owner pointing clew at
that tree would do, and it keeps one relative-INPUT, Doxyfile-driven build in the
suite after `sample/` (previously the only one) is gone.

@brief Integration robustness test for malformed source.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.cli import build_index

pytestmark = pytest.mark.integration

## The pinned target's C/C++ fixture directory — 12 `.c` + 1 `.cpp`, each a
## small standalone translation unit, which is exactly the shape this test
## wants: corrupt one and the siblings must still extract.
FIXTURE_INPUT = "tests/fixtures"

## The file that gets the garbage tail.
VICTIM = "tests/fixtures/simple.c"

## A function defined in the VICTIM, BEFORE the appended garbage. Doxygen stops
## at the garbage rather than discarding the file, so this must survive.
VICTIM_SURVIVING_FUNCTION = "Module_Process"

## A function from a DIFFERENT file in the same INPUT root. Pinned by SHA, so
## these names are frozen. Its presence is what "every other file still
## extracts" means concretely — asserting only a global `memberdef > 0` would
## also pass if the whole directory had been dropped.
SIBLING_FILE = "tests/fixtures/typedef_returns.c"
SIBLING_FUNCTION = "get_status"

## Minimal, relative-INPUT Doxyfile. The pipeline force-appends everything it
## needs (GENERATE_SQLITE3/XML, EXTRACT_ALL, RECURSIVE, ...); a target only has
## to say what its sources are.
DOXYFILE_TEXT = (
    "PROJECT_NAME      = doxygen_guard_fixtures\n"
    f"INPUT             = {FIXTURE_INPUT}\n"
    "RECURSIVE         = YES\n"
    "OUTPUT_DIRECTORY  = .doxygen_out\n"
    "GENERATE_HTML     = NO\n"
    "GENERATE_LATEX    = NO\n"
    "EXTRACT_STATIC    = YES\n"
    "QUIET             = YES\n"
)

## Appended to the victim: unbalanced braces, an illegal identifier and
## non-ASCII bytes, i.e. text no C parser can recover into a declaration.
GARBAGE_TAIL = "\n\nvoid @@@corrupt(( { { garbage §§§\n"


## @brief Build a repo through the pipeline with a minimal (manifest-free) argv.
## @param root Repo root to index.
## @param out Output database path.
## @param doxyfile Doxyfile to drive doxygen.
## @return The built database path.
## @version 2
def _build_minimal(root: Path, out: Path, doxyfile: Path) -> Path:
    """Robustness does not depend on the optional manifest passes, so this is
    deliberately not a copy of the index-cache tier's richer `_build`.

    @brief Run the pipeline through the typed entry point, declaring nothing.
    @version 3
    """
    build_index(output=out, repo_root=root, doxyfile=doxyfile)
    return out


## @brief Every (file, function) pair a built database indexed.
## @param db Database path.
## @return Set of (repo-relative file name, function name) pairs.
## @version 1
def _indexed_functions(db: Path) -> set[tuple[str, str]]:
    """Joined through `path` rather than counting `memberdef` rows, because
    "which files survived" is the actual question and a bare count cannot answer
    it.

    @brief Read back the indexed functions with their files.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return {
            (path_name, function_name)
            for path_name, function_name in conn.execute(
                "SELECT p.name, m.name FROM memberdef m "
                "JOIN path p ON p.rowid = m.file_id WHERE m.kind = 'function'",
            )
        }
    finally:
        conn.close()


## @brief A repo containing an unparseable source file still builds from the rest.
## @param guard_repo Staged copy of the pinned target repo.
## @param tmp_path Per-test temp directory.
## @return None.
## @version 2
def test_build_survives_malformed_source_file(guard_repo: Path, tmp_path: Path) -> None:
    """One garbage-tailed C file must not fail the whole build — doxygen stops at
    the garbage and tree-sitter is error-tolerant, so the valid files (in that
    file and every other) still extract into a usable db.

    @brief Malformed source degrades gracefully, not fatally.
    @version 2
    """
    doxyfile = guard_repo / "Doxyfile"
    doxyfile.write_text(DOXYFILE_TEXT, encoding="utf-8")
    victim = guard_repo / VICTIM
    victim.write_text(victim.read_text(encoding="utf-8") + GARBAGE_TAIL, encoding="utf-8")

    db = _build_minimal(guard_repo, tmp_path / "out.db", doxyfile)
    indexed = _indexed_functions(db)

    assert indexed, "the build produced no functions at all"
    # Every other file in the same INPUT root still extracted...
    assert (SIBLING_FILE, SIBLING_FUNCTION) in indexed
    # ...and so did the valid part of the corrupted file itself.
    assert (VICTIM, VICTIM_SURVIVING_FUNCTION) in indexed
