# SPDX-License-Identifier: MIT
"""Deriving the sub-index split from the nested git trees a repo already contains.

WHY DERIVED RATHER THAN DECLARED. A repo that vendors dependencies as submodules should not have
to write configuration before it can build in reasonable time — and clew already walks for nested
trees on every build (`nested_repo_roots`), so the boundaries are a fact it has and discards. A
declaration overrides the derivation; it is not the price of entry.

THE FIXTURE BUILDS BOTH SHAPES OF NESTED TREE, DELIBERATELY. This project has already been bitten
by exactly one fixture mistake here, recorded in its own lessons: `git submodule` writes a 44-byte
`gitdir:` POINTER FILE where a plain clone has a `.git` DIRECTORY, and a detector testing only
`".git" in dirnames` finds nested CLONES while silently skipping every SUBMODULE. Every unit
fixture at the time built a directory, so the suite was structurally incapable of catching it —
the fixture matched the detector rather than the world. Submodules are the case this feature
exists for, so a fixture that only built directories would be testing the wrong repository shape.

@brief Tests for deriving sub-index boundaries from nested git trees.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.scope import FIRST_PARTY_INDEX, derive_sub_indexes


## @brief Create a nested repository, as either a clone or a submodule.
## @param root Directory to become a nested tree.
## @param as_pointer True to write a `gitdir:` file (submodule), False for a directory (clone).
## @return The nested root.
## @version 1
def _nested(root: Path, as_pointer: bool) -> Path:
    """@brief Build one nested git tree in either on-disk shape.
    @return The directory that is now a nested repository.
    @version 1
    """
    root.mkdir(parents=True, exist_ok=True)
    (root / "src.c").write_text("int nested(void) { return 1; }\n", encoding="utf-8")
    if as_pointer:
        (root / ".git").write_text("gitdir: ../../.git/modules/dep\n", encoding="utf-8")
    else:
        (root / ".git").mkdir()
    return root


## @brief A repo with no nested trees is not split at all.
## @version 1
def test_a_repo_without_nested_trees_is_not_split(tmp_path: Path) -> None:
    """THE COMPATIBILITY CASE, and the reason the return is a LIST rather than always at least
    one entry: a repository with nothing vendored must keep building exactly as it does today,
    to one index, with no new slug and no migration. An empty result says "do not split" without
    the caller needing to compare counts.

    @brief No nested trees means no sub-indexes.
    @version 1
    """
    repo = tmp_path / "plain"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.c").write_text("int main(void){return 0;}\n", encoding="utf-8")

    assert derive_sub_indexes(repo) == [], (
        "a repo with nothing vendored was split, which would give every existing target a new "
        "slug and strand its index"
    )


## @brief Both nested-tree shapes are found, and first-party excludes them.
## @version 1
def test_submodules_and_clones_both_become_sub_indexes(tmp_path: Path) -> None:
    """THE POINTER-FILE HALF IS THE ONE THAT MATTERS. A submodule's `.git` is a FILE, and a
    fixture built only from directories would pass against a detector blind to exactly the case
    this feature exists for.

    First-party is asserted to exclude BOTH trees, because that is what makes its build small —
    a split whose first-party index still walks the vendored trees has done nothing.

    @brief Clones and submodules both split out; first-party excludes them.
    @version 1
    """
    repo = tmp_path / "vendored"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
    clone = _nested(repo / "extern" / "cloned", as_pointer=False)
    submodule = _nested(repo / "deps" / "submoduled", as_pointer=True)

    split = derive_sub_indexes(repo)
    by_name = {s.name: s for s in split}

    assert FIRST_PARTY_INDEX in by_name, f"no first-party sub-index in {sorted(by_name)}"
    assert len(split) == 3, f"expected first-party plus two trees, got {sorted(by_name)}"

    first = by_name[FIRST_PARTY_INDEX]
    assert set(first.excludes) == {clone.resolve(), submodule.resolve()}, (
        f"first-party does not exclude both nested trees: {first.excludes}"
    )
    assert first.roots == (repo.resolve(),)

    ## Each nested tree is its own index, rooted at itself and excluding nothing.
    vendored = [s for s in split if s.name != FIRST_PARTY_INDEX]
    assert {s.roots[0] for s in vendored} == {clone.resolve(), submodule.resolve()}
    assert all(s.excludes == () for s in vendored)


## @brief Names are unique, stable and safe as directory components.
## @version 1
def test_names_are_unique_stable_and_path_safe(tmp_path: Path) -> None:
    """The name becomes a slug component and therefore a directory name, and two trees whose
    basenames collide — `a/dep` and `b/dep` — must not land on one database. Derived from the
    repo-relative PATH rather than the basename for that reason.

    Stability matters as much as uniqueness: nothing persists the name-to-database mapping, so
    the derivation IS the mapping, exactly as it is for the unnamed slug.

    @brief Distinct trees get distinct, repeatable names.
    @version 1
    """
    repo = tmp_path / "collide"
    (repo / "app").mkdir(parents=True)
    _nested(repo / "a" / "dep", as_pointer=True)
    _nested(repo / "b" / "dep", as_pointer=False)

    split = derive_sub_indexes(repo)
    names = [s.name for s in split]
    assert len(names) == len(set(names)), f"names collided: {names}"
    assert names == [s.name for s in derive_sub_indexes(repo)], "derivation is not stable"
    for name in names:
        assert "/" not in name and not name.startswith("."), f"unsafe name: {name!r}"


## @brief Nested trees the repository ignores are not split out.
## @param tmp_path Pytest temp dir.
## @return None.
## @version 1
def test_ignored_nested_trees_are_not_sub_indexes(tmp_path: Path) -> None:
    """FOUND BY DRIVING THE PRODUCT, NOT BY A FIXTURE. Every test above passed while the
    derivation happily split out CMake FetchContent output — `build/_deps/catch2-src`,
    `build/_deps/httplib-src` and six more — because each is a real git clone and
    `nested_repo_roots` walks the whole tree. A real build spent twenty minutes indexing
    throwaway artefacts before it was stopped.

    THE RULE MUST BE THE BUILD'S OWN RULE. `whole_repo_scope` already excludes what git ignores,
    so a tree the build would never index must not become an index of its own — otherwise the
    split and the build disagree about what the repository contains, and the split is the one
    nobody checked. Reused rather than re-derived for exactly that reason.

    This fixture needs a real git repository, because the rule is git's: a `.gitignore` means
    nothing without one, and a test that skipped `git init` would assert against an empty ignore
    list and pass no matter what the code did.

    @brief A nested tree under an ignored path is left out of the split.
    @version 1
    """
    import subprocess

    repo = tmp_path / "withbuild"
    (repo / "app").mkdir(parents=True)
    (repo / "app" / "main.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)

    ## A genuinely vendored dependency: tracked, and worth its own index.
    vendored = _nested(repo / "extern" / "dep", as_pointer=True)
    ## Build output that merely happens to be a clone: ignored, and worth nothing.
    _nested(repo / "build" / "_deps" / "catch2-src", as_pointer=False)

    names = {s.name for s in derive_sub_indexes(repo)}
    assert "extern-dep" in names, "the real vendored dependency was dropped from the split"
    assert not any("catch2" in n or n.startswith("build") for n in names), (
        f"an ignored build artefact became a sub-index: {sorted(names)} — the split must use the "
        "same rule the build uses, or it indexes trees the build would never touch"
    )
    assert vendored.exists()
