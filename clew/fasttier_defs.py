# SPDX-License-Identifier: MIT
"""The fast tier's definition reconciliation: added, removed and renamed functions (PR1; 2.0.0).

OWNER-APPROVED 2026-11-17 (refresh-speed interjection). The fast tier refused any edit that
changed a file's set of definitions, so adding a function cost a full build (5.6 to 13.8 s, PR0).
An edited file's FUNCTIONS are now reconciled by identity (kind, qualified name, overload
ordinal), the same identity the anchors already carry:

- matched: the row stays and moves through the line map built from the matched anchors only;
- removed: its rows, and every row referencing them (`MEMBERDEF_REFERENCES`), are deleted;
- added: a row is written by the full build's own writer (`synth._Writer` for JS/TS,
  `ast_symbols._insert_recovered` for C-family and Python) with a provisional rowid.

REFUSED, AS BEFORE, WHEN IT CANNOT BE EXACT: any other kind of definition changed (a class, a
variable, a macro); the matched anchors are no longer in order (overloads reshuffled); a removed
function's row cannot be found; or a removed function is a thread's entry point, whose `threads`
row three thread-keyed tables point at. Each refusal is a full build.

@brief Reconcile an edited file's functions in the fast tier.
@version 1
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Any

## Every column holding a memberdef rowid, by table: what a removed function's rows are deleted
## from. PINNED by tests/test_fast_tier_definitions.py against every `*_rowid` / `*_id` column of a
## built index, together with `NOT_MEMBERDEF_COLUMNS`, so a new table cannot leave a removed
## function's rows pointing at nothing.
MEMBERDEF_REFERENCES: dict[str, tuple[str, ...]] = {
    "blocking_calls": ("holder_rowid",),
    "call_edges": ("caller_rowid", "callee_rowid", "via_macro_rowid"),
    "context_conflicts": ("member_rowid",),
    "critical_section_calls": ("callee_rowid",),
    "decl_extent": ("memberdef_rowid",),
    "external_boundaries": ("memberdef_rowid", "registered_by_rowid"),
    "lock_acquisitions": ("holder_rowid",),
    "member": ("memberdef_rowid",),
    "memberdef_param": ("memberdef_id",),
    "reimplements": ("memberdef_rowid", "reimplemented_rowid"),
    "req_edges": ("memberdef_rowid",),
    "req_test_edges": ("test_memberdef_rowid",),
    "test_failure_modes": ("test_memberdef_rowid",),
    "shared_key_edges": ("writer_rowid", "reader_rowid"),
    "symbol_liveness": ("memberdef_rowid",),
    "thread_membership": ("memberdef_rowid",),
    "threads": ("entry_memberdef_rowid",),
    "unresolved_inbound": ("callee_rowid",),
    "xrefs": ("src_rowid", "dst_rowid"),
}

## `*_rowid` / `*_id` columns that do NOT hold a memberdef rowid (a path, a compound, a thread, a
## lock, a requirement id). Named, so the pin above fails on a column nobody classified.
NOT_MEMBERDEF_COLUMNS: frozenset[tuple[str, str]] = frozenset(
    {
        ("ast_includes", "src_id"),
        ("ast_includes", "dst_id"),
        ("blocking_calls", "path_rowid"),
        ("compounddef", "file_id"),
        ("compounddef", "header_id"),
        ("compoundref", "base_rowid"),
        ("compoundref", "derived_rowid"),
        ("contains", "inner_rowid"),
        ("contains", "outer_rowid"),
        ("context_conflicts", "thread_id"),
        ("context_conflicts", "path_rowid"),
        ("critical_section_calls", "acquisition_id"),
        ("data_model_keys", "key_id"),
        ("includes", "src_id"),
        ("includes", "dst_id"),
        ("lock_acquisitions", "lock_id"),
        ("lock_acquisitions", "path_rowid"),
        ("locks", "decl_path_rowid"),
        ("member", "scope_rowid"),
        ("memberdef", "bodyfile_id"),
        ("memberdef", "file_id"),
        ("memberdef_param", "param_id"),
        ("owners", "path_rowid"),
        ("property_keys", "path_rowid"),
        ("req_edges", "req_id"),
        ("req_mentions", "req_id"),
        ("req_test_edges", "req_id"),
        ## 2.2: a requirement id and a declared failure-mode id, not rowids.
        ("failure_modes", "req_id"),
        ("failure_modes", "mode_id"),
        ("test_failure_modes", "mode_id"),
        ("requirement_links", "req_id"),
        ("shared_key_edges", "to_thread_id"),
        ("test_scope", "path_rowid"),
        ("thread_membership", "thread_id"),
        ("threads", "spawn_path_rowid"),
    }
)

## The one payload kind reconciled; every other kind's change refuses.
_FUNCTIONS = "functions"


## @brief Refuse the fast tier from inside the transaction; the caller rolls back and builds in full.
## @version 1
class FastRefusal(Exception):
    """@brief A reconciliation that cannot be exact.
    @version 1
    """


## @brief One file's function changes.
## @version 1
@dataclass
class DefinitionChanges:
    """@brief Added and removed function records (payload-shaped).
    @version 1
    """

    added: list[Any] = field(default_factory=list)
    removed: list[Any] = field(default_factory=list)
    ## A JS/TS file's new line count, the end of its `__module__` row; None for other payloads.
    module_lines: int | None = None

    ## @brief Whether anything was added or removed.
    ## @return True when either list holds a record.
    ## @version 1
    ## @utility
    def __bool__(self) -> bool:
        """@brief Any change. @return True when changed."""
        return bool(self.added or self.removed)


## @brief A function record's (name, ordinal) identity, keyed the way the anchors are.
## @param js True for a JS/TS payload.
## @param payload A harvester payload.
## @return {(name, ordinal): record}.
## @version 1
## @utility
def _function_records(js: bool, payload: Any) -> dict[tuple[str, int], Any]:
    """THE ANCHOR SPELLING: `cls.name` for JS/TS, the qualified name (record[1]) for the AST
    payload, and an ordinal counted in payload order, as `fasttier._anchors` counts it.

    @brief Index one payload's functions.
    @return Records by identity.
    """
    out: dict[tuple[str, int], Any] = {}
    seen: dict[str, int] = {}
    for record in (payload or {}).get(_FUNCTIONS) or []:
        name = f"{record.get('cls') or ''}.{record.get('name')}" if js else str(record[1])
        seen[name] = seen.get(name, 0) + 1
        out[(name, seen[name])] = record
    return out


## @brief Line map and function changes between a file's old and new anchors.
## @param js True for a JS/TS payload.
## @param old_payload The old content's payload.
## @param new_payload The new content's payload.
## @param old Old anchors, [((kind, name, field, ordinal), line), ...].
## @param new New anchors.
## @return (old lines, new lines, changes), or None when the change cannot be reconciled.
## @version 1
## @req REQ-DDB-INDEX-006
def reconcile(
    js: bool, old_payload: Any, new_payload: Any, old: list, new: list
) -> tuple[list[int], list[int], DefinitionChanges] | None:
    """ONLY FUNCTIONS MAY DIFFER, and the matched anchors must stay in order: a reshuffled set of
    same-name overloads would map one body onto another's lines.

    @brief Reconcile one file.
    @return The plan, or None.
    """
    old_map, new_map = dict(old), dict(new)
    differing = set(old_map) ^ set(new_map)
    pairs = sorted({(old_map[k], new_map[k]) for k in set(old_map) & set(new_map)})
    ordered = all(b[1] >= a[1] for a, b in zip(pairs, pairs[1:]))
    if any(k[0] != _FUNCTIONS for k in differing) or not ordered:
        return None
    gone = {(k[1], k[3]) for k in set(old_map) - set(new_map)}
    came = {(k[1], k[3]) for k in set(new_map) - set(old_map)}
    old_records, new_records = (
        _function_records(js, old_payload),
        _function_records(js, new_payload),
    )
    changes = DefinitionChanges(
        added=[new_records[i] for i in sorted(came) if i in new_records],
        removed=[old_records[i] for i in sorted(gone) if i in old_records],
        module_lines=(int(new_payload.get("lines") or 0) or None)
        if js and isinstance(new_payload, dict)
        else None,
    )
    return [o for o, _n in pairs], [n for _o, n in pairs], changes


## @brief End a JS/TS file's `__module__` row at the file's new last line.
## @param conn Open connection, inside the transaction, AFTER the shift.
## @param path_rowid The file.
## @param lines The new line count, or None.
## @return None.
## @version 1
## @req REQ-DDB-INDEX-006
def end_module_row(conn: sqlite3.Connection, path_rowid: int, lines: int | None) -> None:
    """FOUND BY `incremental_probe fastcompare` on mattermost-mobile: the module row spans the
    whole file, and the end of the file sits past every anchor, so the line map left it at the old
    length (8 where a full build has 12). Any length-changing edit did this, not only an add.

    @brief Re-end the module row.
    @return None.
    """
    from .jsast import MODULE_CALLER

    if lines:
        conn.execute(
            "UPDATE memberdef SET bodyend = ? WHERE name = ? AND bodyfile_id = ?",
            (lines, MODULE_CALLER, path_rowid),
        )


## @brief The memberdef rows a removed function record was written as.
## @param conn Open connection.
## @param path_rowid The file.
## @param js True for a JS/TS record.
## @param record The removed record.
## @return Rowids.
## @version 1
## @utility
def _rows_of(conn: sqlite3.Connection, path_rowid: int, js: bool, record: Any) -> list[int]:
    """@brief Find a record's rows. @return Rowids."""
    name, line = (record["name"], int(record["line"])) if js else (str(record[0]), int(record[4]))
    return [
        int(r[0])
        for r in conn.execute(
            "SELECT rowid FROM memberdef WHERE kind = 'function' AND name = ? "
            "AND (bodyfile_id = ? OR file_id = ?) AND (bodystart = ? OR line = ?)",
            (name, path_rowid, path_rowid, line, line),
        )
    ]


