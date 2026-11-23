# SPDX-License-Identifier: MIT
"""`satisfies:` on a catalogue entry: requirements that satisfy other requirements (GH #68, P6b-2).

A library's requirement often exists BECAUSE a product requirement needs it. A catalogue entry
names that with `satisfies: [REQ-...]` (a list, or one id as a string); the ids may be this
catalogue's own, an external catalogue's, or `<catalog>:<id>`. The index records each link in
`requirement_links`, and a requirement's dossier carries both directions: `satisfies` (what it
serves) and `satisfied_by` (what serves it).

ABSENT IS NOT EMPTY: an index built before the layer has no table, and its dossier has neither
key; a current index with no links answers `[]`.

The gate's half is tests/guard/test_guard_satisfies.py.

@brief Tests for requirement-to-requirement links.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.mcp_server.tools_query import QueryTools

_CATALOG = """\
requirements:
  REQ-LIB-001:
    name: Bounded retry
    satisfies: [REQ-PRD-001, REQ-PRD-002]
  REQ-LIB-002:
    name: Retry is logged
    satisfies: REQ-PRD-001
  REQ-PRD-001:
    name: The product survives a dropped link
  REQ-PRD-002:
    name: The product reports a dropped link
"""
_SOURCE = """\
/**
 * @brief Send once.
 * @req REQ-LIB-001
 */
int send_once(void) { return 0; }
"""


def _tools(tmp_path: Path, catalog: str = _CATALOG) -> QueryTools:
    """@brief Build a fixture index. @return Tools bound to it."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "requirements.yaml").write_text(catalog, encoding="utf-8")
    (repo / "src/send.c").write_text(_SOURCE, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return QueryTools(lambda: out, lambda: repo)


def test_a_requirement_carries_both_directions_of_satisfies(tmp_path: Path) -> None:
    """@brief LIB-001 satisfies PRD-001 and PRD-002; PRD-001 is satisfied by LIB-001 and LIB-002."""
    tools = _tools(tmp_path)
    lib = tools.dossier("REQ-LIB-001")
    assert lib["satisfies"] == ["REQ-PRD-001", "REQ-PRD-002"], lib
    assert lib["satisfied_by"] == []
    prd = tools.dossier("REQ-PRD-001")
    assert prd["satisfied_by"] == ["REQ-LIB-001", "REQ-LIB-002"], prd
    assert prd["satisfies"] == []


def test_an_index_without_the_layer_leaves_both_keys_absent(tmp_path: Path) -> None:
    """@brief Table dropped (an index from before the layer): no `satisfies`, no `satisfied_by`."""
    tools = _tools(tmp_path)
    conn = sqlite3.connect(tmp_path / "clew.db")
    conn.execute("DROP TABLE requirement_links")
    conn.commit()
    conn.close()
    reply = tools.dossier("REQ-LIB-001")
    assert "satisfies" not in reply and "satisfied_by" not in reply, reply


def test_the_table_exists_when_no_catalogue_does(tmp_path: Path) -> None:
    """@brief We looked and found nothing: the table exists, empty."""
    _tools(tmp_path, catalog="")
    conn = sqlite3.connect(tmp_path / "clew.db")
    assert conn.execute("SELECT COUNT(*) FROM requirement_links").fetchone() == (0,)
    conn.close()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["REQ-A-1", "REQ-B-2"], ["REQ-A-1", "REQ-B-2"]),
        ("REQ-A-1", ["REQ-A-1"]),
        ("REQ-A-1, REQ-B-2", ["REQ-A-1", "REQ-B-2"]),
        ("['REQ-A-1', 'REQ-B-2']", ["REQ-A-1", "REQ-B-2"]),
        (None, []),
        ("", []),
    ],
)
def test_satisfies_is_read_from_every_spelling_a_catalogue_uses(
    value: object, expected: list
) -> None:
    """A YAML list, one id, a CSV cell, and a list some loader already turned into text.

    @brief One normaliser for the index and the gate.
    """
    from clew.requirements import satisfies_ids

    assert satisfies_ids(value) == expected
