# SPDX-License-Identifier: MIT
"""An unreadable directory in the tree is skipped, never fatal (#72 bug 1, 2.1).

FOUND BY AN ADOPTER (#72, 2026-11-23): a device log pulled under a gitignored path, mode 0644 (no
search bit), raised PermissionError from `scope._holds_git_tree` while
`external.stamp_external_provenance` walked the tree, and the whole index failed.

@brief Tests the nested-tree walk over an unreadable directory.
@version 1
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clew import scope


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root reads every directory, so nothing is unreadable"
)
def test_an_unreadable_directory_is_skipped_by_the_nested_tree_walk(tmp_path: Path) -> None:
    """@brief No PermissionError; a real nested clone beside it is still found."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "vendor" / "lib" / ".git").mkdir(parents=True)
    locked = root / "logs" / "device"
    locked.mkdir(parents=True)
    (locked / "dump.txt").write_text("x")
    os.chmod(locked, 0o644)
    try:
        found = scope.nested_repo_roots(root)
    finally:
        os.chmod(locked, 0o755)
    assert root / "vendor" / "lib" in [Path(p) for p in found]


@pytest.mark.skipif(
    os.geteuid() == 0, reason="root reads every directory, so nothing is unreadable"
)
def test_the_git_tree_probe_answers_no_for_an_unreadable_directory(tmp_path: Path) -> None:
    """@brief "Is there a separate git tree here?" — on a directory that cannot be searched, no."""
    locked = tmp_path / "locked"
    locked.mkdir()
    os.chmod(locked, 0o644)
    try:
        assert scope._holds_git_tree(locked) is False
    finally:
        os.chmod(locked, 0o755)
