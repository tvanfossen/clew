# SPDX-License-Identifier: MIT
"""A tier-1 manifest statement survives a real rebuild — measured in EDGE ROWS (gh#364).

WHY THIS IS AN INTEGRATION TEST AND NOT A UNIT ONE. The unit tests in
`tests/test_tiers.py` prove the record round-trips: stamped, read back, withdrawn. They
cannot prove the thing that was actually broken, which is that a LAYER survives — the
defect was measured as a pass that returned in 1.7 s having reverted to the undeclared
policy while reporting success, and every metadata assertion in that scenario was
perfectly healthy. So the controls here count `shared_key_edges` ROWS across four real
builds of a real C tree, exactly as the task required: verified by a layer row count,
never by metadata.

The target is written here rather than taken from a pinned clone because the property
under test needs a repository whose accessors NO built-in pattern claims. `Store_Set_` /
`Store_Get_` are matched only by the manifest this test states, so the undeclared
baseline is a measured ZERO and the stated build's rows can only have come from the
statement. A repo with ingot-shaped accessors would produce edges either way and the
control would prove nothing.

@brief Integration controls for manifest-statement persistence and replay.
@version 2
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.cli import build_index
from clew.declaration import SECTION_SHARED_KEY
from clew.mcp_server.state import _options_meta
from clew.scope import SOURCE_WHOLE_REPO
from clew.tiers import (
    EXPLICIT_KEY,
    TIER_EXPLICIT,
    TIER_HEURISTIC,
    TIER_KEY,
    recorded_document,
    stated_options,
)

pytestmark = pytest.mark.integration

## The accessor family. Deliberately NOT ingot-shaped (`DataModel_Set_`/`Get_`): no
## built-in pattern claims these names, so the undeclared build measures a real zero.
WRITER = "Store_Set_POWER"
READER = "Store_Get_POWER"

## The stated manifest. The name-embedded convention on both sides, so no argument
## index has to be right for the control to mean something.
MANIFEST: dict[str, object] = {
    "writers": [{"name_prefix": "Store_Set_"}],
    "readers": [{"name_prefix": "Store_Get_"}],
}

## One writer and one reader of one key, each in its own documented function so the
## inferred pass has a caller to attribute the access to.
SOURCE = f"""/** @file
 *  @brief Shared-key fixture for the manifest replay controls.
 */
#include <stdint.h>

static int32_t g_power_mv;

/** @brief Store the power reading.
 *  @version 1
 */
void {WRITER}(int32_t value) {{ g_power_mv = value; }}

/** @brief Read the power reading.
 *  @version 1
 */
int32_t {READER}(void) {{ return g_power_mv; }}

/** @brief Produce a power reading.
 *  @version 1
 */
void producer_task(void) {{ {WRITER}(4200); }}

/** @brief Consume the power reading.
 *  @version 1
 */
int32_t consumer_task(void) {{ return {READER}(); }}
"""

## Minimal Doxyfile. The pipeline force-appends everything it needs; a target only has
## to say where its sources are.
DOXYFILE = (
    "PROJECT_NAME     = manifest_replay_fixture\n"
    "INPUT            = src\n"
    "RECURSIVE        = YES\n"
    "GENERATE_HTML    = NO\n"
    "GENERATE_LATEX   = NO\n"
    "EXTRACT_STATIC   = YES\n"
    "QUIET            = YES\n"
)


## @brief Write the throwaway C target this module indexes.
## @param root Directory to populate.
## @return Path to the Doxyfile driving the build.
## @version 1
def _write_target(root: Path) -> Path:
    """@brief Create the fixture repository.
    @return The Doxyfile path.
    @version 1
    """
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "store.c").write_text(SOURCE, encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(DOXYFILE, encoding="utf-8")
    return doxyfile


## @brief Count the causal layer the stated manifest is responsible for.
## @param db Built database.
## @return Number of `shared_key_edges` rows.
## @version 1
def _shared_key_rows(db: Path) -> int:
    """THE MEASUREMENT THE CONTROLS TURN ON. Rows, not metadata: the defect this closes
    left every metadata field healthy and silently emptied the layer.

    @brief Count shared-key edges.
    @return The row count.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return int(conn.execute("SELECT COUNT(*) FROM shared_key_edges").fetchone()[0])
    finally:
        conn.close()


