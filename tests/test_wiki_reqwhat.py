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
