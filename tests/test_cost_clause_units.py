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
