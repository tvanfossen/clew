# SPDX-License-Identifier: MIT
"""Supplementary-doc ingestion: every markdown file the build scanned → FTS5.

Markdown files are chunked by H1/H2/H3 heading and inserted into the FTS5
`supplementary_docs` virtual table, read by `docs.search_prose` at query time.

WHICH FILES, AND WHY THAT CHANGED (1.1.0). `SUPPLEMENTARY_PATTERNS` held ten root-anchored
globs, so a design note at `src/notes.md` or an ADR under `architecture/decisions/` was
invisible to `search_prose` while sitting in the repository the index claims to cover. The
file set is now the build's OWN scanned set — which honours the declared scope, the
operator's excludes, the toolchain's ignores and binary classification — plus those globs,
which still name `README` with no extension, `README.rst` and `README.txt`.

NOT A WIDER GLOB. `**/*.md` from the repo root would read every vendored and build-output
markdown file on disk: `node_modules`, a cargo registry copy, `.venv/share/doc`. Taking
markdown from the scanned set means prose coverage and symbol coverage cannot disagree
about what this repository contains.

@brief Markdown chunking + FTS5 ingest for supplementary docs.
@version 4
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from ._common import logger, within_repo

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

## Markdown by extension, taken from the build's own scanned file set rather than from a
## `**/*.md` glob — see `_candidate_docs`. `.mdown`/`.mkd` are deliberately absent: neither
## appears in any target indexed here, and an extension nobody uses is a line nobody tests.
MARKDOWN_EXTS = (".md", ".markdown")

## The deepest heading that starts its own chunk; deeper ones stay inside their section.
_MAX_CHUNK_LEVEL = 3


## @brief Split markdown into sections by heading.
## @version 2
## @return List of (heading, content) pairs, one per level-1-to-3 heading section.
## @req REQ-DDB-PIPE-001
def chunk_markdown(text: str, file_path: str) -> list[tuple[str, str]]:
    """Split markdown into sections by heading.

    Each chunk is a (heading, content) pair. Content between the start
    of the file and the first heading uses the filename as the heading,
    and includes any front matter. Headings of level 1-3 trigger splits;
    deeper headings stay inside their section.

    THE HEADINGS ARE THE GRAMMAR'S, NOT A REGEX'S. lang-parsing-substrate's
    `markdown_sections` parses the file, so a `#` line inside a code fence
    (a shell comment, a C preprocessor line) no longer splits a section,
    and setext headings (`Title` over `=====`) now do.

    @brief Chunk a markdown file by heading into (heading, content) pairs.
    @version 3
    """
    from lang_parsing_substrate import markdown_sections

    data = text.encode("utf-8")
    heads = [s for s in markdown_sections(text) if 1 <= s.level <= _MAX_CHUNK_LEVEL]
    ## (heading, body start byte, body end byte); each body runs to the next split heading.
    spans = [(Path(file_path).name, 0, heads[0].start_byte if heads else len(data))]
    for i, head in enumerate(heads):
        end = heads[i + 1].start_byte if i + 1 < len(heads) else len(data)
        spans.append((head.heading_text.strip(), head.heading_end_byte, end))

    chunks: list[tuple[str, str]] = []
    for heading, start, end in spans:
        content = data[start:end].decode("utf-8").strip()
        if content:
            chunks.append((heading, content))
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


## @brief Every file to consider as prose: the named globs, plus the scan's markdown.
## @param repo_root Repository root.
## @param patterns Root-anchored globs naming prose that is not markdown by extension.
## @param files Repo-relative POSIX paths of the build's scanned file set, or None.
## @return Candidate paths, globs first, each at most once.
## @version 1
## @req REQ-DDB-PIPE-001
def _candidate_docs(
    repo_root: Path,
    patterns: list[str],
    files: list[str] | None,
) -> list[Path]:
    """WHY THE SCANNED SET RATHER THAN A WIDER GLOB. `**/*.md` from the repo root reads
    every vendored and build-output markdown file on disk — `node_modules`, a cargo
    registry copy, `.venv/share/doc`. The scanned set is the build's own answer to what is
    in scope: it already honours the declared scope, the operator's excludes, the
    toolchain's ignores and binary classification. Taking markdown from it means prose
    coverage and symbol coverage cannot disagree about what this repository contains.

    The globs are still read. They name `README` with no extension, `README.rst` and
    `README.txt` — prose that no markdown rule would find.

    @brief The ordered candidate set.
    @return Paths, deduplicated, globs first.
    """
    found: list[Path] = []
    seen: set[Path] = set()
    for pattern in patterns:
        for path in sorted(repo_root.glob(pattern)):
            if path not in seen:
                seen.add(path)
                found.append(path)
    for rel in sorted(files or ()):
        if not rel.lower().endswith(MARKDOWN_EXTS):
            continue
        path = repo_root / rel
        if path not in seen:
            seen.add(path)
            found.append(path)
    return found


## @brief Scan repo for markdown/text docs, chunk by heading, insert into FTS5.
## @version 2
## @req REQ-DDB-PIPE-001
def ingest_supplementary_docs(
    db_path: Path,
    repo_root: Path,
    patterns: list[str] | None = None,
    files: list[str] | None = None,
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
    for file_path in _candidate_docs(repo_root, patterns, files):
        if not file_path.is_file():
            continue
        ## `glob` FOLLOWS SYMLINKS and git tracks them, so a committed
        ## `README.md -> /proc/self/environ` was read, chunked, and served as this
        ## repository's prose under an in-repo path (1.1.0 audit, H2). The relative path is
        ## taken from the UNRESOLVED entry on purpose: it is what the index calls the file,
        ## and only files that survive the check get that far.
        if within_repo(file_path, repo_root, setting="supplementary document") is None:
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
