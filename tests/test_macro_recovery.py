# SPDX-License-Identifier: MIT
"""gh#403 — the `#define` branch doxygen's preprocessor cannot reach.

WHAT THE GRID MEASURED. mbedtls's graded Q2 asks "the same struct member has two
different names: which, why, and who gets which", and the repository answers it in six
lines of `include/mbedtls/private_access.h`:

    #ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS
    #define MBEDTLS_PRIVATE(member) private_##member    /* line 15 */
    #else
    #define MBEDTLS_PRIVATE(member) member              /* line 17 */
    #endif

doxygen evaluates the `#ifndef`, takes the true branch and never emits line 17, so the
index held one of the two spellings. The 2026-08-12 index arm spent **14.6% MORE tokens**
than reading source, at identical completeness, and read source **8-9 times per run** —
with every one of those reads on two of three runs following a `dossier` that RETURNED
ROWS. A payload gap, not a recall gap.

## WHY THE FIXTURE IS A REAL FILE AND BOTH STAGES ACTUALLY RUN

The answer needs two layers that were built separately and have never been asked to
agree: `ast_symbols` says a `#define` exists at line 17, and `kconfig_gates` says which
branch line 17 sits in. Each has its own notion of a line number — one from
`node.start_point`, one from a gate's recorded extent — and a hand-written database
would let both be wrong in the same direction and still pass. So the fixture is source
text on disk, both stages run for real, and the assertion is read back through
`macro_definitions_conn`, which is the query the served payload uses.

## WHY EVERY POLARITY ASSERTION IS TWO-SIDED

An implementation that attaches every gate in the file to every line satisfies "line 15
is gated by the `#ifndef`" and "line 17 is gated by the `#ifdef`" simultaneously, and
answers the question exactly backwards half the time. Each site is therefore asserted to
report its own form AND to NOT report the other one.

## WHY THE DEDUP ASSERTION FILTERS ON PROVENANCE

A presence check cannot tell a recovered row from an emitted one — the recorded trap
where a recovery layer makes a later test pass for the wrong reason. The doxygen-sourced
count is what must not move, so `dg_source` is in every WHERE clause that counts.
Measured on the real target either side of this change: `macro definition` +
`dg_source='doxygen'` is **2,504 both times**, with 2,916 `dg_source='ast'` rows added.

@brief Tests for macro-definition recovery and per-site gate polarity.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.ast_symbols import harvest_macro_definitions, recover_ast_symbols
from clew.harvest import _ast_parse_one_file, try_import_tree_sitter
from clew.kconfig_gates import import_kconfig_gates
from clew.query import dossier
from clew.query.macros import MACRO_KIND, macro_definitions
from clew.vocabulary import (
    KCONFIG_GATE_IFDEF,
    KCONFIG_GATE_IFNDEF,
    SYMBOL_SOURCE_AST,
    SYMBOL_SOURCE_DOXYGEN,
)

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None, reason="tree-sitter is not installed"
)

## THE EXACT SHAPE, transcribed from `include/mbedtls/private_access.h` including the
## include guard above it — which is why the `#define` line numbers below are 15 and 17
## rather than 3 and 5. Keeping the real offsets means the numbers in this file are the
## numbers in the probe output and in the issue, so a reader comparing them is not also
## translating between two coordinate systems.
PRIVATE_ACCESS_H = """\
/*
 *  Macro wrapper for struct's members.
 *
 *  Copyright placeholder — this fixture reproduces a real header's SHAPE, not its text.
 */

#ifndef MBEDTLS_PRIVATE_ACCESS_H
#define MBEDTLS_PRIVATE_ACCESS_H

/* line 10 */
/* line 11 */
/* line 12 */
/* line 13 */
#ifndef ALLOW_PRIVATE_ACCESS
#define PRIVATE(member) private_##member
#else
#define PRIVATE(member) member
#endif

