# SPDX-License-Identifier: MIT
"""gh#29 — a bare name that is both a generated Python enum mirror and a C++ enum.

WHAT WAS REPORTED. On entropic, `dossier("AgentState")` answered with the ctypes
`IntEnum` mirror in `python/src/entropic/_bindings.py`, generated from the C ABI,
while the authoritative definition is the C++ `enum class` in
`include/entropic/core/engine_types.h`. Both readings are real, `also` disclosed the
other one, and `kind="enumeration"` reached it — so nothing was hidden. The bare call
simply returned the derivative of the two.

WHY THE FILED PROPOSAL WAS NOT TAKEN. It asked for the generated FILE to be
deprioritised, the way `SYNTHETIC_PATH` deprioritises `std::` compounds. Measured over
the three indexed targets — 2,174 class-kind compounds, 308 enum names — that shape
occurs TWICE, and only one of the two is a mirror at all:

    AgentState   python/src/entropic/_bindings.py   vs  include/entropic/core/engine_types.h
    State        a C++ struct in an anonymous ns    vs  a C++ enum in docs/design/

`_bindings.py` holds 15 compounds, so deprioritising the file re-ranks 15 resolutions to
change 1. And the marker that identifies it (`AUTO-GENERATED`, `do not edit`) also matches
`python/src/entropic/__init__.py`, which is hand-written and merely mentions the generated
module — the `macro_collision` objection exactly: the available structural rule also fires
on legitimate cases.

WHAT IS USED INSTEAD IS NOT PROVENANCE. `compoundref` already records that the mirror
derives from `enum::IntEnum`; every one of entropic's 8 mirrors does, and nothing else in
any of the three indexes subclasses Enum or Flag. So the trigger is a fact the index
already holds about the SYMBOL, not a guess about the file that holds it.

IT MUST STAY CONDITIONAL ON THE COLLISION. Declining the class reading outright would
break Python-only repositories: a plain `class Color(Enum)` produces no
`memberdef kind='enumeration'` row, so the enumeration probe never fires for it and
`dossier("Color")` would resolve to NOTHING. A name only loses its class reading when a
real enumeration reading is there to take it — `test_a_python_enum_with_no_cpp_namesake_is_still_a_class`
is that control.

@brief Tests for the Enum-subclass tie-break between the class and enumeration kinds.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew import query as q

## The C++ side: the authoritative definitions, one of which the mirror shadows.
_HEADER = """\
enum class AgentState { IDLE = 0, RUNNING = 1 };
enum class Settings { OFF = 0, ON = 1 };
"""

## The Python side: a generated ctypes mirror, as doxygen files it — `AgentState` and
## `EntropicError` subclass `IntEnum`, `Settings` is an ordinary class.
_MIRROR = """\
class AgentState(enum.IntEnum):
    IDLE = 0
    RUNNING = 1


class EntropicError(enum.IntEnum):
    OK = 0


class Settings:
    pass
