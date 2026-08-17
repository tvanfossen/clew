# SPDX-License-Identifier: MIT
"""A function's PRECONDITIONS survive a real build, with the polarity intact.

WHY AN INTEGRATION TEST AND NOT ONLY A UNIT ONE. `tests/test_kconfig.py` proves the harvest
records a branch's extent and that `gates_covering` places a line inside it. Neither proves the
value reaches a DOSSIER, and the path between them crosses four layers that each drop data for
their own good reasons: the harvest caches per file on a content sha, the insert goes through a
positional SELECT list, the query layer thins a degraded database rather than failing, and the
MCP boundary ELIDES a panel that says nothing. A field that arrives empty is indistinguishable
from a field that says "ungated" — which is the whole substitution this feature exists to end.

WHAT IT IS FOR. Both graded questions on this project's acceptance matrix ask, in effect, "is
this compiled in, and under what flag". `grep mbedtls_mutex_lock` finds the text and cannot tell
you it sits behind a flag that is off by default; before this, neither could the index. The
configuration space could say which lines a SYMBOL gates, which requires already knowing the
symbol — an inventory where the question wanted an adjacency.

THE FIXTURE'S `#else` IS THE LOAD-BEARING PART. Measured with tree-sitter: a `preproc_ifdef`
node spans through its `#endif` with the `#else` hanging off it as `alternative`, so a range join
over the node's own extent reports the else-branch function as present when the symbol is SET —
the exact inverse, stated at full confidence. Every assertion here is therefore two-sided.

@brief Integration control for gate coverage on a function function_dossier.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import build_index
from clew.query import function_dossier
from clew.vocabulary import (
    GATE_ORIGIN_DECLARED,
    GATE_ORIGIN_UNDECLARED,
    KCONFIG_GATE_IFDEF,
    KCONFIG_GATE_IFNDEF,
)

pytestmark = pytest.mark.integration

## The gated pair and an ungated control, each documented so doxygen emits a memberdef for it —
## the function_dossier resolves through `memberdef`, so an undocumented function would make this test
## fail for a reason that has nothing to do with gates.
SOURCE = """/** @file
 *  @brief Gate-coverage fixture: one symbol, both branches, and a function outside both.
 */

#ifdef FIXTURE_FAST_PATH
/** @brief Present only when the symbol is set.
 *  @version 1
 */
void fixture_fast(void) { }
#else
/** @brief Present only when the symbol is NOT set.
 *  @version 1
 */
void fixture_slow(void) { }
#endif

/** @brief Present whatever the configuration says.
 *  @version 1
 */