## @brief Delete removed functions and every row referencing them.
## @param conn Open connection, inside the fast tier's transaction, BEFORE the shift.
## @param path_rowid The file.
## @param js True for JS/TS records.
## @param removed The removed records.
## @return Rows deleted from memberdef.
## @version 1
## @req REQ-DDB-INDEX-006
def remove_definitions(
    conn: sqlite3.Connection, path_rowid: int, js: bool, removed: list[Any]
) -> int:
    """BEFORE THE SHIFT, while the rows still sit at the lines the old payload names.

    @brief Remove functions.
    @return Count.
    """
    ids: list[int] = []
    for record in removed:
        found = _rows_of(conn, path_rowid, js, record)
        if not found:
            raise FastRefusal(f"no row for removed function {record}")
        ids += found
    if not ids:
        return 0
    marks = ",".join("?" * len(ids))
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if (
        "threads" in tables
        and conn.execute(
            f"SELECT 1 FROM threads WHERE entry_memberdef_rowid IN ({marks}) LIMIT 1",
            ids,  # noqa: S608
        ).fetchone()
    ):
        raise FastRefusal("a removed function is a thread's entry point")
    if {"lock_acquisitions", "critical_section_calls"} <= tables:
        conn.execute(
            "DELETE FROM critical_section_calls WHERE acquisition_id IN "  # noqa: S608
            f"(SELECT id FROM lock_acquisitions WHERE holder_rowid IN ({marks}))",
            ids,
        )
    for table, columns in MEMBERDEF_REFERENCES.items():
        if table in tables:
            for column in columns:
                conn.execute(f"DELETE FROM {table} WHERE {column} IN ({marks})", ids)  # noqa: S608
    conn.execute(f"DELETE FROM memberdef WHERE rowid IN ({marks})", ids)  # noqa: S608
    conn.execute(f"DELETE FROM refid WHERE rowid IN ({marks})", ids)  # noqa: S608
    return len(ids)


