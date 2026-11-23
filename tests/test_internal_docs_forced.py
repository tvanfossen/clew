# SPDX-License-Identifier: MIT
"""The index keeps what follows doxygen's `\\internal` (PG1b; 2.0.0, owner Q/A 2026-11-19).

Doxygen's `\\internal` hides the rest of its comment block when `INTERNAL_DOCS` is off, which is
doxygen's DEFAULT. clew's forced Doxyfile flags set `EXTRACT_ALL` and friends but not this, so a
repository using `\\internal` for its real purpose lost the tags after it from the index: a
`@version` and a `@req` written below the marker were gone from `dossier` and from requirement
links, while clew's own gate (which reads source, not doxygen) still saw them. The index now forces
`INTERNAL_DOCS = YES`: clew indexes everything (`EXTRACT_ALL`), and an internal section is part of
the code being described.

@brief Tests that internal documentation reaches the index.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline

_SRC = """\
/**
 * @brief Open the port.
 * @internal
 * Uses the legacy register map; see the errata sheet.
 * @version 3.1
 */
int port_open(int n) { return n; }
"""


def test_text_after_internal_is_in_the_index(tmp_path: Path) -> None:
    """@brief The detail written after `@internal`, and the `@version` after it, reach memberdef."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "port.c").write_text(_SRC)
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    (detail,) = (
        sqlite3.connect(db)
        .execute(
            "SELECT detaileddescription FROM memberdef WHERE name = 'port_open' AND kind = 'function' "
            "ORDER BY bodystart > 0 DESC LIMIT 1"
        )
        .fetchone()
    )
    assert "legacy register map" in (detail or "")
    assert "3.1" in (detail or "")