void fixture_always(void) { }
"""

DOXYFILE = (
    "PROJECT_NAME     = gate_coverage_fixture\n"
    "INPUT            = src\n"
    "RECURSIVE        = YES\n"
    "GENERATE_HTML    = NO\n"
    "GENERATE_LATEX   = NO\n"
    "EXTRACT_STATIC   = YES\n"
    "QUIET            = YES\n"
)


## @brief The (macro, form) pairs a function_dossier reports as this function's preconditions.
## @param db Built index.
## @param name Function to look up.
## @return Set of (macro, form) pairs, and the unplaceable-gate count.
## @version 1
def _gated_by(db: Path, name: str) -> tuple[set[tuple[str, str]], int]:
    """Read through the SHIPPED query entry point, not by querying `kconfig_gates` directly. A
    SQL assertion here would pass while the function_dossier dropped the field, which is precisely the
    layer boundary this test exists to cross.

    @brief Read one function's gate set from its function_dossier.
    @return The (macro, form) pairs and the unplaceable count.
    @version 1
    """
    doss = function_dossier(db, name)
    assert doss is not None, f"{name} is not in the index — the fixture never built"
    return {(g.macro, g.form) for g in doss.gated_by}, doss.gates_unplaceable


def test_a_dossier_reports_the_gates_covering_the_function(tmp_path: Path) -> None:
    """ONE REAL BUILD, THREE FUNCTIONS, TWO-SIDED THROUGHOUT.

    `fixture_fast` must be reported as requiring the symbol and NOT as requiring its absence;
    `fixture_slow` the other way round; `fixture_always` as neither. A one-sided version of any
    of these passes against an implementation that attributes every gate in the file to every
    line — which is what storing the conditional's whole extent produces, and it is the natural
    thing to write.

    NOTE WHAT IS NOT ASSERTED: whether the symbol is actually DEFINED for this build. That is a
    different question (`preprocessor`/`predefined` answers it) and conflating them is how "the
    text is present" gets read as "the code is compiled in". This field says what the presence
    DEPENDS ON, which is the fact a grep cannot supply at any cost.

    @brief Gate coverage survives a real build and keeps its polarity.
    @version 1
    """
    root = tmp_path / "gated"
    (root / "src").mkdir(parents=True)
    (root / "src" / "fixture.c").write_text(SOURCE, encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(DOXYFILE, encoding="utf-8")
    db = tmp_path / "gates.db"

    build_index(output=db, repo_root=root, doxyfile=doxyfile)

    fast, fast_unplaceable = _gated_by(db, "fixture_fast")
    slow, _ = _gated_by(db, "fixture_slow")
    always, _ = _gated_by(db, "fixture_always")

    assert fast_unplaceable == 0, (
        "every gate in this file was harvested with an extent, so an empty gate list here would "
        "mean ungated rather than unknown — the count is what separates those two answers"
    )
    assert ("FIXTURE_FAST_PATH", KCONFIG_GATE_IFDEF) in fast, (
        f"the true branch must report the symbol as required: {sorted(fast)}"
    )
    assert ("FIXTURE_FAST_PATH", KCONFIG_GATE_IFNDEF) not in fast, (
        f"and must not ALSO report the inverse — that is the node-extent bug: {sorted(fast)}"
    )
    assert ("FIXTURE_FAST_PATH", KCONFIG_GATE_IFNDEF) in slow, (
        f"the else branch is present when the symbol is NOT set: {sorted(slow)}"
    )
    assert ("FIXTURE_FAST_PATH", KCONFIG_GATE_IFDEF) not in slow, (
        f"reporting the else branch as gated ON the symbol inverts the variant: {sorted(slow)}"
    )
    assert not always, (
        f"a function outside every conditional must report no preconditions: {sorted(always)}"
    )


## A function behind TWO flags, only one of which the build declares. One build, so the
## difference between the two rows cannot be an artefact of two different builds.
TWO_FLAG_SOURCE = """/** @file
 *  @brief One function, two gating flags, one of them declared by the build.
 */

#if defined(FIXTURE_DECLARED) && defined(FIXTURE_ABSENT)
/** @brief Needs both flags; the build supplies only one.
 *  @version 1
 */
void fixture_two_flags(void) { }
#endif
"""


def test_a_gate_says_whether_this_build_satisfied_it(tmp_path: Path) -> None:
    """PLAN ITEM 2.8, AND THE ANSWER TURNED OUT TO BE A COMPOSITION RATHER THAN A NEW LAYER. The
    item asked to make `--predefined` ADDITIVE — to LABEL what is on and off instead of deciding
    what is indexed — and left open "whether doxygen alone can do this or the tree-sitter path
    must supply the excluded branches". The tree-sitter path ALREADY supplies them: gh#11 recovers
    a function doxygen never emitted, precisely BECAUSE the preprocessor skipped it. So what was
    missing was never the rows; it was the label, and three fields on one row now carry it:

      * `macro` — which flag decides this code
      * `form`  — which way (`ifdef` present-when-set, `ifndef` present-when-unset)
      * `origin` — whether THIS BUILD's declared configuration supplies that macro

    That triple answers "is it compiled in, and under what flag" from a single row, which is what
    both graded questions ask and what `grep` cannot answer at any price.

    THE WIRING IS THE THING UNDER TEST, not the vocabulary. `origin` is computed from the
    `declared` set that `cli` passes as `preprocessor.macros`; if that argument were ever dropped
    or defaulted, every gate would come back `undeclared` and the field would still look
    plausible — a whole configuration reported as absent, confidently. This repo has shipped
    exactly that shape before (a check that could not read its input reported nothing, which
    looked like passing), so the control is that ONE BUILD produces BOTH labels: `FIXTURE_DECLARED`
    must read `declared` and `FIXTURE_ABSENT` `undeclared`. A single-label assertion passes
    against a hardcoded constant.

    @brief One build distinguishes a satisfied gate from an unsatisfied one.
    @version 1
    """
    root = tmp_path / "twoflag"
    (root / "src").mkdir(parents=True)
    (root / "src" / "twoflag.c").write_text(TWO_FLAG_SOURCE, encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(DOXYFILE, encoding="utf-8")
    db = tmp_path / "twoflag.db"

    build_index(
        output=db,
        repo_root=root,
        doxyfile=doxyfile,
        options={"predefined": ["FIXTURE_DECLARED"]},
    )

    doss = function_dossier(db, "fixture_two_flags")
    assert doss is not None, (
        "the function must be INDEXED even though the build does not satisfy its gates — that is "
        "gh#11's recovery, and it is what makes 'index the union, label the branches' possible "
        "without running the preprocessor twice"
    )
    origins = {gate.macro: gate.origin for gate in doss.gated_by}
    assert origins.get("FIXTURE_DECLARED") == GATE_ORIGIN_DECLARED, (
        f"the build declared this macro, so the gate must say so: {origins}"
    )
    assert origins.get("FIXTURE_ABSENT") == GATE_ORIGIN_UNDECLARED, (
        f"the build did NOT declare this one, and that is the half that says the code is absent "
        f"from this variant: {origins}"
    )


## The function whose body is read after its file has been edited. Two functions so a shift can
## push the SECOND one's text into the FIRST one's recorded span — which is the measured defect,
## not a synthetic one.
DRIFT_SOURCE = """/** @file
 *  @brief Body-anchor fixture: two functions, one of which will move.
 */

