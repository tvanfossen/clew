# SPDX-License-Identifier: MIT
"""The parse-built front end: doxygen-shaped rows for languages doxygen cannot read.

Doxygen reads no JavaScript, TypeScript, shell or CMake, so those files got no `path` row,
and therefore no harvest, no call edges and no symbols at all. This module writes the same
tables doxygen and `rustdoc.py` write (`path`, `refid`, `memberdef`, `compounddef`,
`member`, `compoundref`) from lang-parsing-substrate's parse, so every downstream stage
runs on them unchanged.

THREE TREATMENTS, BECAUSE THE FILE TYPES ARE NOT ALIKE (1.1.0). JS/TS and shell and CMake
have a function concept and get `memberdef` rows, each from its own walker
(`clew/jsast.py`, `clew/shast.py`, `clew/cmakeast.py`). YAML and JSON have none — their
grammars offer `block_mapping_pair` and `pair` — so they are REGISTERED AND NEVER
HARVESTED: present in the file set, findable by name, named by the not-indexed report, and
contributing nothing to the namespace that answers a question about a function.

IT ADDS; IT NEVER REPLACES. It runs after doxygen (or rustdoc), and allocates ids the way
`ast_symbols` does (`INSERT INTO refid` and take the rowid), so a mixed repo gets C from
doxygen and the rest from here in one index. Rows are stamped `dg_source='parse'`: written
by a front end that read the documentation (JSDoc, or the `#` block above a shell or CMake
definition), unlike an `ast` recovery row, which has none.

TWO STAGES, because the harvest reads the `path` table. `register_paths` runs before the
shared parse so the claimed files are in the file set; the definitions are harvested there
(the `js_symbols` and `script_symbols` stages, cached per file content); `emit_definitions`
then writes them, before any call layer resolves against `memberdef`.

SHAPES FOLLOW DOXYGEN'S PYTHON ROWS, which the query layer already reads: `definition`
and `scope` are dotted (`src.util.strings.Formatter.trim`), compound names `::`-joined
(`src::util::strings::Formatter`), descriptions `<para>`-wrapped with the version in a
`<simplesect kind="version">`, and every other tag (`@req`) kept as literal text, which is
exactly what doxygen does with a tag it does not define.

@brief Parse-built path/memberdef/compounddef rows for JS/TS, shell, CMake and data files.
@version 2
"""

from __future__ import annotations

import html
import re
import sqlite3
from pathlib import Path, PurePosixPath
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest
from .vocabulary import (
    STAGE_JS_SYMBOLS,
    STAGE_SCRIPT_SYMBOLS,
    SYMBOL_SOURCE_COLUMN,
    SYMBOL_SOURCE_PARSE,
)

## The extensions this front end claims. `.mts`/`.cts` are TypeScript's ES-module and
## CommonJS spellings; `.d.ts` declaration files hold signatures without bodies, which
## yield no definitions, so they need no special case.
SYNTH_EXTS = (".js", ".mjs", ".cjs", ".jsx", ".ts", ".mts", ".cts", ".tsx")

## SHELL AND CMAKE, 1.1.0. Both have a function concept doxygen cannot read, so both get
## `memberdef` rows.
SCRIPT_EXTS = (".sh", ".bash", ".cmake")

## Claimed by whole FILE NAME rather than by extension, matched as a path component: a
## suffix test (`endswith("cmakelists.txt")`) also claims `oldcmakelists.txt`, and claiming
## `.txt` itself would claim every `notes.txt` in the tree. `clew/harvest.py`'s router
## applies the same rule to the same name, and `tests/test_gate_index_extension_parity.py`
## is where a divergence surfaces.
SCRIPT_NAMES = ("cmakelists.txt",)

## DATA FILES: REGISTERED, NEVER HARVESTED. YAML and JSON have no function concept at all —
## their grammars offer `block_mapping_pair` and `pair` — so there is nothing here to write
## as a symbol. What they need is to be VISIBLE: a `path` row makes them part of the file
## set, findable by name and nameable by the miss report, without putting every `steps:`
## key of every workflow file into the namespace that answers a question about a function.
##
## Markdown is absent on purpose. It is prose, and `clew/prose.py` already chunks it into
## the FTS index by heading; a `path` row would also count it as an indexed SOURCE file in
## every coverage figure.
DATA_EXTS = (".yaml", ".yml", ".json")