def test_a_stated_manifest_survives_a_rebuild_and_a_withdrawal_undoes_it(
    tmp_path: Path,
) -> None:
    """FOUR REAL BUILDS, ONE OUTPUT PATH, counted in edge rows.

      1. state nothing          -> the undeclared baseline (expected 0 here)
      2. state the manifest     -> the layer appears
      3. state nothing AGAIN    -> the layer SURVIVES (this is the fix)
      4. withdraw with `{}`     -> the layer returns to the baseline, record gone

    Build 3 is the whole point and it is the one that used to fail: nothing recorded
    the statement, so the rebuild re-resolved the manifest from the target's own
    declaration — which this fixture does not have — and the layer went back to zero
    with the build reporting success. It is also the normal case rather than a corner:
    `status` reports staleness and the guidance says refresh, so an agent that brings
    the index up then rebuilds would lose its own bringup work and never be told.

    ONE OUTPUT PATH throughout, deliberately. The record lives in the database being
    replaced, so a fresh path per build would test nothing — and the replay reads the
    live path BEFORE the atomic swap for exactly that reason.
    """
    root = tmp_path / "target"
    doxyfile = _write_target(root)
    db = tmp_path / "clew.db"

    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    baseline = _shared_key_rows(db)
    assert stated_options(_options_meta(db)) == (), "nothing was stated, so nothing is stamped"

    build_index(
        output=db, repo_root=root, doxyfile=doxyfile, options={SECTION_SHARED_KEY: MANIFEST}
    )
    stated = _shared_key_rows(db)
    assert stated > baseline, (
        f"the stated manifest produced no edges ({stated} vs baseline {baseline}) — the "
        f"control cannot distinguish a lost statement from a fixture that never worked"
    )
    assert stated_options(_options_meta(db)) == (SECTION_SHARED_KEY,)

    ## THE FIX. No options at all, which is what an MCP refresh passes.
    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    assert _shared_key_rows(db) == stated, (
        "the rebuild lost the stated layer — this is gh#364 exactly: the build reports "
        "success and the causal layer silently reverts to the undeclared policy"
    )
    replayed = _options_meta(db)
    assert replayed[f"{SECTION_SHARED_KEY}.{TIER_KEY}"] == TIER_EXPLICIT
    assert recorded_document(replayed, SECTION_SHARED_KEY) == MANIFEST
    assert stated_options(replayed) == (SECTION_SHARED_KEY,), (
        "a replayed statement makes this index carry a policy the repository does not "
        "declare — allowed only because it is visible"
    )

    ## THE WITHDRAWAL, proven by the row count returning to the baseline and by the
    ## record being ABSENT rather than merely ignored on this run.
    build_index(output=db, repo_root=root, doxyfile=doxyfile, options={SECTION_SHARED_KEY: {}})
    assert _shared_key_rows(db) == baseline
    withdrawn = _options_meta(db)
    assert withdrawn[f"{SECTION_SHARED_KEY}.{TIER_KEY}"] == TIER_HEURISTIC
    assert f"{SECTION_SHARED_KEY}.{EXPLICIT_KEY}" not in withdrawn, (
        "the record must be GONE, not ignored: a withdrawal that silently fails to "
        "withdraw is the key_arg_idx-for-key_arg_index class of defect"
    )
    assert recorded_document(withdrawn, SECTION_SHARED_KEY) is None
    assert stated_options(withdrawn) == ()

    ## And a build AFTER the withdrawal stays at the baseline — the withdrawal is not
    ## itself replayed as a statement on the next pass.
    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    assert _shared_key_rows(db) == baseline
    assert stated_options(_options_meta(db)) == ()


## A file whose whole body sits behind a macro the build must be TOLD about. Modelled on
## mbedtls `library/threading.c`, where the difference between a stated and an unstated
## preprocessor configuration is 663 doxygen call edges against 9,940.
_GATED_SOURCE = """\
/** \\file gated.c
 *  \\brief A file doxygen only parses when told the macro is defined.
 */
#if defined(DEMO_FEATURE_ON)
/** \\brief Documented, and reachable only under the macro. */
int gated_documented_fn(int v)
{
    return v + 1;
}
#endif
"""


