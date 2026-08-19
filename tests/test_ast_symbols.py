# SPDX-License-Identifier: MIT
"""gh#11 — the function definitions doxygen never emitted, and their provenance.

Built on doxygen's OWN verbatim schema (`tests/data/doxygen_schema.sql`, the same
file `richdb` loads) rather than a hand-simplified `memberdef`, because the whole
change hinges on altering a table this package does not create: a fixture with a
convenient two-column `memberdef` could not catch a `NOT NULL` column we forgot
to fill, or a `column` identifier that needs quoting. Both were real.

Deliberately NOT folded into the `rich_db` fixture. That fixture's hand-written
memberdef rows are a deliberate SUBSET of what `tests/data/csample/` really
contains, so running recovery over it would insert a row for every csample
function the fixture omits on purpose — inflating counts a dozen other tests pin,
and testing this stage against a database whose barrenness is an artifact of the
fixture rather than of a preprocessor.

@brief Tests for parser-recovered symbols and their reported provenance.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.ast_symbols import (
    ParsedFunction,
    ensure_symbol_provenance,
    harvest_function_definitions,
    function_definition_harvester,
    harvest_python_definitions,
    harvest_type_definitions,
    recover_ast_symbols,
)
from clew.coverage import measure_index_coverage
from clew.harvest import try_import_tree_sitter
from clew.query import function_dossier, resolve_symbol, search, source
from clew.vocabulary import (
    SYMBOL_SOURCE_AST,
    SYMBOL_SOURCE_COLUMN,
    SYMBOL_SOURCE_DOXYGEN,
)

pytestmark = pytest.mark.skipif(
    try_import_tree_sitter() is None,
    reason="gh#11 recovery needs tree_sitter + its C/C++ grammars",
)

DOXYGEN_SCHEMA = Path(__file__).resolve().parent / "data" / "doxygen_schema.sql"

## The canonical gh#11 shape, modelled on mbedtls `library/threading.c`: the whole
## body of the file sits inside a feature macro the build never defined, so doxygen
## emits nothing for it while tree-sitter reads it perfectly well. Padded past
## `coverage.MIN_SUBSTANTIVE_LINES` so the file is judgeable by the coverage metric.
_GUARDED_C = (
    "#include <stddef.h>\n"
    + "\n".join(f"/* pad {n} */" for n in range(110))
    + """
#if defined(DEMO_THREADING_PTHREAD)
static int mutex_lock_pthread(void *mutex)
{
    return 0;
}

int mutex_unlock_pthread(void *mutex, int flags)
{
    return mutex_lock_pthread(mutex);
}

/* gh#372: the four globals below are the measured mbedtls shape, one per row of
   the discriminator table in `ast_symbols`. They sit inside the SAME unsatisfied
   guard as the functions above, which is why doxygen emits none of them. */
demo_mutex_t demo_readdir_mutex;
demo_mutex_t demo_key_slot_mutex, demo_gmtime_mutex;
static int demo_lock_depth = 0;
int (*demo_mutex_lock)(demo_mutex_t *) = mutex_lock_pthread;

/* MUST NOT be recovered as a variable: a prototype, not a global. Same
   `function_declarator` node as the function pointer above it, and only the
   parenthesized declarator tells them apart. */
int demo_prototype_not_a_variable(int x);
#endif

int demo_body_local_is_not_a_global(void)
{
    /* MUST NOT be recovered: a function's local, reached through a
       `compound_statement` the walk refuses to enter. */
    int not_a_global = 1;
    return not_a_global;
}
"""
)

## A file doxygen DID read. Its function must never be recovered a second time —
## the double-count is the likeliest way this change goes wrong.
_SEEN_C = """\
int documented_add(int a)
{
    return a + 1;
}
"""

## A public function DECLARED in a header doxygen could read and DEFINED inside a
## guard it could not satisfy. The declaration carries the brief; the definition
## carries the body. This is the shape that made the first cut lose documentation.
_PUBLIC_H = """\
#ifndef PUBLIC_H
#define PUBLIC_H
int split_api(int v);
#endif
"""

## TWO functions, not one, because `coverage.FileYield.barren` is "at most ONE
## memberdef row" — mbedtls's `threading.c` yields exactly one symbol with its whole
## body guarded out, so the metric deliberately treats 1 as barren. A single
## recovered function therefore does NOT clear the flag, and a fixture with one
## would have made the acceptance assertion below read as a failure of the fix.
_PUBLIC_C = (
    "\n".join(f"/* pad {n} */" for n in range(110))
    + """
#if defined(DEMO_FEATURE_ON)
int split_api(int v)
{
    return v * 2;
}

static int split_helper(int v)
{
    return v - 1;
}
#endif
"""
)

_PATHS = {
    10: "guarded.c",
    11: "seen.c",
    12: "public.h",
    13: "public.c",
}
_SOURCES = {
    "guarded.c": _GUARDED_C,
    "seen.c": _SEEN_C,
    "public.h": _PUBLIC_H,
    "public.c": _PUBLIC_C,
}


## @brief Write one doxygen-shaped memberdef row.
## @param conn Open connection.
## @param rowid Row id to use (also the refid rowid, as doxygen does).
## @param values Column values keyed by column name.
## @version 1
def _memberdef(conn: sqlite3.Connection, rowid: int, **values: object) -> None:
    """@brief Insert a memberdef row plus its refid, doxygen-style.

    @version 1
    """
    conn.execute("INSERT INTO refid (rowid, refid) VALUES (?, ?)", (rowid, f"fx_{rowid}"))
    cols = ", ".join(f'"{k}"' for k in values)
    marks = ", ".join("?" for _ in values)
    conn.execute(
        f"INSERT INTO memberdef (rowid, {cols}) VALUES (?, {marks})",
        (rowid, *values.values()),
    )


## @brief A repo tree plus a doxygen-shaped index describing only part of it.
## @return (db path, repo root).
## @version 1
@pytest.fixture
def barren_index(tmp_path: Path) -> tuple[Path, Path]:
    """Four files on disk; doxygen saw the body in `seen.c` and the DECLARATION in
    `public.h`, and nothing at all in `guarded.c` or `public.c`.

    @brief Index with two barren files and one split decl/def.
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    for name, text in _SOURCES.items():
        (repo / name).write_text(text, encoding="utf-8")

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.executescript(DOXYGEN_SCHEMA.read_text(encoding="utf-8"))
        for rowid, name in _PATHS.items():
            conn.execute(
                "INSERT INTO path (rowid, type, local, found, name) VALUES (?, 1, 1, 1, ?)",
                (rowid, name),
            )
        _memberdef(
            conn,
            1,
            name="documented_add",
            definition="int documented_add",
            argsstring="(int a)",
            kind="function",
            static=0,
            bodystart=1,
            bodyend=4,
            bodyfile_id=11,
            file_id=11,
            line=1,
            column=1,
            briefdescription="<para>Adds one. </para>",
        )
        ## The header DECLARATION: a brief, and no body. bodystart 0 is what doxygen
        ## records for a declaration it never saw defined.
        _memberdef(
            conn,
            2,
            name="split_api",
            definition="int split_api",
            argsstring="(int v)",
            kind="function",
            static=0,
            bodystart=0,
            bodyend=0,
            bodyfile_id=None,
            file_id=12,
            line=3,
            column=1,
            briefdescription="<para>Doubles a value. </para>",
            ## doxygen's real shape, not a bare tag: `extract_version` parses the
            ## `<simplesect kind="version">` wrapper, so a fixture storing the tag
            ## literally leaves that parser untested. Copied from `richdb._detailed`.
            detaileddescription=(
                '<para><simplesect kind="version"><para>4 </para>\n</simplesect>\n</para>\n'
            ),
        )
        conn.commit()
    finally:
        conn.close()
    return db, repo


