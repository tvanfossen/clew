# SPDX-License-Identifier: MIT
"""Tests for the index-cache tree scan: pruning must not change what is scanned.

A warm refresh is sized by the WALK, not by the hash — `size + mtime_ns` lets an
unchanged file skip re-hashing, so a refresh that reprocesses nothing still paid
to enumerate every path under the INPUT roots and test each one against the
EXCLUDE list. At the whole-repo scope tier that means walking `.git`, `.venv` and
build output in full only to discard them.

`_files_under` prunes an excluded directory during descent instead. The saving is
only legitimate if the surviving set is untouched, so the assertions here are
about the SET first and the mechanism second:

  * the pruned enumeration equals an enumerate-then-filter reference, which is
    the algorithm it replaces;
  * a non-source file under INPUT is still enumerated and still moves the tree
    hash. `enumerate_tree` is deliberately not extension-filtered, and a filter
    is exactly the plausible "optimisation" these tests exist to refuse.

@brief Tests for excluded-subtree pruning in the tree scan.
@version 1
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clew import treescan as ts
from clew.indexcache import IndexCache


## @brief Create a file (and its parent directories) with some content.
## @version 1
def _write_scan_file(path: Path, content: str = "int x;\n") -> None:
    """@brief Write a fixture file, creating parents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


## @brief The INPUT/EXCLUDE roots of the synthetic fixture, writing nothing.
## @param root Fixture repo root.
## @return (input roots, exclude roots) for enumerate_tree.
## @version 1
def _scan_tree_scope(root: Path) -> tuple[list[Path], list[Path]]:
    """Kept separate from `_make_scan_tree` so a test can edit a fixture file and
    then re-scan. Deriving the scope used to re-materialise the tree, which
    silently reverted the edit under test and made an invalidation assertion
    compare a file against itself.

    @brief Fixture roots and excludes.
    @version 1
    """
    return [root], [root / "vendored", root / ".cache"]


## @brief Build a synthetic repo holding source, non-source and excluded files.
## @param root Directory to populate.
## @return (input roots, exclude roots) for enumerate_tree.
## @version 2
def _make_scan_tree(root: Path) -> tuple[list[Path], list[Path]]:
    """A shape that exercises every branch: a source file, several non-source
    files doxygen may still read, and two excluded subtrees holding both.

    @brief Materialise the synthetic scan fixture.
    @version 2
    """
    _write_scan_file(root / "src" / "engine.c")
    _write_scan_file(root / "src" / "engine.h")
    _write_scan_file(root / "src" / "snippet.txt", "example text\n")
    _write_scan_file(root / "Doxyfile", "INPUT = src\n")
    _write_scan_file(root / ".doxygen-guard.yaml", "validate: {}\n")
    _write_scan_file(root / "vendored" / "blob.c")
    _write_scan_file(root / "vendored" / "deep" / "nested" / "more.c")
    _write_scan_file(root / ".cache" / "junk.json", "{}\n")
    return _scan_tree_scope(root)


## @brief Enumerate-then-filter: the algorithm pruning replaces.
## @return Same mapping shape as enumerate_tree.
## @version 1
def _reference_enumerate(
    roots: list[Path],
    excludes: list[Path],
    repo_root: Path,
) -> dict[str, Path]:
    """Walk each root in full and drop excluded paths afterwards. Kept here as an
    independent oracle so the optimisation is pinned against the behaviour it
    claims to preserve rather than against itself.

    @brief Unpruned reference enumeration.
    @version 1
    """
    found: dict[str, Path] = {}
    for root in roots:
        if root.is_file():
            candidates = [root]
        elif root.is_dir():
            candidates = [p for p in root.rglob("*") if p.is_file()]
        else:
            candidates = []
        for path in candidates:
            if ts._is_excluded(path, excludes):
                continue
            found[ts.rel_key(path, repo_root)] = path
    return found


## @brief The pruned scan returns exactly the unpruned scan's surviving set.
## @version 1
def test_pruned_enumeration_matches_unpruned_reference(tmp_path: Path) -> None:
    """@brief Pruning changes cost, never membership."""
    roots, excludes = _make_scan_tree(tmp_path)
    assert ts.enumerate_tree(roots, excludes, tmp_path) == _reference_enumerate(
        roots, excludes, tmp_path
    )


