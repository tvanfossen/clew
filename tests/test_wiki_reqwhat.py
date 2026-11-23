# SPDX-License-Identifier: MIT
"""A requirement page shows WHAT is required as plainly as HOW it is met (W-9, 2.0.0).

OWNER REVIEW 2026-11-22 of req-REQ-DDB-CONFIG-006: "the requirements could be more clearly
visualized on their immediate page, so that the WHAT of the requirement is as clear visually as the
HOW - map is one piece of this, its a very good visual, but it leaves gaps". The page opened on the
evidence diagram (implementers → tests) and kept the requirement itself in one dense paragraph
further down. It now opens with what is required: the criteria one per line, the declared facts,
a declared scenario when the catalog has one, and where in the system it lives.

@brief Tests the requirement page's WHAT section.
@version 1
"""

from __future__ import annotations

from types import SimpleNamespace

from clew.wiki.config import Audience


def _row():
    return SimpleNamespace(
        req_id="REQ-A-001",
        tier="pass",
        implementer_sites=(
            ("resolve", "src/tiers.py", 3),
            ("record", "src/tiers.py", 9),
            ("db", "src/state.py", 4),
        ),
    )


def test_the_what_section_lists_criteria_facts_scenario_and_where() -> None:
    """@brief Criteria split one per line; facts; the declared scenario; blocks by implementer count."""
    from clew.wiki.reqmodal import _what

    entry = {
        "acceptance": "Options resolve through one rule. The winning tier is recorded.",
        "verification": "test",
        "scenario": "Given a flag and a declaration\nWhen a build resolves options\nThen the flag wins",
    }
    ctx = {"rules": Audience(), "blocks": {"src/tiers.py": "Config", "src/state.py": "Server"}}
    html = _what(_row(), entry, ctx)
    assert "<h2>What it requires</h2>" in html
    assert (
        "<li>Options resolve through one rule.</li><li>The winning tier is recorded.</li>" in html
    )
    assert "verification" in html and "test" in html
    assert '<b class="kw">Given</b> a flag and a declaration' in html
    assert html.index("Config") < html.index("Server"), "blocks ordered by implementer count"
    assert 'href="map.html#req=REQ-A-001"' in html


def test_withheld_requirement_text_is_not_shown() -> None:
    """@brief An audience that withholds requirement text gets no criteria or scenario."""
    from clew.wiki.reqmodal import _what

    entry = {"acceptance": "Secret.", "scenario": "Given x\nWhen y\nThen z"}
    html = _what(_row(), entry, {"rules": Audience(exclude_requirement_text=True), "blocks": {}})
    assert "Secret." not in html and "kw" not in html


def test_a_requirement_s_tests_show_what_did_not_pass_and_fold_what_did() -> None:
    """UX review D-7 (owner Q/A 2026-11-22): "Tests (376) is one flat table where most rows say the
    same thing". Each table opens on its summary; tests that did not pass stay visible; passing ones
    fold under their count. Nothing is cut (round 4): every test is still on the page.

    @brief Summary first, passing folded.
    """
    from clew.wiki.reqmodal import _tests

    row = SimpleNamespace(
        tests=(("test_ok1", "passed"), ("test_ok2", "passed"), ("test_bad", "failed")),
        inferred_tests=(),
        measured_tests=(),
        declared_tests=(),
        extent=(),
        distance=(),
        implementers=("f",),
        req_id="REQ-A-001",
    )
    html = _tests(row, {})
    head = html.split("<table", 1)[0]
    assert "3 tests: 1 failed, 2 passed" in head
    visible, folded = html.split("<details", 1)
    assert "test_bad" in visible and "test_ok1" not in visible
    assert "2 passed" in folded and "test_ok1" in folded and "test_ok2" in folded


def test_a_long_implementer_list_is_its_count() -> None:
    """UX review D-9 (owner Q/A 2026-11-22): rows of the requirements index grew to 185 px with 3–4
    long names inline. Two names stay inline; more fold under their count.

    @brief Cells stay two lines.
    """
    from clew.wiki.tracepages import _fold

    assert "<details" not in _fold(["a", "b"], "2 functions")
    folded = _fold(["a", "b", "c"], "3 functions")
    assert folded.startswith('<details class="fold"><summary>3 functions</summary>')


def test_many_requirement_pills_fold_and_each_links_its_page() -> None:
    """UX review D-10: walls of REQ pills. Three or fewer inline; more fold under "N requirements";
    each pill opens the requirement's own page, not an anchor on the index.

    @brief Pills: few inline, many folded, page links.
    """
    from clew.wiki.flowpage import _badges

    few = _badges(["REQ-A-002", "REQ-A-001"])
    assert (
        '<a class="req-badge" href="req-REQ-A-001.html">REQ-A-001</a>' in few
        and "<details" not in few
    )
    many = _badges([f"REQ-A-00{i}" for i in range(1, 6)])
    assert many.startswith('<details class="fold"><summary>5 requirements</summary>')
