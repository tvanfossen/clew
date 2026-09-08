# SPDX-License-Identifier: MIT
"""gh#23 — a derived sub-index scope did not carry the vendored tree's own ignores.

A sub-index builds through a DECLARED `index_scope`, which the resolver takes at its
word and never walks. That is correct for a human-written `.clew.yaml` — walking would
overrule the author — but a sub-index's declaration is MACHINE-DERIVED by
`derive_sub_indexes`, so nobody ever told it to skip the vendored tree's own `build/`.

The reported symptom: a vendored dependency shipping CMake-generated headers under a
`.gitignore`'d `build/` had `search` resolving symbols into throwaway output rather
than into the tree's real source.

The whole-repo tier never had this problem — `whole_repo_scope` asks git on both sides
of every submodule boundary. The set was already computed and simply was not handed to
the sub-indexes.

@brief Tests for gitignored paths reaching a derived sub-index's excludes.
@version 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from clew.scope import FIRST_PARTY_INDEX, derive_sub_indexes


##
# @brief A repo vendoring one git tree that gitignores its own build output.
# @param tmp_path Pytest temp dir.
# @return The outer repo root.
# @version 1
def _repo(tmp_path: Path) -> Path:
    """REAL GIT TREES, not `.git` directories faked by hand: the ignore lookup runs
    `git check-ignore`, so a fixture without a working repository would report nothing
    ignored and the test would pass against the bug."""
    root = tmp_path / "outer"
    (root / "src").mkdir(parents=True)
    (root / "src" / "a.c").write_text("void a(void) {}\n", encoding="utf-8")

    dep = root / "deps" / "vendored"
    (dep / "src").mkdir(parents=True)
    (dep / "src" / "b.c").write_text("void b(void) {}\n", encoding="utf-8")
    (dep / "build" / "artifact").mkdir(parents=True)
    (dep / "build" / "artifact" / "gen.h").write_text("/* generated */\n", encoding="utf-8")
    (dep / ".gitignore").write_text("build/\n", encoding="utf-8")

    for tree in (dep, root):
        subprocess.run(["git", "init", "-q", "."], cwd=tree, check=True)
        subprocess.run(["git", "add", "-A"], cwd=tree, check=True)
        subprocess.run(
            ["git", "-c", "user.email=t@e", "-c", "user.name=t", "commit", "-qm", "init"],
            cwd=tree,
            check=True,
        )
    return root


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="needs git",
)
def test_a_vendored_sub_index_excludes_its_own_gitignored_build(tmp_path: Path) -> None:
    """THE REPORTED CASE. `deps/vendored/build/` is ignored by the vendored tree's OWN
    `.gitignore`, which `git ls-files` in the parent cannot see through — so it has to be
    asked per tree, which `whole_repo_scope` already does. The sub-index simply was not
    given the answer.
    """
    root = _repo(tmp_path)
    subs = {s.name: s for s in derive_sub_indexes(root)}
    vendored = next(s for name, s in subs.items() if name != FIRST_PARTY_INDEX)

    assert vendored.roots == (root / "deps" / "vendored",)
    assert any(p.name == "build" for p in vendored.excludes), (
        f"the vendored tree's own gitignored build/ is not excluded: {vendored.excludes}"
    )


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="needs git",
)
def test_the_tree_itself_is_never_in_its_own_excludes(tmp_path: Path) -> None:
    """THE SELF-EXCLUSION TRAP. `_under_any` matches equality as well as containment — by
    design, because an exclusion names the directory itself — so a tree that git reports as
    ignored WITHIN ITS PARENT would otherwise exclude its own root and index nothing at all.

    A sub-index whose root is in its own excludes builds an empty database and reports
    success, which is the silent-emptiness failure this project keeps finding.
    """
    root = _repo(tmp_path)
    for sub in derive_sub_indexes(root):
        for tree in sub.roots:
            assert tree not in sub.excludes, f"{sub.name} excludes its own root"


@pytest.mark.skipif(
    subprocess.run(["git", "--version"], capture_output=True).returncode != 0,
    reason="needs git",
)
def test_a_child_trees_ignores_are_not_repeated_on_the_parent(tmp_path: Path) -> None:
    """The parent already excludes the child tree WHOLE, so listing paths inside it again
    adds entries that exclude nothing — and this list becomes doxygen's EXCLUDE, where a
    repository vendoring several large dependencies would otherwise carry every ignored path
    in the tree on every sub-index."""
    root = _repo(tmp_path)
    subs = {s.name: s for s in derive_sub_indexes(root)}
    first = subs[FIRST_PARTY_INDEX]
    dep = root / "deps" / "vendored"

    assert dep in first.excludes, "the parent must still exclude the vendored tree whole"
    inside = [p for p in first.excludes if p != dep and dep in p.parents]
    assert inside == [], f"first-party repeats paths inside an already-excluded tree: {inside}"
