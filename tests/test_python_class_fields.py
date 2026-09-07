# SPDX-License-Identifier: MIT
"""gh#17 — the Python class attributes doxygen never emits.

A Python class attribute reaches `memberdef` only when it is NOT a bare annotation
with a simple-identifier type. Determined by controlled experiment, not by reading
doxygen's source:

    bare_str: str              dropped     bare_union: int | None       kept
    bare_int: int              dropped     bare_optional: str | None    kept
    with_default: str = ""     kept        bare_list: list[str]         kept

A value assignment always saves it; among bare annotations, a `|` or `[` in the type
saves it. `EXTRACT_ALL=YES` changes nothing — this is a parser limitation, so the
recovery has to be clew's.

MEASURED ON THIS REPOSITORY: 164 of 357 fields across `clew/query/models.py` reached
the index (46%), every one of its 49 dataclasses was short at least one field, and
`LockNestingPair` returned an EMPTY member list — a class that declares ten fields
reported as having none, with nothing in the reply saying otherwise.

That is the same absence-as-measurement shape gh#15 and gh#16 were filed over, one
layer down: gh#16 made the member list carry documentation, and this is why that fix
buys a Python repo less than it looks.

@brief Tests for recovering Python class attributes doxygen drops.
@version 1
"""

from __future__ import annotations

import sqlite3

import pytest

from clew.ast_symbols import _recover_class_fields_into, harvest_python_class_fields
from clew.harvest import _ast_parse_one_file, try_import_tree_sitter

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the class-field recovery tests need tree_sitter + the Python grammar",
)


##
# @brief Write the fixture and parse it exactly as the pipeline does.
# @param tmp_path Pytest temp dir.
# @return (tree, source bytes).
# @version 1
def _parse(tmp_path):
    """@brief Parse the module fixture through the real per-file parse path."""
    Language, Parser = try_import_tree_sitter()
    path = tmp_path / "m.py"
    path.write_text(_SOURCE, encoding="utf-8")
    parsed = _ast_parse_one_file("m.py", path, {}, Parser, Language)
    assert parsed is not None
    return parsed


_SOURCE = '''\
"""Module."""

from dataclasses import dataclass


@dataclass
class Shapes:
    """A dataclass whose fields doxygen only half-emits."""

    bare_str: str
    bare_int: int
    bare_union: int | None
    with_default: str = ""
    CONST = 3

    def method(self) -> None:
        """Not a field."""
        local_annotated: int = 1
        return None


class Plain:
    """No decorator, same rule."""

    class_level_bare: str
    class_level_assigned: str = "x"


def free_function() -> None:
    """A module-level annotation is not a class field."""
    module_local: str = ""
'''


##
# @brief Every annotated class attribute is harvested, whatever doxygen did with it.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_every_annotated_class_attribute_is_harvested(tmp_path) -> None:
    """Harvests ALL of them, not only the ones doxygen dropped. Which rows are already
    present is a question about the DATABASE, and answering it here would put the dedup
    rule in the parser where it cannot see the index — the same split
    `harvest_variable_declarations` already keeps from `_recoverable_variables`.
    """
    tree, src = _parse(tmp_path)
    got = {(f.class_name, f.name): f for f in harvest_python_class_fields(tree, src)}

    assert {k[1] for k in got} == {
        "bare_str",
        "bare_int",
        "bare_union",
        "with_default",
        "class_level_bare",
        "class_level_assigned",
    }, sorted(k[1] for k in got)
    assert got[("Shapes", "bare_union")].type_text == "int | None"
    assert got[("Shapes", "with_default")].type_text == "str"
    assert got[("Plain", "class_level_bare")].class_name == "Plain"


##
# @brief A local, a module global and a bare assignment are not class fields.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_non_fields_are_not_harvested(tmp_path) -> None:
    """THE THREE WAYS TO OVER-COLLECT, each of which would put a row in `memberdef` under
    a class that does not declare it:

      * `local_annotated` is inside a METHOD — annotated, indented under the class, and
        not a field. A walk that descends into function bodies collects it.
      * `module_local` is inside a free function at module scope.
      * `CONST = 3` is an assignment with NO annotation. It is a real class attribute,
        but doxygen already emits it (a value always saves it), so recovering it would
        duplicate a row the index holds — which is what `provenance` exists to keep
        distinguishable and what the dedup must prevent anyway.
    """
    tree, src = _parse(tmp_path)
    names = {f.name for f in harvest_python_class_fields(tree, src)}

    assert "local_annotated" not in names, "a method-local annotation is not a class field"
    assert "module_local" not in names, "a function-local annotation is not a class field"
    assert "CONST" not in names, "an unannotated assignment is doxygen's to emit, not ours"
    assert "method" not in names, "a method is a function, recovered by the function walk"


##
# @brief Each field carries the line it is declared on.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_each_field_carries_its_declaration_line(tmp_path) -> None:
    """The line is what makes a recovered row navigable, and what
    `_one_row_per_declaration` keys on when the same name appears twice. A row without
    it would be reported at line 0 and collapse against its own siblings."""
    tree, src = _parse(tmp_path)
    lines = {f.name: f.line for f in harvest_python_class_fields(tree, src)}
    source_lines = _SOURCE.splitlines()
    for name, line in lines.items():
        assert name in source_lines[line - 1], f"{name} reported at line {line}"


