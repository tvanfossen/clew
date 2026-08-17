# SPDX-License-Identifier: MIT
"""gh#18 — the Kconfig configuration space, its help text, and its gating sites.

The assertion this file exists for is `test_a_limitation_documented_only_in_help_is
_searchable`: the issue's own "done means" is that `search_prose` finds a limitation
documented nowhere but a `help` block. Everything else here defends it.

THE FIXTURE IS SYNTHETIC AND MIRRORS THE ISSUE'S SHAPE — a `choice` of two motor
variants where the second's `help` records that its overcurrent thresholds are
placeholders reused from the first. It also exercises `source`d files, a `menu`, a
conditional `default` and an `int` type, because those are what a real Kconfig tree
is made of and a single-file fixture would pass while the sourcing path was broken.

WHAT IS DELIBERATELY ASSERTED NEGATIVELY, and why each one is a real failure mode
rather than paranoia:
  - the placeholder phrase must appear in NO other file of the fixture, or the
    search test would pass on a markdown chunk and prove nothing about Kconfig;
  - `#ifndef` must not be recorded as `ifdef`, because that inverts the variant;
  - `IS_ENABLED(...)` in ordinary C must NOT become a gate, because that code is
    compiled either way;
  - a repo with no Kconfig must gain no table, no row and no `kconfig.*` meta, so
    the change is inert for every existing target;
  - a Kconfig that was FOUND and could not be parsed must be distinguishable from a
    repo that has none — this repo's standing lesson is that "no rows" is a claim
    about the detector until you have checked whether the detector could look.

@brief Tests for Kconfig discovery, parsing, storage, prose and gating.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import declaration as decl_mod
from clew.kconfig import (
    KCONFIG_NAME,
    KEY_ROOT,
    SECTION_KCONFIG,
    SOURCE_DECLARED,
    SOURCE_ROOT,
    discover_kconfig,
    import_kconfig,
    ingest_kconfig_prose,
    load_kconfig,
)
from clew.kconfig_gates import (
    declared_macro_names,
    ensure_kconfig_gates_table,
    import_kconfig_gates,
)
from clew.query import resolve_subject, search, subject_dossier
from clew.query.symbols import CONFIG_SYMBOL_KIND
from clew.prose import ingest_supplementary_docs
from clew.query import kconfig_space, search_prose
from clew.query.kconfig import gates_covering
from clew.signature import write_build_signature
from clew.vocabulary import (
    LAYER_STATE_ABSENT,
    LAYER_STATE_EMPTY,
    LAYER_STATE_POPULATED,
    KCONFIG_GATE_IF_EXPR,
    GATE_ORIGIN_DECLARED,
    GATE_ORIGIN_KCONFIG,
    GATE_ORIGIN_UNDECLARED,
    KCONFIG_GATE_IFDEF,
    KCONFIG_GATE_IFNDEF,
)

FIXTURE = Path(__file__).resolve().parent / "data" / "kconfigsample"

## The phrase that exists ONLY inside a `help` block in the fixture. Written out here
## so the control — "it is nowhere else" — is a single assertion rather than a
## comment nobody re-checks.
HELP_ONLY_PHRASE = "placeholder pending real measurements"


## @brief A copy of the Kconfig fixture, writable and isolated per test.
## @return Path to the copied repo root.
## @version 1
@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """COPIED rather than used in place. Several tests add or remove files to reach a
    discovery branch (an ambiguous convention, a missing `source`d file), and doing
    that in `tests/data` would leave the tree dirty and make the tests order-dependent.

    @brief Per-test copy of the synthetic Kconfig repo.
    @return The copy's root.
    @version 1
    """
    import shutil

    root = tmp_path / "repo"
    shutil.copytree(FIXTURE, root)
    return root


## @brief A database with just the `path` table the gate harvest reads.
## @param db Path to create.
## @param rel_paths Repo-relative source paths to register.
## @version 1
def _db_with_paths(db: Path, rel_paths: tuple[str, ...]) -> None:
    """The gate harvest is driven by `run_harvest`, which iterates the `path` table
    doxygen produces. Hand-making just that table keeps these tests off a doxygen run
    — which needs the binary and tens of seconds — while exercising the real harvest
    code rather than a copy of it.

    @brief Create a minimal index carrying only a path table.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE path (name TEXT)")
    conn.executemany("INSERT INTO path(name) VALUES(?)", [(p,) for p in rel_paths])
    conn.commit()
    conn.close()


# ─── part 1: discovery, which never guesses ──────────────────────────────────


def test_an_unambiguous_root_kconfig_is_found_and_stored_repo_relative(repo: Path) -> None:
    """Root first, because an unambiguous root `Kconfig` is the convention every
    Kconfig build system shares. The path must come back REPO-RELATIVE: `build_meta`
    is published over MCP, and an absolute path here is the machine-layout disclosure
    that forced the build-version-9 bump."""
    location = discover_kconfig(repo)
    assert location.source == SOURCE_ROOT
    assert location.path == Path(KCONFIG_NAME)
    assert not location.path.is_absolute()
    assert location.searched, "a discovery that names no locations cannot be audited"


def test_convention_refuses_among_several_candidates(tmp_path: Path) -> None:
    """`discover_doxyfile` was once caught selecting a TEST FIXTURE's Doxyfile to index
    a whole project by resolving strays alphabetically. Here the wrong choice describes
    a configuration space the repo does not ship, and every count taken from it looks
    legitimate — so ambiguity refuses."""
    root = tmp_path / "ambiguous"
    for directory in ("app", "src"):
        (root / directory).mkdir(parents=True)
        (root / directory / KCONFIG_NAME).write_text("config A\n\tbool\n", encoding="utf-8")

    location = discover_kconfig(root)
    assert location.path is None, "two conventional candidates must not be resolved by order"
    assert len(location.searched) > 1


def test_a_single_conventional_candidate_is_accepted(tmp_path: Path) -> None:
    """The refusal above must not be a refusal to look. One candidate is not
    ambiguous, and a fixture that only ever tests the refusal would pass with
    discovery hard-wired to None."""
    root = tmp_path / "app_only"
    (root / "app").mkdir(parents=True)
    (root / "app" / KCONFIG_NAME).write_text("config A\n\tbool\n", encoding="utf-8")

    assert discover_kconfig(root).path == Path("app/Kconfig")


def test_a_declared_root_beats_convention(repo: Path) -> None:
    """CLI flag > declaration > convention is the precedence every other discovery
    here follows. The declared file is deliberately NOT at the root, so a pass cannot
    be explained by the root fallback."""
    (repo / "conf").mkdir()
    (repo / "conf" / KCONFIG_NAME).write_text("config DECLARED_ONLY\n\tbool\n", encoding="utf-8")

    location = discover_kconfig(repo, {SECTION_KCONFIG: {KEY_ROOT: "conf/Kconfig"}})
    assert location.source == SOURCE_DECLARED
    assert location.path == Path("conf/Kconfig")


