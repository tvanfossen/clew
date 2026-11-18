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
from .config_defaults import ORIGIN_DECLARED
from .harvest import Harvester, run_harvest
from .indexcache import IndexCache
from .vocabulary import (
    CONFIG_DEFAULT_ON,
    KCONFIG_GATE_IFDEF,
    KCONFIG_GATE_IFNDEF,
    STAGE_MACRO_REFS,
)

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
# @brief Every macro name's definitions, those the default build does not compile removed.
# @param conn Open index connection.
# @param test_patterns The build's test-path patterns, or None to read `test_scope`.
# @return {name: [memberdef rowids]}.
# v2: config states in test files decide nothing; the build passes its test patterns (2.0.0, measured on mbedtls)
# @version 2
# @req REQ-DDB-PIPE-003
def macro_definitions(
    conn: sqlite3.Connection, test_patterns: tuple[str, ...] | list[str] | None = None
) -> dict[str, list[int]]:
    """UPERF T5 (2.0.0, mbedtls F3): `{name: rowid}` kept whichever same-name definition was read
    LAST, so `mbedtls_calloc` — defined in three `#if` branches of platform.h — was credited to an
    arbitrary one. A definition inside a branch the DEFAULT BUILD does not compile is dropped: its
    covering gates of known polarity (`ifdef` / `ifndef`) are evaluated against the shipped
    configuration (`config_defaults`). A gate whose symbol the configuration does not decide, or
    whose polarity is unknown (`if_expr`), drops nothing — unknown is never read as off.

    @brief Every macro name's definitions, those the default build skips removed.
    @return {name: [rowids]}.
    @version 1
    """
    by_name: dict[str, list[tuple[int, str, int]]] = {}
    has_path = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'path'").fetchone()
    query = (
        "SELECT m.rowid, m.name, p.name, m.line FROM memberdef m "
        "LEFT JOIN path p ON p.rowid = m.file_id WHERE m.kind = 'macro definition'"
        if has_path
        ## No file table: no gate can be located, so every definition is kept (never dropped).
        else "SELECT rowid, name, '', 0 FROM memberdef WHERE kind = 'macro definition'"
    )
    for rowid, name, file_path, line in conn.execute(query):
        by_name.setdefault(name, []).append((rowid, file_path or "", line or 0))
    states = _shipped_states(conn, test_patterns)
    out = {}
    for name, defs in by_name.items():
        kept = [
            d for d in defs if len(defs) == 1 or _compiled(conn, d[1], d[2], states) is not False
        ]
        out[name] = [d[0] for d in (kept or defs)]
    return out