## SOURCE TYPES WITH NO GRAMMAR: REGISTERED, NEVER HARVESTED, AND NOT RESOLVED TO CONTENT.
## The same treatment `DATA_EXTS` gets directly above, for a different reason. A YAML file has no
## function concept to harvest; a Perl script HAS one and this toolchain cannot read it. Both end
## up in the file set and out of the namespace, and the difference is recorded where it belongs —
## `register_paths` writes `found = 0` for these, which is doxygen's own column for "known by
## name, never resolved to content".
##
## MEASURED, ON THE FROZEN mbedtls CHECKOUT (948 files): 6 `.pl` and 8 `Makefile`. mbedtls Q4 is
## the grid's lowest-scoring cluster and its `set` mark wants `scripts/generate_errors.pl` as a
## NAME IN A LIST — `claims()` returned False for it, so the index held no `path` row and could
## not report that the file exists. Seven of that question's eight marks are conclusions about
## build provenance, not about Perl.
##
## DELIBERATELY NOT CLAIMED, from the same census: 140 `.data`, 94 `.function`, 61 `.vcxproj`.
## The first two are mbedtls's own test-fixture formats rather than a language, and 234 extra rows
## would move `coverage.indexed_files` and every `DirectoryEntry.indexed_files` for a file format
## one repository invented. Claiming a type because it exists somewhere is how an inventory
## becomes noise.
##
## NOT IN THE EXTENSION-PARITY TEST, deliberately and for the same reason `DATA_EXTS` is not:
## that test's subject is what the index READS, so the gate must be able to check it. Nothing
## reads these.
UNPARSED_EXTS = (".pl", ".pm", ".mk")

## Claimed by whole FILE NAME, matched as a path component, for the reason `SCRIPT_NAMES` states:
## `endswith("makefile")` also claims `oldmakefile.txt`.
UNPARSED_NAMES = ("makefile",)

## Every file type the front end puts in the file set.
CLAIMED_EXTS = SYNTH_EXTS + SCRIPT_EXTS + DATA_EXTS + UNPARSED_EXTS

_TYPE_FILE = 1

## A PAYLOAD'S OWN `kind` MAPPED ONTO DOXYGEN'S. The left side is this package's
## vocabulary, written by the per-language walkers; the right side is doxygen's
## `memberdef.kind` string, which the query layer reads. A CMake `macro` pastes its body
## into the caller's scope and its arguments are textual substitutions, which is what
## doxygen's "macro definition" means too, so it maps there rather than being flattened to
## a function — a reader chasing a variable that leaks out of a macro gets told it is one.
##
## `clew/query/macros.py` owns the doxygen spelling ("spelled once: it is a doxygen
## vocabulary string, not ours"). `tests/test_member_kind_parity.py` holds the two
## together, because that module is on the READ side and importing it here would stand the
## pipeline's layering on its head.
MEMBER_KIND = {"function": "function", "macro": "macro definition"}


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


