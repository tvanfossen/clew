# SPDX-License-Identifier: MIT
"""`qualified` SELECTS ONE VARIABLE, OR SAYS IT DID NOT.

1.4.0 GRID, mattermost Q4 r2: `dossier("enhanced", qualified="app.screens.….enhanced")` was asked
three times with three different selectors and returned the SAME 48.9 KB reply each time — every
one of the 196 `enhanced` declarations in the repository — because the variable path ignored the
selector (its own @param said "functions only") and the reply never said so. Each reply was over
the client's persist threshold, so an index_only agent saw a stub it could not read; that one cell
cost 711k tokens against 298–462k for its siblings.

Two rules, both pinned here:
  * a selector that names one declaration (exactly, or by a unique boundary-aligned suffix — the
    rule `resolve_selector` applies to functions) narrows `sites` to it;
  * a selector that names none leaves every site and the reply SAYS the selector was not applied.

@brief A variable dossier honours `qualified`.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import clew.query as q


## @brief An index holding one variable name declared in three modules.
## @param tmp_path Per-test temporary directory.
## @return Path to the database.
## @version 1
@pytest.fixture()
def spread(tmp_path: Path) -> Path:
    """The mattermost shape: a module-level `enhanced` in many files, each spelled by its module.

    @brief Seed three same-named variables.
    @return Path to the database.
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER, line INTEGER
        );
        """
    )
    files = ["app/a/index.ts", "app/b/index.ts", "app/c/index.ts"]
    conn.executemany(
        "INSERT INTO path (rowid, name, type) VALUES (?, ?, 1)",
        [(i + 1, f) for i, f in enumerate(files)],
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static, line) "
        "VALUES (?, 'variable', 'enhanced', ?, ?, 0, 0, ?, '', '', '', 0, 10)",
        [(i + 1, i + 1, i + 1, f"app.{c}.index.enhanced") for i, c in enumerate("abc")],
    )
    conn.commit()
    conn.close()
    return db


def test_without_a_selector_every_site_is_reported(spread: Path) -> None:
    """The unchanged default: a variable dossier names every declaration site."""
    reply = q.dossier(spread, "enhanced")
    assert reply is not None and reply.variable is not None
    assert len(reply.variable.sites) == 3
    assert reply.variable.selector_note is None


@pytest.mark.parametrize(
    "selector", ["app.b.index.enhanced", "b.index.enhanced", "b::index::enhanced"]
)
def test_a_selector_naming_one_declaration_narrows_the_sites(spread: Path, selector: str) -> None:
    """Exact, a unique suffix, or the other separator — the function path's selector rule."""
    reply = q.dossier(spread, "enhanced", qualified=selector)
    assert reply is not None and reply.variable is not None
    assert [s.file for s in reply.variable.sites] == ["app/b/index.ts"]
    assert reply.variable.selector_note is None


def test_a_selector_naming_nothing_is_disclosed_not_silently_ignored(spread: Path) -> None:
    """The 1.4.0 defect: three different selectors, one identical reply, no word of why."""
    reply = q.dossier(spread, "enhanced", qualified="app.z.index.enhanced")
    assert reply is not None and reply.variable is not None
    assert len(reply.variable.sites) == 3
    assert reply.variable.selector_note
    assert "app.z.index.enhanced" in reply.variable.selector_note