## @brief The shipped on/off state of every option a configuration header decides.
## @param conn Open connection.
## @return {macro: True for on, False for off}, unanimous symbols only.
## v2 (2.0.0): only a unanimous state outside the test files decides (measured on mbedtls).
## v3 (2.0.0): where a macro has a row from a DECLARED config header, only declared rows vote.
## @version 3
## @dg_internal
def _shipped_states(
    conn: sqlite3.Connection, test_patterns: tuple[str, ...] | list[str] | None = None
) -> dict[str, bool]:
    """ONLY A UNANIMOUS STATE DECIDES. `config_defaults` records every header that visibly
    decides an option — the shipped config, alternative profiles, `config_adjust_*` headers and
    test configs — and nothing in the index says which one the default build reads. Measured on
    mbedtls: 92 macros carry conflicting states, and taking the last row dropped definitions the
    default build compiles. Rows in test files (`test_scope`) are ignored; a symbol whose
    remaining rows disagree is unknown, and unknown drops nothing.

    @brief Read config_defaults. @return States.
    """
    try:
        rows = conn.execute(
            "SELECT macro, state, file_path, origin FROM config_defaults"
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    tests = _test_files(conn, test_patterns, {r[2] for r in rows})
    ## A DECLARED HEADER IS THE OPERATOR SAYING WHICH ONE THE BUILD READS: where a macro has a row
    ## from one, only declared rows vote, so an alternative profile cannot make it undecided.
    declared = {m for m, _s, f, origin in rows if origin == ORIGIN_DECLARED and f not in tests}
    seen: dict[str, set[str]] = {}
    for macro, state, file_path, origin in rows:
        if file_path not in tests and (macro not in declared or origin == ORIGIN_DECLARED):
            seen.setdefault(macro, set()).add(state)
    return {m: states == {CONFIG_DEFAULT_ON} for m, states in seen.items() if len(states) == 1}


## @brief Whether the default build compiles a line: False only when a known gate excludes it.
## @param conn Open connection.
## @param file_path The definition's file.
## @param line Its line.
## @param states The shipped option states.
## @return False (excluded), else None (not known to be excluded).
## @version 1
## @dg_internal
def _compiled(
    conn: sqlite3.Connection, file_path: str, line: int, states: dict[str, bool]
) -> bool | None:
    """@brief Evaluate covering gates. @return False or None."""
    try:
        gates = conn.execute(
            "SELECT macro, form FROM kconfig_gates WHERE file_path = ? AND line <= ? AND ? < end_line",
            (file_path, line, line),
        ).fetchall()
    except sqlite3.OperationalError:
        return None
    for macro, form in gates:
        on = states.get(macro)
        if on is None or form not in (KCONFIG_GATE_IFDEF, KCONFIG_GATE_IFNDEF):
            continue
        if on != (form == KCONFIG_GATE_IFDEF):
            return False
    return None


## @brief A name's definitions, the referring file's own first when it has one.
## @param rowids The name's kept definitions.
## @param path_rowid The referring file.
## @param conn Open connection.
## @return The definitions credited.
## v2 (2.0.0): a definition in a source file is credited only from that file.
## @version 2
## @dg_internal
def _same_file_first(rowids: list[int], path_rowid: int, conn: sqlite3.Connection) -> list[int]:
    """A REFERENCE IN THE FILE THAT DEFINES THE NAME means that file's definition; otherwise every
    kept definition is credited — several rows rather than one arbitrary pick.

    A DEFINITION IN A SOURCE FILE IS INVISIBLE OUTSIDE IT (translation-unit rule, a C fact): a
    `#define` in `ccm.c` cannot be what `ssl_tls.c` expands. Measured on mbedtls before this
    rule: references to `mbedtls_printf` from every file were credited to the local fallback
    defines in `library/ccm.c` and `programs/test/udp_proxy.c` as well as platform.h's.

    @brief Choose the credited definitions.
    @return Rowids.
    """
    if not rowids:
        return []
    marks = ",".join("?" * len(rowids))
    rows = (
        conn.execute(
            f"SELECT m.rowid, m.file_id, p.name FROM memberdef m LEFT JOIN path p ON p.rowid = m.file_id "
            f"WHERE m.rowid IN ({marks})",
            rowids,
        ).fetchall()
        if _has_path(conn)
        else [(r, None, "") for r in rowids]
    )
    own = [r for r, file_id, _name in rows if file_id == path_rowid]
    visible = [
        r for r, file_id, name in rows if file_id == path_rowid or not _is_source_file(name or "")
    ]
    return own or visible


## @brief Which of these files are test code.
## @param conn Open connection.
## @param test_patterns The build's test-path patterns, or None to read `test_scope`.
## @param files Candidate repo-relative paths.
## @return The subset that is test code.
## @version 1
## @dg_internal
def _test_files(
    conn: sqlite3.Connection, test_patterns: tuple[str, ...] | list[str] | None, files: set[str]
) -> set[str]:
    """THE BUILD PASSES ITS PATTERNS because this stage runs before `test_scope` is marked (that
    stage waits for the complete path table); a caller with a finished index reads the table.

    @brief Test-file subset.
    @return Paths.
    """
    if test_patterns is not None:
        from .testscope import is_test_path

        return {f for f in files if is_test_path(f, test_patterns)}
    if (
        not _has_path(conn)
        or not conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'test_scope'").fetchone()
    ):
        return set()
    return {
        r[0]
        for r in conn.execute(
            "SELECT p.name FROM test_scope t JOIN path p ON p.rowid = t.path_rowid"
        )
    }


## C and C++ translation-unit suffixes: a macro defined in one is not visible to another file.
_SOURCE_SUFFIXES = (".c", ".cc", ".cpp", ".cxx", ".c++")


## @brief Whether a path is a translation unit rather than a header.
## @param name The repo-relative path.
## @return True for a C/C++ source file.
## @version 1
## @dg_internal
def _is_source_file(name: str) -> bool:
    """@brief Source-file test. @return Bool."""
    return name.lower().endswith(_SOURCE_SUFFIXES)


## @brief Whether the index holds a `path` table.
## @param conn Open connection.
## @return Bool.
## @version 1
## @dg_internal
def _has_path(conn: sqlite3.Connection) -> bool:
    """@brief Table probe. @return Bool."""
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'path'").fetchone() is not None


##
# @brief Insert the macro references doxygen's xref pass did not record.
# @param db Path to the index being built.
# @param repo_root Repository the index describes.
# @param cache Index cache, or None.
# @param test_patterns The build's test-path patterns (config states in test files decide nothing).
# @return Number of xrefs rows inserted.
# v4 (2.0.0, UPERF T5): same-name macros resolve by build activity (`macro_definitions`), and a
# reference in the defining file means that file's definition.
# v5: config states in test files decide nothing; the build passes its test patterns (2.0.0, measured on mbedtls)
# @version 5
# @req REQ-DDB-PIPE-003
def import_ast_macro_refs(
    db: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
    test_patterns: tuple[str, ...] | list[str] | None = None,
) -> int:
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
    THE CALLER IS RESOLVED IN ITS OWN FILE. The enclosing function is looked up by the
    file the body was harvested from and its name. Only when that file holds no row for it
    does a name resolve alone, and then only if no other function shares it.

    @return Rows inserted.
    @version 4
    """
    conn = sqlite3.connect(str(db))
    try:
        payloads = run_harvest(conn, repo_root, MacroRefHarvester(), cache)
        macros = macro_definitions(conn, test_patterns)
        if not macros:
            logger.info("macro_refs: index holds no macro definitions — nothing to recover")
            return 0
        ## Keyed by the defining file as well as the name: a bare name is shared across
        ## files (two vendored copies of one program, a C `help` and a shell `help`), and a
        ## name-only map credits every body to whichever row was read last.
        functions: dict[tuple[int, str], int] = {}
        by_name: dict[str, list[int]] = {}
        for rowid, name, file_id, bodyfile_id in conn.execute(
            "SELECT rowid, name, file_id, bodyfile_id FROM memberdef "
            "WHERE kind='function' ORDER BY rowid"
        ):
            functions[(file_id, name)] = rowid
            if bodyfile_id is not None:
                functions[(bodyfile_id, name)] = rowid
            by_name.setdefault(name, []).append(rowid)
        ## A body whose file holds no row for it (only a prototype elsewhere carries the
        ## name) still resolves when the name is unambiguous across the index.
        unique = {name: rowids[0] for name, rowids in by_name.items() if len(rowids) == 1}

        rows: list[tuple[int, int, str]] = []
        for path_rowid, payload in payloads:
            for fn_name, ident, _line in payload or ():
                src = functions.get((path_rowid, fn_name), unique.get(fn_name))
                if src is None:
                    continue
                rows += [
                    (src, dst, AST_REF_CONTEXT)
                    for dst in _same_file_first(macros.get(ident, ()), path_rowid, conn)
                    if dst != src
                ]

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
