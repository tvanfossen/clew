# SPDX-License-Identifier: MIT
"""The per-file text layers the fast tier recomputes for an edited file.

Split from `clew.fasttier` so each module keeps one job: that one decides whether the fast tier
applies and moves symbol positions; this one rewrites the layers whose rows belong wholly to one
file. Each function here reuses the full stage's own per-file computation — the memoized
helpers 1.3.4 split out — so a row the fast tier writes is the row the full build would write
for the same bytes.

@brief Fast-tier rewrites of an edited file's text layers.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .indexcache import IndexCache


## @brief Rewrite every per-file text layer for one edited file.
## @param conn Open index connection, inside the fast tier's transaction.
## @param repo_root The working tree.
## @param rel The edited file, repo-relative.
## @param cache The index cache.
## @return None.
## @version 1
## @req REQ-DDB-INDEX-006
def refresh_text_layers(
    conn: sqlite3.Connection, repo_root: Path, rel: str, cache: IndexCache
) -> None:
    """@brief Recompute file docs, requirement mentions and generated-file evidence. @return None."""
    _refresh_file_doc(conn, repo_root, rel, cache)
    _refresh_mentions(conn, repo_root, rel, cache)
    _refresh_generated(conn, repo_root, rel, cache)


## @brief Whether a table exists in the index.
## @param conn Open connection.
## @param name Table name.
## @return True when present.
## @version 1
## @dg_internal
def _has(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Table probe. @return True when present."""
    return (
        conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (name,)).fetchone() is not None
    )


## @brief Rewrite one file's file-level documentation and its searchable copy.
## @param conn Open connection.
## @param repo_root The working tree.
## @param rel The file.
## @param cache The index cache.
## @return None.
## @version 1
## @dg_internal
def _refresh_file_doc(
    conn: sqlite3.Connection, repo_root: Path, rel: str, cache: IndexCache
) -> None:
    """THE SAME ROWS `ingest_file_docs` WRITES: one `file_docs` row and one `supplementary_docs`
    chunk headed `<rel> — file-level documentation`, through the same memoized extraction.

    @brief Rewrite one file's docs.
    @return None.
    """
    from .filedocs import FILE_DOCS_STAGE_VERSION, _doc_of
    from .indexcache import memoized

    if not _has(conn, "file_docs"):
        return
    heading = f"{rel} — file-level documentation"
    conn.execute("DELETE FROM file_docs WHERE file_path = ?", (rel,))
    if _has(conn, "supplementary_docs"):
        conn.execute(
            "DELETE FROM supplementary_docs WHERE file_path = ? AND heading = ?", (rel, heading)
        )
    doc = memoized(
        cache,
        rel,
        repo_root / rel,
        "file_docs",
        FILE_DOCS_STAGE_VERSION,
        rel,
        lambda: _doc_of(repo_root / rel, rel),
    )
    if not doc:
        return
    conn.execute("INSERT INTO file_docs (file_path, doc) VALUES (?, ?)", (rel, doc))
    if _has(conn, "supplementary_docs"):
        conn.execute(
            "INSERT INTO supplementary_docs (file_path, heading, content) VALUES (?, ?, ?)",
            (rel, heading, f"{rel}\n{doc}"),
        )


## @brief Rewrite one file's requirement mentions.
## @param conn Open connection.
## @param repo_root The working tree.
## @param rel The file.
## @param cache The index cache.
## @return None.
## @version 1
## @dg_internal
def _refresh_mentions(
    conn: sqlite3.Connection, repo_root: Path, rel: str, cache: IndexCache
) -> None:
    """THE SAME KEY `record_req_mentions` USES — content sha plus the id set — so the payload it
    reads or writes is the full stage's.

    @brief Rewrite one file's mentions.
    @return None.
    """
    import hashlib

    from .indexcache import memoized
    from .req_mentions import REQ_MENTIONS_STAGE_VERSION, TABLE, _known_ids, _mentions_of

    if not _has(conn, TABLE):
        return
    conn.execute(f"DELETE FROM {TABLE} WHERE file = ?", (rel,))
    ids = _known_ids(conn)
    if not ids:
        return
    pattern = re.compile(
        r"(?<![\w-])("
        + "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True))
        + r")(?![\w-])"
    )
    key = hashlib.sha256("\n".join(sorted(ids)).encode()).hexdigest()[:16]
    found = memoized(
        cache,
        rel,
        repo_root / rel,
        "req_mentions",
        REQ_MENTIONS_STAGE_VERSION,
        key,
        lambda: _mentions_of(repo_root / rel, pattern),
    )
    conn.executemany(
        f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?)",
        [(req, rel, number, line) for req, number, line in found or ()],
    )


