# SPDX-License-Identifier: MIT
"""Five-tier layered-option resolution (gh#319).

The rule under test: `resolved = (tier1 or tier2 or tier5) union tier3 union tier4`
— you can correct our guesses, you cannot un-discover a fact.

Every test here was run against the pre-change code and watched to fail, or is a
success-path assertion added because this repo has shipped a check that tested
only its failure path.
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

import pytest

from clew.buildoptions import MANIFEST_OPTIONS
from clew.cli import (
    OPTION_ENTRY_PATTERNS,
    OPTION_KEY_ALIAS_PREFIXES,
    _entry_patterns,
    _manifest_option_tiers,
    _recorded_entry_patterns,
    _replay_manifest_statements,
)
from clew.declaration import (
    KNOWN_SECTIONS,
    SECTION_DISPATCH,
    SECTION_ENTRY_PATTERNS,
    SECTION_LOCKS,
    SECTION_MQTT,
    SECTION_SHARED_KEY,
    SECTION_THREADS,
)
from clew.propose.notindexed import _like, seeds_reachability
from clew.reachability import (
    DEFAULT_ENTRY_PATTERNS,
    ENTRY_PATTERN_FACTS,
    ENTRY_PATTERN_HEURISTICS,
)
from clew.shared_key_edges import (
    DEFAULT_KEY_ALIAS_PREFIXES,
    KEY_ALIAS_FIELD,
    resolve_key_alias_prefixes,
    resolve_shared_key_patterns,
)
from clew.signature import write_build_signature
from clew.tiers import (
    ACCUMULATING_TIERS,
    EXPLICIT_KEY,
    OPTIONS_META_PREFIX,
    STATED_TIERS,
    TIER_DECLARED,
    TIER_ECOSYSTEM,
    TIER_EXPLICIT,
    TIER_HEURISTIC,
    TIER_KEY,
    TIER_ORDER,
    TIER_TARGET_FACT,
    DocumentResolution,
    LayeredResolution,
    canonical_document,
    options_meta,
    recorded_document,
    recorded_explicit,
    resolve_document,
    resolve_layered,
    stated_options,
)

FACTS = ("fact_a", "fact_b")
ECOSYSTEM = ("eco_a",)
GUESSES = ("%guess_a%", "%guess_b%")


# ── the combination rule ────────────────────────────────────────────────────


def test_a_target_stating_nothing_gets_facts_and_guesses_together() -> None:
    """THE SUCCESS PATH, and it is here deliberately.

    A check with a test for its failure path and none for its success path shipped
    a completely broken install path in this repo while the suite stayed green. The
    interesting failure of a rule that protects facts from being dropped is that it
    drops the guesses instead, and only this asserts otherwise.
    """
    resolved = resolve_layered(facts=FACTS, ecosystem=ECOSYSTEM, heuristics=GUESSES)
    assert resolved.values == (*FACTS, *ECOSYSTEM, *GUESSES)
    assert resolved.tier == TIER_HEURISTIC
    assert resolved.stated == GUESSES


def test_an_explicit_statement_displaces_the_guesses_and_keeps_the_facts() -> None:
    """Tier 1 replaces tier 5; tiers 3 and 4 accumulate underneath."""
    resolved = resolve_layered(
        facts=FACTS, ecosystem=ECOSYSTEM, heuristics=GUESSES, explicit=["%mine%"]
    )
    assert resolved.values == (*FACTS, *ECOSYSTEM, "%mine%")
    assert resolved.tier == TIER_EXPLICIT
    for guess in GUESSES:
        assert guess not in resolved.values


def test_a_declaration_displaces_the_guesses_and_keeps_the_facts() -> None:
    """Tier 2 behaves exactly as tier 1 does against the guesses."""
    resolved = resolve_layered(
        facts=FACTS, ecosystem=ECOSYSTEM, heuristics=GUESSES, declared=["%theirs%"]
    )
    assert resolved.values == (*FACTS, *ECOSYSTEM, "%theirs%")
    assert resolved.tier == TIER_DECLARED


def test_tier_one_beats_tier_two() -> None:
    """A flag is a deliberate one-off override of the repo's standing statement."""
    resolved = resolve_layered(
        facts=FACTS, heuristics=GUESSES, declared=["%theirs%"], explicit=["%mine%"]
    )
    assert resolved.values == (*FACTS, "%mine%")
    assert resolved.tier == TIER_EXPLICIT


def test_an_empty_explicit_list_withdraws_rather_than_states() -> None:
    """`--entry-patterns` with no values falls back, it does not resolve to nothing.

    Collapsing this into "states an empty set" would make a recorded statement
    unwithdrawable except by deleting the database, and would seed reachability
    from the facts alone.
    """
    resolved = resolve_layered(facts=FACTS, heuristics=GUESSES, declared=["%theirs%"], explicit=[])
    assert resolved.tier == TIER_DECLARED
    assert resolved.values == (*FACTS, "%theirs%")

    bare = resolve_layered(facts=FACTS, heuristics=GUESSES, explicit=[])
    assert bare.tier == TIER_HEURISTIC
    assert bare.values == (*FACTS, *GUESSES)