## The tables the recovery reads and writes, with doxygen's own NOT NULL constraints on
## `member` — the ones that failed the first real run.
_SCHEMA = """
CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
CREATE TABLE refid (rowid INTEGER PRIMARY KEY AUTOINCREMENT, refid TEXT);
CREATE TABLE compounddef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, file_id INTEGER);
CREATE TABLE memberdef (
    rowid INTEGER PRIMARY KEY, name TEXT, definition TEXT, type TEXT, scope TEXT,
    kind TEXT, static INTEGER, file_id INTEGER, line INTEGER, "column" INTEGER,
    dg_source TEXT
);
CREATE TABLE member (
    rowid INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_rowid INTEGER NOT NULL, memberdef_rowid INTEGER NOT NULL,
    prot INTEGER NOT NULL, virt INTEGER NOT NULL,
    UNIQUE(scope_rowid, memberdef_rowid)
);
INSERT INTO path (rowid, name) VALUES (1, 'a/models.py'), (2, 'b/models.py');
INSERT INTO compounddef (rowid, name, kind, file_id) VALUES
    (10, 'a::Config', 'class', 1),
    (20, 'b::Config', 'class', 2);
"""


##
# @brief Build the minimal index the recovery reads.
# @return An open connection.
# @version 1
def _index() -> sqlite3.Connection:
    """@brief A two-file index with a same-named class in each."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(_SCHEMA)
    return conn


def _members(conn: sqlite3.Connection, compound: str) -> list[tuple]:
    return list(
        conn.execute(
            "SELECT m.name, m.type, COALESCE(m.dg_source,'doxygen') FROM member mm "
            "JOIN memberdef m ON m.rowid = mm.memberdef_rowid "
            "JOIN compounddef c ON c.rowid = mm.scope_rowid "
            "WHERE c.name = ? ORDER BY m.name",
            (compound,),
        )
    )


def test_a_dropped_field_is_inserted_and_linked_to_its_class() -> None:
    """A `memberdef` row alone is not the answer here, which is what separates this from
    every other recovery in the module. The existing kinds are file-scope, so a row IS the
    result; a class attribute is reachable only through `member(scope_rowid,
    memberdef_rowid)`, and a row without that link is present in the table and absent from
    every class view — the same defect one layer in."""
    conn = _index()
    harvested = [(1, {"class_fields": [["name", "Config", "str", 7]]})]
    assert _recover_class_fields_into(conn, harvested) == 1
    assert _members(conn, "a::Config") == [("name", "str", "ast")]


def test_a_field_doxygen_already_emitted_is_not_duplicated() -> None:
    """The harvest deliberately collects EVERY annotated field, including the ones doxygen
    emitted, because which are present is a fact about the database rather than the source.
    The dedup therefore has to happen here, against the existing links — and if it does not,
    a class ends up with two rows for one attribute, which is gh#19's defect reintroduced
    through the back door."""
    conn = _index()
    conn.execute(
        "INSERT INTO memberdef (rowid, name, type, kind, file_id, line) "
        "VALUES (99, 'brief', 'str', 'variable', 1, 9)"
    )
    conn.execute("INSERT INTO member (scope_rowid, memberdef_rowid, prot, virt) VALUES (10,99,0,0)")

    harvested = [
        (1, {"class_fields": [["brief", "Config", "str", 9], ["name", "Config", "str", 7]]})
    ]
    assert _recover_class_fields_into(conn, harvested) == 1, "only the missing one is inserted"
    assert _members(conn, "a::Config") == [("brief", "str", "doxygen"), ("name", "str", "ast")]


def test_the_same_class_name_in_two_files_is_attached_to_the_right_one() -> None:
    """MATCHED BY (file, name tail), not by name. Two modules may each declare a `Config`,
    and a bare-name match would file one module's attributes under the other's class —
    silently, and in a way that reads as a real member list. The file the attribute was
    parsed from settles it, and one file cannot declare a class name twice."""
    conn = _index()
    harvested = [
        (1, {"class_fields": [["from_a", "Config", "str", 7]]}),
        (2, {"class_fields": [["from_b", "Config", "int", 3]]}),
    ]
    assert _recover_class_fields_into(conn, harvested) == 2
    assert [m[0] for m in _members(conn, "a::Config")] == ["from_a"]
    assert [m[0] for m in _members(conn, "b::Config")] == ["from_b"]


def test_a_field_whose_class_is_not_indexed_is_skipped() -> None:
    """FAILS CLOSED. A class the index does not hold — excluded by scope, or in a file
    doxygen did not parse — gives nothing to attach to, and inventing a compound would put a
    class in the index that no other layer knows about. The attribute is dropped, which is
    the state before this stage existed."""
    conn = _index()
    harvested = [(1, {"class_fields": [["field", "NotIndexed", "str", 3]]})]
    assert _recover_class_fields_into(conn, harvested) == 0


def test_running_the_recovery_twice_inserts_nothing_the_second_time() -> None:
    """A refresh folds the whole cached payload set, so this stage sees every field on every
    build. Without the dedup reading back what it just wrote, each refresh would add another
    row per attribute and a class's member list would grow with the repository's build
    history."""
    conn = _index()
    harvested = [(1, {"class_fields": [["name", "Config", "str", 7]]})]
    assert _recover_class_fields_into(conn, harvested) == 1
    assert _recover_class_fields_into(conn, harvested) == 0
    assert len(_members(conn, "a::Config")) == 1
