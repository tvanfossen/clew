# SPDX-License-Identifier: MIT
"""A call through an interface is evidence about every implementation of it — and only them.

THE DEFECT, REPRODUCED BEFORE IT WAS FIXED. A method reached only through an interface-typed
property — the shape dependency injection produces — reported `callers: []` AND
`callers_unresolved: 0`. The second number is the damaging one: it is a MEASUREMENT, "we looked
and nothing was refused", while a call site in the repository plainly invokes one of the
implementations.

WHY IT READ ZERO. `_attributable` credits a refused call site only when every candidate is the
SAME identity. With one implementation that holds and the count is 1 — reproduced, and correct.
But injected services routinely have two: the real one and a test double. Two implementations
are two identities, the site is attributable to neither, and both read as never-called.

THE NARROW FIX. The rule exists for a reason its own docstring measured: crediting every
candidate of every refused site qualified 87% of inbound-less functions on entropic, a permanent
banner that trains readers to ignore it, and treats a NAME as evidence of linkage. So candidates
are NOT all credited. They are credited when they form a DISPATCH FAMILY — one member name across
classes sharing a common base — because then the call site genuinely dispatches to one of them.
Same-named methods on UNRELATED classes still refuse; the negative test below pins that.

@brief Tests that interface dispatch is attributed to its implementations, and only them.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cli import _build_argparser, _run_pipeline

_INTERFACE = (
    "export interface UserService { getUser(id: string): string; }\n"
    "export class UserServiceImpl implements UserService {\n"
    "  getUser(id: string): string { return id; }\n}\n"
)
_MOCK = (
    "export class MockUserService implements UserService {\n"
    "  getUser(id: string): string { return 'mock'; }\n}\n"
)
_CONTROLLER = (
    "import { UserService } from './svc';\n"
    "export class Controller {\n"
    "  constructor(private svc: UserService) {}\n"
    "  handle(id: string): string { return this.svc.getUser(id); }\n}\n"
)


## @brief Build a repository and return the unresolved-inbound site count per definition.
## @param tmp_path Pytest temporary directory.
## @param files Relative path to file text.
## @return definition -> sites credited.
## @version 1
def _unresolved(tmp_path: Path, files: dict[str, str]) -> dict[str, int]:
    """@brief Build and read `unresolved_inbound`.
    @return Mapping of function definition to refused-site count.
    @version 1
    """
    repo = tmp_path / "repo"
    for rel, text in files.items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    conn = sqlite3.connect(out)
    rows = conn.execute(
        "SELECT m.definition, u.sites FROM unresolved_inbound u "
        "JOIN memberdef m ON m.rowid = u.callee_rowid"
    )
    return dict(rows)


## @brief One implementation: the refusal is attributed, as it already was.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_single_implementation_is_credited_as_before(tmp_path: Path) -> None:
    """THE CASE THAT ALREADY WORKED, pinned so the fix cannot regress it. The interface's method
    signature is not a `memberdef` function row, so the implementation is the only candidate.

    @brief Single-implementation dispatch reads 1.
    @return None.
    @version 1
    """
    counts = _unresolved(tmp_path, {"src/svc.ts": _INTERFACE, "src/controller.ts": _CONTROLLER})
    assert counts.get("src.svc.UserServiceImpl.getUser") == 1, counts


## @brief Two implementations of one interface are each credited.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_two_implementations_of_one_interface_are_each_credited(tmp_path: Path) -> None:
    """@brief The reproduced defect: both read zero before the fix.
    @return None.
    @version 1
    """
    counts = _unresolved(
        tmp_path,
        {"src/svc.ts": _INTERFACE + _MOCK, "src/controller.ts": _CONTROLLER},
    )
    assert counts.get("src.svc.UserServiceImpl.getUser") == 1, counts
    assert counts.get("src.svc.MockUserService.getUser") == 1, counts


## @brief Same-named methods on unrelated classes are still not credited.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_same_named_methods_on_unrelated_classes_are_not_credited(tmp_path: Path) -> None:
    """THE RULE'S REASON FOR EXISTING, AND WHAT KEEPS THIS FIX NARROW. Two classes that merely
    share a method name are not a dispatch family; a call on an untyped receiver names a NAME,
    and a name is not evidence of linkage. Crediting both is the blanket hedge measured at 87% on
    entropic and withdrawn.

    @brief A shared name alone earns nothing.
    @return None.
    @version 1
    """
    counts = _unresolved(
        tmp_path,
        {
            "src/a.ts": "export class Alpha {\n  getUser(id: string) { return id; }\n}\n",
            "src/b.ts": "export class Beta {\n  getUser(id: string) { return 'b'; }\n}\n",
            "src/use.ts": "export function run(x: any) { return x.getUser('a'); }\n",
        },
    )
    assert "src.a.Alpha.getUser" not in counts, counts
    assert "src.b.Beta.getUser" not in counts, counts