def test_a_declared_but_missing_root_is_not_silently_replaced_by_convention(repo: Path) -> None:
    """A typo'd declaration must NOT fall through to the root file. Falling through
    would index a different configuration space than the one declared and report
    success — the quiet substitution the no-hardcoding mandate exists to prevent."""
    location = discover_kconfig(repo, {SECTION_KCONFIG: {KEY_ROOT: "conf/Kconfig"}})
    assert location.path is None
    assert location.searched == ("conf/Kconfig",)


def test_the_declaration_section_spelling_is_pinned() -> None:
    """`kconfig.py` does not import `declaration.py` and is not imported by it, so the
    section name is spelled twice. This pins them together, exactly as
    `test_declaration.py` does for `index_scope` and `preprocessor`. A drift here means
    a repo's declaration parses into a mapping nothing reads while the build reports it
    was honoured."""
    assert SECTION_KCONFIG in decl_mod.KNOWN_SECTIONS
    assert decl_mod.SECTION_KCONFIG == SECTION_KCONFIG


# ─── part 2: the space, its choices and its defaults ─────────────────────────


def test_a_sourced_file_is_parsed_and_choices_group_their_members(repo: Path) -> None:
    """`source "Kconfig.motor"` is where a single-file fixture would have passed while
    the real path was broken, so the two grouped variants live there.

    Both members must share ONE choice key. `choice` semantics are the point: exactly
    one member is selected, so a consumer that reads them as independent features will
    describe two mutually exclusive variants as both present."""
    model = load_kconfig(discover_kconfig(repo), repo)
    assert model.error == "", model.error
    by_name = {sym.name: sym for sym in model.symbols}

    assert {"WIDGET_MOTOR_ALPHA", "WIDGET_MOTOR_BETA", "WIDGET_LOG_LEVEL"} <= set(by_name)
    alpha, beta = by_name["WIDGET_MOTOR_ALPHA"], by_name["WIDGET_MOTOR_BETA"]
    assert alpha.choice_key is not None
    assert alpha.choice_key == beta.choice_key
    assert by_name["WIDGET_LOG_LEVEL"].choice_key is None, "an ungrouped symbol has no group"
    assert len(model.choices) == 1
    assert model.choices[0].prompt == "Motor variant"


def test_types_defaults_and_conditions_survive_verbatim(repo: Path) -> None:
    """`default FOO if BAR` and `default FOO` say different things about which variant
    is the unstated one, so the condition is kept. Dropping the `if` would turn a
    conditional default into an unconditional claim."""
    model = load_kconfig(discover_kconfig(repo), repo)
    by_name = {sym.name: sym for sym in model.symbols}

    assert by_name["WIDGET_LOG_LEVEL"].type == "int"
    assert by_name["WIDGET_MOTOR_NAME"].type == "string"
    assert by_name["WIDGET_MOTOR_ALPHA"].type == "bool"
    assert "if" in by_name["WIDGET_MOTOR_NAME"].default, (
        "the conditional default lost its condition, which reads as unconditional"
    )
    assert model.choices[0].default, "a choice's default names the unstated variant"


def test_locations_are_repo_relative_and_point_at_the_declaring_file(repo: Path) -> None:
    """A symbol declared in a `source`d file must report THAT file, not the top-level
    one — otherwise `file:line` cannot be opened. And repo-relative, always."""
    model = load_kconfig(discover_kconfig(repo), repo)
    beta = next(s for s in model.symbols if s.name == "WIDGET_MOTOR_BETA")

    assert beta.file_path == "Kconfig.motor"
    assert not Path(beta.file_path).is_absolute()
    assert beta.line > 0


def test_the_stored_tables_round_trip_through_the_query_layer(repo: Path, tmp_path: Path) -> None:
    """Drives the real pipeline entry point and reads back through R2, so the DDL, the
    inserts and the JOIN are all the shipped ones rather than copies."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    model = import_kconfig(db, repo, None)
    write_build_signature(db, kconfig=model.as_meta())

    space = kconfig_space(db)
    assert space.found is True
    assert space.error == ""
    by_name = {sym.name: sym for sym in space.symbols}
    assert by_name["WIDGET_MOTOR_BETA"].choice == "Motor variant", (
        "the query layer must surface the group's HUMAN identity, not the synthetic key"
    )
    assert by_name["WIDGET_LOG_LEVEL"].choice is None


# ─── part 4: the help text, which is the reason for all of it ────────────────


def test_a_limitation_documented_only_in_help_is_searchable(repo: Path, tmp_path: Path) -> None:
    """THE ISSUE'S OWN "DONE MEANS". A `help` block routinely carries the only
    statement of a known limitation in a repository, and until gh#18 not a word of it
    was indexed.

    The control is the second assertion, and it is what makes the first one mean
    anything: the phrase appears in NO other file of the fixture, so a hit cannot be
    coming from a markdown chunk."""
    others = [
        path
        for path in repo.rglob("*")
        if path.is_file()
        and path.name != "Kconfig.motor"
        and HELP_ONLY_PHRASE in path.read_text(encoding="utf-8", errors="replace")
    ]
    assert others == [], f"the phrase is not help-only any more — also in {others}"

    db = tmp_path / "clew.db"
    _db_with_paths(db, ())
    ingest_supplementary_docs(db, repo)
    assert search_prose(db, HELP_ONLY_PHRASE) == [], (
        "the markdown ingest alone must NOT find it — otherwise this test would pass "
        "without the Kconfig ingest doing anything"
    )

    import_kconfig(db, repo, None)
    hits = search_prose(db, HELP_ONLY_PHRASE)
    assert hits, "a limitation documented only in a help block is still unreachable"
    assert any("MOTOR_BETA" in hit.heading for hit in hits), (
        "the hit must name the symbol the limitation belongs to"
    )


def test_prompt_and_symbol_name_both_reach_the_prose_corpus(repo: Path, tmp_path: Path) -> None:
    """Two different readers search two different ways: an engineer hunting a
    limitation types words from the help text, one auditing a symbol types its name.
    Both have to hit, which is why the name is in the heading AND the content."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ())
    import_kconfig(db, repo, None)

    assert search_prose(db, "CONFIG_WIDGET_MOTOR_BETA"), "the symbol name is unreachable"
    assert search_prose(db, "Motor"), "a prompt word is unreachable"