## @brief An excluded directory is never descended into.
## @version 1
def test_excluded_subtree_is_never_visited(tmp_path: Path, monkeypatch) -> None:
    """The STRUCTURAL half. Equal output sets would also hold for
    enumerate-then-filter, so membership alone cannot show the walk got smaller;
    this records every directory the walk actually yielded.

    @brief Assert the walk skips excluded subtrees outright.
    @version 1
    """
    roots, excludes = _make_scan_tree(tmp_path)
    visited: list[str] = []
    real_walk = os.walk

    def spy(top, **kwargs):
        for dirpath, dirnames, filenames in real_walk(top, **kwargs):
            visited.append(dirpath)
            yield dirpath, dirnames, filenames

    monkeypatch.setattr(ts.os, "walk", spy)
    ts.enumerate_tree(roots, excludes, tmp_path)

    assert str(tmp_path / "src") in visited
    assert str(tmp_path / "vendored") not in visited
    assert str(tmp_path / "vendored" / "deep") not in visited
    assert str(tmp_path / ".cache") not in visited


## @brief A non-source file under INPUT is still enumerated.
## @version 1
@pytest.mark.parametrize("name", ["src/snippet.txt", "Doxyfile", ".doxygen-guard.yaml"])
def test_non_source_files_are_enumerated(tmp_path: Path, name: str) -> None:
    """The scan is deliberately NOT extension-filtered. A filter is the obvious
    way to make this walk cheaper and it would drop exactly these paths.

    @brief Non-source files stay in the scanned set.
    @version 1
    """
    roots, excludes = _make_scan_tree(tmp_path)
    assert name in ts.enumerate_tree(roots, excludes, tmp_path)


## @brief A root whose own ancestor is excluded contributes nothing.
## @version 1
def test_root_under_an_exclude_contributes_nothing(tmp_path: Path) -> None:
    """Pruning starts AT the root, so an exclude above the root would be invisible
    to the descent unless the root itself is tested.

    @brief Exclusion above an INPUT root still applies.
    @version 1
    """
    _write_scan_file(tmp_path / "src" / "engine.c")
    assert ts.enumerate_tree([tmp_path / "src"], [tmp_path], tmp_path) == {}


## @brief An exclude naming a single FILE drops just that file.
## @version 1
def test_exclude_naming_a_file_is_honoured(tmp_path: Path) -> None:
    """@brief A file-valued EXCLUDE entry is matched exactly."""
    _write_scan_file(tmp_path / "src" / "engine.c")
    _write_scan_file(tmp_path / "src" / "generated.c")
    found = ts.enumerate_tree([tmp_path], [tmp_path / "src" / "generated.c"], tmp_path)
    assert "src/engine.c" in found
    assert "src/generated.c" not in found


## @brief Tree hash for one scan of an already-materialised fixture repo.
## @return The cache's tree_sha over the enumerated set.
## @version 2
def _tree_sha(tmp_path: Path, cache_path: Path) -> str:
    """@brief Scan the fixture and hash it."""
    roots, excludes = _scan_tree_scope(tmp_path)
    cache = IndexCache(cache_path, tmp_path)
    try:
        cache.scan(ts.enumerate_tree(roots, excludes, tmp_path))
        return cache.tree_sha("DOXYFILE-CONTENT", [])
    finally:
        cache.close()


## @brief Editing any scanned file — source or not — moves the doxygen cache key.
## @version 1
@pytest.mark.parametrize("name", ["src/engine.c", "src/snippet.txt", ".doxygen-guard.yaml"])
def test_editing_a_scanned_file_invalidates_the_tree_hash(tmp_path: Path, name: str) -> None:
    """A faster scan that misses an invalidation is worse than a slow one. The
    non-source cases are the ones an extension filter would break: the tree hash
    gates whether doxygen is re-run at all, so a missed change ships a database
    describing content that no longer exists.

    @brief Tree hash responds to every scanned file.
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_scan_tree(repo)
    cache_path = tmp_path / "c.idxcache"
    before = _tree_sha(repo, cache_path)
    (repo / name).write_text("CHANGED CONTENT\n", encoding="utf-8")
    assert _tree_sha(repo, cache_path) != before


## @brief An unchanged tree keeps its hash, so a warm refresh still hits.
## @version 1
def test_unchanged_tree_keeps_its_hash(tmp_path: Path) -> None:
    """The other half of the invalidation contract — without this, "always
    invalidate" would pass every test above while destroying the cache.

    @brief Stable hash across two scans of identical content.
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_scan_tree(repo)
    cache_path = tmp_path / "c.idxcache"
    assert _tree_sha(repo, cache_path) == _tree_sha(repo, cache_path)


## @brief A file appearing inside an excluded subtree does not move the hash.
## @version 1
def test_excluded_file_does_not_move_the_hash(tmp_path: Path) -> None:
    """@brief Excluded content stays out of the cache key."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _make_scan_tree(repo)
    cache_path = tmp_path / "c.idxcache"
    before = _tree_sha(repo, cache_path)
    _write_scan_file(repo / "vendored" / "late.c", "int late;\n")
    assert _tree_sha(repo, cache_path) == before