## @brief Column values for every memberdef row, keyed by name.
## @param db Database to read.
## @return name -> (provenance, bodystart, bodyend, brief, static).
## @version 1
def _rows_by_name(db: Path) -> dict[str, tuple]:
    """@brief Read back every memberdef row for assertion.

    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return {
            r[0]: (r[1], r[2], r[3], r[4], r[5])
            for r in conn.execute(
                f"SELECT name, {SYMBOL_SOURCE_COLUMN}, bodystart, bodyend, "
                "briefdescription, static FROM memberdef ORDER BY rowid"
            )
        }
    finally:
        conn.close()


# ─── the harvest itself ──────────────────────────────────────────────────────


def test_a_guarded_body_is_parsed_even_though_doxygen_saw_nothing() -> None:
    """The premise of the whole issue: the parser does not care about the
    preprocessor. Asserted on the harvest alone, so a failure here separates "we
    cannot see these functions" from "we cannot store them"."""
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_c

    tree = parser_cls(language_cls(tree_sitter_c.language())).parse(_GUARDED_C.encode())
    found = {f.name: f for f in harvest_function_definitions(tree, _GUARDED_C.encode())}

    assert set(found) == {
        "mutex_lock_pthread",
        "mutex_unlock_pthread",
        "demo_body_local_is_not_a_global",
    }
    ## gh#372 put a prototype in this file. It must not become a FUNCTION either —
    ## function recovery keys on `function_definition` and a prototype is a
    ## `declaration`, so this is the other half of the same discriminator.
    assert "demo_prototype_not_a_variable" not in found
    assert found["mutex_lock_pthread"].static is True
    assert found["mutex_unlock_pthread"].static is False
    assert found["mutex_unlock_pthread"].args == "(void *mutex, int flags)"


def test_a_nested_definition_is_not_recorded_as_a_second_symbol() -> None:
    """A GNU nested function sits INSIDE its parent's span, so recording both would
    make the span-overlap dedup order-dependent — whichever was seen second would
    lose. The walk stops descending at a definition instead."""
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_c

    src = b"int outer(void) {\n  int inner(void) { return 1; }\n  return inner();\n}\n"
    tree = parser_cls(language_cls(tree_sitter_c.language())).parse(src)

    assert [f.name for f in harvest_function_definitions(tree, src)] == ["outer"]


def test_every_cpp_declarator_shape_that_has_a_name_is_recovered() -> None:
    """A SECOND GAP THE TEST ABOVE EXPOSED. `_declared_names` accepted only
    `identifier` and `qualified_identifier`, and tree-sitter-cpp names a method
    defined inside its class body `field_identifier` — so EVERY in-class method
    definition was silently skipped. Nothing failed; those symbols were simply never
    recovered, which is the same shape as the defect gh#11 exists to fix, one level
    down. The accepted set is now enumerated from a grammar probe.

    `operator=` stays refused on purpose: its declarator is a `reference_declarator`
    with no `function_declarator` beneath it, so there is no name node to read, and
    inventing one would put a guess into every downstream resolution."""
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_cpp

    src = (
        b"namespace ns {\nclass W {\n public:\n"
        b"  int inline_method() { return 1; }\n"
        b"  ~W() { }\n"
        b"  W& operator=(int) { return *this; }\n"
        b"  static int static_method() { return 2; }\n"
        b"};\n"
        b"int W::out_of_line() { return 4; }\n"
        b"static int free_fn(int a) { return a; }\n"
        b"template <typename T> T tmpl(T v) { return v; }\n}\n"
    )
    tree = parser_cls(language_cls(tree_sitter_cpp.language())).parse(src)
    found = {f.name: f for f in harvest_function_definitions(tree, src)}

    assert set(found) == {
        "inline_method",
        "~W",
        "static_method",
        "out_of_line",
        "free_fn",
        "tmpl",
    }
    ## The out-of-line definition keeps its QUALIFIED name, which is what
    ## `qualified_name_of` needs to key it to doxygen's declaration row.
    assert found["out_of_line"].qualified == "W::out_of_line"
    assert found["free_fn"].static is True
    assert found["static_method"].static is True


def test_a_defaulted_or_deleted_special_member_is_not_recovered() -> None:
    """FOUND BY MEASUREMENT, not by reading the grammar. `W(W&&) = default;` IS a
    `function_definition` in tree-sitter-cpp — the `= default;` sits where a body
    would — so the first cut recovered a row for a member that has no body and that
    doxygen had already emitted a declaration for.

    Measured on entropic: 18 of 20 recovered rows were defaulted or deleted special
    members. Worse than merely redundant — their `definition` is the bare declarator,
    so `qualified_name_of` keyed them to a different identity than doxygen's
    `entropic::SandboxManager::SandboxManager`, giving one function two graph nodes,
    which is gh#26 reintroduced by the fix for gh#11. It also made the spurious row
    outrank the real constructor in `function_candidates`, because a recovered row
    has `file_id == bodyfile_id` and an out-of-line constructor does not.

    Pinned on the grammar's own discriminator — a real definition has a `body`
    field, a defaulted one does not — rather than on the clause node's name.
    """
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_cpp

    src = (
        b"class W {\n public:\n  W() = default;\n  W(W&&) = default;\n"
        b"  W(const W&) = delete;\n  int real() { return 1; }\n};\n"
        b"W::~W() = default;\n"
    )
    tree = parser_cls(language_cls(tree_sitter_cpp.language())).parse(src)

    assert [f.name for f in harvest_function_definitions(tree, src)] == ["real"]


