# SPDX-License-Identifier: MIT
"""What a change reaches beyond its own tags: covering tests, and requirements through callers.

2.1, clew#74 items 2-4 (entropic, v2.14.6). `impact.json` named a changed function's own `@req`
tags and stopped. A consumer selecting tests from it needs the tests covering each requirement,
and a fix made entirely in `@utility` helpers named no requirement at all.

- COVERING TESTS are read from the test tree with no index: Catch2 cases by title
  (`clew.catch2`) and test functions carrying `@req`, by the gate's own parser.
- THE CALLER WALK uses the repository's existing index (`clew.indexlocate.find_index`), up its
  non-fuzzy `call_edges` at most `VIA_DEPTH` calls, stopping at the first `@req` function on each
  path. With no index nothing is walked, and the change is reported unmapped with that reason.

@brief Covering tests and caller reach for the impact report.
@version 1
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..catch2 import CASE_MACROS, cases_in, named_reqs
from ..testscope import TEST_PATH_FACTS, is_test_path

logger = logging.getLogger(__name__)

## How many calls up the walk goes from a changed function to a `@req` function.
VIA_DEPTH = 3
## Unmapped reasons, as the report states them.
NO_INDEX = "no index to walk callers"
NO_CALLER = f"no @req caller within {VIA_DEPTH} calls"
## Test code implements no requirement, so it is not walked (found running entropic's v2.14.6).
TEST_CODE = "test code"
## The languages whose test files hold Catch2 cases.
_CATCH2_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".h", ".hpp", ".hh")


## @brief One covering test.
#  @version 1.0
#  @utility
@dataclass(frozen=True)
class TestRef:
    __test__ = False  # not a pytest class
    name: str
    file: str


## @brief The tests covering each requirement, read from the test tree.
#  @version 1.0
#  @req REQ-DDB-GUARD-010
#  @param repo_root The repository.
#  @param req_ids The requirements the report names.
#  @param catalog The catalog's ids; a Catch2 tag counts only when it is one.
#  @param files Repo-relative candidate files, or None for every tracked file.
#  @param config The guard configuration (`test_paths`, and the parser's languages).
#  @return {req_id: [TestRef]}, each list in file then line order.
def covering_tests(
    repo_root: Path,
    req_ids: set[str],
    catalog: set[str],
    files: list[str] | None = None,
    config: dict[str, Any] | None = None,
) -> dict[str, list[TestRef]]:
    config = config or {}
    patterns = tuple(config.get("test_paths") or TEST_PATH_FACTS)
    out: dict[str, list[TestRef]] = {}
    for rel in files if files is not None else _tracked(repo_root):
        if not is_test_path(rel, patterns):
            continue
        for req_id, ref in _file_tests(repo_root, rel, catalog, config):
            if req_id in req_ids and ref not in out.setdefault(req_id, []):
                out[req_id].append(ref)
    return out


## @brief The (requirement, test) pairs one test file declares.
#  @version 1.0
#  @utility
#  @return Pairs, Catch2 cases first.
def _file_tests(
    repo_root: Path, rel: str, catalog: set[str], config: dict[str, Any]
) -> list[tuple[str, TestRef]]:
    pairs: list[tuple[str, TestRef]] = []
    path = repo_root / rel
    if rel.lower().endswith(_CATCH2_SUFFIXES):
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            logger.warning("impact: cannot read %s for its test cases: %s", rel, exc)
            lines = []
        for case in cases_in(lines):
            pairs += [(r, TestRef(name=case.title, file=rel)) for r in named_reqs(case, catalog)]
    from .config import parse_source_file

    for func in parse_source_file(str(path), config) or []:
        ## A Catch2 macro the parser reads as a function is the case above, already named.
        if func.name in CASE_MACROS or not func.doxygen:
            continue
        pairs += [(r, TestRef(name=func.name, file=rel)) for r in func.doxygen.tags.get("req", [])]
    return pairs


## @brief Every tracked file, repo-relative.
#  @version 1.0
#  @utility
#  @return Paths; empty when git cannot list them.
def _tracked(repo_root: Path) -> list[str]:
    from .git import run_git

    listed = run_git(["git", "-C", str(repo_root), "ls-files"])
    return [line for line in (listed or "").splitlines() if line]


## @brief The index-backed caller walk, and the covering tests the report attaches.
#  @version 1.0
class Reach:
    ## @brief Hold the index (or None) and, optionally, precomputed covering tests.
    #  @version 1.0
    #  @utility
    #  @param db The repository's index, or None when it has none.
    #  @param tests Covering tests by requirement, or None to read them when asked.
    #  @param repo_root The repository, for reading tests; None reads none.
    #  @param config The guard configuration.
    def __init__(
        self,
        db: Path | None,
        tests: dict[str, list[TestRef]] | None = None,
        repo_root: Path | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        self.db = db
        self.tests = tests
        self.repo_root = repo_root
        self.config = config or {}

    ## @brief The covering tests for these requirements.
    #  @version 1.0
    #  @req REQ-DDB-GUARD-010
    #  @param req_ids The requirements.
    #  @param catalog The catalog's ids.
    #  @return {req_id: [TestRef]}.
    def tests_for(self, req_ids: set[str], catalog: set[str]) -> dict[str, list[TestRef]]:
        if self.tests is None:
            self.tests = (
                covering_tests(self.repo_root, req_ids, catalog, config=self.config)
                if self.repo_root is not None
                else {}
            )
        return self.tests

    ## @brief Whether a changed file is test code, by the gate's test paths.
    #  @version 1.0
    #  @utility
    #  @param file_path The changed file.
    #  @return Bool.
    def is_test(self, file_path: str) -> bool:
        patterns = tuple(self.config.get("test_paths") or TEST_PATH_FACTS)
        return is_test_path(_relative(file_path), patterns)

    ## @brief The requirements a function without `@req` reaches through its callers.
    #  v1.1: rows matched by identity (clew#76)
    #  @version 1.1
    #  @req REQ-DDB-GUARD-010
    #  @param changed The changed function.
    #  @return [(req_id, caller chain ending at the `@req` function)], by requirement id.
    def via(self, changed: Any) -> list[tuple[str, list[str]]]:
        if self.db is None:
            return []
        conn = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            return _walk(conn, _rowids(conn, changed))
        finally:
            conn.close()

    ## @brief The requirements the changed function's own index row carries.
    #  @details The index holds a declaration and its definition as ONE row, so a header
    #  prototype without `@req` gets its definition's tags here (2.2, clew#76).
    #  @version 1.0
    #  @req REQ-DDB-GUARD-010
    #  @param changed The changed function.
    #  @return Requirement ids, sorted; empty with no index or no tagged row.
    def own_reqs(self, changed: Any) -> list[str]:
        if self.db is None:
            return []
        conn = sqlite3.connect(f"file:{self.db}?mode=ro", uri=True)
        try:
            rowids = _rowids(conn, changed)
            marks = ",".join("?" * len(rowids))
            rows = (
                conn.execute(
                    f"SELECT DISTINCT req_id FROM req_edges WHERE memberdef_rowid IN ({marks})",
                    rowids,
                ).fetchall()
                if rowids
                else []
            )
        finally:
            conn.close()
        return sorted(str(r) for (r,) in rows)


## @brief A changed file's path as the index names it.
#  @version 1.0
#  @utility
#  @return The repo-relative POSIX path.
def _relative(file_path: str) -> str:
    path = Path(file_path)
    if path.is_absolute():
        try:
            path = path.relative_to(Path.cwd())
        except ValueError:
            return path.as_posix()
    return path.as_posix().removeprefix("./")


## @brief Walk callers breadth-first to the nearest `@req` functions.
#  v1.1: starts from the matched rows (2.2, clew#76: by identity, either of a row's two files)
#  @version 1.1
#  @utility
#  @return [(req_id, chain)], the first (shortest) chain per requirement.
def _walk(conn: sqlite3.Connection, start: list[int]) -> list[tuple[str, list[str]]]:
    tagged: dict[int, list[str]] = {}
    for rowid, req_id in conn.execute("SELECT memberdef_rowid, req_id FROM req_edges"):
        tagged.setdefault(int(rowid), []).append(str(req_id))
    frontier: list[tuple[int, list[str]]] = [(rowid, []) for rowid in start]
    seen = {rowid for rowid, _ in frontier}
    found: dict[str, list[str]] = {}
    for _ in range(VIA_DEPTH):
        frontier = _step(conn, frontier, seen, tagged, found)
    return sorted(found.items())


## @brief One level of the walk: each frontier function's callers.
#  @version 1.0
#  @utility
#  @return The next frontier (callers that carry no `@req`).
def _step(
    conn: sqlite3.Connection,
    frontier: list[tuple[int, list[str]]],
    seen: set[int],
    tagged: dict[int, list[str]],
    found: dict[str, list[str]],
) -> list[tuple[int, list[str]]]:
    nxt: list[tuple[int, list[str]]] = []
    for rowid, chain in frontier:
        for caller, caller_name in conn.execute(
            "SELECT DISTINCT ce.caller_rowid, m.name FROM call_edges ce "
            "JOIN memberdef m ON m.rowid = ce.caller_rowid "
            "WHERE ce.callee_rowid = ? AND ce.confidence != 'fuzzy' ORDER BY m.name",
            (rowid,),
        ):
            if caller in seen:
                continue
            seen.add(caller)
            path = [*chain, str(caller_name)]
            for req_id in tagged.get(caller, []):
                found.setdefault(req_id, path)
            if caller not in tagged:
                nxt.append((caller, path))
    return nxt


## @brief The index rows for a changed function.
#  v1.1: matched in EITHER of a row's files, its declaration's or its body's, and narrowed by the
#  parser's scope (2.2, clew#76: a header prototype's row has the .cpp as its body file, so
#  `ServerManager::execute` in server_manager.h matched nothing, or a same-named `Other::execute`)
#  @version 1.1
#  @utility
#  @return Rowids: in the changed file and scope, else the one function of that name.
def _rowids(conn: sqlite3.Connection, changed: Any) -> list[int]:
    file_path = _relative(changed.file_path)
    rows = conn.execute(
        "SELECT m.rowid, m.scope, d.name, b.name FROM memberdef m "
        "LEFT JOIN path d ON d.rowid = m.file_id LEFT JOIN path b ON b.rowid = m.bodyfile_id "
        "WHERE m.kind = 'function' AND m.name = ?",
        (changed.name,),
    ).fetchall()
    scope = _scope(getattr(changed, "qualified", None))
    here = [
        int(r)
        for r, row_scope, decl, body in rows
        if file_path in (decl, body) and (scope is None or _same_scope(row_scope, scope))
    ]
    return here or ([int(rows[0][0])] if len(rows) == 1 else [])


## @brief The class or namespace part of the parser's `Scope::name(params)`.
#  @version 1.0
#  @utility
#  @return The scope, or None for an unscoped name.
def _scope(qualified: str | None) -> str | None:
    head = (qualified or "").split("(", 1)[0]
    return head.rsplit("::", 1)[0] if "::" in head else None


## @brief Whether an index row's scope is the parser's, which may omit outer namespaces.
#  v1.1: template arguments are dropped from both (`SessionResidency< Tok >`; entropic, clew#76)
#  @version 1.1
#  @utility
#  @return Bool.
def _same_scope(row_scope: str | None, scope: str) -> bool:
    row, want = _untemplated(str(row_scope or "")), _untemplated(scope)
    return row == want or row.endswith(f"::{want}")


## @brief A scope with every `<...>` argument list removed, nested ones included.
#  @version 1.0
#  @utility
#  @return The bare scope.
def _untemplated(scope: str) -> str:
    out, depth = [], 0
    for ch in scope:
        depth += (ch == "<") - (ch == ">")
        if depth == 0 and ch != ">":
            out.append(ch)
    return "".join(out).replace(" ", "")
