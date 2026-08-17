# SPDX-License-Identifier: MIT
"""Layer 6: synthetic call edges recovered from the dispatch DECLARATION.

Reads the manifest `dispatch.py` parsed and writes the edges the static layers
structurally cannot see, all tagged `source='declared_dispatch'` so a consumer
can always separate "the pipeline observed this call" from "the repo's owner
says this indirection connects these two functions".

Two producers, one provenance:

  **interfaces** — every existing `call_edges` row landing on a declared
  interface method gets a sibling row to the bound implementor's override. The
  pairing prefers doxygen's own `reimplements` relation (exact) and falls back to
  same-name matching WITHIN the two declared compounds. Both sides are filtered
  by `definition` boundary match, because doxygen lists a base class's members
  under the derived compound too — pairing on membership alone would emit
  `ILinkPort::~ILinkPort -> ILinkPort::~ILinkPort` self-edges.

  **dispatch_tables** — every call site of the declared registrar contributes its
  handler argument, and an edge is emitted from the declared dispatching function
  to each handler. This is the fnptr-container shape the Layer 4 callback
  resolver cannot reach: Layer 4 keys on `GLOBAL = PARAM;` assignment
  registration, while a container-held pointer is registered by a METHOD CALL
  (`broker_.register_dispatcher(&stage_shim)`) whose callee is a
  `field_expression` and whose argument is a `pointer_expression` — neither of
  which Layer 4's harvest accepts.

Runs BEFORE the thread and reachability stages on purpose: `thread_membership`
is a call-closure BFS and `mark_reachability` a seeded BFS, both over non-fuzzy
`call_edges`, so a synthetic edge added here is what lets membership and liveness
flow across the seam. That cascade is the entire point — it is why one declared
`register_via` can move a whole dispatched sub-graph from orphan to live without
any liveness-specific special case.

@brief Declared-dispatch call edges + interface-boundary termini.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .call_edges import _ast_record_call_edge, _build_function_indexes
from .callback_edges import _ensure_external_boundaries_table
from .dispatch import DispatchManifest, InterfaceBinding
from .harvest import Harvester, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .shared_key_edges import _definition_preferring_name_index
from .threads import _qualified_at_boundary, _resolve_qualified_entry, _tail_identifier
from .vocabulary import (
    BOUNDARY_KIND_INTERFACE,
    BOUNDARY_STRENGTH_HIGH,
    CALL_MATCH,
    CALL_MATCH_FUZZY,
    CALL_MATCH_RESOLVED,
    CALL_SOURCE_DECLARED_DISPATCH,
    STAGE_DISPATCH,
)


## @brief True when a table exists in the open database.
## @param conn Open connection.
## @param name Table name.
## @return True when the table is present.
## @version 1
## @dg_internal
def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Check for a table without importing the query layer.

    @version 1
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


# ─── interfaces: virtual dispatch through an injected seam ──────────────────


## @brief Fully-qualified names of the compounds a declared class name refers to.
## @param conn Open connection.
## @param declared Class name as declared (bare or fully qualified).
## @return Matching compound names, exact match preferred over qualified-tail.
## @version 2
## @dg_internal
def _matching_compounds(conn: sqlite3.Connection, declared: str) -> list[str]:
    """Matches EXACTLY or on a `::`-qualified tail — never a substring. There is
    deliberately no `kind` filter: doxygen registers a compound per FILE too
    (`ilinkport.hpp`), and a substring match would have picked it up, but no file
    or namespace compound is ever named `ILinkPort` or `*::ILinkPort`. So the
    name rule alone is precise, and the module avoids importing the query layer's
    class-kind list into a pipeline stage.

    @brief Resolve a declared class name to indexed compound names.
    @return The matching compound names, deduplicated and sorted.
    @version 2
    """
    if not _table_exists(conn, "compounddef"):
        return []
    names = [
        row[0]
        for row in conn.execute(
            "SELECT name FROM compounddef WHERE name = ? OR name LIKE ?",
            (declared, f"%::{declared}"),
        )
        if row[0] == declared or row[0].endswith(f"::{declared}")
    ]
    return sorted(set(names))


## @brief Functions genuinely belonging to one compound, keyed by member name.
## @param conn Open connection.
## @param compound Fully-qualified compound name.
## @return Mapping of member name to the memberdef rowids that define it here.
## @version 1
## @dg_internal
def _class_functions(conn: sqlite3.Connection, compound: str) -> dict[str, list[int]]:
    """Membership alone is not ownership: doxygen lists a base class's inherited
    members under the derived compound as well, with the BASE's rowids. Pairing
    an interface to an implementor on membership alone therefore pairs the
    interface's own inherited constructor/`operator=` rows with themselves.

    Filtering by `definition` containing `<compound>::<name>` at a token boundary
    keeps only the members this compound actually declares — the same fail-closed
    rule the thread layer uses for a qualified entry point, and for the same
    reason: borrowing another type's rowid fabricates a relationship.

    @brief Members a compound genuinely owns, name → rowids.
    @version 1
    """
    owned: dict[str, list[int]] = {}
    rows = conn.execute(
        "SELECT m.name, m.rowid, COALESCE(m.definition, '') FROM member mm "
        "JOIN memberdef m ON m.rowid = mm.memberdef_rowid "
        "JOIN compounddef c ON c.rowid = mm.scope_rowid "
        "WHERE c.name = ? AND m.kind = 'function'",
        (compound,),
    ).fetchall()
    for name, rowid, definition in rows:
        if _qualified_at_boundary(definition, f"{compound}::{name}"):
            owned.setdefault(name, []).append(rowid)
    return owned


## @brief Map each interface-method rowid to the implementor rowids that override it.
## @param conn Open connection.
## @param iface Interface members, name → rowids.
## @param concrete Implementor members, name → rowids.
## @return Mapping of interface rowid to override rowids (self-pairs removed).
## @version 1
## @dg_internal
def _override_targets(
    conn: sqlite3.Connection,
    iface: dict[str, list[int]],
    concrete: dict[str, list[int]],
) -> dict[int, list[int]]:
    """doxygen's own `reimplements` relation is exact and signature-aware, so it
    wins wherever it covers an interface method. Same-name matching within the
    two DECLARED compounds is the fallback for repos where doxygen emitted no
    reimplements rows (older versions, and C "interfaces" built from structs of
    function pointers), and is safe precisely because the author named both types.

    @brief Pair interface methods to their declared implementor's overrides.
    @version 1
    """
    concrete_rowids = {r for rowids in concrete.values() for r in rowids}
    exact: dict[int, list[int]] = {}
    if _table_exists(conn, "reimplements"):
        for derived, base in conn.execute(
            "SELECT memberdef_rowid, reimplemented_rowid FROM reimplements"
        ):
            if derived in concrete_rowids:
                exact.setdefault(base, []).append(derived)
    targets: dict[int, list[int]] = {}
    for name, iface_rowids in iface.items():
        for iface_rowid in iface_rowids:
            found = exact.get(iface_rowid) or concrete.get(name, [])
            picked = sorted({r for r in found if r != iface_rowid})
            if picked:
                targets[iface_rowid] = picked
    return targets


## @brief Distinct callers of each callee rowid, with the incoming edge's confidence.
## @param conn Open connection.
## @param rowids Callee rowids to look up.
## @return Mapping of callee rowid to (caller rowid, strongest incoming confidence) pairs.
## @version 5
## @dg_internal
def _callers_of(conn: sqlite3.Connection, rowids: list[int]) -> dict[int, list[tuple[int, str]]]:
    """Reads the call edges the STATIC layers already produced: a virtual call
    does land on the interface method, it just stops there. This stage continues
    it.

    Carries each incoming edge's CONFIDENCE so `_crossed_edges` can propagate the
    weakest link. Without it a synthetic edge was always emitted as `resolved`
    even when the premise it rests on — "something calls this interface method" —
    was only a fuzzy name match, i.e. a high-confidence conclusion from a
    low-confidence premise.

    Because `call_edges` stores one row per extraction LAYER
    (`UNIQUE(caller_rowid, callee_rowid, source)`), the same caller can appear
    several times with different confidence; the STRONGEST is kept, since the
    premise is "an edge exists and this is how well established it is".

    @brief Load distinct callers, each with its strongest incoming confidence.
    @return callee rowid → list of (caller rowid, confidence).
    @version 4
    """
    if not rowids or not _table_exists(conn, "call_edges"):
        return {}
    placeholders = ",".join("?" * len(rowids))
    best: dict[tuple[int, int], str] = {}
    for callee, caller, conf in conn.execute(
        f"SELECT DISTINCT callee_rowid, caller_rowid, confidence FROM call_edges "
        f"WHERE callee_rowid IN ({placeholders})",
        rowids,
    ):
        key = (callee, caller)
        current = best.get(key)
        if current is None or CALL_MATCH.rank.get(conf, -1) > CALL_MATCH.rank.get(current, -1):
            best[key] = conf
    callers: dict[int, list[tuple[int, str]]] = {}
    for (callee, caller), conf in best.items():
        callers.setdefault(callee, []).append((caller, conf))
    return callers


## @brief One declared interface binding's synthetic edges and termini.
## @param conn Open connection.
## @param binding The declared interface binding.
## @return (resolved edges, fuzzy edges, terminus rows) for this binding.
## @version 1
## @dg_internal
def _interface_edges(
    conn: sqlite3.Connection, binding: InterfaceBinding
) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]], list[tuple[int, str]]]:
    """A declaration naming a type that is not in the index resolves to nothing
    and says so at WARNING rather than failing the build: conditional compilation
    legitimately keeps an implementor out of one build's scope, and a declaration
    is a standing statement across configurations.

    @brief Emit one interface binding's edges and boundary rows.
    @version 1
    """
    iface = _binding_members(conn, binding.interface, binding.methods)
    concrete = _binding_members(conn, binding.binds, binding.methods) if binding.binds else {}
    targets = _override_targets(conn, iface, concrete) if concrete else {}
    iface_rowids = sorted({r for rowids in iface.values() for r in rowids})
    callers = _callers_of(conn, iface_rowids)
    resolved, fuzzy = _crossed_edges(targets, callers)
    boundaries = _boundary_rows(binding, iface, callers) if binding.boundary else []
    if binding.binds and not targets:
        logger.warning(
            "dispatch: interface %s -> %s resolved no override pair — no edges emitted",
            binding.interface,
            binding.binds,
        )
    return resolved, fuzzy, boundaries


## @brief The declared class's owned functions, narrowed by any method filter.
## @param conn Open connection.
## @param class_name Declared class name.
## @param methods Method names to keep, or () for all.
## @return Mapping of member name to rowids; empty when the class is unresolvable.
## @version 1
## @dg_internal
def _binding_members(
    conn: sqlite3.Connection, class_name: str, methods: tuple[str, ...]
) -> dict[str, list[int]]:
    """Refuses an AMBIGUOUS class name (two indexed compounds sharing a tail)
    rather than picking one: the two would have different implementors, so a
    guess here fabricates a call graph. Naming the candidates in the warning is
    what makes the fix — qualifying the declaration — mechanical.

    @brief Resolve one declared class to the members it owns.
    @version 1
    """
    compounds = _matching_compounds(conn, class_name)
    if len(compounds) != 1:
        logger.warning(
            "dispatch: class %r matches %d indexed compounds%s — skipping",
            class_name,
            len(compounds),
            f" ({', '.join(compounds)})" if compounds else "",
        )
        return {}
    owned = _class_functions(conn, compounds[0])
    if not methods:
        return owned
    return {name: rowids for name, rowids in owned.items() if name in methods}


## @brief Cross each interface method's callers with its override targets.
## @param targets Interface rowid → override rowids.
## @param callers Interface rowid → (caller rowid, incoming confidence) pairs.
## @return (resolved edges, fuzzy edges) as (caller, callee, source) triples.
## @version 2
## @dg_internal
def _crossed_edges(
    targets: dict[int, list[int]], callers: dict[int, list[tuple[int, str]]]
) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """One override is a `resolved` edge; several (an overload set, or a method
    the implementor declares more than once) degrade to `fuzzy`, so they stay out
    of the reachability and thread-membership BFS — both of which skip fuzzy
    edges. A caller that IS the target is dropped: the implementor's own body
    calling up to the interface must not become self-recursion.

    A synthetic edge inherits the WEAKEST LINK in its derivation: it is `resolved`
    only when the override is unambiguous AND the incoming edge it was derived
    from is itself non-fuzzy. Previously the incoming confidence was ignored, so a
    fuzzy premise — "a function of this name calls this interface method, though
    the class was never confirmed" — produced a `resolved` conclusion. That is a
    high-confidence claim resting on a low-confidence one, and because the
    reachability and thread BFS both traverse `resolved` edges, it would have
    propagated an unverified premise through the whole liveness graph.

    This mirrors why `ast_member` is kept separate from `ast` (#48): the
    distinction a consumer needs is exactly the one a merge would hide.

    @brief Build the synthetic caller→override edges, inheriting the weakest link.
    @version 2
    """
    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    for iface_rowid, override_rowids in targets.items():
        unambiguous = len(override_rowids) == 1
        for caller, incoming in callers.get(iface_rowid, []):
            firm = (
                unambiguous
                and CALL_MATCH.rank.get(incoming, -1) > CALL_MATCH.rank[CALL_MATCH_FUZZY]
            )
            bucket = resolved if firm else fuzzy
            bucket.extend(
                (caller, override, CALL_SOURCE_DECLARED_DISPATCH)
                for override in override_rowids
                if override != caller
            )
    return resolved, fuzzy


## @brief Terminus rows for an interface declared as an out-of-repo boundary.
## @param binding The declared interface binding.
## @param iface Interface members, name → rowids.
## @param callers Interface rowid → (caller rowid, incoming confidence) pairs.
## @return (caller rowid, qualified interface method) pairs.
## @version 3
## @dg_internal
def _boundary_rows(
    binding: InterfaceBinding,
    iface: dict[str, list[int]],
    callers: dict[int, list[tuple[int, str]]],
) -> list[tuple[int, str]]:
    """The SECOND terminus kind. `external_boundaries` recorded exactly one
    shape — a function pointer forwarded to an out-of-repo registrar — which is
    why a C/POSIX repo measured four termini and an interface-HAL C++ codebase
    measured zero with the detector working correctly. Here the sink is a virtual
    call whose implementor is outside the index, and the author is the only one
    who can say so.

    A boundary is recorded regardless of the incoming edge's confidence, and that
    is deliberate: the claim being recorded is "calls to this interface leave the
    repo", which the AUTHOR declared. It does not depend on how well any one call
    site was resolved, so the weakest-link rule that governs synthetic call edges
    (`_crossed_edges`) does not apply here.

    @brief Record where a declared interface call leaves the repo.
    @version 3
    """
    return [
        (caller, f"{binding.interface}::{name}")
        for name, rowids in iface.items()
        for rowid in rowids
        for caller, _confidence in callers.get(rowid, [])
    ]


# ─── dispatch_tables: handlers registered into a container ──────────────────


## @brief The function name a handler argument refers to, if it names one.
## @param node The argument AST node.
## @param src_bytes The file's raw source bytes.
## @return The handler's (possibly qualified) name, or None when it is not a name.
## @version 1
## @dg_internal
def _handler_text(node: Any, src_bytes: bytes) -> str | None:
    """Accepts the four shapes a registered handler is actually written as:
    `fn`, `&fn`, `Ns::fn` and `&Class::fn`. Anything else — a lambda, a
    `std::bind`, a member pointer through an object — has no static name to bind
    and is refused rather than guessed at.

    @brief Resolve a handler argument to a function name.
    @return The handler's name, or None when the argument does not name one.
    @version 1
    """
    inner = node
    if inner is not None and inner.type == "pointer_expression":
        named = [c for c in inner.named_children if c.is_named]
        inner = named[0] if len(named) == 1 else None
    if inner is None or inner.type not in ("identifier", "qualified_identifier"):
        return None
    return src_bytes[inner.start_byte : inner.end_byte].decode("utf-8", errors="replace")


## @brief Harvest one file's declared registration call sites.
## @param tree Parsed tree-sitter tree.
## @param src_bytes The file's raw source bytes.
## @param arg_index_by_name Registrar trailing name → handler argument index.
## @return List of [registrar name, handler name] pairs, rowid-free.
## @version 1
## @dg_internal
def _walk_registration_sites(
    tree: Any, src_bytes: bytes, arg_index_by_name: dict[str, int]
) -> list[list[str]]:
    """Matches the callee's TRAILING name, so `broker_.register_dispatcher(...)`,
    `this->register_dispatcher(...)` and a free `register_dispatcher(...)` all
    hit — the object a method is called on is a runtime value with no type at the
    call site, so a declaration can only ever name the method.

    @brief Per-file harvest of declared registration sites.
    @version 1
    """
    sites: list[list[str]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call_expression":
            continue
        callee = node.child_by_field_name("function")
        name = _tail_identifier(callee, src_bytes) if callee is not None else None
        index = arg_index_by_name.get(name or "")
        if index is None:
            continue
        args = node.child_by_field_name("arguments")
        named = args.named_children if args is not None else []
        handler = _handler_text(named[index], src_bytes) if index < len(named) else None
        if handler:
            sites.append([name or "", handler])
    return sites


## @brief The dispatch stage's cacheable per-file registration harvester.
## @version 1
class _DispatchHarvester(Harvester):
    """Records `[registrar, handler]` pairs per file. The declared registrar set
    decides what matches at all, so the manifest's content hash is folded into
    the cache key — editing the declaration must re-harvest, exactly as editing a
    shared-key or thread manifest does.

    @brief Declared-registration per-file harvester.
    @version 1
    """

    stage = STAGE_DISPATCH
    # Bump when _walk_registration_sites' extraction changes.
    stage_version = 1
    label = "declared dispatch"

    ## @brief Store the registrar→argument-index map plus the manifest cache key.
    ## @param arg_index_by_name Registrar trailing name → handler argument index.
    ## @param extra_key Manifest-derived cache-key component.
    ## @version 1
    ## @dg_internal
    def __init__(self, arg_index_by_name: dict[str, int], extra_key: str) -> None:
        super().__init__(extra_key)
        self.arg_index_by_name = arg_index_by_name

    ## @brief Harvest one file's declared registration sites.
    ## @param tree Parsed tree-sitter tree.
    ## @param src_bytes The file's raw source bytes.
    ## @return List of [registrar, handler] pairs.
    ## @version 1
    ## @req REQ-DDB-SCHEMA-004
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return _walk_registration_sites(tree, src_bytes, self.arg_index_by_name)


## @brief Layer 6's harvester, or None when no dispatch table is declared.
## @param manifest The parsed dispatch manifest.
## @param extra_key Manifest-derived cache-key component.
## @return A Harvester, or None when this stage does no AST work at all.
## @version 1
## @req REQ-DDB-SCHEMA-004
def dispatch_harvester(manifest: DispatchManifest, extra_key: str = "") -> Harvester | None:
    """None when the manifest declares no `dispatch_tables`, which is the same
    condition `_harvest_sites` already refuses on — a repo declaring only interfaces
    pays no AST walk, and gh#358's shared parse pass must not warm one for it.

    @brief Build this stage's harvester, or None when it is inert.
    @version 1
    """
    if not manifest.tables:
        return None
    arg_index_by_name = {
        t.register_via.rsplit("::", 1)[-1]: t.handler_arg_index for t in manifest.tables
    }
    return _DispatchHarvester(arg_index_by_name, extra_key)


## @brief Resolve a declared function name to exactly one memberdef rowid.
## @param conn Open connection.
## @param name Function name, bare or `Class::method`.
## @param name_index Definition-preferring name → rowids index.
## @return The rowid, or None when the name is absent or ambiguous.
## @version 1
## @dg_internal
def _resolve_declared_function(
    conn: sqlite3.Connection, name: str, name_index: dict[str, list[int]]
) -> int | None:
    """A qualified name resolves against `definition` for exact-overload
    precision and must resolve to ITS OWN class or not at all; a bare name must
    be unique in the index. Both fail closed, because the alternative is
    attributing a whole dispatched sub-graph to the wrong function.

    @brief Resolve one declared function name to a rowid.
    @version 1
    """
    if "::" in name:
        return _resolve_qualified_entry(conn, name)
    candidates = name_index.get(name, [])
    return candidates[0] if len(candidates) == 1 else None


## @brief Synthetic edges from each declared dispatcher to its registered handlers.
## @param conn Open connection.
## @param manifest The parsed dispatch manifest.
## @param sites Harvested [registrar, handler] pairs across the whole index.
## @return (resolved edges, fuzzy edges) as (caller, callee, source) triples.
## @version 1
## @dg_internal
def _table_edges(
    conn: sqlite3.Connection, manifest: DispatchManifest, sites: list[list[str]]
) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]]:
    """Every handler registered through a declared registrar becomes a callee of
    that entry's declared dispatching function. Handler resolution reuses the
    shared `_ast_record_call_edge` tiering, so a handler name that matches several
    indexed functions produces fuzzy edges to each rather than an arbitrary pick.

    @brief Build the declared dispatcher→handler edges.
    @version 1
    """
    name_index = _definition_preferring_name_index(conn)
    plain_index, _ = _build_function_indexes(conn)
    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    for table in manifest.tables:
        dispatcher = _resolve_declared_function(conn, table.dispatch_via, name_index)
        registrar_tail = table.register_via.rsplit("::", 1)[-1]
        handlers = sorted({h for registrar, h in sites if registrar == registrar_tail})
        if dispatcher is None:
            logger.warning(
                "dispatch: dispatch_via %r resolved to no unique indexed function "
                "— %d registered handler(s) left unconnected",
                table.dispatch_via,
                len(handlers),
            )
            continue
        _record_handlers(conn, dispatcher, handlers, (plain_index, name_index), (resolved, fuzzy))
    return resolved, fuzzy


## @brief Record one dispatcher's handler edges into the resolved/fuzzy buckets.
## @param conn Open connection.
## @param dispatcher Rowid of the declared dispatching function.
## @param handlers Handler names harvested for this table.
## @param indexes (plain name index, definition-preferring name index).
## @param buckets (resolved accumulator, fuzzy accumulator).
## @return None.
## @version 1
## @dg_internal
def _record_handlers(
    conn: sqlite3.Connection,
    dispatcher: int,
    handlers: list[str],
    indexes: tuple[dict[str, list[int]], dict[str, list[int]]],
    buckets: tuple[list[tuple[int, int, str]], list[tuple[int, int, str]]],
) -> None:
    """Split from `_table_edges` so each stays one readable idea; a qualified
    handler takes the exact-overload path while a bare one takes the shared
    tiering that Layers 3 and 4 already use.

    @brief File one dispatcher's handlers as resolved or fuzzy edges.
    @version 1
    """
    plain_index, name_index = indexes
    resolved, fuzzy = buckets
    for handler in handlers:
        if "::" in handler:
            rowid = _resolve_declared_function(conn, handler, name_index)
            if rowid is not None and rowid != dispatcher:
                resolved.append((dispatcher, rowid, CALL_SOURCE_DECLARED_DISPATCH))
            continue
        _ast_record_call_edge(
            dispatcher, handler, plain_index, resolved, fuzzy, CALL_SOURCE_DECLARED_DISPATCH
        )


# ─── insertion + the stage driver ───────────────────────────────────────────


## @brief Insert synthetic call edges at their two confidence tiers.
## @param conn Open connection.
## @param resolved Single-target edges.
## @param fuzzy Multi-candidate edges.
## @return (resolved inserted, fuzzy inserted).
## @version 1
## @dg_internal
def _insert_edges(
    conn: sqlite3.Connection,
    resolved: list[tuple[int, int, str]],
    fuzzy: list[tuple[int, int, str]],
) -> tuple[int, int]:
    """A single-target edge is 'resolved'; several candidates degrade to 'fuzzy'
    through the shared `_ast_record_call_edge` tiering, exactly as Layers 3 and 4
    do — and the weaker tier is skipped by BOTH the reachability and
    thread-membership BFS, so the distinction is load-bearing, not cosmetic.

    @brief Bulk-insert declared-dispatch call edges, ignoring duplicates.
    @version 2
    """
    sql = (
        "INSERT OR IGNORE INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, ?, ?)"
    )
    inserted_resolved = conn.executemany(
        sql, [(*e, CALL_MATCH_RESOLVED) for e in resolved]
    ).rowcount
    inserted_fuzzy = conn.executemany(sql, [(*e, CALL_MATCH_FUZZY) for e in fuzzy]).rowcount
    return inserted_resolved, inserted_fuzzy


## @brief Insert declared interface-boundary terminus rows.
## @param conn Open connection.
## @param boundaries (caller rowid, qualified interface method) pairs.
## @return Number of rows inserted.
## @version 1
## @dg_internal
def _insert_boundaries(conn: sqlite3.Connection, boundaries: list[tuple[int, str]]) -> int:
    """Every enumerated value is BOUND, not spelled into the SQL text: the kind,
    the provenance and the strength each have exactly one registered spelling, and
    a drifted literal here would be caught only by whichever CHECK happened to
    reject it mid-build.

    @brief Bulk-insert `interface_boundary` termini, ignoring duplicates.
    @version 2
    """
    return conn.executemany(
        "INSERT OR IGNORE INTO external_boundaries "
        "(memberdef_rowid, global_name, kind, source, confidence) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            (
                rowid,
                name,
                BOUNDARY_KIND_INTERFACE,
                CALL_SOURCE_DECLARED_DISPATCH,
                BOUNDARY_STRENGTH_HIGH,
            )
            for rowid, name in boundaries
        ],
    ).rowcount


## @brief Harvest the declared registration sites across the whole index.
## @param conn Open connection.
## @param repo_root Repository root (for resolving indexed relative paths).
## @param manifest The parsed dispatch manifest.
## @param cache Optional incremental index cache; None disables caching.
## @param extra_key Manifest-derived cache-key component.
## @param harvester Pre-built harvester from the shared parse pass; built here when omitted.
## @return Flat list of [registrar, handler] pairs, or [] when nothing to do.
## @version 2
## @dg_internal
def _harvest_sites(
    conn: sqlite3.Connection,
    repo_root: Path,
    manifest: DispatchManifest,
    cache: IndexCache | None,
    extra_key: str,
    harvester: Harvester | None = None,
) -> list[list[str]]:
    """Skipped entirely when no `dispatch_tables` are declared, so a repo that
    declares only interfaces pays no AST walk at all — which is also why
    `dispatch_harvester` returns None for that case rather than an inert object.

    @brief Drive the per-file registration harvest.
    @version 2
    """
    ts_classes = try_import_tree_sitter()
    harvester = harvester or dispatch_harvester(manifest, extra_key)
    if harvester is None:
        return []
    if ts_classes is None:
        logger.info("tree_sitter not available — skipping declared dispatch-table harvest")
        return []
    return [
        site
        for _rowid, payload in run_harvest(conn, repo_root, harvester, ts_classes, cache)
        for site in payload
    ]


## @brief Layer 6: emit the call edges and termini the dispatch declaration implies.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root (for resolving indexed relative paths).
## @param manifest The parsed dispatch manifest.
## @param cache Optional incremental index cache; None disables caching.
## @param extra_key Manifest-derived cache-key component for the AST harvest.
## @param harvester Pre-built harvester from the shared parse pass; built here when omitted.
## @return None.
## @version 2
## @req REQ-DDB-SCHEMA-004
def import_declared_dispatch_edges(
    db_path: Path,
    repo_root: Path,
    manifest: DispatchManifest,
    cache: IndexCache | None = None,
    extra_key: str = "",
    harvester: Harvester | None = None,
) -> None:
    """No declaration means no work and no rows — the state every repo is in
    today, and the one every existing build must keep reproducing exactly.

    @brief Import declared-dispatch call edges and interface termini.
    @version 2
    """
    if manifest.is_empty():
        return
    conn = sqlite3.connect(str(db_path))
    _ensure_external_boundaries_table(conn)
    if not _table_exists(conn, "call_edges"):
        logger.warning("dispatch: call_edges is absent — skipping declared-dispatch stage")
        conn.close()
        return

    resolved: list[tuple[int, int, str]] = []
    fuzzy: list[tuple[int, int, str]] = []
    boundaries: list[tuple[int, str]] = []
    for binding in manifest.interfaces:
        binding_resolved, binding_fuzzy, binding_boundaries = _interface_edges(conn, binding)
        resolved += binding_resolved
        fuzzy += binding_fuzzy
        boundaries += binding_boundaries

    sites = _harvest_sites(conn, repo_root, manifest, cache, extra_key, harvester)
    table_resolved, table_fuzzy = _table_edges(conn, manifest, sites)
    inserted = _insert_edges(conn, resolved + table_resolved, fuzzy + table_fuzzy)
    inserted_boundaries = _insert_boundaries(conn, boundaries)
    conn.commit()
    conn.close()
    logger.info(
        "dispatch: %d registration site(s) -> %d resolved + %d fuzzy declared_dispatch "
        "call_edges, %d interface-boundary terminus row(s)",
        len(sites),
        inserted[0],
        inserted[1],
        inserted_boundaries,
    )
