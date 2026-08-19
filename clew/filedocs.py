# SPDX-License-Identifier: MIT
"""File-level documentation ingestion: module docstrings and `@file` blocks.

gh#10. `search` indexed function NAMES and per-function `@brief` text and
nothing else, so a query phrased as a CONCEPT missed code that is entirely
about that concept. Measured on this repository's own index:
`search("deadlock")` returned zero while `query/locks.py` is a module about
lock nesting, and `search("function pointer")` did not reach
`callback_edges.py`, whose module docstring is an essay on resolving
function-pointer calls. The implementations are named for mechanics —
`_harvest_registration`, `lock_nestings` — which is good naming for a
maintainer and unreachable for a conceptual query.

The prose that answers those queries already exists in the source; nothing
read it. This stage does, storing it TWICE on purpose because two different
query shapes need it:

  * `file_docs` — one row per file, read by `query.search` with the same
    AND-over-tokens semantics as a symbol hit, so a conceptual query returns
    the FILE as a hit alongside the function hits.
  * `supplementary_docs` — the FTS5 prose corpus, so `search_prose` reaches
    the same text ranked by relevance with a snippet.

Only DOXYGEN-STYLE comment blocks count for C-family files (`/**`, `/*!`,
`///`, `//!`). A plain `/* ... */` header is excluded by construction, which
is what keeps a license notice out of the corpus without needing a heuristic
that guesses at what a license looks like — otherwise `search("copyright")`
would return every file in the repository.

BOUNDED LIMITATION, stated rather than worked around: only the leading block
is read. A `@file` comment placed after the include list is not found. That is
a deliberate stopping point, not an oversight — the alternative is scanning
every comment in every file and deciding which one is "the file's", which has
no honest answer.

@brief Module-docstring and file-level doxygen-comment ingest into the index.
@version 1
"""

from __future__ import annotations

import ast
import re
import sqlite3
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from ._common import logger

## Doxygen's path rows for symbols it harvested from system headers are bracketed
## (`[STL]`, `[generated]`); the SHAPE is filtered, not any one literal. Mirrors
## `query.corpus.SYNTHETIC_PATH` — a synthetic row names no readable file.
SYNTHETIC_PATH = re.compile(r"^\[.*\]$")

## `path.type` for a file row (as opposed to a directory row).
PATH_TYPE_FILE = 1

## A leading run of `///` or `//!` line comments — doxygen's line form.
_CXX_LINE_DOC = re.compile(r"^[ \t]*//[/!](?P<body>.*)$")

## A leading `/**` or `/*!` block — doxygen's block form. A bare `/*` is NOT
## matched, which is what excludes a license header.
_CXX_BLOCK_DOC = re.compile(r"^[ \t]*/\*[*!](?!\*/)(?P<body>.*?)\*/", re.DOTALL)

## One line that may precede the doc block without ending the search for it: a blank,
## or the `#`-comment / non-doxygen `//` line a source file conventionally opens with.
## Requires the newline, so the final unterminated line cannot loop forever.
_SKIPPABLE_LINE = re.compile(r"^[ \t]*(//[^/!].*|#.*)?\n")

## A plain `/* ... */` block — NOT `/**` or `/*!`. Skipped over rather than read: this is
## the shape a license notice takes, and the whole license defence is that it is not
## doxygen-marked. It must not TERMINATE the search either, because the real `@file`
## block routinely sits directly beneath one.
_PLAIN_BLOCK = re.compile(r"^[ \t]*/\*(?![*!]).*?\*/[ \t]*\n?", re.DOTALL)


## @brief Collapse whitespace and strip comment furniture from a doc block.
## @param text Raw block text.
## @return Single-spaced text with leading `*` gutters removed.
## @version 1
## @dg_internal
def _clean(text: str) -> str:
    """Removes the leading `*` gutter a doxygen block conventionally carries on
    each continuation line, then collapses whitespace runs so a multi-line block
    stores as one searchable string.

    Markup is deliberately NOT stripped: this text is prose, and a `<stdio.h>`
    or a generic `<T>` inside it is CONTENT. Same reasoning as
    `query.corpus._collapse`, which had to make the identical call.

    @brief Normalise a raw documentation block to one searchable line.
    @return Cleaned single-spaced text.
    @version 1
    """
    lines = [re.sub(r"^[ \t]*\*[ \t]?", "", line) for line in text.splitlines()]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


