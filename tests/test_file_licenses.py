# SPDX-License-Identifier: MIT
"""Each file's `SPDX-License-Identifier` header is recorded, not skipped (S5; 2.0.0).

@brief Tests the file-licence layer.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.licenses import ingest_file_licenses, spdx_of


@pytest.mark.parametrize(
    ("header", "expression"),
    [
        ("// SPDX-License-Identifier: GPL-2.0-only\nint x;\n", "GPL-2.0-only"),
        ("/* SPDX-License-Identifier: MIT */\n", "MIT"),
        (
            "#!/bin/sh\n# SPDX-License-Identifier: Apache-2.0 WITH LLVM-exception\n",
            "Apache-2.0 WITH LLVM-exception",
        ),
        ("<!-- SPDX-License-Identifier: CC-BY-4.0 -->\n", "CC-BY-4.0"),
        ("-- SPDX-License-Identifier: (MIT OR BSD-3-Clause)\n", "(MIT OR BSD-3-Clause)"),
    ],
)
def test_the_expression_is_read_in_any_comment_style(header: str, expression: str) -> None:
    """@brief The tag is matched where it stands, whatever opens the comment."""
    assert spdx_of(header)[0] == expression


def test_no_tag_and_a_tag_far_below_the_header_are_not_declarations() -> None:
    """REUSE places the tag in the header; a mention deep in a file is prose, not a declaration.

    @brief Only the header declares.
    """
    assert spdx_of("int x;\n") is None
    assert spdx_of("\n" * 40 + "// SPDX-License-Identifier: MIT\n") is None


def test_the_layer_records_each_file_and_exists_when_empty(tmp_path: Path) -> None:
    """@brief One row per declaring file; the table is created even with none."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.c").write_text("// SPDX-License-Identifier: MIT\nint a;\n")
    (repo / "b.py").write_text('"""No licence."""\n')
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER)")
    conn.executemany("INSERT INTO path(name, type) VALUES (?, 1)", [("a.c",), ("b.py",)])
    conn.commit()
    conn.close()
    assert ingest_file_licenses(db, repo) == 1
    rows = (
        sqlite3.connect(db).execute("SELECT file_path, license, line FROM file_licenses").fetchall()
    )
    assert rows == [("a.c", "MIT", 1)]
