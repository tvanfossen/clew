# SPDX-License-Identifier: MIT
"""The `doxygen_cache` retrieval contract, asserted directly against `IndexCache` (#399).

TIER 1 ON PURPOSE, and that is not a preference. `tests/integration/` is deselected
without `--integration`, so a guard tested only there is unguarded on every default run —
and the two guards here are an UPGRADE path and an UNREADABLE-FILE path, neither of which
a real build produces. The one property that does need a real doxygen run (a widened scope
reappearing in `path` rows after a withdrawal) is asserted where it belongs, in
`tests/integration/test_manifest_replay_integration.py`.

WHY A UNIT TEST CAN SEE #399 AT ALL. The defect is not about doxygen; it is about the cache
answering a question it cannot answer. Every key in `doxygen_cache` names the SAME output
path — the directory comes from `--index-cache`/`--output` alone (`cli._doxygen_out_dir`)
and the filename is fixed (`doxygen.doxygen_db_path`) — so the aliasing is reproduced
exactly by writing one file, recording it under one key, and then overwriting the file the
way the next build does. No doxygen needed to demonstrate a hit that should be a miss.

THE SUCCESS PATH IS ASSERTED BESIDE EVERY FAILURE PATH, because a cache that always
misses satisfies every "must not serve the wrong output" assertion in this module while
silently costing a full doxygen run per build — the shape this repo has recorded as a
check with a test for its failure path and none for its success path.

@brief Tier-1 tests for the doxygen output cache's key/content binding.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.indexcache import IndexCache

KEY_A = "a" * 64
KEY_B = "b" * 64


## @brief Write a stand-in doxygen output file.
## @param path Where to write it.
## @param body Bytes to write, distinguishing one build's output from another's.
## @return The path written.
## @version 1
def _write_output(path: Path, body: str) -> Path:
    """The cache never parses this file, it only hashes it, so any distinguishable bytes
    stand in for a doxygen database.

    @brief Create a fake doxygen output.
    @return The path.
    @version 1
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def test_a_cached_output_is_served_under_the_key_that_produced_it(tmp_path: Path) -> None:
    """THE SUCCESS PATH. Nothing overwrote the file, so the skip must be taken — this is the
    whole value of the cache (#363: a cold doxygen run costs tens of seconds) and it is the
    half that a too-eager invalidation silently destroys.
    """
    output = _write_output(tmp_path / "out" / "doxygen_sqlite3.db", "WIDE build output")
    cache = IndexCache(tmp_path / "c.idxcache", tmp_path)
    cache.doxygen_put(KEY_A, output)

    assert cache.doxygen_get(KEY_A) == output, (
        "an untouched output was not served back to its own key — the cache now costs a "
        "full doxygen run on every build and no test of the failure path would notice"
    )


def test_a_key_is_not_served_another_key_s_overwrite_of_the_same_path(tmp_path: Path) -> None:
    """#399 REPRODUCED AT UNIT SCALE, and the exact sequence measured on a real build: key A
    runs and records the shared path; key B runs, OVERWRITES that path, and records it too;
    key A is asked again.

    The old hit condition was "a row for this key exists AND the path exists", both of which
    are still true — so key A was served key B's output. On a real target this was seen in
    both directions, which is what makes it aliasing rather than staleness: a withdrawn
    `predefined` inherited the WIDER earlier output, a withdrawn `index_scope` the NARROWER
    one. Neither is "the newer output wins"; it is "whichever output was written last wins,
    whatever its key said".
    """
    shared = tmp_path / "out" / "doxygen_sqlite3.db"
    _write_output(shared, "NARROW build output")
    cache = IndexCache(tmp_path / "c.idxcache", tmp_path)
    cache.doxygen_put(KEY_A, shared)
    assert cache.doxygen_get(KEY_A) == shared

    ## Key B is the next build: same path, different content, its own row.
    _write_output(shared, "WIDE build output — a different configuration of the same repo")
    cache.doxygen_put(KEY_B, shared)

    assert cache.doxygen_get(KEY_A) is None, (
        "key A was served the output key B wrote over the shared path — the cache reported a "
        "hit for a configuration whose output no longer exists anywhere (#399)"
    )
    assert cache.doxygen_get(KEY_B) == shared, (
        "the key that actually produced the current file must still hit; invalidating both "
        "would trade a wrong answer for a permanently cold cache"
    )


def test_an_output_that_cannot_be_hashed_is_not_cached_at_all(tmp_path: Path) -> None:
    """THE EMPTY-STRING WILDCARD, refused. `treescan.hash_file` returns "" for a file it
    cannot read, so recording that digest would make a later unreadable read compare
    `"" == ""` and HIT — a false hit manufactured out of two failures. The row is therefore
    not written, and the next build re-runs doxygen instead of trusting a file nobody hashed.
    """
    cache = IndexCache(tmp_path / "c.idxcache", tmp_path)
    missing = tmp_path / "out" / "never_written.db"

    cache.doxygen_put(KEY_A, missing)

    rows = cache.conn.execute("SELECT COUNT(*) FROM doxygen_cache").fetchone()[0]
    assert rows == 0, "an unhashable output was recorded, so its digest is a wildcard"
    assert cache.doxygen_get(KEY_A) is None


def test_a_sidecar_predating_output_sha_is_rebuilt_rather_than_crashing(tmp_path: Path) -> None:
    """THE UPGRADE PATH, which no real build produces and which therefore had no coverage.

    `CREATE TABLE IF NOT EXISTS` does nothing to a table that already exists, so a sidecar
    written before `output_sha` keeps its three-column shape and the first `doxygen_put`
    against it raises `no column named output_sha`. The build-version wipe does not help —
    it deletes ROWS, not columns. A crash here would land on every existing cache on disk,
    in the one component whose whole job is to be discardable.
    """
    cache_path = tmp_path / "old.idxcache"
    conn = sqlite3.connect(str(cache_path))
    conn.executescript(
        "CREATE TABLE doxygen_cache ("
        "  tree_sha TEXT PRIMARY KEY, db_path TEXT NOT NULL, created_at INTEGER NOT NULL);"
    )
    conn.execute(
        "INSERT INTO doxygen_cache(tree_sha, db_path, created_at) VALUES (?, ?, 0)",
        (KEY_A, str(tmp_path / "stale.db")),
    )
    conn.commit()
    conn.close()

    cache = IndexCache(cache_path, tmp_path)

    columns = {row[1] for row in cache.conn.execute("PRAGMA table_info(doxygen_cache)")}
    assert "output_sha" in columns, "the old table shape survived, so every put will raise"
    output = _write_output(tmp_path / "out" / "doxygen_sqlite3.db", "post-upgrade output")
    cache.doxygen_put(KEY_A, output)
    assert cache.doxygen_get(KEY_A) == output, (
        "an upgraded sidecar cannot store and serve an entry, so the rebuild left the table "
        "unusable rather than merely empty"
    )
