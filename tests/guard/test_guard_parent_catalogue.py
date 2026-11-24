# SPDX-License-Identifier: MIT
"""A parent catalogue is checked when its clone is present, else reported unchecked (#73 item 3).

#73 (an adopter, 2026-11-23): a module row `satisfies: [PARENT-ID]` made the module's own gate
refuse unless the parent (product) catalogue was cloned wherever that gate ran — every developer
machine, every CI job — so product and modules pinned each other. Owner Q/A 2026-11-24, remedy (a):
an external catalogue marked `parent: true` is checked when its clone is present; otherwise links
into it are reported unchecked, a warning and never a violation.

@brief Tests the parent catalogue.
@version 1
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

import pytest

from clew.guard.checks import check_satisfies
from clew.guard.impact import RequirementsError, load_external_requirements


def _config(entry: dict) -> dict:
    return {"requirements": {"file": "requirements.yaml", "external": [entry]}}


def _clone(path: Path, catalog: str) -> str:
    path.mkdir(parents=True)
    (path / "requirements.yaml").write_text(catalog)
    for args in (
        ["init", "-q"],
        ["add", "-A"],
        ["-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "c"],
    ):
        subprocess.run(["git", *args], cwd=path, check=True)
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=path, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_an_absent_parent_is_reported_unchecked_not_refused(
    tmp_path: Path, monkeypatch, caplog
) -> None:  # noqa: ANN001
    """@brief No clone: no error; its name is recorded; an unresolvable link is a warning."""
    monkeypatch.chdir(tmp_path)
    unchecked: list[str] = []
    entry = {
        "name": "product",
        "repo": "../product",
        "rev": "abc123",
        "path": "requirements.yaml",
        "parent": True,
    }
    assert load_external_requirements(_config(entry), unchecked) == {}
    assert unchecked == ["product"]
    rows = {"REQ-LIB-001": {"satisfies": "REQ-PRD-001"}}
    with caplog.at_level(logging.WARNING):
        assert check_satisfies(rows, {"REQ-LIB-001"}, "requirements.yaml", unchecked) == []
    assert "REQ-PRD-001" in caplog.text and "unchecked" in caplog.text and "product" in caplog.text


def test_a_catalogue_not_marked_parent_still_refuses(tmp_path: Path, monkeypatch) -> None:  # noqa: ANN001
    """@brief The default is unchanged: a missing pinned catalogue is an error naming it."""
    monkeypatch.chdir(tmp_path)
    entry = {"name": "product", "repo": "../product", "rev": "abc123", "path": "requirements.yaml"}
    with pytest.raises(RequirementsError):
        load_external_requirements(_config(entry), [])


def test_a_present_parent_is_checked_and_a_broken_link_is_a_violation(
    tmp_path: Path, monkeypatch
) -> None:  # noqa: ANN001
    """@brief With the clone at the pin, links into it are checked as any other."""
    rev = _clone(tmp_path / "product", "requirements:\n  REQ-PRD-001:\n    name: Survives\n")
    (tmp_path / "lib").mkdir()
    monkeypatch.chdir(tmp_path / "lib")
    unchecked: list[str] = []
    entry = {
        "name": "product",
        "repo": "../product",
        "rev": rev,
        "path": "requirements.yaml",
        "parent": True,
    }
    known = {"REQ-LIB-001", *load_external_requirements(_config(entry), unchecked)}
    assert unchecked == [] and "REQ-PRD-001" in known
    rows = {"REQ-LIB-001": {"satisfies": ["REQ-PRD-001", "REQ-PRD-999"]}}
    found = check_satisfies(rows, known, "requirements.yaml", unchecked)
    assert len(found) == 1 and "REQ-PRD-999" in found[0].message