#endif /* MBEDTLS_PRIVATE_ACCESS_H */
"""

## The two lines the whole issue is about. Named rather than repeated, because they
## appear in six assertions and a transcription slip in one of them would read as a
## behaviour difference between two sites.
GATED_LINE = 15
ELSE_LINE = 17

HEADER = "include/private_access.h"


## @brief A repo whose one header carries the two-branch conditional `#define`.
## @param tmp_path pytest's per-test temp directory.
## @return Path to the repo root.
## @version 1
@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """@brief Write the fixture header to a temp repo.
    @return Repo root.
    @version 1
    """
    root = tmp_path / "repo"
    (root / "include").mkdir(parents=True)
    (root / HEADER).write_text(PRIVATE_ACCESS_H, encoding="utf-8")
    return root


## @brief A doxygen-shaped index holding ONLY the branch doxygen would have taken.
## @param tmp_path pytest's per-test temp directory.
## @param repo The fixture repo the paths are relative to.
## @return Path to the database.
## @version 1
@pytest.fixture
def taken_branch_index(tmp_path: Path, repo: Path) -> Path:
    """SEEDED WITH THE ROW DOXYGEN REALLY WRITES, down to `bodystart=15, bodyend=-1` and
    `bodyfile_id` set — which is not decoration. That half-open body span is why the macro
    dedup cannot reuse the function rule: an overlap test against `[15, -1]` behaves
    nothing like a body. A fixture with a NULL span would let a span-based dedup pass here
    and drop the `#else` branch on the real target.

    `dg_source` is created here rather than left to `ensure_symbol_provenance`, so the
    seeded row is unambiguously labelled `doxygen` before recovery runs and the counting
    assertions have a fixed baseline.

    @brief Build an index carrying one doxygen macro row at the gated line.
    @return Database path.
    @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE refid (rowid INTEGER PRIMARY KEY AUTOINCREMENT, refid TEXT UNIQUE);
        CREATE TABLE path (rowid INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, name TEXT, definition TEXT, argsstring TEXT,
            type TEXT, kind TEXT, static INTEGER, bodystart INTEGER, bodyend INTEGER,
            bodyfile_id INTEGER, file_id INTEGER, line INTEGER, "column" INTEGER,
            initializer TEXT, briefdescription TEXT, detaileddescription TEXT,
            dg_source TEXT NOT NULL DEFAULT 'doxygen'
        );
        CREATE TABLE param (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT, attributes TEXT, type TEXT,
            declname TEXT, defname TEXT, array TEXT, defval TEXT, briefdescription TEXT
        );
        CREATE TABLE memberdef_param (
            rowid INTEGER PRIMARY KEY AUTOINCREMENT, memberdef_id INTEGER, param_id INTEGER
        );
        """
    )
    conn.execute("INSERT INTO refid (rowid, refid) VALUES (900, 'dox_private')")
    conn.execute("INSERT INTO path (rowid, name, type) VALUES (1, ?, 1)", (HEADER,))
    conn.execute(
        "INSERT INTO memberdef (rowid, name, kind, static, bodystart, bodyend, "
        'bodyfile_id, file_id, line, "column", initializer, briefdescription, '
        "detaileddescription, dg_source) "
        "VALUES (900, 'PRIVATE', ?, 0, ?, -1, 1, 1, ?, 9, 'private_##member', '', '', ?)",
        (MACRO_KIND, GATED_LINE, GATED_LINE, SYMBOL_SOURCE_DOXYGEN),
    )
    conn.execute("INSERT INTO param (rowid, defname) VALUES (500, 'member')")
    conn.execute("INSERT INTO memberdef_param (memberdef_id, param_id) VALUES (900, 500)")
    conn.commit()
    conn.close()
    return db


## @brief Count macro rows for one name at one provenance.
## @param db The index.
## @param source The `dg_source` value to count.
## @return Row count.
## @version 1
def _macro_rows(db: Path, source: str) -> int:
    """PROVENANCE IS IN THE WHERE CLAUSE, never inferred from a count. A recovery layer
    answers presence checks for the layer under test — the recorded trap — so a count that
    does not name the layer it means cannot distinguish "doxygen still has its row" from
    "something has a row".

    @brief Count `PRIVATE` macro rows written by one layer.
    @return Count.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM memberdef WHERE name='PRIVATE' AND kind=? AND dg_source=?",
                (MACRO_KIND, source),
            ).fetchone()[0]
        )
    finally:
        conn.close()


# ─── part 1: the harvest reads both branches ─────────────────────────────────


