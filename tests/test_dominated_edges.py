# SPDX-License-Identifier: MIT
"""Dominated-fuzzy suppression (gh#26): the AST name fan-out goes, real edges stay.

The two tests that matter here pull in OPPOSITE directions, and the second one
matters more.

`test_fabricated_fanout_row_is_deleted` is the defect: this repo has four
module-private `_table_exists` helpers, so an `ast` layer that resolves callees by
name attributes all four to any caller of one. When a stronger layer has already
named which one, the other three are fabrications.

`test_caller_of_two_same_named_functions_keeps_both` is the FALSE-DELETION GUARD,
and it is the reason the rule is anchored per (caller, name) group rather than
being a blanket "prefer non-fuzzy". A caller genuinely calling two same-named
functions was objection 1 to shipping this at all. It is admitted here as a
specification: when a non-fuzzy layer confirms BOTH callees, both survive, because
each is its own anchor.

The remaining tests pin the three exemptions, each of which exists because the
version without it was wrong: same-identity rows (they name the relationship the
anchor already names, so deleting them removes real rows rather than
fabrications), doxygen-recorded virtual overrides of an anchor (template-method
dispatch, where the fan-out row is the only edge reaching the derived override),
and the non-AST `fuzzy` sources that encode a deliberate multi-candidate
dispatch.

@brief Tests for the gh#26 dominated-fuzzy call-edge suppression.
@version 1
"""

from __future__ import annotations

import sqlite3

import pytest

from clew.dominated_edges import prune_dominated_fuzzy_edges
from clew.vocabulary import (
    CALL_MATCH_EXACT,
    CALL_MATCH_FUZZY,
    CALL_MATCH_RESOLVED,
    CALL_SOURCE_AST,
    CALL_SOURCE_AST_MEMBER,
    CALL_SOURCE_DECLARED_DISPATCH,
    CALL_SOURCE_DOXYGEN_SQLITE,
)