## @brief Per-file harvester for shell and CMake definitions.
## @version 1
class _ScriptSymbolHarvester(Harvester):
    """ONE STAGE FOR TWO LANGUAGES. Every harvest stage is offered every indexed file, so a
    second partition would store an empty payload per file per index — 40,000 rows on a
    large target recording that a C file defines no shell function. The two walkers share
    this stage's version as the cost of that.

    Dispatch is by NODE SHAPE, not by the file's extension and not by the tree's root
    type: a bash tree is rooted at `program`, the same as JavaScript's, and a CMake tree at
    `source_file`, the same as Rust's. Each walker recognises its own definition nodes and
    returns nothing for a tree that has none, so the dispatch cannot mistake one language
    for another even though both roots are shared.

    @brief Shell/CMake definitions harvester.
    @version 1
    """

    stage = STAGE_SCRIPT_SYMBOLS
    ## v2: the CMake branch now also returns `generated` — the `add_custom_command` rules saying
    ## which files do not exist until something produces them. A cached v1 payload holds
    ## definitions and no rules, so reusing one would leave a rebuilt index silently without
    ## them, which is why the version is part of the cache key.
    stage_version = 2
    label = "shell/cmake definitions and generation rules"

    ## @brief Harvest one file's definitions, and a CMake file's generation rules.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's bytes.
    ## @return The payload, or {} for a file of neither language.
    ## v2: the CMake branch merges `harvest_generation` — the `add_custom_command` rules naming
    ## which files do not exist until something produces them.
    ## @version 2
    ## @req REQ-DDB-PIPE-012
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        from .cmakeast import harvest_definitions as cmake_definitions
        from .cmakeast import is_cmake_tree
        from .shast import harvest_definitions as sh_definitions
        from .shast import is_sh_tree

        if is_sh_tree(tree):
            return sh_definitions(tree, src_bytes)
        if is_cmake_tree(tree):
            from .cmakeast import harvest_generation

            ## GENERATION RULES RIDE IN THIS PAYLOAD rather than in a stage of their own, and the
            ## vocabulary argues it: `STAGE_SCRIPT_SYMBOLS` covers two languages in one partition
            ## because "every stage in this vocabulary is harvested over every indexed file, so a
            ## second partition would add an empty payload row per file per index — on a
            ## 40,000-file target that is 40,000 rows". Generation rules live only in CMake files,
            ## so a `generation` stage would store precisely that.
            return {**cmake_definitions(tree, src_bytes), **harvest_generation(tree, src_bytes)}
        return {}


## @brief The shell/CMake definitions stage's harvester.
## @return A Harvester; build it the same way everywhere so the cache key agrees.
## @version 1
## @req REQ-DDB-PIPE-012
def script_symbol_harvester() -> Harvester:
    """@brief Build this stage's harvester."""
    return _ScriptSymbolHarvester()


## @brief Whether a repo-relative path is one this front end claims.
## @param rel Path, any separator.
## @return True for any claimed type: JS/TS, shell, CMake, a YAML/JSON data file, or a source type with no grammar.
## v3 (C5): the no-grammar source types, so a file this toolchain cannot read is still a file it
## can name. See `UNPARSED_EXTS` for the census that set the list.
## @version 3
## @dg_internal
def claims(rel: str) -> bool:
    """Every type this front end registers in `path`, whether or not it will carry
    symbols: a YAML file is claimed so that it is in the file set, and harvested by
    nothing.

    @brief Claimed-file-type test.
    """
    lower = rel.lower()
    name = PurePosixPath(lower).name
    return lower.endswith(CLAIMED_EXTS) or name in SCRIPT_NAMES or name in UNPARSED_NAMES


## @brief Whether a repo-relative path is one of the symbol-bearing script types.
## @param rel Path, any separator.
## @return True for a shell or CMake source file.
## @version 1
## @dg_internal
def script_claims(rel: str) -> bool:
    """@brief Shell/CMake extension-or-name test."""
    lower = rel.lower()
    return lower.endswith(SCRIPT_EXTS) or PurePosixPath(lower).name in SCRIPT_NAMES


## @brief Whether a claimed path is one this toolchain has no grammar for.
## @param rel Path, any separator.
## @return True for a source type registered by name only.
## @version 1
## @dg_internal
def unparsed_claims(rel: str) -> bool:
    """Split from `claims` because the two answer different questions and only one of them
    decides a stored value: `claims` decides whether the file is in the SET, this decides whether
    the row may say it was READ.

    @brief No-grammar source-type test.
    """
    lower = rel.lower()
    return lower.endswith(UNPARSED_EXTS) or PurePosixPath(lower).name in UNPARSED_NAMES


