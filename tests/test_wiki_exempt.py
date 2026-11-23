# SPDX-License-Identifier: MIT
"""The wiki honours the gate's exempt statuses (round 4, R8).

OWNER 2026-11-16, on the clew demo: "5 missing requirements". Three of the five were
REQ-DDB-CONFIG-002 (`x-status: configuration`) and REQ-DDB-SCHEMA-008 / -010 (`x-status:
planned`) — exactly the statuses `impact.requirements.exempt_status` exempts from `clew guard
coverage`. The gate said "exempt", the wiki said MISSING: two tools disagreeing about one catalogue.
A requirement with no linked test whose declared status is exempt is EXEMPT, by status — never
MISSING, and never silently dropped from the count.

@brief Tests for EXEMPT requirement tiers in the wiki.
@version 1
"""

from __future__ import annotations

from clew.wiki.evidence import RequirementEvidence, exempt_by_status
from clew.wiki.summary import TIERS

_GUARD = {
    "requirements": {"status_field": "x-status", "exempt_status": ["planned", "configuration"]}
}


def _row(rid: str, tier: str, tests=()) -> RequirementEvidence:
    return RequirementEvidence(rid, "", tier, tuple(tests), ())


def test_an_exempt_status_with_no_test_is_exempt_not_missing() -> None:
    """@brief planned / configuration → EXEMPT; an implemented one with no test stays MISSING."""
    evidence = [
        _row("R-PLANNED", "MISSING"),
        _row("R-CONFIG", "MISSING"),
        _row("R-FORGOT", "MISSING"),
    ]
    declared = {
        "R-PLANNED": {"x-status": "planned"},
        "R-CONFIG": {"x-status": "configuration"},
        "R-FORGOT": {"x-status": "implemented"},
    }
    tiers = {r.req_id: r.tier for r in exempt_by_status(evidence, declared, _GUARD)}
    assert tiers == {"R-PLANNED": "EXEMPT", "R-CONFIG": "EXEMPT", "R-FORGOT": "MISSING"}


def test_measured_evidence_is_never_overridden_by_a_status() -> None:
    """@brief A planned requirement whose linked test FAILED is GAP: evidence outranks a label."""
    evidence = [
        _row("R-PLANNED", "GAP", [("t", "failed")]),
        _row("R-P2", "PASS", [("t", "passed")]),
    ]
    declared = {"R-PLANNED": {"x-status": "planned"}, "R-P2": {"x-status": "planned"}}
    tiers = {r.req_id: r.tier for r in exempt_by_status(evidence, declared, _GUARD)}
    assert tiers == {"R-PLANNED": "GAP", "R-P2": "PASS"}


def test_without_a_declaration_nothing_is_exempt() -> None:
    """@brief No guard config or no exempt_status: every untested requirement stays MISSING."""
    evidence = [_row("R-PLANNED", "MISSING")]
    declared = {"R-PLANNED": {"x-status": "planned"}}
    assert exempt_by_status(evidence, declared, None)[0].tier == "MISSING"
    assert exempt_by_status(evidence, declared, {"impact": {}})[0].tier == "MISSING"


def test_the_summary_counts_exempt_as_its_own_tier() -> None:
    """@brief EXEMPT is a tier the charts and group table count, not a hole in the total."""
    assert "EXEMPT" in TIERS
