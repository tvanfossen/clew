# SPDX-License-Identifier: MIT
"""A file dossier serves what the file includes and what includes it (T3 served; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW: entropic F2 (the `includes` table exists, no dossier
key serves it) and mbedtls F6 (re-checked by the P2 measurement: doxygen's table held 2 includers
of `constant_time_internal.h`, the AST layer `ast_includes` holds 18). This serves the AST layer.

`includes` keeps the spec as written, its line and the file it resolved to, or `file: None` when
no indexed file matches ("seen, not resolved"). `included_by` lists the includers with the line.
Both are ABSENT on an index built before the layer existed, and EMPTY when the layer ran and found
nothing; those are different answers.

ON A FAST-REFRESHED INDEX TOO. The edited file's directives are re-read by the fast tier: the
tier's preconditions keep the file set unchanged, so resolution cannot differ from a full build,
and the refreshed rows must equal the full build's exactly.

@brief Tests the include graph on file dossiers, full and fast-refreshed.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.query.subject import dossier
from clew.refresh_command import refresh_main

_A = '#include "common.h"\n#include <stdio.h>\n\nint a_fn(void) { return 1; }\n'
_B = '#include "common.h"\n\nint b_fn(void) { return 2; }\n'
_COMMON = "#pragma once\n#define COMMON 1\n"


def _repo(tmp_path: Path) -> tuple[Path, Path]:
    """@brief A three-file C repo, fully built. @return (repo, db)."""
    repo = tmp_path / "repo"
    (repo / "lib").mkdir(parents=True)
    (repo / "lib/a.c").write_text(_A)
    (repo / "lib/b.c").write_text(_B)
    (repo / "lib/common.h").write_text(_COMMON)
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return repo, db


def _file(db: Path, repo: Path, path: str):
    """@brief The file section. @return FileSubject."""
    d = dossier(db, path, kind="file", repo_root=repo)
    assert d is not None and d.file is not None, path
    return d.file


def _includes(db: Path, repo: Path, path: str) -> list[tuple]:
    """@brief (spec, resolved file, line) rows. @return Rows."""
    return [(i.spec, i.file, i.line) for i in _file(db, repo, path).includes]


def test_a_file_lists_what_it_includes_resolved_or_not(tmp_path: Path) -> None:
    """@brief A quoted spec resolves beside the includer; a system header stays unresolved."""
    repo, db = _repo(tmp_path)
    assert _includes(db, repo, "lib/a.c") == [("common.h", "lib/common.h", 1), ("stdio.h", None, 2)]


def test_a_header_lists_its_includers(tmp_path: Path) -> None:
    """@brief Both .c files, with the directive's line."""
    repo, db = _repo(tmp_path)
    assert [(i.file, i.line) for i in _file(db, repo, "lib/common.h").included_by] == [
        ("lib/a.c", 1),
        ("lib/b.c", 1),
    ]


def test_a_file_that_includes_nothing_has_an_empty_list_not_none(tmp_path: Path) -> None:
    """@brief The layer ran: empty is a measurement."""
    repo, db = _repo(tmp_path)
    assert _file(db, repo, "lib/common.h").includes == ()


def test_an_index_without_the_layer_says_nothing_rather_than_none_found(tmp_path: Path) -> None:
    """@brief Table dropped (an index from before T3): both fields absent (None)."""
    repo, db = _repo(tmp_path)
    with sqlite3.connect(db) as conn:
        conn.execute("DROP TABLE ast_includes")
    f = _file(db, repo, "lib/a.c")
    assert f.includes is None and f.included_by is None


def test_a_fast_refresh_serves_the_edited_files_includes_as_a_full_build_does(
    tmp_path: Path,
) -> None:
    """@brief Lines shifted and a directive added: the fast tier's rows equal a full build's."""
    repo, db = _repo(tmp_path)
    (repo / "lib/a.c").write_text('/* moved */\n#include "missing.h"\n' + _A)
    assert refresh_main(["--output", str(db), "--repo-root", str(repo)]) == 0
    with sqlite3.connect(db) as conn:
        fast = dict(conn.execute("SELECT key, value FROM build_meta WHERE key LIKE 'fast.%'"))
    assert fast.get("fast.pending") == "1", f"the fast tier did not run: {fast}"
    reference = tmp_path / "full.db"
    _run_pipeline(
        _build_argparser().parse_args(["--output", str(reference), "--repo-root", str(repo)])
    )
    assert (
        _includes(db, repo, "lib/a.c")
        == _includes(reference, repo, "lib/a.c")
        == [
            ("missing.h", None, 2),
            ("common.h", "lib/common.h", 3),
            ("stdio.h", None, 4),
        ]
    )
