# SPDX-License-Identifier: MIT
"""The measured refresh cost must be quoted in units a reader acts on.

`_cost_clause` grounds its number in the target's own history rather than a constant, which is
the important half and was already right. What was wrong was the UNIT: it said "506974 ms", which
is eight and a half minutes and does not scan like it. The tool recommended a refresh and then
priced it in a unit that reads as small — and that exact number sat in a real target's metadata
while the stated tolerance was ten minutes, with nobody noticing the two were in tension.

WHAT IS DELIBERATELY NOT CHANGED: the number itself, its provenance, and the honest "unmeasured"
answer when a target has no history. A fabricated estimate presented as a measurement is this
repo's most-recorded failure, and rendering is not permission to start estimating.

@brief Tests for readable units in the measured cost clause.
@version 1
"""

from __future__ import annotations

import pytest

from clew.mcp_server.freshness import _cost_clause, _humanise_ms


@pytest.mark.parametrize(
    ("ms", "expected"),
    [
        ## Below ten seconds the milliseconds ARE the informative unit: rounding a 2.7 s refresh
        ## to "3 s" throws away what makes it obviously cheap.
        ("2700", "2700 ms"),
        ("9999", "9999 ms"),
        ("10000", "10 s"),
        ("59400", "59 s"),
        ("60000", "1 min 0 s"),
        ## The real measurement this was written for.
        ("506974", "8 min 27 s"),
    ],
)
def test_durations_are_spelled_the_way_a_reader_says_them(ms: str, expected: str) -> None:
    """@brief Stored milliseconds render in readable units.
    @version 1
    """
    assert _humanise_ms(ms) == expected


@pytest.mark.parametrize("raw", ["", "later", "1e9999", None])
def test_an_unreadable_duration_is_quoted_not_guessed(raw: object) -> None:
    """FALLS BACK, NEVER RAISES AND NEVER INVENTS. `duration_ms` is persisted as text and an
    index written by another version could hold anything. A staleness notice that raised would
    take down a query that was otherwise answerable, and one that substituted a plausible number
    would be the fabricated-measurement failure this repo has recorded more than any other.

    @brief A non-numeric duration is passed through.
    @version 1
    """
    out = _humanise_ms(raw)  # type: ignore[arg-type]
    assert str(raw) in out


## @brief The clause quotes minutes for a long refresh, not raw milliseconds.
## @version 1
def test_the_cost_clause_no_longer_quotes_bare_milliseconds() -> None:
    """THE REGRESSION THIS EXISTS FOR, asserted on the clause rather than the helper — the helper
    could be perfect and unused, which is exactly how the old wording survived.

    @brief The rendered clause is readable.
    @version 1
    """
    clause = _cost_clause({"duration_ms": "506974", "payloads_recomputed": "42651"})
    assert "8 min 27 s" in clause, clause
    assert "506974" not in clause, (
        "the clause still quotes raw milliseconds, which is the unit that made an eight-minute "
        f"refresh read as a small number: {clause}"
    )
    ## The payload count is untouched — a different fact, and one #470 already got right.
    assert "42651" in clause


## @brief An untimed target still says so plainly.
## @version 1
def test_an_untimed_target_is_still_reported_as_unmeasured() -> None:
    """The honest-absence path must survive a rendering change. An agent that cannot measure the
    correction estimates it badly, so "unmeasured" has to stay available rather than degrading
    into a rendered zero.

    @brief No history still reads as no history.
    @version 1
    """
    assert "unmeasured" in _cost_clause(None)
    assert "unmeasured" in _cost_clause({})


## The real measurement from a stale target, verbatim from its build_meta.
_SASSAFRAS = {
    "duration_ms": "37635",
    "payloads_recomputed": "18",
    "cache_hits": "13509",
    ## THE COMPLETE STAGE LIST, not the top few. A truncated paste makes the total smaller and
    ## doxygen's share correspondingly larger — 74% instead of 66% — so an abbreviated fixture
    ## would have pinned the wrong number while looking like the real measurement.
    "stages": (
        "resolve=445 declaration=8 index_cache_scan=85 doxygen=24913 copy=19 sanitize=73 "
        "fix_paths=138 repair_names=36 supplementary_docs=235 kconfig=1 shared_parse=113 "
        "kconfig_gates=138 ast_symbols=512 external=66 coverage=194 file_docs=616 "
        "call_edges=122 macro_hop_edges=66 ast_call_edges=4254 macro_refs=190 "
        "callback_edges=1007 locks=158 dispatch_edges=0 dominated_fuzzy=95 threads=129 "
        "shared_key_inferred=234 shared_key_declared=0 data_model_keys=954 mqtt_dispatch=0 "
        "event_edges=0 thread_boundaries=6 requirements=16 req_edges=85 req_test_edges=22 "
        "reachability=2139 test_scope=68 scope_provenance=226 signature=206 swap=28 "
        "report_stats=18"
    ),
}


