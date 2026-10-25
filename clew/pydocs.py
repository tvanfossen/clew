# SPDX-License-Identifier: MIT
"""PEP 257 docstrings, where doxygen left a Python definition undocumented.

Doxygen stays Python's front end: its `##` blocks, `@brief`/`@version`/`@req`, aliases and
cross-references are kept exactly. What it does NOT do is read a plain docstring as
documentation. With `PYTHON_DOCSTRING` on (its default) a plain triple-quoted docstring becomes
`<verbatim>` text in the detailed description, the brief stays empty, and a `@version` inside
it is never parsed. A codebase that documents the PEP 257 way therefore indexed as
undocumented: no brief in `search` or `dossier`, no revision.

This stage fills exactly that gap, and only that gap:

* a doxygen row (function or class) whose brief is EMPTY gets the docstring's summary line
  (PEP 257: the first line, up to the first blank line) as its brief;
* a `@version` in the docstring becomes the `<simplesect kind="version">` the query layer
  reads, when doxygen's detail carries none.

A row doxygen documented (a `##` block, or a docstring opened with the `!` marker) is never changed,
which is the same precedence the gate applies: `##` wins. `@req` needs nothing here, because
the requirements pass already reads the literal tag out of the verbatim detail. Recovered
`ast` rows are left alone: their provenance says they have no documentation, and filling one
in would make that statement false.

@brief PEP 257 summary lines and versions for doxygen rows doxygen left bare.
@version 1
"""

from __future__ import annotations

import html
import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest
from .vocabulary import STAGE_PY_DOCSTRINGS, SYMBOL_SOURCE_AST, SYMBOL_SOURCE_COLUMN

_DEFINITIONS = ("function_definition", "class_definition")


## @brief Per-file harvester for Python docstrings.
## @version 1
class _DocstringHarvester(Harvester):
    """Rowid-free (line, name, raw docstring), so it caches on content like every stage.

    @brief Python docstring harvester.
    @version 1
    """

    stage = STAGE_PY_DOCSTRINGS
    stage_version = 1
    label = "python docstrings"

    ## @brief Harvest one file's definition docstrings.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's bytes.
    ## @return [[kind, def line (1-based), name, docstring body]], empty for non-Python.
    ## @version 1
    ## @req REQ-DDB-PIPE-013
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        from .pyast import is_python_tree

        return harvest_docstrings(tree) if is_python_tree(tree) else []


## @brief The docstring stage's harvester.
## @return A Harvester; built the same way everywhere so the cache key agrees.
## @version 1
## @req REQ-DDB-PIPE-013
def docstring_harvester() -> Harvester:
    """@brief Build this stage's harvester."""
    return _DocstringHarvester()


## @brief Every function and class docstring in a Python tree.
## @param tree A Python tree.
## @return [[kind, def line, name, body]] with the quotes stripped.
## @version 1
## @req REQ-DDB-PIPE-013
def harvest_docstrings(tree: Any) -> list[list[Any]]:
    """The line is the `def` / `class` line, not a decorator's, which is the line doxygen
    records, so the two join on (file, line, name).

    @brief Collect definition docstrings.
    @return The docstrings found.
    """
    from .guard.ts_parser import _find_python_docstring_node, _strip_docstring_quotes

    out: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type not in _DEFINITIONS:
            continue
        name = node.child_by_field_name("name")
        string = _find_python_docstring_node(node)
        if name is None or string is None or not string.text:
            continue
        body = _strip_docstring_quotes(string.text.decode("utf-8", errors="replace"))
        if body.strip():
            kind = "class" if node.type == "class_definition" else "function"
            out.append([kind, node.start_point[0] + 1, name.text.decode("utf-8"), body])
    return out


## @brief The PEP 257 summary and the @version of one docstring.
## @param body Docstring text without its quotes.
## @return (summary, version), each "" when absent.
## @version 1
## @req REQ-DDB-PIPE-013
def summarize(body: str) -> tuple[str, str]:
    """An explicit `@brief` wins over the summary line, as in the gate.

    @brief Read a docstring's brief and version.
    @return The pair.
    """
    from .guard.parser import apply_autobrief, parse_doxygen_tags

    tags = parse_doxygen_tags(body)
    apply_autobrief(body, tags)
    return tags.get("brief", [""])[0], tags.get("version", [""])[0]


