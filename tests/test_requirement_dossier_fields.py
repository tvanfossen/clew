# SPDX-License-Identifier: MIT
"""A requirement dossier carries the IEEE 29148 attributes and every unmapped catalog key (S4
served; 2.0.0).

P2 (S4) made `status`, `rationale`, `verification` and `parent` columns on `requirements`, and
kept every key the reader does not map in `extra`. Nothing served them: a requirement dossier
returned block, title, acceptance and priority only, so a catalog carrying the 29148 attributes
still read, through the tool, exactly like one that did not.

`extra` is the catalog's own keys, verbatim, and ABSENT when the entry had none; the four
attributes are '' when the catalog does not state them.

@brief Tests the 29148 attributes on requirement dossiers.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.query import req_trace
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
  REQ-A-002:
    name: Close the device
"""


def _db(tmp_path: Path) -> Path:
    """@brief Ingest the catalog. @return The db."""
    catalog = tmp_path / "requirements.yaml"
    catalog.write_text(_CATALOG)
    db = tmp_path / "clew.db"
    ingest_requirements_yaml(db, catalog)
    return db


def test_the_29148_attributes_and_extra_are_served(tmp_path: Path) -> None:
    """@brief All four attributes, and the unmapped key under `extra`."""
    t = req_trace(_db(tmp_path), "REQ-A-001")
    assert (t.status, t.rationale, t.verification, t.parent) == (
        "approved",
        "Callers need a handle.",
        "test",
        "REQ-SYS-001",
    )
    assert t.extra == {"x-owner": "platform"}


def test_an_entry_stating_none_of_them_has_empty_attributes_and_no_extra(tmp_path: Path) -> None:
    """@brief '' for an unstated attribute; `extra` absent, not {}."""
    t = req_trace(_db(tmp_path), "REQ-A-002")
    assert (t.status, t.rationale, t.verification, t.parent) == ("", "", "", "")
    assert t.extra is None


def test_an_index_from_before_the_columns_still_traces(tmp_path: Path) -> None:
    """@brief A requirements table without the S4 columns: the trace degrades, it does not raise."""
    db = tmp_path / "old.db"
    with sqlite3.connect(db) as conn:
        conn.execute(
            "CREATE TABLE requirements (id TEXT, block TEXT, title TEXT, acceptance TEXT, priority TEXT)"
        )
        conn.execute("INSERT INTO requirements VALUES ('REQ-A-001', 'A', 'Open', '', '')")
    t = req_trace(db, "REQ-A-001")
    assert t.title == "Open" and t.status == "" and t.extra is None