def test_a_restated_fact_is_not_duplicated() -> None:
    """An operator restating `main` gets one seed, not two."""
    resolved = resolve_layered(facts=FACTS, heuristics=GUESSES, explicit=["fact_a", "%mine%"])
    assert resolved.values == (*FACTS, "%mine%")


def test_the_tier_names_partition_into_stated_and_accumulating() -> None:
    """Nothing may be in both groups, and nothing may be in neither."""
    assert set(STATED_TIERS) | set(ACCUMULATING_TIERS) == set(TIER_ORDER)
    assert not set(STATED_TIERS) & set(ACCUMULATING_TIERS)
    assert set(ACCUMULATING_TIERS) == {TIER_TARGET_FACT, TIER_ECOSYSTEM}


# ── entry patterns: the first migrated consumer ─────────────────────────────


def test_the_default_entry_pattern_set_is_exactly_the_two_halves() -> None:
    """The composed constant is the ONE answer for "what a silent target gets"."""
    assert DEFAULT_ENTRY_PATTERNS == [*ENTRY_PATTERN_FACTS, *ENTRY_PATTERN_HEURISTICS]
    assert set(ENTRY_PATTERN_FACTS) == {"main", "app_main"}
    assert not set(ENTRY_PATTERN_FACTS) & set(ENTRY_PATTERN_HEURISTICS)


def test_an_explicit_flag_no_longer_drops_the_language_entry_point() -> None:
    """THE BUG. Watched failing before the change: `--entry-patterns %mystyle%`
    resolved to `['%mystyle%']`, so `main` and `app_main` were not seeds, liveness
    collapsed, and nothing in the build or the index said so.
    """
    args = argparse.Namespace(entry_patterns=["%mystyle%"])
    resolved = _entry_patterns(args, {})
    assert "main" in resolved.values
    assert "app_main" in resolved.values
    assert "%mystyle%" in resolved.values
    assert "%init%" not in resolved.values
    assert resolved.tier == TIER_EXPLICIT


def test_a_declared_vocabulary_replaces_the_guesses_and_keeps_the_facts() -> None:
    """Also watched failing before the change, in the other direction: the
    declaration used to EXTEND the whole default set, so `%init%` survived.
    """
    args = argparse.Namespace(entry_patterns=None)
    resolved = _entry_patterns(args, {SECTION_ENTRY_PATTERNS: ["%trampoline%", "dispatch_%"]})
    assert resolved.values == ("main", "app_main", "%trampoline%", "dispatch_%")
    assert resolved.tier == TIER_DECLARED


def test_a_silent_target_resolves_to_the_whole_built_in_set() -> None:
    """The success path for the migrated consumer specifically."""
    resolved = _entry_patterns(argparse.Namespace(entry_patterns=None), {})
    assert list(resolved.values) == DEFAULT_ENTRY_PATTERNS
    assert resolved.tier == TIER_HEURISTIC


# ── the second consumer ─────────────────────────────────────────────────────

## Names chosen to straddle the split: two match only the tier-3 facts, four match
## only tier-5 guesses, one matches neither. A probe set that hit only one half
## would let a consumer reading one half alone pass.
_PROBES = (
    "main",
    "app_main",
    "sensor_init",
    "rx_task",
    "on_error_handler",
    "poll_callback",
    "compute_checksum",
    "Initialize",
)


def test_the_proposer_and_reachability_agree_on_what_an_entry_point_is() -> None:
    """CONTROL FOR THE SPLIT'S SECOND CONSUMER.

    `propose/notindexed.seeds_reachability` mirrors the pattern set "as SQLite
    would apply it", so after splitting the constant it can silently disagree with
    the pass it claims to mirror — and the disagreement surfaces as a hazard report
    that omits the `main` collision the module exists to warn about.

    Compared against the RESOLVER's own no-statement result, not against the
    constant, so a change to how the default set is composed fails here too. Both
    sides use the same `_like`, which is the point: the question under test is
    WHICH PATTERNS each side uses, not how LIKE is implemented.
    """
    expected_patterns = _entry_patterns(argparse.Namespace(entry_patterns=None), {}).values
    for name in _PROBES:
        expected = any(_like(name.lower(), pattern) for pattern in expected_patterns)
        assert seeds_reachability(name) is expected, name