def test_overlaps_collapses_a_malformed_end_to_its_start_line() -> None:
    """doxygen records `bodyend = -1` for a body it never saw closed. Treating that
    literally makes the interval `[start, -1]`, which an unguarded comparison reads
    as matching everything after `start` — silencing recovery for the whole file."""
    fn = ParsedFunction(name="f", qualified="f", args="()", static=False, start=50, end=60)

    assert fn.overlaps(55, -1) is True
    assert fn.overlaps(10, -1) is False


# ─── storage + the duplicate that must not happen ────────────────────────────


def test_recovery_inserts_the_guarded_functions_and_marks_them_ast(
    barren_index: tuple[Path, Path],
) -> None:
    """The headline. Functions doxygen never emitted become rows, and every one
    of them says so."""
    db, repo = barren_index
    inserted = recover_ast_symbols(db, repo, None)
    rows = _rows_by_name(db)

    ## 5 functions (three in guarded.c, two in public.c) + 5 gh#372 globals + gh#403's
    ## one macro, `public.h`'s `#define PUBLIC_H` include guard. The return value covers
    ## EVERY kind, which is why this is not 5.
    ##
    ## THE GUARD IS RECOVERED DELIBERATELY, not tolerated. doxygen skips an include guard
    ## and a rule that skipped it here would need to recognise the idiom — one more
    ## heuristic, on a walk whose value is that a `#define` is the least ambiguous thing
    ## in a C file. A row saying `PUBLIC_H` is defined at that line is true.
    assert inserted == 11
    assert rows["mutex_lock_pthread"][0] == SYMBOL_SOURCE_AST
    assert rows["mutex_unlock_pthread"][0] == SYMBOL_SOURCE_AST
    ## Static-ness is one of the four things the issue says a recovered row carries.
    assert rows["mutex_lock_pthread"][4] == 1
    assert rows["mutex_unlock_pthread"][4] == 0


def test_a_function_doxygen_already_emitted_is_never_duplicated(
    barren_index: tuple[Path, Path],
) -> None:
    """THE DOUBLE-COUNT GUARD, and the likeliest way this change goes wrong. A
    recovered row for a function doxygen already has would corrupt every count and
    every name resolution built on it."""
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    conn = sqlite3.connect(str(db))
    try:
        assert (
            conn.execute("SELECT COUNT(*) FROM memberdef WHERE name='documented_add'").fetchone()[0]
            == 1
        )
        ## And the surviving row is still doxygen's, with its brief intact.
        assert (
            conn.execute(
                f"SELECT {SYMBOL_SOURCE_COLUMN} FROM memberdef WHERE name='documented_add'"
            ).fetchone()[0]
            == SYMBOL_SOURCE_DOXYGEN
        )
    finally:
        conn.close()


def test_running_recovery_twice_inserts_nothing_the_second_time(
    barren_index: tuple[Path, Path],
) -> None:
    """A smoke run caught the first cut doing the opposite: the dedup compared only
    against doxygen-sourced spans, so a second pass re-inserted the whole recovered
    set. It surfaced as a UNIQUE violation on the synthetic refid; without that
    index it would have silently doubled the graph.

    Covers BOTH kinds since gh#372, and the variable half has its own way to fail:
    its dedup key is `(file, name)` read back from `memberdef`, so a second pass
    that queried the wrong provenance or the wrong kind would re-insert all five
    globals. The `== 0` below is the only assertion that catches it.

    THREE KINDS SINCE gh#403, and the macro half has a THIRD way to fail that neither
    other kind can reach: its key is `(file, name, LINE)`, deliberately finer than the
    variable rule so a conditional `#define`'s second branch survives. A key that finer
    is a key with more ways to miss — read back the wrong column, or compare a
    tree-sitter line against a `bodystart`, and every macro in the repository is
    re-inserted on every build. Only the `== 0` catches it."""
    db, repo = barren_index

    assert recover_ast_symbols(db, repo, None) == 11
    assert recover_ast_symbols(db, repo, None) == 0


def test_every_doxygen_row_is_labelled_doxygen_without_an_update_sweep(
    barren_index: tuple[Path, Path],
) -> None:
    """The `NOT NULL DEFAULT` is what makes the column honest about rows that
    existed before it did. If the default were absent (or NULL-able) doxygen's own
    rows would read as provenance-unknown until some later pass filled them in, and
    there would be a window in which a query could see an unlabelled row."""
    db, _repo = barren_index
    conn = sqlite3.connect(str(db))
    try:
        assert ensure_symbol_provenance(conn) is True
        assert ensure_symbol_provenance(conn) is False, "must be idempotent"
        sources = {
            r[0] for r in conn.execute(f"SELECT DISTINCT {SYMBOL_SOURCE_COLUMN} FROM memberdef")
        }
        assert sources == {SYMBOL_SOURCE_DOXYGEN}
    finally:
        conn.close()


def test_the_provenance_column_refuses_an_unregistered_value(
    barren_index: tuple[Path, Path],
) -> None:
    """The CHECK is generated from `vocabulary.SYMBOL_SOURCE`, so this pins that the
    ALTER actually carried it — SQLite permits a CHECK in ADD COLUMN, but silently
    dropping one would leave an unconstrained free-text provenance column, which is
    the exact defect `external_boundaries.source` was fixed for."""
    db, _repo = barren_index
    conn = sqlite3.connect(str(db))
    try:
        ensure_symbol_provenance(conn)
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"UPDATE memberdef SET {SYMBOL_SOURCE_COLUMN} = 'guessed' WHERE rowid = 1")
    finally:
        conn.close()


# ─── decl/def duality: the highest-risk regression ───────────────────────────


