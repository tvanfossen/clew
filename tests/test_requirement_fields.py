# SPDX-License-Identifier: MIT
"""IEEE 29148 requirement attributes reach the index; a key nothing reads is kept (S4; 2.0.0).

OWNER-APPROVED 2026-11-17 (standards research, S4): a catalog entry's `status`, `rationale`,
`verification` (method: inspection / analysis / demonstration / test) and `parent` are the
29148 attributes a traceability checklist needs. Before, `_insert_req_entry` wrote five columns
and DROPPED every other key silently, so a catalog carrying these read exactly like one that did
not. Every key the reader does not map is now kept, verbatim, in `extra` (JSON), and the build
log names them — disclosed, never dropped.

@brief Tests S4 requirement columns and unread-key disclosure.
@version 1
"""

from __future__ import annotations

import json
import logging
import sqlite3
from pathlib import Path

from clew.requirements import ingest_requirements_yaml

_CATALOG = """\
requirements:
  REQ-A-001:
    name: Open the device
    status: approved
    rationale: Callers need a handle.
    verification: test
    parent: REQ-SYS-001
    x-owner: platform
    risk: high
"""


def _row(tmp_path: Path, caplog) -> dict:
    """@brief Ingest the catalog and read REQ-A-001 back. @return Column → value."""
    catalog = tmp_path / "requirements.yaml"
    catalog.write_text(_CATALOG)
    db = tmp_path / "clew.db"
    with caplog.at_level(logging.INFO, logger="clew"):
        ingest_requirements_yaml(db, catalog)
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return dict(conn.execute("SELECT * FROM requirements WHERE id = 'REQ-A-001'").fetchone())


def test_the_29148_attributes_are_columns(tmp_path: Path, caplog) -> None:
    """@brief status / rationale / verification / parent land in their own columns."""
    row = _row(tmp_path, caplog)
    assert (row["status"], row["rationale"], row["verification"], row["parent"]) == (
        "approved",
        "Callers need a handle.",
        "test",
        "REQ-SYS-001",
    )


def test_an_unread_key_is_kept_and_named(tmp_path: Path, caplog) -> None:
    """@brief `risk` and `x-owner` are kept in `extra`, and the log names them."""
    row = _row(tmp_path, caplog)
    assert json.loads(row["extra"]) == {"risk": "high", "x-owner": "platform"}
    assert "risk" in caplog.text and "x-owner" in caplog.text


def test_an_entry_with_nothing_extra_has_no_extra(tmp_path: Path, caplog) -> None:
    """@brief `extra` is NULL (absent), not `{}`, when every key was read."""
    catalog = tmp_path / "requirements.yaml"
    catalog.write_text("requirements:\n  REQ-B-001:\n    name: Close\n")
    db = tmp_path / "clew.db"
    ingest_requirements_yaml(db, catalog)
    (extra,) = sqlite3.connect(db).execute("SELECT extra FROM requirements").fetchone()
    assert extra is None