/** @brief The subject of the function_dossier.
 *  @version 1
 */
int drift_subject(void)
{
    return 1;
}

/** @brief The function whose text will occupy the subject's line span.
 *  @version 1
 */
int drift_neighbour(void)
{
    return 2;
}
"""


def test_a_body_read_after_the_file_moved_is_disclosed_not_returned_silently(
    tmp_path: Path,
) -> None:
    """THE DEFECT THIS REPRODUCES WAS FOUND BY USING THE TOOL, not by reading the code. A function_dossier
    reported `line_start: 896` and returned 55 lines of a DIFFERENT function; `line_start`,
    `line_end` and `total_lines` were all self-consistent, so nothing in the payload contradicted
    it, and the reader went and read the file instead — a miss the tool caused and then concealed.

    THE MECHANISM IS NOT STALENESS IN GENERAL. `body_excerpt` reads the LIVE working tree at the
    span the INDEX recorded. Same rowid, same identity, correct name, correct file — and text that
    has since moved. `body_excerpt`'s own docstring already called quoting another function's
    source "the worst possible version of that bug, because a body looks like proof", and guarded
    only the re-resolution route to it; this is the other route.

    BOTH DIRECTIONS ARE ASSERTED IN ONE TEST so they cannot drift apart. Before the edit the
    excerpt must report `anchor_mismatch is False` — a check that fires on an untouched tree is
    worse than no check — and after prepending enough lines to push a different function into the
    recorded span it must report True. The lines are still returned either way: withholding
    evidence is worse than labelling it.

    @brief A moved body is disclosed rather than passed off as the function's own.
    @version 1
    """
    root = tmp_path / "drift"
    (root / "src").mkdir(parents=True)
    source = root / "src" / "drift.c"
    source.write_text(DRIFT_SOURCE, encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(DOXYFILE, encoding="utf-8")
    db = tmp_path / "drift.db"

    build_index(output=db, repo_root=root, doxyfile=doxyfile)

    fresh = function_dossier(db, "drift_subject", repo_root=root)
    assert fresh is not None and fresh.body is not None, "the fixture must produce a body"
    assert fresh.body.anchor_mismatch is False, (
        f"the tree is untouched, so the excerpt is the function's own — a mismatch here means the "
        f"check fires on ordinary code: {fresh.body.lines}"
    )
    assert any("drift_subject" in line for line in fresh.body.lines), (
        "and the excerpt really is anchored at the signature, which is what makes the check work"
    )

    ## THE EDIT. Prepending nine lines pushes `drift_neighbour` into the span recorded for
    ## `drift_subject`, which is the shape measured in the wild rather than a truncation.
    source.write_text("/* nine\n * added\n * lines\n * of\n * new\n * leading\n * comment\n"
                      " * text\n */\n" + DRIFT_SOURCE, encoding="utf-8")  # fmt: skip

    moved = function_dossier(db, "drift_subject", repo_root=root)
    assert moved is not None and moved.body is not None
    assert moved.body.anchor_mismatch is True, (
        f"the recorded span no longer holds this function, and saying nothing is what sent a "
        f"reader to the file: {moved.body.lines}"
    )
    assert moved.body.lines, (
        "the lines must still be returned — withholding the evidence is worse than labelling it, "
        "and a reader may still recognise what they are looking at"
    )