def test_decl_def_duality_survives_and_the_two_rows_stay_one_function(
    barren_index: tuple[Path, Path],
) -> None:
    """gh#26's identity key is `qualified_name_of`, and a recovered row has to land
    on the SAME identity as doxygen's declaration of the same function — otherwise
    `split_api` becomes two unrelated graph nodes, which is how 957 entropic
    declarations were once torn from their definitions."""
    from clew.query._common import identity_rowids

    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    conn = sqlite3.connect(str(db))
    try:
        rowids = identity_rowids(conn, "split_api")
        ## Two rows — doxygen's header declaration and the parser's definition — and
        ## they are ONE identity, not two.
        assert len(rowids) == 2
        kinds = dict(
            conn.execute(
                f"SELECT {SYMBOL_SOURCE_COLUMN}, bodystart FROM memberdef "
                "WHERE name='split_api' ORDER BY rowid"
            )
        )
        assert kinds[SYMBOL_SOURCE_DOXYGEN] == 0, "the declaration still has no body"
        assert kinds[SYMBOL_SOURCE_AST] > 0, "the definition now has one"
    finally:
        conn.close()


def test_a_documented_declaration_keeps_its_brief_when_its_body_is_recovered(
    barren_index: tuple[Path, Path],
) -> None:
    """THE DOCUMENTATION REGRESSION THE FIRST CUT SHIPPED. `function_candidates`
    orders body rows first, so after recovery the function_dossier's chosen row is the
    parser's — which has no brief. Reading the brief from that row alone reported a
    documented function as undocumented, i.e. a change whose purpose is to ADD
    information destroyed some."""
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    d = function_dossier(db, "split_api")
    assert d is not None
    assert d.brief == "Doubles a value.", "the header's brief must survive"
    assert d.version == "4", "and so must its @version"
    ## The location comes from the parser, which is the only thing that knows it.
    assert d.file == "public.c"
    assert d.provenance == SYMBOL_SOURCE_AST


# ─── provenance at every symbol-returning surface ────────────────────────────


def test_a_parsed_row_is_distinguishable_from_a_doxygen_row_at_every_surface(
    barren_index: tuple[Path, Path],
) -> None:
    """The issue's third bullet. A consumer must be able to tell a documented symbol
    from a parsed one WITHOUT reading the brief and guessing, because an absent brief
    is ambiguous between 'undocumented' and 'unparsed' — and one of those two means
    the tool cannot see the code at all."""
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    parsed, documented = "mutex_lock_pthread", "documented_add"

    assert resolve_symbol(db, parsed).provenance == SYMBOL_SOURCE_AST
    assert resolve_symbol(db, documented).provenance is None

    assert function_dossier(db, parsed).provenance == SYMBOL_SOURCE_AST
    assert function_dossier(db, documented).provenance is None

    hits = {h.name: h for h in search(db, parsed)}
    assert hits[parsed].provenance == SYMBOL_SOURCE_AST
    assert {h.name: h for h in search(db, documented)}[documented].provenance is None

    assert source(db, parsed, repo).provenance == SYMBOL_SOURCE_AST
    assert source(db, documented, repo).provenance is None


def test_a_parsed_row_carries_no_brief_and_nothing_pretends_otherwise(
    barren_index: tuple[Path, Path],
) -> None:
    """A preprocessor that skipped the code skipped its doc comment, so there is no
    prose to recover and inventing any — a synthesized brief, a placeholder, the
    function's own name — would be worse than an empty one. Checked at the ROW and
    at the surfaces, because a mapper could fabricate one on the way out."""
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT briefdescription, detaileddescription, inbodydescription FROM memberdef "
            "WHERE name='mutex_lock_pthread'"
        ).fetchone()
    finally:
        conn.close()
    assert row == (None, None, None), "a recovered row must carry no description at all"

    d = function_dossier(db, "mutex_lock_pthread")
    assert d.brief == ""
    assert d.version == ""
    assert d.requirements == [], "and no @req tags, since those live in the prose"

    hit = {h.name: h for h in search(db, "mutex_lock_pthread")}["mutex_lock_pthread"]
    assert hit.brief == ""


def test_the_recovered_body_is_readable_source_which_it_previously_was_not(
    barren_index: tuple[Path, Path],
) -> None:
    """`source` needs `bodystart`/`bodyend`, and before recovery a guarded-out
    function had neither — so the tool answered nothing. This is the capability the
    issue's 'done means' clause is about."""
    db, repo = barren_index
    assert source(db, "mutex_unlock_pthread", repo) is None

    recover_ast_symbols(db, repo, None)
    listing = source(db, "mutex_unlock_pthread", repo)

    assert listing is not None
    assert listing.file == "guarded.c"
    assert "mutex_unlock_pthread" in listing.lines[0]
    assert any("return mutex_lock_pthread(mutex);" in line for line in listing.lines)


# ─── the metric the issue asks to be judged by ───────────────────────────────


def test_recovery_lowers_the_barren_ratio_and_leaves_the_documented_gap_visible(
    barren_index: tuple[Path, Path],
) -> None:
    """gh#6's metric is gh#11's acceptance criterion, so it has to move. But making
    it move must NOT silence the advice to declare PREDEFINED, because that recovers
    the DOCUMENTATION this cannot. Both halves are asserted: the graph gap closes
    and the prose gap stays measured."""
    db, repo = barren_index

    before = measure_index_coverage(db, repo)
    assert before.barren_files == 2, "guarded.c and public.c yield nothing"
    assert before.undocumented_files == 2

    recover_ast_symbols(db, repo, None)
    after = measure_index_coverage(db, repo)

    assert after.barren_files == 0, "the graph gap is closed"
    assert after.barren_ratio < before.barren_ratio
    ## guarded.c's two functions have no documentation anywhere; public.c's one is
    ## documented in its header, and the metric attributes prose per FILE, so
    ## public.c reads undocumented too. Both stay visible.
    assert after.undocumented_files == 2, "the prose gap is untouched"
    assert after.undocumented_ratio > after.barren_ratio


def test_the_coverage_meta_publishes_both_ratios(barren_index: tuple[Path, Path]) -> None:
    """A number that lives only in a warning is gone by query time — the defect this
    project has now fixed three times. The documented ratio has to be persisted for
    the same reason the barren one is."""
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)
    meta = measure_index_coverage(db, repo).as_meta()

    assert "barren_ratio" in meta
    assert "undocumented_ratio" in meta
    assert meta["undocumented_files"] == "2"