def test_kconfig_prose_must_be_ingested_after_the_markdown_ingest(
    repo: Path, tmp_path: Path
) -> None:
    """`ingest_supplementary_docs` DROPs and recreates `supplementary_docs` on every
    build. This pins the ORDER the pipeline depends on by demonstrating the failure:
    run the Kconfig ingest first and its rows are deleted, with no error anywhere.

    That is the quietest possible failure mode, so it is asserted rather than left to
    a comment in `cli.py`."""
    wrong = tmp_path / "wrong.db"
    _db_with_paths(wrong, ())
    model = load_kconfig(discover_kconfig(repo), repo)
    assert ingest_kconfig_prose(wrong, model) > 0
    ingest_supplementary_docs(wrong, repo)
    assert search_prose(wrong, HELP_ONLY_PHRASE) == [], (
        "if this finds the phrase the ordering hazard has gone and this test is stale"
    )

    right = tmp_path / "right.db"
    _db_with_paths(right, ())
    ingest_supplementary_docs(right, repo)
    ingest_kconfig_prose(right, model)
    assert search_prose(right, HELP_ONLY_PHRASE), "the pipeline's own order must work"


# ─── part 3: symbol → file:line ──────────────────────────────────────────────


def test_gating_sites_record_the_form_and_the_line(repo: Path, tmp_path: Path) -> None:
    """`ifndef` must NOT be filed as `ifdef`. The C and C++ grammars use ONE node type
    for both directives, so the sense lives only in the leading token — and a consumer
    told the wrong one describes the variant exactly backwards."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    assert import_kconfig_gates(db, repo) > 0

    gates = {(g.symbol, g.form) for g in kconfig_space(db).gates}
    assert ("WIDGET_MOTOR_BETA", KCONFIG_GATE_IFDEF) in gates
    assert ("WIDGET_RADIO", KCONFIG_GATE_IFNDEF) in gates
    assert ("WIDGET_MOTOR_ALPHA", KCONFIG_GATE_IF_EXPR) in gates
    assert ("WIDGET_RADIO", KCONFIG_GATE_IFDEF) not in gates, (
        "the #ifndef site was recorded with the opposite sense"
    )

    beta = next(g for g in kconfig_space(db).gates if g.symbol == "WIDGET_MOTOR_BETA")
    assert beta.file_path == "src/motor.c"
    assert beta.macro == "CONFIG_WIDGET_MOTOR_BETA"
    text = (repo / "src" / "motor.c").read_text(encoding="utf-8").splitlines()
    assert "CONFIG_WIDGET_MOTOR_BETA" in text[beta.line - 1], "the recorded line is wrong"


def test_one_conditional_naming_two_symbols_yields_two_rows(repo: Path, tmp_path: Path) -> None:
    """Both symbols in `#if defined(A) || B > 2` genuinely participate in deciding
    whether the line exists, so both are recorded."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    import_kconfig_gates(db, repo)

    expr = {g.symbol for g in kconfig_space(db).gates if g.form == KCONFIG_GATE_IF_EXPR}
    assert {"WIDGET_MOTOR_ALPHA", "WIDGET_LOG_LEVEL"} <= expr


def test_a_runtime_is_enabled_branch_is_not_a_gate(repo: Path, tmp_path: Path) -> None:
    """`if (IS_ENABLED(CONFIG_X))` in ordinary C is compiled either way. Recording it
    as gating would tell a reader that removing the symbol removes the function.

    Asserted by LINE, because `CONFIG_WIDGET_RADIO` legitimately has a gate elsewhere
    in the same file — a symbol-level assertion would pass while the bug was present."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    import_kconfig_gates(db, repo)

    lines = (repo / "src" / "motor.c").read_text(encoding="utf-8").splitlines()
    runtime_line = next(
        i + 1
        for i, text in enumerate(lines)
        if "IS_ENABLED" in text and text.lstrip().startswith("if (")
    )
    assert all(g.line != runtime_line for g in kconfig_space(db).gates)


def test_a_gate_on_an_undeclared_symbol_is_kept(repo: Path, tmp_path: Path) -> None:
    """Dead code behind a symbol nobody can set is a defect in the target. Filtering
    the gate list to declared symbols would delete the evidence of it, and it is the
    kind of thing this tool exists to surface."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    import_kconfig(db, repo, None)
    import_kconfig_gates(db, repo)

    space = kconfig_space(db)
    assert "WIDGET_UNDECLARED" not in {s.name for s in space.symbols}
    assert "WIDGET_UNDECLARED" in {g.symbol for g in space.gates}


def test_gate_counts_reach_the_symbol_rows(repo: Path, tmp_path: Path) -> None:
    """A symbol that gates nothing must arrive as 0 rather than as an absence a caller
    has to interpret."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    model = import_kconfig(db, repo, None)
    import_kconfig_gates(db, repo)
    write_build_signature(db, kconfig=model.as_meta())

    by_name = {s.name: s for s in kconfig_space(db).symbols}
    assert by_name["WIDGET_MOTOR_BETA"].gate_count == 1
    assert by_name["WIDGET_MOTOR_NAME"].gate_count == 0


# ─── part 4: the gate harvest is not Kconfig-only (gh#390) ──────────────────

## A repository that gates on its OWN macro names and has never heard of Kconfig. This is
## not an exotic shape — it is what mbedtls, and most C, actually looks like.
_NO_KCONFIG_SOURCE = """\
#include <stdio.h>

#ifndef PROJ_WIDGET_H
#define PROJ_WIDGET_H

#if defined(PROJ_THREADING_C) && defined(PROJ_THREADING_PTHREAD)
void widget_lock(void) { }
#endif

#ifdef PROJ_LEGACY
void widget_legacy(void) { }
#endif

#ifndef PROJ_OMIT_TELEMETRY
void widget_telemetry(void) { }
#endif

#ifndef PROJ_GUARD_WITHOUT_H_SUFFIX
#define PROJ_GUARD_WITHOUT_H_SUFFIX
void widget_guarded_twice(void) { }
#endif

#ifdef PROJ_FAST_PATH
void widget_fast(void) { }
#else
void widget_slow(void) { }
#endif

void widget_always(void) { }

