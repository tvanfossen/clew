# SPDX-License-Identifier: MIT
"""A call through an injected, interface-typed member reaches that interface's implementations.

THE DEPENDENCY-INJECTION SHAPE, in TypeScript's own syntax:

    class Screen {
        constructor(private readonly svc: UserService) {}
        load() { return this.svc.getUser('1'); }
    }

`this.svc`'s type is DECLARED, so which `getUser` the call can reach is a fact, not a guess: the
methods of classes implementing `UserService`. It narrows the call to that family — and never to an
unrelated class that happens to have a `getUser` too. Which implementation is BOUND at runtime is
decided by container configuration the source does not state, so the call is recorded as a FUZZY
edge to each implementation: bounded by the declared type, never picked.

ONLY AN INTERFACE-TYPED RECEIVER widens to its implementors. A class-typed receiver resolves to
that class exactly as before, which keeps C++ base-pointer resolution unchanged.

@brief Tests for injected interface receivers.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline

_SRC = """\
export interface UserService { getUser(id: string): string; }
export class RealUserService implements UserService { getUser(id: string) { return id; } }
export class FakeUserService implements UserService { getUser(id: string) { return 'x'; } }
export class Other { getUser(id: string) { return 'o'; } }

export class Screen {
    constructor(private readonly svc: UserService) {}
    load() { return this.svc.getUser('1'); }
}

export class Holder {
    repo: UserService;
    run() { return this.repo.getUser('2'); }
}
"""


## @brief Build the fixture and return every (caller, callee, confidence) edge.
## @param tmp_path Pytest temporary directory.
## @return The edges.
## @version 1
def _edges(tmp_path: Path) -> set[tuple[str, str, str]]:
    """@brief Build and read edges. @return Edges."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/svc.ts").write_text(_SRC, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return set(
        sqlite3.connect(out).execute(
            "SELECT a.definition, b.definition, e.confidence FROM call_edges e "
            "JOIN memberdef a ON a.rowid = e.caller_rowid "
            "JOIN memberdef b ON b.rowid = e.callee_rowid "
            "WHERE b.name = 'getUser'"
        )
    )


## @brief A constructor-injected interface reaches every implementation, fuzzily, and no namesake.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_constructor_injected_interface_reaches_its_implementations(tmp_path: Path) -> None:
    """@brief Screen.load -> Real/Fake getUser, not Other.
    @return None.
    @version 1
    """
    edges = _edges(tmp_path)
    callees = {callee for caller, callee, _ in edges if caller == "src.svc.Screen.load"}
    assert {"src.svc.RealUserService.getUser", "src.svc.FakeUserService.getUser"} <= callees, edges
    assert "src.svc.Other.getUser" not in callees, edges


## @brief A typed field works the same way.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_typed_field_reaches_the_interface_implementations(tmp_path: Path) -> None:
    """@brief Holder.run -> Real/Fake getUser.
    @return None.
    @version 1
    """
    edges = _edges(tmp_path)
    callees = {callee for caller, callee, _ in edges if caller == "src.svc.Holder.run"}
    assert {"src.svc.RealUserService.getUser", "src.svc.FakeUserService.getUser"} <= callees, edges
    assert "src.svc.Other.getUser" not in callees, edges
