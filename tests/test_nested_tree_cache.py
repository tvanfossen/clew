# SPDX-License-Identifier: MIT
"""gh#24 — the nested-tree walk ran repeatedly inside one build.

`nested_repo_roots` answers "which directories under this root are separate git
trees". Three callers need it — descent exclusion, dependency ownership, and the
sub-index split — and none was given another's answer. Measured on a two-file fixture
with one nested tree, a single CLI build called the underlying walk FOUR times on the
same root; the reporter measured the resolve stage at ~24s on a real repo with
vendored submodules, dominating a refresh whose other stages total a few hundred ms.

SCOPED TO A BUILD, NOT TO THE PROCESS, and that is the whole design. The answer is
filesystem state: a submodule added or removed while a long-lived MCP server runs
would make a process-lifetime cache serve a stale SCOPE, and scope decides what gets
indexed at all. Outside a build the cache is inert and every call walks, which is the
behaviour that existed before it.

@brief Tests for the per-build nested-tree cache.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import clew.scope as scope


##
# @brief A repo root with one nested git tree.
# @param tmp_path Pytest temp dir.
# @return The outer root.
# @version 1
def _nested(tmp_path: Path) -> Path:
    """@brief Build a root containing a second git tree."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "vendor" / "dep" / ".git").mkdir(parents=True)
    return root


def test_the_walk_runs_once_per_root_inside_the_cache(tmp_path: Path, monkeypatch) -> None:
    """Four callers, one walk. The cache is keyed by RESOLVED root, so two callers naming
    the same tree differently still share the answer."""
    root = _nested(tmp_path)
    calls: list[Path] = []
    real = scope._nested_repos_under
    monkeypatch.setattr(scope, "_nested_repos_under", lambda r: calls.append(r) or real(r))

    with scope.nested_tree_cache():
        first = scope.nested_repo_roots(root)
        scope.nested_repo_roots(root)
        scope.nested_repo_roots(Path(str(root) + "/."))

    assert len(calls) == 1, f"the walk ran {len(calls)} times inside one build"
    assert [p.name for p in first] == ["dep"]


def test_outside_the_cache_every_call_walks(tmp_path: Path, monkeypatch) -> None:
    """THE STALENESS GUARD, asserted rather than assumed. The cache must not outlive the
    build that opened it: `nested_repo_roots` answers filesystem state, and a submodule
    added while a long-lived server runs would otherwise serve a stale SCOPE — which
    decides what is indexed at all, so the cost of being wrong is not a slow build but a
    wrong one.
    """
    root = _nested(tmp_path)
    calls: list[Path] = []
    real = scope._nested_repos_under
    monkeypatch.setattr(scope, "_nested_repos_under", lambda r: calls.append(r) or real(r))

    scope.nested_repo_roots(root)
    scope.nested_repo_roots(root)
    assert len(calls) == 2, "outside a build the walk must not be memoised"


def test_the_cache_sees_a_tree_added_between_builds(tmp_path: Path) -> None:
    """The behavioural form of the guard above: two builds, a nested tree appearing
    between them, and the second build must see it. A process-lifetime cache passes the
    call-count test and fails this one."""
    root = _nested(tmp_path)
    with scope.nested_tree_cache():
        before = scope.nested_repo_roots(root)
    (root / "vendor" / "extra" / ".git").mkdir(parents=True)
    with scope.nested_tree_cache():
        after = scope.nested_repo_roots(root)

    assert {p.name for p in before} == {"dep"}
    assert {p.name for p in after} == {"dep", "extra"}, (
        "the second build did not see a tree added after the first — the cache outlived its build"
    )


def test_nesting_the_cache_is_a_no_op_and_the_outermost_owns_it(tmp_path: Path) -> None:
    """`build_index` opens one, and a caller that already opened its own must not have the
    inner exit clear it out from under the rest of the build. The outermost owns the
    lifetime; an inner activation is inert."""
    root = _nested(tmp_path)
    with scope.nested_tree_cache():
        scope.nested_repo_roots(root)
        with scope.nested_tree_cache():
            scope.nested_repo_roots(root)
        assert scope._NESTED_CACHE is not None, "the inner exit cleared the outer cache"
    assert scope._NESTED_CACHE is None, "the outermost exit must clear it"
