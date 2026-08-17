# SPDX-License-Identifier: MIT
"""The self-edge guard (#61): genuine recursion kept, fabrications dropped.

A `caller_rowid == callee_rowid` row is a MIX. Measured on two real indexes
before the guard existed:

  clew  70 self-edge rows / 37 callers — 10 genuine, 27 `obj.name()` on
           another object, 12 `super().__init__()`, 21 with no same-named call
           site anywhere in the caller's body.
  a C++ codebase     458 self-edge rows / 228 callers —  6 genuine, 442 an anonymous-
           namespace doxygen artifact, 10 `::close()`/`::open()` shadowing a
           member of the same name.

So a blanket drop would delete true recursion, and keeping everything reads to
a consumer as infinite recursion in `IndexCache.close`. The discriminator is NOT
name-uniqueness — `close`/`commit` are unique names and fabricated, `_classify`
is unique and genuine — it is the CALL SHAPE, which is what these tests pin.

Every fixture body range is DERIVED from the fixture's own AST, so editing a
fixture cannot silently invalidate a test by shifting a line number.

@brief Tests for the call_edges self-edge guard.
@version 1
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from clew.call_edges import (
    GUARDED_SELF_EDGE_SOURCES,
    _build_function_indexes,
    _self_directed_sites,
    import_ast_call_edges,
    prune_fabricated_self_edges,
)
from clew.harvest import _ast_parse_one_file, try_import_tree_sitter
from clew.vocabulary import (
    CALL_SOURCE_DECLARED_DISPATCH,
    CALL_SOURCE_DOXYGEN_SQLITE,
    CALL_SOURCE_FNPTR,
)

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="the self-edge guard needs tree_sitter + its C/C++/Python grammars",
)

# Each function below is one measured mechanism, named for it.
_PY_FIXTURE = '''\
import sqlite3


def descend(node):
    """GENUINE: a bare self-call, the shape that must survive."""
    for child in node:
        descend(child)


def main():
    """FABRICATED: never names itself. doxygen attributes the module-level
    `main()` in the __main__ guard below to this member, producing a self xref."""
    descend([])
    return 0


class Cache:
    def __init__(self, path):
        """FABRICATED: 28 memberdefs share the name `__init__`, so the
        unqualified name resolves back onto the caller's own rowid."""
        super().__init__()
        self.conn = sqlite3.connect(path)

    def close(self):
        """FABRICATED: `close` on ANOTHER object. The only `close` memberdef is
        this wrapper, so resolution bound the call back to the wrapper."""
        self.conn.close()

    def walk(self, node):
        """GENUINE: `self.walk` is the ONLY way a Python method recurses."""
        for child in node:
            self.walk(child)

    def cull(self, registry):
        """FABRICATED (gh#30): a BARE `cull(...)` inside a METHOD is not a
        self-call. Python has no implicit `this`, so this names the imported
        module-level `cull` — exactly `DocsDbServer.cull`'s shape, whose bare
        `cull(self.registry, ...)` is `state.cull`."""
        return cull(registry)

    @property
    def refresh(self):
        """FABRICATED, and the case that pins the scope-skip walk: a DECORATED
        method is `class_definition > block > decorated_definition >
        function_definition`, so a walk that did not step over
        `decorated_definition` would read this as module-level and accept the
        bare call."""
        return refresh(self)

    def prune(self, node):
        """GENUINE, and the control on the rule above: `self.prune` recursion in
        a method that ALSO makes a bare same-named call is still recursion. A
        rule that rejected the method wholesale rather than per-call-site would
        lose this."""
        prune(node)
        self.prune(node.next)


if __name__ == "__main__":
    raise SystemExit(main())
