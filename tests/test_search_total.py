# SPDX-License-Identifier: MIT
"""A search cut by its limit says how many rows there were (T1; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mattermost F2, mbedtls F5), confirmed in code and by
replay: `search(corpus='code', text='retry', limit=25)` on mattermost-mobile returned exactly 25
rows with keys `count/kind/provenance/results/subject/wire_version` only. `count` was the rows
SHOWN, so "25 functions mention retry" and "25 of 140" read the same. The dossier already
discloses its caps this way (`_limited` with `total_available`); search did not.

COUNTED, NOT ESTIMATED, and PRESENT ONLY WHEN A CUT HAPPENED: a reply under its limit has no
`_limited` key, because a field that does not apply is absent.

@brief Tests search's limit disclosure.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.mcp_server.tools_query import QueryTools
from clew.query.export import export_search


@pytest.mark.parametrize(("corpus", "text"), [("symbols", "sensor"), ("code", "return")])
def test_a_cut_search_reports_the_true_total(rich_db: Path, repo_root: Path, corpus, text) -> None:
    """@brief limit=2 against a token with more matches: `_limited.total_available` is the full count."""
    full = export_search(rich_db, text, corpus=corpus, limit=1000, repo_root=repo_root)
    assert full["count"] > 2 and "_limited" not in full
    cut = export_search(rich_db, text, corpus=corpus, limit=2, repo_root=repo_root)
    assert cut["count"] == 2
    assert cut["_limited"]["total_available"] == full["count"]
    assert cut["_limited"]["adjusted"] == {"results": f"{full['count']} -> 2"}


def test_the_mcp_reply_carries_the_same_disclosure(rich_db: Path, repo_root: Path) -> None:
    """@brief The MCP `search` tool, not only the export, says it was cut."""
    tools = QueryTools(lambda: rich_db, lambda: repo_root)
    full = tools.search("return", corpus="code", limit=1000)["count"]
    cut = tools.search("return", corpus="code", limit=3)
    assert cut["_limited"]["total_available"] == full


def test_a_search_under_its_limit_has_no_limited_key(rich_db: Path, repo_root: Path) -> None:
    """@brief Absent, not `total_available == count`."""
    assert "_limited" not in export_search(rich_db, "return", corpus="symbols", limit=25)
