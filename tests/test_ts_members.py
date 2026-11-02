# SPDX-License-Identifier: MIT
"""Interface members and object-literal functions are definitions too.

FOUND BY THE TYPESCRIPT AUDIT of mattermost-mobile, beside the larger mixin gap:

* INTERFACE METHODS had no row: 22 `method_signature`s there, plus function-typed property
  signatures (`login: () => Promise<void>`), the form dependency-injected service interfaces use
  most. Without a row for the interface's method there is nothing for a call through an injected
  interface to narrow TO — the dispatch family is the interface method and its implementations,
  and the interface half was missing.
* FUNCTION-VALUED PROPERTIES of module-level objects (`{guard: () => ..., action: (s) => ...}`) had
  no row: 43 there, 39 of them a keyboard state machine's transitions.

INDEX ONLY, NOT THE GATE (owner's ruling): a signature is a type declaration, and the gate does not
demand documentation for one.

A SIGNATURE IS A DECLARATION, written as doxygen writes a C prototype: no body, `bodystart` and
`bodyend` of -1, so no call site can ever be attributed to it.

@brief Tests for interface-member and object-literal definitions.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import lang_parsing_substrate as lps

from clew.cli import _build_argparser, _run_pipeline
from clew.jsast import harvest_definitions

_SRC = b"""\
export interface UserService {
    getUser(id: string): Promise<User>;
    login: () => Promise<void>;
    name: string;
}

export class RealUserService implements UserService {
    getUser(id: string) { return fetchUser(id); }
    login = async () => {};
    name = 'real';
}

export const transitions = {
    idle: { guard: () => true },
    action: (s: State) => s,
    limit: 3,
};
"""


## @brief Interface method and function-typed property signatures are declarations.
## @return None.
## @version 1
def test_interface_members_are_declarations() -> None:
    """A PLAIN DATA PROPERTY IS NOT ONE: `name: string` stays out.

    @brief Interface signatures harvested.
    @return None.
    @version 1
    """
    out = harvest_definitions(lps.parse_tree("typescript", _SRC), _SRC)
    decls = {(f["cls"], f["name"]) for f in out["functions"] if f.get("decl")}
    assert decls == {("UserService", "getUser"), ("UserService", "login")}, decls


## @brief Function-valued object-literal properties are definitions, owned by their binding.
## @return None.
## @version 1
def test_object_literal_functions_are_definitions() -> None:
    """A NESTED OBJECT'S FUNCTION belongs to the outer binding — the name a reader writes is
    `transitions`, and `idle` is a key, not a declared thing. A non-function value stays out.

    @brief Object-literal functions harvested.
    @return None.
    @version 1
    """
    out = harvest_definitions(lps.parse_tree("typescript", _SRC), _SRC)
    owned = {(f["cls"], f["name"]) for f in out["functions"] if f["cls"] == "transitions"}
    assert owned == {("transitions", "guard"), ("transitions", "action")}, owned


## @brief A declaration row has no body, so nothing can be attributed to it.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_signature_row_has_no_body(tmp_path: Path) -> None:
    """@brief Declarations are written bodiless.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/svc.ts").write_text(_SRC.decode(), encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    rows = dict(
        (definition, (bs, be))
        for definition, bs, be in sqlite3.connect(out).execute(
            "SELECT definition, bodystart, bodyend FROM memberdef WHERE name = 'getUser'"
        )
    )
    assert rows.get("src.svc.UserService.getUser") == (-1, -1), rows
    assert rows.get("src.svc.RealUserService.getUser", (-1, -1))[0] > 0, rows


## @brief A signature that re-declares an implementation does not erase its unresolved count.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_type_signature_does_not_split_attribution(tmp_path: Path) -> None:
    """MEASURED BEFORE IT SHIPPED. Recording interface signatures dropped mattermost-mobile's
    unresolved inbound sites from 4,006 to 3,531: `BaseDataOperator.batchRecords` went from 153 to
    ZERO, because `BaseDataOperatorType` re-declares `batchRecords` and the refused site now had
    two identities, which the attribution rule refuses to credit. A zero there reads as a measured
    "nothing else calls this" — the #32 failure, reintroduced by a type.

    A signature is the contract the implementation satisfies, not a competing callee: it is set
    aside when crediting a refusal, unless nothing but signatures remain.

    @brief Signatures do not dilute unresolved-inbound attribution.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/op.ts").write_text(
        "export interface OperatorType {\n"
        "    batchRecords: (models: string[]) => Promise<void>;\n"
        "}\n"
        "export default class Operator {\n"
        "    async batchRecords(models: string[]) { return; }\n"
        "}\n",
        encoding="utf-8",
    )
    (repo / "src/use.ts").write_text(
        "export async function save(op: any) { await op.batchRecords([]); }\n", encoding="utf-8"
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    credited = dict(
        sqlite3.connect(out).execute(
            "SELECT m.definition, u.sites FROM unresolved_inbound u "
            "JOIN memberdef m ON m.rowid = u.callee_rowid"
        )
    )
    assert credited.get("src.op.Operator.batchRecords") == 1, credited
