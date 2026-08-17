# SPDX-License-Identifier: MIT
"""Build-pipeline robustness to imperfect real-world repos.

clew is meant to index ANY repo, so the build must degrade gracefully rather
than crash: a source file that does not parse, and a repo with no source at all.
These pin that contract — verified behaviour, now guarded against regression.

The malformed-source half moved to
`tests/integration/test_robustness_integration.py` when `sample/` was deleted: it
needs a real source TREE to corrupt one file of. The source-less case stays here
because it writes its own two-file repo and depends on no fixture project — the
module-level doxygen gate is all it needs.

Uses a MINIMAL build argv (`--doxyfile`/`--output`/`--repo-root`, no
manifests) since robustness does not depend on the optional manifest passes.

@brief Robustness tests for the build pipeline.
@version 2
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.cli import build_index

pytestmark = pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="the robustness build tests need the real doxygen binary",
)


## @brief Build a repo through the pipeline with a minimal (manifest-free) argv.
## @param root Repo root to index.
## @param out Output database path.
## @param doxyfile Doxyfile to drive doxygen.
## @return The built database path.
## @version 1
def _build_minimal(root: Path, out: Path, doxyfile: Path) -> Path:
    """@brief Run the pipeline through the typed entry point, declaring nothing."""
    build_index(output=out, repo_root=root, doxyfile=doxyfile)
    return out


## @brief Count function rows in a built database.
## @param db Database path.
## @return memberdef row count (0 = empty but structurally valid).
## @version 1
def _memberdef_count(db: Path) -> int:
    """@brief Read the memberdef row count from a built db."""
    conn = sqlite3.connect(str(db))
    try:
        return conn.execute("SELECT COUNT(*) FROM memberdef").fetchone()[0]
    finally:
        conn.close()


## @brief A source-less repo yields a valid, empty database (never a crash).
## @version 1
def test_build_produces_valid_empty_db_for_sourceless_repo(tmp_path: Path) -> None:
    """A docs-only repo (no C/C++) must produce a well-formed, empty db — full
    schema, zero functions — so a consumer opens a valid database and the query
    layer returns empty results rather than erroring.

    @brief Source-less repo builds a valid empty db.
    @version 1
    """
    root = tmp_path / "empty"
    (root / "docs").mkdir(parents=True)
    (root / "docs" / "readme.md").write_text("# docs only, no source\n", encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(
        f"INPUT = {root}\nOUTPUT_DIRECTORY = {root}/out\nRECURSIVE = YES\nGENERATE_SQLITE3 = YES\n",
        encoding="utf-8",
    )

    db = _build_minimal(root, tmp_path / "out.db", doxyfile)
    assert _memberdef_count(db) == 0
    conn = sqlite3.connect(str(db))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert {"memberdef", "call_edges"} <= tables  # full schema, just empty
