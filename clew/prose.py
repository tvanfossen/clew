# SPDX-License-Identifier: MIT
"""Supplementary-doc ingestion: README/CHANGELOG/docs/*.md → FTS5.

Markdown files matching `SUPPLEMENTARY_PATTERNS` are scanned, chunked
by H1/H2/H3 heading, and inserted into the FTS5 `supplementary_docs`
virtual table. Used by docs.search_prose at query time.

@brief Markdown chunking + FTS5 ingest for supplementary docs.
@version 2
"""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from ._common import logger

SUPPLEMENTARY_PATTERNS: list[str] = [
    "README.md",
    "README.rst",
    "README.txt",
    "README",
    "CHANGELOG.md",
    "CHANGELOG",
    "CONTRIBUTING.md",
    "docs/*.md",
    "doc/*.md",
    "docs/**/*.md",
]

_HEADING_RE = re.compile(r"^(#{1,3})\s+(.+)")


## @brief Split markdown into sections by heading.
## @version 1
## @return List of (heading, content) pairs, one per level-1-to-3 heading section.
## @req REQ-DDB-PIPE-001
def chunk_markdown(text: str, file_path: str) -> list[tuple[str, str]]:
    """Split markdown into sections by heading.

    Each chunk is a (heading, content) pair. Content between the start
    of the file and the first heading uses the filename as the heading.
    Headings of level 1-3 (# through ###) trigger splits; deeper
    headings stay inside their section.

    @brief Chunk a markdown file by heading into (heading, content) pairs.
    @version 2
    """
    chunks: list[tuple[str, str]] = []
    current_heading = Path(file_path).name
    current_lines: list[str] = []

    for line in text.splitlines():
        match = _HEADING_RE.match(line)
        if match:
            content = "\n".join(current_lines).strip()
            if content:
                chunks.append((current_heading, content))
            current_heading = match.group(2).strip()
            current_lines = []
        else:
            current_lines.append(line)

    content = "\n".join(current_lines).strip()
    if content:
        chunks.append((current_heading, content))
    return chunks


## @brief Read + chunk one markdown file; insert chunks; return chunk count.
## @version 3
## @dg_internal
def _ingest_one_doc_file(
    conn: sqlite3.Connection,
    file_path: Path,
    rel_path: str,
) -> int:
    """Read + chunk one markdown file; insert chunks; return chunk count.

    Skip files whose contents aren't valid UTF-8. Previously this
    used `errors="replace"`, which silently substituted U+FFFD for
    every invalid byte — that garbage then flowed all the way to the
    model via `docs.search_prose`, producing hallucinated citations
    (observed 2026-05-14: an `error_definition.md` was GBK and reached
    the model as a long string of U+FFFD replacement characters).

    Logging the skip + the byte that triggered it gives the user
    enough info to re-encode the source file once. Strict mode is
    correct here because the alternative — pretending the file's
    content is "available" when it's actually garbled — is worse.
    """
    try:
        raw = file_path.read_bytes()
    except OSError:
        logger.warning("Could not read %s, skipping", file_path)
        return 0
    try:
        text = raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as ude:
        logger.warning(
            "Skipping %s: not valid UTF-8 (byte 0x%02X at offset %d). "
            "Re-encode the source file or exclude it from the docs build.",
            rel_path,
            raw[ude.start] if ude.start < len(raw) else 0,
            ude.start,
        )
        return 0
    chunks = chunk_markdown(text, rel_path)
    for heading, content in chunks:
        conn.execute(
            "INSERT INTO supplementary_docs (file_path, heading, content) VALUES (?, ?, ?)",
            (rel_path, heading, content),
        )
    return len(chunks)


## @brief Scan repo for markdown/text docs, chunk by heading, insert into FTS5.
## @version 1
## @req REQ-DDB-PIPE-001
def ingest_supplementary_docs(
    db_path: Path,
    repo_root: Path,
    patterns: list[str] | None = None,
) -> int:
    """Scan repo for markdown/text docs, chunk by heading, insert into FTS5.

    Recreates the supplementary_docs FTS5 virtual table on every run
    so the result is idempotent. Skip-list dedupes files matched by
    multiple patterns (e.g. README.md AND docs/**/*.md).

    @brief Scan a repo for supplementary docs and insert into FTS5 table.
    @version 3
    """
    if patterns is None:
        patterns = SUPPLEMENTARY_PATTERNS

    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS supplementary_docs
        USING fts5(file_path, heading, content)
        """,
    )
    conn.execute("DELETE FROM supplementary_docs")
    conn.commit()

    total_chunks = 0
    seen_files: set[str] = set()
    for pattern in patterns:
        for file_path in sorted(repo_root.glob(pattern)):
            if not file_path.is_file():
                continue
            rel_path = str(file_path.relative_to(repo_root))
            if rel_path in seen_files:
                continue
            seen_files.add(rel_path)
            total_chunks += _ingest_one_doc_file(conn, file_path, rel_path)

    conn.commit()
    conn.close()
    logger.info(
        "Ingested %d chunks from %d supplementary files",
        total_chunks,
        len(seen_files),
    )
    return total_chunks
