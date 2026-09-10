# SPDX-License-Identifier: MIT
"""gh#34 — the AST call-edge stage re-resolves every file on every refresh.

MEASURED on develop, a 6.8 GB repository with five nested trees, refreshing after ONE
touched file:

    incremental refresh   8.6 s wall   0 payloads recomputed, 8,064 served from cache

Zero payloads recomputed — so none of that is tree-sitter or doxygen work. `ast_call_edges`
alone was 3,255 ms of it, 40% of the whole refresh, and profiling the stage with every parse
served from cache says where:

    _fold_call_payload   2,699 ms   645 files      <- 59% of the stage
      _ast_record_call_edge        67,677 calls
      _scope_is                   790,306 calls
      _narrow_by_receiver          16,163 calls

`import_ast_call_edges`' own docstring states the design plainly: "The per-file parse is
cached by content sha; the line->rowid and name->rowid resolution ALWAYS RERUNS." That was a
fair trade when the parse dominated. With the parse cached it is the whole cost.

WHY THE ROWS CANNOT SIMPLY BE KEPT. The build writes into a fresh staging database and swaps
atomically, and `_ast_insert_edges` only ever INSERTs — so `call_edges` starts empty on every
build and every file must be folded again to repopulate it. Incrementality here is not
"skip work", it is "serve this file's RESOLVED EDGES from the cache".

WHAT MAKES THAT SOUND, AND IT IS NOT THE PAYLOAD SHA ALONE. Resolution reads the whole
index: `name_to_rowids`, `definition_of`, `receiver_types`, `scope_of`, `argc_of`. One edited
file can change any of them and thereby change how an UNCHANGED file's call sites resolve —
a new overload joins a candidate set, a moved definition changes which rowid wins. So the
cache key carries a digest of every one of those inputs, and any change to any of them
invalidates every file's cached fold at once. `test_a_new_function_invalidates_every_cached_fold`
is that guard, and it is the test that matters most here: a stale edge served from cache is
exactly the silent wrongness this project treats as its most expensive defect class.

PARITY IS STRUCTURAL, WHICH IS WHY THIS IS SAFE TO DO AT ALL. `_fold_call_payload` appends to
three shared lists, and every post-pass — `_collapse_duplicate_targets`,
`_insert_unresolved_inbound`, `_ast_insert_edges`, `prune_fabricated_self_edges` — runs over
the FULL lists afterwards. So if a cached slice equals what folding would have appended, the
final rows are identical by construction rather than by argument.

@brief Tests for caching the resolved call edges of an unchanged file.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from test_self_edges import _functions, _parse

from clew.indexcache import IndexCache

_A = '''\
def helper(x):
    """@brief Helper."""
    return x + 1


def caller(x):
    """@brief Caller."""
    return helper(x)
'''

_B = '''\
def other(y):
    """@brief Other."""
    return y * 2


def second(y):
    """@brief Second."""
    return other(y)
'''


##
# @brief Seed a two-file index the fold stage can run over.
# @param tmp_path Pytest temp dir.
# @param sources Mapping of file name to its text.
# @param db_name Database file name, so one repo can hold two seeded indexes.
# @return The database path.
# @version 1
def _two_file_db(tmp_path: Path, sources: dict[str, str], db_name: str = "clew.db") -> Path:
    """TWO FILES, because the property under test is per-file: one must be able to change
    while the other holds. A single-file fixture cannot tell "cached the unchanged file"
    from "cached everything".

    @brief Build a synthetic index over several fixture files.
    @return The db path.
    @version 1
    """
    tmp_path.mkdir(parents=True, exist_ok=True)
    db_path = tmp_path / db_name
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT,
            UNIQUE(caller_rowid, callee_rowid, source)
        );
        """
    )
    for file_id, (name, text) in enumerate(sources.items(), start=1):
        tree, src = _parse(tmp_path, name, text)
        conn.execute("INSERT INTO path (rowid, name) VALUES (?, ?)", (file_id, name))
        conn.executemany(
            "INSERT INTO memberdef (kind, name, file_id, bodyfile_id, bodystart, bodyend) "
            "VALUES ('function', ?, ?, ?, ?, ?)",
            [(n, file_id, file_id, s, e) for n, s, e in _functions(tree, src)],
        )
    conn.commit()
    conn.close()
    return db_path