def test_the_probe_set_straddles_both_halves_of_the_split() -> None:
    """Without this the agreement test could pass on a consumer reading one half.

    A probe set that happened to contain only fact-matching names would be
    satisfied by a `seeds_reachability` that had dropped the heuristics entirely.
    """
    fact_only = [n for n in _PROBES if any(_like(n.lower(), p) for p in ENTRY_PATTERN_FACTS)]
    guess_only = [n for n in _PROBES if any(_like(n.lower(), p) for p in ENTRY_PATTERN_HEURISTICS)]
    assert len(fact_only) >= 2, fact_only
    assert len(guess_only) >= 2, guess_only
    assert any(not seeds_reachability(n) for n in _PROBES), "no negative probe"


# ── key alias prefixes: the second migrated consumer (tier 4) ───────────────


def test_a_declared_alias_prefix_does_not_drop_the_ingot_default() -> None:
    """THE BUG, watched failing before the change: `tuple(declared) or DEFAULTS`
    meant declaring `APP_KEY_` resolved to `('APP_KEY_',)` and the ingot `DM_KEY_`
    normalization silently stopped, leaving an orphan write-half.
    """
    resolved = resolve_key_alias_prefixes({KEY_ALIAS_FIELD: ["APP_KEY_"]})
    assert set(resolved.values) == {"APP_KEY_", *DEFAULT_KEY_ALIAS_PREFIXES}
    assert resolved.tier == TIER_DECLARED


def test_a_target_declaring_no_alias_prefixes_gets_the_ingot_defaults() -> None:
    """THE SUCCESS PATH. The equivalent of the entry-pattern control that catches
    the inverse failure — a rule that protects the defaults by dropping everything
    else, or one that resolves to nothing at all when no declaration exists.

    The tier reads `heuristic` because nothing was stated and this option has an
    EMPTY tier-5 layer; for `key_alias_prefixes` that label means "defaults only",
    not "a guess was used".
    """
    resolved = resolve_key_alias_prefixes(None)
    assert resolved.values == DEFAULT_KEY_ALIAS_PREFIXES
    assert resolved.tier == TIER_HEURISTIC
    assert resolved.stated == ()


def test_alias_prefixes_accumulate_exactly_as_their_siblings_do() -> None:
    """The inconsistency the migration closes, asserted against the control arm:
    the writers from the SAME generator already accumulated while the prefixes
    replaced.
    """
    writers, _readers, prefixes = resolve_shared_key_patterns(
        {KEY_ALIAS_FIELD: ["APP_KEY_"], "writers": [{"name_prefix": "App_Set_"}]}
    )
    surviving = {getattr(w, "prefix", None) for w in writers}
    assert {"App_Set_", "DataModel_Set_"} <= surviving, "writers accumulate — control arm"
    assert set(prefixes) == {"APP_KEY_", *DEFAULT_KEY_ALIAS_PREFIXES}


def test_an_explicit_manifest_file_outranks_a_declared_section(tmp_path: Path) -> None:
    """Tier 1 beats tier 2, and the split is read from the SOURCE TYPE —
    `cli._declared_or_flag` hands back a Path for `--shared-key-patterns` and the
    parsed mapping for a declaration, so no second argument has to be kept in sync.
    """
    manifest = tmp_path / "patterns.yaml"
    manifest.write_text(f"{KEY_ALIAS_FIELD}: ['FLAG_KEY_']\n", encoding="utf-8")

    resolved = resolve_key_alias_prefixes(manifest, {KEY_ALIAS_FIELD: ["DECL_KEY_"]})
    assert resolved.tier == TIER_EXPLICIT
    assert set(resolved.values) == {"FLAG_KEY_", "DECL_KEY_", *DEFAULT_KEY_ALIAS_PREFIXES}, (
        "tier 1 wins the TIER, but tier 2 is still a stated layer contributing values"
    )


def test_a_manifest_that_states_no_prefixes_does_not_claim_the_tier(tmp_path: Path) -> None:
    """A `--shared-key-patterns` file declaring only writers has stated NOTHING
    about alias prefixes, so recording `tier=explicit` would be a provenance record
    that is checkable and wrong — the failure `_scope_provenance` calls out.

    THE SECOND CASE IS THE ONE THAT BITES, and the first version of this test did
    not have it. With `extra=None` the two readings are indistinguishable: dropping
    the `bool(contributed)` guard makes `by_flag` true, but the statement is then
    the empty list, which `resolve_layered` treats as a WITHDRAWAL and falls through
    to the same answer. A mutation removing the guard passed. It takes a flag file
    that states nothing ALONGSIDE a declaration that states something to tell them
    apart — and there the wrong reading attributes the DECLARATION's prefixes to the
    flag.
    """
    manifest = tmp_path / "patterns.yaml"
    manifest.write_text("writers:\n  - name_prefix: 'App_Set_'\n", encoding="utf-8")

    alone = resolve_key_alias_prefixes(manifest)
    assert alone.values == DEFAULT_KEY_ALIAS_PREFIXES
    assert alone.tier == TIER_HEURISTIC

    beside_a_declaration = resolve_key_alias_prefixes(manifest, {KEY_ALIAS_FIELD: ["DECL_KEY_"]})
    assert beside_a_declaration.tier == TIER_DECLARED, (
        "the flag stated nothing about prefixes — the DECLARATION did"
    )
    assert set(beside_a_declaration.values) == {"DECL_KEY_", *DEFAULT_KEY_ALIAS_PREFIXES}


