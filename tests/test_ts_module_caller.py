# SPDX-License-Identifier: MIT
"""Code outside every named function still has a caller: the file's `__module__`.

FOUND BY THE 1.3.0 GRID. mattermost-mobile's `index_only` arm lost Q4 by 21 points because
`observeCanViewArchivedChannels` showed NO callers, though three screens call it. Each call sits in
the HOC wiring every screen file ends with:

    const enhanced = withObservables([], ({database}) => ({
        canShowArchivedChannels: observeCanViewArchivedChannels(database),
    }));
    export default withDatabase(enhanced(BrowseChannels));

The callback is anonymous and module-level, so no named function encloses the call, and a call
site with no enclosing function was DROPPED — no edge, no refusal, nothing. Measured: on that tree
`observeConfigBooleanValue` had 23 edges against 63 non-test files using it.

ONE ROW PER FILE, named `__module__`, spanning the whole file. The innermost-span rule credits a
call to the smallest enclosing function, so every named function still wins; only code no named
function contains falls to the module — which is exactly where it runs, at import. Parse-built
(JS/TS) only.

@brief Tests for the per-file module caller.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline

_QUERIES = "export function observeArchived(db: string) { return db; }\n"
_SCREEN = """\
import {observeArchived} from './queries';

export function BrowseChannels() { return observeArchived('inside'); }

const enhanced = withObservables([], ({database}) => ({
    canShowArchived: observeArchived(database),
}));

export default withDatabase(enhanced(BrowseChannels));
"""


## @brief Build the fixture and return (caller definition, callee name) edges.
## @param tmp_path Pytest temporary directory.
## @return The edges.
## @version 1
def _edges(tmp_path: Path) -> set[tuple[str, str]]:
    """@brief Build and read edges. @return Edges."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/queries.ts").write_text(_QUERIES, encoding="utf-8")
    (repo / "src/screen.tsx").write_text(_SCREEN, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return set(
        sqlite3.connect(out).execute(
            "SELECT a.definition, b.name FROM call_edges e "
            "JOIN memberdef a ON a.rowid = e.caller_rowid "
            "JOIN memberdef b ON b.rowid = e.callee_rowid"
        )
    )


## @brief A call in module-level HOC wiring is an edge from the file's `__module__`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_call_in_module_level_wiring_has_the_module_as_caller(tmp_path: Path) -> None:
    """@brief observeArchived's caller is src.screen.__module__.
    @return None.
    @version 1
    """
    edges = _edges(tmp_path)
    assert ("src.screen.__module__", "observeArchived") in edges, edges


## @brief A call inside a named function is still credited to that function, not the module.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_named_function_still_wins_over_the_module(tmp_path: Path) -> None:
    """THE INNERMOST SPAN DECIDES: the call inside `BrowseChannels` is credited to
    `BrowseChannels`, so `__module__` only ever catches what no named function contains.

    @brief Named functions keep their calls.
    @return None.
    @version 1
    """
    edges = _edges(tmp_path)
    assert ("src.screen.BrowseChannels", "observeArchived") in edges, edges
