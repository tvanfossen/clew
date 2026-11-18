# SPDX-License-Identifier: MIT
"""Each file's declared licence: its `SPDX-License-Identifier` header, read into `file_licenses` (S5).

2.0.0 (owner 2026-11-17, prior-art adoption; feeds the SBOM page, GH #70). The REUSE convention
(https://reuse.software) and the Linux kernel put one `SPDX-License-Identifier: <expression>` line
at the top of every file. `filedocs` already recognised and SKIPPED that line to reach the
docstring; this layer records it instead of throwing it away.

ONLY THE DECLARATION IS RECORDED: the expression exactly as written (`MIT`, `GPL-2.0-only OR
BSD-3-Clause`, `Apache-2.0 WITH LLVM-exception`), and the line it is on. No licence is inferred
from a LICENSE file, a header's prose or a package manifest, and nothing is judged compatible or
not here — that is the SBOM page's job, against the repository's declared acceptable set.

@brief The file-licence layer.
@version 1
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from ._common import logger, within_repo
from .indexcache import IndexCache, memoized

## Bumped whenever extraction changes, so a cached result from older logic is not reused.
LICENSES_STAGE_VERSION = 1
## How far into a file the identifier is looked for. REUSE places it in the header comment; a
## shebang, an encoding line or a short copyright block may precede it.
_HEAD_LINES = 30
## The tag and its expression: licence ids and the SPDX operators, up to whatever closes the
## comment (`*/`, `-->`) or the line.
_SPDX = re.compile(r"SPDX-License-Identifier:\s*([A-Za-z0-9.+\-() ]+?)\s*(?:\*/|-->|$)")

_DDL = """
CREATE TABLE IF NOT EXISTS file_licenses (
    file_path TEXT PRIMARY KEY,
    license TEXT NOT NULL,
    line INTEGER NOT NULL
);
"""


## @brief The SPDX expression a file's header declares, and its line.
## @param text The file's text.
## @return (expression, 1-based line), or None when the header declares none.
## @version 1
## @req REQ-DDB-INDEX-008
def spdx_of(text: str) -> tuple[str, int] | None:
    """Any comment style — `//`, `#`, `/* */`, `--`, `<!-- -->`, `;` — because the tag is matched
    where it stands, not after a comment prefix this module would have to know per language.

    @brief Read the SPDX identifier.
    @return Expression and line, or None.
    """
    for number, line in enumerate(text.splitlines()[:_HEAD_LINES], start=1):
        match = _SPDX.search(line)
        if match and match.group(1).strip():
            return " ".join(match.group(1).split()), number
    return None


## @brief One file's declared licence, read from disk.
## @param path The file.
## @return (expression, line), or None.
## @version 1
## @dg_internal
def _license_of(path: Path) -> tuple[str, int] | None:
    """@brief Read one file's header. @return Expression and line, or None."""
    try:
        with open(path, encoding="utf-8", errors="replace") as handle:
            head = "".join(handle.readline() for _ in range(_HEAD_LINES))
    except OSError:
        return None
    return spdx_of(head)


## @brief Record every indexed file's declared licence.
## @param db_path The index.
## @param repo_root The repository.
## @param cache The run's index cache, or None.
## @return Files with a declaration.
## @version 1
## @req REQ-DDB-INDEX-008
def ingest_file_licenses(db_path: Path, repo_root: Path, cache: IndexCache | None = None) -> int:
    """MEMOIZED ON CONTENT like `file_docs`, so an unchanged file is not re-read. THE TABLE IS
    ALWAYS CREATED: empty means "no file declares one", absent would mean "this layer never ran".

    @brief Build the licence layer.
    @return Row count.
    """
    from .filedocs import _indexed_files

    conn = sqlite3.connect(str(db_path))
    try:
        conn.executescript(_DDL)
        conn.execute("DELETE FROM file_licenses")
        resolved: dict[str, str] = {}
        rows = []
        for rel in _indexed_files(conn):
            if (
                within_repo(repo_root / rel, repo_root, setting=f"licence of {rel}", memo=resolved)
                is None
            ):
                continue
            found = license_of(cache, repo_root, rel)
            if found:
                rows.append((rel, found[0], found[1]))
        conn.executemany(
            "INSERT INTO file_licenses (file_path, license, line) VALUES (?, ?, ?)", rows
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("file_licenses: %d file(s) declare an SPDX licence", len(rows))
    return len(rows)


## @brief One file's declared licence, through the content-keyed cache.
## @param cache The index cache, or None.
## @param repo_root The repository.
## @param rel The file.
## @return (expression, line), or None.
## @version 1
## @dg_internal
def license_of(cache: IndexCache | None, repo_root: Path, rel: str) -> tuple[str, int] | None:
    """@brief Memoized read. @return Expression and line, or None."""
    found = memoized(
        cache,
        rel,
        repo_root / rel,
        "file_licenses",
        LICENSES_STAGE_VERSION,
        rel,
        lambda: _license_of(repo_root / rel),
    )
    return tuple(found) if found else None  # a cached value comes back as a list


## @brief Rewrite one edited file's licence row (the fast tier).
## @param conn Open connection, inside the fast tier's transaction.
## @param repo_root The repository.
## @param rel The edited file.
## @param cache The index cache.
## @return None.
## @version 1
## @req REQ-DDB-INDEX-006
def refresh_file_license(
    conn: sqlite3.Connection, repo_root: Path, rel: str, cache: IndexCache
) -> None:
    """@brief The same row `ingest_file_licenses` writes, for one file. @return None."""
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'file_licenses'").fetchone() is None:
        return
    conn.execute("DELETE FROM file_licenses WHERE file_path = ?", (rel,))
    found = license_of(cache, repo_root, rel)
    if found:
        conn.execute(
            "INSERT INTO file_licenses (file_path, license, line) VALUES (?, ?, ?)", (rel, *found)
        )
