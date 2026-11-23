# SPDX-License-Identifier: MIT
"""The Tests tab is grouped, counted and summary-first (UX review D-8, owner Q/A 2026-11-22).

Independent UX review: "3,356 rows sit in one flat table with no grouping. Fixture tests … with
result 'absent' are mixed in … A filter box is not a structure." Owner Q/A: before 2.0.0.

@brief Tests the Tests tab's grouping.
@version 1
"""

from __future__ import annotations

from types import SimpleNamespace


def _d(name, file, start=1):
    return SimpleNamespace(name=name, file=file, start=start)


def test_tests_are_grouped_by_file_with_counts_and_fixtures_folded_last() -> None:
    """@brief One collapsed group per file with its result counts; fixture data apart, at the end."""
    from clew.wiki.testpages import _tests_groups

    defs = [
        _d("test_b", "tests/test_b.py"),
        _d("test_a1", "tests/test_a.py"),
        _d("test_a2", "tests/test_a.py", 9),
        _d("test_fx", "tests/data/csample/test_fx.c"),
    ]
    results = {
        "test_a1": SimpleNamespace(status="passed"),
        "test_a2": SimpleNamespace(status="failed"),
        "test_b": SimpleNamespace(status="passed"),
    }
    html = _tests_groups(defs, results, {}, {"test_a1": "test-a1.html"})
    a, b = html.index("tests/test_a.py"), html.index("tests/test_b.py")
    fixtures = html.index('class="tgroup fixtures"')
    assert (
        a < b < fixtures and html.count('<details class="tgroup"') == 3
    )  # the fixture file's own group sits inside the fixtures section
    assert "2 tests · 1 failed · 1 passed" in html  # failures first: what matters most
    assert '<a href="test-a1.html"><code>test_a1</code></a>' in html
    assert html.count('<table class="clew tests-all"') == 3


def test_the_tab_opens_on_result_chips() -> None:
    """@brief Chips per result with counts; each filters the tab."""
    from clew.wiki.testpages import _result_chips

    html = _result_chips({"passed": 3, "failed": 1, "absent": 2})
    assert (
        'data-filter-chip="failed"' in html
        and "failed 1" in html
        and html.index("passed") < html.index("absent")
    )


def test_the_filter_opens_matching_groups_and_the_chips_filter() -> None:
    """@brief Typing opens groups with matches and hides empty ones; a chip toggles its result."""
    from pathlib import Path

    import clew.wiki

    js = (Path(clew.wiki.__file__).parent / "themes/clew/static/clew-views.js").read_text()
    assert "details.tgroup" in js and "data-filter-chip" in js