#endif
"""

## The `#else` pair above, by line, and the ungated function after it. Written here because
## every assertion about coverage is an assertion about a LINE, and a fixture whose line
## numbers are recomputed by hand in each test drifts from the source it is describing.
_FAST_LINE = _NO_KCONFIG_SOURCE.splitlines().index("void widget_fast(void) { }") + 1
_SLOW_LINE = _NO_KCONFIG_SOURCE.splitlines().index("void widget_slow(void) { }") + 1
_ALWAYS_LINE = _NO_KCONFIG_SOURCE.splitlines().index("void widget_always(void) { }") + 1


## @brief A one-file C repo whose gates use no CONFIG_ prefix.
## @param tmp_path Per-test directory.
## @return (repo root, index path).
## @version 1
def _no_kconfig_repo(tmp_path: Path) -> tuple[Path, Path]:
    """@brief Build a fixture repo that gates on its own macro names.
    @return Repo root and a path-table-only index.
    @version 1
    """
    root = tmp_path / "proj"
    (root / "src").mkdir(parents=True)
    (root / "src" / "widget.c").write_text(_NO_KCONFIG_SOURCE, encoding="utf-8")
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/widget.c",))
    return root, db


## @brief Give a path-only fixture index the memberdef rows `search` ranks against.
## @param db The index to extend.
## @param names Function names to add.
## @version 1
def _add_functions(db: Path, names: tuple[str, ...]) -> None:
    """WITHOUT THESE THE RANK TEST IS VACUOUS. `_db_with_paths` builds only the `path`
    table, which is all the gate HARVEST needs — so a search-ranking assertion over it
    compares the config corpus against nothing and passes however the tiers are set.

    OPT-IN, not folded into `_no_kconfig_repo`, because a PARTIAL `memberdef` is a trap: the
    subject and dossier paths read columns this table does not have (`definition` first), and
    growing a fake schema to satisfy each one in turn produces a fixture that diverges from
    the shipped shape while looking more realistic. Only the ranking query needs it, so only
    the ranking test gets it.

    @brief Add function rows to a minimal index.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    conn.execute(
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, "
        "file_id INTEGER, briefdescription TEXT, initializer TEXT)"
    )
    conn.executemany(
        "INSERT INTO memberdef(name, kind, file_id, briefdescription, initializer) "
        "VALUES(?, 'function', 1, '', '')",
        [(name,) for name in names],
    )
    conn.commit()
    conn.close()


def test_a_repo_that_uses_no_kconfig_still_gets_a_gate_layer(tmp_path: Path) -> None:
    """THE MEASURED DEFECT (gh#390). The harvest matched one hardcoded prefix, `CONFIG_`,
    justified as reading Kconfig's own universal convention. True for a Kconfig repo, and
    it made the layer INERT on the dominant C convention: on mbedtls — 500 files whose
    entire question is "what is compiled in" — `kconfig_gates` existed with exactly the
    right columns and held ZERO rows, so `search("MBEDTLS_THREADING_PTHREAD")` returned a
    confident empty result nine times across one benchmark run.

    A prefix that decides what is HARVESTED is a hardcoded assumption about a target's
    shape, which this project forbids. A prefix that decides how a row is LABELLED is a
    reading of a declaration, which it requires.
    """
    root, db = _no_kconfig_repo(tmp_path)
    assert import_kconfig_gates(db, root) > 0

    gates = {(g.symbol, g.form) for g in kconfig_space(db).gates}
    assert ("PROJ_THREADING_C", KCONFIG_GATE_IF_EXPR) in gates
    assert ("PROJ_THREADING_PTHREAD", KCONFIG_GATE_IF_EXPR) in gates
    assert ("PROJ_LEGACY", KCONFIG_GATE_IFDEF) in gates


def test_defined_is_an_operator_and_never_a_gating_symbol(tmp_path: Path) -> None:
    """`defined` appears in nearly every `#if` a C repository writes, so harvesting it
    would put one meaningless symbol at the top of every gate query by sheer frequency —
    and it is an operator, not a name anybody can set.
    """
    root, db = _no_kconfig_repo(tmp_path)
    import_kconfig_gates(db, root)
    assert "defined" not in {g.symbol for g in kconfig_space(db).gates}


def test_origin_labels_the_declared_variant_without_filtering_the_rest(tmp_path: Path) -> None:
    """CLASSIFY, NEVER FILTER. The declaration says which variant the index REPRESENTS;
    it must not decide which gates exist, or a target that has declared nothing — the
    third-party case the whole declaration model exists to serve — would get an empty
    layer again, for a new reason.
    """
    root, db = _no_kconfig_repo(tmp_path)
    import_kconfig_gates(db, root, declared=["PROJ_THREADING_C=1"])

    origin = {g.symbol: g.origin for g in kconfig_space(db).gates}
    ## Declared WITH a value: the value is not part of the identity a gate matches on.
    assert origin["PROJ_THREADING_C"] == GATE_ORIGIN_DECLARED
    ## Gated on, declared by nothing: kept, and marked as the finding it is.
    assert origin["PROJ_THREADING_PTHREAD"] == GATE_ORIGIN_UNDECLARED
    assert origin["PROJ_LEGACY"] == GATE_ORIGIN_UNDECLARED


def test_a_config_prefixed_symbol_is_labelled_kconfig_whatever_else_is_declared(
    repo: Path, tmp_path: Path
) -> None:
    """`CONFIG_X` is Kconfig's whatever else a target declares — the prefix is a universal
    convention, not a per-repo statement. Reading it the other way would relabel a Zephyr
    tree the moment it also shipped a config header.
    """
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    import_kconfig_gates(db, repo, declared=["CONFIG_WIDGET_MOTOR_BETA"])

    origin = {g.symbol: g.origin for g in kconfig_space(db).gates}
    assert origin["WIDGET_MOTOR_BETA"] == GATE_ORIGIN_KCONFIG


def test_a_gated_on_symbol_is_a_dossier_subject(tmp_path: Path) -> None:
    """THE OTHER HALF OF gh#390, and storing the rows without this fixes nothing a caller
    can see. `_is_config` used to probe declared symbols only, reasoning that a gate on an
    undeclared symbol "is not a subject, because there is nothing to describe". Once the
    harvest widened past the `CONFIG_` prefix there is a great deal to describe — where the
    symbol decides code exists, in how many files, in which form — and that IS the answer
    the benchmark questions wanted. Without this, `dossier` returned a confident negative
    for the exact symbols Q1 and Q2 are about while the rows sat in the table.
    """
    root, db = _no_kconfig_repo(tmp_path)
    import_kconfig_gates(db, root)

    assert "config" in resolve_subject(db, "PROJ_THREADING_PTHREAD")
    subject = subject_dossier(db, "PROJ_THREADING_PTHREAD")
    assert subject is not None
    assert subject.kind == "config"
    assert subject.config is not None
    assert {g.symbol for g in subject.config.gates} == {"PROJ_THREADING_PTHREAD"}


def test_a_name_that_is_neither_declared_nor_gated_is_still_not_a_config_subject(
    tmp_path: Path,
) -> None:
    """THE NEGATIVE HALF. Widening `_is_config` to accept gated-on names must not widen it
    to accept ANY name — a probe that answers yes for everything classifies every string as
    a config symbol and makes the kind meaningless. Without this assertion the widened
    probe could be `return True` and the test above would still pass.
    """
    root, db = _no_kconfig_repo(tmp_path)
    import_kconfig_gates(db, root)
    assert "config" not in resolve_subject(db, "PROJ_NEVER_MENTIONED_ANYWHERE")


