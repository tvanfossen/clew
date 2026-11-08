# SPDX-License-Identifier: MIT
"""A successful build leaves the index cache without a mostly-free file.

FOUND BY A PEER SESSION, 2026-11-07, and verified here: clew never vacuumed `<output>.idxcache`.
Payload churn (`INSERT OR REPLACE`) and build-version invalidation (`DELETE`) left free pages that
nothing reclaimed — entropic's cache was 9,856 MB with 97% of its pages free (231 MB after a
manual VACUUM), sassafras-class's 3,227 MB at 31% free. Together about 10.6 GB, on a disk that
filled that week.

@brief Tests for the index cache's free-page reclamation.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.indexcache import VACUUM_FREE_RATIO, IndexCache


## @brief The share of a database's pages on its free list.
## @param path The database.
## @return free pages / page count.
## @version 1
def _free_ratio(path: Path) -> float:
    """@brief Free-page ratio. @return Ratio."""
    conn = sqlite3.connect(path)
    try:
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        free = conn.execute("PRAGMA freelist_count").fetchone()[0]
    finally:
        conn.close()
    return free / pages if pages else 0.0


## @brief Fill the cache with payloads, then drop them, as an invalidating build does.
## @param cache An open cache.
## @return None.
## @version 1
def _churn(cache: IndexCache) -> None:
    """@brief Write then delete a few MB of payload rows. @return None."""
    for i in range(400):
        cache.extract_put(f"sha{i}", "stage", 1, "", {"blob": "x" * 8000})
    cache.flush()
    cache.conn.execute("DELETE FROM extract_cache")
    cache.flush()


## @brief A commit over a mostly-free cache reclaims the space.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_successful_build_reclaims_a_mostly_free_cache(tmp_path: Path) -> None:
    """@brief Free ratio is under the threshold after commit.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    path = tmp_path / "clew.db.idxcache"
    cache = IndexCache(path, repo)
    _churn(cache)
    assert _free_ratio(path) > VACUUM_FREE_RATIO, "fixture did not create free pages"
    cache.commit()
    cache.close()
    assert _free_ratio(path) <= VACUUM_FREE_RATIO


## @brief An aborted build (flush, no commit) does not vacuum.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_flush_alone_does_not_vacuum(tmp_path: Path) -> None:
    """THE SUCCESS PATH ONLY. A VACUUM rewrites the whole file; an aborted build that paid for one
    would pay it on every retry, which is the cost the cache exists to avoid.

    @brief Free pages survive a flush.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    path = tmp_path / "clew.db.idxcache"
    cache = IndexCache(path, repo)
    _churn(cache)
    cache.close()
    assert _free_ratio(path) > VACUUM_FREE_RATIO