## @brief Drop the leading non-doxygen preamble from C-family source text.
## @param text Full decoded file contents.
## @return The text from the first line that is neither blank, a non-doxygen comment, nor a plain block comment.
## @version 1
## @dg_internal
def _strip_preamble(text: str) -> str:
    """Loops because the two skippable shapes interleave: an SPDX line, then a
    copyright block, then a blank, then the real block. Each branch consumes at least
    one character and `_SKIPPABLE_LINE` requires a newline, so the loop terminates on
    the last line even when the file has no trailing newline.

    @brief Skip the license/SPDX preamble above a file-level doxygen block.
    @return Remaining text.
    @version 1
    """
    while True:
        match = _PLAIN_BLOCK.match(text) or _SKIPPABLE_LINE.match(text)
        if not match:
            return text
        text = text[match.end() :]


## @brief Extractor of the file-level documentation for one family of languages.
## @version 1
class FileDocExtractor(ABC):
    """Base class carrying the whole template: which suffixes it claims, and the
    read-normalise-gate sequence every concrete extractor shares. A subclass
    supplies ONLY the language-specific act of locating the raw block.

    @brief Base file-level documentation extractor.
    @version 1
    """

    ## Suffixes this extractor claims, lower-cased and dot-prefixed.
    EXTENSIONS: ClassVar[tuple[str, ...]] = ()

    ## @brief The file-level documentation for one file's text, or "".
    ## @param text Full decoded file contents.
    ## @return Cleaned documentation text; "" when the file carries none.
    ## @version 1
    ## @req REQ-DDB-PIPE-008
    def doc_for(self, text: str) -> str:
        """Template method: locate, then normalise. Returning "" rather than None
        for "no documentation" keeps the caller's filter a plain truth test, and a
        file with no module doc is the common case, not an error.

        @brief Extract and normalise one file's leading documentation.
        @return Cleaned text, or "" when there is none.
        @version 1
        """
        return _clean(self._raw(text))

    ## @brief Locate the raw, un-normalised documentation block.
    ## @param text Full decoded file contents.
    ## @return Raw block text, or "" when absent.
    ## @version 1
    ## @dg_internal
    @abstractmethod
    def _raw(self, text: str) -> str:
        """@brief Language-specific location of the leading doc block.
        @return Raw block text or "".
        @version 1
        """


## @brief Module-docstring extractor for Python sources.
## @version 1
class PythonFileDoc(FileDocExtractor):
    """Uses `ast`, not a regex. The module docstring is a language construct with
    a definition, and every regex approximation of it is wrong about at least one
    of raw strings, concatenation, and a leading `from __future__` import.

    @brief Python module-docstring extractor.
    @version 1
    """

    EXTENSIONS: ClassVar[tuple[str, ...]] = (".py", ".pyi")

    ## @brief The module docstring, or "" when the file has none or will not parse.
    ## @param text Full decoded file contents.
    ## @return Docstring text or "".
    ## @version 1
    ## @dg_internal
    def _raw(self, text: str) -> str:
        """A `SyntaxError` yields "" rather than propagating: this stage annotates
        an index, and one unparseable file must not fail a build that doxygen
        already indexed successfully.

        @brief Read the module docstring via the AST.
        @return Docstring or "".
        @version 1
        """
        try:
            return ast.get_docstring(ast.parse(text)) or ""
        except (SyntaxError, ValueError):
            return ""