'''

_CPP_FIXTURE = """\
#include <unistd.h>

namespace {
void warn_failure(int code)
{
    log_warn(code);
}
}  // namespace

int Port::close()
{
    return ::close(fd_);
}

void Tree::walk(Node *n)
{
    this->walk(n->next);
}

int brace_expand(const char *s)
{
    return brace_expand(s + 1);
}

int Buffer::compact(int n)
{
    return compact(n - 1);
}
"""


## @brief Parse a written source file exactly as the pipeline does.
## @param tmp_path Pytest temp dir.
## @param name File name (its extension selects the grammar).
## @param text Source text.
## @return (tree, src_bytes).
## @version 1
def _parse(tmp_path: Path, name: str, text: str):
    """@brief Write a fixture and parse it through the production plumbing.

    @return (tree, src_bytes).
    @version 1
    """
    language_cls, parser_cls = try_import_tree_sitter()
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    parsed = _ast_parse_one_file(name, path, {}, parser_cls, language_cls)
    assert parsed is not None, f"{name} did not parse"
    return parsed


## @brief Enumerate a fixture's functions as (name, bodystart, bodyend).
## @param tree The parsed tree.
## @param src_bytes The file's raw bytes.
## @return One tuple per function definition, in document order.
## @version 1
def _functions(tree, src_bytes) -> list[tuple[str, int, int]]:
    """Handles both grammars: Python names a `function_definition`'s `name`
    field directly, while C/C++ nests it under `declarator`.

    @brief Derive every function's name and body line range from the AST.
    @return (name, bodystart, bodyend) per function.
    @version 1
    """
    out: list[tuple[str, int, int]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "function_definition":
            continue
        name = _declared_name(node, src_bytes)
        if name is not None:
            out.append((name, node.start_point[0] + 1, node.end_point[0] + 1))
    return sorted(out, key=lambda f: f[1])


## @brief The declared name of a function_definition in either grammar.
## @param node A `function_definition` node.
## @param src_bytes The file's raw bytes.
## @return The bare function name, or None when it cannot be read.
## @version 1
def _declared_name(node, src_bytes) -> str | None:
    """@brief Read a function definition's bare name (C/C++ or Python).

    @return The name, or None.
    @version 1
    """
    cursor = node.child_by_field_name("name") or node.child_by_field_name("declarator")
    while cursor is not None and cursor.type not in ("identifier", "field_identifier"):
        cursor = cursor.child_by_field_name("declarator") or cursor.child_by_field_name("name")
    if cursor is None:
        return None
    return src_bytes[cursor.start_byte : cursor.end_byte].decode("utf-8")


## @brief Build a doxygen-shaped DB over one fixture file.
## @param tmp_path Test temp dir.
## @param name Fixture file name.
## @param text Fixture source.
## @return (db path, name -> memberdef rowid).
## @version 1
def _make_db(tmp_path: Path, name: str, text: str) -> tuple[Path, dict[str, int]]:
    """Mirrors the columns the guard and `_build_function_indexes` read, with
    line ranges taken from the AST rather than written by hand.

    @brief Seed memberdef/path/call_edges rows for one fixture.
    @return (database path, name -> rowid).
    @version 1
    """
    tree, src = _parse(tmp_path, name, text)
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT,
            UNIQUE(caller_rowid, callee_rowid, source)
        );
        """
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, ?)", (name,))
    conn.executemany(
        "INSERT INTO memberdef (kind, name, file_id, bodyfile_id, bodystart, bodyend) "
        "VALUES ('function', ?, 1, 1, ?, ?)",
        _functions(tree, src),
    )
    conn.commit()
    rowids = {n: r for r, n in conn.execute("SELECT rowid, name FROM memberdef").fetchall()}
    conn.close()
    return db_path, rowids


## @brief Seed a self-edge for each named function, in every guarded layer.
## @param db_path Database to write.
## @param rowids name -> rowid map.
## @param names Functions to give a self-edge.
## @version 1
def _seed_self_edges(db_path: Path, rowids: dict[str, int], names: list[str]) -> None:
    """@brief Insert one self-edge per guarded source for each named function.

    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    conn.executemany(
        "INSERT INTO call_edges VALUES (?, ?, ?, 'exact')",
        [(rowids[n], rowids[n], source) for n in names for source in GUARDED_SELF_EDGE_SOURCES],
    )
    conn.commit()
    conn.close()


## @brief Run the guard over a seeded database and return the surviving callers.
## @param db_path Database to prune.
## @param repo_root Root the indexed path is relative to.
## @return Set of caller rowids that still hold a self-edge.
## @version 1
def _prune(db_path: Path, repo_root: Path) -> set[int]:
    """@brief Execute the guard and report which self-edges survived.

    @return Surviving caller rowids.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    _name_index, file_funcs = _build_function_indexes(conn)
    prune_fabricated_self_edges(conn, repo_root, try_import_tree_sitter(), file_funcs)
    conn.commit()
    survivors = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT caller_rowid FROM call_edges WHERE caller_rowid = callee_rowid"
        ).fetchall()
    }
    conn.close()
    return survivors


def test_bare_self_call_is_kept(tmp_path) -> None:
    """Mechanism 1. `scope._classify` really does contain `_classify(child)`;
    deleting that edge would delete a true fact, which is why a blanket drop of
    self-edges is wrong however much noise sits beside it."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["descend"])
    assert _prune(db, tmp_path) == {rowids["descend"]}


def test_self_rooted_method_recursion_is_kept(tmp_path) -> None:
    """`self.walk(child)` is the ONLY way a Python method can recurse — a bare
    `walk(child)` inside a method does not resolve to the method at all. A rule
    that accepted only bare calls would therefore discard every recursive method
    in every Python codebase, so the receiver has to be inspected, not just the
    presence of a dot."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["walk"])
    assert _prune(db, tmp_path) == {rowids["walk"]}


def test_this_rooted_method_recursion_is_kept(tmp_path) -> None:
    """The C++ half of the same rule: `this->walk(...)` inside `Tree::walk`."""
    db, rowids = _make_db(tmp_path, "fixture.cpp", _CPP_FIXTURE)
    _seed_self_edges(db, rowids, ["walk"])
    assert _prune(db, tmp_path) == {rowids["walk"]}


def test_attribute_call_on_another_object_is_dropped(tmp_path) -> None:
    """Mechanism 2, and the one that proves uniqueness is the wrong test:
    `IndexCache.close` is the ONLY `close` memberdef in clew's index, yet
    `self.conn.close()` is sqlite3's method on a different object. Bound back to
    the wrapper, it reads to a consumer as infinite recursion."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["close"])
    assert _prune(db, tmp_path) == set()


def test_super_init_is_dropped(tmp_path) -> None:
    """Mechanism 3. `super().__init__()` is DOUBLE damage — it fabricates the
    self-edge and loses the real subclass->baseclass edge — so the drop removes
    a false claim without removing a true one that was ever present."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["__init__"])
    assert _prune(db, tmp_path) == set()


def test_caller_with_no_same_named_call_site_is_dropped(tmp_path) -> None:
    """The DOMINANT mechanism, and one the original three-way split missed: 442
    of a C++ codebase's 458 self-edge rows are anonymous-namespace functions that never
    name themselves anywhere, and 21 of clew's 70 are a `main()` invoked from
    a `if __name__ == "__main__":` guard which doxygen files inside `main`. Both
    carry source='doxygen_sqlite', so no change to the AST
    extractor could have reached them."""
    py_db, py_rowids = _make_db(tmp_path / "py", "fixture.py", _PY_FIXTURE)
    _seed_self_edges(py_db, py_rowids, ["main"])
    assert _prune(py_db, tmp_path / "py") == set()

    cpp_db, cpp_rowids = _make_db(tmp_path / "cpp", "fixture.cpp", _CPP_FIXTURE)
    _seed_self_edges(cpp_db, cpp_rowids, ["warn_failure"])
    assert _prune(cpp_db, tmp_path / "cpp") == set()


def test_global_scope_qualified_call_is_dropped(tmp_path) -> None:
    """`::close(fd_)` inside a member named `close` calls POSIX close, not the
    member. Accepting any qualified shape as self-directed would have kept all
    ten of a C++ codebase's `::close()`/`::open()` rows as recursion."""
    db, rowids = _make_db(tmp_path, "fixture.cpp", _CPP_FIXTURE)
    _seed_self_edges(db, rowids, ["close"])
    assert _prune(db, tmp_path) == set()


def test_bare_c_recursion_is_kept(tmp_path) -> None:
    """a C++ codebase's one genuine self-edge shape, kept alongside 442 fabricated rows in
    the same database — the reason the guard has to judge per caller."""
    db, rowids = _make_db(tmp_path, "fixture.cpp", _CPP_FIXTURE)
    _seed_self_edges(db, rowids, ["brace_expand"])
    assert _prune(db, tmp_path) == {rowids["brace_expand"]}


def test_bare_call_in_a_python_method_is_dropped(tmp_path) -> None:
    """gh#30. Python has NO implicit `this`, so a bare `cull(...)` inside a
    method named `cull` cannot reach the method — it names a module-level or
    imported `cull`. `DocsDbServer.cull` is the measured instance: its body's
    bare `cull(self.registry, ...)` is the `state.cull` it imports, and the
    guard kept that self-edge as the eighth of eight "genuine" recursions when
    the other seven were real.

    This is the ONE shape the language-conditional rule removes. Every other
    test in this file pins something it must NOT remove."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["cull"])
    assert _prune(db, tmp_path) == set()


def test_bare_call_in_a_cpp_method_is_kept(tmp_path) -> None:
    """The rule is conditional on the LANGUAGE, not on method-ness: C++ DOES
    have an implicit `this`, so a bare `compact(n - 1)` inside `Buffer::compact`
    is genuine recursion. Dropping it would regress the language the bare-name
    rule was always correct for, which is the risk this whole change carries."""
    db, rowids = _make_db(tmp_path, "fixture.cpp", _CPP_FIXTURE)
    _seed_self_edges(db, rowids, ["compact"])
    assert _prune(db, tmp_path) == {rowids["compact"]}


def test_python_module_level_bare_recursion_is_still_kept(tmp_path) -> None:
    """The other half of the guard against over-reach: the rule keys on the
    enclosing function being a METHOD, not on the file being Python. A
    module-level `descend(child)` is still recursion, so a rule that keyed on
    the file's language alone would delete every recursive free function in
    every Python codebase."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["descend"])
    assert _prune(db, tmp_path) == {rowids["descend"]}


def test_bare_call_in_a_decorated_python_method_is_dropped(tmp_path) -> None:
    """A `@property`/`@staticmethod` sits under an extra `decorated_definition`
    node, so the walk from the function to its owning scope has to step over it.
    Without that step a decorated method reads as module-level and gh#30's rule
    silently stops applying to it — which is most of a real class's surface."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["refresh"])
    assert _prune(db, tmp_path) == set()


def test_self_rooted_recursion_survives_a_bare_call_in_the_same_method(tmp_path) -> None:
    """Per CALL SITE, not per function. `prune` makes both a bare `prune(node)`
    and a real `self.prune(node.next)`; the bare one proves nothing and the
    self-rooted one proves recursion, so the edge stays. A rule that rejected
    the whole method on seeing a bare call would drop a true fact."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["prune"])
    assert _prune(db, tmp_path) == {rowids["prune"]}


def test_verdict_log_identifies_callers_by_rowid(tmp_path, caplog) -> None:
    """gh#30's third requirement. The verdict log used to print BARE names, and
    this repo holds three unrelated `_classify` functions — so `KEPT ...
    _classify` named a symbol a reader could not locate, and was mistaken for
    evidence of gh#26, a different defect in a different layer.

    `name#rowid` is checkable against `memberdef`. Asserting the rowid is
    PRESENT is the whole point: a bare name would satisfy any test that only
    looked for the name."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["descend", "cull"])
    with caplog.at_level(logging.DEBUG, logger="clew"):
        _prune(db, tmp_path)
    text = caplog.text
    assert f"descend#{rowids['descend']}" in text, "a kept caller must carry its rowid"
    assert f"cull#{rowids['cull']}" in text, "a dropped caller must carry its rowid"


def test_unreadable_caller_file_leaves_its_edges_alone(tmp_path) -> None:
    """FAIL CLOSED, and in the direction that matters: a file that will not
    parse is a fact about the DETECTOR, not about the code, so its self-edges
    survive unjudged rather than being deleted on absence of evidence."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["close", "main"])
    (tmp_path / "fixture.py").unlink()
    assert _prune(db, tmp_path) == {rowids["close"], rowids["main"]}


def test_caller_without_a_body_range_is_left_alone(tmp_path) -> None:
    """A declaration-only memberdef has no usable body range, so there is
    nowhere to look for a call site. That is UNVERIFIABLE, not fabricated."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO memberdef (kind, name, file_id, bodyfile_id, bodystart, bodyend) "
        "VALUES ('function', 'declared_only', 1, 1, 0, 0)"
    )
    conn.commit()
    declared_only = conn.execute(
        "SELECT rowid FROM memberdef WHERE name = 'declared_only'"
    ).fetchone()[0]
    conn.close()
    rowids["declared_only"] = declared_only
    _seed_self_edges(db, rowids, ["declared_only"])
    assert _prune(db, tmp_path) == {declared_only}


def test_indirection_layers_are_outside_the_guards_jurisdiction(tmp_path) -> None:
    """`fnptr` and `declared_dispatch` assert an INDIRECTION no call site names —
    a stored function pointer, an author-declared virtual seam — so the
    call-shape rule has no evidence to apply and must not delete them. Neither
    produced a self-edge on either codebase; this pins the intent."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    conn = sqlite3.connect(str(db))
    conn.executemany(
        "INSERT INTO call_edges VALUES (?, ?, ?, 'resolved')",
        [
            (rowids["close"], rowids["close"], CALL_SOURCE_FNPTR),
            (rowids["main"], rowids["main"], CALL_SOURCE_DECLARED_DISPATCH),
        ],
    )
    conn.commit()
    conn.close()
    assert _prune(db, tmp_path) == {rowids["close"], rowids["main"]}


def test_non_self_edges_are_untouched(tmp_path) -> None:
    """The guard's whole jurisdiction is the diagonal. An ordinary edge in the
    same layers must survive byte for byte, including a `main -> descend` edge
    whose caller IS a pruned self-edge caller."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["main", "close"])
    conn = sqlite3.connect(str(db))
    conn.execute(
        "INSERT INTO call_edges VALUES (?, ?, ?, 'exact')",
        (rowids["main"], rowids["descend"], CALL_SOURCE_DOXYGEN_SQLITE),
    )
    conn.commit()
    conn.close()
    _prune(db, tmp_path)
    conn = sqlite3.connect(str(db))
    remaining = conn.execute("SELECT caller_rowid, callee_rowid, source FROM call_edges").fetchall()
    conn.close()
    assert remaining == [(rowids["main"], rowids["descend"], CALL_SOURCE_DOXYGEN_SQLITE)]


def test_self_directed_sites_reads_shape_not_name(tmp_path) -> None:
    """Unit-level statement of the rule the mechanisms above exercise: a bare
    call and a `self.`-rooted call are self-directed; `self.conn.close()`,
    `super().__init__()` and `::close()` are not."""
    tree, src = _parse(tmp_path, "fixture.py", _PY_FIXTURE)
    names = {name for name, _line in _self_directed_sites(tree, src)}
    assert {"descend", "walk"} <= names
    assert "close" not in names, "self.conn.close() has a receiver of its own"
    assert "__init__" not in names, "super().__init__() is not rooted at self"

    tree, src = _parse(tmp_path, "fixture.cpp", _CPP_FIXTURE)
    names = {name for name, _line in _self_directed_sites(tree, src)}
    assert {"walk", "brace_expand", "log_warn"} <= names
    assert "close" not in names, "::close() is the global-scope function"


def test_end_to_end_layer3_prunes_what_it_and_doxygen_wrote(tmp_path) -> None:
    """The wiring: `import_ast_call_edges` runs the guard itself, so a build
    that reaches Layer 3 is guarded with no pipeline-driver change — and a build
    without tree-sitter skips both together rather than pruning unguarded.

    Also the end-to-end statement of gh#30: Layer 3 does not merely INHERIT the
    fabricated `cull` self-edge from doxygen, it MANUFACTURES one, because the
    bare `cull(registry)` resolves by name straight back onto the method. So the
    guard is the only thing standing between that call site and a self-edge, and
    `cull` must be absent from the survivors while `prune` — which really does
    call `self.prune` — is present."""
    db, rowids = _make_db(tmp_path, "fixture.py", _PY_FIXTURE)
    _seed_self_edges(db, rowids, ["main", "close", "__init__", "descend", "walk", "cull", "prune"])
    import_ast_call_edges(db, tmp_path, None)
    conn = sqlite3.connect(str(db))
    survivors = {
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT caller_rowid FROM call_edges WHERE caller_rowid = callee_rowid"
        ).fetchall()
    }
    conn.close()
    assert survivors == {rowids["descend"], rowids["walk"], rowids["prune"]}
    assert rowids["cull"] not in survivors, "a bare call in a Python method is not recursion"
