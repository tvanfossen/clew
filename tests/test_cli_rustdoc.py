# SPDX-License-Identifier: MIT
"""CLI wiring for the rustdoc path: `_is_rust_only_repo` and an end-to-end
`build_index` against a real cargo crate.

`clew/rustdoc.py` itself is tested in isolation in `tests/test_rustdoc.py`;
this file covers the decision of WHEN `_build_stages` reaches for it instead
of doxygen, and that a real `build_index` call against a Rust repo lands a
queryable database — the same end-to-end contract `test_mcp_server.py`'s
`test_the_build_runs_in_process_and_keeps_stdout_clean` asserts for a C repo.

@brief CLI-level tests for Rust repo detection and the rustdoc build path.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from clew.cli import _is_rust_only_repo, build_index
from clew.query import function_dossier, search

RUSTSAMPLE = Path(__file__).resolve().parent / "data" / "rustsample"


def _nightly_rustdoc_available() -> bool:
    if shutil.which("cargo") is None:
        return False
    proc = subprocess.run(["cargo", "+nightly", "--version"], capture_output=True, text=True)
    return proc.returncode == 0


def test_is_rust_only_repo_true_for_a_bare_cargo_crate(tmp_path: Path) -> None:
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    assert _is_rust_only_repo(tmp_path) is True


def test_is_rust_only_repo_false_without_a_cargo_manifest(tmp_path: Path) -> None:
    assert _is_rust_only_repo(tmp_path) is False


def test_is_rust_only_repo_false_when_the_repo_ships_its_own_doxyfile(tmp_path: Path) -> None:
    """A repo that deliberately configured a doxygen build — a C/C++ project
    vendoring a small Rust tool, say — keeps that configuration rather than
    having it silently overridden by Cargo.toml's mere presence.
    """
    (tmp_path / "Cargo.toml").write_text("[package]\nname='x'\n", encoding="utf-8")
    (tmp_path / "Doxyfile").write_text("INPUT = .\n", encoding="utf-8")
    assert _is_rust_only_repo(tmp_path) is False


@pytest.mark.skipif(
    not _nightly_rustdoc_available(),
    reason="needs cargo + a nightly toolchain (rustup toolchain install nightly)",
)
def test_build_index_against_a_rust_repo_is_queryable(tmp_path: Path) -> None:
    db_path = tmp_path / "clew.db"
    build_index(output=db_path, repo_root=RUSTSAMPLE)
    assert db_path.exists()

    conn = sqlite3.connect(str(db_path))
    try:
        names = {row[0] for row in conn.execute("SELECT name FROM memberdef")}
        assert {"add", "helper", "MAX_RETRIES"} <= names
    finally:
        conn.close()

    hits = search(db_path, "add")
    assert any(hit.name == "add" for hit in hits)

    dossier = function_dossier(db_path, "add", repo_root=RUSTSAMPLE)
    assert dossier is not None
    assert dossier.file == "src/main.rs"
    assert dossier.brief == "Adds two numbers together."
    assert "left + right" in " ".join(dossier.body.lines)