def test_the_harvest_reads_both_branches_of_a_conditional_define(repo: Path) -> None:
    """The parser has no preprocessor, so BOTH `#define`s are ordinary nodes to it. This
    is the premise of the whole change and it is asserted before anything is stored: if
    the walk saw one, no dedup rule downstream could recover the other."""
    ts_classes = try_import_tree_sitter()
    language_cls, parser_cls = ts_classes
    parsed = _ast_parse_one_file(HEADER, repo / HEADER, {}, parser_cls, language_cls)
    assert parsed is not None
    tree, src = parsed

    macros = {(m.name, m.line): m for m in harvest_macro_definitions(tree, src)}
    assert macros[("PRIVATE", GATED_LINE)].expansion == "private_##member"
    assert macros[("PRIVATE", ELSE_LINE)].expansion == "member"
    ## The parameter list, on BOTH sites. A function-like macro is a
    ## `preproc_function_def` with a `parameters` field; a walk that accepted only
    ## `preproc_def` would report every object-like `#define` in the repo and miss the one
    ## symbol this exists for, and a `preproc_params` read that took every child would
    ## return the parentheses as parameters.
    assert macros[("PRIVATE", GATED_LINE)].params == ("member",)
    assert macros[("PRIVATE", ELSE_LINE)].params == ("member",)
    ## The include guard is an OBJECT-like define with no value, and it is recovered
    ## rather than special-cased — recognising the idiom would be one more heuristic on a
    ## walk whose whole value is that a `#define` is unambiguous.
    assert macros[("MBEDTLS_PRIVATE_ACCESS_H", 8)].expansion == ""
    assert macros[("MBEDTLS_PRIVATE_ACCESS_H", 8)].params == ()


# ─── part 2: the row doxygen already has is not duplicated ───────────────────


def test_the_else_branch_is_recovered_and_doxygens_own_row_is_untouched(
    taken_branch_index: Path, repo: Path
) -> None:
    """THE DEDUP CONTROL, and the assertion that matters is the FIRST one: doxygen's own
    macro row count must not move. Measured the same way on the real target across this
    change — 2,504 either side — because that holds whatever the dedup rule does, where an
    assertion about the rule only holds if the rule is the one being read."""
    assert _macro_rows(taken_branch_index, SYMBOL_SOURCE_DOXYGEN) == 1

    recover_ast_symbols(taken_branch_index, repo, None)

    assert _macro_rows(taken_branch_index, SYMBOL_SOURCE_DOXYGEN) == 1, (
        "recovery must not add, replace or relabel a row doxygen emitted"
    )
    ## Exactly ONE recovered row for this name: the `#else` branch. A `(file, name)` key
    ## would give zero (doxygen already has the name in this file) and no key at all would
    ## give two.
    assert _macro_rows(taken_branch_index, SYMBOL_SOURCE_AST) == 1

    sites = {m.line: m for m in macro_definitions(taken_branch_index, "PRIVATE")}
    assert sorted(sites) == [GATED_LINE, ELSE_LINE]
    assert sites[GATED_LINE].expansion == "private_##member"
    assert sites[ELSE_LINE].expansion == "member"
    ## Provenance separates the two halves of the answer. The `#else` spelling is not
    ## something doxygen declined to document — it is something doxygen could not see.
    assert sites[GATED_LINE].provenance is None
    assert sites[ELSE_LINE].provenance == SYMBOL_SOURCE_AST
    ## The recovered site carries its parameters, which means the `param` /
    ## `memberdef_param` write happened. Without it the site reads as object-like and the
    ## two rows of one macro would differ by who recovered them.
    assert sites[ELSE_LINE].params == "(member)"


def test_recovery_is_idempotent_for_macros(taken_branch_index: Path, repo: Path) -> None:
    """A `(file, name, line)` key is finer than the variable rule's `(file, name)`, and a
    finer key has more ways to miss: read back the wrong column, or compare a tree-sitter
    line against a `bodystart`, and every macro is re-inserted on every build. Only a
    second pass returning zero new rows catches it."""
    recover_ast_symbols(taken_branch_index, repo, None)
    after_first = _macro_rows(taken_branch_index, SYMBOL_SOURCE_AST)

    recover_ast_symbols(taken_branch_index, repo, None)

    assert _macro_rows(taken_branch_index, SYMBOL_SOURCE_AST) == after_first
    assert _macro_rows(taken_branch_index, SYMBOL_SOURCE_DOXYGEN) == 1


# ─── part 3: which branch — two-sided, per site ──────────────────────────────