##
# @brief The clause must not blame the duration on the payload count.
# @return None.
# @version 1
def test_the_cost_is_not_attributed_to_the_payload_count() -> None:
    """gh#10. Both numbers were right and the SENTENCE joining them was not:

        "the last refresh of this target measured 38 s recomputing 18 cached stage payload(s)"

    reads as "38 seconds went on recomputing 18 payloads". On the target it was measured
    from, 13,509 payloads were cache HITS, only 18 were recomputed, and 66% of the time was
    doxygen re-running — which the payload cache does not cover at all.

    A reader draws one of two wrong conclusions: that 18 payloads cost 38 seconds, so payload
    work is ruinous; or that a refresh is cheap because so few payloads are stale. The actual
    determinant — how much doxygen must redo — was not in the sentence.

    The README argues explicitly that refresh cost must be legible, because "an agent that
    believes the index is expensive to correct stops using the index, and then reasons from a
    stale one". This clause is the only place that cost reaches a reader mid-session.

    @brief The duration and the payload count are separate facts.
    @return None.
    @version 1
    """
    clause = _cost_clause(_SASSAFRAS)
    assert "measured 37635" not in clause
    assert "37635" not in clause, f"raw milliseconds are back: {clause}"
    assert "s recomputing 18" not in clause, (
        f"the duration is still welded to the payload count as its cause: {clause}"
    )


##
# @brief The clause names what actually dominated the cost.
# @return None.
# @version 1
def test_the_clause_names_the_stage_that_dominated() -> None:
    """WHAT A READER NEEDS IN ORDER TO ACT. Knowing a refresh costs 38 s says whether to run
    it; knowing two thirds of that is doxygen says what would change it — and that trimming
    the changed-file set will not, because doxygen's xref pass is global.

    The share is READ FROM THE TARGET'S OWN STAGE TIMINGS, like every other number in this
    clause. Nothing here is a constant or a typical value.

    @brief The dominant stage and its share are reported.
    @return None.
    @version 1
    """
    clause = _cost_clause(_SASSAFRAS)
    assert "doxygen" in clause, f"the dominant stage is not named: {clause}"
    assert "66%" in clause, f"its share is not given: {clause}"


##
# @brief The cache hits are reported, so the recomputed count reads as a fraction.
# @return None.
# @version 1
def test_the_cache_hits_are_reported_beside_the_recomputed_count() -> None:
    """18 ALONE IS THE MISLEADING HALF. Without its denominator it reads as the whole of the
    work; beside 13,509 hits it reads as what it is — a cache that worked almost perfectly,
    on a refresh whose cost was somewhere else entirely.

    @brief Recomputed and cached payloads appear together.
    @return None.
    @version 1
    """
    clause = _cost_clause(_SASSAFRAS)
    assert "18" in clause and "13509" in clause, clause


##
# @brief An index with no stage timings attributes nothing.
# @return None.
# @version 1
def test_an_index_without_stage_timings_attributes_nothing() -> None:
    """DEGRADES INTO SILENCE, NOT INTO A GUESS. An index built before stage timings were
    recorded cannot say what dominated, and naming a typical stage would be the fabricated
    measurement this module's own docstring calls the repo's most-recorded failure. The
    duration and payload count still report; the attribution simply is not there.

    @brief No timings means no attribution clause.
    @return None.
    @version 1
    """
    clause = _cost_clause({"duration_ms": "37635", "payloads_recomputed": "18"})
    assert "38 s" in clause, f"37635 ms rounds to 38 s: {clause}"
    assert "18" in clause
    assert "%" not in clause, f"a share was invented with no timings to derive it from: {clause}"
    assert "doxygen" not in clause