## @brief Count only the rows DOXYGEN emitted, never the recovered ones.
## @param db Built database.
## @return Number of `dg_source='doxygen'` memberdef functions.
## @version 1
def _doxygen_functions(db: Path) -> int:
    """FILTERED ON PROVENANCE, and that filter is the whole reason this control works.
    gh#11's AST recovery reads the source TEXT, so `gated_documented_fn` lands in
    `memberdef` whether or not the macro reached doxygen — as `dg_source='ast'`, with no
    brief, no params and no `@req`. A count of all functions is therefore IDENTICAL either
    way, and a control written that way would pass against a completely lost statement.

    That is the standing lesson stated one layer over: after adding a recovery layer, every
    later test asserting presence has to say WHICH layer it expects.

    @brief Count doxygen-emitted functions.
    @return The row count.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return int(
            conn.execute(
                "SELECT COUNT(*) FROM memberdef WHERE kind='function' AND dg_source='doxygen'"
            ).fetchone()[0]
        )
    finally:
        conn.close()


## @brief How many macros the build RESOLVED, as the pipeline itself recorded it.
## @param db Built database.
## @return `preprocessor.macro_count`, or 0 when no row was written.
## @version 2
def _resolved_macro_count(db: Path) -> int:
    """THE PIPELINE'S OWN RECORD of what it decided, as distinct from what was STATED. The
    two can disagree, and telling them apart is what separated gh#366 from #399: on a
    withdrawal the stated rows and this one both went to zero while `memberdef` did NOT,
    because the doxygen cache served an older build's output under a reverted key.

    #399 IS FIXED and the two now agree, so this reads as a corroborating measurement rather
    than as the only one available. It is still the RECORD and not the OUTCOME — a stage that
    resolved a macro and then failed to act on it would satisfy this and nothing else — which
    is why the row counts are asserted beside it.

    @brief Read the resolved macro count.
    @return The count.
    @version 2
    """
    conn = sqlite3.connect(str(db))
    try:
        row = conn.execute(
            "SELECT value FROM build_meta WHERE key='preprocessor.macro_count'"
        ).fetchone()
    finally:
        conn.close()
    return int(row[0]) if row and row[0] else 0


def test_a_stated_predefined_survives_a_rebuild_and_a_withdrawal_undoes_it(
    tmp_path: Path,
) -> None:
    """gh#366 — THE SAME HOLE gh#364 CLOSED FOR MANIFESTS, and it loses more than a policy.
    A stated `predefined` decides which preprocessor branches doxygen parses at all, so
    losing it changes WHICH CODE IS IN THE INDEX rather than merely how it is annotated.

    FOUR REAL BUILDS, ONE OUTPUT PATH, counted in DOXYGEN-EMITTED rows:

      1. state nothing        -> the gated function is absent from doxygen's rows
      2. state the macro      -> doxygen parses the branch and emits it
      3. state nothing AGAIN  -> it SURVIVES (this is the fix; it used to vanish)
      4. withdraw with `[]`   -> back to the baseline, and the RECORD is gone

    Build 3 was the failure and it is the normal case, not a corner: `status` reports
    staleness and the guidance says refresh, so an agent that brings an index up with a
    stated configuration and then refreshes discards its own bringup work silently.

    THE COUNT IS PROVENANCE-FILTERED because AST recovery masks the loss — see
    `_doxygen_functions`. An unfiltered count cannot tell a lost statement from a working one.
    """
    root = tmp_path / "gated"
    (root / "src").mkdir(parents=True)
    (root / "src" / "gated.c").write_text(_GATED_SOURCE, encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(DOXYFILE, encoding="utf-8")
    db = tmp_path / "gated.db"

    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    baseline = _doxygen_functions(db)
    assert stated_options(_options_meta(db)) == ()

    build_index(
        output=db, repo_root=root, doxyfile=doxyfile, options={"predefined": ["DEMO_FEATURE_ON"]}
    )
    stated = _doxygen_functions(db)
    assert stated > baseline, (
        f"the stated macro produced no new doxygen rows ({stated} vs baseline {baseline}) — "
        f"the control cannot tell a lost statement from a fixture that never worked"
    )
    assert "predefined" in stated_options(_options_meta(db))

    ## THE FIX. No options at all, which is exactly what an MCP refresh passes.
    ##
    ## THE STAMP WAS ONCE THE ONLY LOAD-BEARING ASSERTION HERE, and mutation is how that was
    ## established rather than assumed: with the replay deleted, the row-count line below
    ## still PASSED — because the doxygen cache served the previous build's output under the
    ## reverted key (#399) — and only the tier assertion failed. A reader who trusted the row
    ## count would have thought this test guarded more than it did.
    ##
    ## #399 IS FIXED, so the row count is load-bearing too and this note is kept as the record
    ## of why a passing row count is not self-evidently a working test. `doxygen_get` now
    ## verifies that the file it serves still holds the digest THIS key produced, so a
    ## reverted key misses instead of inheriting its neighbour's output.
    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    assert _doxygen_functions(db) == stated, (
        "the rebuild lost the stated preprocessor configuration — the build reports success "
        "and the index silently describes a DIFFERENT variant of the repository"
    )
    replayed = _options_meta(db)
    assert replayed[f"predefined.{TIER_KEY}"] == TIER_EXPLICIT, (
        "the record is what makes the replay possible, and it is the assertion mutation "
        "shows to be load-bearing"
    )
    assert "predefined" in stated_options(replayed), (
        "a replayed statement makes this index carry a policy the repository does not "
        "declare — allowed only because it is visible"
    )
    assert _resolved_macro_count(db) == 1, (
        "the replayed macro must reach the stage, not just the stamp"
    )

    ## THE WITHDRAWAL. `[]` is the list spelling of `{}`, and the record must be GONE.
    ##
    ## ASSERTED ON ROWS AGAIN AS WELL AS ON WHAT THE PIPELINE RESOLVED. This step used to
    ## check only `_resolved_macro_count`, and said so: the withdrawal reached the pipeline
    ## correctly — the `preprocessor.*` rows disappeared and the stamp returned to
    ## `heuristic` — while `memberdef` STILL HELD the gated function, because the doxygen
    ## cache mapped many keys to ONE output path that every build overwrote (#399). A
    ## row-count assertion therefore failed on a defect that was not this one.
    ##
    ## That cache is fixed, so the row count is asserted here too. It is the counterpart of
    ## the `index_scope` control below and it points the OTHER WAY, which is what identified
    ## the defect as aliasing rather than staleness: this key was served a WIDER earlier
    ## output, that one a NARROWER earlier output. Neither is "the newer output wins".
    build_index(output=db, repo_root=root, doxyfile=doxyfile, options={"predefined": []})
    assert _doxygen_functions(db) == baseline, (
        "the withdrawal returned the stamp and the macro count to the baseline while the "
        "index kept the gated function — the doxygen cache served the stated build's output "
        "back to the withdrawn key (#399)"
    )
    withdrawn = _options_meta(db)
    assert withdrawn[f"predefined.{TIER_KEY}"] == TIER_HEURISTIC
    assert f"predefined.{EXPLICIT_KEY}" not in withdrawn, (
        "the record must be GONE, not ignored: a withdrawal that silently fails is the "
        "key_arg_idx-for-key_arg_index class of defect"
    )
    assert _resolved_macro_count(db) == 0, "the withdrawal must reach the preprocessor stage"

    ## And the withdrawal is not itself replayed as a statement on the next pass.
    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    assert stated_options(_options_meta(db)) == ()
    assert _resolved_macro_count(db) == 0
    assert _doxygen_functions(db) == baseline


def test_a_stated_preprocessor_section_reaches_the_stage_through_the_declaration(
    tmp_path: Path,
) -> None:
    """gh#382 — `preprocessor:` and `kconfig:` were TIER-2 ONLY: readable from a checked-in
    `.clew.yaml` and unreachable from the MCP surface, because neither has an argparse
    dest. That is CLAUDE.md's rule read the other way round — "a declaration reachable only
    from argv is not a declaration" — and it bites hardest on the case the declaration model
    exists for: a third-party repo carrying no config file for a tool it has never heard of.

    THE SECTION NAME IS THE OPTION NAME, which is the 1:1 ruling made literal, and the whole
    section document is stated. Verified through the STAGE rather than the stamp: a section
    that is recorded but never read would satisfy any metadata assertion.

    `predefined` remains as a convenience alias for `preprocessor.predefined`, so this test
    also pins that stating the SECTION works where only the alias did before — the alias
    cannot express `config_header:` at all.
    """
    root = tmp_path / "sectioned"
    (root / "src").mkdir(parents=True)
    (root / "src" / "gated.c").write_text(_GATED_SOURCE, encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(DOXYFILE, encoding="utf-8")
    db = tmp_path / "sectioned.db"

    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    assert _resolved_macro_count(db) == 0

    ## THE SECTION, not the alias. This is the route that did not exist.
    build_index(
        output=db,
        repo_root=root,
        doxyfile=doxyfile,
        options={"preprocessor": {"predefined": ["DEMO_FEATURE_ON"]}},
    )
    assert _resolved_macro_count(db) == 1, (
        "a stated `preprocessor:` section never reached resolve_preprocessor — the option "
        "was accepted and then dropped, which is worse than refusing it"
    )

    ## AND WITHDRAWING IT restores the target's own declaration (here: none).
    build_index(output=db, repo_root=root, doxyfile=doxyfile, options={"preprocessor": {}})
    assert _resolved_macro_count(db) == 0


## @brief Whether one doxygen-emitted function name is in the index.
## @param db Built database.
## @param name Function name to look for.
## @return True when doxygen emitted a row for it.
## @version 1
def _doxygen_has(db: Path, name: str) -> bool:
    """PROVENANCE-FILTERED for the same reason `_doxygen_functions` is: a scope statement
    decides which files doxygen READS, and gh#11's recovery reads source text separately, so
    an unfiltered presence check cannot tell a narrowed scope from a wide one.

    @brief Look for a doxygen-emitted function.
    @return Presence.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return bool(
            conn.execute(
                "SELECT 1 FROM memberdef WHERE name=? AND dg_source='doxygen' LIMIT 1", (name,)
            ).fetchone()
        )
    finally:
        conn.close()


