# SPDX-License-Identifier: MIT
"""The evidence diagram stays readable, and light, at any size (2.0.0, P5.4 follow-up).

MEASURED on clew's own site at 788ea335: REQ-DDB-CONFIG-001 drew 553 tests and 7,758 edges in a
1.15 MB SVG about 14,000 px tall, and the 140 requirement pages carried 14.6 MB of evidence SVG
out of 24.7 MB. That is unreadable and undoes the P5.1 weight work. Above `SUMMARY_TESTS` tests the
diagram draws each implementer to RESULT BUCKETS with counts, and says the full list is in the
tests table on the same page, so nothing is hidden.

@brief Tests the evidence diagram's summary form.
@version 1
"""

from __future__ import annotations

from types import SimpleNamespace

from clew.wiki.reqdiagram import SUMMARY_TESTS, evidence_svg


def _row(n_tests: int):
    """@brief A requirement with two implementers and n tests, every test reaching both."""
    tests = tuple((f"test_{i}", "failed" if i == 0 else "passed") for i in range(n_tests))
    return SimpleNamespace(
        implementers=("load", "parse"),
        tests=tests,
        extent=tuple((t, ("load", "parse")) for t, _s in tests),
        implementers_uncovered=(),
    )


def test_a_small_requirement_draws_every_test() -> None:
    """@brief Up to the threshold: one row per test, one edge per measured link."""
    svg = evidence_svg(_row(SUMMARY_TESTS))
    assert svg.count('class="test"') == SUMMARY_TESTS and "summary" not in svg


def test_a_large_requirement_is_summarised_by_result() -> None:
    """@brief Above it: buckets with counts, a pointer to the table, and a bounded size."""
    svg = evidence_svg(_row(553))
    assert 'class="test"' not in svg
    assert ">552 passed</text>" in svg and ">1 failed</text>" in svg
    assert 'data-edge="load→passed"' in svg and "tests table below" in svg
    assert len(svg) < 4000, len(svg)


def test_the_summary_is_wide_enough_for_its_own_header_and_note() -> None:
    """W-9 (owner review 2026-11-22, req-REQ-DDB-CONFIG-006): the summary form clipped "results (376
    tests" and "every test is in the tests tab…" — its width counted the column labels only.

    @brief The SVG fits its header and its note.
    """
    import re
    from types import SimpleNamespace

    from clew.wiki.reqdiagram import _summary_svg, _width

    tests = [(f"t{i}", "passed") for i in range(376)]
    row = SimpleNamespace(extent=(), implementers_uncovered=())
    svg = _summary_svg(row, ["a"], tests)
    width = float(re.search(r'width="(\d+)"', svg).group(1))
    note = "376 tests, a summary by result: every test is in the tests table below"
    assert width >= _width([note]) and width >= _width(["results (376 tests)"]) + _width(["a"])
