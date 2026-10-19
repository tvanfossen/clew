# SPDX-License-Identifier: MIT
"""A recovered macro reference is credited to the function in the file it was read from.

The enclosing function used to be resolved by name across the whole index, last row wins. Two
vendored copies of one C program each define `help`, and once the substrate published bash a
shell script's `help` joined them: a macro use inside one C body was credited to a shell
function in a different file. The caller is now looked up by (file, name).

@brief Tests for file-scoped caller resolution in the AST macro-reference layer.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import macro_refs


@pytest.fixture
def db(tmp_path: Path) -> Path:
    """@brief An index holding one macro and three same-named functions in three files."""
    path = tmp_path / "index.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT,
                                file_id INTEGER, bodyfile_id INTEGER);
        CREATE TABLE xrefs (rowid INTEGER PRIMARY KEY AUTOINCREMENT, src_rowid INTEGER,
                            dst_rowid INTEGER, context TEXT,
                            UNIQUE(src_rowid, dst_rowid, context) ON CONFLICT IGNORE);
        INSERT INTO memberdef VALUES (1, 'LOG', 'macro definition', 9, 9);
        INSERT INTO memberdef VALUES (10, 'help', 'function', 1, 1);
        INSERT INTO memberdef VALUES (20, 'help', 'function', 2, 2);
        INSERT INTO memberdef VALUES (30, 'help', 'function', 3, NULL);
        """
    )
    conn.commit()
    conn.close()
    return path


def test_each_copy_of_a_function_keeps_its_own_macro_reference(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Files 1 and 2 use the macro inside `help`; file 3 (the shell script, last row) does not.

    @brief Both C copies get the edge and the shell function gets none. @version 1
    """
    payloads = [(1, [("help", "LOG", 4)]), (2, [("help", "LOG", 4)]), (3, [])]
    monkeypatch.setattr(macro_refs, "run_harvest", lambda *a, **k: payloads)

    macro_refs.import_ast_macro_refs(db, tmp_path)

    conn = sqlite3.connect(db)
    got = sorted(conn.execute("SELECT src_rowid, dst_rowid, context FROM xrefs"))
    conn.close()
    assert got == [(10, 1, "ast"), (20, 1, "ast")]


def test_a_body_with_only_a_prototype_elsewhere_resolves_by_its_unique_name(
    db: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A function whose definition row is missing (the parser dropped it, or only a header
    prototype carries the name) keeps its edge when no other function shares the name; `help`,
    which is shared, does not fall back.

    @brief Unique names fall back; shared names do not. @version 1
    """
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO memberdef VALUES (40, 'step', 'function', 5, NULL)")
    conn.commit()
    conn.close()
    payloads = [(6, [("step", "LOG", 9), ("help", "LOG", 12)])]
    monkeypatch.setattr(macro_refs, "run_harvest", lambda *a, **k: payloads)

    macro_refs.import_ast_macro_refs(db, tmp_path)

    conn = sqlite3.connect(db)
    got = sorted(conn.execute("SELECT src_rowid, dst_rowid FROM xrefs"))
    conn.close()
    assert got == [(40, 1)]