## @brief Insert `path` rows for the JS/TS files of this build's scanned tree.
## @param db_path The database being built.
## @param files Repo-relative POSIX paths of every file in scope.
## @return How many rows were inserted.
## v3 (C5): `found` is written per file rather than always 1, so a no-grammar source type does
## not claim it was resolved to content.
## @version 3
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
        ## `found` IS A MEASUREMENT AND IS WRITTEN AS ONE (C5). doxygen's own column means
        ## "resolved to content", `query.corpus._was_harvested` reads it, and
        ## `FileSubject.harvested` serves it — so a Perl script registered with `found = 1` would
        ## claim this toolchain parsed it, and would be indistinguishable from a C file it did.
        ## The honest row says: I know this file's name, I did not read it.
        conn.executemany(
            "INSERT INTO path (type, local, found, name) VALUES (?, 1, ?, ?)",
            [(_TYPE_FILE, 0 if unparsed_claims(f) else 1, f) for f in new],
        )
        conn.commit()
    finally:
        conn.close()
    if new:
        logger.info("parse front end: %d file(s) registered", len(new))
    return len(new)


## @brief Create the `generated_files` table if it is absent.
## @param conn Open connection to the index.
## @return None.
## @version 1
## @req REQ-DDB-SCHEMA-014
def ensure_generated_files_table(conn: sqlite3.Connection) -> None:
    """CREATED UNCONDITIONALLY, EVEN AT ZERO ROWS — the rule this codebase returns to most. An
    EMPTY table means the layer ran and this repository declares no generation rules; an ABSENT
    one means the layer never ran, and `query.corpus.generation_rule` reports None for both
    unless the table exists to tell them apart.

    ONE ROW PER (output, argument), not per rule, so a rule's arguments are queryable without
    parsing a packed column. The rule's own identity repeats across its rows, which is the shape
    `kconfig_gates` already uses and which `_compact_gate_panel` compacts on the wire rather than
    in storage.

    @brief Ensure the generation table exists.
    @version 1
    """
    conn.execute(
        "CREATE TABLE IF NOT EXISTS generated_files ("
        "  output_name    TEXT NOT NULL,"
        "  output_literal TEXT NOT NULL,"
        "  kind           TEXT NOT NULL,"
        "  source_file    TEXT NOT NULL,"
        "  source_line    INTEGER NOT NULL,"
        "  role           TEXT NOT NULL,"
        "  arg_name       TEXT NOT NULL,"
        "  arg_literal    TEXT NOT NULL,"
        "  unresolved     INTEGER NOT NULL DEFAULT 0)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_output ON generated_files(output_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_generated_arg ON generated_files(arg_name)")


