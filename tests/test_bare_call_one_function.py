# SPDX-License-Identifier: MIT
"""A bare call to a function the index holds twice — its prototype and its definition.

`_ast_record_call_edge` resolves a bare identifier only when the callee name matches ONE
memberdef row. A C function declared in a header and defined in a source file is two rows, so
every bare call to it was refused, and `_collapse_duplicate_targets` — the post-pass that knows a
decl/def pair is one function — only ever sees the receiver-verified member calls.

Two shapes, both measured on public mbedtls (068ff080b369, `clew --rebuild` over the whole tree):

- doxygen wrote both rows (`mbedtls_platform_zeroize`): the pair shares an identity, the call
  is refused, and the refusal is counted — 0 edges, 244 unresolved inbound sites.
- doxygen's preprocessor skipped the definition and `recover_ast_symbols` added it
  (`mbedtls_aes_crypt_ecb`, `mbedtls_aes_free`): the recovered row stores `definition` as the
  bare declarator and `argsstring` with the source's line breaks, while doxygen's row reads
  `MBEDTLS_CHECK_RETURN_TYPICAL int mbedtls_aes_crypt_ecb` with normalized arguments. The
  identities differ, so the call earned no edge AND no unresolved count: an empty `callers`
  that read as a measured negative.

@brief Tests for resolving bare calls to a decl/def pair.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from richdb import DOXYGEN_SCHEMA

from clew.ast_symbols import recover_ast_symbols
from clew.call_edges import (
    SOURCE_AST,
    SOURCE_AST_MEMBER,
    _ast_record_call_edge,
    _function_identities,
    _one_function_targets,
    build_call_edges,
    import_ast_call_edges,
)

_HEADER = """\
#define CHECK_RETURN
CHECK_RETURN int lib_fn(int a,
                        char *b);
"""

## The definition sits under a guard nothing defines, which is the shape that makes doxygen
## skip it and `recover_ast_symbols` add it.
_GUARDED_SOURCE = """\
#include "lib.h"
#if defined(LIB_FEATURE)
int lib_fn(int a,
           char *b)
{
    return a + (b != 0);
}
#endif
"""

_PLAIN_SOURCE = """\
#include "lib.h"
int lib_fn(int a, char *b)
{
    return a + (b != 0);
}
"""

_CALLER = """\
#include "lib.h"
int use_it(void)
{
    return lib_fn(1, 0);
}
"""

## path rowids for the fixture files.
_H, _C, _CALLER_C = 1, 2, 3


## @brief Write a repository and seed the doxygen half of its index.
## @param tmp_path Test temporary directory.
## @param source The text of lib.c.
## @param rows memberdef rows (rowid, name, definition, args, bodystart, bodyend, bodyfile, file).
## @return (repo root, database path).
## @version 1
def _build(tmp_path: Path, source: str, rows: list[tuple]) -> tuple[Path, Path]:
    """@brief Lay down lib.h / lib.c / caller.c and the doxygen rows describing them.

    @return (repo, db).
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "lib.h").write_text(_HEADER, encoding="utf-8")
    (repo / "lib.c").write_text(source, encoding="utf-8")
    (repo / "caller.c").write_text(_CALLER, encoding="utf-8")
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(DOXYGEN_SCHEMA.read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT INTO path (rowid, type, local, found, name) VALUES (?, 1, 1, 1, ?)",
        [(_H, "lib.h"), (_C, "lib.c"), (_CALLER_C, "caller.c")],
    )
    for rowid, name, definition, args, start, end, bodyfile, file_id in rows:
        conn.execute("INSERT INTO refid (rowid, refid) VALUES (?, ?)", (rowid, f"fx_{rowid}"))
        conn.execute(
            "INSERT INTO memberdef (rowid, name, definition, argsstring, kind, static, "
            'bodystart, bodyend, bodyfile_id, file_id, line, "column") '
            "VALUES (?, ?, ?, ?, 'function', 0, ?, ?, ?, ?, 1, 1)",
            (rowid, name, definition, args, start, end, bodyfile, file_id),
        )
    conn.commit()
    conn.close()
    return repo, db