def test_the_stamped_alias_resolution_matches_the_one_the_pass_uses() -> None:
    """PINS THE DOUBLE RESOLUTION. `resolve_key_alias_prefixes` is called twice per
    build — once inside `import_shared_key_edges_inferred` and once in
    `_build_stages` to stamp the tier — because the value is computed several frames
    below the stamping stage. It is pure and both calls take the same two locals, so
    they cannot disagree; this asserts that rather than trusting it, and would fail
    the moment either call site starts resolving something else.
    """
    for sources in (
        (None, None),
        ({KEY_ALIAS_FIELD: ["APP_KEY_"]}, None),
        ({"writers": [{"name_prefix": "App_Set_"}]}, {KEY_ALIAS_FIELD: ["WRAP_KEY_"]}),
    ):
        via_pass = resolve_shared_key_patterns(*sources)[2]
        via_stamp = resolve_key_alias_prefixes(*sources).values
        assert via_pass == via_stamp, sources


def test_the_alias_tier_is_stamped_beside_the_entry_pattern_tier(tmp_path: Path) -> None:
    """Both layered options reach `build_meta` through the one producer that refuses
    values whose tier was discarded.
    """
    db = tmp_path / "clew.db"
    write_build_signature(
        db,
        options=options_meta(
            **{
                OPTION_ENTRY_PATTERNS: _entry_patterns(argparse.Namespace(entry_patterns=None), {}),
                OPTION_KEY_ALIAS_PREFIXES: resolve_key_alias_prefixes(
                    {KEY_ALIAS_FIELD: ["APP_KEY_"]}
                ),
            }
        ),
    )
    section = _options_meta_section(db)
    assert section[f"{OPTION_ENTRY_PATTERNS}.{TIER_KEY}"] == TIER_HEURISTIC
    assert section[f"{OPTION_KEY_ALIAS_PREFIXES}.{TIER_KEY}"] == TIER_DECLARED
    ## NOT REPLAYED, and this asserts the absence rather than assuming it. Only a
    ## tier-1 statement is recorded for replay, and a declaration re-derives from a
    ## file that may have changed — so the stale-row hazard `recorded_explicit`
    ## guards against cannot arise for a declared win in the first place.
    assert f"{OPTION_KEY_ALIAS_PREFIXES}.{EXPLICIT_KEY}" not in section
    assert recorded_explicit(section, OPTION_KEY_ALIAS_PREFIXES) == ()


# ── provenance: stamped, and read back rather than re-derived ───────────────


def test_options_meta_refuses_values_whose_tier_was_discarded() -> None:
    """THE "CANNOT FORGET" MECHANISM. There is no code path from a bare list to the
    `options.*` rows, so recording the tier is structural rather than a habit.
    """
    with pytest.raises(TypeError, match="LayeredResolution"):
        options_meta(entry_patterns=["main", "%init%"])  # type: ignore[arg-type]


def test_only_a_tier_one_statement_is_recorded_for_replay() -> None:
    """A declaration re-derives from a file that may have changed since, so
    replaying a stored copy would freeze a stale declaration.
    """
    explicit = resolve_layered(facts=FACTS, heuristics=GUESSES, explicit=["%mine%"])
    declared = resolve_layered(facts=FACTS, heuristics=GUESSES, declared=["%theirs%"])
    silent = resolve_layered(facts=FACTS, heuristics=GUESSES)

    assert options_meta(opt=explicit) == {
        f"opt.{TIER_KEY}": TIER_EXPLICIT,
        f"opt.{EXPLICIT_KEY}": "%mine%",
    }
    assert options_meta(opt=declared) == {f"opt.{TIER_KEY}": TIER_DECLARED}
    assert options_meta(opt=silent) == {f"opt.{TIER_KEY}": TIER_HEURISTIC}


def test_a_multi_value_statement_round_trips_through_the_stored_form() -> None:
    """The separator has to survive values containing commas and spaces, which a
    SQL LIKE pattern legitimately does.
    """
    stated = ["handle,%", "on %", "%weird%"]
    resolution = resolve_layered(facts=FACTS, heuristics=GUESSES, explicit=stated)
    # `options_meta` emits the section as `meta_section` hands it back: the
    # `options.` prefix is added by the writer and stripped by the reader, so what
    # `recorded_explicit` sees is exactly this mapping.
    assert recorded_explicit(options_meta(o=resolution), "o") == tuple(stated)