## @brief Leading doxygen-comment extractor for C-family sources, plus Rust.
## @version 2
class CFamilyFileDoc(FileDocExtractor):
    """Accepts ONLY a doxygen-marked comment (`/**`, `/*!`, `///`, `//!`). The
    exclusion of a bare `/*` block is the whole license-header defence: a
    copyright notice is a comment and is not documentation, and deciding which
    is which by content would need a heuristic about what a license looks like.
    The marker the author already wrote answers it exactly.

    RUST'S `//!` IS THE SAME SYNTAX, not a lookalike: `//!`/`///` and
    `/*!`/`/**` are Rust's own module- and item-doc-comment markers, spelled
    identically to doxygen's, so `_CXX_LINE_DOC`/`_CXX_BLOCK_DOC` need no
    Rust-specific branch — only `.rs` needed adding to this list. (Confirmed
    against `knots`, whose `coupling.rs`/`config.rs`/`duplicate_diff.rs`/
    `duplicates.rs` already carry real `//!` module docs that `file_docs`
    was silently not ingesting before this.)

    @brief C/C++/Rust file-level leading-doc-comment extractor.
    @version 2
    """

    EXTENSIONS: ClassVar[tuple[str, ...]] = (
        ".c",
        ".cc",
        ".cpp",
        ".cxx",
        ".h",
        ".hh",
        ".hpp",
        ".hxx",
        ".rs",
    )

    ## @brief The leading doxygen comment, block form or line-run form.
    ## @param text Full decoded file contents.
    ## @return Raw comment body or "".
    ## @version 1
    ## @dg_internal
    def _raw(self, text: str) -> str:
        """The preamble — blanks, `#` and non-doxygen `//` lines, and plain `/* */`
        blocks — is skipped OVER rather than treated as the end of the search, so an
        SPDX line or a copyright block above the real `@file` block does not hide it.
        That is the same shape as the `#`-divider trap that used to make doxygen-guard
        read the wrong block, and it is why the license case needed a control test
        rather than an assumption.

        @brief Locate the leading doxygen comment in C-family source.
        @return Raw body text or "".
        @version 2
        """
        rest = _strip_preamble(text)
        block = _CXX_BLOCK_DOC.match(rest)
        return block.group("body") if block else self._line_run(rest.splitlines())

    ## @brief Join a contiguous run of `///` / `//!` lines from the top.
    ## @param lines Source lines, starting at the first non-skippable one.
    ## @return Joined comment bodies, or "" when the first line is not one.
    ## @version 1
    ## @dg_internal
    def _line_run(self, lines: list[str]) -> str:
        """@brief Collect doxygen line comments until the run ends.
        @return Joined bodies or "".
        @version 1
        """
        bodies: list[str] = []
        for line in lines:
            match = _CXX_LINE_DOC.match(line)
            if not match:
                break
            bodies.append(match.group("body"))
        return "\n".join(bodies)


## Concrete extractors, resolved by suffix. A suffix no extractor claims yields no
## row — silently, and correctly: a `.json` fixture has no file-level documentation
## to find, and inventing one would put noise on a search surface.
_EXTRACTORS: tuple[FileDocExtractor, ...] = (PythonFileDoc(), CFamilyFileDoc())


## @brief The file-level documentation for one repo-relative source file.
## @param rel_path Repo-relative path, used only to choose an extractor.
## @param text Full decoded file contents.
## @return Cleaned documentation text; "" when the language is unclaimed or the file has none.
## @version 1
## @req REQ-DDB-PIPE-008
def extract_file_doc(rel_path: str, text: str) -> str:
    """Dispatch on suffix. Exposed separately from the ingest stage so the
    extraction is testable against a string without a database anywhere near it.

    @brief Extract one file's file-level documentation.
    @return Cleaned text or "".
    @version 1
    """
    suffix = Path(rel_path).suffix.lower()
    for extractor in _EXTRACTORS:
        if suffix in extractor.EXTENSIONS:
            return extractor.doc_for(text)
    return ""