## @brief Rewrite one file's self-declared generated-file evidence.
## @param conn Open connection.
## @param repo_root The working tree.
## @param rel The file.
## @param cache The index cache.
## @return None.
## @version 1
## @dg_internal
def _refresh_generated(
    conn: sqlite3.Connection, repo_root: Path, rel: str, cache: IndexCache
) -> None:
    """ONLY THE SELF-DECLARED ROW: the CMake-derived rows of `generated_files` describe build
    rules, which a source edit does not change.

    @brief Rewrite one file's generated evidence.
    @return None.
    """
    from .generated import KIND_SELF_DECLARED, SELF_DECLARED_STAGE_VERSION, _evidence_of
    from .indexcache import memoized

    if not _has(conn, "generated_files"):
        return
    conn.execute(
        "DELETE FROM generated_files WHERE output_literal = ? AND kind LIKE ?",
        (rel, f"{KIND_SELF_DECLARED}:%"),
    )
    evidence = memoized(
        cache,
        rel,
        repo_root / rel,
        "self_declared",
        SELF_DECLARED_STAGE_VERSION,
        rel,
        lambda: _evidence_of(repo_root / rel, rel),
    )
    if evidence:
        conn.execute(
            "INSERT INTO generated_files (output_name, output_literal, kind, source_file, "
            "source_line, role, arg_name, arg_literal) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (rel, rel, f"{KIND_SELF_DECLARED}: {evidence}", rel, 0, "output", "", ""),
        )


## @brief Replace one file's rows in the contentless code corpus.
## @param conn Open connection, inside the fast tier's transaction, AFTER positions moved.
## @param repo_root The working tree.
## @param rel The edited file.
## @param cache The index cache.
## @param old_sha The content sha the last full build indexed.
## @param old_rows The file's corpus rows BEFORE positions moved, as `code_text_rows` orders them.
## @return True when the file's corpus rows are current; False when the old text was not
##         recoverable and the corpus must stay disclosed stale.
## @version 1
## @req REQ-DDB-INDEX-006
def refresh_code_text(
    conn: sqlite3.Connection,
    repo_root: Path,
    rel: str,
    cache: IndexCache,
    old_sha: str,
    old_rows: list,
) -> bool:
    """A CONTENTLESS FTS5 TABLE DELETES ONLY BY RESTATING WHAT WAS INDEXED: the `'delete'` command
    needs each row's exact old text, and SQLite 3.37 has no contentless-delete. That text is in
    the cache — the full stage memoized it under the OLD content sha and the OLD spans — so it is
    read back, never recomputed from the new bytes. Not there, nothing is touched and the caller
    keeps the corpus on the stale list.

    @brief Delete the old corpus rows, insert the new.
    @return Whether the corpus is current for this file.
    """
    from .code_text import (
        CODE_TEXT_STAGE_VERSION,
        TABLE,
        code_text_rows,
        file_code_texts,
        spans_key,
    )

    if not _has(conn, TABLE):
        return True
    old = (
        cache.extract_get(old_sha, "code_text", CODE_TEXT_STAGE_VERSION, spans_key(old_rows))
        if old_rows
        else {"v": []}
    )
    if old is None:
        return False
    for row, text in zip(old_rows, old["v"] or [], strict=False):
        conn.execute(
            f"INSERT INTO {TABLE} ({TABLE}, rowid, body) VALUES ('delete', ?, ?)",
            (int(row[0]), text),
        )
    new_rows = code_text_rows(conn, rel)
    texts = file_code_texts(cache, repo_root, rel, new_rows) if new_rows else []
    conn.executemany(
        f"INSERT INTO {TABLE} (rowid, body) VALUES (?, ?)",
        [(int(r[0]), t) for r, t in zip(new_rows, texts or [], strict=False)],
    )
    return True
