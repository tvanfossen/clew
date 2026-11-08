# SPDX-License-Identifier: MIT
"""Functions declared inside functions are definitions, and a bare call finds them lexically.

FOUND BY THE TYPESCRIPT AUDIT: 478 named closures in mattermost-mobile had no row, because the
definition walk stopped at the first function and never looked inside it — `fetchAllMemberships`
inside an action, `withLock` inside a websocket handler, `initializeApp` inside a layout.

NESTED UNDER THEIR ENCLOSING FUNCTION: `outer.inner`, so two components that each declare an
`onPress` are two definitions, not one name. And a bare `inner()` resolves the way JavaScript
does: the innermost enclosing scope that declares it, outward to the module — before any
same-named function in another file is even considered.

INDEX ONLY: the gate does not demand documentation for a closure (owner's ruling).

A HOOK BINDS A VALUE, NOT ITS CALLBACK. `const v = useMemo(() => ...)` is the computed value;
only `useCallback` returns the function it is given. React's own rule — a `use[A-Z]` call is a
hook — decides it, not a list of hooks.

@brief Tests for nested function definitions and lexical call resolution.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import lang_parsing_substrate as lps

from clew.cli import _build_argparser, _run_pipeline
from clew.jsast import harvest_definitions

_SRC = b"""\
export function outer(a: number) {
    const inner = (x: number) => x + 1;
    function helper() { return inner(a); }
    const value = useMemo(() => compute(a), [a]);
    const onPress = useCallback(() => helper(), []);
    return helper();
}

export class Svc {
    run() {
        const step = () => 1;
        return step();
    }
}
"""

_ELSEWHERE = b"""\
export function inner(x: number) { return x; }
export function helper() { return 0; }
export function step() { return 2; }
"""


## @brief Named closures are definitions under their enclosing function; hook values are not.
## @return None.
## @version 1
def test_nested_functions_are_definitions_under_their_enclosing_function() -> None:
    """@brief Nested definitions harvested and scoped.
    @return None.
    @version 1
    """
    out = harvest_definitions(lps.parse_tree("typescript", _SRC), _SRC)
    got = {(f["cls"], f["name"]) for f in out["functions"]}
    assert {
        ("", "outer"),
        ("outer", "inner"),
        ("outer", "helper"),
        ("outer", "onPress"),
        ("Svc", "run"),
        ("Svc.run", "step"),
    } <= got, got
    assert ("outer", "value") not in got, "useMemo binds a value, not its callback"


## @brief A bare call resolves to the lexically enclosing declaration, not a namesake elsewhere.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_bare_call_resolves_lexically(tmp_path: Path) -> None:
    """THREE NAMESAKES in another file make the bare name ambiguous, so only scope decides.

    @brief inner/helper/step resolve to their enclosing scope's declarations.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/a.ts").write_text(_SRC.decode(), encoding="utf-8")
    (repo / "src/b.ts").write_text(_ELSEWHERE.decode(), encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    edges = set(
        sqlite3.connect(out).execute(
            "SELECT a.definition, b.definition FROM call_edges e "
            "JOIN memberdef a ON a.rowid = e.caller_rowid "
            "JOIN memberdef b ON b.rowid = e.callee_rowid"
        )
    )
    assert ("src.a.outer.helper", "src.a.outer.inner") in edges, edges
    assert ("src.a.outer", "src.a.outer.helper") in edges, edges
    assert ("src.a.Svc.run", "src.a.Svc.run.step") in edges, edges
    assert not any(callee.startswith("src.b.") for _, callee in edges), edges
