# SPDX-License-Identifier: MIT
"""A QUESTION THE JUDGE NEVER RULED ON SCORED 0.0 AND WAS PUBLISHED AS A CAPABILITY RESULT.

**MEASURED on the frozen 1.1.0 grid.** `self` Q6, blended arm, all three replicates:

    samples=18  errors=18  decisions=13  hit=None on every one
    score=0.0   unmarked_pct=1.00

Every judge call for that cell failed. Nothing was ruled. `QuestionResult.score()` leaves
unruled weight in the DENOMINATOR, so 100% unruled divides zero earned weight by the full total
and returns **0.0** — a number indistinguishable from a question answered entirely wrong.

Across the grid: 152 of 2,970 judge samples errored (5.1%), over 14 cells, of which **4 were
100% unruled and scored anyway**, all of them `self` Q6. Eleven of the fourteen sit on `self`
Q5 and Q6.

**WHAT IT COST, AND IT IS NOT SMALL.** Excluding only the cells where nothing was ruled:

    self, blended arm      published 37.9  (LOSES to baseline 44.0)  ->  45.4  (WINS by +1.4)
    headline, blended      published +0.25                           ->  +1.54
    headline, index_only   published -13.92                          ->  -13.67

The blended arm has a strict superset of the baseline arm's tools, so it is not capable of
scoring lower for reasons of capability — that observation is what sent anyone looking here. The
answer is that it did not score lower. Three cells were scored zero after the judge errored
eighteen times out of eighteen.

**THIS IS THE RULE THIS REPOSITORY RETURNS TO MOST.** `tool_calls = -1` means unknown and must
never be counted as zero; an absent table means the layer never ran. A question nothing ruled on
is unmeasured, and reporting it as 0.0 is absence published as a measurement — on the one axis
the whole harness exists to measure.

**THE FINGERPRINT MOVES, FOR THE FOURTH TIME.** `grader_fingerprint` hashes every `*.py` under
`acceptance/grader/`, so this changes it from `0e7ad2bdb67d` to `5489758d9a50`. The frozen run's
144 sidecars record `9cc2b15baf93` and were already un-re-gradable from this tree before today;
this moves it further, and `test_grader_fingerprint_is_the_value_published_runs_recorded` is where
that decision is made consciously rather than routed around. Declining to fix a defect in order
to hold a hash still would be the failure that pin exists to prevent, not honour. The run's own
grading stays valid at the fingerprint its sidecars record.

@brief A question with no ruled weight is refused, not scored zero.
@version 1
"""

from __future__ import annotations

import pytest

from acceptance.grader.score import Decision, QuestionResult


##
# @brief One decision with a given verdict and weight.
# @version 1
def _dec(mark: str, weight: int, hit: bool | None) -> Decision:
    return Decision(mark=mark, kind="conclusion", weight=weight, hit=hit)


## @brief A question with no ruled weight reports no score.
## @version 1
def test_a_fully_unruled_question_has_no_score() -> None:
    """RED BEFORE THE FIX: `score()` returns `(0.0, 1.0)` — a zero score beside the statement
    that 100% of the weight was never ruled. The two fields contradict each other and the
    aggregation reads the first.

    Asserted as `None` rather than as a sentinel number: every numeric choice here is a score
    some answer could legitimately earn, and the whole defect is a number standing in for an
    absent measurement.
    """
    q = QuestionResult(id="Q6", decisions=[_dec("a", 3, None), _dec("b", 2, None)])

    score, unmarked = q.score()

    assert unmarked == pytest.approx(1.0), "precondition: every mark unruled"
    assert score is None, (
        f"a question nothing was ruled on scored {score!r} — absence published as a measurement"
    )


## @brief A partially ruled question still scores, over the full denominator.
## @version 1
def test_a_partially_unruled_question_still_scores() -> None:
    """THE BOUND, AND IT IS NOT A STYLE CHOICE. `self` Q6's baseline cells were 33-81% unruled
    and still scored, which is the behaviour the docstring describes — unruled weight stays in
    the denominator so a judge that could not rule cannot be mistaken for a mark that was missed.

    Widening the refusal to "any unruled weight" would void 14 cells of the frozen grid and
    change the published figure far beyond the defect being fixed. Only the case where NOTHING
    was ruled is unmeasured.
    """
    q = QuestionResult(
        id="Q6", decisions=[_dec("a", 3, True), _dec("b", 2, None), _dec("c", 1, False)]
    )

    score, unmarked = q.score()

    assert score == pytest.approx(3 / 6), f"earned/total over the full denominator: {score}"
    assert unmarked == pytest.approx(2 / 6)


## @brief A question with no decisions at all is also unmeasured.
## @version 1
def test_a_question_with_no_decisions_is_unmeasured() -> None:
    """The same distinction one step earlier: a question the grader produced no decisions for was
    returning `(0.0, 0.0)` — a zero score AND a claim that nothing was unmarked, which reads as
    "measured, scored nothing". It is the shape `acceptance/DESIGN.md` records as defect 4c, an
    arm-fenced question reporting a measured zero.
    """
    assert QuestionResult(id="Q6", decisions=[]).score()[0] is None