## @brief Whether the index holds a `path` row for one repo-relative file.
## @param db Built database.
## @param name The `path.name` value to look for.
## @return True when doxygen reported reading that file.
## @version 1
def _indexed_path(db: Path, name: str) -> bool:
    """THE FILE INVENTORY DOXYGEN ITSELF REPORTED, which is the narrowest statement of what a
    scope statement controls: `path` is populated straight out of doxygen's own output, so it
    carries no AST-recovery layer to confound it and needs no provenance filter.

    This is the assertion #399 forced this module to give up. It is back because the doxygen
    output cache now verifies that the file it serves is the output THIS key produced, so a
    widened scope is once again measurable in rows.

    @brief Look for one file in the indexed inventory.
    @return Presence.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return bool(conn.execute("SELECT 1 FROM path WHERE name=? LIMIT 1", (name,)).fetchone())
    finally:
        conn.close()


## @brief The scope the pipeline recorded for its own build.
## @param db Built database.
## @return (`scope.source`, `scope.roots`), each empty when unstamped.
## @version 2
def _scope_stamp(db: Path) -> tuple[str, str]:
    """THE PIPELINE'S OWN RECORD of the boundary it resolved, which is the scope analogue of
    `_resolved_macro_count`: distinct from what was STATED. It was for a while the ONLY
    assertion available on a withdrawal, because the doxygen output cache confounded every
    row count (#399); it is kept beside the row assertions now that they work, because a
    record and an outcome are two different claims.

    @brief Read the recorded scope source and roots.
    @return The two values.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        rows = dict(
            conn.execute(
                "SELECT key, value FROM build_meta WHERE key IN ('scope.source','scope.roots')"
            ).fetchall()
        )
    finally:
        conn.close()
    return str(rows.get("scope.source", "")), str(rows.get("scope.roots", ""))


def test_a_stated_index_scope_narrows_the_index_and_a_withdrawal_widens_it(
    tmp_path: Path,
) -> None:
    """gh#382's LAST KEY, and the one that could not use the injection point. `index_scope`
    is resolved by `derive_scope_logged` BEFORE the declaration the stages read is loaded, so
    the stated document is threaded down into `scope._declared_index_scope` and built through
    the SAME construction a written declaration takes.

    MEASURED ON WHAT GOT INDEXED, never on the stamp. A scope statement that is recorded and
    then ignored satisfies every metadata assertion while indexing the whole tree — which is
    the failure the other controls in this module were written against, one section over.

    THE FIXTURE NEEDS TWO ROOTS. With one, "narrowed to src" and "the whole repo" index the
    same files and the control proves nothing; `extra/` exists purely so its function's
    ABSENCE is the measurement.

    @brief A stated index_scope reaches the scope stage.
    """
    root = tmp_path / "scoped"
    doxyfile = _write_target(root)
    (root / "extra").mkdir()
    (root / "extra" / "aside.c").write_text(
        "/** @file\n *  @brief Out-of-scope fixture.\n */\n\n"
        "/** @brief A function only a WIDE scope reaches.\n *  @version 1\n */\n"
        "void aside_fn(void) {}\n",
        encoding="utf-8",
    )
    db = tmp_path / "scoped.db"

    ## 1. State nothing: the whole-repo tier, which must reach BOTH directories. The
    ##    Doxyfile says `INPUT = src`, and from-guard REPLACES that (gh#333) — so this
    ##    assertion also pins that a repo is not punished for documenting itself.
    build_index(output=db, repo_root=root, doxyfile=doxyfile)
    assert _doxygen_has(db, "aside_fn"), (
        "the whole-repo baseline did not reach extra/ — without that this fixture cannot "
        "distinguish a narrowed scope from a scope statement that was silently dropped"
    )

    ## 2. STATE THE SECTION. `extra/` must fall out of the index entirely.
    build_index(
        output=db,
        repo_root=root,
        doxyfile=doxyfile,
        options={"index_scope": {"roots": ["src"]}},
    )
    assert not _doxygen_has(db, "aside_fn"), (
        "a stated `index_scope:` never reached derive_scope — the option was accepted and "
        "then dropped, which builds a DIFFERENT boundary than the caller stated and reports "
        "success"
    )
    assert _doxygen_has(db, WRITER), "the narrowed scope must still index what it named"

    ## 3. WITHDRAW IT. `{}` restores the target's own answer, here the whole repo. A
    ##    statement that cannot be taken back is a one-way door on a surface whose whole
    ##    point is that the target's tree is never modified.
    ##
    ##    ASSERTED ON ROWS AGAIN, WHICH IS THE #399 CONTROL. This step used to check only
    ##    `_scope_stamp`, because the doxygen output cache mapped many KEYS to ONE output
    ##    file that every build overwrote: `doxygen_get` hit on "a row for this key exists
    ##    AND the path exists", which is true of every key as soon as ANY of them has run.
    ##    So the withdrawal reached `derive_scope` — `scope.source` read `whole-repo`, roots
    ##    `.` — while step 2's NARROW output was served back to this WIDE key and `path` still
    ##    held only `src/store.c`. That is why the defect is not "the newer output wins" but
    ##    "whichever output was written last wins, whatever its key said": the `predefined`
    ##    withdrawal above was served a WIDER earlier output and this one a NARROWER one.
    ##
    ##    `doxygen_get` now compares the recorded digest of the output against the file's
    ##    current one, so this key MISSES against step 2's overwrite and doxygen re-runs.
    ##    The two lines below are the control: with that verification removed they fail and
    ##    only the stamp survives, which is exactly the state this comment used to describe.
    build_index(output=db, repo_root=root, doxyfile=doxyfile, options={"index_scope": {}})
    assert _indexed_path(db, "extra/aside.c"), (
        "the withdrawal widened the scope on paper and the index did not follow — the "
        "doxygen output cache served the narrow build's output back to the wide key (#399)"
    )
    assert _doxygen_has(db, "aside_fn"), (
        "extra/ is back in the file inventory but its function is not, so the served output "
        "is not the one this configuration produced"
    )
    assert _scope_stamp(db) == (SOURCE_WHOLE_REPO, "."), (
        "the withdrawal did not widen the scope back — three-state semantics are what make "
        "every other option's absent/empty/non-empty rule uniform"
    )


def test_every_declaration_section_has_a_matching_option() -> None:
    """THE 1:1 RULING, ASSERTED SO IT CANNOT DRIFT (gh#382). Keys are meant to be 1:1 and
    share one namespace, because a translation layer is where two spellings diverge. This was
    9 of 11 when the work started and the two names the plan listed were not the two that
    were actually missing — it named `config_header`, which is a KEY INSIDE `preprocessor`
    rather than a section.

    IT IS NOW 11 OF 11: `index_scope` was the last gap and the exception this test used to
    assert is DELETED, which is the mechanism working as intended — closing the gap broke the
    test and the exception had to be removed deliberately rather than decaying into a claim
    nobody re-checked. It needed its own route (threaded into `scope._declared_index_scope`)
    because scope is resolved before the declaration the stages read is loaded.

    ONE DELIBERATE ASYMMETRY REMAINS, named here so it cannot become an accident:
    `predefined` is an option with no section, kept as a convenience alias for
    `preprocessor.predefined` because the acceptance harness and every existing caller
    name it.
    """
    from clew import buildoptions
    from clew.declaration import KNOWN_SECTIONS

    sections, options = set(KNOWN_SECTIONS), set(buildoptions.accepted_options())
    assert not sections - options, (
        "a declaration section with no option is tier-2 only and therefore unreachable from "
        "the MCP surface, which is the shape the declaration model forbids"
    )
    assert options - sections == {"predefined"}, (
        "an option whose name is not a section is a translation layer, and that is where two "
        "spellings drift — only the documented alias is allowed"
    )