# ─── the deliberate limits, pinned so they are choices and not accidents ─────


def test_python_recovers_functions_and_still_no_module_variables(tmp_path: Path) -> None:
    """INVERTED, NOT DELETED (gh#397). This test used to assert that Python is REFUSED, on
    the ground its own name gave: "because doxygen already indexes it". Its docstring said
    "Pinned so that enabling Python later is a decision rather than a side effect" — this is
    that decision, and the premise it rested on was MEASURED FALSE:

    On this repository's own index at build 42, `tests/test_mcp_server.py` declares 93
    top-level functions and doxygen emitted 41. The other 52 were absent from every table:
    not truncated (rows reached the file's last line), not misattributed (zero rows anywhere
    for sampled names), and not predicted by whether a `##` block was present. Enabling
    recovery took that file from 52 missing to 1, and the repo from 158 to 160 of 172 files
    indexing >=95% of their defs.

    THE VARIABLE HALF STILL HOLDS, and it is kept for the reason the original gave: a Python
    module's assignments are exactly what a careless widening of the walk would start
    harvesting, and doxygen already indexes them. That half would break silently, so it stays
    asserted alongside the inverted half.

    INVARIANCE CONTROL, run outside the suite because it needs a real target: rebuilding
    mbedtls across this change left all 36 tables byte-identical, so the widening is a strict
    no-op on C. On the self-index, doxygen rows moved 4,493 -> 4,497 and the four were
    verified to be exactly this change's own new code, not disturbed rows.
    """
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_python

    src = b"TOP_LEVEL = 3\n\n\ndef top():\n    return 1\n"
    tree = parser_cls(language_cls(tree_sitter_python.language())).parse(src)

    from clew.ast_symbols import (
        _PAYLOAD_FUNCTIONS,
        _PAYLOAD_VARIABLES,
        _FunctionDefinitionHarvester,
    )

    payload = _FunctionDefinitionHarvester().harvest(tree, src)
    assert [row[0] for row in payload.get(_PAYLOAD_FUNCTIONS, [])] == ["top"]
    assert payload.get(_PAYLOAD_VARIABLES, []) == [], (
        "TOP_LEVEL is a module-level assignment doxygen already indexes; recovering it "
        "would double-count every Python constant in the repo"
    )


def test_a_declaration_only_header_contributes_no_phantom_body(
    barren_index: tuple[Path, Path],
) -> None:
    """`public.h` DECLARES `split_api` and defines nothing. The harvester keys on
    `function_definition`, which a declaration is not — so no body span is invented
    for a header, and `public.h` never gains a recovered row."""
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    conn = sqlite3.connect(str(db))
    try:
        assert (
            conn.execute(
                f"SELECT COUNT(*) FROM memberdef WHERE bodyfile_id = 12 "
                f"AND {SYMBOL_SOURCE_COLUMN} = '{SYMBOL_SOURCE_AST}'"
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()


# ─── gh#372: global and file-scope variables ─────────────────────────────────


## @brief Read back every recovered variable row, keyed by name.
## @param db Database to read.
## @return name -> (kind, type, definition, static, line, bodystart, bodyfile_id).
## @version 1
def _variable_rows(db: Path) -> dict[str, tuple]:
    """Reads the columns a variable row must and must NOT carry, so one helper
    serves both the presence assertions and the "no body" assertions.

    @brief Read back the ast-sourced variable rows.
    @return Mapping of name to its stored columns.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return {
            row[0]: row[1:]
            for row in conn.execute(
                "SELECT name, kind, type, definition, static, line, bodystart, bodyfile_id "
                f"FROM memberdef WHERE {SYMBOL_SOURCE_COLUMN} = '{SYMBOL_SOURCE_AST}' "
                "AND kind = 'variable'"
            )
        }
    finally:
        conn.close()


def test_a_guarded_global_is_recovered_with_its_declared_type(
    barren_index: tuple[Path, Path],
) -> None:
    """THE MEASURED GAP. mbedtls declares five global mutex OBJECTS behind
    `#if defined(MBEDTLS_FS_IO)` and friends; doxygen's preprocessor strips them, so
    `search` returned a confident zero for every one and the only route to the repo's
    mutex list was reading `mbedtls_threading_set_alt`'s BODY.

    The declared TYPE is asserted, not just the name, because that is what lets a
    reader separate the mutex objects from the lock primitive — the exact distinction
    a rubric mark grades.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)
    rows = _variable_rows(db)

    assert rows["demo_readdir_mutex"][1] == "demo_mutex_t"
    assert rows["demo_readdir_mutex"][2] == "demo_mutex_t demo_readdir_mutex"
    assert rows["demo_lock_depth"][3] == 1, "the `static` storage class is recorded"
    assert rows["demo_readdir_mutex"][3] == 0


def test_one_declaration_declaring_two_names_yields_two_rows(
    barren_index: tuple[Path, Path],
) -> None:
    """`demo_mutex_t demo_key_slot_mutex, demo_gmtime_mutex;` is ONE `declaration`
    node with TWO `declarator`-field children. Reading `child_by_field_name` —
    singular — would index the first and silently drop the second, which is a whole
    global missing with nothing to indicate it. Both share the declaration's type.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)
    rows = _variable_rows(db)

    assert "demo_key_slot_mutex" in rows
    assert "demo_gmtime_mutex" in rows
    assert rows["demo_key_slot_mutex"][1] == rows["demo_gmtime_mutex"][1] == "demo_mutex_t"


def test_a_function_pointer_global_is_a_variable_and_a_prototype_is_not(
    barren_index: tuple[Path, Path],
) -> None:
    """THE ONE JUDGEMENT A WRONG ANSWER MAKES HARMFUL RATHER THAN INCOMPLETE.

    Both shapes present a `function_declarator`, so that node cannot decide it:

        int demo_prototype_not_a_variable(int x);   function_declarator → identifier
        int (*demo_mutex_lock)(demo_mutex_t *);     function_declarator
                                                    → parenthesized_declarator
                                                    → pointer_declarator → identifier

    Getting it backwards puts a function prototype in the index as a variable, which
    is precisely the "a variable where a caller expected a function" failure. Both
    directions are asserted here — a test naming only the function pointer would pass
    against an implementation that recovered every prototype in the repo.

    mbedtls's lock PRIMITIVE is the function-pointer case, which is why the
    permissive half matters and cannot simply be dropped to stay safe.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)
    rows = _variable_rows(db)

    assert "demo_mutex_lock" in rows, "a function-pointer global IS a variable"
    assert "demo_prototype_not_a_variable" not in rows, "a prototype is NOT a variable"

    ## THE `definition` MUST SPELL THE POINTER, and this was caught on the real index
    ## rather than here. A C declaration's `type` field holds only the BASE type, so
    ## the first cut published mbedtls's lock primitive as `int mbedtls_mutex_lock` —
    ## indistinguishable from an integer counter, on the one row whose entire value is
    ## saying "this is a function pointer, not a mutex object". Asserted against the
    ## object row too, because the fix must not smear the two together: telling the
    ## objects from the primitive is the graded distinction.
    assert rows["demo_mutex_lock"][2] == "int (*demo_mutex_lock)(demo_mutex_t *)"
    assert rows["demo_readdir_mutex"][2] == "demo_mutex_t demo_readdir_mutex"