## @brief Fill empty doxygen briefs (and missing versions) from PEP 257 docstrings.
## @param db_path The database being built.
## @param repo_root Repository root.
## @param cache The index cache (the shared parse warmed it), or None.
## @return How many rows were enriched.
## @version 3
## @req REQ-DDB-PIPE-013
def enrich_python_docstrings(db_path: Path, repo_root: Path, cache: Any = None) -> int:
    """@brief Write docstring summaries into the rows doxygen left bare."""
    conn = sqlite3.connect(str(db_path))
    try:
        harvested = run_harvest(conn, repo_root, docstring_harvester(), cache)
        provenance = _has_provenance(conn)
        located = _locate_rows(conn)
        enriched = 0
        for path_rowid, payload in harvested:
            for kind, line, name, body in payload or ():
                candidates = located.get((_table_for(kind), path_rowid, line))
                if not candidates:
                    continue
                summary, version = summarize(body)
                if not summary and not version:
                    continue
                enriched += _enrich_one(
                    conn, kind, path_rowid, line, name, summary, version, provenance, candidates
                )
        conn.commit()
    finally:
        conn.close()
    if enriched:
        logger.info("pep 257: %d Python definition(s) documented from their docstrings", enriched)
    return enriched


## @brief Whether memberdef carries the dg_source column.
## @return True when the column exists.
## @version 1
## @dg_internal
def _has_provenance(conn: sqlite3.Connection) -> bool:
    return any(r[1] == SYMBOL_SOURCE_COLUMN for r in conn.execute("PRAGMA table_info(memberdef)"))


## @brief The table a harvested definition's doxygen row lives in.
## @return `compounddef` for a class, `memberdef` otherwise.
## @version 1
## @dg_internal
def _table_for(kind: str) -> str:
    return "compounddef" if kind == "class" else "memberdef"


## @brief Every row a docstring could land on, keyed by (table, file, line).
## @return The rowids under each key.
## @version 1
## @dg_internal
def _locate_rows(conn: sqlite3.Connection) -> dict[tuple[str, int, int], list[int]]:
    """Doxygen's tables carry no index, so `_enrich_one`'s lookup used to scan all of
    `memberdef` once per docstring: 15 s of a 42 s mbedtls build, for no row changed. One
    pass here keys every row on the columns that lookup matches by equality, and
    `_enrich_one` then runs its full WHERE over just the rowids under its key. The keys
    are exactly the lookup's (`memberdef` by body file, else declaring file), so no row
    the full scan would find is missed.

    @brief Index doxygen's rows by file and line.
    @version 1
    """
    located: dict[tuple[str, int, int], list[int]] = {}
    for table, file_expr in (
        ("memberdef", "COALESCE(NULLIF(bodyfile_id, 0), file_id)"),
        ("compounddef", "file_id"),
    ):
        for rowid, file_id, line in conn.execute(f"SELECT rowid, {file_expr}, line FROM {table}"):
            located.setdefault((table, file_id, line), []).append(rowid)
    return located


## @brief Enrich the rows matching one docstring, when doxygen left them bare.
## @return How many rows changed.
## @version 2
## @dg_internal
def _enrich_one(
    conn: sqlite3.Connection,
    kind: str,
    path_rowid: int,
    line: int,
    name: str,
    summary: str,
    version: str,
    provenance: bool,
    candidates: list[int],
) -> int:
    from .query._common import extract_version, strip_xml

    table = _table_for(kind)
    if kind == "class":
        where = "file_id = ? AND line = ? AND (name = ? OR name LIKE ?)"
        args: tuple[Any, ...] = (path_rowid, line, name, f"%::{name}")
    else:
        where = "COALESCE(NULLIF(bodyfile_id, 0), file_id) = ? AND line = ? AND name = ?"
        args = (path_rowid, line, name)
        if provenance:
            where += f" AND {SYMBOL_SOURCE_COLUMN} != '{SYMBOL_SOURCE_AST}'"
    marks = ",".join("?" * len(candidates))
    rows = conn.execute(
        f"SELECT rowid, briefdescription, detaileddescription FROM {table}"
        f" WHERE rowid IN ({marks}) AND {where}",
        (*candidates, *args),
    ).fetchall()
    changed = 0
    for rowid, brief, detail in rows:
        if strip_xml(brief):
            continue  # doxygen documented it: a `##` block wins
        new_brief = f"<para>{html.escape(summary, quote=False)}</para>" if summary else brief
        new_detail = detail or ""
        if version and not extract_version(new_detail):
            new_detail += (
                f'<para><simplesect kind="version"><para>{html.escape(version, quote=False)}'
                "</para>\n</simplesect>\n</para>"
            )
        conn.execute(
            f"UPDATE {table} SET briefdescription = ?, detaileddescription = ? WHERE rowid = ?",
            (new_brief, new_detail, rowid),
        )
        changed += 1
    return changed