## @brief Insert added functions with the full build's own writer.
## @param conn Open connection, inside the transaction, AFTER the shift.
## @param path_rowid The file.
## @param rel The file's path.
## @param js True for JS/TS records.
## @param added The added records.
## @return The added functions' names.
## @version 1
## @req REQ-DDB-INDEX-006
def add_definitions(
    conn: sqlite3.Connection, path_rowid: int, rel: str, js: bool, added: list[Any]
) -> list[str]:
    """THE SAME WRITERS THE FULL BUILD USES, so a provisional row is shaped as the full build's
    row will be. A C-family or Python function is written as an `ast`-sourced row, which is what
    the full build writes for a function doxygen has not seen; its doxygen row replaces it then.

    @brief Add functions.
    @return Names.
    """
    from .ast_symbols import ParsedFunction, _insert_recovered
    from .synth import _Writer, module_of

    writer = _Writer(conn) if js else None
    for record in added:
        if writer is not None:
            owner = _owner(conn, path_rowid, str(record.get("cls") or ""))
            writer._function(path_rowid, module_of(rel), record, owner, "js")
        else:
            r = record
            fn = ParsedFunction(
                name=r[0], qualified=r[1], args=r[2], static=bool(r[3]), start=r[4], end=r[5]
            )
            _insert_recovered(conn, path_rowid, fn)
    return [str(r["name"] if js else r[0]) for r in added]


## @brief The compound a JS/TS method belongs to, in this file.
## @param conn Open connection.
## @param path_rowid The file.
## @param cls The class name ('' for a free function).
## @return The compound rowid, or None.
## @version 1
## @utility
def _owner(conn: sqlite3.Connection, path_rowid: int, cls: str) -> int | None:
    """@brief Find the owning class. @return Rowid or None."""
    if not cls:
        return None
    row = conn.execute(
        "SELECT rowid FROM compounddef WHERE file_id = ? AND (name = ? OR name LIKE ?) LIMIT 1",
        (path_rowid, cls, f"%::{cls}"),
    ).fetchone()
    return int(row[0]) if row else None
