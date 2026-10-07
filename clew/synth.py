# SPDX-License-Identifier: MIT
"""The parse-built front end: doxygen-shaped rows for languages doxygen cannot read.

Doxygen has no JavaScript or TypeScript parser, so a `.js` / `.ts` / `.tsx` file got no
`path` row, and therefore no harvest, no call edges and no symbols at all. This module
writes the same tables doxygen and `rustdoc.py` write (`path`, `refid`, `memberdef`,
`compounddef`, `member`, `compoundref`) from lang-parsing-substrate's parse, so every
downstream stage runs on them unchanged.

IT ADDS; IT NEVER REPLACES. It runs after doxygen (or rustdoc), and allocates ids the way
`ast_symbols` does (`INSERT INTO refid` and take the rowid), so a mixed repo gets C from
doxygen and JS/TS from here in one index. Rows are stamped `dg_source='parse'`: written by
a front end that read the documentation (JSDoc), unlike an `ast` recovery row, which has
none.

TWO STAGES, because the harvest reads the `path` table. `register_paths` runs before
the shared parse so the JS/TS files are in the file set; the definitions are harvested
there (the `js_symbols` stage, cached per file content); `emit_definitions` then writes
them, before any call layer resolves against `memberdef`.

SHAPES FOLLOW DOXYGEN'S PYTHON ROWS, which the query layer already reads: `definition`
and `scope` are dotted (`src.util.strings.Formatter.trim`), compound names `::`-joined
(`src::util::strings::Formatter`), descriptions `<para>`-wrapped with the version in a
`<simplesect kind="version">`, and every other tag (`@req`) kept as literal text, which is
exactly what doxygen does with a tag it does not define.

@brief Parse-built path/memberdef/compounddef rows for JS and TS.
@version 1
"""

from __future__ import annotations

import html
import re
import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest
from .vocabulary import STAGE_JS_SYMBOLS, SYMBOL_SOURCE_COLUMN, SYMBOL_SOURCE_PARSE

## The extensions this front end claims. `.mts`/`.cts` are TypeScript's ES-module and
## CommonJS spellings; `.d.ts` declaration files hold signatures without bodies, which
## yield no definitions, so they need no special case.
SYNTH_EXTS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx")

_TYPE_FILE = 1


## @brief Per-file harvester for JS/TS definitions.
## @version 1
class _JsSymbolHarvester(Harvester):
    """Rowid-free (names, spans, raw docs), so it caches on content like every stage.
    A non-JS file yields an empty payload.

    @brief JS/TS definitions harvester.
    @version 1
    """

    stage = STAGE_JS_SYMBOLS
    stage_version = 1
    label = "js/ts definitions"

    ## @brief Harvest one file's definitions.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's bytes.
    ## @return The definitions payload, or {} for a non-JS file.
    ## @version 1
    ## @req REQ-DDB-PIPE-012
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        from .jsast import harvest_definitions, is_js_tree

        return harvest_definitions(tree, src_bytes) if is_js_tree(tree) else {}


## @brief The JS/TS definitions stage's harvester.
## @return A Harvester; build it the same way everywhere so the cache key agrees.
## @version 1
## @req REQ-DDB-PIPE-012
def js_symbol_harvester() -> Harvester:
    """@brief Build this stage's harvester."""
    return _JsSymbolHarvester()


## @brief Whether a repo-relative path is one this front end claims.
## @param rel Path, any separator.
## @return True for a JS/TS source file.
## @version 1
## @dg_internal
def claims(rel: str) -> bool:
    """@brief JS/TS extension test."""
    return rel.lower().endswith(SYNTH_EXTS)


## @brief Insert `path` rows for the JS/TS files of this build's scanned tree.
## @param db_path The database being built.
## @param files Repo-relative POSIX paths of every file in scope.
## @return How many rows were inserted.
## @version 1
## @req REQ-DDB-PIPE-012
def register_paths(db_path: Path, files: list[str]) -> int:
    """Rows already present (a doxygen that somehow saw the file) are left alone, so
    running this over any build is safe.

    @brief Put the JS/TS files into the harvest's file set.
    @return Rows inserted.
    """
    wanted = sorted(f for f in files if claims(f))
    if not wanted:
        return 0
    conn = sqlite3.connect(str(db_path))
    try:
        present = {r[0] for r in conn.execute("SELECT name FROM path")}
        new = [f for f in wanted if f not in present]
        conn.executemany(
            "INSERT INTO path (type, local, found, name) VALUES (?, 1, 1, ?)",
            [(_TYPE_FILE, f) for f in new],
        )
        conn.commit()
    finally:
        conn.close()
    if new:
        logger.info("parse front end: %d JS/TS file(s) registered", len(new))
    return len(new)