def test_recorded_explicit_is_empty_when_nothing_was_recorded() -> None:
    """An absent key means "nothing to replay", not an empty statement."""
    assert recorded_explicit({}, OPTION_ENTRY_PATTERNS) == ()
    assert recorded_explicit({f"{OPTION_ENTRY_PATTERNS}.{TIER_KEY}": TIER_HEURISTIC}, "x") == ()


def _stamp(db: Path, resolution: LayeredResolution) -> None:
    write_build_signature(db, options=options_meta(**{OPTION_ENTRY_PATTERNS: resolution}))


def _options_meta_section(db: Path) -> dict[str, str]:
    """The `options.*` rows with the section prefix stripped, as the reader sees them."""
    from clew.mcp_server.state import _options_meta

    return _options_meta(db)


def test_the_winning_tier_reaches_build_meta_and_is_read_back(tmp_path: Path) -> None:
    """PROVENANCE SURVIVES A REFRESH. Scope is re-derived from scratch on every
    build and nothing consulted what a previous build stamped, so an applied and
    recorded statement was discarded by the next refresh — which then reported
    success over a policy the operator had replaced. This is the same read-back
    `_operator_excludes` does, asserted end to end through the real writer.
    """
    db = tmp_path / "clew.db"
    resolution = _entry_patterns(argparse.Namespace(entry_patterns=["%mystyle%"]), {})
    _stamp(db, resolution)

    rows = dict(
        sqlite3.connect(str(db))
        .execute(f"SELECT key, value FROM build_meta WHERE key LIKE '{OPTIONS_META_PREFIX}.%'")
        .fetchall()
    )
    assert rows[f"{OPTIONS_META_PREFIX}.{OPTION_ENTRY_PATTERNS}.{TIER_KEY}"] == TIER_EXPLICIT
    assert rows[f"{OPTIONS_META_PREFIX}.{OPTION_ENTRY_PATTERNS}.{EXPLICIT_KEY}"] == "%mystyle%"

    # A later build passing NO flag inherits the recorded statement rather than
    # silently re-deriving the built-in guesses.
    inherited = _recorded_entry_patterns(argparse.Namespace(entry_patterns=None), db)
    assert inherited == ["%mystyle%"]
    assert list(_entry_patterns(argparse.Namespace(entry_patterns=inherited), {}).values) == [
        "main",
        "app_main",
        "%mystyle%",
    ]


def test_a_recorded_statement_can_be_withdrawn(tmp_path: Path) -> None:
    """Three states: absent inherits, EMPTY withdraws, non-empty replaces."""
    db = tmp_path / "clew.db"
    _stamp(db, _entry_patterns(argparse.Namespace(entry_patterns=["%mystyle%"]), {}))

    withdrawn = _recorded_entry_patterns(argparse.Namespace(entry_patterns=[]), db)
    assert withdrawn == []
    assert list(_entry_patterns(argparse.Namespace(entry_patterns=withdrawn), {}).values) == (
        DEFAULT_ENTRY_PATTERNS
    )

    replaced = _recorded_entry_patterns(argparse.Namespace(entry_patterns=["%other%"]), db)
    assert replaced == ["%other%"]


def test_a_declaration_is_not_replayed_from_the_record(tmp_path: Path) -> None:
    """The recorded row for a tier-2 win carries no statement, so a later build
    re-reads the declaration file rather than a frozen copy of it.
    """
    db = tmp_path / "clew.db"
    args = argparse.Namespace(entry_patterns=None)
    _stamp(db, _entry_patterns(args, {SECTION_ENTRY_PATTERNS: ["%trampoline%"]}))
    assert _recorded_entry_patterns(args, db) is None


def test_reading_provenance_off_an_older_index_is_empty_not_an_error(tmp_path: Path) -> None:
    """An index built before this section existed answers "not recorded"."""
    db = tmp_path / "clew.db"
    write_build_signature(db)
    assert _recorded_entry_patterns(argparse.Namespace(entry_patterns=None), db) is None


def test_status_reports_which_tier_chose_the_seeds(tmp_path: Path) -> None:
    """RECORDED IS NOT ENOUGH — it has to be REPORTED. A tiered resolution whose
    winner never reaches a consumer is the same opacity as an untiered one with
    more moving parts, so `status` carries the section beside scope and coverage.
    """
    from clew.mcp_server.state import _options_meta

    db = tmp_path / "clew.db"
    assert _options_meta(db) == {}, "a nonexistent index reports nothing, not a default"

    _stamp(db, _entry_patterns(argparse.Namespace(entry_patterns=["%mine%"]), {}))
    assert _options_meta(db) == {
        f"{OPTION_ENTRY_PATTERNS}.{TIER_KEY}": TIER_EXPLICIT,
        f"{OPTION_ENTRY_PATTERNS}.{EXPLICIT_KEY}": "%mine%",
    }

    _stamp(db, _entry_patterns(argparse.Namespace(entry_patterns=None), {}))
    assert _options_meta(db)[f"{OPTION_ENTRY_PATTERNS}.{TIER_KEY}"] == TIER_HEURISTIC