## @brief The (caller, callee) pairs a build wrote for one callee name.
## @param db The built database.
## @param callee The callee's name.
## @return Sorted (caller name, callee rowid, source) triples.
## @version 1
def _edges_to(db: Path, callee: str) -> list[tuple[str, int, str]]:
    """@brief Read the call edges into a named callee.

    @return The edges.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return sorted(
            conn.execute(
                "SELECT c.name, e.callee_rowid, e.source FROM call_edges e "
                "JOIN memberdef c ON c.rowid = e.caller_rowid "
                "JOIN memberdef m ON m.rowid = e.callee_rowid WHERE m.name = ?",
                (callee,),
            ).fetchall()
        )
    finally:
        conn.close()


## The prototype doxygen writes for the header, and the caller.
_PROTOTYPE = (10, "lib_fn", "CHECK_RETURN int lib_fn", "(int a, char *b)", None, None, None, _H)
_USE_IT = (20, "use_it", "int use_it", "(void)", 2, 5, _CALLER_C, _CALLER_C)


def test_a_bare_call_reaches_a_RECOVERED_definition(tmp_path: Path) -> None:
    """THE REPORTED SHAPE. doxygen saw the prototype and not the definition, so the only
    definition row is the one `recover_ast_symbols` wrote, spelled the way the source spells it.
    The call is to the one function both rows describe, and it must land on the row with the
    body."""
    repo, db = _build(tmp_path, _GUARDED_SOURCE, [_PROTOTYPE, _USE_IT])
    assert recover_ast_symbols(db, repo) >= 1, "premise: the guarded definition is recovered"
    build_call_edges(db)
    import_ast_call_edges(db, repo)
    conn = sqlite3.connect(str(db))
    recovered = conn.execute(
        "SELECT rowid FROM memberdef WHERE name = 'lib_fn' AND dg_source = 'ast'"
    ).fetchone()[0]
    conn.close()
    assert _edges_to(db, "lib_fn") == [("use_it", recovered, SOURCE_AST)]


def test_a_bare_call_reaches_a_pair_doxygen_wrote_both_halves_of(tmp_path: Path) -> None:
    """THE OTHER SHAPE. doxygen copies the definition's body range onto the header row, so both
    rows carry one body and one identity. The edge goes to the definition — the row whose own
    file holds the body."""
    definition = (11, "lib_fn", "int lib_fn", "(int a, char *b)", 2, 5, _C, _C)
    header = (10, "lib_fn", "int lib_fn", "(int a, char *b)", 2, 5, _C, _H)
    repo, db = _build(tmp_path, _PLAIN_SOURCE, [header, definition, _USE_IT])
    build_call_edges(db)
    import_ast_call_edges(db, repo)
    assert _edges_to(db, "lib_fn") == [("use_it", 11, SOURCE_AST)]


def test_the_two_spellings_of_one_function_share_an_identity(tmp_path: Path) -> None:
    """The prototype's `definition` carries the return type and any annotation macro; the
    recovered row's carries only the declarator, and its arguments keep the source's line
    breaks. Neither difference is a difference in WHICH function — so the identity is the
    declared name and the whitespace-free parameter list."""
    _repo, db = _build(
        tmp_path,
        _PLAIN_SOURCE,
        [
            _PROTOTYPE,
            (11, "lib_fn", "lib_fn", "(int a,\n           char *b)", 2, 5, _C, _C),
        ],
    )
    conn = sqlite3.connect(str(db))
    identity_of, _defined = _function_identities(conn)
    conn.close()
    assert identity_of[10] == identity_of[11], identity_of


def test_a_different_parameter_list_is_a_different_function(tmp_path: Path) -> None:
    """THE CONTROL on the identity. Whitespace is dropped; the parameters are not."""
    _repo, db = _build(
        tmp_path,
        _PLAIN_SOURCE,
        [_PROTOTYPE, (11, "lib_fn", "lib_fn", "(int a, long b)", 2, 5, _C, _C)],
    )
    conn = sqlite3.connect(str(db))
    identity_of, _defined = _function_identities(conn)
    conn.close()
    assert identity_of[10] != identity_of[11], identity_of


def test_a_qualified_definition_is_not_merged_with_another_class() -> None:
    """The return type is dropped from the identity, the qualifier is not: `A::run` and `B::run`
    with one parameter list stay two functions, which is the line `_collapse_duplicate_targets`
    already holds for receiver-verified calls."""
    conn = sqlite3.connect(":memory:")
    conn.executescript(DOXYGEN_SCHEMA.read_text(encoding="utf-8"))
    conn.executemany(
        "INSERT INTO memberdef (rowid, name, definition, argsstring, kind, bodystart, file_id, "
        "line, \"column\") VALUES (?, 'run', ?, '(int)', 'function', 0, 1, 1, 1)",
        [(1, "void ns::A::run"), (2, "void ns::B::run")],
    )
    identity_of, _defined = _function_identities(conn)
    assert identity_of[1] != identity_of[2], identity_of


def test_two_bodies_with_one_signature_are_still_refused() -> None:
    """THE CONTROL on the resolution. Two `static int helper(void)` definitions in two files
    share an identity and are still two functions; a name cannot say which one a call meant, so
    the call is refused exactly as before (gh#347) and the refusal is recorded."""
    identity = ("helper", "helper", "(void)")
    targets = _one_function_targets(
        {"helper": [30, 31]},
        {30: identity, 31: identity},
        {30: (1, 10), 31: (2, 10)},
        homes={30, 31},
    )
    assert targets == {}, "two bodies are two functions"
    resolved: list[tuple[int, int, str]] = []
    unresolved: list[list[int]] = []
    _ast_record_call_edge(
        1,
        "helper",
        {"helper": [30, 31]},
        resolved,
        [],
        SOURCE_AST,
        unresolved=unresolved,
        one_function=targets,
    )
    assert resolved == [] and unresolved == [[30, 31]]


def test_a_member_call_is_not_resolved_by_the_pair_alone() -> None:
    """THE CONTROL on the source. `obj.lib_fn()` names a function of that name and says nothing
    about the receiver; the unverified-receiver refusal holds whether the name has one row or a
    decl/def pair."""
    identity = ("lib_fn", "lib_fn", "(inta,char*b)")
    targets = _one_function_targets(
        {"lib_fn": [10, 11]}, {10: identity, 11: identity}, {11: (2, 2)}, homes={11}
    )
    assert targets == {(10, 11): 11}, "premise: the pair is one function"
    resolved: list[tuple[int, int, str]] = []
    _ast_record_call_edge(
        1, "lib_fn", {"lib_fn": [10, 11]}, resolved, [], SOURCE_AST_MEMBER, one_function=targets
    )
    assert resolved == []