def test_an_include_guard_is_not_a_configuration_gate(tmp_path: Path) -> None:
    """DETECTED BY STRUCTURE, NOT BY A `_H` SUFFIX. `#ifndef FOO_H` / `#define FOO_H` tests
    a symbol the very next line defines, which no configuration gate ever does — a config
    gate reads a symbol somebody else set. Widening the harvest past `CONFIG_` (gh#390)
    admitted these, and once they reached `search` (gh#394) they ranked EXACT on their own
    names: 10 of 10 gating symbols in this repo's C fixture were guards.

    THE SUFFIX RULE WOULD HAVE BEEN WRONG, measured on mbedtls: the structural rule removed
    220 symbols where a `_H`-suffix count found only 201, so 19 real guards do not end in
    `_H`. `PROJ_GUARD_WITHOUT_H_SUFFIX` is that case in fixture form.
    """
    root, db = _no_kconfig_repo(tmp_path)
    import_kconfig_gates(db, root)

    symbols = {g.symbol for g in kconfig_space(db).gates}
    assert "PROJ_WIDGET_H" not in symbols
    assert "PROJ_GUARD_WITHOUT_H_SUFFIX" not in symbols, "the suffix is not the rule"


def test_a_plain_ifndef_gate_survives_the_include_guard_exclusion(tmp_path: Path) -> None:
    """THE LOAD-BEARING NEGATIVE. Excluding guards must not exclude every `#ifndef`, and
    the case that proves it is not hypothetical: Q2's whole answer rests on
    `#ifndef MBEDTLS_ALLOW_PRIVATE_ACCESS` at `private_access.h:14`, which is an ifndef
    that does NOT define its own symbol and is therefore a real gate. A rule keyed on the
    directive rather than on the self-define would have deleted it, and the deletion would
    have looked like a tidier gate layer.
    """
    root, db = _no_kconfig_repo(tmp_path)
    import_kconfig_gates(db, root)

    gates = {(g.symbol, g.form) for g in kconfig_space(db).gates}
    assert ("PROJ_OMIT_TELEMETRY", KCONFIG_GATE_IFNDEF) in gates


def test_search_finds_a_gating_symbol_by_name(tmp_path: Path) -> None:
    """gh#394, THE DISCOVERY HALF. After gh#390 stored the rows, `dossier` answered for a
    config symbol and `search` still returned NOTHING — so a caller who did not already
    know the name could not find it, which is the common case for "what turns this on".
    The graded agent searched for these symbols BY NAME nine times in one run and was
    refused every time.

    Asserts the RANK, not just presence: a hit buried below a capped reply is a hit the
    caller never sees.
    """
    root, db = _no_kconfig_repo(tmp_path)
    import_kconfig_gates(db, root)

    hits = search(db, "PROJ_THREADING_PTHREAD")
    assert hits, "a stored gating symbol must be discoverable"
    assert hits[0].name == "PROJ_THREADING_PTHREAD"
    assert hits[0].kind == CONFIG_SYMBOL_KIND
    ## ONE ROW PER SYMBOL, never one per site: MBEDTLS_THREADING_C gates 151 lines and 151
    ## identical-looking hits would bury every other corpus for a query that means one thing.
    assert len([h for h in hits if h.kind == CONFIG_SYMBOL_KIND]) == 1


def test_a_config_symbol_does_not_outrank_a_function_it_gates(tmp_path: Path) -> None:
    """THE COST OF THE NEW CORPUS, bounded. A gating symbol habitually shares every token
    with the function it gates, and the function is the row a caller can read a body for.
    The config tier breaks a TIE only, so a query that spells neither name exactly must
    still put the function first — otherwise adding the corpus degrades every existing
    query, which is how the neighbour-cap experiment cost 48% in tokens.
    """
    root, db = _no_kconfig_repo(tmp_path)
    _add_functions(db, ("widget_lock", "widget_telemetry"))
    import_kconfig_gates(db, root)

    ## "telemetry" is carried by BOTH `widget_telemetry` (function) and `PROJ_OMIT_TELEMETRY`
    ## (gate), and is an exact match for neither — which is the collision this tier exists to
    ## settle. A query matching only one corpus would pass whatever the tiers were.
    hits = search(db, "telemetry")
    kinds = [h.kind for h in hits]
    assert "function" in kinds, "the fixture's functions must still be findable"
    assert CONFIG_SYMBOL_KIND in kinds, "and a gating symbol must be in the same reply"
    assert kinds.index("function") < kinds.index(CONFIG_SYMBOL_KIND)

    ## AND THE EXACT NAME STILL WINS, or the tier has become a demotion rather than a
    ## tie-break and the corpus is unusable for the query it was added for.
    exact = search(db, "PROJ_OMIT_TELEMETRY")
    assert exact[0].kind == CONFIG_SYMBOL_KIND


def test_declared_macro_names_drops_the_value_half(tmp_path: Path) -> None:
    """PREDEFINED entries carry an optional `=value`, and comparing raw strings would
    classify every valued macro as undeclared — silently, on the exact repos that bother
    to declare one.

    THE QUOTED SHAPE IS THE ONE THAT MATTERED, AND THIS TEST USED TO OMIT IT. `macros` holds
    ALREADY-RENDERED doxygen tokens — `'"NAME"'`, quotes included, because rendering the Doxyfile
    is what they were built for — and this function stripped the value while leaving the quotes.
    So `'"PROBE_DECLARED"'` matched no bare symbol and EVERY macro a build actually declared was
    labelled `undeclared`: `kconfig_gates.origin` reported an entire configuration as absent from
    the build that declared it.

    It survived because the case above is the only one this test asserted — unquoted inputs that
    the pipeline never produces. That is the recorded shape "the fixture matched the detector
    rather than the world", and no mutation control could have caught it either, because a
    mutation control tests the code against its fixtures while only a real build tests the
    fixtures. What found it was an integration control asking ONE build to distinguish a
    satisfied gate from an unsatisfied one.

    The function now delegates to `preprocessor.bare_macro_names`, so both assertions below
    exercise the single shared spelling.
    """
    assert declared_macro_names(["A", "B=1", " C = 2 ", ""]) == frozenset({"A", "B", "C"})
    assert declared_macro_names(['"PROBE_DECLARED"', '"WITH_VALUE=1"']) == frozenset(
        {"PROBE_DECLARED", "WITH_VALUE"}
    ), "the RENDERED doxygen shape is what the pipeline passes; the bare shape never reaches it"


# ─── part 5: provenance, and the three ways to be empty ─────────────────────