"""


##
# @brief Build an index where one name is both an Enum-subclass mirror and a C++ enum.
# @param tmp_path Pytest temp dir.
# @return (db path, repo root).
# @version 1
def _index(tmp_path: Path) -> tuple[Path, Path]:
    """@brief Seed the collision, plus both controls, in one index."""
    repo = tmp_path / "repo"
    (repo / "include").mkdir(parents=True)
    (repo / "python").mkdir(parents=True)
    (repo / "include" / "engine_types.h").write_text(_HEADER, encoding="utf-8")
    (repo / "python" / "_bindings.py").write_text(_MIRROR, encoding="utf-8")
    db = tmp_path / "m.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);
        CREATE TABLE compounddef (
            rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, file_id INTEGER,
            line INTEGER, briefdescription TEXT, detaileddescription TEXT
        );
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, type TEXT, argsstring TEXT,
            definition TEXT, scope TEXT, initializer TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER, line INTEGER,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        CREATE TABLE member (scope_rowid INTEGER, memberdef_rowid INTEGER);
        CREATE TABLE compoundref (base_rowid INTEGER, derived_rowid INTEGER);
        INSERT INTO path (rowid, type, name) VALUES
            (1, 1, 'include/engine_types.h'),
            (2, 1, 'python/_bindings.py');
        INSERT INTO compounddef (rowid, name, kind, file_id, line, briefdescription) VALUES
            (30, 'enum::IntEnum', 'class', 2, 0, ''),
            (31, 'pkg::_bindings::AgentState', 'class', 2, 1, 'generated mirror'),
            (32, 'pkg::_bindings::EntropicError', 'class', 2, 6, 'generated mirror'),
            (33, 'pkg::_bindings::Settings', 'class', 2, 10, 'a hand-written class');
        INSERT INTO compoundref (base_rowid, derived_rowid) VALUES (30, 31), (30, 32);
        INSERT INTO memberdef (rowid, name, kind, file_id, bodyfile_id, bodystart, bodyend,
                               line, briefdescription, detaileddescription, static)
        VALUES (40, 'AgentState', 'enumeration', 1, 1, 1, 1, 1,
                '<para>The authoritative agent state.</para>', '', 0),
               (41, 'Settings', 'enumeration', 1, 1, 2, 2, 2,
                '<para>The authoritative settings flag.</para>', '', 0);
        """,
    )
    conn.commit()
    conn.close()
    return db, repo


def test_a_bare_name_prefers_the_cpp_enum_over_its_python_mirror(tmp_path: Path) -> None:
    """The reported case. Nothing about the FILE is consulted — the mirror loses because
    `compoundref` says it subclasses `IntEnum`, which is the index's own statement that the
    compound is an enumeration wearing a class's clothes."""
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "AgentState", repo_root=repo)
    assert doss is not None
    assert doss.kind == "enumeration", "the C++ enum is the authoritative reading"
    assert doss.enumeration is not None
    assert doss.enumeration.file == "include/engine_types.h"


def test_the_mirror_stays_disclosed_and_reachable(tmp_path: Path) -> None:
    """A TIE-BREAK, NOT A SUPPRESSION. gh#6's contract was that a pick is only safe when
    the caller can see one was made, so `also` must still name `class` and passing it back
    must still reach the mirror. Losing the tie-break is not the same as not existing."""
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "AgentState", repo_root=repo)
    assert doss is not None
    assert "class" in doss.also, "the reading that lost must still be named"
    mirror = q.dossier(db, "AgentState", kind="class", repo_root=repo)
    assert mirror is not None
    assert mirror.kind == "class"
    assert mirror.compound is not None
    assert mirror.compound.name == "pkg::_bindings::AgentState"


def test_a_colliding_class_that_is_not_an_enum_keeps_the_class_reading(tmp_path: Path) -> None:
    """CONTROL. `Settings` collides exactly as `AgentState` does — an ordinary Python class
    beside a C++ enum of the same name — and must be untouched, because the trigger is the
    Enum base and not the collision. Without this the rule would be the blanket re-ranking
    this repository has refused before."""
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "Settings", repo_root=repo)
    assert doss is not None
    assert doss.kind == "class", "a real class must not lose to a namesake enum"
    assert doss.compound is not None
    assert doss.compound.name == "pkg::_bindings::Settings"


def test_a_python_enum_with_no_cpp_namesake_is_still_a_class(tmp_path: Path) -> None:
    """THE CONTROL THAT KEEPS PYTHON-ONLY REPOSITORIES WORKING. `EntropicError` subclasses
    `IntEnum` and has no `memberdef kind='enumeration'` row, which is every enum in a
    Python-only codebase. Declining the class reading here would resolve it to nothing at
    all — a definitive miss on a symbol the index plainly holds."""
    db, repo = _index(tmp_path)
    doss = q.dossier(db, "EntropicError", repo_root=repo)
    assert doss is not None, "a Python Enum with no C namesake must still resolve"
    assert doss.kind == "class"
    assert doss.compound is not None
    assert doss.compound.name == "pkg::_bindings::EntropicError"
