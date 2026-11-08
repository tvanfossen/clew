# SPDX-License-Identifier: MIT
"""Supplementary-doc ingestion: every markdown and reStructuredText file the build scanned → FTS5.

Markdown files are chunked by H1/H2/H3 heading, and reStructuredText files by their first
three section levels, into the FTS5 `supplementary_docs` virtual table, read by
`docs.search_prose` at query time.

RESTRUCTUREDTEXT IS PROSE, NOT SYMBOLS. A section title or a `.. _label:` target written as a
`memberdef` row would land in the namespace that answers `dossier("my_function")`, which is
why YAML keys are not symbols either (docs/languages/SCRIPT_INTEGRATION.md). An `.rst` file
therefore gets no `path` row, as markdown gets none. Before this, `README.rst` was the one
`.rst` file read at all, and it was chunked as markdown.

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

@brief Markdown and reStructuredText chunking + FTS5 ingest for supplementary docs.
@version 5
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

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


## reStructuredText by extension, taken from the same scanned set. `.rest` and `.txt` are
## deliberately absent: the substrate maps only `.rst` to the grammar, and a `.txt` file is
## not reStructuredText by any rule a reader could check (`README.txt` stays a named glob,
## read as markdown, as before).
RST_EXTS = (".rst",)

## Every extension the scanned set contributes prose by.
PROSE_EXTS = MARKDOWN_EXTS + RST_EXTS

## The substrate's language key for reStructuredText (lang-parsing-substrate 0.15.0).
_RST_KEY = "rst"

## The grammar's node types this module reads. A `section` holds its `title` and its
## `adornment` line(s). Every explicit target is a `target`: an internal one
## (`.. _install:`) has a `name` child only, an external (`.. _ext: https://...`) or
## indirect (`.. _a: b_`) one has a `name` and a `link`, and an anonymous one
## (`__ http://...`) has a `link` only.
_RST_SECTION = "section"
_RST_TITLE = "title"
_RST_ADORNMENT = "adornment"
_RST_TARGET = "target"
_RST_TARGET_NAME = "name"
_RST_TARGET_LINK = "link"


## @brief Split reStructuredText into sections by title.
## @param text The file's text.
## @param file_path Repo-relative path; its name heads the content before the first title.
## @return List of (heading, content) pairs, one per level-1-to-3 section.
## @version 1
## @req REQ-DDB-PIPE-001
def chunk_rst(text: str, file_path: str) -> list[tuple[str, str]]:
    """THE SAME SHAPE AS `chunk_markdown`, so the corpus reads one way whatever wrote it:
    the content before the first title is headed by the file name, levels 1-3 split, a
    deeper section stays inside its parent's chunk, and an empty section is dropped.

    A LEVEL IS AN ORDER OF APPEARANCE, NOT A CHARACTER. reStructuredText has no fixed
    `=`-is-level-1 rule: docutils gives each adornment style a level in the order the
    document first uses it, and a title with an overline is a different style from one
    underlined with the same character. `_rst_levels` applies that rule.

    AN EXPLICIT TARGET BELONGS TO THE SECTION IT LABELS. `.. _install:` directly above a
    title is how `:ref:` reaches that section, so the target opens the section's chunk
    rather than closing the previous one, and a search for the label lands on the text it
    names.

    WITHOUT THE GRAMMAR (a substrate built without `lang-rst`) the file is one chunk under
    its name: still searchable, and never split by a guess at what a title looks like.

    @brief Chunk a reStructuredText file by section title into (heading, content) pairs.
    """
    from .substrate import has_language

    name = Path(file_path).name
    if not has_language(_RST_KEY):
        whole = text.strip()
        return [(name, whole)] if whole else []
    from .tsnode import Parser

    data = text.encode("utf-8")
    root = Parser(_RST_KEY).parse(data).root_node
    heads = [s for s, level in _rst_levels(root) if level <= _MAX_CHUNK_LEVEL]
    starts = [_labelled_start(s) for s in heads]
    chunks = [(name, _span_text(data, 0, starts[0] if heads else len(data)))]
    for i, section in enumerate(heads):
        end = starts[i + 1] if i + 1 < len(heads) else len(data)
        labels = _span_text(data, starts[i], section.start_byte)
        body = _span_text(data, _heading_end(section), end)
        chunks.append((_rst_title(section), "\n\n".join(p for p in (labels, body) if p)))
    return [(heading, content) for heading, content in chunks if content]


## @brief Every section of a parsed document with its docutils level, in document order.
## @param root The document's root node.
## @return (section node, 1-based level) pairs.
## @version 1
## @dg_internal
def _rst_levels(root: Any) -> list[tuple[Any, int]]:
    """A STYLE is the adornment character plus whether the title is overlined; levels are
    handed out in the order styles first appear, which is docutils' own rule. The walk
    collects sections at any depth, so a grammar that nests sections inside their parent
    reads the same as one that lists them flat.

    @brief Sections paired with their levels.
    """
    from .scriptast import walk_nodes

    sections = sorted(
        (n for n in walk_nodes(root) if n.type == _RST_SECTION), key=lambda n: n.start_byte
    )
    styles: dict[tuple[str, bool], int] = {}
    out: list[tuple[Any, int]] = []
    for section in sections:
        style = _rst_style(section)
        level = styles.setdefault(style, len(styles) + 1)
        out.append((section, level))
    return out


## @brief The adornment style of one section: its character, and whether it is overlined.
## @param section A `section` node.
## @return (adornment character, overlined).
## @version 1
## @dg_internal
def _rst_style(section: Any) -> tuple[str, bool]:
    """@brief A section's adornment style."""
    kids = section.children
    rules = [k for k in kids if k.type == _RST_ADORNMENT]
    char = rules[-1].text[:1].decode("utf-8", errors="replace") if rules else ""
    return char, bool(kids) and kids[0].type == _RST_ADORNMENT