def test_a_withdrawn_statement_is_not_replayed_from_a_stale_row(tmp_path: Path) -> None:
    """FOUND BY WRITING THE CONTROL IN THE AWKWARD DIRECTION.

    `write_build_signature` upserts and never deletes, so stamping a withdrawal
    onto a database that already carries a statement leaves the retracted
    `<option>.explicit` row beside a fresh `<option>.tier = heuristic`. The first
    version of `recorded_explicit` read the statement key alone and replayed it —
    turning a retraction into a silent re-application.

    The real pipeline does not reach this (every build stamps a fresh temp database
    that then replaces the live one), which is exactly why it needs a test: the
    safety lives in a DIFFERENT module, and `_stamp_refresh_metrics` already stamps
    onto the live database for another section. The tier row is written on every
    stamp, so it is authoritative and a disagreeing statement replays nothing.
    """
    db = tmp_path / "clew.db"
    _stamp(db, _entry_patterns(argparse.Namespace(entry_patterns=["%mine%"]), {}))
    _stamp(db, _entry_patterns(argparse.Namespace(entry_patterns=None), {}))

    section = _options_meta_section(db)
    assert section[f"{OPTION_ENTRY_PATTERNS}.{EXPLICIT_KEY}"] == "%mine%", (
        "the stale row must still be present — otherwise this test proves nothing"
    )
    assert section[f"{OPTION_ENTRY_PATTERNS}.{TIER_KEY}"] == TIER_HEURISTIC
    assert recorded_explicit(section, OPTION_ENTRY_PATTERNS) == ()
    assert _recorded_entry_patterns(argparse.Namespace(entry_patterns=None), db) is None


# ── manifest statements: recorded, replayed, withdrawn (gh#364) ──────────────

## A shared-key manifest small enough to read and shaped like a real one: the
## argument-keyed convention on the writer, the name-embedded one on the reader.
STATED_MANIFEST: dict[str, object] = {
    "writers": [{"pattern": "Store_Set", "key_arg_index": 0}],
    "readers": [{"name_prefix": "Store_Get_"}],
}

## The same document with every mapping's keys in the OPPOSITE order. Equal as
## Python objects, different insertion order — which is what the canonical form has
## to erase.
STATED_MANIFEST_REORDERED: dict[str, object] = {
    "readers": [{"name_prefix": "Store_Get_"}],
    "writers": [{"key_arg_index": 0, "pattern": "Store_Set"}],
}

## Every manifest option unstated, which is what an MCP refresh passing no flags
## produces and therefore the case the replay exists for.
_UNSTATED = dict.fromkeys(MANIFEST_OPTIONS)


def _manifest_namespace(**stated: object) -> argparse.Namespace:
    """A namespace carrying all five manifest options, unstated unless named."""
    return argparse.Namespace(**{**_UNSTATED, **stated})


def _stamp_manifest(db: Path, option: str, resolution: DocumentResolution) -> None:
    """Stamp one manifest option's resolution through the real writer."""
    write_build_signature(db, options=options_meta(**{option: resolution}))


def test_the_manifest_option_names_are_the_declaration_section_names() -> None:
    """AN IDENTITY THE REPLAY DEPENDS ON, pinned rather than trusted.

    `_manifest_option_tiers` reads the target's declared document with
    `section(decl, option)` and `_replay_manifest_statements` reads the argparse dest
    with `getattr(args, option)`, so ONE string serves as the option name, the
    declaration section name and the flag's dest. That is the design
    (`buildoptions`: "THE VOCABULARY IS THE DECLARATION FILE'S"), but nothing enforced
    it — and a renamed section would leave the replay reading a declaration that is
    always empty, stamping `heuristic` over a repo that declares its own conventions.
    """
    assert set(MANIFEST_OPTIONS) == {
        SECTION_SHARED_KEY,
        SECTION_THREADS,
        SECTION_LOCKS,
        SECTION_DISPATCH,
        SECTION_MQTT,
    }
    assert set(MANIFEST_OPTIONS) <= KNOWN_SECTIONS


def test_a_manifest_statement_survives_a_later_build_that_states_nothing(
    tmp_path: Path,
) -> None:
    """THE DEFECT, at the unit level. gh#360 made a manifest statable inline and did
    not persist it, so the next build resolved the manifest from the target's own
    declaration and the stated layer vanished with the build reporting success —
    measured on this repo's self-index as a 1.7 s pass that reverted to the undeclared
    policy. gh#332 shipped the same hole for the path form.

    The build that discards it is usually the MCP server's, which passes no flags at
    all: `status` reports staleness and the guidance says refresh, so a cell's agent
    that brought the index up loses its own bringup work mid-cell and is never told.
    """
    db = tmp_path / "clew.db"
    _stamp_manifest(
        db, SECTION_SHARED_KEY, resolve_document(explicit=STATED_MANIFEST, declared=None)
    )

    args = _manifest_namespace()
    assert _replay_manifest_statements(args, db) == [SECTION_SHARED_KEY]
    assert args.shared_key_patterns == STATED_MANIFEST
    ## The other four are untouched — a replay must not invent a statement for an
    ## option nobody stated.
    assert args.locks is None
    assert args.thread_patterns is None


