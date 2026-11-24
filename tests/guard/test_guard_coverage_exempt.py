# SPDX-License-Identifier: MIT
"""Requirement coverage, exempted by status and never silently (round 3, P6c-2).

OWNER 2026-11-16: gate that every catalogued requirement resolves to an implementer, "exempted by
status, never silently". A requirement whose status is in `impact.requirements.exempt_status`
(read from `status_field`) is not a coverage gap — it is listed as EXEMPT, by id and status, so
an exemption is visible in every report rather than a hole in the count. Every other untagged
requirement is uncovered and fails `clew guard coverage`.

@brief Tests for status-exempt requirement coverage.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.coverage import analyze_coverage, run_coverage

_SRC = """\
/**
 * @brief Does it.
 * @req REQ-A-001
 * @version 1.0
 */
void f(void) {}
"""


def _config(tmp_path: Path, catalog: str, exempt: list[str] | None) -> dict:
    from guard_helpers import guard_yaml

    from clew.guard.config import load_config

    (tmp_path / "src").mkdir(exist_ok=True)
    (tmp_path / "src" / "f.c").write_text(_SRC)
    (tmp_path / "requirements.yaml").write_text(catalog)
    extra = ""
    if exempt is not None:
        extra = f"  status_field: x-status\n  exempt_status: [{', '.join(exempt)}]\n"
    cfg = tmp_path / "guard.yaml"
    ## FIXTURE CHANGED (2.0.0, R5-CFG F7): the catalog is the top-level `requirements:`.
    cfg.write_text("requirements:\n  file: requirements.yaml\n" + extra + guard_yaml(""))
    return load_config(cfg)


_CATALOG = """\
requirements:
  REQ-A-001: {name: tagged, x-status: implemented}
  REQ-A-002: {name: unbuilt, x-status: planned}
  REQ-A-003: {name: by config, x-status: configuration}
  REQ-A-004: {name: forgotten, x-status: implemented}
"""


def test_an_exempt_status_is_listed_not_counted_as_a_gap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief planned and configuration are exempt, by id and status; the forgotten one is a gap."""
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, _CATALOG, ["planned", "configuration"])
    report = analyze_coverage(["src"], config)
    assert report["uncovered"] == ["REQ-A-004"]
    ## SPEC WIDENED, ADDITIVE (2.1, #72 item 14): each exempt row also says WHY (`reason`), since a
    ## field (`exempt_when`) can exempt as well as the status. The listed rows are unchanged.
    assert report["exempt"] == [
        {"req_id": "REQ-A-002", "status": "planned", "reason": "x-status: planned"},
        {"req_id": "REQ-A-003", "status": "configuration", "reason": "x-status: configuration"},
    ]
    assert run_coverage(["src"], config) == 1


def test_with_every_gap_exempt_the_gate_passes_and_still_names_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief Exit 0, and the text report still lists each exemption."""
    monkeypatch.chdir(tmp_path)
    catalog = _CATALOG.replace("REQ-A-004: {name: forgotten, x-status: implemented}", "")
    config = _config(tmp_path, catalog, ["planned", "configuration"])
    assert run_coverage(["src"], config) == 0
    out = capsys.readouterr().out
    assert "REQ-A-002" in out and "planned" in out and "REQ-A-003" in out


def test_without_exempt_status_nothing_is_exempt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief No declaration, no exemption: every untagged requirement is uncovered."""
    monkeypatch.chdir(tmp_path)
    config = _config(tmp_path, _CATALOG, None)
    report = analyze_coverage(["src"], config)
    assert report["uncovered"] == ["REQ-A-002", "REQ-A-003", "REQ-A-004"]
    assert report["exempt"] == []
