# SPDX-License-Identifier: MIT
"""Tests for repair_attribute_named_functions — fix doxygen's __attribute__ mislabel.

A function with a leading `__attribute__((...))` line is recorded by doxygen
as a memberdef NAMED `__attribute__` owning the real body span, plus a
separate bodyless declaration row with the real name. The repair transfers
the body onto the declaration row and deletes the __attribute__ row (so call
edges don't split across two same-named rows), or renames when no
declaration row exists.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.doxygen import repair_attribute_named_functions

_SRC = (
    "#include <x.h>\n"  # 1
    '__attribute__((visibility("hidden")))\n'  # 2 = bodystart
    "void real_fn(int a)\n"  # 3
    "{\n"  # 4
    "    do_thing(a);\n"  # 5
    "}\n"  # 6 = bodyend
)


## @brief Build a clew.db with an __attribute__ def row + a bodyless decl row.
## @version 1
def _make_db(path: Path, *, with_decl: bool) -> None:
    conn = sqlite3.connect(str(path))
    conn.executescript(
        """
        CREATE TABLE path(rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef(
            rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT,
            file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        INSERT INTO path(rowid,name,type) VALUES(1,'mod.c',1);
        INSERT INTO memberdef(rowid,name,kind,file_id,bodyfile_id,bodystart,bodyend)
            VALUES(10,'__attribute__','function',1,1,2,6);
        """
    )
    if with_decl:
        conn.execute(
            "INSERT INTO memberdef(rowid,name,kind,file_id,bodyfile_id,bodystart,bodyend)"
            " VALUES(20,'real_fn','function',1,NULL,0,0)"
        )
    conn.commit()
    conn.close()


## @brief With a decl row present, the body transfers to it and the __attribute__ row is deleted.
## @version 1
def test_repair_merges_body_into_declaration(tmp_path):
    (tmp_path / "mod.c").write_text(_SRC)
    db = tmp_path / "d.db"
    _make_db(db, with_decl=True)
    n = repair_attribute_named_functions(db, tmp_path)
    assert n == 1
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT rowid, name, bodystart, bodyend FROM memberdef WHERE name='real_fn'"
    ).fetchall()
    attr = conn.execute("SELECT COUNT(*) FROM memberdef WHERE name='__attribute__'").fetchone()[0]
    conn.close()
    assert attr == 0
    assert rows == [(20, "real_fn", 2, 6)]  # single row, decl now owns the body


## @brief With no decl row, the __attribute__ row is renamed in place.
## @version 1
def test_repair_renames_when_no_declaration(tmp_path):
    (tmp_path / "mod.c").write_text(_SRC)
    db = tmp_path / "d.db"
    _make_db(db, with_decl=False)
    n = repair_attribute_named_functions(db, tmp_path)
    assert n == 1
    conn = sqlite3.connect(str(db))
    row = conn.execute(
        "SELECT rowid, name, bodystart FROM memberdef WHERE name='real_fn'"
    ).fetchone()
    conn.close()
    assert row == (10, "real_fn", 2)  # same row, renamed


## @brief No __attribute__ rows -> no-op.
## @version 1
def test_repair_noop_without_attribute_rows(tmp_path):
    db = tmp_path / "d.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        "CREATE TABLE path(rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);"
        "CREATE TABLE memberdef(rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT,"
        " file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER);"
        "INSERT INTO path(rowid,name,type) VALUES(1,'mod.c',1);"
        "INSERT INTO memberdef(rowid,name,kind,file_id,bodyfile_id,bodystart,bodyend)"
        " VALUES(1,'ok_fn','function',1,1,2,4);"
    )
    conn.commit()
    conn.close()
    assert repair_attribute_named_functions(db, tmp_path) == 0