def test_a_stated_path_replays_as_a_path(tmp_path: Path) -> None:
    """BOTH INPUT FORMS ARE PERSISTED, because both had the hole (gh#332 shipped the
    path form). JSON tells them apart with no second key: a path is a string, a
    document is an object, so the reader cannot get the form wrong.
    """
    db = tmp_path / "clew.db"
    stated = str(tmp_path / "locks.yaml")
    _stamp_manifest(db, SECTION_LOCKS, resolve_document(explicit=stated))

    args = _manifest_namespace()
    assert _replay_manifest_statements(args, db) == [SECTION_LOCKS]
    assert args.locks == stated


def test_a_statement_made_on_this_call_is_not_overwritten_by_the_record(
    tmp_path: Path,
) -> None:
    """The three states, and this is the REPLACE one: what an operator says now wins
    over what they said before.
    """
    db = tmp_path / "clew.db"
    _stamp_manifest(db, SECTION_SHARED_KEY, resolve_document(explicit=STATED_MANIFEST))

    args = _manifest_namespace(shared_key_patterns={"writers": [{"pattern": "Now_Set"}]})
    assert _replay_manifest_statements(args, db) == []
    assert args.shared_key_patterns == {"writers": [{"pattern": "Now_Set"}]}


def test_an_empty_document_withdraws_the_record_rather_than_ignoring_it(
    tmp_path: Path,
) -> None:
    """`{}` DOES BOTH JOBS WITH ONE SPELLING (owner decision, gh#364): it stops
    overriding this run AND removes the record, because those are one intent.

    THE ASSERTION THAT MATTERS IS THAT THE RECORD IS GONE, not that this run ignored
    it. A withdrawal that silently fails to withdraw is the `key_arg_idx`-for
    -`key_arg_index` class of defect — a valid mapping no consumer reads — so this
    checks the row a NEXT build would read, not the absence of an error.
    """
    db = tmp_path / "clew.db"
    _stamp_manifest(db, SECTION_SHARED_KEY, resolve_document(explicit=STATED_MANIFEST))

    args = _manifest_namespace(shared_key_patterns={})
    assert _replay_manifest_statements(args, db) == [], "an empty document states nothing"
    assert args.shared_key_patterns == {}

    ## What THIS build would stamp for the withdrawn option: a tier, and no statement.
    ## Every build writes a fresh `build_meta` into the temp database that replaces the
    ## live one, so an absent statement here IS the record being gone.
    withdrawn = _manifest_option_tiers(args, {})[SECTION_SHARED_KEY]
    assert withdrawn.tier == TIER_HEURISTIC
    assert withdrawn.as_meta(SECTION_SHARED_KEY) == {
        f"{SECTION_SHARED_KEY}.{TIER_KEY}": TIER_HEURISTIC
    }
    fresh = tmp_path / "next.db"
    _stamp_manifest(fresh, SECTION_SHARED_KEY, withdrawn)
    assert recorded_document(_options_meta_section(fresh), SECTION_SHARED_KEY) is None
    assert _replay_manifest_statements(_manifest_namespace(), fresh) == []


def test_a_withdrawn_manifest_statement_is_not_replayed_from_a_stale_row(
    tmp_path: Path,
) -> None:
    """THE TIER CROSS-CHECK, CONFIRMED FOR THE DOCUMENT FORM RATHER THAN ASSUMED.

    The guard lives in the READER, so a second reader that skipped it would replay a
    withdrawn statement while `recorded_explicit` refused to — and the task asked for
    this to be confirmed, not inherited. `write_build_signature` upserts and never
    deletes, so stamping a withdrawal onto a database that already carries a statement
    leaves the retracted `<option>.explicit` row beside a fresh
    `<option>.tier = heuristic`.
    """
    db = tmp_path / "clew.db"
    _stamp_manifest(db, SECTION_SHARED_KEY, resolve_document(explicit=STATED_MANIFEST))
    _stamp_manifest(db, SECTION_SHARED_KEY, resolve_document())

    section = _options_meta_section(db)
    assert section[f"{SECTION_SHARED_KEY}.{EXPLICIT_KEY}"] == canonical_document(STATED_MANIFEST), (
        "the stale row must still be present — otherwise this test proves nothing"
    )
    assert section[f"{SECTION_SHARED_KEY}.{TIER_KEY}"] == TIER_HEURISTIC
    assert recorded_document(section, SECTION_SHARED_KEY) is None
    assert _replay_manifest_statements(_manifest_namespace(), db) == []


