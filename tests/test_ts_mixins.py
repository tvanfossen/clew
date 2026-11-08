# SPDX-License-Identifier: MIT
"""A TypeScript mixin class is a class: its members are definitions and its `this` has a base.

FOUND BY AUDITING A REAL TREE. mattermost-mobile builds its whole REST client and its database
operator from mixins of this shape:

    const ClientFiles = <TBase extends Constructor<ClientBase>>(superclass: TBase) =>
        class extends superclass { getFileUrl(...) {...} }

The class is ANONYMOUS and sits in an arrow function's body, and the definition harvest stopped at
the arrow. An AST walk of 2,067 files counted 330 members of such classes; all 330 had no row, so
`getFileUrl` did not exist as far as the index could say. And because the class had no name,
every `this.doFetch()` inside it carried no qualifier and resolved by bare name against every
`doFetch` in the tree — one of the largest sources of unresolved inbound sites measured there.

THE BASE IS DECLARED, NOT GUESSED. `extends superclass` names a parameter; the parameter's type is
`TBase`; `TBase`'s constraint is `Constructor<ClientBase>`. That chain is the language's own
statement of what `this` is, so following it resolves a call without picking among candidates.

@brief Tests for TypeScript mixin classes.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import lang_parsing_substrate as lps

from clew.cli import _build_argparser, _run_pipeline
from clew.jsast import harvest_calls, harvest_definitions

_MIXIN = b"""\
type Constructor<T> = new (...args: any[]) => T;

export default class ClientBase {
    doFetch(url: string) { return url; }
}

const ClientFiles = <TBase extends Constructor<ClientBase>>(superclass: TBase) => class extends superclass {
    getFileUrl(id: string) { return this.doFetch(id); }
    upload = async (f: string) => { return this.doFetch(f); };
};

export const ClientUsers = <TBase extends Constructor<ClientBase>>(superclass: TBase) => {
    return class extends superclass {
        getMe() { return this.doFetch('me'); }
    };
};
"""


## @brief A mixin's members are definitions, owned by a class named after the binding.
## @return None.
## @version 1
def test_mixin_members_are_definitions_of_a_class_named_for_its_binding() -> None:
    """BOTH FORMS that occur: the class as the arrow's expression body, and `return class ...`.

    @brief Mixin members are harvested.
    @return None.
    @version 1
    """
    out = harvest_definitions(lps.parse_tree("typescript", _MIXIN), _MIXIN)
    functions = {(f["cls"], f["name"]) for f in out["functions"]}
    assert {
        ("ClientFiles", "getFileUrl"),
        ("ClientFiles", "upload"),
        ("ClientUsers", "getMe"),
    } <= functions, functions


## @brief A mixin's base is its constraint type, not the parameter it extends.
## @return None.
## @version 1
def test_a_mixin_class_extends_its_declared_constraint_type() -> None:
    """`extends superclass` names a PARAMETER. Recording `superclass` as the base would name a
    class that does not exist; the constraint `Constructor<ClientBase>` names the real one.

    @brief The base is ClientBase.
    @return None.
    @version 1
    """
    out = harvest_definitions(lps.parse_tree("typescript", _MIXIN), _MIXIN)
    classes = {c["name"]: c for c in out["classes"]}
    assert classes["ClientFiles"]["bases"] == ["ClientBase"], classes.get("ClientFiles")
    assert classes["ClientUsers"]["bases"] == ["ClientBase"], classes.get("ClientUsers")


## @brief `this.m()` inside a mixin is qualified by the mixin's class.
## @return None.
## @version 1
def test_this_inside_a_mixin_is_qualified_by_the_mixin() -> None:
    """@brief Mixin `this` calls carry a qualifier.
    @return None.
    @version 1
    """
    sites = harvest_calls(
        lps.parse_tree("typescript", _MIXIN), _MIXIN, "ast", "ast_member", "binding"
    )
    qualifiers = {s[3] for s in sites if s[0] == "doFetch"}
    assert qualifiers == {"ClientFiles.doFetch", "ClientUsers.doFetch"}, qualifiers


## @brief End to end: a mixin member's `this.doFetch()` is an edge to the base's `doFetch`.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_mixin_calls_its_base_through_this(tmp_path: Path) -> None:
    """THE NAME ALONE WOULD NOT DO IT: a second, unrelated `doFetch` exists, so a bare-name
    lookup has two candidates and refuses. Only the declared base picks the right one.

    @brief this.doFetch() resolves to ClientBase.doFetch.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/client.ts").write_text(_MIXIN.decode(), encoding="utf-8")
    (repo / "src/other.ts").write_text(
        "export class Other { doFetch(x: string) { return x; } }\n", encoding="utf-8"
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    edges = set(
        sqlite3.connect(out).execute(
            "SELECT a.name, b.definition FROM call_edges e "
            "JOIN memberdef a ON a.rowid = e.caller_rowid "
            "JOIN memberdef b ON b.rowid = e.callee_rowid "
            "WHERE b.name = 'doFetch'"
        )
    )
    callers = {caller for caller, callee in edges if callee.endswith("ClientBase.doFetch")}
    assert {"getFileUrl", "upload", "getMe"} <= callers, edges
    assert not any(callee.endswith("Other.doFetch") for _, callee in edges), edges
