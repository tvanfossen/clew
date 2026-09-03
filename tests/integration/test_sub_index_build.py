# SPDX-License-Identifier: MIT
"""Building a split repository, and refreshing one part of it without touching the rest.

THIS FILE EXISTS FOR ONE ASSERTION. Splitting a repository into per-git-tree indexes is only
worth anything if a first-party edit does NOT rebuild the vendored trees — that is the entire
economic argument, because a vendored tree is pinned by its gitlink and therefore immutable. If a
refresh re-reads it anyway, the split has added machinery and bought nothing, and every other
test here would still pass.

So `test_a_first_party_refresh_leaves_the_vendored_index_alone` is the one that matters, and it
asserts against the vendored index's own recorded build time rather than against a duration —
a timing assertion would be flaky and would not distinguish "fast" from "not rebuilt".

@brief Integration tests for building and refreshing sub-indexes.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew._common import captured_output
from clew.cli import build_sub_indexes
from clew.scope import FIRST_PARTY_INDEX

pytestmark = pytest.mark.integration


## @brief A repo with one first-party tree and one vendored submodule.
## @param root Directory to build the repository in.
## @return The repository root.
## @version 1
def _split_repo(root: Path) -> Path:
    """The vendored tree uses a `gitdir:` POINTER FILE, the shape `git submodule` actually
    writes — a fixture built from a `.git` directory would exercise the nested-clone path and
    skip the case this feature is for.

    @brief Build a repository with one vendored submodule.
    @return The repository root.
    @version 1
    """
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.c").write_text("int app_entry(void) { return 0; }\n", encoding="utf-8")
    vendor = root / "extern" / "dep"
    vendor.mkdir(parents=True)
    (vendor / "dep.c").write_text("int dep_helper(void) { return 1; }\n", encoding="utf-8")
    (vendor / ".git").write_text("gitdir: ../../.git/modules/dep\n", encoding="utf-8")
    (root / "Doxyfile").write_text("PROJECT_NAME = split\nINPUT = .\n", encoding="utf-8")
    return root


## @brief Read one build_meta value from an index.
## @param db Database path.
## @param key build_meta key.
## @return The value, or None.
## @version 1
def _meta(db: str | Path, key: str) -> str | None:
    """@brief Read a build_meta value.
    @return The value, or None when absent.
    @version 1
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT value FROM build_meta WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return row[0] if row else None


## @brief A split build produces one index per part, each holding only its own code.
## @version 1
def test_a_split_build_separates_first_party_from_vendored(tmp_path: Path) -> None:
    """Asserts on SYMBOL MEMBERSHIP rather than counts: each index must hold its own function and
    not the other's. Counts would be satisfied by two indexes that both covered everything.

    @brief Each sub-index contains its own code and not the other's.
    @version 1
    """
    repo = _split_repo(tmp_path / "repo")
    with captured_output():
        built = build_sub_indexes(repo, home=tmp_path / "state")

    by_name = {t.name: t for t in built}
    assert set(by_name) == {FIRST_PARTY_INDEX, "extern-dep"}, f"unexpected split: {sorted(by_name)}"

    def _functions(db: str) -> set[str]:
        conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
        try:
            return {r[0] for r in conn.execute("SELECT name FROM memberdef WHERE kind='function'")}
        finally:
            conn.close()

    first = _functions(by_name[FIRST_PARTY_INDEX].db_path)
    vendored = _functions(by_name["extern-dep"].db_path)

    assert "app_entry" in first, "the first-party index is missing first-party code"
    assert "dep_helper" not in first, (
        "the first-party index still contains the vendored tree, so the split saved nothing"
    )
    assert "dep_helper" in vendored, "the vendored index is missing the vendored code"


## @brief Refreshing first-party does not rebuild the vendored index.
## @version 1
def test_a_first_party_refresh_leaves_the_vendored_index_alone(tmp_path: Path) -> None:
    """THE ASSERTION THE WHOLE FEATURE EXISTS FOR. A vendored tree is pinned, so its index is
    immutable and must be built once; if an ordinary edit re-reads it, the split has bought
    nothing and merely added machinery.

    Asserted against the vendored index's recorded `refresh.at_epoch` — its own statement of when
    it was last built — rather than against elapsed time. A duration assertion would be flaky on
    a loaded machine and, worse, would pass for a rebuild that merely happened to be quick.

    @brief A targeted refresh rebuilds only what was named.
    @version 1
    """
    repo = _split_repo(tmp_path / "repo")
    state = tmp_path / "state"
    with captured_output():
        built = build_sub_indexes(repo, home=state)
    by_name = {t.name: t for t in built}
    vendored_db = by_name["extern-dep"].db_path
    before = _meta(vendored_db, "refresh.at_epoch")
    assert before is not None, "the vendored index recorded no build time; this test is vacuous"

    (repo / "app" / "main.c").write_text(
        "int app_entry(void) { return 0; }\nint app_added(void) { return 2; }\n",
        encoding="utf-8",
    )
    with captured_output():
        again = build_sub_indexes(repo, home=state, only=FIRST_PARTY_INDEX)

    assert [t.name for t in again] == [FIRST_PARTY_INDEX], (
        f"a targeted refresh built {[t.name for t in again]}"
    )
    assert _meta(vendored_db, "refresh.at_epoch") == before, (
        "the vendored index was rebuilt by a first-party edit — the split saves nothing if a "
        "pinned tree is re-read on every refresh"
    )
    ## And the edit really did land, so the refresh was not a no-op that trivially satisfies it.
    conn = sqlite3.connect(f"file:{by_name[FIRST_PARTY_INDEX].db_path}?mode=ro", uri=True)
    try:
        names = {r[0] for r in conn.execute("SELECT name FROM memberdef WHERE kind='function'")}
    finally:
        conn.close()
    assert "app_added" in names, "the first-party refresh did not pick up the edit"


## @brief A repository with nothing vendored is not split.
## @version 1
def test_an_unvendored_repo_is_not_split(tmp_path: Path) -> None:
    """THE COMPATIBILITY CASE. Every existing target must keep its slug and its database; a
    driver that split unconditionally would strand them all.

    @brief No nested trees means no sub-index build.
    @version 1
    """
    repo = tmp_path / "plain"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "main.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
    (repo / "Doxyfile").write_text("PROJECT_NAME = plain\nINPUT = .\n", encoding="utf-8")

    with captured_output():
        assert build_sub_indexes(repo, home=tmp_path / "state") == []