def test_a_function_local_never_becomes_a_global(
    barren_index: tuple[Path, Path],
) -> None:
    """`not_a_global` is declared inside `demo_body_local_is_not_a_global`'s body.
    A `compound_statement` is full of `declaration` nodes, so a walk that did not
    refuse to enter a `function_definition` would flood the index with every `i`,
    `ret` and `len` in the repo — and each one would be searchable, which is worse
    than the gap this change closes.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    assert "not_a_global" not in _variable_rows(db)


def test_a_recovered_variable_carries_no_body_and_no_bodyfile(
    barren_index: tuple[Path, Path],
) -> None:
    """A variable is not executable. `bodystart`/`bodyend` stay unset so
    `_covered_body_spans` cannot see the row and no function recovery is ever blocked
    by a global's span, and `bodyfile_id` stays NULL so `graph_stats`'s
    files-with-bodies count does not grow by a file that only declares one.

    A payload implying a variable has a body is worse than its absence — it invites a
    caller to trace into something that cannot be traced.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)
    rows = _variable_rows(db)

    for name, row in rows.items():
        assert not row[5], f"{name} must carry no body span, got bodystart={row[5]!r}"
        assert row[6] is None, f"{name} must carry no bodyfile_id, got {row[6]!r}"


def test_no_call_edge_is_ever_created_to_or_from_a_recovered_variable(
    rich_db: Path,
) -> None:
    """A HARD CONSTRAINT, asserted rather than argued. Variable-mediated coupling
    belongs to `shared_key_edges`, which has its own evidence rules; a call edge to a
    global would assert a control-flow relationship that does not exist.

    THE ONLY TEST IN THIS FILE THAT USES `rich_db`, deliberately and against the
    module docstring's general rule. The rule is about testing the STAGE, and this
    tests an INVARIANT ACROSS STAGES: the `barren_index` fixture is doxygen's verbatim
    schema, which has no `call_edges` table at all, so the same assertion there could
    only ever have been skipped — and a skipped test on a hard constraint is the
    constraint unchecked. `rich_db` runs the real call-edge layers over `csample` and
    carries six recovered globals, so it can actually be wrong here.

    This holds today because every call-edge importer filters `kind='function'`, and
    that is exactly the kind of incidental guarantee that stops holding when someone
    widens a filter for an unrelated reason. Pinned so the widening fails here.
    """
    conn = sqlite3.connect(str(rich_db))
    try:
        variables = conn.execute(
            f"SELECT rowid FROM memberdef WHERE {SYMBOL_SOURCE_COLUMN} = "
            f"'{SYMBOL_SOURCE_AST}' AND kind = 'variable'"
        ).fetchall()
        assert variables, "the fixture must actually contain recovered variables"
        marks = ",".join("?" for _ in variables)
        touching = conn.execute(
            f"SELECT COUNT(*) FROM call_edges WHERE caller_rowid IN ({marks}) "
            f"OR callee_rowid IN ({marks})",
            [r[0] for r in variables] * 2,
        ).fetchone()[0]
        assert touching == 0
    finally:
        conn.close()


def test_a_recovered_global_is_findable_through_search_and_typed_as_a_variable(
    barren_index: tuple[Path, Path],
) -> None:
    """THE END-TO-END CLAIM, and the only test here that exercises the query half.

    Storing the row is worthless if `search` still filters `kind='function'` — which
    it did, and which is why the 902 `kind='variable'` rows doxygen already writes on
    mbedtls unaided were just as unfindable as the ones it never wrote. The gap was
    never only a pipeline gap.

    `kind` is asserted because it is the whole safety story: a caller must be able to
    see that this hit has no body, no callers and no callees before treating it as
    callable.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    hits = {h.name: h for h in search(db, "demo_readdir_mutex")}
    assert "demo_readdir_mutex" in hits, "a global must be findable by its own name"
    assert hits["demo_readdir_mutex"].kind == "variable"
    assert hits["demo_readdir_mutex"].file == "guarded.c"


def test_search_still_prefers_a_function_when_a_name_scores_equally(
    barren_index: tuple[Path, Path],
) -> None:
    """THE REGRESSION CONTROL. Adding a corpus must not reorder the old one: a
    variable appearing where a caller expected a function is the failure mode.

    Variables sit in the lowest tie-break tier, so a function wins every score TIE.
    `demo_mutex_lock` (a global) and `mutex_lock_pthread` (a function) both carry the
    token, and the function must not be displaced from the results.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    names = [h.name for h in search(db, "mutex_lock")]
    assert "mutex_lock_pthread" in names
    assert names.index("mutex_lock_pthread") < names.index("demo_mutex_lock")


_PY_SOURCE = '''\
"""A module doxygen may or may not emit rows for."""


def top_level_plain():
    return 1


@some_decorator
def top_level_decorated():
    return 2


class Holder:
    """A class, so its methods need scope qualification."""

    def method_one(self):
        def closure_helper():
            return "local"

        return closure_helper()

    @property
    def method_two(self):
        return 4
'''


