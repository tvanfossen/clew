# SPDX-License-Identifier: MIT
"""The fast tier's outgoing call edges: an edited file's AST call sites, re-resolved in place.

1.3.5 phase 5. A body edit that changes what a function calls is the commonest save there is, so
the fast tier re-folds the edited files' call sites against the same index-wide resolution maps
the full stage builds (`call_edges.import_ast_call_edges`), and replaces exactly the edges the fold
writes — sources `ast`, `ast_member`, `binding` and `jsx` — for callers in those files.

WHAT STAYS WHOLE-INDEX, and is therefore still named stale: doxygen's own call layer
(`doxygen_sqlite` rows come from a doxygen run), the refused-call record (`unresolved_inbound`),
and the two global prunes (dominated fuzzy edges, fabricated self-edges).

Measured on the four acceptance indexes, building the resolution maps costs 150-450 ms cold — the
price of this phase, paid once per fast refresh however many files it covers.

@brief Fast-tier re-resolution of an edited file's outgoing AST call edges.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from .indexcache import IndexCache
from .vocabulary import (
    CALL_SOURCE_AST,
    CALL_SOURCE_AST_MEMBER,
    CALL_SOURCE_BINDING,
    CALL_SOURCE_JSX,
)

## The `call_edges.source` values the AST fold writes — the rows this phase replaces.
FOLD_SOURCES = (CALL_SOURCE_AST, CALL_SOURCE_AST_MEMBER, CALL_SOURCE_BINDING, CALL_SOURCE_JSX)


## @brief Replace the AST-fold call edges whose caller lives in one of the edited files.
## @param conn Open index connection, inside the fast tier's transaction, AFTER positions moved.
## @param repo_root The working tree.
## @param cache The index cache.
## @param files {repo-relative path: path rowid} of the edited files.
## @return The resolution maps it built, so later per-file layers reuse them.
## v2 (phase 6): returns the maps, so the blocking-call rewrite reuses `file_funcs`.
## @version 2
## @req REQ-DDB-INDEX-006
def refresh_outbound_calls(
    conn: sqlite3.Connection, repo_root: Path, cache: IndexCache, files: dict[str, int]
) -> dict[str, Any]:
    """AFTER THE POSITION SHIFT, because the fold assigns each call site to the function whose
    span holds its line: the spans must already be the edited file's.

    @brief Re-fold and replace one or more files' outgoing AST edges.
    @return The resolution maps.
    @version 2
    """
    from . import call_edges as ce

    maps = _resolution_maps(conn)
    resolved: list = []
    fuzzy: list = []
    for rel, rowid in files.items():
        funcs = maps["file_funcs"].get(rowid, [])
        _delete_fold_edges(conn, [int(f[0]) for f in funcs])
        payload = _call_payload(rel, repo_root / rel, cache)
        if not funcs or payload is None:
            continue
        ce._fold_call_payload(
            payload,
            funcs,
            maps["name_to_rowids"],
            resolved,
            fuzzy,
            maps["definition_of"],
            receiver_types=maps["receiver_types"],
            scope_of=maps["scope_of"],
            argc_of=maps["argc_of"],
            unresolved=[],
            bases_of=maps["bases_of"],
            class_scopes=maps["class_scopes"],
            implementors=maps["implementors"],
            one_function=maps["one_function"],
        )
    collapsed, fuzzy = ce._collapse_duplicate_targets(fuzzy, maps["identity_of"], maps["defined"])
    ce._ast_insert_edges(conn, resolved + collapsed, fuzzy)
    return maps


## @brief The index-wide maps the AST fold resolves against, built as the full stage builds them.
## @param conn Open index connection.
## @return The maps, keyed as `_fold_all_files` reads them, plus identity_of/defined.
## @version 1
## @dg_internal
def _resolution_maps(conn: sqlite3.Connection) -> dict[str, Any]:
    """THE FULL STAGE'S OWN CONSTRUCTORS, called the same way (`import_ast_call_edges`), so an
    edge resolved here is the edge the full build resolves for the same index.

    @brief Build the resolution maps.
    @return Maps.
    @version 1
    """
    from . import call_edges as ce

    name_to_rowids, file_funcs = ce._build_function_indexes(conn)
    receiver_types = ce._receiver_types(conn)
    identity_of, defined = ce._function_identities(conn)
    body_of, homes = ce._function_bodies(conn)
    scope_of: dict[int, str] = {}
    argc_of: dict[int, int] = {}
    if receiver_types:
        scope_of = {
            int(r): str(sc or "")
            for r, sc in conn.execute("SELECT rowid, scope FROM memberdef WHERE kind = 'function'")
        }
        if ce._table_exists(conn, "memberdef_param"):
            argc_of = {
                int(r): int(n)
                for r, n in conn.execute(
                    "SELECT memberdef_id, COUNT(*) FROM memberdef_param GROUP BY memberdef_id"
                )
            }
    bases = ce._class_bases(conn)
    return {
        "name_to_rowids": name_to_rowids,
        "file_funcs": file_funcs,
        "definition_of": ce._definition_index(conn),
        "receiver_types": receiver_types,
        "scope_of": scope_of,
        "argc_of": argc_of,
        "bases_of": bases,
        "class_scopes": ce._class_scopes(conn),
        "implementors": ce._interface_implementors(bases, ce._interfaces(conn)),
        "one_function": ce._one_function_targets(name_to_rowids, identity_of, body_of, homes=homes),
        "identity_of": identity_of,
        "defined": defined,
    }


## @brief Delete the AST-fold edges whose caller is one of the given functions.
## @param conn Open index connection.
## @param callers Function rowids of the edited files.
## @return None.
## @version 1
## @dg_internal
def _delete_fold_edges(conn: sqlite3.Connection, callers: list[int]) -> None:
    """ONLY THE FOLD'S SOURCES: doxygen's rows and the callback layer's are not this phase's to
    replace, and deleting them would leave a hole the fold does not refill.

    @brief Remove one file's fold edges.
    @return None.
    """
    if not callers:
        return
    marks = ",".join("?" for _ in callers)
    sources = ",".join("?" for _ in FOLD_SOURCES)
    conn.execute(
        f"DELETE FROM call_edges WHERE caller_rowid IN ({marks}) AND source IN ({sources})",
        (*callers, *FOLD_SOURCES),
    )


## @brief One file's call-site payload, from the cache or a fresh parse.
## @param rel Repo-relative path.
## @param path Absolute path.
## @param cache The index cache.
## @return The payload, or None when the file is not parseable.
## @version 1
## @dg_internal
def _call_payload(rel: str, path: Path, cache: IndexCache) -> Any:
    """@brief Harvest one file's call sites. @return Payload or None."""
    from .call_edges import call_site_harvester
    from .harvest import HarvestTally, _harvest_one_file

    return _harvest_one_file(rel, path, call_site_harvester(), {}, cache, HarvestTally())


