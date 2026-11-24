# SPDX-License-Identifier: MIT
"""A dossier's `line_start` is where the function is declared, not where doxygen's body starts (2.1).

FOUND in 2.0.0 (W-11 then the roadmap): for `derive_flow` the index holds `line` 127 (the `def`)
and `bodystart` 142, and the dossier served 142 — a reader opening the file there landed on the
docstring, and the body excerpt began mid-signature (`) -> dict[str, Any]:`). When the declaration
and the body are in ONE file and the declaration comes first, the declaration line leads; a member
defined out of line (header declaration, body in the source file) keeps its body's line.

@brief Tests dossier line_start.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.query.export import export_dossier

_PY = '''"""Mod."""


def spread(
    first: int,
    second: int,
) -> int:
    """Add two numbers across several lines of signature.

    @brief Add.
    """
    return first + second
'''


def _index(repo: Path, tmp_path: Path) -> Path:
    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db


def test_a_multi_line_signature_starts_at_its_def(tmp_path: Path) -> None:
    """@brief `line_start` and the body excerpt both begin at `def`."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text(_PY)
    reply = export_dossier(_index(repo, tmp_path), "spread", repo_root=repo)
    assert reply["line_start"] == 4, reply["line_start"]
    assert reply["body"]["start_line"] == 4 and reply["body"]["lines"][0].startswith("def spread(")


def test_an_out_of_line_member_keeps_its_bodys_line(tmp_path: Path) -> None:
    """@brief Declared in the header, defined in the source: the source's line, not the header's."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "a.h").write_text("/** @brief Twice. */\nint twice(int x);\n")
    (repo / "a.cpp").write_text('#include "a.h"\n\n\nint twice(int x)\n{\n    return 2 * x;\n}\n')
    reply = export_dossier(_index(repo, tmp_path), "twice", repo_root=repo)
    assert reply["file"] == "a.cpp" and reply["line_start"] == 4