def test_python_definitions_are_recovered_with_class_qualification() -> None:
    """WHY THIS EXISTS, having been refused for the life of the module. The harvester
    returned `{}` for every Python tree, on the stated ground that "doxygen indexes Python
    fully — a Doxyfile-less Python codebase measured 4,739 functions — so there is nothing
    to recover there".

    THAT PREMISE IS FALSE, measured on this repository's own index at build 42:
    `tests/test_mcp_server.py` declares 93 top-level functions and doxygen emitted 41. The
    other 52 were absent from every table — not truncated (rows reached the file's last
    line), not misattributed (zero rows anywhere), and not predicted by the presence of a
    `##` block. So the backstop for doxygen's misses was switched off because doxygen was
    believed not to miss.

    The second stated ground — that a def inside a Python class "would need scope handling
    this stage does not do" — was true of this module and false of the package:
    `pyast.class_ranges`/`enclosing_class` already do it for the call-edge layer, and are
    reused rather than reimplemented.

    FOUR SHAPES, because three of them were the ones that would silently not work:
    a bare def; a DECORATED def (wrapped in `decorated_definition`, so a walk accepting only
    a bare `function_definition` skips every fixture and every property — most of a test
    suite); a METHOD, which must be qualified by its class; and a CLOSURE, which must NOT
    appear, because a nested def sits inside its parent's span and recording both makes the
    span-overlap dedup order-dependent.
    """
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_python

    src = _PY_SOURCE.encode()
    tree = parser_cls(language_cls(tree_sitter_python.language())).parse(src)
    found = {f.name: f for f in harvest_python_definitions(tree, src)}

    assert "top_level_plain" in found
    assert "top_level_decorated" in found, "a decorated def must not be skipped"
    assert "method_one" in found
    assert "method_two" in found, "a @property is a decorated method"
    ## THE NEGATIVE HALF. Without it this test would pass on a walk that recorded
    ## everything, and the dedup would then be order-dependent on every real file.
    assert "closure_helper" not in found, "a nested def is a LOCAL, not a symbol"

    ## Methods carry their class; module-level functions do not invent one.
    assert found["method_one"].qualified == "Holder.method_one"
    assert found["top_level_plain"].qualified == "top_level_plain"

    ## `static` is C's internal linkage and Python has no such thing. A @staticmethod
    ## reported as static=True would make symbol_liveness call a public method file-private.
    assert all(f.static is False for f in found.values())


def test_the_harvester_ITSELF_returns_python_functions_not_an_empty_payload() -> None:
    """THE WIRING, and it needs its own test because the one above does not cover it. That
    test calls `harvest_python_definitions` directly, so it passes whether or not anything
    CALLS that function — proven by mutation: restoring the harvester's
    `if is_python_tree(tree): return {}` early-out left it green.

    That is the exact failure this project names "a capability existing is not a capability
    used", and it is how a fix ships with a passing test and no effect. So this drives
    `_FunctionDefinitionHarvester.harvest`, which is what the pipeline actually invokes.

    @brief The harvester's own payload carries Python functions.
    @version 1
    """
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_python

    src = _PY_SOURCE.encode()
    tree = parser_cls(language_cls(tree_sitter_python.language())).parse(src)
    payload = function_definition_harvester().harvest(tree, src)

    assert payload, "an empty payload means the Python branch is unwired"
    names = {row[0] for row in payload["functions"]}
    assert "top_level_plain" in names
    assert "top_level_decorated" in names
    ## Variables stay empty for Python: `harvest_variable_declarations` reads C declarator
    ## shapes the Python grammar does not produce, and a module-level assignment is already
    ## indexed by doxygen.
    assert payload["variables"] == []


def test_a_guarded_typedef_is_recovered_as_a_typedef_row() -> None:
    """gh#395, and it is gh#11 one kind over. THE MEASURED GAP:
    `function_dossier("mbedtls_threading_mutex_t")` returned the alt-dummy
    `struct { int dummy; }` at `tests/include/alt-dummy/threading_alt.h`, while the real
    pthread-backed type at `include/mbedtls/threading.h:29` produced NO ROW IN ANY TABLE —
    it sits behind `MBEDTLS_THREADING_PTHREAD`. Exactly one `compounddef` row existed for
    that name, so resolution picked the only row there was and was RIGHT to.

    That is why this was nearly misfiled as a ranking bug: a test-path demotion tier would
    have produced a green test proving the tier worked while the real type stayed invisible.

    NODE SHAPE PROBED, NOT ASSUMED, per the gh#11 lesson that the grammar is its own
    discriminator: tree-sitter shapes `typedef struct X { ... } X;` as a `type_definition`
    wrapping a `struct_specifier`, confirmed against the real mbedtls header.

    THE LAST `type_identifier` IS THE NAME, and the negative below is why that matters:
    `typedef struct foo_s foo_t;` has a struct TAG and a typedef NAME that differ, and it is
    the declarator a caller types.
    """
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_c

    src = (
        b"#if defined(DEMO_GUARD)\n"
        b"typedef struct demo_mutex_t {\n  int held;\n} demo_mutex_t;\n"
        b"#endif\n"
        b"typedef struct tag_differs_s tag_differs_t;\n"
        b"int demo_fn(void) {\n  typedef int local_alias;\n  return 0;\n}\n"
    )
    tree = parser_cls(language_cls(tree_sitter_c.language())).parse(src)
    found = {t.name for t in harvest_type_definitions(tree, src)}

    ## Behind an unsatisfied guard, which is the whole point.
    assert "demo_mutex_t" in found
    ## The DECLARATOR name, not the struct tag.
    assert "tag_differs_t" in found
    assert "tag_differs_s" not in found, "the struct tag is not what a caller types"
    ## A typedef inside a function body is a local, like every other local this walk skips.
    assert "local_alias" not in found, "a function-local typedef is not a file-scope type"


def test_the_harvester_payload_carries_typedefs_separately_from_variables() -> None:
    """THE WIRING, which needs its own test for the reason the Python one did: a test that
    calls `harvest_type_definitions` directly passes whether or not anything CALLS it.
    Mutation proved that on gh#397 — the direct-call test stayed green with the early-out
    restored.

    A SEPARATE KEY rather than folding typedefs into `variables`, because the two are written
    with different `memberdef.kind` values and a shared list would have to carry the kind per
    row — the shape that lets one loop write the wrong one.
    """
    ts = try_import_tree_sitter()
    assert ts is not None
    language_cls, parser_cls = ts
    import tree_sitter_c

    src = b"typedef struct only_a_type_t { int x; } only_a_type_t;\nint only_a_var;\n"
    tree = parser_cls(language_cls(tree_sitter_c.language())).parse(src)
    payload = function_definition_harvester().harvest(tree, src)

    assert [row[0] for row in payload["typedefs"]] == ["only_a_type_t"]
    assert [row[0] for row in payload["variables"]] == ["only_a_var"], (
        "the two kinds must not bleed into one another's list"
    )


