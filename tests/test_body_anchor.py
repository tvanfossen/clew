# SPDX-License-Identifier: MIT
"""A colleague's report against valkey 7f1dffed: doxygen's body spans for src/module.c sat three
lines early throughout the file, so `dossier("moduleAcquireGIL")` returned the TAIL OF THE
PRECEDING FUNCTION as its body, and one candidate named a (file, line) that cannot exist —
`src/module.h:9296` in a 252-line header.

The shift itself did not reproduce here: a clean build at the same pin, both scoped to `src/`
and over the whole repository, with doxygen 1.18.0, recorded every span exactly. So these tests
do not chase the cause. They pin the two consequences that are wrong WHATEVER the cause:

  * a candidate's file and line must come from the same row's same location — the header's file
    paired with the definition's body line is impossible by construction;
  * when the chosen row's recorded span does not open on the function it is filed under and a
    sibling row of the same identity DOES, the dossier describes the sibling. The correct span
    was sitting in the reply as an `ast` candidate while the body quoted another function.

@brief Tests for body anchoring and candidate location consistency.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.query._common import function_candidates
from clew.query.dossier import function_dossier

## The shape of valkey's src/module.c, reduced: a preamble, a preceding function, then the subject.
_SOURCE = """\
/* Copyright notice
 * spanning a few lines
 */
void acquire_gil(void)
{
    spin();
}

void release_gil(void)
{
    unlock();
}
"""

_HEADER = """\
#ifndef MODULE_H
void release_gil(void);
#endif
"""


## @brief Recreate the reported index state: a shifted doxygen row, a header row, an exact AST row.
## @param tmp_path Pytest temporary directory.
## @return (database path, repository root).
## @version 1
def _shifted_db(tmp_path: Path) -> tuple[Path, Path]:
    """Rows mirror what the colleague's reply showed for `moduleReleaseGIL`:
    a doxygen definition three lines early, a doxygen header declaration whose body fields point
    into the .c at that same wrong line, and a parser-recovered definition at the right line.

    @brief Build the shifted-span fixture.
    @version 1
    """
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "module.c").write_text(_SOURCE, encoding="utf-8")
    (root / "src" / "module.h").write_text(_HEADER, encoding="utf-8")
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(db)
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT,
            static INTEGER, line INTEGER, bodystart INTEGER, bodyend INTEGER,
            file_id INTEGER, bodyfile_id INTEGER, dg_source TEXT
        );
        INSERT INTO path (rowid, name) VALUES (1, 'src/module.c'), (2, 'src/module.h');
        INSERT INTO memberdef
          (rowid, kind, name, definition, argsstring, briefdescription, detaileddescription,
           static, line, bodystart, bodyend, file_id, bodyfile_id, dg_source)
        VALUES
          -- doxygen's definition: three lines early, so its span opens inside acquire_gil
          (1, 'function', 'release_gil', 'void release_gil', '(void)', '', '', 0, 6, 6, 9, 1, 1, 'doxygen'),
          -- doxygen's header declaration: declared at module.h:2, body fields into the .c
          (2, 'function', 'release_gil', 'void release_gil', '(void)', '', '', 0, 2, 6, 9, 2, 1, 'doxygen'),
          -- the parser's definition, exact
          (3, 'function', 'release_gil', 'void release_gil', '(void)', '', '', 0, 9, 9, 12, 1, 1, 'ast');
        """
    )
    conn.commit()
    conn.close()
    return db, root


def test_a_candidate_never_pairs_one_files_name_with_another_files_line(tmp_path: Path) -> None:
    """THE IMPOSSIBLE LOCATION. `function_candidates` read the path from `file_id` — the file that
    DECLARES the symbol — and the line from `bodystart` — a line in the file that DEFINES it. For a
    header declaration those are two different files, so the candidate reported
    `src/module.h:<a line in module.c>`: 9296 in a 252-line header on valkey. It needs no shifted
    span to happen; any header declaration row listed as a candidate produces it.

    @brief A candidate's file and line come from the same location.
    @version 1
    """
    db, _root = _shifted_db(tmp_path)
    conn = sqlite3.connect(db)
    rows = function_candidates(conn, "release_gil")
    conn.close()

    header = [row for row in rows if row[2] == "src/module.h"]
    assert header, f"the header declaration row is still listed, got {rows}"
    assert header[0][3] == 2, (
        f"the header row is at module.h:2, not at a line of module.c; got {header[0][3]}"
    )


def test_the_dossier_describes_the_row_whose_span_is_actually_the_function(tmp_path: Path) -> None:
    """THE BODY THAT LOOKS LIKE PROOF. The chosen row's span opened three lines early, so the
    dossier quoted the end of the PRECEDING function under this function's heading — with
    `anchor_mismatch: true`, correctly, but with the text still there to quote, while the exact
    span sat one row away as a parser-recovered candidate of the same identity.

    Disclosure was the right call when no better row existed. When one does, describing it makes
    the wrong body unreachable instead of merely flagged — and the dossier's own line numbers move
    with it, so the header and the body cannot disagree.

    @brief An unanchored pick yields to an anchored sibling of the same identity.
    @version 1
    """
    db, root = _shifted_db(tmp_path)
    dossier = function_dossier(db, "release_gil", repo_root=root)

    assert dossier is not None
    assert dossier.body is not None
    assert not dossier.body.anchor_mismatch, (
        f"an anchored sibling existed and was not used; body was {dossier.body.lines}"
    )
    assert "release_gil" in dossier.body.lines[0], (
        f"the body must open on the function itself, got {dossier.body.lines}"
    )
    assert dossier.line_start == 9, (
        f"the dossier's location follows the row it describes, got {dossier.line_start}"
    )


def test_with_no_anchored_sibling_the_mismatch_is_still_disclosed(tmp_path: Path) -> None:
    """THE CONTROL. Re-anchoring must only ever move to EVIDENCE — a row of the same identity whose
    own span opens on the name. With no such row the original behaviour stands: the body is shown
    and `anchor_mismatch` says not to trust it. Guessing a nearby line would be a heuristic
    wearing the authority of an index row.

    @brief Without a better row, the flag stays and nothing is invented.
    @version 1
    """
    db, root = _shifted_db(tmp_path)
    conn = sqlite3.connect(db)
    conn.execute("DELETE FROM memberdef WHERE rowid = 3")
    conn.commit()
    conn.close()

    dossier = function_dossier(db, "release_gil", repo_root=root)

    assert dossier is not None and dossier.body is not None
    assert dossier.body.anchor_mismatch, "the shifted span is still flagged when nothing is better"