## @brief Write every harvested JS/TS definition into the index.
## @param db_path The database being built.
## @param repo_root Repository root.
## @param cache The index cache (the shared parse warmed it), or None.
## @return (functions written, classes written).
## @version 2
## @req REQ-DDB-PIPE-012
def emit_definitions(db_path: Path, repo_root: Path, cache: Any = None) -> tuple[int, int]:
    """@brief Turn the cached js_symbols payloads into rows."""
    from .ast_symbols import ensure_symbol_provenance

    conn = sqlite3.connect(str(db_path))
    try:
        if not _has_claimed_path(conn):
            return 0, 0
        ensure_symbol_provenance(conn)
        harvested = run_harvest(conn, repo_root, js_symbol_harvester(), cache)
        writer = _Writer(conn)
        for path_rowid, payload in harvested:
            if payload:
                writer.file(path_rowid, payload)
        writer.inheritance()
        conn.commit()
    finally:
        conn.close()
    logger.info(
        "parse front end: %d JS/TS function(s), %d class(es)", writer.functions, writer.classes
    )
    return writer.functions, writer.classes


## @brief Whether any registered file is one this front end claims.
## @return True when a JS/TS path row exists.
## @version 1
## @dg_internal
def _has_claimed_path(conn: sqlite3.Connection) -> bool:
    return any(claims(r[0]) for r in conn.execute("SELECT name FROM path WHERE type = 1"))


## @brief The dotted module name of a repo-relative file: `src/a/b.ts` -> `src.a.b`.
## @param rel Repo-relative path.
## @return The module path.
## @version 1
## @dg_internal
def module_of(rel: str) -> str:
    """@brief Dotted module path of a file."""
    stem = rel
    for ext in sorted(SYNTH_EXTS, key=len, reverse=True):
        if stem.lower().endswith(ext):
            stem = stem[: -len(ext)]
            break
    return re.sub(r"[^\w$]+", ".", stem.replace("\\", "/")).strip(".")


class _Writer:
    """Allocates ids additively and remembers compounds across files for inheritance."""

    ## @brief Start a writer on an open connection.
    ## @version 1
    ## @dg_internal
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.functions = 0
        self.classes = 0
        self.compound_rowid: dict[str, list[int]] = {}
        self.pending_bases: list[tuple[int, list[str]]] = []

    ## @brief Allocate a refid row for one definition.
    ## @return The new rowid.
    ## @version 1
    ## @dg_internal
    def _refid(self, key: str) -> int:
        """`refid.refid` is NOT NULL UNIQUE; the key is file, position and name, which no
        two definitions share."""
        return int(self.conn.execute("INSERT INTO refid (refid) VALUES (?)", (key,)).lastrowid)

    ## @brief Write one file's harvested classes and functions.
    ## @version 1
    ## @dg_internal
    def file(self, path_rowid: int, payload: dict[str, Any]) -> None:
        rel = self.conn.execute("SELECT name FROM path WHERE rowid = ?", (path_rowid,)).fetchone()[
            0
        ]
        module = module_of(rel)
        local: dict[str, int] = {}
        for cls in payload.get("classes", []):
            local[cls["name"]] = self._compound(path_rowid, module, cls)
        for fn in payload.get("functions", []):
            self._function(path_rowid, module, fn, local.get(fn["cls"]))

    ## @brief Insert one class-like compounddef row.
    ## @return Its rowid.
    ## @version 1
    ## @dg_internal
    def _compound(self, path_rowid: int, module: str, cls: dict[str, Any]) -> int:
        rowid = self._refid(f"jscls_{path_rowid}_{cls['line']}_{cls['col']}_{cls['name']}")
        owner = f"{cls['outer']}::" if cls["outer"] else ""
        name = f"{module.replace('.', '::')}::{owner}{cls['name']}"
        brief, detail = render_doc(cls["doc"])
        self.conn.execute(
            "INSERT INTO compounddef (rowid, name, kind, prot, file_id, line, column, "
            "briefdescription, detaileddescription) VALUES (?, ?, ?, 0, ?, ?, ?, ?, ?)",
            (rowid, name, cls["kind"], path_rowid, cls["line"], cls["col"], brief, detail),
        )
        self.compound_rowid.setdefault(cls["name"], []).append(rowid)
        if cls["bases"]:
            self.pending_bases.append((rowid, cls["bases"]))
        self.classes += 1
        return rowid

    ## @brief Insert one function memberdef row, and its member link.
    ## @version 1
    ## @dg_internal
    def _function(
        self, path_rowid: int, module: str, fn: dict[str, Any], owner: int | None
    ) -> None:
        rowid = self._refid(f"jsfn_{path_rowid}_{fn['line']}_{fn['col']}_{fn['name']}")
        scope = f"{module}.{fn['cls']}" if fn["cls"] else module
        brief, detail = render_doc(fn["doc"])
        self.conn.execute(
            "INSERT INTO memberdef (rowid, name, definition, type, argsstring, scope, kind, "
            "prot, static, bodystart, bodyend, bodyfile_id, file_id, line, column, "
            f"briefdescription, detaileddescription, {SYMBOL_SOURCE_COLUMN}) "
            "VALUES (?, ?, ?, ?, ?, ?, 'function', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rowid,
                fn["name"],
                f"{scope}.{fn['name']}",
                fn["ret"],
                fn["args"],
                scope,
                1 if fn["name"].startswith("#") else 0,
                fn["static"],
                fn["line"],
                fn["end"],
                path_rowid,
                path_rowid,
                fn["line"],
                fn["col"],
                brief,
                detail,
                SYMBOL_SOURCE_PARSE,
            ),
        )
        if owner is not None:
            self.conn.execute(
                "INSERT OR IGNORE INTO member (scope_rowid, memberdef_rowid, prot, virt) "
                "VALUES (?, ?, 0, 0)",
                (owner, rowid),
            )
        self.functions += 1

    ## @brief Link each derived class to a uniquely named base.
    ## @version 1
    ## @dg_internal
    def inheritance(self) -> None:
        """A base resolves only when exactly one JS/TS class of that name exists: an
        ambiguous base links nothing rather than linking the wrong class."""
        for derived, bases in self.pending_bases:
            for base in bases:
                candidates = self.compound_rowid.get(base, [])
                if len(candidates) == 1 and candidates[0] != derived:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO compoundref (base_rowid, derived_rowid, prot, virt) "
                        "VALUES (?, ?, 0, 0)",
                        (candidates[0], derived),
                    )


