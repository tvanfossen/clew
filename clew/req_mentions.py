# SPDX-License-Identifier: MIT
"""Every indexed file line that names a requirement — documentation, build files, comments.

OWNER, 2026-11-04: a requirement was linked to its implementing functions through `@req` tags and
to nothing else, while the design document, the diagram page, the CMake option and the release
note that name it are what a reader asks for next. Once reStructuredText became prose (#65) the
gap was plain; the owner widened it at once — "markdowns, text files, cmakes, etc, not just rst".
So this is ONE mechanism over every file the index holds, whatever its type.

THE IDS ARE THE ONES THE INDEX ALREADY KNOWS: the catalog's rows plus every id a `@req` tag
named. A requirement nobody declared is not searched for, which keeps an arbitrary `REQ-`-looking
string in a changelog from becoming a requirement.

LEFT OUT ON PURPOSE: a `@req` tag line (already an implementer, through `req_edges`) and the
catalog file (it names every id, and would list itself under all of them).

A POST-BUILD PASS, rebuilt whole each build like the code corpus. CREATED EVEN WHEN EMPTY, so
"nothing mentions this requirement" and "this index never looked" stay distinguishable.

@brief Requirement mentions across the indexed file set.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from ._common import logger

## The mentions table.
TABLE = "req_mentions"

## A file larger than this is not scanned: a generated table or a vendored archive would cost the
## build more than any mention in it is worth to a reader.
MAX_FILE_BYTES = 2_000_000

## A line carrying a `@req` tag is an implementer link, recorded by `req_edges`.
_TAG_LINE = re.compile(r"[@\\]req\b")


## @brief Rebuild the requirement-mentions table from the indexed file set.
## @param db_path The database under construction.
## @param repo_root Repository root the indexed paths are relative to.
## @param catalog The requirements catalog file, or None; it is never scanned.
## @return Number of mentions recorded.
## @version 1
## @utility
def record_req_mentions(db_path: Path, repo_root: Path, catalog: Path | None) -> int:
    """@brief Record requirement mentions. @return Mentions recorded."""
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(f"DROP TABLE IF EXISTS {TABLE}")
        conn.execute(
            f"CREATE TABLE {TABLE} (req_id TEXT NOT NULL, file TEXT NOT NULL, "
            "line INTEGER NOT NULL, text TEXT NOT NULL)"
        )
        ids = _known_ids(conn)
        rows = [] if not ids else _scan(conn, repo_root, catalog, ids)
        conn.executemany(f"INSERT INTO {TABLE} VALUES (?, ?, ?, ?)", rows)
        conn.commit()
    finally:
        conn.close()
    logger.info(
        "requirements: %d mention(s) of %d known id(s) in the indexed files", len(rows), len(ids)
    )
    return len(rows)


## @brief The requirement ids the index knows: the catalog's and every `@req` tag's.
## @param conn Open connection.
## @return The ids.
## @version 1
## @dg_internal
def _known_ids(conn: sqlite3.Connection) -> set[str]:
    """@brief Known ids. @return The set."""
    ids: set[str] = set()
    for table, column in (("requirements", "id"), ("req_edges", "req_id")):
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name = ?", (table,)).fetchone():
            ids.update(str(r[0]) for r in conn.execute(f"SELECT DISTINCT {column} FROM {table}"))
    return {i for i in ids if i}


## @brief Every line of every indexed file that names a known id.
## @param conn Open connection.
## @param repo_root Repository root.
## @param catalog The catalog file, skipped.
## @param ids Known ids.
## @return (req_id, file, line, text) rows.
## @version 1
## @dg_internal
def _scan(
    conn: sqlite3.Connection, repo_root: Path, catalog: Path | None, ids: set[str]
) -> list[tuple[str, str, int, str]]:
    """AN ID MATCHES WHOLE: `REQ-A-001` does not match inside `REQ-A-0011`, so the boundary
    excludes the characters an id is made of on either side.

    @brief Scan the indexed files.
    @return Rows.
    """
    pattern = re.compile(
        r"(?<![\w-])("
        + "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True))
        + r")(?![\w-])"
    )
    skip = catalog.resolve() if catalog is not None else None
    rows: list[tuple[str, str, int, str]] = []
    for rel in _indexed_files(conn):
        path = repo_root / rel
        text = _text_of(path, skip)
        if text is None:
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            if _TAG_LINE.search(line):
                continue
            for found in sorted(set(pattern.findall(line))):
                rows.append((found, str(rel), number, line.strip()))
    return rows


## @brief Every file the index holds: its registered paths and the prose corpus's files.
## @param conn Open connection.
## @return Repo-relative paths, sorted.
## @version 1
## @dg_internal
def _indexed_files(conn: sqlite3.Connection) -> list[str]:
    """PROSE IS NOT IN `path`: markdown and reStructuredText are read into `supplementary_docs`
    without a path row, and a design document is the commonest place a requirement is named.

    @brief The indexed file set.
    @return Paths.
    """
    files = {str(r[0]) for r in conn.execute("SELECT name FROM path")}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'supplementary_docs'").fetchone():
        files.update(
            str(r[0]) for r in conn.execute("SELECT DISTINCT file_path FROM supplementary_docs")
        )
    return sorted(files)


## @brief A file's text, or None when it is the catalog, too large, unreadable or not a file.
## @param path The file.
## @param skip The resolved catalog path, or None.
## @return The text or None.
## @version 1
## @dg_internal
def _text_of(path: Path, skip: Path | None) -> str | None:
    """@brief Read a scannable file. @return Text or None."""
    try:
        if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
            return None
        if skip is not None and path.resolve() == skip:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