def test_a_repo_with_no_kconfig_is_completely_unaffected(tmp_path: Path) -> None:
    """The whole change must be inert for every existing target: no table created, no
    prose chunk, no `kconfig.*` row, and an honest `found: false` from the query
    layer."""
    root = tmp_path / "plain"
    (root / "src").mkdir(parents=True)
    (root / "src" / "main.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/main.c",))

    model = import_kconfig(db, root, None)
    write_build_signature(db, kconfig=model.as_meta())

    assert model.as_meta() == {}, "a repo with no Kconfig must stamp no kconfig.* row"
    conn = sqlite3.connect(str(db))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    metas = {row[0] for row in conn.execute("SELECT key FROM build_meta")}
    conn.close()
    assert "kconfig_symbols" not in tables
    assert "kconfig_choices" not in tables
    assert not any(key.startswith("kconfig.") for key in metas)

    space = kconfig_space(db)
    assert space.found is False
    assert space.symbols == ()
    assert space.error == ""


def test_store_kconfig_refuses_an_unfound_model_on_its_own(tmp_path: Path) -> None:
    """FOUND BY A CONTROL, and the control is the only reason this exists.

    `test_a_repo_with_no_kconfig_is_completely_unaffected` passed with
    `store_kconfig`'s own `found` guard removed, because `import_kconfig` short-circuits
    before reaching it — so the guard was untested and the test above was proving the
    short-circuit, not the guard. Both paths lead to "create no tables", and a defence
    that only one of them exercises is a defence that will be deleted as dead code.

    This drives `store_kconfig` directly, which is what makes the guard load-bearing.
    """
    from clew.kconfig import KconfigLocation, KconfigModel, store_kconfig

    db = tmp_path / "clew.db"
    _db_with_paths(db, ())
    assert store_kconfig(db, KconfigModel(location=KconfigLocation(path=None))) == 0

    conn = sqlite3.connect(str(db))
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    conn.close()
    assert "kconfig_symbols" not in tables
    assert "kconfig_choices" not in tables


def test_a_kconfig_that_cannot_be_parsed_is_recorded_rather_than_silent(
    repo: Path, tmp_path: Path
) -> None:
    """THE CASE A HARD DEPENDENCY DOES NOT COVER. A Zephyr application's top-level
    Kconfig `source`s the Zephyr tree's own, so indexing it outside a west workspace
    fails to parse — ordinarily, not exotically.

    That must be distinguishable from a repo with no Kconfig. Both present as zero
    symbols, and this repo's standing lesson is that "no rows" is a claim about the
    detector until you have checked whether the detector could look."""
    (repo / "Kconfig.motor").unlink()
    db = tmp_path / "clew.db"
    _db_with_paths(db, ())

    model = import_kconfig(db, repo, None)
    write_build_signature(db, kconfig=model.as_meta())

    assert model.found is True, "discovery succeeded; only the parse failed"
    assert model.error, "a failed parse must be recorded, not swallowed"
    assert model.symbols == ()

    space = kconfig_space(db)
    assert space.found is True
    assert space.error, "the query layer must report the parse failure, not a bare empty"
    assert space.symbols == ()


def test_a_measured_zero_survives_the_build_signature(tmp_path: Path) -> None:
    """`write_build_signature` DROPS falsy values, so every count is passed as a
    STRING: `"0"` is truthy where `0` is not. gh#6 and gh#17 both had to work around
    this, and forgetting it here would erase exactly the finding that matters —
    "we found a Kconfig and it declares nothing"."""
    root = tmp_path / "empty_space"
    root.mkdir()
    (root / KCONFIG_NAME).write_text("# a comment and nothing else\n", encoding="utf-8")
    db = tmp_path / "clew.db"
    _db_with_paths(db, ())

    model = import_kconfig(db, root, None)
    write_build_signature(db, kconfig=model.as_meta())

    assert model.found is True
    assert model.symbols == ()
    conn = sqlite3.connect(str(db))
    meta = dict(conn.execute("SELECT key, value FROM build_meta"))
    conn.close()
    assert meta["kconfig.symbol_count"] == "0", "the measured zero was dropped as falsy"
    assert meta["kconfig.source"] == SOURCE_ROOT


def test_the_configured_variant_travels_beside_the_space(repo: Path, tmp_path: Path) -> None:
    """Structure and instance must arrive TOGETHER and stay LABELLED. An agent reading
    a `default` without knowing which variant the index was built in will describe the
    default as what the firmware does — which is the confusion gh#18 part 5 names."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ())
    model = import_kconfig(db, repo, None)
    write_build_signature(
        db,
        kconfig=model.as_meta(),
        preprocessor={"predefined": '"CONFIG_WIDGET_MOTOR_BETA"', "source": "declared"},
    )

    space = kconfig_space(db)
    assert "CONFIG_WIDGET_MOTOR_BETA" in space.configured_macros
    assert space.symbols, "the space must still be reported alongside the instance"


def test_the_gate_list_can_be_narrowed_to_one_symbol(repo: Path, tmp_path: Path) -> None:
    """Accepts the name bare or `CONFIG_`-prefixed, because a caller reading a gate out
    of source has the prefixed form in front of them and requiring them to strip it
    produces a confident empty result — the failure gh#31 records for `search`."""
    db = tmp_path / "clew.db"
    _db_with_paths(db, ("src/motor.c",))
    import_kconfig_gates(db, repo)

    bare = kconfig_space(db, "WIDGET_MOTOR_BETA").gates
    prefixed = kconfig_space(db, "CONFIG_WIDGET_MOTOR_BETA").gates
    assert bare == prefixed
    assert bare and {g.symbol for g in bare} == {"WIDGET_MOTOR_BETA"}


