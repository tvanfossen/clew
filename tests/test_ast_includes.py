# SPDX-License-Identifier: MIT
"""Every `#include` is recorded from the parse, resolved to an indexed file where one matches (T3; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mbedtls F6, re-checked by the P2 measurement before
this was written): doxygen's `includes` table held 2 includers of `constant_time_internal.h`
where the tree has 17 (`grep -l`, library/*.c), so "what reaches this header" could not be
answered from the index. An AST harvest records every `#include` directive.

ITS OWN TABLE, `ast_includes`, beside doxygen's `includes`, because doxygen's table has no
provenance column and an unresolved spec must still be recorded: `dst_id` is NULL when no
indexed file matches (seen, not resolved) — never a guess. A spec resolves to the file beside
the includer first, then to the ONE indexed path ending in it; two candidates resolve to none.

@brief Tests the AST include layer.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.tsnode import Parser


def test_the_harvest_reads_quoted_system_and_nested_includes() -> None:
    """@brief Quoted, angle-bracket and conditional includes; a macro include is skipped."""
    from clew.ast_includes import includes_harvester

    src = (
        b'#include "a/b.h"\n#include <stdio.h>\n#if X\n#  include "c.h"\n#endif\n#include MACRO_H\n'
    )
    rows = includes_harvester().harvest(Parser("c").parse(src), src)
    assert sorted(rows) == [["a/b.h", 1, 1], ["c.h", 1, 4], ["stdio.h", 0, 2]]


def _index(tmp_path: Path, files: dict[str, str]) -> Path:
    """@brief A repo with these files and a path table naming them. @return The db path."""
    repo = tmp_path / "repo"
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, local INTEGER, found INTEGER, name TEXT)"
    )
    conn.executemany(
        "INSERT INTO path (type, local, found, name) VALUES (1, 1, 1, ?)", [(r,) for r in files]
    )
    conn.commit()
    conn.close()
    return db


def test_specs_resolve_beside_the_includer_then_by_unique_suffix(tmp_path: Path) -> None:
    """@brief Same directory first; else the unique indexed suffix; ambiguous or absent → NULL."""
    from clew.ast_includes import import_ast_includes

    db = _index(
        tmp_path,
        {
            "library/aes.c": '#include "common.h"\n#include "mbedtls/aes.h"\n#include "dup.h"\n#include <stdio.h>\n',
            "library/common.h": "",
            "include/mbedtls/aes.h": "",
            "a/dup.h": "",
            "b/dup.h": "",
        },
    )
    assert import_ast_includes(db, tmp_path / "repo") == 4
    rows = (
        sqlite3.connect(db)
        .execute(
            "SELECT i.spec, d.name FROM ast_includes i LEFT JOIN path d ON d.rowid = i.dst_id ORDER BY i.line"
        )
        .fetchall()
    )
    assert rows == [
        ("common.h", "library/common.h"),
        ("mbedtls/aes.h", "include/mbedtls/aes.h"),
        ("dup.h", None),
        ("stdio.h", None),
    ]


def test_the_table_exists_when_nothing_includes_anything(tmp_path: Path) -> None:
    """@brief Empty, not absent."""
    from clew.ast_includes import import_ast_includes

    db = _index(tmp_path, {"main.py": "print(1)\n"})
    assert import_ast_includes(db, tmp_path / "repo") == 0
    assert sqlite3.connect(db).execute("SELECT COUNT(*) FROM ast_includes").fetchone() == (0,)