## @brief Create the `file_docs` table if it is absent.
## @param conn Open connection to the index.
## @return None.
## @version 1
## @req REQ-DDB-SCHEMA-014
def ensure_file_docs_table(conn: sqlite3.Connection) -> None:
    """No enumerated column, so nothing here comes from `vocabulary` — there is
    no `CHECK` to generate. `IF NOT EXISTS` plus a `DELETE` at ingest time makes
    the stage idempotent across rebuilds of the same database.

    @brief Ensure the file-level documentation table exists.
    @version 1
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS file_docs (  file_path TEXT NOT NULL,  doc       TEXT NOT NULL)"
    )


## @brief The indexed, non-synthetic source files, repo-relative.
## @param conn Open connection to the index.
## @return Repo-relative paths in path order.
## @version 1
## @dg_internal
def _indexed_files(conn: sqlite3.Connection) -> list[str]:
    """Reads the INDEXED inventory rather than globbing the working tree, so this
    stage cannot widen the scope decision the build already made. A file doxygen
    was never asked to parse must not acquire a searchable row here.

    @brief List the indexed file paths.
    @return Repo-relative path list.
    @version 1
    """
    rows = conn.execute(
        "SELECT name FROM path WHERE type = ? AND name <> '' ORDER BY name",
        (PATH_TYPE_FILE,),
    ).fetchall()
    return [name for (name,) in rows if not SYNTHETIC_PATH.match(name)]


## @brief Read one file's text, or None when it is unreadable or not UTF-8.
## @param path Absolute path to the file.
## @param rel_path Repo-relative path, for the log line.
## @return Decoded text, or None.
## @version 1
## @dg_internal
def _read_text(path: Path, rel_path: str) -> str | None:
    """Strict UTF-8, for the reason `prose._ingest_one_doc_file` documents at
    length: `errors="replace"` once fed a long run of U+FFFD to a model, which
    produced hallucinated citations. A skip with the offending byte named is
    something an owner can act on; garbage that looks like content is not.

    @brief Decode one source file strictly.
    @return Text or None.
    @version 1
    """
    try:
        raw = path.read_bytes()
    except OSError:
        logger.warning("file_docs: could not read %s, skipping", rel_path)
        return None
    try:
        return raw.decode("utf-8", errors="strict")
    except UnicodeDecodeError as ude:
        logger.warning(
            "file_docs: skipping %s: not valid UTF-8 (byte 0x%02X at offset %d)",
            rel_path,
            raw[ude.start] if ude.start < len(raw) else 0,
            ude.start,
        )
        return None


## @brief Ingest every indexed file's file-level documentation.
## @param db_path Path to the index being built.
## @param repo_root Working-tree root the indexed paths are relative to.
## @return Number of files that yielded documentation.
## @version 1
## @req REQ-DDB-PIPE-008
def ingest_file_docs(db_path: Path, repo_root: Path) -> int:
    """MUST RUN AFTER `prose.ingest_supplementary_docs`, which DROPs and recreates
    `supplementary_docs` on every build — above it, these rows would be inserted
    and then deleted, and the observable result would be an empty search with no
    error anywhere. The same trap `kconfig.ingest_kconfig_prose` documents.

    MUST ALSO RUN AFTER `coverage.report_index_coverage`, which is a SECOND and
    less obvious ordering constraint. Coverage excludes files that yielded PROSE
    instead of symbols, by reading `supplementary_docs` — a markdown file is not
    barren, it is not code. Run above it, every source file with a module
    docstring would suddenly count as "yielded prose" and the barren ratio, whose
    whole job is to say how much of the index is empty, would silently improve
    without a single extra symbol being indexed.

    The path is repeated inside the content because FTS5 ranks over the columns it
    is given, and someone searching for a capability types words from the prose
    while someone auditing a file types its name. Both have to hit.

    @brief Ingest module docstrings and file-level doxygen comments.
    @return Count of files that yielded documentation.
    @version 1
    """
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_file_docs_table(conn)
        conn.execute("DELETE FROM file_docs")
        rows = _collect_file_docs(conn, repo_root)
        conn.executemany("INSERT INTO file_docs (file_path, doc) VALUES (?, ?)", rows)
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS supplementary_docs "
            "USING fts5(file_path, heading, content)"
        )
        conn.executemany(
            "INSERT INTO supplementary_docs (file_path, heading, content) VALUES (?, ?, ?)",
            [(rel, f"{rel} — file-level documentation", f"{rel}\n{doc}") for rel, doc in rows],
        )
        conn.commit()
    finally:
        conn.close()
    logger.info("file_docs: %d file(s) yielded file-level documentation", len(rows))
    return len(rows)


## @brief Every indexed file that carries file-level documentation.
## @param conn Open connection to the index.
## @param repo_root Working-tree root the indexed paths are relative to.
## @return List of (repo-relative path, cleaned documentation) pairs.
## @version 1
## @dg_internal
def _collect_file_docs(conn: sqlite3.Connection, repo_root: Path) -> list[tuple[str, str]]:
    """Split out of `ingest_file_docs` so the transaction handling and the
    per-file work are separately readable, and so the loop stays inside the
    complexity budget.

    @brief Collect (path, documentation) pairs for the indexed files.
    @return List of pairs; files with no documentation are absent.
    @version 1
    """
    collected: list[tuple[str, str]] = []
    for rel in _indexed_files(conn):
        text = _read_text(repo_root / rel, rel)
        if text is None:
            continue
        doc = extract_file_doc(rel, text)
        if doc:
            collected.append((rel, doc))
    return collected