## @brief A gate's recorded extent covers only the branch its own form describes.
## @return None.
## @version 1
def test_a_gate_covers_its_own_branch_and_the_else_gets_inverted_polarity(tmp_path: Path) -> None:
    """THE POLARITY TRAP, WHICH IS THE WHOLE REASON THE EXTENT IS NOT THE NODE'S EXTENT. Measured
    with `.claude/tmp/gate_extent_probe.py`: tree-sitter parses

        #ifdef PROJ_FAST_PATH / void widget_fast / #else / void widget_slow / #endif

    as ONE `preproc_ifdef` spanning the whole construct, with the `#else` as its `alternative`
    child. So a range join over the node's own extent reports `widget_slow` as present when
    `PROJ_FAST_PATH` is SET — the exact inverse of the truth, stated with full confidence. That is
    worse than no answer, and it is invisible to any test that only checks a gate was found.

    THE ASSERTIONS ARE A PAIR AND BOTH ARE LOAD-BEARING: `widget_fast` must be covered by `ifdef`
    and NOT by `ifndef`; `widget_slow` the other way round. A single-sided check passes against an
    implementation that reports both gates on both lines, which is the natural result of storing
    the node's extent and the thing this fixture exists to catch.

    @brief Extents stop at the else, and the else inverts.
    @version 1
    """
    root, db = _no_kconfig_repo(tmp_path)
    assert import_kconfig_gates(db, root) > 0

    conn = sqlite3.connect(str(db))
    try:
        fast, fast_unknown = gates_covering(conn, "src/widget.c", _FAST_LINE)
        slow, _ = gates_covering(conn, "src/widget.c", _SLOW_LINE)
        always, _ = gates_covering(conn, "src/widget.c", _ALWAYS_LINE)
    finally:
        conn.close()

    assert fast_unknown == 0, "every gate in this file was harvested with an extent"
    fast_forms = {(g.macro, g.form) for g in fast}
    slow_forms = {(g.macro, g.form) for g in slow}
    assert ("PROJ_FAST_PATH", KCONFIG_GATE_IFDEF) in fast_forms, (
        f"the true branch must report the symbol as REQUIRED: {sorted(fast_forms)}"
    )
    assert ("PROJ_FAST_PATH", KCONFIG_GATE_IFNDEF) not in fast_forms, (
        "the true branch must NOT also report the inverted gate — that is the node-extent bug"
    )
    assert ("PROJ_FAST_PATH", KCONFIG_GATE_IFNDEF) in slow_forms, (
        f"the else branch is present when the symbol is NOT set: {sorted(slow_forms)}"
    )
    assert ("PROJ_FAST_PATH", KCONFIG_GATE_IFDEF) not in slow_forms, (
        "reporting the else branch as gated ON the symbol inverts the variant a reader concludes"
    )
    ## THE NEGATIVE HALF. A function outside every conditional must come back with nothing;
    ## without this the feature could report every gate in the file for every line and still
    ## satisfy both assertions above.
    assert not always, (
        f"an ungated function must report no gates, not the file's gates: {sorted(always)}"
    )


## @brief A gate with no recorded extent is counted, never guessed at.
## @return None.
## @version 1
def test_a_gate_without_an_extent_is_reported_as_unknown_not_as_ungated(tmp_path: Path) -> None:
    """THE THIRD STATE, which this project has been bitten by in five other places: an index built
    before the extent column stores `end_line = 0`, and both available guesses are wrong in a way
    that reads as an answer. Treating it as covering nothing reports a fully gated file as
    ungated; treating it as covering the rest of the file attributes ordinary code to the last
    conditional above it.

    So the count travels with the answer, and an empty `gates` beside a non-zero count means "this
    index cannot tell" — a different statement from "this function is ungated". Simulated by
    dropping the column, which is exactly what an older index looks like to the reader.

    @brief Unknown extent is disclosed, not resolved.
    @version 1
    """
    root, db = _no_kconfig_repo(tmp_path)
    assert import_kconfig_gates(db, root) > 0
    conn = sqlite3.connect(str(db))
    try:
        ## An index built before the column: same rows, no extent.
        conn.execute("ALTER TABLE kconfig_gates DROP COLUMN end_line")
        conn.commit()
        gates, unknown = gates_covering(conn, "src/widget.c", _FAST_LINE)
    finally:
        conn.close()
    assert gates == (), "with no extent recorded, no gate can honestly be placed on a line"
    assert unknown > 0, (
        "an unplaceable gate must be COUNTED — an empty list with a zero count claims the "
        "function is ungated, which is a different and unearned answer"
    )


# ─── part 6: `found` is about KCONFIG; the gate harvest speaks for itself (gh#404) ──


## @brief The three states of the gate layer, each on its own database.
## @return None.
## @version 1
def test_the_gate_layer_reports_its_own_state_independently_of_kconfig(tmp_path: Path) -> None:
    """gh#404 — `found` ANSWERS A DIFFERENT QUESTION THAN THE ONE CALLERS ASK. It is true when a
    Kconfig was discovered and parsed, which is all it ever claimed. But a caller reads
    `found: false` as "this repository has no configuration space", and mbedtls — which has no
    Kconfig — measured 12,096 gating sites over 1,107 distinct symbols. Kconfig is a Zephyr/Linux
    convention; a header of `#define`s is the dominant C one, and reporting the dominant case as
    absence is the misreport `KconfigSpace` exists to prevent, one level up.

    ALL THREE STATES, because the two that look alike are the ones this project keeps confusing. A
    table that EXISTS and holds nothing is a measurement — the harvest ran over this repo and found
    no gating site. An ABSENT table is a detector that never looked. Only the first is evidence
    about the repository, and a test asserting just `populated` would leave them interchangeable.

    @brief populated / empty / absent are distinguishable.
    @version 1
    """
    ## POPULATED: no Kconfig anywhere, but the gate harvest saw two symbols.
    gated, _db = _no_kconfig_repo(tmp_path / "gated")
    assert import_kconfig_gates(_db, gated) > 0
    space = kconfig_space(_db, None)
    assert space.found is False, "this fixture has no Kconfig — `found` must stay honest about that"
    assert space.gate_state == LAYER_STATE_POPULATED
    assert space.gate_symbols > 0, "the harvest saw gating symbols and must say how many"
    ## The question a caller actually has, answerable at last.
    assert space.found or space.gate_state == LAYER_STATE_POPULATED

    ## EMPTY: the table exists because the harvest ran; it found nothing to record.
    empty_db = tmp_path / "empty.db"
    conn = sqlite3.connect(str(empty_db))
    conn.execute("CREATE TABLE path (name TEXT, type INT)")
    ensure_kconfig_gates_table(conn)
    conn.commit()
    conn.close()
    empty_space = kconfig_space(empty_db, None)
    assert empty_space.gate_state == LAYER_STATE_EMPTY, (
        "a table that exists and holds nothing is a MEASUREMENT, not an absent detector"
    )
    assert empty_space.gate_symbols == 0

    ## ABSENT: no gate table at all — an older index, or a build where the layer never ran.
    bare_db = tmp_path / "bare.db"
    conn = sqlite3.connect(str(bare_db))
    conn.execute("CREATE TABLE path (name TEXT, type INT)")
    conn.commit()
    conn.close()
    bare_space = kconfig_space(bare_db, None)
    assert bare_space.gate_state == LAYER_STATE_ABSENT, (
        "an absent layer must NOT read as an empty one — that is the substitution this whole "
        "class was written to prevent"
    )