def test_each_definition_site_reports_its_own_gate_polarity(
    taken_branch_index: Path, repo: Path
) -> None:
    """ "WHICH CONSUMER GETS WHICH" IS A QUESTION ABOUT A GATE, and this is the assertion
    the graded question actually needs. Two rows with two different expansions read as a
    contradiction until something says which branch each sits in.

    EVERY CLAIM IS TWO-SIDED. An implementation that attached every gate in the file to
    every line would satisfy the positive halves of both assertions below and would answer
    the question backwards half the time, so each site is asserted to report its own form
    AND to NOT report the other's.

    Both stages run for real against the same file, which is the coupling no hand-written
    database can test: `ast_symbols` decides line 17 from `node.start_point` and
    `kconfig_gates` decides the `#else` extent from its own walk, and the answer is only
    right if those two agree."""
    recover_ast_symbols(taken_branch_index, repo, None)
    assert import_kconfig_gates(taken_branch_index, repo) > 0

    sites = {m.line: m for m in macro_definitions(taken_branch_index, "PRIVATE")}
    gated = {(g.macro, g.form) for g in sites[GATED_LINE].gated_by}
    otherwise = {(g.macro, g.form) for g in sites[ELSE_LINE].gated_by}

    assert ("ALLOW_PRIVATE_ACCESS", KCONFIG_GATE_IFNDEF) in gated
    assert ("ALLOW_PRIVATE_ACCESS", KCONFIG_GATE_IFDEF) not in gated, (
        "the private_ spelling is what a unit that has NOT defined the symbol gets"
    )
    assert ("ALLOW_PRIVATE_ACCESS", KCONFIG_GATE_IFDEF) in otherwise
    assert ("ALLOW_PRIVATE_ACCESS", KCONFIG_GATE_IFNDEF) not in otherwise, (
        "the bare spelling is what a unit that HAS defined the symbol gets"
    )
    ## Zero is a measurement here: every gate in this file had a recorded extent, so an
    ## empty `gated_by` on some other site would mean ungated rather than unknown.
    assert sites[GATED_LINE].gates_unplaceable == 0
    assert sites[ELSE_LINE].gates_unplaceable == 0


def test_a_macro_only_dossier_carries_the_first_sites_gates(
    taken_branch_index: Path, repo: Path
) -> None:
    """A dossier has ONE `file` and ONE `line_start`, so its `gated_by` can describe one
    position — and it must be the position it reports. `_macro_dossier` takes its identity
    from the first site and COPIES that site's gates rather than recomputing them, so the
    two cannot drift apart.

    `PRIVATE` resolves to no function in this fixture, so this is the macro-SUBJECT path.
    The per-site lists on `macros` stay the complete answer; this pins that the
    dossier-level field means the same thing here as it does on a function."""
    recover_ast_symbols(taken_branch_index, repo, None)
    import_kconfig_gates(taken_branch_index, repo)

    doss = dossier(taken_branch_index, "PRIVATE")
    assert doss is not None
    assert doss.kind == MACRO_KIND
    assert doss.line_start == GATED_LINE
    assert {(g.macro, g.form) for g in doss.gated_by} == {
        ("ALLOW_PRIVATE_ACCESS", KCONFIG_GATE_IFNDEF)
    }, "the dossier's gates must describe the line the dossier reports, not both branches"
    ## And the panel still carries both, which is the field a reader is pointed at.
    assert sorted(m.line for m in doss.macros) == [GATED_LINE, ELSE_LINE]


def test_the_include_guard_is_not_reported_as_a_configuration_gate(
    taken_branch_index: Path, repo: Path
) -> None:
    """THE NEGATIVE HALF, and it is what stops the polarity answer above from being luck.
    The fixture's outer `#ifndef MBEDTLS_PRIVATE_ACCESS_H` spans BOTH `#define`s, so a
    gate harvest that recorded include guards would attach it to every site — every macro
    in every header would come back "gated", and the one gate that means something would
    sit in a list beside a guard that means nothing."""
    recover_ast_symbols(taken_branch_index, repo, None)
    import_kconfig_gates(taken_branch_index, repo)

    sites = {m.line: m for m in macro_definitions(taken_branch_index, "PRIVATE")}
    for line, site in sites.items():
        assert "MBEDTLS_PRIVATE_ACCESS_H" not in {g.macro for g in site.gated_by}, (
            f"site at line {line} reports the include guard as a configuration gate"
        )
