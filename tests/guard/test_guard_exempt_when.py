# SPDX-License-Identifier: MIT
"""Exempt a requirement by any catalogue field, not only its status (#72 item 14, 2.1).

#72 (an adopter, 2026-11-23): most of its MISSING requirements belong to the app, the cloud or the
device firmware, not to the library. The catalogue says so in `responsibility:`, but
`requirements.exempt_status` keyed only on `status`, so "not ours" and "ours and untested" read the
same. `exempt_when: {responsibility: [App, Cloud]}` separates them, and every exemption says why.

@brief Tests exempt_when.
@version 1
"""

from __future__ import annotations

from clew.guard.config import REQUIREMENTS_SCHEMA, _validate_node, exemption


def _req(**extra) -> dict:  # noqa: ANN003
    return {"status_field": "status", "exempt_status": ["planned"], **extra}


def test_a_requirement_is_exempt_by_status_or_by_a_named_field() -> None:
    """@brief The reason names the field and its value; neither match is None."""
    req = _req(exempt_when={"responsibility": ["App", "Cloud"]})
    assert exemption({"status": "planned"}, req) == "status: planned"
    assert (
        exemption({"status": "active", "responsibility": "Cloud"}, req) == "responsibility: Cloud"
    )
    assert exemption({"status": "active", "responsibility": "Library"}, req) is None
    assert exemption({"responsibility": "App"}, _req()) is None, (
        "no exempt_when, no field exemption"
    )


def test_coverage_lists_an_exempt_requirement_with_its_reason() -> None:
    """@brief `clew guard coverage` says why each one is exempt."""
    from clew.guard.coverage import _exempt

    rows = {
        "REQ-A-001": {"status": "active", "responsibility": "App"},
        "REQ-A-002": {"status": "active"},
    }
    config = {"requirements": _req(exempt_when={"responsibility": ["App"]})}
    assert _exempt(rows, {"REQ-A-001", "REQ-A-002"}, config) == [
        {"req_id": "REQ-A-001", "status": "active", "reason": "responsibility: App"}
    ]


def test_exempt_when_must_map_fields_to_lists() -> None:
    """@brief A string where the list belongs is refused, as everywhere in the schema."""
    errors = _validate_node(
        {"exempt_when": {"responsibility": "App"}}, REQUIREMENTS_SCHEMA, "requirements"
    )
    assert any("exempt_when" in e and "list" in e for e in errors), errors
