# SPDX-License-Identifier: MIT
"""A path the repository declares `vendored:` is in the wiki's Vendor block (P4; 2.0.0: W5).

W5 (PARTLY, defect CONFIRMED): the build records a declared `vendored:` as
`scope.vendored_roots`, and `wiki.graph._vendored` read only the nested-git-tree stamp
(`dg_external_root`). A copied-in library the repository itself calls vendored (mbedtls's
`3rdparty/`, once declared) was drawn as first-party code. A declaration is as much a statement
by the repository as a submodule is, and belongs in the same block.

@brief Tests declared vendored paths in the wiki's block assignment.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.graph import _vendored


def test_a_declared_vendored_path_is_vendored(tmp_path: Path) -> None:
    """@brief third_party/ declared: its file is vendored; src/ is not."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "third_party/lib").mkdir(parents=True)
    (repo / "src/app.c").write_text("int lib_fn(void);\nint main(void) { return lib_fn(); }\n")
    (repo / "third_party/lib/lib.c").write_text("int lib_fn(void) { return 1; }\n")
    (repo / ".clew.yaml").write_text("vendored:\n  - third_party\n")
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    vendored = _vendored(sqlite3.connect(db))
    assert "third_party/lib/lib.c" in vendored
    assert "src/app.c" not in vendored