## A comment marker at the start of a JSDoc line: `/**`, `*`, `*/`.
_JSDOC_PREFIX = re.compile(r"^\s*(?:/\*\*|\*/|\*(?!/))?\s?")
_TAG_LINE = re.compile(r"^\s*@\w")


## @brief Render a raw JSDoc block as doxygen's brief / detailed description markup.
## @param raw The block text, or "".
## @return (briefdescription, detaileddescription), each "" when absent.
## @version 1
## @req REQ-DDB-PIPE-012
def render_doc(raw: str) -> tuple[str, str]:
    """The summary (an explicit @brief, else the first paragraph) is the brief. The
    remaining prose paragraphs, the version simplesect `extract_version` reads, and every
    other tag as literal `@tag value` text form the detail. Text is HTML-escaped, because
    `strip_xml` would otherwise eat a `Map<string, T>` or a JSX example as markup.

    @brief JSDoc to doxygen description markup.
    @return The two description columns.
    """
    if not raw:
        return "", ""
    from .guard.parser import apply_autobrief, parse_doxygen_tags

    tags = parse_doxygen_tags(raw)
    explicit_brief = "brief" in tags
    apply_autobrief(raw, tags)
    brief = tags.pop("brief", [""])[0]
    paragraphs = _prose_paragraphs(raw)
    if not explicit_brief and paragraphs:
        paragraphs = paragraphs[1:]
    parts = [f"<para>{html.escape(p, quote=False)}</para>" for p in paragraphs]
    for version in tags.pop("version", []):
        parts.append(
            f'<para><simplesect kind="version"><para>{html.escape(version, quote=False)}'
            "</para>\n</simplesect>\n</para>"
        )
    for tag, values in tags.items():
        parts += [f"<para>@{tag} {html.escape(v, quote=False)}</para>" for v in values]
    brief_xml = f"<para>{html.escape(brief, quote=False)}</para>" if brief else ""
    return brief_xml, "\n".join(parts)


## @brief The prose paragraphs of a JSDoc block, before its first tag line.
## @return The paragraphs, joined per paragraph.
## @version 1
## @dg_internal
def _prose_paragraphs(raw: str) -> list[str]:
    paragraphs: list[list[str]] = [[]]
    for line in raw.splitlines():
        text = _JSDOC_PREFIX.sub("", line).removesuffix("*/").rstrip()
        if _TAG_LINE.match(text):
            break
        text = re.split(r"\s@\w", text, maxsplit=1)[0].strip()
        if text:
            paragraphs[-1].append(text)
        elif paragraphs[-1]:
            paragraphs.append([])
    return [" ".join(p) for p in paragraphs if p]