## @brief An all-miss question still scores zero, because that IS a measurement.
## @version 1
def test_an_all_miss_question_still_scores_zero() -> None:
    """THE CASE THE FIX MUST NOT SWALLOW. An answer the judge ruled on and rejected at every mark
    genuinely earned 0.0, and that is a result. If this returned `None` the fix would have traded
    one indistinguishable pair for another, in the direction that flatters the tool.
    """
    q = QuestionResult(id="Q6", decisions=[_dec("a", 3, False), _dec("b", 2, False)])

    score, unmarked = q.score()

    assert score == pytest.approx(0.0), "a ruled rejection is a measured zero and must stay one"
    assert unmarked == pytest.approx(0.0)


# ─── the consumers, which a null score would crash ──────────────────────────


## @brief The variance table survives a cell with no score.
## @version 1
def test_the_variance_table_skips_an_unmeasured_pass() -> None:
    """THE DEFECT MY OWN FIX WOULD HAVE INTRODUCED, caught by reading the consumers rather than
    by the suite — no test fed a null score through the report, so 2,521 tests passed over a
    `float(None)`.

    `_variance_rows` did `float(p.get("score", 0.0))`, which raises `TypeError` on the `null` a
    fully-unruled cell now records. A grade pass with no score contributes no spread, because
    there is no spread between a number and an absence; it must be dropped from that pass list,
    not coerced to zero — coercing is the original defect moved one file over.

    @brief A null-score pass is excluded from the spread.
    @return None.
    @version 1
    """
    from acceptance.__main__ import _scored_passes

    passes = [{"score": 0.4, "arm": "index_only"}, {"score": None, "arm": "index_only"}]

    kept = _scored_passes(passes)

    assert [p["score"] for p in kept] == [0.4], (
        "a pass the judge ruled nothing on has no score to compare and must be dropped"
    )
    assert _scored_passes([{"score": None}]) == [], (
        "every pass unmeasured means there is nothing to report a spread over"
    )


## @brief A tie count does not count two absences as equal.
## @version 1
def test_two_unmeasured_cells_are_not_a_tie() -> None:
    """`abs(ref["score"] - other["score"])` raises on a null, and the obvious repair — treat two
    nulls as equal — would be worse than the crash. A tie means two arms SCORED the same; two
    cells nobody ruled on have not tied, they have not been measured, and counting them as tied
    would report saturation where there is no data.
    """
    from acceptance.__main__ import _is_tie

    assert _is_tie({"score": 0.5}, {"score": 0.5}) is True
    assert _is_tie({"score": 0.5}, {"score": 0.25}) is False
    assert _is_tie({"score": None}, {"score": None}) is False, (
        "two unmeasured cells have not tied; they have not been measured"
    )
    assert _is_tie({"score": None}, {"score": 0.5}) is False


## @brief The per-cell table prints `unruled`, not a dash and not a zero.
## @version 1
def test_the_cell_table_prints_unruled_rather_than_crashing(capsys) -> None:
    """THE THIRD CONSUMER, AND THE ONE GREPPING MISSED. I searched for the sites that READ
    `grade["score"]` and fixed two. This one formats it — `f"{grade['score']:6.1%}"` — so it does
    not look like arithmetic and raises `TypeError: unsupported format string passed to
    NoneType.__format__`. It was found by running the real report over synthetic null-score
    sidecars, which is the check that distinguishes "unit tested" from "the report survives the
    data the grader now writes".

    THREE OUTCOMES, THREE DISPLAYS. No grade at all prints `—`; a grade the judge ruled nothing
    on prints `unruled`; a measured score prints the percentage. Collapsing the middle into
    either neighbour is the defect this whole change exists to remove, one layer out.

    @brief An unruled cell is displayed as unruled.
    @return None.
    @version 1
    """
    from acceptance.__main__ import _print_cells

    meta = {
        "stem": "Q6_m_index_r1",
        "seconds": 1.0,
        "output_tokens": 1,
        "cache_read_tokens": 1,
        "result_bytes": 1,
        "turns": 1,
        "tool_calls": 1,
        "non_index_tool_calls": 0,
        "denied_tool_calls": 0,
    }
    _print_cells(
        [
            (meta, {"score": None, "unmarked_pct": 1.0, "split_decisions": 0}),
            (
                dict(meta, stem="Q6_m_index_r2"),
                {"score": 0.25, "unmarked_pct": 0.0, "split_decisions": 0},
            ),
            (dict(meta, stem="Q6_m_index_r3"), None),
        ]
    )
    out = capsys.readouterr().out

    assert "unruled" in out, f"an unruled cell must say so:\n{out}"
    assert "25.0%" in out, f"a measured score must still print:\n{out}"
    assert "—" in out, f"an absent grade must still print a dash:\n{out}"