## @brief The configured-macro list must say what it is evidence OF, and route to the default.
## @return None.
## @version 1
def test_configured_macros_carry_their_provenance_and_a_route() -> None:
    """THE PAYLOAD ARGUED FOR A FALSE ANSWER, which is worse than withholding a true one.

    Measured on Mbed-TLS/mbedtls 2026-08-14. The acceptance build states
    `MBEDTLS_THREADING_C` and `MBEDTLS_THREADING_PTHREAD` as PREDEFINED so doxygen can reach the
    guarded bodies. Every reply then carried
    `configured_macros: "MBEDTLS_THREADING_C" "MBEDTLS_THREADING_PTHREAD"` and labelled all 154
    matching gate rows `origin: "declared"` — while the repository ships both COMMENTED OUT at
    `include/mbedtls/mbedtls_config.h:3787` and `:2196`. Two graded marks ask for exactly that
    shipped state, and both `search(corpus='config')` and `dossier` pointed the other way,
    because they share this payload.

    FOUR STATES, and the MIXED one is the trap that caught my own first version. It said "these
    were STATED BY THE OPERATOR" whenever any statement was involved, which on mbedtls describes
    2 macros out of 144 — the other 142 come from the repository's own header. That inverts the
    disclosure in the opposite direction, inviting a reader to discount the whole list as a build
    artifact. A correction that is wrong the other way is not a correction.

    AND THE LEAD SENTENCE IS CONDITIONAL, because "never a statement about the default" is FALSE
    when the list WAS read from the repository's header, and a note contradicting its own next
    sentence teaches a reader to skip it.
    """
    from clew.query.kconfig import macros_meaning

    header = "include/mbedtls/mbedtls_config.h"

    stated = macros_meaning('"MBEDTLS_THREADING_C"', "declared", header)
    assert "STATED BY THE OPERATOR" in stated
    assert "may well be OFF, or commented out" in stated
    assert header in stated, "the ROUTE is the point — a disclaimer alone leaves the agent hunting"

    mixed = macros_meaning('"A" "B"', "declared+config_header", header)
    assert "COMBINES" in mixed
    assert "STATED BY THE OPERATOR" not in mixed, (
        "on mbedtls this list is 142/144 read from the repository — claiming the operator stated "
        "it inverts the disclosure the other way"
    )
    assert header in mixed

    from_repo = macros_meaning('"A"', "config_header", header)
    assert "does describe what the repository builds by default" in from_repo
    assert "not a statement about what the repository" not in from_repo, (
        "the lead must not contradict the sentence after it"
    )

    ## NO HEADER DECLARED: the default is UNKNOWN, said so, and never implied to be this list.
    unknown = macros_meaning('"A"', "declared", "")
    assert "No config header is recorded" in unknown
    assert "treat the default as unknown" in unknown

    ## NOTHING RECORDED AT ALL stays silent rather than emitting a note about an absent value.
    assert macros_meaning("", "", "") == ""


## @brief The config corpus lists SYMBOLS and filters on text, instead of dumping every site.
## @return None.
## @version 1
def test_the_config_inventory_lists_symbols_and_honours_text(tmp_path: Path) -> None:
    """A 2.1 MB REPLY ON THE AXIS UNDER TEST. `search(corpus='config', text='MBEDTLS_THREADING_C')`
    returned 2,149,463 characters on mbedtls 2026-08-14 — all 12,096 gate SITES, because inventory
    corpora ignored `text` — while reporting `found: false` for a symbol whose name sits in
    `configured_macros` in the same reply. In a graded cell that is a budget-destroying reply or a
    bail-out.

    The corpus's own contract is "the question `dossier` cannot answer: which symbols EXIST", and
    the sites are not that. `dossier` already returned one symbol's sites correctly filtered, so
    this is the corpus returning its own inventory rather than a new capability. Re-measured after
    the change: 5,423 characters filtered, 17,057 unfiltered.

    THE EMPTY `gates` LIST MUST NOT READ AS "NOTHING GATES CODE HERE" — the exact ambiguity
    `found`/`source`/`error` exist to prevent — so `gates_meaning` says the sites were omitted
    deliberately and names the call that returns them.
    """
    import sqlite3

    from clew.query.kconfig import _NAME_CAP, gates_meaning, kconfig_space

    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE kconfig_gates (
            symbol TEXT, macro TEXT, form TEXT, file_path TEXT, line INTEGER,
            origin TEXT, end_line INTEGER
        );
        INSERT INTO kconfig_gates VALUES ('MBEDTLS_THREADING_C','MBEDTLS_THREADING_C','if_expr','a.c',1,'declared',3);
        INSERT INTO kconfig_gates VALUES ('MBEDTLS_THREADING_C','MBEDTLS_THREADING_C','if_expr','b.c',9,'declared',11);
        INSERT INTO kconfig_gates VALUES ('MBEDTLS_SSL_PROTO_TLS1_3','MBEDTLS_SSL_PROTO_TLS1_3','ifdef','c.c',4,'undeclared',6);
        """
    )
    conn.commit()
    conn.close()

    ## INVENTORY FORM: names, no sites.
    inventory = kconfig_space(db, None, include_gates=False)
    assert inventory.gate_symbol_names == ("MBEDTLS_SSL_PROTO_TLS1_3", "MBEDTLS_THREADING_C")
    assert inventory.gates == (), "the inventory form must NOT carry the per-site rows"
    assert "omitted" in inventory.gates_meaning and "dossier" in inventory.gates_meaning, (
        "an empty gates list must say it was omitted and where the sites are"
    )

    ## `text` FILTERS, which is the whole difference between a usable reply and a 2 MB one.
    filtered = kconfig_space(db, "MBEDTLS_THREADING_C", include_gates=False)
    assert filtered.gate_symbol_names == ("MBEDTLS_THREADING_C",)
    ## The CONFIG_ prefix is accepted too — a caller reading a gate out of source has it in hand.
    assert kconfig_space(db, "CONFIG_MBEDTLS_THREADING_C", include_gates=False).gate_symbol_names

    ## THE SITE FORM IS UNCHANGED, or this fix would have removed the answer instead of bounding
    ## it. `dossier` uses this path and must still get every row for its symbol.
    sites = kconfig_space(db, "MBEDTLS_THREADING_C")
    assert len(sites.gates) == 2, "naming a symbol must still return ITS sites"
    assert sites.gates_meaning == "", "the site form has nothing omitted to explain"

    ## THE CAP SAYS SO. A truncated inventory that stays silent reads as the whole space.
    assert f"{_NAME_CAP}" in gates_meaning(_NAME_CAP, _NAME_CAP + 7, False)
    assert "7 are not shown" in gates_meaning(_NAME_CAP, _NAME_CAP + 7, False)
    assert gates_meaning(3, 3, False) and "not shown" not in gates_meaning(3, 3, False)
    ## Nothing measured stays silent rather than describing an absent layer.
    assert gates_meaning(0, 0, False) == ""