##
# @brief Run the stage against a COPY of the seeded index, counting folds.
# @param db The seeded index; copied so each run starts from the same rows.
# @param repo The working tree the fixtures live in.
# @param cache_path The sidecar to share across runs.
# @param monkeypatch Pytest monkeypatch, for the fold counter.
# @return (number of files folded, the resulting call_edges rows).
# @version 1
def _run_stage(db: Path, repo: Path, cache_path: Path, monkeypatch) -> tuple[int, set]:
    """COUNTS FOLDS RATHER THAN TIMING, because a timing assertion in a unit test measures
    the machine. The fold count is the mechanism: a file served from cache is a file
    `_fold_call_payload` was never called for.

    @brief Run the stage once, reporting folds and rows.
    @return (fold count, call_edges rows).
    @version 1
    """
    import shutil

    from clew import call_edges as ce

    working = db.parent / f"run-{cache_path.stem}-{id(monkeypatch)}.db"
    shutil.copy(db, working)

    folded = {"n": 0}
    original = ce._fold_call_payload

    def counting(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
        folded["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(ce, "_fold_call_payload", counting)
    cache = IndexCache(cache_path, repo)
    ce.import_ast_call_edges(working, repo, cache)
    cache.commit()
    monkeypatch.undo()

    conn = sqlite3.connect(str(working))
    rows = set(
        conn.execute(
            "SELECT caller_rowid, callee_rowid, source, confidence FROM call_edges"
        ).fetchall()
    )
    conn.close()
    return folded["n"], rows


def test_an_unchanged_file_is_not_refolded_on_a_second_run(tmp_path: Path, monkeypatch) -> None:
    """THE 59%. Nothing about the tree or the index moved between the two runs, so the second
    run has nothing to resolve — and resolved it all again anyway.

    @brief A second run over an unchanged tree folds nothing.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    db = _two_file_db(repo, {"a.py": _A, "b.py": _B})
    cache = tmp_path / "clew.db.idxcache"

    first, first_rows = _run_stage(db, repo, cache, monkeypatch)
    second, second_rows = _run_stage(db, repo, cache, monkeypatch)

    assert first == 2, f"the cold run must fold both files, folded {first}"
    assert second == 0, f"an unchanged tree needs no folding, folded {second}"
    assert second_rows == first_rows, "the cached run must write exactly the same edges"


def test_only_the_edited_file_is_refolded(tmp_path: Path, monkeypatch) -> None:
    """THE COMMON INCREMENTAL EDIT: a body changes, no signature does, so the resolution
    inputs are identical and every other file's fold is still valid. This is the case the
    field report was made of — seven edited files out of 913.

    @brief Editing one body re-folds one file.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    db = _two_file_db(repo, {"a.py": _A, "b.py": _B})
    cache = tmp_path / "clew.db.idxcache"
    _run_stage(db, repo, cache, monkeypatch)

    ## A body edit only: same functions, same lines, different statement.
    (repo / "b.py").write_text(_B.replace("return y * 2", "return y * 3"), encoding="utf-8")
    second, _rows = _run_stage(db, repo, cache, monkeypatch)

    assert second == 1, f"only the edited file needed folding, folded {second}"


def test_a_new_function_invalidates_every_cached_fold(tmp_path: Path, monkeypatch) -> None:
    """THE GUARD THAT MATTERS MOST, and the reason the payload sha alone is not the key. A
    new function joins `name_to_rowids`, so a call site in an UNCHANGED file may now resolve
    to a different rowid — or resolve at all where it did not. Serving that file's old edges
    would be a stale edge presented as a measurement, which is this project's most expensive
    recorded defect class.

    @brief A changed resolution input re-folds everything, not just the changed file.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    db = _two_file_db(repo, {"a.py": _A, "b.py": _B})
    cache = tmp_path / "clew.db.idxcache"
    _run_stage(db, repo, cache, monkeypatch)

    ## A NEW index, with an extra function — the resolution inputs have moved.
    widened = _two_file_db(
        repo,
        {
            "a.py": _A,
            "b.py": _B + '\n\ndef third(z):\n    """@brief Third."""\n    return other(z)\n',
        },
        db_name="widened.db",
    )
    second, _rows = _run_stage(widened, repo, cache, monkeypatch)

    assert second == 2, (
        f"a changed name->rowid map invalidates every file's fold, not just the edited "
        f"one — folded {second}"
    )


def test_the_cached_run_writes_exactly_what_a_cold_run_writes(tmp_path: Path, monkeypatch) -> None:
    """PARITY, asserted rather than argued. A cache that produces almost the right edges is
    worse than no cache: the rows it gets wrong are indistinguishable from measurements.

    @brief A cache-served run and a cache-free run write identical rows.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    db = _two_file_db(repo, {"a.py": _A, "b.py": _B})

    warm_cache = tmp_path / "warm.idxcache"
    _run_stage(db, repo, warm_cache, monkeypatch)
    folded_warm, warm_rows = _run_stage(db, repo, warm_cache, monkeypatch)

    cold_cache = tmp_path / "cold.idxcache"
    folded_cold, cold_rows = _run_stage(db, repo, cold_cache, monkeypatch)

    assert folded_warm == 0 and folded_cold == 2, "the two runs must differ in HOW they got there"
    assert warm_rows == cold_rows, "...and not in what they wrote"
    assert warm_rows, "the fixture must produce edges at all, or this asserts nothing"
