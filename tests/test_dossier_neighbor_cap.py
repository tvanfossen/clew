# SPDX-License-Identifier: MIT
"""`max_neighbors` caps a dossier's callers and callees at depth 1, and the cut is disclosed.

FOUND BY THE 1.3.0 GRID'S COST FIGURE. On mattermost-mobile the `index_only` arm read 32.6% MORE
cache-read tokens than the shell-only baseline. The diagnosis measured the dossier replies the
agents received: `doFetch` returned 50,692 bytes listing all 229 callers, and every later turn
re-reads it. The tool's own parameter says "Cap on callers and callees listed per symbol", but the
cap applied only to a depth > 1 walk; at depth 1 it did nothing, and the 65,536-byte budget was the
only bound.

CAPPED, NEVER SILENTLY. The total is the most useful fact about a hub — "229 callers" — so it is
kept: the cut list gets a `_limited` entry carrying `total_available` and how to see the rest
(raise `max_neighbors`). The default is 25: enough for every "where is this used" set the rubrics
grade (the largest is eight files), and a bound on a hub.

@brief Tests for the depth-1 neighbour cap.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline
from clew.mcp_server.tools_query import QueryTools

_CALLERS = 30


## @brief Index a TS repo where one function has `_CALLERS` callers.
## @param tmp_path Pytest temporary directory.
## @return QueryTools bound to the built index.
## @version 1
def _tools(tmp_path: Path) -> QueryTools:
    """@brief Build the hub fixture. @return Tools."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    body = "export function hub(x: number) { return x; }\n" + "".join(
        f"export function caller{i}() {{ return hub({i}); }}\n" for i in range(_CALLERS)
    )
    (repo / "src/hub.ts").write_text(body, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return QueryTools(lambda: out, lambda: repo)


## @brief The default cap bounds a hub's callers and discloses the total.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_the_default_cap_bounds_callers_and_discloses_the_total(tmp_path: Path) -> None:
    """@brief 30 callers -> 25 listed, total 30 disclosed.
    @return None.
    @version 1
    """
    reply = _tools(tmp_path).dossier("hub")
    assert len(reply["callers"]) == 25, len(reply["callers"])
    limited = reply.get("_limited", {}).get("callers", {})
    assert limited.get("total_available") == _CALLERS, reply.get("_limited")
    assert "max_neighbors" in limited.get("how_to_narrow", ""), limited


## @brief Raising `max_neighbors` returns every caller, with nothing disclosed as cut.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_raising_the_cap_returns_every_caller(tmp_path: Path) -> None:
    """@brief max_neighbors=40 -> all 30, no _limited for callers.
    @return None.
    @version 1
    """
    reply = _tools(tmp_path).dossier("hub", max_neighbors=40)
    assert len(reply["callers"]) == _CALLERS, len(reply["callers"])
    assert "callers" not in reply.get("_limited", {}), reply.get("_limited")