## @brief Build a minimal index holding just memberdef, call_edges and reimplements.
## @param functions (rowid, name, definition) triples to insert as memberdef rows.
## @param edges (caller, callee, source, confidence) call-edge rows.
## @param reimplements (derived rowid, base rowid) override relations.
## @return Open in-memory connection.
## @version 1
def _index(
    functions: list[tuple[int, str, str]],
    edges: list[tuple[int, int, str, str]],
    reimplements: list[tuple[int, int]] | None = None,
) -> sqlite3.Connection:
    """Hand-built rather than driven through a real doxygen run, because the rule
    under test is a pure function of (identity, edge, override) and a real build
    would make the fixture's INTENT — which rows are namesakes — invisible.

    `definition` carries the qualified name exactly as doxygen writes it: the
    qualified name in the last whitespace-separated token, the argument list in a
    separate column. `qualified_name_of` reads that shape.

    @brief Assemble a minimal in-memory index for the suppression pass.
    @return Connection with memberdef, call_edges and reimplements populated.
    @version 1
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, definition TEXT)")
    conn.execute(
        "CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, "
        "source TEXT, confidence TEXT, UNIQUE(caller_rowid, callee_rowid, source))"
    )
    conn.execute("CREATE TABLE reimplements (memberdef_rowid INTEGER, reimplemented_rowid INTEGER)")
    conn.executemany("INSERT INTO memberdef VALUES (?, ?, ?)", functions)
    conn.executemany("INSERT INTO call_edges VALUES (?, ?, ?, ?)", edges)
    conn.executemany("INSERT INTO reimplements VALUES (?, ?)", reimplements or [])
    return conn


## @brief The surviving (caller, callee, source) rows, sorted.
## @param conn Open connection.
## @return Sorted list of remaining call-edge keys.
## @version 1
def _rows(conn: sqlite3.Connection) -> list[tuple[int, int, str]]:
    """@brief Read back the surviving call-edge keys.
    @return Sorted (caller, callee, source) triples.
    @version 1
    """
    return sorted(
        (c, e, s)
        for c, e, s in conn.execute("SELECT caller_rowid, callee_rowid, source FROM call_edges")
    )


## Three unrelated module-private helpers sharing a bare name — ordinary Python, and
## the shape gh#26 was reported against. 10 is the caller; 40 an unrelated namesake
## used as a second anchor where a test needs one.
_HELPERS = [
    (10, "import_macro_hop_edges", "None pkg.call_edges.import_macro_hop_edges"),
    (11, "_table_exists", "bool pkg.call_edges._table_exists"),
    (12, "_table_exists", "bool pkg.ast_symbols._table_exists"),
    (13, "_table_exists", "bool pkg.requirements._table_exists"),
]


## @brief A fuzzy row to a namesake the non-fuzzy anchor disproves is deleted.
## @version 1
def test_fabricated_fanout_row_is_deleted() -> None:
    """The core gh#26 claim, asserted as an ABSENCE. doxygen resolved the call to
    `call_edges._table_exists`; the `ast` layer additionally fanned it out to the
    two namesakes in other modules, which cannot see a module-private helper.

    @brief Fabricated fan-out rows are removed when an anchor names the real callee.
    @version 1
    """
    conn = _index(
        _HELPERS,
        [
            (10, 11, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (10, 11, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
            (10, 12, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
            (10, 13, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
    )
    assert prune_dominated_fuzzy_edges(conn) == 2
    assert _rows(conn) == [
        (10, 11, CALL_SOURCE_AST),
        (10, 11, CALL_SOURCE_DOXYGEN_SQLITE),
    ]


## @brief A caller genuinely calling TWO same-named functions keeps both edges.
## @version 1
def test_caller_of_two_same_named_functions_keeps_both() -> None:
    """THE FALSE-DELETION GUARD, and the test to break first when changing this rule.

    Objection 1 to shipping gh#26's fix was that a caller may legitimately call two
    functions that share a name. It does not follow that the rule must spare every
    guess: it follows that a CONFIRMED callee must never be deleted because a
    DIFFERENT confirmed callee exists. Both callees here carry non-fuzzy evidence,
    so both are anchors of their group and neither can dominate the other.

    Note what is deliberately NOT asserted — that the third, unconfirmed namesake
    survives. It is deleted, and that is the intended behaviour: two layers looked
    at this call site and named two specific functions, neither of which was the
    third.

    @brief Two confirmed same-named callees both survive.
    @version 1
    """
    conn = _index(
        _HELPERS,
        [
            (10, 11, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (10, 12, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (10, 11, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
            (10, 12, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
            (10, 13, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
        ],
    )
    assert prune_dominated_fuzzy_edges(conn) == 1
    survivors = _rows(conn)
    assert (10, 11, CALL_SOURCE_DOXYGEN_SQLITE) in survivors
    assert (10, 12, CALL_SOURCE_DOXYGEN_SQLITE) in survivors
    assert (10, 11, CALL_SOURCE_AST_MEMBER) in survivors, "confirmed callee lost its AST row"
    assert (10, 12, CALL_SOURCE_AST_MEMBER) in survivors, "confirmed callee lost its AST row"
    assert (10, 13, CALL_SOURCE_AST_MEMBER) not in survivors


## @brief With no non-fuzzy anchor in the group, the whole fan-out survives.
## @version 1
def test_unanchored_fanout_is_left_alone() -> None:
    """The answer to objection 2 — that C++ member edges are mostly fuzzy by
    construction, so a rule preferring non-fuzzy could empty a C++ graph. It cannot,
    because with nothing to dominate the guess the guess is all the evidence there
    is, and `fuzzy` already says what it is worth. Measured on entropic: 25,162 of
    29,880 rows are fuzzy and only 539 sit in an anchored group.

    @brief An unanchored fan-out group is untouched.
    @version 1
    """
    conn = _index(
        _HELPERS,
        [
            (10, 11, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
            (10, 12, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
            (10, 13, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
        ],
    )
    assert prune_dominated_fuzzy_edges(conn) == 0
    assert len(_rows(conn)) == 3


## @brief A fuzzy row naming the anchor's OWN identity is kept.
## @version 2
def test_same_identity_row_is_kept() -> None:
    """Same function, weaker layer: the row names the relationship the anchor
    already names, so it is not a fan-out artefact. An earlier draft deleted them
    as redundant duplicates, which removes real rows while the row count looks
    healthier.

    Also pins decl/def duality: rowid 14 is the DECLARATION of the same function as
    rowid 11, so it shares a qualified name and must not read as a namesake.

    @brief Same-identity and decl/def rows survive.
    @version 2
    """
    conn = _index(
        [*_HELPERS, (14, "_table_exists", "bool pkg.call_edges._table_exists")],
        [
            (10, 11, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (10, 11, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
            (10, 14, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
    )
    assert prune_dominated_fuzzy_edges(conn) == 0
    assert len(_rows(conn)) == 3


## @brief A virtual override of the anchor survives; an unrelated namesake does not.
## @version 1
def test_virtual_override_of_the_anchor_is_kept() -> None:
    """Template-method dispatch: a base `generate()` calls the protected virtual
    `do_generate()`, and the real dynamic target is the derived override. The
    fan-out row is the ONLY edge that reaches it, so deleting it would remove
    genuine dispatch reach — 48 rows of exactly this shape on entropic.

    The control is in the same test: an unrelated `do_generate` on a class with no
    override relation is still deleted, so the exemption is doxygen's `reimplements`
    relation and not merely "spare anything that shares a name".

    @brief A reimplements-linked override is exempt; an unrelated namesake is not.
    @version 1
    """
    conn = _index(
        [
            (20, "generate", "Result Backend::generate"),
            (21, "do_generate", "Result Backend::do_generate"),
            (22, "do_generate", "Result LlamaBackend::do_generate"),
            (23, "do_generate", "Result UnrelatedThing::do_generate"),
        ],
        [
            (20, 21, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (20, 22, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
            (20, 23, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
        reimplements=[(22, 21)],
    )
    assert prune_dominated_fuzzy_edges(conn) == 1
    survivors = _rows(conn)
    assert (20, 22, CALL_SOURCE_AST) in survivors, "virtual override lost its only edge"
    assert (20, 23, CALL_SOURCE_AST) not in survivors


## @brief A deliberate multi-candidate dispatch row is never second-guessed.
## @version 1
def test_declared_dispatch_fuzzy_row_is_never_deleted() -> None:
    """`declared_dispatch` and `fnptr` emit `fuzzy` to encode that an author's
    declaration named several possible targets. That row IS the answer, not a name
    guess, so the pass must not touch it even inside an anchored group — deleting it
    would break declared dispatch while every `ast` row around it was handled
    correctly.

    @brief Non-AST fuzzy sources are out of the pass's jurisdiction.
    @version 1
    """
    conn = _index(
        _HELPERS,
        [
            (10, 11, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (10, 12, CALL_SOURCE_DECLARED_DISPATCH, CALL_MATCH_FUZZY),
        ],
    )
    assert prune_dominated_fuzzy_edges(conn) == 0
    assert (10, 12, CALL_SOURCE_DECLARED_DISPATCH) in _rows(conn)


## @brief An anchor supplied by a LATER layer still dominates the fan-out.
## @version 1
def test_a_resolved_anchor_from_any_layer_counts() -> None:
    """Why the stage sits below every call-edge layer rather than inside Layer 3:
    the anchor may be 'resolved' from `macro_hop`, `fnptr` or the declared-dispatch
    layer, all of which run after the AST walk. Judged too early, this row would be
    spared by a layer that had not spoken yet.

    @brief 'resolved' confidence anchors as well as 'exact'.
    @version 1
    """
    conn = _index(
        _HELPERS,
        [
            (10, 11, CALL_SOURCE_DECLARED_DISPATCH, CALL_MATCH_RESOLVED),
            (10, 12, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
    )
    assert prune_dominated_fuzzy_edges(conn) == 1
    assert (10, 12, CALL_SOURCE_AST) not in _rows(conn)


## @brief A memberdef with no `definition` column deletes nothing, rather than raising.
## @version 1
def test_schema_without_definition_column_deletes_nothing() -> None:
    """Fail CLOSED on a thin schema. Without `definition` every namesake collapses
    to one identity, so no group has a non-anchor member and a destructive stage
    removes nothing — the right direction for a pass that cannot tell namesakes
    apart. Several fixtures elsewhere hand-build a `memberdef` with only the columns
    their own assertion needs, and a bare `SELECT definition` would raise at them
    from a layer they are not exercising.

    @brief A definition-less schema is inert, not fatal.
    @version 1
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT)")
    conn.execute(
        "CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, "
        "source TEXT, confidence TEXT)"
    )
    conn.executemany(
        "INSERT INTO memberdef VALUES (?, ?)",
        [(10, "caller"), (11, "_table_exists"), (12, "_table_exists")],
    )
    conn.executemany(
        "INSERT INTO call_edges VALUES (?, ?, ?, ?)",
        [
            (10, 11, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (10, 12, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
    )
    assert prune_dominated_fuzzy_edges(conn) == 0


## @brief An index with no call_edges table returns 0 instead of failing the build.
## @version 1
def test_missing_call_edges_table_is_not_fatal() -> None:
    """@brief A thin index skips the stage rather than raising.
    @version 1
    """
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, definition TEXT)")
    assert prune_dominated_fuzzy_edges(conn) == 0


## @brief The verdict log names all four outcomes, including the ones that are zero.
## @version 2
def test_verdict_log_names_every_exemption(caplog: pytest.LogCaptureFixture) -> None:
    """A silent exemption is indistinguishable from one that never fires, and both
    exemptions here exist because the version without them was wrong. The log has to
    let a reader see that they fired.

    @brief The log reports kept-same-identity, kept-override and kept-unanchored.
    @version 2
    """
    conn = _index(
        _HELPERS,
        [
            (10, 11, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (10, 11, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
            (10, 12, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
    )
    with caplog.at_level("INFO", logger="clew"):
        prune_dominated_fuzzy_edges(conn)
    message = caplog.text
    assert "deleted 1 fan-out row" in message
    assert "same-identity" in message
    assert "override" in message
    assert "unanchored" in message