## @brief The title text of one section, whitespace collapsed.
## @param section A `section` node.
## @return The title, or "" when the node has none.
## @version 1
## @dg_internal
def _rst_title(section: Any) -> str:
    """@brief A section's title."""
    for kid in section.children:
        if kid.type == _RST_TITLE:
            return " ".join(kid.text.decode("utf-8", errors="replace").split())
    return ""


## @brief Where a section's title lines end and its body begins.
## @param section A `section` node.
## @return The byte after the last title or adornment line.
## @version 1
## @dg_internal
def _heading_end(section: Any) -> int:
    """Measured from the title and its adornments rather than from the section node, so a
    grammar whose section spans its whole body still yields the body.

    @brief End byte of a section's heading.
    """
    ends = [k.end_byte for k in section.children if k.type in (_RST_TITLE, _RST_ADORNMENT)]
    return max(ends, default=section.end_byte)


## @brief Where a section's chunk starts: its first labelling target, else its title.
## @param section A `section` node.
## @return The start byte of the run of internal targets directly above it, or its own.
## @version 1
## @dg_internal
def _labelled_start(section: Any) -> int:
    """Only INTERNAL targets (`.. _name:`, nothing after the colon) label a section. An
    external, indirect or anonymous target is a link destination for the text that
    references it, and stays with the paragraph before it.

    @brief Chunk start for one section.
    """
    start = section.start_byte
    node = section.prev_sibling
    while node is not None and node.type == _RST_TARGET and _is_internal_target(node):
        start = node.start_byte
        node = node.prev_sibling
    return start


## @brief Whether a target node is an internal one (`.. _name:`), the kind that labels.
## @param node A `target` node.
## @return True when it carries a name and no link.
## @version 1
## @dg_internal
def _is_internal_target(node: Any) -> bool:
    """@brief Internal-target test."""
    kinds = {k.type for k in node.children}
    return _RST_TARGET_NAME in kinds and _RST_TARGET_LINK not in kinds


## @brief The stripped UTF-8 text of a byte range, "" for an empty or inverted one.
## @param data The file's bytes.
## @param start First byte.
## @param end Byte after the last.
## @return The text, stripped.
## @version 1
## @dg_internal
def _span_text(data: bytes, start: int, end: int) -> str:
    """@brief Text of a byte span."""
    return data[start:end].decode("utf-8").strip() if end > start else ""


## reStructuredText files are chunked by their own grammar; before, every file went through
## `chunk_markdown`, including the globbed `README.rst`.
## @brief Read + chunk one prose file; insert chunks; return chunk count.
## @version 4
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
    chunker = chunk_rst if rel_path.lower().endswith(RST_EXTS) else chunk_markdown
    chunks = chunker(text, rel_path)
    for heading, content in chunks:
        conn.execute(
            "INSERT INTO supplementary_docs (file_path, heading, content) VALUES (?, ?, ?)",
            (rel_path, heading, content),
        )
    return len(chunks)


## The scanned set now contributes reStructuredText as well as markdown.
## @brief Every file to consider as prose: the named globs, plus the scan's markdown and rst.
## @param repo_root Repository root.
## @param patterns Root-anchored globs naming prose that is not markdown by extension.
## @param files Repo-relative POSIX paths of the build's scanned file set, or None.
## @return Candidate paths, globs first, each at most once.
## @version 2
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
        if not rel.lower().endswith(PROSE_EXTS):
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
