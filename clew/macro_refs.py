# SPDX-License-Identifier: MIT
"""Recover macro references doxygen's xref pass does not record.

`dossier`'s `referenced_by` answers "I am about to change this constant — what else is baked
against it", and it was answering INCOMPLETELY. doxygen is one source of that fact, not the
only one, and an incomplete list is an incomplete list however it came to be short.

**WHAT DOXYGEN MISSES, MEASURED (gh#9).** Six uses of one macro, each inside a documented
function body, built and read back:

    int n = MACRO;                          xref emitted
    int buf[MACRO];                         xref emitted        (C array size)
    static const int k = MACRO;             xref emitted
    std::array<Row, MACRO> kRows{};         NO XREF
    std::array<int, MACRO> a{};             NO XREF
    Box<int, MACRO> b{};                    NO XREF             (user template)

The discriminator is NON-TYPE TEMPLATE ARGUMENT POSITION, not "inside a body" — the reporter's
own first reading — and not `std::array` specifically, since a user-defined template misses too.

**WHY A PARTIAL LIST IS WORSE THAN AN EMPTY ONE.** `_referenced_by`'s existing disclosure says
an EMPTY list is not a measured negative, and that was true and useful: on mbedtls 871 of 2,504
macros have any inbound reference at all. It says nothing about a list that is present and
short, which reads as complete. A reader checking what depends on a constant finds two of three
sites and learns about the third from a compiler error.

**THE RECOVERY IS DELIBERATELY NOT TEMPLATE-SPECIFIC.** Harvesting only template arguments would
fix the reported case and stay blind to whatever else doxygen's xref pass does not reach. This
walks every identifier inside a function body and keeps the ones that name a macro the index
holds, so the layer is bounded by what macros exist rather than by which syntax was anticipated.

**PROVENANCE WITHOUT A SCHEMA CHANGE.** doxygen's own `xrefs` table already carries a `context`
column (`inline`, `argument`, `initializer`) and its uniqueness constraint includes it, so rows
recovered here are written with `context='ast'`: they cannot collide with a doxygen row for the
same pair, and a consumer can tell the layers apart. That matters because this repo's standing
lesson is that a capability you shipped is the thing most able to make the next feature's tests
lie — a presence test that cannot say WHICH layer supplied a row is the shape that has misled
here before.

@brief Recover macro references from the AST that doxygen's xref pass does not record.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .vocabulary import STAGE_MACRO_REFS

## The `xrefs.context` value every row this module writes carries. doxygen writes `inline`,
## `argument` and `initializer`; this is a fourth value it never emits, so the two layers are
## separable by a plain WHERE and neither can be mistaken for the other.
AST_REF_CONTEXT = "ast"

## Node types whose text is a bare identifier a macro use can appear as. `type_identifier`
## is included because a macro expanding to a type name parses as one; `field_identifier` is
## NOT, because `x.MACRO` names a member and not the macro.
_IDENTIFIER_NODES = frozenset({"identifier", "type_identifier"})


## @brief Per-file harvest of every identifier used inside a function body.
## @version 1
class MacroRefHarvester(Harvester):
    """ROWID-FREE AND NAME-KEYED, like every other harvester here: the payload records the
    enclosing function's name and the identifier text, never a database id, so it survives in
    the cache across rebuilds that renumber rows.

    NO FILTERING AGAINST MACRO NAMES HAPPENS HERE, and that is forced rather than chosen. The
    payload is cached per file; which names are macros is a property of the WHOLE index and can
    change when another file is added. Filtering at harvest time would bake a global fact into a
    per-file cache entry, so the filter lives at insert time where it can see the finished
    `memberdef`.

    @brief Harvest identifier uses per enclosing function.
    @version 1
    """

    stage = STAGE_MACRO_REFS
    stage_version = 1
    label = "macro refs"

    ## @brief Harvest one parsed file.
    ## @param tree Parsed tree-sitter tree.
    ## @param src_bytes The file's bytes.
    ## @return List of [function_name, identifier, line] triples.
    ## @version 1
    ## @req REQ-DDB-PIPE-003
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        """@brief Collect identifier uses inside each function body.
        @return Rowid-free triples.
        @version 1
        """
        out: list[list[Any]] = []
        seen: set[tuple[str, str]] = set()
        for fn_node, fn_name in _function_bodies(tree.root_node, src_bytes):
            for name, line in _identifiers_in(fn_node, src_bytes):
                key = (fn_name, name)
                if key in seen:
                    continue
                seen.add(key)
                out.append([fn_name, name, line])
        return out


##
# @brief Every function definition node in a tree, with its declared name.
# @param root Tree root node.
# @param src_bytes File bytes.
# @return (body node, function name) pairs.
# @version 1
# @dg_internal
def _function_bodies(root: Any, src_bytes: bytes) -> list[tuple[Any, str]]:
    """The BODY node, not the whole definition, so a macro in the return type or a parameter
    default is not attributed to the function. gh#9's reporter conceded that return-type use is
    defensibly excluded, and doxygen excludes it too — matching that keeps the layers consistent
    rather than making this one silently broader.

    @brief Locate every function definition body and its name.
    @return (body, name) pairs.
    @version 1
    """
    found: list[tuple[Any, str]] = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type == "function_definition":
            body = node.child_by_field_name("body")
            name = _definition_name(node, src_bytes)
            if body is not None and name:
                found.append((body, name))
        stack.extend(node.children)
    return found


##
# @brief The bare name a function definition declares.
# @param node A `function_definition` node.
# @param src_bytes File bytes.
# @return The bare name, or "" when it cannot be read.
# @version 4
# @dg_internal
def _definition_name(node: Any, src_bytes: bytes) -> str:
    """ONE UNWRAPPER, SHARED. `ast_symbols._function_declarator` is the single place that knows
    how a definition's declarator nests, and it is used here rather than re-implemented — an
    earlier version of this function walked the chain itself and had to learn the same lesson
    separately.

    THE LESSON, RECORDED WHERE IT WAS PAID: `const std::array<Row, MACRO>& bold_table()` parses
    with a `reference_declarator`, which does NOT expose its inner declarator under the
    `declarator` field. The shared helper only followed that field, so it returned None for every
    reference-returning definition and this recovery skipped them. Five of six measured cases
    passed; the one that was REPORTED failed. Only a control naming all six caught it, and the
    fix belonged in the shared helper — where it also restored reference-returning functions to
    `ast_symbols`' own recovery, which had been silently missing them.

    `field_identifier` is accepted alongside `identifier` because tree-sitter-cpp names a method
    defined inside its class body that way.

    @brief Read a definition's bare name.
    @return The name, or "".
    @version 4
    """
    from .ast_symbols import _function_declarator

    declarator = _function_declarator(node)
    if declarator is None:
        return ""
    cur = declarator.child_by_field_name("declarator")
    while cur is not None:
        if cur.type in {"identifier", "field_identifier"}:
            return src_bytes[cur.start_byte : cur.end_byte].decode("utf-8", "replace")
        if cur.type == "qualified_identifier":
            name = cur.child_by_field_name("name")
            if name is None:
                return ""
            return src_bytes[name.start_byte : name.end_byte].decode("utf-8", "replace")
        cur = cur.child_by_field_name("declarator")
    return ""


##
# @brief Every identifier appearing anywhere inside one body node.
# @param body A function body node.
# @param src_bytes File bytes.
# @return (identifier text, 1-based line) pairs.
# @version 1
# @dg_internal
def _identifiers_in(body: Any, src_bytes: bytes) -> list[tuple[str, int]]:
    """@brief Collect identifier text and line from a subtree.
    @return (name, line) pairs.
    @version 1
    """
    out: list[tuple[str, int]] = []
    stack = [body]
    while stack:
        node = stack.pop()
        if node.type in _IDENTIFIER_NODES:
            out.append(
                (
                    src_bytes[node.start_byte : node.end_byte].decode("utf-8", "replace"),
                    node.start_point[0] + 1,
                )
            )
        stack.extend(node.children)
    return out


##
# @brief Insert the macro references doxygen's xref pass did not record.
# @param db Path to the index being built.
# @param repo_root Repository the index describes.
# @param cache Index cache, or None.
# @return Number of xrefs rows inserted.
# @version 1
# @req REQ-DDB-PIPE-003
def import_ast_macro_refs(db: Path, repo_root: Path, cache: IndexCache | None = None) -> int:
    """FILTERED AGAINST REAL MACRO ROWS, so an identifier that merely shares a name with nothing
    contributes nothing: the join is the filter, and the layer's size is bounded by how many
    macros the index actually holds.

    `INSERT OR IGNORE` plus the table's own `UNIQUE(src_rowid, dst_rowid, context)` makes this
    idempotent, and the distinct `context` means a pair doxygen already recorded gains a second
    row rather than colliding — `_referenced_by` selects DISTINCT names, so a consumer sees one
    entry either way while the provenance stays readable.

    SELF-REFERENCE IS DROPPED. A macro whose expansion names another macro can produce a body
    identifier equal to the enclosing function; recording that would assert a function references
    itself.

    @brief Recover and insert AST-sourced macro references.
    @return Rows inserted.
    @version 1
    """
    ts = try_import_tree_sitter()
    if ts is None:
        logger.info("macro_refs: tree-sitter unavailable — skipping (doxygen xrefs only)")
        return 0

    conn = sqlite3.connect(str(db))
    try:
        payloads = run_harvest(conn, repo_root, MacroRefHarvester(), ts, cache)
        macros = {
            name: rowid
            for rowid, name in conn.execute(
                "SELECT rowid, name FROM memberdef WHERE kind='macro definition'"
            )
        }
        if not macros:
            logger.info("macro_refs: index holds no macro definitions — nothing to recover")
            return 0
        functions = {
            name: rowid
            for rowid, name in conn.execute(
                "SELECT rowid, name FROM memberdef WHERE kind='function'"
            )
        }

        rows: list[tuple[int, int, str]] = []
        for _path_rowid, payload in payloads:
            for fn_name, ident, _line in payload or ():
                dst = macros.get(ident)
                src = functions.get(fn_name)
                if dst is None or src is None or src == dst:
                    continue
                rows.append((src, dst, AST_REF_CONTEXT))

        conn.executemany(
            "INSERT OR IGNORE INTO xrefs (src_rowid, dst_rowid, context) VALUES (?, ?, ?)",
            rows,
        )
        inserted = conn.total_changes
        conn.commit()
    finally:
        conn.close()

    logger.info(
        "macro_refs: recovered %d macro reference(s) doxygen did not record "
        "(context='%s'; doxygen's xref pass misses non-type template argument uses)",
        inserted,
        AST_REF_CONTEXT,
    )
    return inserted
