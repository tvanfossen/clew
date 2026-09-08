# SPDX-License-Identifier: MIT
"""gh#22 — the incremental splice used the wrong identity for a `param` row.

doxygen's own schema declares the key:

    CREATE UNIQUE INDEX idx_param ON param (type, defname);

`_insert_params` instead matched on the FULL seven-column tuple to decide whether a
row already existed. Two memberdefs for one function — a header declaration and its
out-of-line definition — share `(type, defname)` while differing elsewhere, and
`briefdescription` is the obvious one: a parameter documented on the declaration and
not repeated on the definition. The full-tuple lookup calls that pair absent, INSERTs,
and hits the unique index.

WHAT MAKES IT EXPENSIVE RATHER THAN FATAL. The IntegrityError is caught and the whole
refresh degrades to a full doxygen run — reported at WARNING, with `ok: true` — so the
only symptom is an unexplained cost spike on every refresh of a repo that documents
its parameters. The reporter measured 1s, 2s, then a 23s full run in one call where
~8s incremental was normal.

MATCHING THE KEY REPRODUCES A FULL BUILD, which is the standard this splice is held
to. Under the unique index doxygen itself can only keep the first row written and
link the second memberdef to it; reusing on `(type, defname)` is that behaviour, not
an approximation of it.

THE SCHEMA IS LOADED VERBATIM, not hand-simplified — without `idx_param` the defect
cannot reproduce at all and this file would pass against the bug.

@brief Tests for param-row identity in the incremental splice.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.doxygen_splice import SpliceReport, _insert_params

SCHEMA = Path(__file__).resolve().parent.parent / "clew" / "data" / "doxygen_schema.sql"


##
# @brief A doxygen-shaped database holding one function and one documented parameter.
# @param brief The parameter's briefdescription.
# @param refid The memberdef's refid.
# @return An open connection.
# @version 1
def _db(brief: str, refid: str = "fn_1") -> sqlite3.Connection:
    """@brief Seed a doxygen-schema database with one param row."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    conn.execute(
        "INSERT INTO path (rowid, type, local, found, name) VALUES (1, 1, 1, 1, 'src/a.c')"
    )
    conn.execute("INSERT INTO refid (rowid, refid) VALUES (1, ?)", (refid,))
    conn.execute(
        "INSERT INTO memberdef (rowid, name, kind, file_id, line, \"column\") "
        "VALUES (1, 'fn', 'function', 1, 10, 1)"
    )
    conn.execute(
        "INSERT INTO param (rowid, type, defname, briefdescription) VALUES (1, 'int', 'count', ?)",
        (brief,),
    )
    conn.execute("INSERT INTO memberdef_param (memberdef_id, param_id) VALUES (1, 1)")
    conn.commit()
    return conn


def test_a_param_documented_on_one_side_only_does_not_break_the_splice() -> None:
    """THE REPORTED CRASH. The working copy holds the parameter undocumented (as the
    definition writes it) and the subset holds it documented (as the declaration does).
    They share `(type, defname)`, which is the schema's unique key, so a second INSERT is
    an IntegrityError — and the splice's caller turns that into a full doxygen run.
    """
    work, sub = _db(brief=""), _db(brief="<para>How many.</para>")
    report = SpliceReport()
    ctx = {"sub_paths": {"src/a.c": 1}}

    _insert_params(work, sub, {"src/a.c"}, ctx, report)

    rows = work.execute("SELECT rowid, type, defname FROM param").fetchall()
    assert len(rows) == 1, f"the row was duplicated rather than reused: {rows}"
    assert report.relations_inserted == 1


def test_the_existing_row_is_reused_rather_than_rewritten() -> None:
    """REUSE, NOT UPDATE, and the reason is that a full build cannot do better. Under
    `idx_param` doxygen keeps whichever row it wrote first and links every later memberdef
    to it, so the documented text may genuinely be the one that loses — on both paths
    equally. Rewriting here would make the splice produce something a full rebuild does not,
    which is the one property `test_incremental_splice_matches_a_full_rebuild` exists to
    hold.
    """
    work, sub = _db(brief=""), _db(brief="<para>How many.</para>")
    _insert_params(work, sub, {"src/a.c"}, {"sub_paths": {"src/a.c": 1}}, SpliceReport())

    kept = work.execute("SELECT briefdescription FROM param WHERE rowid = 1").fetchone()[0]
    assert kept == "", "the pre-existing row must be linked to, not rewritten in place"


def test_a_genuinely_different_parameter_is_still_inserted() -> None:
    """THE CONTROL. Keying on `(type, defname)` must not collapse parameters that differ in
    either half — a second `int` named something else, or a `char*` named `count`, is a
    different row under the schema's own key and the splice must still add it.
    """
    work, sub = _db(brief=""), _db(brief="")
    sub.execute("INSERT INTO param (rowid, type, defname) VALUES (2, 'char *', 'name')")
    sub.execute("INSERT INTO memberdef_param (memberdef_id, param_id) VALUES (1, 2)")
    sub.commit()

    _insert_params(work, sub, {"src/a.c"}, {"sub_paths": {"src/a.c": 1}}, SpliceReport())

    keys = set(work.execute("SELECT type, defname FROM param"))
    assert keys == {("int", "count"), ("char *", "name")}, keys


def test_the_schema_key_is_what_this_matches_on() -> None:
    """PINS THE PREMISE. If doxygen ever changes `idx_param`, matching on `(type, defname)`
    silently becomes the wrong rule — and the failure would look like this bug again rather
    than like a schema change. Read from the shipped schema so the two cannot drift.
    """
    sql = SCHEMA.read_text(encoding="utf-8")
    assert "CREATE UNIQUE INDEX idx_param ON param" in sql
    index_def = sql.split("CREATE UNIQUE INDEX idx_param ON param", 1)[1].split(";", 1)[0]
    assert "type" in index_def and "defname" in index_def, index_def
