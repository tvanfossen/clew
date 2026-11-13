# SPDX-License-Identifier: MIT
"""The whole-tree text stages reuse an unchanged file's result instead of recomputing it.

1.3.4, Track 2 (LSP-speed refresh). Measured with `scripts/refresh_bench.py` at f018113b, the
stages that re-read and re-scan EVERY indexed file on every build were most of a one-file
refresh: `file_docs`, `req_mentions`, `code_text`, `self_declared` and friends — 13.6 s of
21.3 s on this repository. A profile on a copy of the index put the cost in per-file CPU (regex
scans, identifier splitting, docstring parsing), not in the inserts.

THE RULE PINNED HERE: with an index cache, a second build over UNCHANGED files calls the
per-file computation ZERO times, and writes exactly the rows the first build wrote. A cache that
is consulted but always recomputes would pass a row-equality test alone, so the call count is
asserted too; and a first build that never called the computation would make "zero on the second"
vacuous, so that is asserted non-zero.

@brief Tests that the text stages are memoized per file content.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from clew import code_text, coverage, filedocs, generated, prose, req_mentions
from clew.indexcache import IndexCache


## @brief Every row of a table, sorted, for an order-free comparison.
## @param db The index.
## @param table Table name.
## @return Sorted rows.
## @version 1
def _rows(db: Path, table: str) -> list[tuple[Any, ...]]:
    """@brief Read a table. @return Sorted rows."""
    with sqlite3.connect(db) as conn:
        return sorted(conn.execute(f"SELECT * FROM {table}").fetchall(), key=repr)


_STAGES = [
    (
        "file_docs",
        filedocs,
        "extract_file_doc",
        lambda db, repo, cache: filedocs.ingest_file_docs(db, repo, cache=cache),
    ),
    (
        "generated_files",
        generated,
        "self_declared",
        lambda db, repo, cache: generated.record_self_declared(db, repo, cache=cache),
    ),
    (
        "code_text",
        code_text,
        "_identifier_parts",
        lambda db, repo, cache: code_text.record_code_text(db, repo, cache=cache),
    ),
    (
        "req_mentions",
        req_mentions,
        "_file_mentions",
        lambda db, repo, cache: req_mentions.record_req_mentions(db, repo, None, cache=cache),
    ),
    (
        "supplementary_docs",
        prose,
        "_chunks_of",
        lambda db, repo, cache: prose.ingest_supplementary_docs(db, repo, cache=cache),
    ),
    (
        "path",
        coverage,
        "_line_count",
        lambda db, repo, cache: coverage.measure_index_coverage(db, repo, cache=cache),
    ),
]


@pytest.mark.parametrize(("table", "module", "name", "stage"), _STAGES, ids=[s[0] for s in _STAGES])
def test_an_unchanged_file_is_not_recomputed(
    tmp_path: Path,
    rich_db: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    table: str,
    module: Any,
    name: str,
    stage: Callable[[Path, Path, IndexCache], Any],
) -> None:
    """@brief Second cached build: zero per-file computations, identical rows.
    @return None.
    @version 1
    """
    db = tmp_path / "clew.db"
    shutil.copy(rich_db, db)
    sidecar = tmp_path / "clew.db.idxcache"
    real = getattr(module, name)
    calls = {"n": 0}

    def counting(*args: Any, **kwargs: Any) -> Any:
        ## A PATH ROW WITH NO FILE BEHIND IT (the fixture registers system headers like
        ## `stdio.h`) has no content to key a cache entry by, so it is computed every build —
        ## cheaply, as a failed open. Only calls on a file that exists count as recomputation.
        if not (args and isinstance(args[0], Path) and not args[0].exists()):
            calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(module, name, counting)
    runs = []
    for _ in range(2):
        calls["n"] = 0
        cache = IndexCache(sidecar, repo_root)
        stage(db, repo_root, cache)
        cache.commit()
        cache.close()
        runs.append((calls["n"], _rows(db, table)))
    (first_calls, first_rows), (second_calls, second_rows) = runs
    assert first_calls > 0, f"{name} never ran on the first build — the test would be vacuous"
    assert second_calls == 0, f"{name} recomputed {second_calls} unchanged file(s)"
    assert second_rows == first_rows


def test_an_edited_file_is_recomputed(
    tmp_path: Path, rich_db: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE OTHER HALF: a memo that never invalidates would pass the test above. One edited file
    must be recomputed — and only that one.

    @brief Editing one file recomputes exactly that file.
    @return None.
    @version 1
    """
    tree = tmp_path / "tree"
    shutil.copytree(repo_root, tree)
    db = tmp_path / "clew.db"
    shutil.copy(rich_db, db)
    sidecar = tmp_path / "clew.db.idxcache"
    seen: list[str] = []
    real = generated.self_declared
    monkeypatch.setattr(
        generated, "self_declared", lambda rel, head: seen.append(rel) or real(rel, head)
    )
    cache = IndexCache(sidecar, tree)
    generated.record_self_declared(db, tree, cache=cache)
    cache.commit()
    cache.close()
    with sqlite3.connect(db) as conn:
        target = next(str(r[0]) for r in conn.execute("SELECT name FROM path WHERE type = 1"))
    with (tree / target).open("a") as handle:
        handle.write("\n/* edited */\n")
    seen.clear()
    cache = IndexCache(sidecar, tree)
    generated.record_self_declared(db, tree, cache=cache)
    cache.close()
    assert seen == [target]
