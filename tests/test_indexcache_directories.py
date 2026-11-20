# SPDX-License-Identifier: MIT
"""A directory is never recorded as a source file (entropic, 2.0.0).

ENTROPIC'S RERUN OF 314e4696: every refresh, the no-edit one included, logged
`index cache: 699 unchanged, 0 modified, 0 added, 61 removed source file(s)` straight after a fresh
build that logged `699 added`. All 61 were DIRECTORIES: `sha_for` is asked about each doxygen path
row, directory rows included, and recorded them; the next scan then reported them removed
(`previous - files`). So the cache never settled, and every refresh planned a deletion-only splice
for files that never left.

@brief Tests that IndexCache ignores directories.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.indexcache import IndexCache


def test_a_directory_has_no_identity_and_is_never_removed(tmp_path: Path) -> None:
    """@brief sha_for on a directory records nothing; the next scan removes nothing."""
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.c").write_text("int a(void) { return 1; }\n", encoding="utf-8")
    files = {"src/a.c": repo / "src" / "a.c"}
    cache_path = tmp_path / "clew.db.idxcache"

    first = IndexCache(cache_path, repo)
    first.scan(files)
    assert first.sha_for("src", repo / "src") is None
    first.commit()

    second = IndexCache(cache_path, repo)
    summary = second.scan(files)
    assert summary.removed == [] and summary.unchanged == ["src/a.c"], summary
