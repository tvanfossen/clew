# SPDX-License-Identifier: MIT
"""A member call reaches a free function only through the module or object that holds it.

FOUND BY MEASURING mattermost-mobile's unresolved inbound sites: 43% of them (1,852 of 4,266, by
a hand-written list of built-in method names) were collisions like `latinise.map` reading 645
"possible callers" — nearly every one an `Array.map` call on some local array. A refused member
call credited every same-named function, including FREE functions no member call can reach.

THE RULE IS JAVASCRIPT'S, not a list of built-in names. `recv.m()` can reach a function that is not
a method only when `recv` IS what holds it: a module the calling file imports
(`import * as latinise ...; latinise.map(s)`), or the object it is a property of
(`transitions.action(s)`). Any other receiver contradicts it — the same "contrary evidence" rule
`_receiver_contradicts` already applies to a typed receiver. And a receiver that names the owning
object exactly is not merely consistent: it resolves the call.

@brief Tests for member-call reachability of free functions.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline


## @brief Build a small TS repo and return (edges, unresolved credits).
## @param tmp_path Pytest temporary directory.
## @return (set of (caller, callee) definitions, {callee definition: sites}).
## @version 1
def _build(tmp_path: Path) -> tuple[set, dict]:
    """@brief Build the fixture. @return Edges and credits."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/lat.ts").write_text(
        "export function map(s: string) { return s; }\n", encoding="utf-8"
    )
    (repo / "src/use.ts").write_text(
        "import * as lat from './lat';\n"
        "export const transitions = { action: (s: string) => s };\n"
        "export function arrays(xs: string[]) { return xs.map((x) => x); }\n"
        "export function chained(o: object) { return Object.keys(o).map((k) => k); }\n"
        "export function viaModule(s: string) { return lat.map(s); }\n"
        "export function viaObject(s: string) { return transitions.action(s); }\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    conn = sqlite3.connect(out)
    edges = set(
        conn.execute(
            "SELECT a.definition, b.definition FROM call_edges e "
            "JOIN memberdef a ON a.rowid = e.caller_rowid "
            "JOIN memberdef b ON b.rowid = e.callee_rowid"
        )
    )
    credits = dict(
        conn.execute(
            "SELECT m.definition, u.sites FROM unresolved_inbound u "
            "JOIN memberdef m ON m.rowid = u.callee_rowid"
        )
    )
    return edges, credits


## @brief `xs.map()` on a local array is not evidence about a free function named `map`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_method_call_on_a_local_value_does_not_credit_a_free_function(tmp_path: Path) -> None:
    """ONE SITE, THROUGH THE IMPORTED MODULE, is the only one that may count for `lat.map`. A
    CHAINED receiver (`Object.keys(o).map`) is a call's result — never a module or an object
    binding — so it is contrary evidence too; measured, it was the 151 that survived the first cut.

    @brief Array.map does not credit lat.map.
    @return None.
    @version 1
    """
    _, credits = _build(tmp_path)
    assert credits.get("src.lat.map") == 1, credits


## @brief A receiver naming the owning object resolves the call.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_receiver_naming_the_owning_object_resolves(tmp_path: Path) -> None:
    """@brief transitions.action(s) is an edge.
    @return None.
    @version 1
    """
    edges, _ = _build(tmp_path)
    assert ("src.use.viaObject", "src.use.transitions.action") in edges, edges
