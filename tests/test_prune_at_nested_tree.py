# SPDX-License-Identifier: MIT
"""gh#36 — the whole-repo scope walk descends a vendored tree it will never prune usefully.

MEASURED on a repository vendoring nine submodules (boost 641 MB, opencv 217 MB, pcl 142 MB):
`resolve` cost ~24.6 s on EVERY build, full or incremental, while every other stage totalled a
few hundred ms.

    forced full rebuild   resolve 24804 ms   doxygen 25470 ms   total 56383 ms
    incremental, 7 files  resolve 24583 ms   doxygen  3695 ms   total 33768 ms

c8cfb2b (gh#24) deduplicated the nested-tree walk and `scope_provenance` fell from ~24 s to
~33 ms, so the cache works. What remained is a DIFFERENT walk: `_pruned_dirs`, collecting the
dot and cache directories the whole-repo scope must exclude. It descends into every nested
tree, so it reads all of boost to find `libs/*/.github` and `.drone` — and prints both
`boost/libs/spirit/.../lexer/parser/{tree,tokeniser}` depth-limit warnings on every build.
The vendored sub-indexes show what the number should look like: `deps-tinyfsm` resolve 64 ms,
`deps-libBissellIoT` 924 ms.

WHY IT DESCENDED, AND WHY THAT REASON EXPIRED. gh#333 made this walk enter nested trees
deliberately: the whole-repo tier INDEXES a nested tree and tags its rows, so its `.git`
object store and caches were the one part of the tree nothing pruned. That still holds for the
tree's OWN top-level dot directories, and it is why this prunes them explicitly rather than
simply stopping. It does not hold for `.github` eleven levels down inside a vendored library:
doxygen would skip those by file pattern anyway, they are 390-odd of the exclude entries that
overflowed a client's reply limit (gh#37), and reaching them costs the whole 641 MB.

@brief Tests that the whole-repo scope walk stops at a nested git tree.
@version 1
"""

from __future__ import annotations

from pathlib import Path


##
# @brief A repo whose vendored trees hide dot-directories several levels down.
# @param root Directory to build in.
# @return (repo root, submodule-style tree, clone-style tree, the deep dot-dir).
# @version 1
def _repo_with_deep_vendored_dots(root: Path) -> tuple[Path, Path, Path, Path]:
    """BOTH ON-DISK SHAPES OF A NESTED REPOSITORY, because they prune differently and only one
    of them was ever the case this walk handled. A submodule's `.git` is a FILE, so there is no
    `.git` directory to collect and the walk's only reason to enter is the tree's other dot
    directories; a clone's `.git` IS a directory and must still be excluded.

    @brief Build both nested shapes plus a deep dot-dir.
    @return (repo, submodule tree, clone tree, deep dot-dir).
    @version 1
    """
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    submodule = root / "deps" / "boost"
    (submodule / "libs" / "spirit" / "test").mkdir(parents=True)
    (submodule / ".git").write_text("gitdir: ../../.git/modules/boost\n", encoding="utf-8")
    ## The nested tree's OWN cache directory, at its top level — still pruned, per gh#333.
    (submodule / ".cache").mkdir()
    ## And one buried deep inside it, which is what the walk used to read 641 MB to find.
    deep = submodule / "libs" / "spirit" / "test" / ".github"
    deep.mkdir(parents=True)
    clone = root / "deps" / "opencv"
    (clone / ".git" / "objects").mkdir(parents=True)
    (clone / "modules").mkdir()
    return root.resolve(), submodule.resolve(), clone.resolve(), deep.resolve()


def test_the_walk_does_not_descend_a_nested_tree(tmp_path: Path) -> None:
    """THE COST IS THE DESCENT, so the assertion is about what the walk never reached. A
    dot-directory buried inside a vendored tree can only appear in the exclude list if the walk
    read the whole tree to find it — which is the 24.6 s.

    @brief A deep dot-dir inside a nested tree is not collected.
    @return None.
    @version 1
    """
    from clew.scope import whole_repo_scope

    repo, _sub, _clone, deep = _repo_with_deep_vendored_dots(tmp_path / "repo")
    excludes = {p.resolve() for p in whole_repo_scope(repo).excludes}

    assert deep not in excludes, (
        "a dot-dir this deep inside a vendored tree means the walk descended it — the whole "
        "641 MB, on every build"
    )


def test_a_nested_trees_own_top_level_dot_dirs_are_still_pruned(tmp_path: Path) -> None:
    """gh#333's REASON, PRESERVED. The whole-repo tier indexes a nested tree, so its `.git`
    object store and its caches must still reach doxygen as excludes — otherwise stopping at
    the boundary would hand doxygen the one directory nothing else prunes.

    @brief The nested tree's own `.git` and `.cache` are excluded without descending it.
    @return None.
    @version 1
    """
    from clew.scope import whole_repo_scope

    repo, submodule, clone, _deep = _repo_with_deep_vendored_dots(tmp_path / "repo")
    excludes = {p.resolve() for p in whole_repo_scope(repo).excludes}

    assert submodule / ".cache" in excludes, "the nested tree's own cache dir must still be pruned"
    assert clone / ".git" in excludes, (
        "a nested CLONE's `.git` IS a directory and is the one thing nothing else prunes — "
        "stopping the walk must not stop excluding it"
    )


def test_the_nested_tree_itself_is_still_in_scope(tmp_path: Path) -> None:
    """THE CONTROL THAT KEEPS gh#333. Pruning the WALK must not exclude the TREE: the whole-repo
    tier indexes a vendored dependency and tags its rows, and a `chain_trace` that stopped at the
    submodule boundary is the defect gh#333 fixed. Stopping the walk is a statement about cost,
    not about what belongs in the index.

    @brief The vendored tree is not itself excluded.
    @return None.
    @version 1
    """
    from clew.scope import whole_repo_scope

    repo, submodule, clone, _deep = _repo_with_deep_vendored_dots(tmp_path / "repo")
    scope = whole_repo_scope(repo)
    excludes = {p.resolve() for p in scope.excludes}

    assert submodule not in excludes, "the whole-repo tier indexes nested trees (gh#333)"
    assert clone not in excludes, "a nested clone is indexed and tagged, not excluded"
    assert scope.roots == (repo,)


def test_first_party_code_beside_the_vendored_tree_is_still_walked(tmp_path: Path) -> None:
    """PRUNING ONE BRANCH IS NOT PRUNING THE WALK. First-party dot-directories at any depth
    must still be collected — they are the ones this function exists for, and a fix that
    stopped early everywhere would silently hand doxygen the parent's own caches.

    @brief A deep first-party dot-dir is still collected.
    @return None.
    @version 1
    """
    from clew.scope import whole_repo_scope

    repo, _sub, _clone, _deep = _repo_with_deep_vendored_dots(tmp_path / "repo")
    own = repo / "app" / "generated" / "__pycache__"
    own.mkdir(parents=True)

    excludes = {p.resolve() for p in whole_repo_scope(repo).excludes}
    assert own.resolve() in excludes, "a first-party cache dir must still be pruned"