def test_a_declared_manifest_is_not_replayed_from_the_record(tmp_path: Path) -> None:
    """A tier-2 declaration re-derives from a file that may have changed since, so no
    statement is recorded for it and a later build re-reads the declaration rather
    than a frozen copy.
    """
    db = tmp_path / "clew.db"
    resolution = resolve_document(explicit=None, declared=STATED_MANIFEST)
    assert resolution.tier == TIER_DECLARED
    _stamp_manifest(db, SECTION_SHARED_KEY, resolution)

    section = _options_meta_section(db)
    assert f"{SECTION_SHARED_KEY}.{EXPLICIT_KEY}" not in section
    assert recorded_document(section, SECTION_SHARED_KEY) is None


def test_the_stored_document_is_byte_STABLE_across_key_orderings() -> None:
    """WHAT PINS THE CANONICAL FORM. `test_warm_rebuild_is_deterministic` compares two
    real builds' `build_meta` VERBATIM, so a serialisation that preserved insertion
    order would make the stored row a function of how the caller spelled its mapping —
    an intermittent failure there rather than a useful one.
    """
    assert canonical_document(STATED_MANIFEST) == canonical_document(STATED_MANIFEST_REORDERED)
    assert " " not in canonical_document(STATED_MANIFEST)
    assert (
        recorded_document(options_meta(o=resolve_document(explicit=STATED_MANIFEST_REORDERED)), "o")
        == STATED_MANIFEST
    )


def test_a_corrupt_record_refuses_rather_than_reverting_silently() -> None:
    """FAIL CLOSED. Reverting to the target's declaration because the record could not
    be read is the exact defect the read-back exists to remove: the build would report
    success over a policy nobody chose. Nothing but `tiers` writes this row, so
    reaching here means the database was hand-edited.
    """
    ## Both halves of the refusal: JSON that will not parse, and JSON that parses to a
    ## shape no manifest loader can read. The second is the quieter one — it would
    ## otherwise fail several frames away, in a parser whose message names a shape
    ## rather than a corrupt record.
    for raw in ("{not json", "[1,2]"):
        section = {f"o.{TIER_KEY}": TIER_EXPLICIT, f"o.{EXPLICIT_KEY}": raw}
        with pytest.raises(ValueError, match="'o'"):
            recorded_document(section, "o")


def test_options_meta_refuses_a_bare_manifest_mapping() -> None:
    """The refusal that makes recording the tier structural has to cover the document
    form too — a bare manifest mapping is exactly what a caller would reach for.
    """
    with pytest.raises(TypeError, match="DocumentResolution"):
        options_meta(**{SECTION_SHARED_KEY: STATED_MANIFEST})  # type: ignore[arg-type]


def test_status_names_the_options_an_operator_stated(tmp_path: Path) -> None:
    """THE VISIBLE STAMP — the owner's condition for allowing the replay at all. A
    replayed statement means the index carries a policy the repository does not
    declare, so two operators of one commit can hold different indexes; that is the
    shape of the defect rejected in gh#352 and it is acceptable only because it is
    deliberate AND visible. They may differ; never silently.
    """
    from clew.mcp_server.state import _options_meta

    db = tmp_path / "clew.db"
    write_build_signature(
        db,
        options=options_meta(
            **{
                OPTION_ENTRY_PATTERNS: _entry_patterns(argparse.Namespace(entry_patterns=None), {}),
                SECTION_SHARED_KEY: resolve_document(explicit=STATED_MANIFEST),
                SECTION_LOCKS: resolve_document(declared=STATED_MANIFEST),
            }
        ),
    )
    assert stated_options(_options_meta(db)) == (SECTION_SHARED_KEY,), (
        "only a tier-1 win is a STATEMENT — a declaration is the repository's own, and "
        "the built-in floor is nobody's"
    )


def test_nothing_is_stated_and_nothing_replays_for_a_target_that_states_nothing(
    tmp_path: Path,
) -> None:
    """THE SUCCESS PATH, and the control for "entropic and mbedtls are unchanged". A
    target that states nothing must record nothing and replay nothing — asserted
    strictly (an exact section) rather than by absence of a single key, because this
    repo has shipped a check that tested only its failure path.
    """
    db = tmp_path / "clew.db"
    args = _manifest_namespace()
    write_build_signature(db, options=options_meta(**_manifest_option_tiers(args, {})))

    assert _options_meta_section(db) == {
        f"{option}.{TIER_KEY}": TIER_HEURISTIC for option in MANIFEST_OPTIONS
    }
    assert stated_options(_options_meta_section(db)) == ()
    assert _replay_manifest_statements(_manifest_namespace(), db) == []