## @brief Rewrite the blocking call sites of the edited files.
## @param conn Open index connection, inside the fast tier's transaction, after the shift.
## @param repo_root The working tree.
## @param cache The index cache.
## @param files {repo-relative path: path rowid} of the edited files.
## @param file_funcs The function spans per path rowid, from `refresh_outbound_calls`' maps.
## @return Rows inserted.
## @version 1
## @req REQ-DDB-INDEX-006
def refresh_blocking_calls(
    conn: sqlite3.Connection,
    repo_root: Path,
    cache: IndexCache,
    files: dict[str, int],
    file_funcs: dict[int, list],
) -> int:
    """WHOLLY PER FILE, the same way `blocking.extract_blocking_calls` builds it: the file's
    payload, each site's holder by the function span that contains its line, one row each.

    @brief Replace one or more files' blocking_calls rows.
    @return Rows inserted.
    @version 1
    """
    from .blocking import blocking_harvester
    from .call_edges import _ast_caller_at_line, _table_exists
    from .harvest import HarvestTally, _harvest_one_file

    ## NOT `ensure_blocking_table`: its `executescript` COMMITs, which would end the fast tier's
    ## one transaction half-way. An index without the table never ran the layer; nothing to do.
    if not _table_exists(conn, "blocking_calls"):
        return 0
    inserted = 0
    for rel, rowid in files.items():
        conn.execute("DELETE FROM blocking_calls WHERE path_rowid = ?", (rowid,))
        payload = _harvest_one_file(
            rel, repo_root / rel, blocking_harvester(), {}, cache, HarvestTally()
        )
        for record in payload or []:
            holder = _ast_caller_at_line(file_funcs.get(rowid, []), record[1])
            if holder is None:
                continue
            inserted += conn.execute(
                "INSERT OR IGNORE INTO blocking_calls "
                "(holder_rowid, path_rowid, line, primitive, wait, wait_operand, guard) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (holder, rowid, record[1], record[0], record[2], record[3], record[4]),
            ).rowcount
    return inserted
