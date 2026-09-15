# SPDX-License-Identifier: MIT
"""A stated `index_scope` survives the next build that states nothing.

MEASURED ON RIOT while sizing gh#48's background refresh. The index had been built with a tier-1
`index_scope` of fifteen roots — 1,141 files. A plain refresh, the exact call an automatic refresh
makes, read no statement, derived the WHOLE repository instead — 14,711 candidate files — and ran
doxygen over it until doxygen exited 2. Had doxygen succeeded, the refresh would have replaced a
deliberately narrowed index with a different one and reported success.

Every other tier-1 statement is replayed (`_replay_manifest_statements`, gh#364), and
`options.index_scope.explicit` was already recorded. It was not READ BACK because scope is resolved
before the replay runs: the record sat in the database, one function too late.

A background refresh makes this the common case rather than an operator's mistake, which is why it
has to be fixed before that loop exists.

@brief A tier-1 index_scope statement is replayed by a later plain build.
@version 1
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from clew.query._common import meta_section


## @brief A repository with two top-level trees, one of which a statement narrows away.
## @param root Directory to populate.
## @return The repository root.
## @version 1
def _two_tree_repo(root: Path) -> Path:
    """@brief Build a two-tree repository. @return The root. @version 1"""
    for tree, name in (("kept", "kept_fn"), ("dropped", "dropped_fn")):
        (root / tree).mkdir(parents=True)
        (root / tree / f"{name}.c").write_text(
            f"/** @brief {name}. */\nint {name}(void) {{ return 0; }}\n", encoding="utf-8"
        )
    return root


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="asserted against a real build")
## @brief The second, unstated build indexes what the first build was told to index.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_a_stated_index_scope_survives_a_plain_rebuild(tmp_path: Path) -> None:
    """THE PLAIN REBUILD IS THE AUTOMATIC ONE. `_auto_refresh` and the background loop both call
    `_run_build` with `options=None`, so what this second `build_index` call does is what every
    unattended refresh of a narrowed index does.

    @brief A recorded index_scope is replayed rather than widened to the whole repository.
    @version 1
    """
    from clew.cli import build_index

    root = _two_tree_repo(tmp_path / "repo")
    out = tmp_path / "clew.db"

    build_index(output=out, repo_root=root, options={"index_scope": {"roots": ["kept"]}})
    assert meta_section(out, "scope")["roots"] == "kept", "premise: the statement narrowed it"

    (root / "kept" / "kept_fn.c").write_text(
        "/** @brief kept_fn. */\nint kept_fn(void) { return 1; }\n", encoding="utf-8"
    )
    build_index(output=out, repo_root=root)

    scope = meta_section(out, "scope")
    assert scope["roots"] == "kept", (
        f"a plain rebuild widened a stated index_scope to {scope['roots']!r} "
        f"({scope.get('reason')!r}) instead of replaying it"
    )
    assert meta_section(out, "options")["index_scope.tier"] == "explicit", (
        "the replayed statement must still be recorded as a statement, so the next build "
        "replays it too"
    )