## @brief Write one CMake file's generation rules into `generated_files`.
## @param conn Open connection.
## @param source_file The repo-relative path of the build file holding the rules.
## @param rules The `generated` records from the harvest payload.
## @return Rows written.
## @version 1
## @req REQ-DDB-PIPE-012
def _write_generation(conn: sqlite3.Connection, source_file: str, rules: list) -> int:
    """A RULE WITH NO OUTPUT STILL WRITES ITS ROWS. `add_custom_target` names no OUTPUT — it is
    the aggregate forcing the rules above it to run — and its row carries `output_name = ''` so
    the target's DEPENDS are still readable while `generation_rule`'s lookup, which requires a
    non-empty name, cannot mistake it for a generated file.

    @brief Insert a file's generation rows.
    @return Rows written.
    @version 1
    """
    rows = []
    for rule in rules:
        outputs = rule.get("outputs") or [{"literal": "", "name": ""}]
        for out in outputs:
            for role in ("command", "depends"):
                for arg in rule.get(role) or []:
                    rows.append(
                        (
                            out.get("name", ""),
                            out.get("literal", ""),
                            rule.get("kind", ""),
                            source_file,
                            int(rule.get("line") or 0),
                            role,
                            arg.get("name", ""),
                            arg.get("literal", ""),
                            1 if arg.get("unresolved") else 0,
                        )
                    )
    if rows:
        conn.executemany("INSERT INTO generated_files VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


## @brief Write every harvested JS/TS definition into the index.
## @param db_path The database being built.
## @param repo_root Repository root.
## @param cache The index cache (the shared parse warmed it), or None.
## @return (functions written, classes written).
## v4: also writes `generated_files` from the CMake branch's `generated` records, and creates
## that table unconditionally so an empty layer is distinguishable from an absent one.
## @version 4
## @req REQ-DDB-PIPE-012
def emit_definitions(db_path: Path, repo_root: Path, cache: Any = None) -> tuple[int, int]:
    """@brief Turn the cached js_symbols payloads into rows."""
    from .ast_symbols import ensure_symbol_provenance

    conn = sqlite3.connect(str(db_path))
    try:
        ## BEFORE THE EARLY RETURN, and that placement is the whole point. An index of a repo
        ## with no claimed file type still ran this layer and found nothing, which is a different
        ## fact from the layer never having run — and the first version of this created the table
        ## AFTER the guard, so a C-only repository got no table and `generation_rule` could not
        ## tell the two apart. `test_fixture_fidelity` caught it.
        ensure_generated_files_table(conn)
        conn.execute("DELETE FROM generated_files")
        if not _has_claimed_path(conn):
            conn.commit()
            return 0, 0
        ensure_symbol_provenance(conn)
        generated_rows = 0
        writer = _Writer(conn)
        ## TWO STAGES, ONE WRITER. The refid key prefix differs per stage so a shell
        ## function and a JS function at the same line of two files cannot collide on the
        ## `refid.refid` UNIQUE constraint; the rows themselves are identical in shape.
        for harvester, prefix in (
            (js_symbol_harvester(), "js"),
            (script_symbol_harvester(), "script"),
        ):
            for path_rowid, payload in run_harvest(conn, repo_root, harvester, cache):
                if not payload:
                    continue
                writer.file(path_rowid, payload, prefix)
                if payload.get("generated"):
                    row = conn.execute(
                        "SELECT name FROM path WHERE rowid = ?", (path_rowid,)
                    ).fetchone()
                    generated_rows += _write_generation(
                        conn, str(row[0]) if row else "", payload["generated"]
                    )
        writer.inheritance()
        conn.commit()
    finally:
        conn.close()
    logger.info(
        "parse front end: %d function(s), %d class(es), %d generation row(s)",
        writer.functions,
        writer.classes,
        generated_rows,
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
    def file(self, path_rowid: int, payload: dict[str, Any], prefix: str = "js") -> None:
        rel = self.conn.execute("SELECT name FROM path WHERE rowid = ?", (path_rowid,)).fetchone()[
            0
        ]
        module = module_of(rel)
        local: dict[str, int] = {}
        for cls in payload.get("classes", []):
            local[cls["name"]] = self._compound(path_rowid, module, cls, prefix)
        for fn in payload.get("functions", []):
            self._function(path_rowid, module, fn, local.get(fn["cls"]), prefix)

    ## @brief Insert one class-like compounddef row.
    ## @return Its rowid.
    ## @version 1
    ## @dg_internal
    def _compound(self, path_rowid: int, module: str, cls: dict[str, Any], prefix: str) -> int:
        rowid = self._refid(f"{prefix}cls_{path_rowid}_{cls['line']}_{cls['col']}_{cls['name']}")
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
        self,
        path_rowid: int,
        module: str,
        fn: dict[str, Any],
        owner: int | None,
        prefix: str,
    ) -> None:
        rowid = self._refid(f"{prefix}fn_{path_rowid}_{fn['line']}_{fn['col']}_{fn['name']}")
        scope = f"{module}.{fn['cls']}" if fn["cls"] else module
        brief, detail = render_doc(fn["doc"])
        self.conn.execute(
            "INSERT INTO memberdef (rowid, name, definition, type, argsstring, scope, kind, "
            "prot, static, bodystart, bodyend, bodyfile_id, file_id, line, column, "
            f"briefdescription, detaileddescription, {SYMBOL_SOURCE_COLUMN}) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                rowid,
                fn["name"],
                f"{scope}.{fn['name']}",
                fn["ret"],
                fn["args"],
                scope,
                MEMBER_KIND[fn.get("kind", "function")],
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
