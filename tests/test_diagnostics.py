# SPDX-License-Identifier: MIT
"""A STRUCTURED ZERO IS EVIDENCE — gh#320.

The load-bearing test here is `test_a_clean_target_still_reports_its_zeros`. Every other
test proves the diagnostics appear when there is something to say; that one proves they
appear when there is NOT, which is the case the whole change exists for. This project has
read a silent zero as a fact about a repository three times, so the zero is the feature and
the named list is the garnish.

`test_the_stamped_prefix_round_trips` is the other one worth keeping. Three modules spell
the section name — the flatten, the writer and the reader — and only two of them import a
constant. A test that writes through one and reads through another fails on a divergence at
either end, which a shared constant would not do for the two literals.

@brief Tests for the build's discovery diagnostics and their persistence.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew import diagnostics as dg
from clew.query._common import meta_section
from clew.shared_key_edges import AccessorFamily
from clew.vocabulary import EXTERNAL_ROOT_COLUMN
from clew.signature import write_build_signature

## An ALIASES line in the shape doxygen actually takes, with one tag the built-in
## vocabulary claims (`emits`) and two it does not (`broadcasts`, `req`).
ALIASES_TEXT = (
    'ALIASES = "emits=@xrefitem evt_emits \\"Emits\\" \\"Events\\"" \\\n'
    '          "broadcasts=@xrefitem bus_bcast \\"Broadcasts\\" \\"Events\\"" \\\n'
    '          "req=@xrefitem reqs \\"Requirement\\" \\"Requirements\\""\n'
)


## @brief A database carrying a memberdef corpus of the given (kind, name) rows.
## @param path Where to create it.
## @param rows (kind, name) pairs to insert.
## @return The path, for chaining.
## @version 1
def _corpus(path: Path, rows: list[tuple[str, str]]) -> Path:
    """Built by hand rather than by running the pipeline, so a test states exactly which
    corpus it measures. The `kind` values are doxygen's own literals — a fixture using any
    other spelling would prove only that it agrees with the code.

    @brief Create a minimal memberdef corpus.
    @return The database path.
    @version 1
    """
    conn = sqlite3.connect(str(path))
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT)")
    conn.executemany(
        "INSERT INTO memberdef (kind, name) VALUES (?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return path


## @brief A corpus whose rows are attributed to files, some of them vendored.
## @param path Where to create it.
## @param rows (kind, name, file rowid) triples.
## @param files (rowid, name, external_root or None) file rows.
## @return The path, for chaining.
## @version 1
def _attributed_corpus(
    path: Path,
    rows: list[tuple[str, str, int]],
    files: list[tuple[int, str, str | None]],
) -> Path:
    """A SEPARATE BUILDER FROM `_corpus`, ON PURPOSE. `_corpus` has no `path` table at all,
    which is a real index shape — every build before gh#335 — and it exercises the fallback
    where the detector reports everything as first party. Adding the column to `_corpus`
    instead would have deleted that coverage while looking like an improvement.

    @brief Create a memberdef corpus with per-file external tags.
    @return The database path.
    @version 1
    """
    conn = sqlite3.connect(str(path))
    conn.executescript(
        f"""
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER
        );
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, {EXTERNAL_ROOT_COLUMN} TEXT);
        """
    )
    conn.executemany(
        f"INSERT INTO path (rowid, name, {EXTERNAL_ROOT_COLUMN}) VALUES (?, ?, ?)", files
    )
    conn.executemany(
        "INSERT INTO memberdef (kind, name, file_id, bodyfile_id) VALUES (?, ?, ?, ?)",
        [(kind, name, file_id, file_id) for kind, name, file_id in rows],
    )
    conn.commit()
    conn.close()
    return path


## @brief A vendored accessor family is COUNTED but not NAMED as actionable.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_vendored_accessor_family_is_counted_but_not_named(tmp_path: Path) -> None:
    """WHY THIS SPLIT EXISTS, measured rather than argued. Probing this detector against both
    public targets: [tvanfossen/entropic](https://github.com/tvanfossen/entropic) examines
    17,773 distinct names and names NINE families, ALL NINE vendored inside `extern/llama.cpp`
    (`ma_*` from miniaudio, `ggml_set_*`); Mbed-TLS/mbedtls examines 5,967 and names TWO, both
    DES key-schedule setters. Eleven families across two repos, and an operator should declare
    NONE of them.

    A hint whose entries are unactionable teaches its reader to skip the hint, which is the
    same defect as `lock_roster` telling a caller to quote a count that is 57% another
    repository's — and this one costs an operator time before they discover it yielded nothing.

    THE EXTERNAL FAMILIES ARE STILL COUNTED. Dropping them would make "found nothing"
    indistinguishable from "found nine things in somebody else's code", and those call for
    different next steps. So `accessor_families_count` stays the total, and an EMPTY name list
    beside a non-zero count is the honest reading of entropic.

    @brief A vendored family is counted in the total and absent from the named list.
    @version 1
    """
    db = _attributed_corpus(
        tmp_path / "clew.db",
        [("macro definition", f"ggml_set_{key}", 2) for key in ("A", "B", "C", "D", "E")]
        + [("function", f"Store_Set_{key}", 1) for key in ("A", "B", "C", "D")],
        [(1, "src/store.c", None), (2, "extern/llama.cpp/ggml/src/ggml.c", "extern/llama.cpp")],
    )

    meta = dg.collect(db, tmp_path / "absent.Doxyfile", None, None, None).as_meta()

    assert meta["accessor_families_count"] == "2", "both families are found"
    assert meta["accessor_families_first_party_count"] == "1"
    assert meta["accessor_families_external_count"] == "1"
    ## The three counts reconcile, which is the gh#352 contract.
    assert int(meta["accessor_families_first_party_count"]) + int(
        meta["accessor_families_external_count"]
    ) == int(meta["accessor_families_count"])
    assert "Store_Set_*" in meta["accessor_families"], "the actionable family is named"
    assert "ggml_set_" not in meta["accessor_families"], (
        "a vendored family is not the operator's to declare, so naming it beside the one they "
        "can act on is what trains a reader to ignore the whole hint"
    )


## @brief A family with functions on BOTH sides is first party, not external.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_family_spanning_both_sides_is_first_party(tmp_path: Path) -> None:
    """THE STATED RULE FOR AN EXPRESSIBLE AMBIGUITY. A prefix can collect functions from both
    a repo and its submodule, and then the classification could silently pick either side.
    Fail-closed here means OURS — the same asymmetry `scope._is_dependency_of_parent` and
    `locks._origin_per_mutex` argue: if any part of the family is this repo's, declaring a
    prefix IS an action the operator can take, and calling it external would remove it from the
    list they act on.

    @brief A mixed-origin family is named as actionable.
    @version 1
    """
    db = _attributed_corpus(
        tmp_path / "clew.db",
        [("function", f"Store_Set_{key}", 1) for key in ("A", "B")]
        + [("function", f"Store_Set_{key}", 2) for key in ("C", "D")],
        [(1, "src/store.c", None), (2, "extern/dep/store_extra.c", "extern/dep")],
    )

    meta = dg.collect(db, tmp_path / "absent.Doxyfile", None, None, None).as_meta()

    assert meta["accessor_families_first_party_count"] == "1"
    assert meta["accessor_families_external_count"] == "0"
    assert "Store_Set_* (4 keys)" in meta["accessor_families"], (
        "all four keys count toward the family; only its ORIGIN is at issue"
    )


# ─── the control: nothing to report is still a report ─────────────────────────


## @brief A target with no undeclared families and no stray aliases reports zeros, not silence.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_clean_target_still_reports_its_zeros(tmp_path: Path) -> None:
    """THE LOAD-BEARING TEST. A silent zero is indistinguishable from a diagnostic that
    never ran, from an index built before the diagnostic existed, and from a detector that
    is structurally blind to the target — and this repo has made the third mistake and
    written it down as a correct negative, on a target whose real accessors were macros
    with 1,093 call sites and no `kind='function'` rows.

    So both counts must be PRESENT and `"0"`, and the corpus size must be present and
    non-zero: "searched N names, matched none" is a measurement, while an absent key is not.

    @brief Zero is reported, with the corpus it was measured over.
    @version 1
    """
    db = _corpus(tmp_path / "clew.db", [("function", "run"), ("function", "main")])

    meta = dg.collect(db, tmp_path / "absent.Doxyfile", None, None, None).as_meta()

    assert meta["accessor_families_count"] == "0"
    assert meta["unclaimed_event_aliases_count"] == "0"
    assert meta["accessor_names_examined"] == "2", "a zero needs the corpus it was measured over"
    assert meta["event_vocabulary_source"] == dg.SOURCE_BUILT_IN


## @brief An undeclared MACRO accessor family is named, with its key count.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_macro_accessor_family_is_named_in_the_payload(tmp_path: Path) -> None:
    """Macros only, deliberately: the case the diagnostic exists for is a repo whose
    accessors produce ZERO function rows, so a fixture with a function in it would pass
    against a functions-only corpus and prove nothing.

    @brief A macro-defined family reaches the payload by name.
    @version 1
    """
    db = _corpus(
        tmp_path / "clew.db",
        [("macro definition", f"Store_Set_{key}") for key in ("A", "B", "C", "D", "E")],
    )

    result = dg.collect(db, tmp_path / "absent.Doxyfile", None, None, None)
    meta = result.as_meta()

    assert (result.accessor_families[0].prefix, result.accessor_families[0].keys) == (
        "Store_Set_",
        5,
    )
    assert "Store_Set_* (5 keys)" in meta["accessor_families"]
    assert meta["accessor_families_count"] == "1"
    assert meta["accessor_names_examined"] == "5"
    ## The fixture's `path` table carries no external tag, so the family is FIRST PARTY and the
    ## three counts reconcile — which is the gh#352 contract at this surface.
    assert meta["accessor_families_first_party_count"] == "1"
    assert meta["accessor_families_external_count"] == "0"


## @brief Aliased tags no vocabulary claims are named; a claimed one is not.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_unclaimed_aliases_are_named_and_claimed_ones_are_not(tmp_path: Path) -> None:
    """BOTH HALVES, because a diagnostic that lists every alias would be noise and one that
    lists none would be the silence being fixed. `emits` is a built-in producer verb and
    must NOT appear; `broadcasts` and `req` are unclaimed and must.

    `req` appearing is deliberate rather than sloppy — nothing in an ALIASES line marks a
    tag as belonging to an event bus, so filtering would mean guessing, and guessing wrong
    hides exactly the tag an owner needed to see.

    @brief Unclaimed aliases are surfaced; claimed ones are excluded.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(ALIASES_TEXT, encoding="utf-8")
    db = _corpus(tmp_path / "clew.db", [("function", "run")])

    result = dg.collect(db, doxyfile, None, None, None)

    assert set(result.unclaimed_aliases) == {"broadcasts", "req"}
    assert "emits" not in result.unclaimed_aliases, "a claimed verb is not a finding"
    assert result.as_meta()["unclaimed_event_aliases_count"] == "2"


## @brief A declared vocabulary is reported as declared, and changes what counts as unclaimed.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_declared_vocabulary_is_reported_and_reclassifies(tmp_path: Path) -> None:
    """The loop gh#332 closes: an operator declares `event_tags`, and the reply has to say
    whether the declaration ARRIVED. A count alone cannot — it moves for several reasons.

    Declaring `broadcasts` must both claim it and UNCLAIM `emits`, because a declared
    vocabulary REPLACES the built-in verbs rather than extending them. Asserting only the
    first half would pass against an extend-semantics implementation.

    @brief A declaration is reported as the source and replaces the defaults.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(ALIASES_TEXT, encoding="utf-8")
    db = _corpus(tmp_path / "clew.db", [("function", "run")])

    result = dg.collect(db, doxyfile, None, None, {"broadcasts": "producer"})
    meta = result.as_meta()

    assert meta["event_vocabulary_source"] == dg.SOURCE_DECLARED
    assert meta["event_vocabulary_size"] == "1"
    assert "broadcasts" not in result.unclaimed_aliases, "the declared verb is claimed"
    assert "emits" in result.unclaimed_aliases, "a declaration REPLACES the built-in verbs"


## @brief The named list is capped while the count stays exact.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_capped_list_still_reports_the_true_count(tmp_path: Path) -> None:
    """A cap that cannot be seen is how a bounded answer comes to read as a complete one.
    The count is the claim and stays exact, so `count > len(named)` makes the truncation
    visible without a second field.

    @brief Truncation is visible through the exact count.
    @version 1
    """
    rows = [
        ("function", f"Fam{fam}_Set_{key}")
        for fam in range(dg.MAX_NAMED + 3)
        for key in ("A", "B", "C", "D")
    ]
    db = _corpus(tmp_path / "clew.db", rows)

    meta = dg.collect(db, tmp_path / "absent.Doxyfile", None, None, None).as_meta()

    assert meta["accessor_families_count"] == str(dg.MAX_NAMED + 3)
    assert meta["accessor_families"].count("keys)") == dg.MAX_NAMED


## @brief A declared pattern covering a family removes it from the diagnostic.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_covered_family_is_not_reported(tmp_path: Path) -> None:
    """The diagnostic names what is NOT covered, so declaring the prefix must silence it.
    Without this the payload would be a list of every accessor family in the repo, which
    would say nothing about what is missing — and would keep saying it after an operator
    fixed the thing it complained about.

    @brief Declaring the prefix silences the finding.
    @version 1
    """
    from clew.shared_key_edges import NamePrefixPattern

    db = _corpus(
        tmp_path / "clew.db",
        [("macro definition", f"Store_Set_{key}") for key in ("A", "B", "C", "D", "E")],
    )
    covering = NamePrefixPattern("Store_Set_")

    bare = dg.collect(db, tmp_path / "absent.Doxyfile", None, None, None)
    assert bare.as_meta()["accessor_families_count"] == "1", "control: undeclared, so reported"

    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        from clew.shared_key_edges import detect_undeclared_accessor_families

        assert detect_undeclared_accessor_families(conn, [covering]) == []
    finally:
        conn.close()


# ─── persistence ─────────────────────────────────────────────────────────────


## @brief The section survives a write/read round trip under the same prefix.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_the_stamped_prefix_round_trips(tmp_path: Path) -> None:
    """THREE MODULES SPELL THIS SECTION NAME and only one imports the constant: the
    flatten (`diagnostics.META_PREFIX`), the writer (`signature`, a literal) and the reader
    (`mcp_server.state`, a literal). A shared constant would not have caught a divergence
    in the two literals; writing through one and reading through the other does.

    @brief The diagnostics section persists and reads back.
    @version 1
    """
    db = tmp_path / "clew.db"
    payload = dg.BuildDiagnostics(
        accessor_families=(AccessorFamily(prefix="Store_Set_", keys=5),),
        accessor_names_examined=3784,
        unclaimed_aliases=("broadcasts",),
    )

    write_build_signature(db, diagnostics=payload.as_meta())
    read = meta_section(db, dg.META_PREFIX)

    assert read["accessor_families_count"] == "1"
    assert read["accessor_names_examined"] == "3784"
    assert read["unclaimed_event_aliases"] == "broadcasts"


## @brief A zero count survives persistence, where a falsy value would be dropped.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_zero_count_survives_the_falsy_drop(tmp_path: Path) -> None:
    """`write_build_signature` DROPS falsy values, so an int `0` would vanish and rebuild
    the silent zero one layer down — in the persistence rather than in the detector. The
    flatten emits `"0"`, which is truthy, and this is the test that says so.

    Its control is the empty NAMED list in the same payload, which is SUPPOSED to be
    dropped: the count is the claim and must always be present, the names are evidence and
    may be absent.

    @brief A measured zero persists; an empty name list does not have to.
    @version 1
    """
    db = tmp_path / "clew.db"

    write_build_signature(db, diagnostics=dg.BuildDiagnostics().as_meta())
    read = meta_section(db, dg.META_PREFIX)

    assert read["accessor_families_count"] == "0", "the zero IS the measurement"
    assert read["unclaimed_event_aliases_count"] == "0"
    assert "accessor_families" not in read, "an empty name list carries no claim"


# ─── the wiring, against a real build ─────────────────────────────────────────


@pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="the stamp is asserted against a real build",
)
## @brief A real build stamps the section, naming a family doxygen itself emitted.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_real_build_stamps_the_diagnostics_section(tmp_path: Path) -> None:
    """THE TEST THAT COVERS THE WIRING, and without it the whole feature is green for the
    wrong reason: every test above calls `collect` or `write_build_signature` directly, so
    deleting the `diagnostics=` argument from `cli`'s stamp leaves them all passing while
    no built index carries the section. Mutation-checked, not assumed.

    It asserts a family is NAMED rather than that a zero appears, so it also proves the
    detector works on real doxygen output — a hand-built corpus only ever proves the
    fixture agrees with the code.

    @brief A real build records the diagnostics, detected from doxygen's own rows.
    @version 1
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "store.c").write_text(
        "".join(
            f"/** @brief Set {key}. */\nvoid Store_Set_{key}(int v) {{ (void)v; }}\n"
            for key in ("ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON")
        ),
        encoding="utf-8",
    )
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(
        f"INPUT = {root}\nOUTPUT_DIRECTORY = {root}/out\nRECURSIVE = YES\nGENERATE_SQLITE3 = YES\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"

    from clew.cli import build_index

    build_index(output=out, repo_root=root, doxyfile=doxyfile)

    section = meta_section(out, dg.META_PREFIX)
    assert section, "a built index must carry the section, not merely be able to"
    assert section["accessor_families_count"] == "1"
    assert "Store_Set_* (5 keys)" in section["accessor_families"]
    assert int(section["accessor_names_examined"]) >= 5
    assert section["event_vocabulary_source"] == dg.SOURCE_BUILT_IN


@pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="precedence is asserted against a real build",
)
## @brief A STATED vocabulary beats the repo's DECLARED one, through a real build.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_stated_vocabulary_beats_the_repos_declaration(tmp_path: Path) -> None:
    """gh#332's PRECEDENCE, and it needs a real build because the `or` chain that
    implements it lives one line deep inside `_build_stages`. A mutation control found this
    untested: swapping the two sides — so the declaration beats the statement — left the
    entire suite green, which is tier 1 reachable and INERT, the exact shape gh#332 exists
    to fix reintroduced one line lower.

    The observable is the gh#320 diagnostics, which is why the two changes belong together:
    `event_vocabulary_source` and `_size` report WHICH vocabulary was in force, so the
    precedence is checkable from the payload rather than by inspection. The declaration
    carries TWO entries and the statement ONE, so the size alone discriminates.

    @brief A caller's stated event vocabulary wins over the declared one.
    @version 1
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "unit.c").write_text("/** @brief A unit. */\nvoid unit(void) {}\n", encoding="utf-8")
    (root / ".clew.yaml").write_text(
        "event_tags:\n  emits: producer\n  handles: consumer\n", encoding="utf-8"
    )
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(
        f"INPUT = {root}\nOUTPUT_DIRECTORY = {root}/out\nRECURSIVE = YES\nGENERATE_SQLITE3 = YES\n",
        encoding="utf-8",
    )

    from clew.cli import build_index

    declared_only = tmp_path / "declared.db"
    build_index(output=declared_only, repo_root=root, doxyfile=doxyfile)
    baseline = meta_section(declared_only, dg.META_PREFIX)
    assert baseline["event_vocabulary_size"] == "2", "premise: the declaration is read"
    assert baseline["event_vocabulary_source"] == dg.SOURCE_DECLARED

    stated = tmp_path / "stated.db"
    build_index(
        output=stated,
        repo_root=root,
        doxyfile=doxyfile,
        options={"event_tags": {"broadcasts": "producer"}},
    )
    section = meta_section(stated, dg.META_PREFIX)

    assert section["event_vocabulary_size"] == "1", "a stated vocabulary REPLACES the declared one"
    ## KNOWN COARSENESS, asserted so it is visible rather than discovered. `source` says
    ## only "not the built-in verbs" — it does NOT separate a STATED vocabulary (tier 1)
    ## from a DECLARED one (tier 2), so both read `declared` and the SIZE is what
    ## discriminates above. Reporting the tier properly means an `options.event_tags.tier`
    ## row, which `options_meta` will only accept from a LayeredResolution.
    assert section["event_vocabulary_source"] == dg.SOURCE_DECLARED
