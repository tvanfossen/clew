# SPDX-License-Identifier: MIT
"""A first-party refresh walks first-party code, and walks it once.

gh#48 set the bar: "any refresh after first should be incremental, <10s nominally". Profiled on
sassafras-class, one first-party refresh called `derive_sub_indexes` FOUR times,
`whole_repo_scope` six times, `_nested_repos_under` 25 times and `git ls-files` 72 times.
`derive_sub_indexes` recurses INTO every vendored tree to find the trees nested inside it. On
the gh#48 reporter's repository that recursion covers boost, opencv and pcl, and one pass was
measured at 24.6 s. Four passes put a refresh over a minute before doxygen starts.

A first-party build needs none of that recursion. Its scope is the repository minus its DIRECT
nested trees, plus its own git ignores, and both come from a walk that stops at every nested
boundary.

@brief Tests that a first-party refresh never walks inside a vendored tree.
@version 1
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="the MCP SDK is a REQUIRED dependency")

from clew import scope
from clew.mcp_server import state as st
from clew.mcp_server.server import build_server
from clew.scope import FIRST_PARTY_INDEX, derive_sub_indexes

needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="needs git")


## @brief Initialise and commit one git tree.
## @param tree Directory to make a repository.
## @return None.
## @version 1
def _commit(tree: Path) -> None:
    """@brief Make a committed git tree. @version 1"""
    subprocess.run(["git", "init", "-q", "."], cwd=tree, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init"],
        cwd=tree,
        check=True,
    )


## @brief A repository shaped like the reporter's: vendored trees that vendor more trees.
## @param tmp_path Pytest temp dir.
## @return The repository root.
## @version 1
def _nested_split_repo(tmp_path: Path) -> Path:
    """Depth-2 nesting (`deps/slam/third_party/boost`), a second depth-1 tree, a root gitignore,
    a gitignored FetchContent-style clone under `build/`, and a vendored tree's own ignore.
    Every input `derive_sub_indexes` reads is present, so an equivalence that holds here
    holds for every rule it applies.

    @brief Build a nested split repository.
    @version 1
    """
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.c").write_text("/** @brief app. */\nint app(void) { return 0; }\n")
    (root / "build" / "_deps" / "catch2-src").mkdir(parents=True)
    (root / "build" / "_deps" / "catch2-src" / "c.h").write_text("/* fetched */\n")
    (root / "notes.tmp").write_text("scratch\n")
    (root / ".gitignore").write_text("build/\n*.tmp\n")
    boost = root / "deps" / "slam" / "third_party" / "boost"
    boost.mkdir(parents=True)
    (boost / "b.h").write_text("int boost_fn(void);\n")
    (root / "deps" / "slam" / "slam.c").write_text("int slam_fn(void) { return 0; }\n")
    (root / "deps" / "slam" / "out").mkdir()
    (root / "deps" / "slam" / "out" / "gen.c").write_text("/* generated */\n")
    (root / "deps" / "slam" / ".gitignore").write_text("out/\n")
    tiny = root / "deps" / "tinyfsm"
    tiny.mkdir(parents=True)
    (tiny / "fsm.h").write_text("int fsm(void);\n")
    for tree in (
        root / "build" / "_deps" / "catch2-src",
        boost,
        root / "deps" / "slam",
        tiny,
        root,
    ):
        _commit(tree)
    return root.resolve()


@needs_git
def test_the_cheap_first_party_split_equals_the_derived_one(tmp_path: Path) -> None:
    """THE EQUIVALENCE THE SHORTCUT RESTS ON. If `first_party_sub_index` and
    `derive_sub_indexes(...)[0]` ever disagree, a refresh indexes a different first-party scope
    from the one the full split names. That is a wrong index, not a slow one.

    @brief first_party_sub_index matches derive_sub_indexes' first-party entry exactly.
    @version 1
    """
    root = _nested_split_repo(tmp_path)

    derived = derive_sub_indexes(root)
    assert [s.name for s in derived][0] == FIRST_PARTY_INDEX
    assert scope.first_party_sub_index(root) == derived[0]

    plain = tmp_path / "plain"
    plain.mkdir()
    (plain / "a.c").write_text("int a(void) { return 0; }\n")
    _commit(plain)
    assert scope.first_party_sub_index(plain) is None, (
        "an unsplit repository has no first-party part"
    )


@needs_git
@pytest.mark.skipif(shutil.which("doxygen") is None, reason="asserted against a real build")
def test_a_first_party_refresh_never_walks_inside_a_vendored_tree(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE COST, PINNED STRUCTURALLY. Timing a small fixture proves nothing about boost, but the
    walk roots do: a first-party refresh that lists a directory under `deps/` as a walk root has
    paid for a vendored tree's size. Also asserted: the repository root is walked once per
    refresh, not once per question asked of it.

    @brief A first-party build walks no vendored tree, derives no full split, and walks root once.
    @version 1
    """
    root = _nested_split_repo(tmp_path)
    registry = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(registry)
    first_party = registry.register(root, FIRST_PARTY_INDEX)
    registry.note_derived(str(root), tuple(s.name for s in derive_sub_indexes(root)))

    walked: list[Path] = []
    derives: list[Path] = []
    real_walk, real_derive = scope._nested_repos_under, scope.derive_sub_indexes

    def _walk(input_root: Path) -> list[Path]:
        walked.append(Path(input_root))
        return real_walk(input_root)

    def _derive(repo_root: Path) -> list[scope.SubIndex]:
        derives.append(Path(repo_root))
        return real_derive(repo_root)

    monkeypatch.setattr(scope, "_nested_repos_under", _walk)
    monkeypatch.setattr(scope, "derive_sub_indexes", _derive)

    outcome = state._run_build(first_party, None, "from-guard", None, None, False)

    assert outcome.get("ok"), outcome
    vendored = [p for p in walked if p != root and (root / "deps") in (p, *p.parents)]
    assert vendored == [], f"a first-party refresh walked vendored trees: {vendored}"
    assert derives == [], f"a first-party refresh derived the full split {len(derives)} time(s)"
    assert walked.count(root) == 1, f"the root was walked {walked.count(root)} times, not once"