def test_search_discloses_a_dropped_row_only_when_provenance_DIFFERS(
    barren_index: tuple[Path, Path],
) -> None:
    """gh#392, and the narrowing is the whole point of the test.

    `search` collapses per NAME and `documented_first` keeps doxygen's row, so a bare
    recovered row can never hide a documented one. Right in general, and MEASURED WRONG once:
    after gh#395 recovered mbedtls's guarded `mbedtls_threading_mutex_t`, the surviving row
    was the TEST FIXTURE at `tests/include/alt-dummy/threading_alt.h` and the dropped one was
    the shipping type at `include/mbedtls/threading.h`.

    MY FIRST CUT DISCLOSED EVERY DROPPED FILE and was wrong in the way this project warns
    about most: it fired on 22.0% of mbedtls's 7,864 distinct names, including plain
    decl/def pairs, which is a guard firing on the ordinary case and burying the one case
    that matters. Narrowing to a PROVENANCE-CROSSING drop — the event `documented_first`
    actually decided — takes it to 12.7%, and every firing then says something: the row you
    got is doxygen's declaration, and the parser found this name somewhere else too.

    `split_api` is that shape in the fixture: DECLARED in `public.h` where doxygen read it,
    DEFINED in `public.c` behind a guard doxygen could not satisfy. `documented_add` is the
    control — one row, one provenance, nothing to disclose.

    Disclosing rather than re-ranking: inverting the order would let every bare recovered row
    hide a documented one, and preferring a non-test path would hardcode a convention.
    """
    db, repo = barren_index
    recover_ast_symbols(db, repo, None)

    hits = {h.name: h for h in search(db, "split_api")}
    assert "split_api" in hits
    ## The kept row is doxygen's header declaration ...
    assert hits["split_api"].file == "public.h"
    ## ... and the recovered definition's file is NAMED rather than silently dropped.
    assert hits["split_api"].also_in == ("public.c",)

    ## THE CONTROL. A name with a single row must disclose nothing, or the field is noise.
    plain = {h.name: h for h in search(db, "documented_add")}
    assert plain["documented_add"].also_in == ()

    ## THE NARROWING, and it needs its own row because MUTATION SHOWED THE TEST DID NOT
    ## COVER IT: replacing the provenance comparison with `True` left everything above green,
    ## since the fixture had no same-provenance duplicate to be silent about. A plain
    ## decl/def pair — BOTH doxygen's, in two files — is the ordinary case that must stay
    ## quiet, and it is the 22.0% of mbedtls names my first cut fired on.
    conn = sqlite3.connect(str(db))
    try:
        _memberdef(
            conn,
            900,
            name="documented_add",
            definition="int documented_add",
            argsstring="(int a)",
            kind="function",
            static=0,
            bodystart=0,
            bodyend=0,
            bodyfile_id=None,
            file_id=12,
            line=9,
            column=1,
            briefdescription="<para>The header declaration. </para>",
        )
        conn.commit()
    finally:
        conn.close()

    both_doxygen = {h.name: h for h in search(db, "documented_add")}
    assert both_doxygen["documented_add"].also_in == (), (
        "a decl/def pair is BOTH doxygen's — `documented_first` decided nothing across "
        "provenance, so there is nothing to disclose and firing here is pure noise"
    )


## @brief A reference-returning definition must be recovered, not silently skipped.
## @return None.
## @version 1
def test_reference_returning_definitions_are_recovered() -> None:
    """FOUND WHILE FIXING gh#9, AND IT IS THE LARGER OF THE TWO BUGS. `_function_declarator`
    followed `child_by_field_name("declarator")` only, and a `reference_declarator` does NOT
    expose its inner declarator under that field — so the walk returned None and EVERY
    reference-returning definition was absent from the recovery layer whose whole job is
    recovering what doxygen did not emit.

    In C++ that is not an edge case. `const T& accessor()`, `T& operator[]()`, `begin()`/`end()`
    — the shape is everywhere, and all of it was being dropped in silence. The helper's own
    docstring said "pointer/parenthesized"; reference was never in the set.

    HOW IT SURFACED IS THE PART WORTH KEEPING. The macro-reference recovery reused this helper,
    passed five of six measured cases, and failed the ONE that had been reported. A test asserting
    "recovery works" on any single non-reference case would have passed throughout.

    Both the plain and the `const` reference shapes are asserted, plus a pointer return as the
    control that the original behaviour is intact.

    @brief Reference-returning functions reach the recovery layer.
    @return None.
    @version 1
    """
    import tree_sitter_cpp

    from clew.harvest import try_import_tree_sitter

    ts = try_import_tree_sitter()
    assert ts is not None, "precondition: tree-sitter must be importable"
    language_cls, parser_cls = ts

    src = (
        b"#include <array>\n"
        b"struct Row { int a; };\n"
        b"static Row g_row;\n"
        b"static Row g_rows[4];\n"
        b"const std::array<Row, 4>& const_ref_return() { static std::array<Row, 4> k{}; return k; }\n"
        b"Row& plain_ref_return() { return g_row; }\n"
        b"Row* ptr_return() { return &g_row; }\n"
        b"int value_return() { return 1; }\n"
    )
    tree = parser_cls(language_cls(tree_sitter_cpp.language())).parse(src)
    found = {f.name for f in harvest_function_definitions(tree, src)}

    assert "const_ref_return" in found, (
        f"a `const T&`-returning definition was skipped — this is the reported shape; got {found}"
    )
    assert "plain_ref_return" in found, f"a `T&`-returning definition was skipped; got {found}"
    ## THE CONTROLS: the shapes that already worked must keep working, or a fix that recovered
    ## references by loosening the walk into accepting anything would pass the two above.
    assert "ptr_return" in found, "pointer returns were already recovered and must remain so"
    assert "value_return" in found, "plain value returns must remain so"
