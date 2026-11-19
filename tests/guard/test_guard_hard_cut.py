# SPDX-License-Identifier: MIT
"""A doxygen-guard leftover fails the gate, naming it (PG4; 2.0.0, owner Q/A 2026-11-19).

OWNER: "2.0.0 is a good time for a hard cut of doxygen-guard priors — clew only", and a leftover
`.doxygen-guard.yaml` or `doxygen-guard` hook id FAILS rather than warns. FAIL CLOSED, the
precedent the entropic session gave: its requirements catalog was deleted and went unnoticed
for 15 months because every consumer failed open. A stale config a reader believes still applies
is the same failure. clew never reads `.doxygen-guard.yaml`; while it exists, a contributor reading
it is told rules the gate does not enforce.

@brief Tests the doxygen-guard hard cut.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.main import main

_BLOCK = "/**\n * @file a.c\n * @brief B.\n * @version 1.0\n */\n"


def _repo(tmp_path: Path) -> Path:
    """@brief A clean repo with a 2.0.0 config. @return Root."""
    (tmp_path / "a.c").write_text(_BLOCK)
    (tmp_path / ".clew.yaml").write_text("guard:\n  validate: {}\n")
    return tmp_path


def test_a_clean_repo_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief The control: no leftover, rc 0."""
    monkeypatch.chdir(_repo(tmp_path))
    assert main(["validate", "--no-git", "a.c"]) == 0


def test_a_leftover_doxygen_guard_yaml_fails_naming_it(tmp_path, monkeypatch, capsys) -> None:
    """@brief `.doxygen-guard.yaml` present: rc 1, the file named, the fix stated."""
    (_repo(tmp_path) / ".doxygen-guard.yaml").write_text("validate: {}\n")
    monkeypatch.chdir(tmp_path)
    assert main(["validate", "--no-git", "a.c"]) == 1
    err = capsys.readouterr().err
    assert ".doxygen-guard.yaml" in err and ".clew.yaml" in err, err


def test_a_doxygen_guard_hook_id_fails_naming_it(tmp_path, monkeypatch, capsys) -> None:
    """@brief A `doxygen-guard` hook id in .pre-commit-config.yaml: rc 1, naming `clew-guard`."""
    (_repo(tmp_path) / ".pre-commit-config.yaml").write_text(
        "repos:\n  - repo: https://example.invalid/doxygen-guard\n    rev: v1\n    hooks:\n      - id: doxygen-guard\n"
    )
    monkeypatch.chdir(tmp_path)
    assert main(["validate", "--no-git", "a.c"]) == 1
    err = capsys.readouterr().err
    assert "doxygen-guard" in err and "clew-guard" in err, err
