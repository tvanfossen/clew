# SPDX-License-Identifier: MIT
"""Two-layer call-graph importer for the unified `call_edges` table.

Schema: `call_edges(caller_rowid, callee_rowid, source, confidence)`
where source ∈ {doxygen_sqlite, macro_hop, ast, ast_member, fnptr,
declared_dispatch, binding} and
confidence ∈ {exact, resolved, fuzzy}. Each layer populates the table with a
different source tag; `mark_reachability` reads the union.

`ast` vs `ast_member` both come from Layer 3 but are kept apart on purpose: an
`ast` edge's callee was a bare identifier (a free function, unambiguous), while
an `ast_member` edge was recovered by unwrapping a member/qualified/template
callee down to its unqualified tail, which often matches several classes. On
On a large C++ codebase the `ast_member` layer dominates, and it is mostly
fuzzy — merging them would hide exactly the distinction a consumer needs to
weigh an edge.

  Layer 1 — `build_call_edges`:
      Imports inline-context xrefs from doxygen's sqlite3 backend.
      confidence='exact'.

  Layer 3 — `import_ast_call_edges`:
      Walks tree-sitter ASTs of every indexed C/C++ file. Catches
      static helpers, calls through macros, calls inside lambdas, and
      calls in source files that lack doxygen-formatted docstrings
      entirely. confidence='resolved' for unique-name matches,
      'fuzzy' when multiple candidates share a name.

  Layer 4 — `callback_edges.import_callback_registration_edges` (a
      sibling module, not defined here): resolves calls through a
      registered callback (`GLOBAL = PARAM;` inside a registration
      function, then `GLOBAL(...)` call sites elsewhere) into real
      call_edges rows. source='fnptr'.

Layer 3 (and Layer 4, which reuses its AST plumbing) is graceful-
fallback: if tree_sitter or its grammars aren't installed, we log and
skip without aborting.

  SELF-EDGE GUARD — `prune_fabricated_self_edges`, run at the end of
      Layer 3 because that is the only point where every name-resolving
      layer has run AND the AST evidence to check them is in hand. See
      its docstring for the call-shape rule and the measured mechanisms.

@brief Two-layer call-graph importers (+ sibling Layer 4, fnptr) and the
       self-edge guard.
@version 5
"""

from __future__ import annotations

import bisect
import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import (
    Harvester,
    _ast_parse_one_file,
    _ts_language_for,
    run_harvest,
    try_import_tree_sitter,
)
from .indexcache import IndexCache
from .pyast import SELF_NAMES, harvest_calls, is_python_tree, node_text
from .vocabulary import (
    CALL_MATCH_RESOLVED,
    CALL_SOURCE_AST,
    CALL_SOURCE_AST_MEMBER,
    CALL_SOURCE_BINDING,
    CALL_SOURCE_DOXYGEN_SQLITE,
    CALL_SOURCE_FNPTR,
    CALL_SOURCE_MACRO_HOP,
    STAGE_AST_CALLS,
    check,
)

# Re-exported for the sibling AST stages (callback_edges, shared_key_edges,
# threads, doxygen) that grew up importing this plumbing from here; it now
# lives in `harvest` so the harvest driver has no back-dependency on this module.
__all__ = [
    "_ast_caller_at_line",
    "_ast_parse_one_file",
    "_build_function_indexes",
    "_ts_language_for",
    "build_call_edges",
    "import_ast_call_edges",
    "prune_fabricated_self_edges",
]

# ─── Layer 1: doxygen sqlite3 inline xrefs ──────────────────────────────────


## @brief Create call_edges table keyed on memberdef.rowid and import.
## @version 6
## @req REQ-DDB-PIPE-003
def build_call_edges(db_path: Path) -> None:
    """Create call_edges table keyed on memberdef.rowid and import
    inline-context xrefs emitted by doxygen's sqlite3 backend.

    'inline' in doxygen's xref context means "referenced from within
    a function body" — the closest proxy for a call edge in the
    sqlite3 backend. The `source` CHECK includes 'fnptr' for the
    sibling `callback_edges` module's Layer 4, which inserts into this
    same table after Layers 1-3 have run.

    @brief Build call_edges table and import doxygen sqlite3 inline xrefs.
    @version 6
    """
    conn = sqlite3.connect(str(db_path))
    conn.execute("DROP TABLE IF EXISTS call_edges")
    conn.execute(
        f"""
        CREATE TABLE call_edges (
            caller_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            callee_rowid INTEGER NOT NULL REFERENCES memberdef(rowid),
            source       TEXT NOT NULL {check("call_edges", "source")},
            confidence   TEXT NOT NULL {check("call_edges", "confidence")},
            -- WHY this edge exists, when the answer is a macro (gh#350). NULL on every
            -- other layer, because only the macro hop is COMPOSED from two observations
            -- and only there is the intermediary a thing a caller cannot see. It is the
            -- macro's memberdef ROWID and not its expansion TEXT: doxygen already stores
            -- that text in `memberdef.initializer`, and copying it here would create a
            -- second place for it to be stale. The query layer joins for it.
            via_macro_rowid INTEGER REFERENCES memberdef(rowid),
            UNIQUE(caller_rowid, callee_rowid, source)
        )
        """,
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_call_edges_caller ON call_edges(caller_rowid)",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_call_edges_callee ON call_edges(callee_rowid)",
    )
    imported = conn.execute(
        """
        INSERT OR IGNORE INTO call_edges
            (caller_rowid, callee_rowid, source, confidence)
        SELECT x.src_rowid, x.dst_rowid, 'doxygen_sqlite', 'exact'
        FROM xrefs x
        JOIN memberdef m1 ON m1.rowid = x.src_rowid
        JOIN memberdef m2 ON m2.rowid = x.dst_rowid
        WHERE x.context = 'inline'
          AND m1.kind = 'function'
          AND m2.kind = 'function'
        """,
    ).rowcount
    conn.commit()
    conn.close()
    logger.info("call_edges: imported %d edges from doxygen sqlite3 xrefs", imported)


## @brief True when a table exists (a mini/partial db may lack doxygen's xrefs).
## @param conn Open connection.
## @param name Table to look for.
## @return True if a user table of that name exists.
## @version 1
## @dg_internal
def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    """@brief Report whether a user table exists.
    @return True when present.
    @version 1
    """
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
        (name,),
    ).fetchone()
    return row is not None


## @brief Compose caller→callee edges through the macro hop doxygen already records.
## @param db_path Path to the clew.db being built.
## @return Number of edges imported.
## @version 4
## @req REQ-DDB-PIPE-003
def import_macro_hop_edges(db_path: Path) -> int:
    """Recover the calls a codebase makes THROUGH function-like macros.

    THE HOPS WERE ALWAYS THERE. doxygen models a `#define` as a first-class memberdef of
    `kind='macro definition'` and records both halves in `xrefs`:
    `caller (function) → STORE_SET_FOO (macro definition)` and
    `STORE_SET_FOO → store_set (function)`. `import_call_edges` requires BOTH endpoints
    to be `kind='function'`, so every one of those pairs was discarded — and a codebase
    whose accessor convention is entirely macros therefore produced ZERO outgoing call
    edges for its macro-only callers. Not a doxygen limitation; ours.

    Composing the two hops is sound: expanding the macro at that call site produces a
    call to the callee. A macro that wraps SEVERAL calls emits several edges, and all of
    them are real — the caller does reach each one.

    NOT FIXED BY THE PREPROCESSOR, which is where I looked first and was wrong.
    `MACRO_EXPANSION=YES` + `EXPAND_ONLY_PREDEF=NO` is a measured NO-OP here: zero delta
    on memberdef, functions, bodies, call_edges by source and shared_key_edges, on a
    purpose-built fixture AND on entropic, with the instrument validated (on a macro that
    GENERATES definitions the same flag moves functions 1→5 and edges 1→13).

    CONFIDENCE is 'resolved', not 'exact'. Both hops are doxygen's own observations, so
    this is stronger than any name match — but the join is ours, and 'exact' is reserved
    for what doxygen stated directly. `CALL_SOURCE` ranks it accordingly.

    SCOPE IS THE REAL GATE, and it is worth knowing before trusting a zero here: with the
    macro's DEFINING HEADER outside the indexed set, doxygen has no macro memberdef to
    hang either hop on — measured, macro rows 7→1 and function→macro xrefs 15→0, so the
    call sites leave no trace at all. Documentation is NOT the gate (undocumented macros
    index fine under the forced `EXTRACT_ALL`). So an empty result here means "no
    macro-mediated calls IN SCOPE", which is a claim about `index_scope`, not about the
    repo.

    Self-referential and non-function endpoints are excluded: a macro referencing itself
    or another macro would compose a hop that is not a call.

    THE MACRO ITSELF IS NOW RECORDED (gh#350), in `via_macro_rowid`. Before it, a caller saw
    an edge at confidence `resolved` and could not see the thing that made it — the one layer
    here whose edge does not correspond to any text in the caller's body. Naming the
    intermediary PUBLISHES A FACT: it infers no role, needs no threshold and needs no ranking.
    The caller reads the macro and judges for itself. That is deliberately the opposite of the
    rejected auto-discovery direction, which tried to infer a role FROM the expansion and could
    not, because `do { } while (0)` is a disabled trace macro AND a compiler hint AND a
    portability stub.

    `MIN(macro.rowid)` RATHER THAN AN ARBITRARY PICK, and it is a real choice. `UNIQUE(caller,
    callee, source)` means one caller→callee pair holds ONE macro-hop row even when the pair is
    genuinely reachable through two different macros, so something has to choose. Joining the
    macro to the UNIQUE key would multiply rows per neighbour, which is the inflation gh#38
    removed — every neighbour list doubled and every depth cap truncating half the real edges.
    So the pair stays one row and `MIN` makes which macro it names DETERMINISTIC; a bare
    `DISTINCT` left it to whatever the query planner returned first, which would differ between
    two builds of the same commit. The macro named is therefore ONE witness, not the only one.

    @brief Import call edges composed through a macro definition, naming the macro.
    @return Count of edges imported.
    @version 4
    """
    conn = sqlite3.connect(str(db_path))
    try:
        if not _table_exists(conn, "xrefs"):
            logger.info("call_edges: no xrefs table — skipping the macro hop layer")
            return 0
        imported = conn.execute(
            f"""
            INSERT OR IGNORE INTO call_edges
                (caller_rowid, callee_rowid, source, confidence, via_macro_rowid)
            SELECT xin.src_rowid, xout.dst_rowid,
                   '{CALL_SOURCE_MACRO_HOP}', '{CALL_MATCH_RESOLVED}',
                   MIN(macro.rowid)
            FROM xrefs xin
            JOIN memberdef caller ON caller.rowid = xin.src_rowid
            JOIN memberdef macro  ON macro.rowid  = xin.dst_rowid
            JOIN xrefs xout       ON xout.src_rowid = macro.rowid
            JOIN memberdef callee ON callee.rowid = xout.dst_rowid
            WHERE caller.kind = 'function'
              AND macro.kind  = 'macro definition'
              AND callee.kind = 'function'
              AND xin.src_rowid <> xout.dst_rowid
            GROUP BY xin.src_rowid, xout.dst_rowid
            """,
        ).rowcount
        conn.commit()
    finally:
        conn.close()
    logger.info("call_edges: imported %d edges composed through a macro definition", imported)
    return imported


# ─── Layer 3: tree-sitter AST walk ──────────────────────────────────────────


## @brief Build name->rowids and bodyfile_id->function-range indexes.
## @version 3
## @dg_internal
def _build_function_indexes(
    conn: sqlite3.Connection,
) -> tuple[dict[str, list[int]], dict[int, list[tuple[int, str, int, int]]]]:
    """Build (name → rowids) and (bodyfile_id → [(rowid, name, bodystart, bodyend)]).

    Grouped by `bodyfile_id` — the file the body actually lives in — not
    `file_id`. Doxygen assigns EVERY memberdef a `file_id` (the declaring
    file) and gives even a bare prototype (no body at all) a nonzero
    `bodystart`/`bodyend` pair; when a function is declared in one file
    and defined in another, its `bodyfile_id` correctly points at the
    defining file while `file_id` still points at the declaration.
    Grouping by `file_id` files a declaration-only row's bogus body range
    under the WRONG file, where it can coincidentally overlap a real
    function's actual body range and make `_ast_caller_at_line` pick the
    declaration instead of the true enclosing function (confirmed live:
    a cross-file callback-registration chain was misattributed this way).

    @brief Build name->rowids and bodyfile_id->function-range indexes.
    @version 3
    """
    name_to_rowids: dict[str, list[int]] = {}
    for rowid, name in conn.execute(
        "SELECT rowid, name FROM memberdef WHERE kind = 'function'",
    ).fetchall():
        name_to_rowids.setdefault(name, []).append(rowid)
    file_funcs: dict[int, list[tuple[int, str, int, int]]] = {}
    for rowid, name, file_id, bodyfile_id, bodystart, bodyend in conn.execute(
        """
        SELECT rowid, name, file_id, bodyfile_id, bodystart, bodyend
        FROM memberdef
        WHERE kind = 'function' AND bodystart > 0
        """,
    ).fetchall():
        file_funcs.setdefault(bodyfile_id or file_id, _FuncRanges()).append(
            (rowid, name, bodystart, bodyend),
        )
    return name_to_rowids, file_funcs


# The three provenance tags this module and its Layer 4 sibling write. They are
# RE-EXPORTS of the `call_source` vocabulary members, not second spellings: the
# same tokens are the CHECK on `call_edges.source`, and a constant that drifts
# from its own CHECK fails at INSERT time with no hint of which of the two is
# wrong. The commentary stays here, beside the code that decides between them.

## Provenance for an edge whose callee was a bare `identifier` — a free
## function, unambiguous by construction.
SOURCE_AST = CALL_SOURCE_AST
## Provenance for an edge recovered by UNWRAPPING a member/qualified/template
## callee. The name that survives is the unqualified tail (`obj.method()` ->
## `method`), which frequently matches several classes, so these skew heavily
## fuzzy — most of what this layer recovers. Kept separable rather
## than merged into 'ast' so a consumer can weigh them: chain_trace can opt in
## deliberately, and callers/callees can label them instead of silently mixing
## a name-only match in with a confirmed one.
SOURCE_AST_MEMBER = CALL_SOURCE_AST_MEMBER
## Provenance for an edge resolved through a registered function pointer
## (Layer 4, callback_edges). Shares _ast_record_call_edge's tiering.
SOURCE_FNPTR = CALL_SOURCE_FNPTR
## Provenance for a reference that was BOUND rather than called — a keyword argument
## handing a function to a framework that will invoke it later (gh#1). Shares
## _ast_record_call_edge's tiering, which is why it can never be graded 'exact': a
## single candidate earns 'resolved' and several earn 'fuzzy'.
SOURCE_BINDING = CALL_SOURCE_BINDING


## @brief One file's function body ranges, with a bisect index when they do not nest.
## @version 1
## @dg_internal
class _FuncRanges(list):
    """A `list` SUBCLASS SO EVERY EXISTING CONSUMER IS UNTOUCHED. Nine call sites across four
    modules take this value and most only iterate it; making the acceleration a separate
    structure would mean changing all of them and their signatures to gain the same answer.

    THE DISJOINT TEST IS WHAT MAKES THE FAST PATH SAFE. When no two body ranges overlap, exactly
    one can contain a given line, so bisect and a scan cannot disagree — the result is identical
    by construction rather than by testing. Nesting is the only case where "the enclosing
    function" is ambiguous, and there the scan is kept.

    In C and C++ most files are entirely disjoint: bodies sit side by side. Lambdas, nested
    classes and in-class method definitions are what produce nesting, so the fallback is the
    exception rather than the rule.

    @brief A file's function ranges with an optional bisect index.
    @version 1
    """

    __slots__ = ("_starts", "_index")

    ## @brief Build the bisect index, or record that this file must use the scan.
    ## @return None.
    ## @version 1
    ## @dg_internal
    def _prepare(self) -> None:
        """Sorted by body start, then checked for overlap in one pass: ranges are disjoint when
        each start is strictly after the previous end.

        @brief Prepare the lookup index.
        @version 1
        """
        ordered = sorted(self, key=lambda row: (row[2], row[3]))
        disjoint = all(ordered[i][2] > ordered[i - 1][3] for i in range(1, len(ordered)))
        self._index = ordered if disjoint else None
        self._starts = [row[2] for row in ordered] if disjoint else []

    ## @brief The rowid of the function whose body contains `line`.
    ## @param line Source line to locate.
    ## @return The enclosing function's rowid, or None.
    ## @version 1
    ## @dg_internal
    def caller_at(self, line: int) -> int | None:
        """@brief Locate the enclosing function.
        @return Its rowid, or None.
        @version 1
        """
        if getattr(self, "_index", ...) is ...:
            self._prepare()
        if self._index is None:
            ## Nested bodies: preserve the existing answer exactly.
            for rid, _name, bs, be in self:
                if bs <= line <= be:
                    return rid
            return None
        at = bisect.bisect_right(self._starts, line) - 1
        if at < 0:
            return None
        rid, _name, bs, be = self._index[at]
        return rid if bs <= line <= be else None


## @brief Ast caller at line.
## @version 2
## @dg_internal
def _ast_caller_at_line(
    funcs_in_file: list[tuple[int, str, int, int]],
    call_line: int,
) -> int | None:
    """WHICH FUNCTION'S BODY CONTAINS THIS LINE. Linear in the file's function count and called
    once per call site, so its cost is O(functions x call sites) per file — 466,595 calls on a
    1,549-file target, and the shape that grows worst on the corpora that already build slowly.

    THE FAST PATH IS ONLY TAKEN WHEN IT IS PROVABLY IDENTICAL. `_FuncRanges.caller_at` uses a
    bisect when a file's body ranges are DISJOINT, where the containing range is unique and any
    correct method must return it. When ranges nest — a lambda inside a function, a method inside
    a class body — it falls back to this scan, because then "the enclosing function" has more
    than one answer and the existing one must be preserved.

    THAT EXISTING ANSWER IS AN ACCIDENT, WHICH IS WHY IT IS NOT REDEFINED HERE.
    `_build_function_indexes` issues its SELECT with no ORDER BY, so "first in list order" is
    whatever order SQLite happened to return — not a chosen rule. Picking a better one
    (innermost, say) is defensible and is a BEHAVIOUR change: it would move call-edge
    attribution and needs a build-version bump, not a performance patch.

    @brief The rowid of the function whose body contains a line.
    @return The enclosing function's rowid, or None.
    @version 2
    """
    if isinstance(funcs_in_file, _FuncRanges):
        return funcs_in_file.caller_at(call_line)
    for rid, _name, bs, be in funcs_in_file:
        if bs <= call_line <= be:
            return rid
    return None


## @brief Ast record call edge.
## @param caller_rowid Enclosing function's rowid.
## @param callee_name Unqualified callee name harvested from the call site.
## @param name_to_rowids Name index built from _build_function_indexes.
## @param edges_resolved Accumulator for (caller, callee, source) with one match.
## @param edges_fuzzy Accumulator for (caller, callee, source) with several.
## @param source Provenance to stamp: 'ast' (bare identifier) or 'ast_member'.
## @param qualified The qualified callee text the call site wrote, or '' (#75).
## @param definition_of rowid → doxygen `definition` signature, for qualifier narrowing.
## @version 5
## @dg_internal
def _ast_record_call_edge(
    caller_rowid: int,
    callee_name: str,
    name_to_rowids: dict[str, list[int]],
    edges_resolved: list[tuple[int, int, str]],
    edges_fuzzy: list[tuple[int, int, str]],
    source: str = SOURCE_AST,
    *,
    qualified: str = "",
    definition_of: dict[int, str] | None = None,
    receiver: str = "",
    argc: int = -1,
    receiver_types: dict[str, set[str]] | None = None,
    scope_of: dict[int, str] | None = None,
    argc_of: dict[int, int] | None = None,
) -> None:
    """A UNIQUE NAME IS NOT EVIDENCE ABOUT A RECEIVER, and conflating the two made this
    layer assert fabrications as certainties.

    For `source='ast'` a single candidate really is resolved: the call site was a bare
    `identifier`, so the name IS the whole call and there is nothing else to verify.

    For `source='ast_member'` it is not. That edge was recovered by unwrapping
    `obj.method()` / `Ns::Class::method()` down to the UNQUALIFIED tail, so the receiver's
    type was never checked. A single candidate means only "exactly one function in the
    index happens to carry this name" — which is a fact about the index, not about the
    call. Measured on the public entropic index: 1,762 such edges were stamped
    `confidence='resolved'`, and `dossier('store')` returned 34 callers of which ONE was
    real — 2.9% precision, presented as certain. Meanwhile multi-candidate member calls
    were already honestly `fuzzy`, so the layer was MORE trustworthy where it knew less.

    Demoted rather than dropped, deliberately: `ast_member` is the sole evidence for
    77.7% of logical edges, so discarding it would cost far more than it fixes. `fuzzy`
    is exactly what it means — a function of that name exists and the specific one was
    never confirmed — and every consumer already reads that correctly, because both the
    reachability and thread BFS traverse only non-fuzzy edges and the tool descriptions
    already tell a model that `ast_member` edges are mostly fuzzy and may be wrong.

    @brief Record one AST call edge, grading confidence by what was actually verified.
    @return None.
    @version 5
    """
    candidates = name_to_rowids.get(callee_name, [])
    if qualified and candidates:
        ## FAIL CLOSED on a qualified miss, and note that this needs NO branch of its own:
        ## narrowing to nothing leaves `candidates` empty and the loop below emits nothing,
        ## which is exactly what an unindexed free function already does. When the call site
        ## names a class explicitly and no indexed function bears it, the callee is OUTSIDE
        ## the index — `std::to_string`, `nlohmann::json::parse`, `::close` are 299 of the
        ## 662 matchable qualified sites on entropic. Falling back to the unqualified
        ## fan-out here would reintroduce exactly the fabrication fd384e5 removed, but with
        ## the call site's own evidence contradicting it, which is worse than the original.
        candidates = _narrow_by_qualifier(qualified, candidates, definition_of)
        if len(candidates) == 1:
            ## GENUINELY resolved: the class was written at the call site and exactly one
            ## indexed function bears it. This is the only path on which an `ast_member`
            ## edge earns `resolved` — a unique NAME never did (see below).
            edges_resolved.append((caller_rowid, candidates[0], source))
            return
    ## THE RECEIVER'S DECLARED TYPE IS EVIDENCE, and reading it is what makes a member call
    ## verifiable rather than merely reportable. `handle->engine->run_turn(input)` looked
    ## unresolvable only because nobody consulted `engine`'s type, which the index already
    ## holds: scoping to `entropic::AgentEngine` eliminates two same-named helpers in
    ## `tests/model/` outright, and arity separates what remains.
    ##
    ## Placed BEFORE the refusal below so a receiver-verified call earns `resolved` on the same
    ## footing as a qualified one — in both cases the SOURCE TEXT names the target, which is
    ## the distinction that whole refusal rests on.
    if source == SOURCE_AST_MEMBER and receiver and receiver_types:
        narrowed, receiver_verified = _narrow_by_receiver(
            receiver, argc, candidates, receiver_types, scope_of or {}, argc_of or {}
        )
        if receiver_verified and len(narrowed) == 1:
            edges_resolved.append((caller_rowid, narrowed[0], source))
            return
        ## THE RECEIVER IS VERIFIED BUT THE OVERLOAD IS NOT, which is exactly what `fuzzy`
        ## means and the one case where emitting several rows is honest rather than a fan-out.
        ## On entropic both `AgentEngine::run_turn` overloads take ONE argument
        ## (`const std::string&`, `std::vector<Message>`), so arity cannot split them and
        ## distinguishing further needs the argument's TYPE — real type checking, which this
        ## layer does not do.
        ##
        ## What makes this different from the expansion gh#347 removed is the BOUND: every row
        ## here is a method of the class the receiver is DECLARED to be, so the set is the
        ## overloads of one method on one class — not every same-named function in the repo,
        ## which is how `tests/` came to emit 778 edges per function. Fuzzy keeps it out of
        ## `mark_reachability` and the thread BFS while letting `callees` show that the call
        ## exists at all, which is the whole complaint: silence read as "calls nothing".
        if receiver_verified and len(narrowed) > 1:
            for rowid in narrowed:
                edges_fuzzy.append((caller_rowid, rowid, source))
            return
        candidates = narrowed
    unverified_receiver = source == SOURCE_AST_MEMBER
    if len(candidates) == 1 and not unverified_receiver:
        edges_resolved.append((caller_rowid, candidates[0], source))
        return
    ## AN UNRESOLVED CALL PRODUCES NO ROW (gh#347). This used to fan out — one row per
    ## same-named candidate — turning ONE true observation into N assertions. tree-sitter was
    ## never the problem: it correctly found a `call_expression`. The defect was resolving the
    ## callee TOKEN against a name index and, where N memberdefs shared the name, emitting all
    ## N. Measured on entropic: 1,982,040 of 2,049,965 edges (96.7%) were that expansion, and
    ## `tests/` alone emitted 778 edges per function against its own `src/`'s 25.
    ##
    ## A NAME IS NOT EVIDENCE OF LINKAGE, and it cannot be, because it is MUTABLE: rename
    ## `func_a` to `function_a` and anything keyed on the name silently changes meaning, while
    ## a real call chain is invariant under rename because both ends move together. A name is a
    ## human convention for humans reading output — never a key, a join, or proof.
    ##
    ## NOT REPLACED BY A ROW WITH A NULL CALLEE CARRYING THE NAME. That was proposed and
    ## rejected: storing `callee_name` preserves name-as-signal in a column.
    ##
    ## A SINGLE CANDIDATE WITH AN UNVERIFIED RECEIVER ALSO GETS NOTHING, which is why the
    ## `unverified_receiver` term above is load-bearing rather than an optimisation. `obj.foo()`
    ## where exactly one indexed `foo` exists is still not proof that `obj` is that class — the
    ## real receiver may be a class this index never saw.
    ##
    ## This repo already condemned this exact expansion in `event_edges._harvest_tagged`
    ## ("5294 edges where 175 are real") and fixed it for that layer only.
    ##
    ## `edges_fuzzy` stays in the signature deliberately: the insert path reports its length, so
    ## the build log now states a measured ZERO rather than falling silent about a layer that
    ## used to dominate the table.
    return


## Type spellings that name no class, so a receiver declared as one of them tells us nothing.
_NOT_A_CLASS = frozenset(
    {
        "auto",
        "void",
        "bool",
        "char",
        "short",
        "int",
        "long",
        "float",
        "double",
        "size_t",
        "unsigned",
        "signed",
        "wchar_t",
        "nullptr_t",
        "T",
        "U",
    }
)


## @brief The class name a declared type refers to, with wrappers peeled off.
## @param type_text A doxygen `memberdef.type` string.
## @return The bare class name, or '' when none is identifiable.
## @version 1
## @dg_internal
def _receiver_class(type_text: str) -> str:
    """PEELS SMART POINTERS AND REFERENCES, because that is how a receiver is almost always
    spelled. `handle->engine` on entropic has declared type
    `std::unique_ptr< entropic::AgentEngine >`, and the class that owns the method is the
    TEMPLATE ARGUMENT, not the wrapper. Recursing handles the nested case
    (`unique_ptr<shared_ptr<Foo>>`) without a special branch.

    Returns '' rather than a guess for anything unidentifiable — `auto`, a template parameter,
    a function type. An empty result makes the caller fall through to today's behaviour, which
    is to emit no edge.

    @brief Reduce a declared type to its class name.
    @return Class name or ''.
    @version 1
    """
    text = (type_text or "").strip()
    for _ in range(6):
        if "<" not in text:
            break
        inner = text[text.index("<") + 1 : text.rindex(">")] if ">" in text else ""
        ## A multi-argument template (`map<K, V>`) names no single receiver class, so refuse
        ## rather than pick the first argument.
        if "," in inner:
            return ""
        text = inner.strip()
    text = text.replace("*", " ").replace("&", " ").strip()
    words = [w for w in text.split() if w not in ("const", "volatile", "struct", "class", "enum")]
    if len(words) != 1:
        return ""
    ## `auto` and the builtins name no class, so returning them would send the narrowing
    ## looking for a scope that cannot exist. Refuse instead, which falls through to
    ## today's behaviour.
    return "" if words[0] in _NOT_A_CLASS else words[0]


## @brief Declared types of every member variable, keyed by the variable's own name.
## @param conn Open connection to the database being built.
## @return Mapping of variable name to the set of class names it may denote; empty when the
##         table carries no `type` column.
## @version 1
## @dg_internal
def _receiver_types(conn: sqlite3.Connection) -> dict[str, set[str]]:
    """THE RECEIVER'S TYPE IS ALREADY IN THE INDEX, which is the whole basis of this layer.
    doxygen records a member variable with its declared type, so `handle->engine`'s class is a
    documented fact rather than an inference — clew was simply not reading it.

    A SET per name, not one type, because two unrelated classes can both have a member called
    `engine` — and the narrowing REFUSES whenever the set holds more than one, since there is
    then no fact about which class the receiver is. Storing the set rather than the first type
    is what makes that refusal possible; keeping one arbitrary type would look identical and be
    a guess.

    @brief Index member-variable names to their declared classes.
    @return Name-to-classes mapping.
    @version 1
    """
    ## DEGRADES ON A TABLE WITHOUT THE COLUMN rather than raising. A minimal fixture, and any
    ## index predating this layer, has a `memberdef` with no `type` — receiver resolution simply
    ## does not apply there, which is missing knowledge and not an error. Five hermetic tests
    ## build exactly that shape and caught this immediately.
    columns = {str(row[1]) for row in conn.execute("PRAGMA table_info(memberdef)")}
    if not {"type", "kind", "name"} <= columns:
        return {}
    types: dict[str, set[str]] = {}
    for name, type_text in conn.execute(
        "SELECT name, COALESCE(type, '') FROM memberdef WHERE kind = 'variable'"
    ):
        klass = _receiver_class(str(type_text))
        if klass:
            types.setdefault(str(name), set()).add(klass)
    return types


## @brief Candidates whose owning class matches the receiver's declared type.
## @param receiver The receiver's trailing member name, e.g. 'engine'.
## @param argc Argument count at the call site, or -1 when unknown.
## @param candidates Rowids sharing the callee name.
## @param receiver_types Name-to-classes mapping from `_receiver_types`.
## @param scope_of Rowid to owning scope.
## @param argc_of Rowid to declared parameter count.
## @return (survivors, verified) — `verified` is True only when the receiver's class
##         actually matched at least one candidate, so a caller can tell a real narrowing
##         from 'the receiver told us nothing'.
## @version 1
## @dg_internal
def _narrow_by_receiver(
    receiver: str,
    argc: int,
    candidates: list[int],
    receiver_types: dict[str, set[str]],
    scope_of: dict[int, str],
    argc_of: dict[int, int],
) -> tuple[list[int], bool]:
    """TURNS AN UNVERIFIED MEMBER CALL INTO A VERIFIED ONE, using evidence the source text
    already carries. On entropic, `handle->engine->run_turn(input)`:

        engine   is a member variable, declared `std::unique_ptr< entropic::AgentEngine >`
        run_turn has FOUR rows — two `entropic::AgentEngine` overloads, and two unrelated
                 file-local helpers in `tests/model/*.cpp`

    Scoping to the declared class ELIMINATES the two test helpers outright — not
    deprioritises them, eliminates them, because the receiver's type says they cannot be the
    target. Argument count then separates the surviving overloads:
    `(const std::string&)` takes one, `(std::vector<Message>)` takes one — equal, so arity
    cannot split those two, and the call correctly stays unresolved rather than picking.

    RETURNS THE INPUT UNCHANGED when the receiver is unknown, so this can only ever NARROW.
    A receiver that is a local, a parameter, an `auto`, or a name doxygen never indexed leaves
    the caller exactly where it was: no edge, which is today's behaviour.

    @brief Narrow candidates by the receiver's declared class and the call's arity.
    @return Surviving candidates.
    @version 1
    """
    classes = receiver_types.get(receiver or "", set())
    if not classes or not candidates:
        return candidates, False
    ## INTERSECT THE RECEIVER'S POSSIBLE CLASSES WITH THE CLASSES THAT ACTUALLY DECLARE THIS
    ## METHOD, and require exactly one survivor. Two weaker rules were tried and both were
    ## wrong in opposite directions:
    ##
    ##   UNION — accept any candidate matching ANY of the receiver's classes. Measured: 56
    ##   fuzzy groups spanned more than one class, `parse_tool_calls` reaching five classes in
    ##   five files. A cross-file fan-out wearing a type-resolution costume.
    ##
    ##   SINGLE CLASS ONLY — refuse whenever the receiver name is declared more than once.
    ##   Measured: kills the case this exists for, because `engine` is declared in FOUR classes
    ##   in entropic (an AgentEngine unique_ptr, an AgentEngine*, a Python ChessEngine, an
    ##   `auto`), so `run_turn` refused again.
    ##
    ## The intersection is what carries evidence: `engine` may be four things, but only ONE of
    ## them declares `run_turn`, so the pair (receiver name, method name) pins the class even
    ## though neither does alone. `parse_tool_calls` exists on all five of its receiver's
    ## classes, so it stays refused — which is correct, since nothing here distinguishes them.
    ## COUNTED AS DISTINCT SCOPES, NOT DISTINCT TYPE SPELLINGS, and that distinction cost a
    ## fourth iteration to find. `engine` is declared both as
    ## `std::unique_ptr< entropic::AgentEngine >` and as `AgentEngine *`, which are the SAME
    ## class written two ways; `_scope_is` matches either against the one real scope, so
    ## counting spellings saw two owners and refused. The target is a scope in the index, so
    ## the scope is what must be unique.
    matched = {
        scope_of.get(rowid, "")
        for rowid in candidates
        if any(_scope_is(scope_of.get(rowid, ""), klass) for klass in classes)
    }
    if len(matched) != 1:
        return candidates, False
    scope_only = next(iter(matched))
    scoped = [rowid for rowid in candidates if scope_of.get(rowid, "") == scope_only]
    ## NO MATCH IS NOT A NARROWING, and conflating the two nearly reshipped the exact fan-out
    ## gh#347 removed. Returning the untouched candidate list with `verified=False` is what
    ## stops the caller emitting one row per same-named function in the repo: measured, that
    ## mistake put 11,390 fuzzy edges into the entropic index in a single build.
    if not scoped:
        return candidates, False
    if len(scoped) > 1 and argc >= 0:
        by_arity = [rowid for rowid in scoped if argc_of.get(rowid, -1) == argc]
        if by_arity:
            return by_arity, True
    return scoped, True


## @brief Whether a memberdef scope denotes the given class.
## @param scope The `memberdef.scope` value.
## @param klass A class name, possibly unqualified.
## @return True when they name the same class.
## @version 1
## @dg_internal
def _scope_is(scope: str, klass: str) -> bool:
    """Matched at a `::` boundary in BOTH directions, because either side may be the qualified
    one: a member declared `AgentEngine*` has an unqualified class while the method's scope is
    `entropic::AgentEngine`, and the reverse happens when a type is written fully qualified in
    a namespace the method's scope omits. A bare substring test would let `Engine` match
    `MyEngineFactory`.

    @brief Compare a scope against a class name.
    @return True on a boundary-respecting match.
    @version 1
    """
    if not scope or not klass:
        return False
    return scope == klass or scope.endswith("::" + klass) or klass.endswith("::" + scope)


## @brief Candidates whose signature actually bears the qualified name written at the call site.
## @param qualified The qualified callee text, e.g. 'Ns::Class::method'.
## @param candidates Same-named memberdef rowids.
## @param definition_of Maps a rowid to its doxygen `definition` signature.
## @return The subset whose signature contains the qualified name at identifier boundaries.
## @version 1
## @dg_internal
def _narrow_by_qualifier(
    qualified: str,
    candidates: list[int],
    definition_of: dict[int, str] | None,
) -> list[int]:
    """Uses `query._common._qualified_match`, which is the SAME boundary-checked comparison
    `rowids_for_name` already relies on — so `CoLinkOwner::run` cannot satisfy a search for
    `LinkOwner::run`. Reusing it rather than writing a second matcher is the point: two
    implementations of "does this signature bear this qualified name" would drift.

    Without a `definition_of` map the caller cannot narrow anything, so every candidate
    survives and the normal fan-out applies. That keeps the two sibling callers
    (`callback_edges`, `dispatch_edges`) working unchanged — neither has qualified call
    sites to narrow.

    @brief Filter same-named candidates by the qualified name at the call site.
    @return Matching rowids, possibly empty.
    @version 1
    """
    if not definition_of:
        return list(candidates)
    from .query._common import _qualified_match

    return [c for c in candidates if _qualified_match(definition_of.get(c, ""), qualified)]


# A call's `function` node is only a bare `identifier` for a free function.
# Every C++ member call, qualified call and template call wraps that identifier,
# and requiring the bare form dropped two thirds of a C++ codebase's call_expressions
# — field_expression 1006, qualified_identifier 995, template_function 406. C is
# barely affected on C codebases, which is why the gap read as "C++ is
# just sparse". Unwrapping yields the UNQUALIFIED tail, which is what
# `memberdef.name` stores; names that belong to stdlib/vendored code simply fail
# to resolve later, exactly as an unknown free function already does.
_CALLEE_TERMINAL = ("identifier", "field_identifier", "destructor_name", "operator_name")
_CALLEE_UNWRAP = {
    "field_expression": "field",  # obj.method() / ptr->method() / rust: obj.method()
    "qualified_identifier": "name",  # Ns::Class::method()
    # tree-sitter-rust's node for a qualified path call (`Type::method()`,
    # `module::func()`, `std::thread::spawn()`) — the direct Rust analogue of
    # C++'s qualified_identifier, and it happens to use the SAME field name
    # ("name"), so this is the only entry Rust's call-site harvest needed: the
    # walk below is driven entirely by tree-sitter node TYPE names, not by a
    # language flag, and `call_expression`/`field_expression`/`identifier` are
    # spelled identically in both grammars.
    "scoped_identifier": "name",  # rust: Type::method() / module::func()
    "template_function": "name",  # f<T>()
    "template_method": "name",  # obj.f<T>()
    "parenthesized_expression": None,  # (f)() — unwrap the sole child
}
_MAX_CALLEE_UNWRAP = 8


## @brief Reduce a call's `function` node to the identifier naming the callee.
## @param callee The call_expression's `function` child (may be None).
## @return The naming identifier node, or None when the callee is not a static name.
## @version 1
## @dg_internal
def _callee_name_node(callee: Any) -> Any:
    """Peel member/qualified/template wrappers off a callee.

    Bounded iteration rather than recursion: a pathological chain cannot spin,
    and anything still unresolved after a few peels (a call through a function
    POINTER, a lambda, a functor's operator()) is correctly refused — those have
    no static callee name and belong to the fnptr layer, not here.
    """
    node = callee
    for _ in range(_MAX_CALLEE_UNWRAP):
        # None and a terminal are both final answers: None means the chain
        # dead-ended, a terminal is the name we were peeling towards.
        if node is None or node.type in _CALLEE_TERMINAL:
            return node
        if node.type not in _CALLEE_UNWRAP:
            return None
        field = _CALLEE_UNWRAP[node.type]
        node = node.child_by_field_name(field) if field else _sole_child(node)
    return None


## @brief The single named child of a wrapper node, if it has exactly one.
## @param node Parent node.
## @return The lone named child, or None.
## @version 2
## @dg_internal
def _sole_child(node: Any) -> Any:
    """@brief Return the only named child, else None (ambiguous to unwrap)."""
    named = [c for c in node.children if c.is_named]
    return named[0] if len(named) == 1 else None


## @brief Harvest one file's rowid-free (callee_name, call_line, source) call sites.
## @return List of [callee_name, call_line, source] triples in walk order.
## @version 8
## @dg_internal
def _ast_harvest_calls(tree: Any, src_bytes: bytes) -> list[list[Any]]:
    """Walk the parse tree iteratively, recording every direct call's callee
    identifier, source line, and whether the callee had to be UNWRAPPED from a
    member/qualified/template form. Deliberately rowid-free so the result can be
    cached against the file's content sha and re-resolved on a later build
    against that build's (different) memberdef rowids.

    A Python tree is handed to `pyast.harvest_calls`, which emits the SAME
    `[name, line, source]` shape and the SAME two provenance tags. The dialects
    are split rather than merged because Python names different nodes for the
    same concepts (`call`/`attribute` against `call_expression`/`field_expression`)
    — one walker serving both would make every branch conditional on a language
    the C path never needs to know about, and the C path's output is pinned by
    test precisely so this addition cannot perturb it.

    RUST NEEDS NO SEPARATE BRANCH. tree-sitter-rust spells calls/method-calls/
    identifiers identically to C++ (`call_expression`, `field_expression` with a
    `field` field, bare `identifier`) — the one node type it names differently is
    a qualified path (`scoped_identifier` where C++ has `qualified_identifier`),
    which `_CALLEE_UNWRAP` already maps to the same "name" field. So this walker
    falls through to the C/C++ path below for a Rust tree and produces the same
    `[name, line, source]` shape with no Rust-specific code here at all.

    @brief Per-file call-site harvest (C/C++/Rust here, Python via pyast).
    @version 7
    """
    if is_python_tree(tree):
        return harvest_calls(tree, src_bytes, SOURCE_AST, SOURCE_AST_MEMBER, SOURCE_BINDING)
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call_expression":
            continue
        raw_callee = node.child_by_field_name("function")
        callee_node = _callee_name_node(raw_callee)
        if callee_node is None:
            continue
        source = SOURCE_AST if callee_node is raw_callee else SOURCE_AST_MEMBER
        callee_name = src_bytes[callee_node.start_byte : callee_node.end_byte].decode(
            "utf-8", errors="replace"
        )
        ## KEEP THE QUALIFIER (#75). Peeling `Ns::Class::method()` to its tail is what lets
        ## it match `memberdef.name` — and it also discards the one piece of evidence that
        ## could say WHICH `method`. Measured on the entropic index: 2,301 of 10,723
        ## member-ish call sites (21%) are qualified, so the class is written right there and
        ## was being thrown away. `_common._qualified_match` already knows how to use it.
        ##
        ## A FOURTH payload element rather than a reshape: `_fold_call_sites` already reads
        ## `site[2] if len(site) > 2`, so a shorter cached payload from an older build stays
        ## readable instead of raising.
        ## FIFTH AND SIXTH elements, appended for #482 rather than reshaping, exactly as the
        ## qualifier was: `_fold_call_payload` reads each index defensively, so a payload
        ## cached by an older build stays foldable. The stage_version bump makes that cold.
        ##
        ## These two are what turn an unverified member call into a verified one. The
        ## receiver's declared type is already in the index — `handle->engine` is a member
        ## variable of type `std::unique_ptr< entropic::AgentEngine >` — so scoping the callee
        ## to that class eliminates same-named functions in unrelated files outright. Arity
        ## then separates surviving overloads.
        sites.append(
            [
                callee_name,
                node.start_point[0] + 1,
                source,
                _qualifier_text(raw_callee, src_bytes),
                _receiver_tail(raw_callee, src_bytes),
                _call_argc(node),
            ]
        )
    return sites


## @brief The trailing member name of a member call's receiver.
## @param raw_callee The call_expression's `function` child.
## @param src_bytes The file's bytes, for slicing.
## @return e.g. 'engine' for `handle->engine->run_turn()`, or '' when there is no receiver.
## @version 1
## @dg_internal
def _receiver_tail(raw_callee: Any, src_bytes: bytes) -> str:
    """THE TAIL, not the whole expression. For `handle->engine->run_turn(input)` the callee is
    a `field_expression` whose `argument` is itself `handle->engine`; the piece that has a
    DECLARED TYPE in the index is that inner expression's own `field`, `engine`. Taking the
    outer text (`handle->engine`) would match no memberdef, and taking the root (`handle`)
    would resolve to the handle's type rather than the engine's.

    A bare-identifier receiver (`obj.method()`) yields `obj`, which usually names a local or
    parameter that doxygen does not index — that simply fails to resolve later, which is the
    correct outcome and not a special case here.

    @brief Extract the receiver's trailing member name.
    @return The name, or ''.
    @version 1
    """
    if raw_callee is None or raw_callee.type != "field_expression":
        return ""
    recv = raw_callee.child_by_field_name("argument")
    if recv is None:
        return ""
    node = recv.child_by_field_name("field") if recv.type == "field_expression" else recv
    if node is None or node.type not in ("identifier", "field_identifier"):
        return ""
    return src_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


## @brief How many arguments a call site passes.
## @param call_node The call_expression node.
## @return The count, or -1 when the argument list cannot be read.
## @version 1
## @dg_internal
def _call_argc(call_node: Any) -> int:
    """Counts NAMED children of the `arguments` node, so punctuation is not counted. Returns -1
    rather than 0 when the list is unreadable, because 0 is a real arity and conflating "no
    arguments" with "unknown" would make arity narrowing pick a nullary overload for a call
    whose arguments were simply not parsed.

    @brief Count a call's arguments.
    @return Count, or -1 when unknown.
    @version 1
    """
    args = call_node.child_by_field_name("arguments")
    if args is None:
        return -1
    return sum(1 for child in args.children if child.is_named)


## @brief The full qualified callee text, when the call site wrote one.
## @param raw_callee The call_expression's `function` child.
## @param src_bytes The file's bytes, for slicing.
## @return e.g. 'Ns::Class::method', or '' when the callee carries no qualifier.
## @version 3
## @dg_internal
def _qualifier_text(raw_callee: Any, src_bytes: bytes) -> str:
    """Only a `qualified_identifier` (or, for Rust, its `scoped_identifier`
    analogue — `Type::method`/`module::func`) is reported. A `field_expression`
    (`obj.method()`) names a RECEIVER, not a type — resolving those needs the
    receiver's declared type, which is 79% of the member-ish sites and a much
    larger job.

    A `template_function` is unwrapped one level first, because `Class::method<T>()` puts
    the qualified name inside the template node.

    @brief Extract the qualified callee text when present.
    @return Qualified name, or ''.
    @version 3
    """
    node = raw_callee
    if node is not None and node.type == "template_function":
        node = node.child_by_field_name("name")
    if node is None or node.type not in ("qualified_identifier", "scoped_identifier"):
        return ""
    return src_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


## @brief Layer 3's cacheable per-file call-site harvester.
## @version 1
class _CallSiteHarvester(Harvester):
    """Records `(callee_name, call_line)` per file for Layer 3.

    @brief Layer 3 per-file harvester.
    @version 1
    """

    stage = STAGE_AST_CALLS
    # Bump when _ast_harvest_calls' extraction changes.
    # 2: sites carry provenance (ast vs ast_member)
    # 3: Python files are parsed at all, so a `.py` path that previously cached
    #    nothing now yields real sites.
    # 4: gh#1 — a Python keyword-argument function binding is harvested as an extra
    #    site tagged 'binding', so a `.py` payload cached at 3 is missing those rows.
    # 5: #482 — a site now carries the receiver's trailing member name and the call's
    #    argument count, which is what lets a member call resolve to ONE method instead
    #    of none. A payload cached at 4 lacks both and would silently keep the old
    #    behaviour, so the bump is what makes the fix take effect on an existing index.
    stage_version = 5
    label = "tree-sitter"

    ## @brief Harvest one file's call sites.
    ## @return List of [callee_name, call_line] pairs.
    ## @version 1
    ## @req REQ-DDB-PIPE-003
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return _ast_harvest_calls(tree, src_bytes)


## @brief Layer 3's per-file harvester.
## @return A Harvester whose cache key this stage will look for.
## @version 1
## @req REQ-DDB-PIPE-003
def call_site_harvester() -> Harvester:
    """Public factory for gh#358's shared parse pass. Only the PARSE is shared: the
    self-edge guard this layer runs after resolution still runs from inside the
    stage, so a build without tree-sitter structurally cannot prune.

    @brief Build this stage's harvester.
    @version 1
    """
    return _CallSiteHarvester()


## @brief Resolve one file's harvested call sites into call_edges rows.
## @version 3
## @dg_internal
def _fold_call_payload(
    payload: list[list[Any]],
    funcs_in_file: list[tuple[int, str, int, int]],
    name_to_rowids: dict[str, list[int]],
    edges_resolved: list[tuple[int, int, str]],
    edges_fuzzy: list[tuple[int, int, str]],
    definition_of: dict[int, str] | None = None,
    receiver_types: dict[str, set[str]] | None = None,
    scope_of: dict[int, str] | None = None,
    argc_of: dict[int, int] | None = None,
) -> None:
    """Map each harvested call line back to its enclosing function's rowid and
    the callee name to candidate rowids — the rowid-dependent half of Layer 3,
    always recomputed against the current build.

    Sites are `[name, line, source]`; a two-element site is tolerated so a
    payload cached by an older extraction still folds (as plain 'ast') instead
    of raising. The stage_version bump makes that path cold in practice.

    @brief Fold a cached call-site payload into call edges.
    @version 3
    """
    for site in payload:
        callee_name, call_line = site[0], site[1]
        source = site[2] if len(site) > 2 else SOURCE_AST
        ## Fourth element added for #75; absent in a payload cached by an older build.
        qualified = site[3] if len(site) > 3 else ""
        ## Fifth and sixth added for #482; absent in a payload cached before stage_version 5.
        receiver = site[4] if len(site) > 4 else ""
        argc = site[5] if len(site) > 5 else -1
        caller_rowid = _ast_caller_at_line(funcs_in_file, call_line)
        if caller_rowid is None:
            continue
        _ast_record_call_edge(
            caller_rowid,
            callee_name,
            name_to_rowids,
            edges_resolved,
            edges_fuzzy,
            source,
            qualified=qualified,
            definition_of=definition_of,
            receiver=receiver,
            argc=argc,
            receiver_types=receiver_types,
            scope_of=scope_of,
            argc_of=argc_of,
        )


## @brief Insert harvested AST edges, carrying each edge's own provenance.
## @param conn Open connection to the database being built.
## @param edges_resolved (caller, callee, source) triples with a single match.
## @param edges_fuzzy (caller, callee, source) triples with several matches.
## @return (resolved inserted, fuzzy inserted).
## @version 2
## @dg_internal
def _ast_insert_edges(
    conn: sqlite3.Connection,
    edges_resolved: list[tuple[int, int, str]],
    edges_fuzzy: list[tuple[int, int, str]],
) -> tuple[int, int]:
    """`source` now rides on each edge rather than being a literal, so an edge
    recovered by unwrapping a member/qualified/template callee is separable
    from one seen as a bare identifier — see SOURCE_AST_MEMBER.
    """
    inserted_resolved = conn.executemany(
        """
        INSERT OR IGNORE INTO call_edges
            (caller_rowid, callee_rowid, source, confidence)
        VALUES (?, ?, ?, 'resolved')
        """,
        edges_resolved,
    ).rowcount
    inserted_fuzzy = conn.executemany(
        """
        INSERT OR IGNORE INTO call_edges
            (caller_rowid, callee_rowid, source, confidence)
        VALUES (?, ?, ?, 'fuzzy')
        """,
        edges_fuzzy,
    ).rowcount
    return inserted_resolved, inserted_fuzzy


## @brief Layer 3: parse C/C++ source with tree-sitter to capture call edges.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root (for resolving indexed relative paths).
## @param cache Optional incremental index cache; None disables caching.
## @version 8
## @req REQ-DDB-PIPE-003
def import_ast_call_edges(
    db_path: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
) -> None:
    """Layer 3: parse C/C++ source with tree-sitter to capture call edges
    doxygen misses (static helpers, indirect callers via macros, calls
    inside nested/lambda scopes, and calls in source files that lack
    doxygen-formatted docstrings entirely).

    The per-file parse is cached by content sha (see `harvest`); the
    line→rowid and name→rowid resolution always reruns.

    Ends by running `prune_fabricated_self_edges` over Layers 1-3, which is
    placed here rather than in the pipeline driver because this is the only
    stage that holds the AST evidence the guard needs — and because a build
    without tree-sitter must NOT prune, which the shared early return below
    guarantees structurally instead of by remembering to check.

    @brief Populate call_edges from tree-sitter AST walk, then guard self-edges.
    @version 8
    """
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.info(
            "tree_sitter not available — skipping Layer 3 AND the self-edge guard "
            "(every self-edge is left in place, unverified; install tree-sitter + "
            "tree-sitter-c + tree-sitter-cpp + tree-sitter-python to enable)",
        )
        return

    conn = sqlite3.connect(str(db_path))
    name_to_rowids, file_funcs = _build_function_indexes(conn)
    ## THE RECEIVER-TYPE MAPS (#482). Built once per build, from rows doxygen already
    ## wrote: `memberdef.type` for member variables, and `scope` plus parameter count for
    ## the functions a call might land on. Nothing is inferred — the receiver's class is a
    ## declared fact that this layer previously did not read.
    receiver_types = _receiver_types(conn)
    ## Both maps are only meaningful when `receiver_types` found anything, and both read
    ## columns a minimal fixture may not have — so they are skipped together rather than each
    ## carrying its own guard.
    scope_of: dict[int, str] = {}
    argc_of: dict[int, int] = {}
    if receiver_types:
        scope_of = {
            int(r): str(sc or "")
            for r, sc in conn.execute("SELECT rowid, scope FROM memberdef WHERE kind = 'function'")
        }
        if _table_exists(conn, "memberdef_param"):
            argc_of = {
                int(r): int(n)
                for r, n in conn.execute(
                    "SELECT memberdef_id, COUNT(*) FROM memberdef_param GROUP BY memberdef_id"
                )
            }
    harvested = run_harvest(conn, repo_root, call_site_harvester(), ts_classes, cache)

    edges_resolved: list[tuple[int, int, str]] = []
    edges_fuzzy: list[tuple[int, int, str]] = []
    definition_of = _definition_index(conn)
    for path_rowid, payload in harvested:
        funcs_in_file = file_funcs.get(path_rowid, [])
        if funcs_in_file:
            _fold_call_payload(
                payload,
                funcs_in_file,
                name_to_rowids,
                edges_resolved,
                edges_fuzzy,
                definition_of,
                receiver_types=receiver_types,
                scope_of=scope_of,
                argc_of=argc_of,
            )

    inserted_resolved, inserted_fuzzy = _ast_insert_edges(
        conn,
        edges_resolved,
        edges_fuzzy,
    )
    prune_fabricated_self_edges(conn, repo_root, ts_classes, file_funcs)
    conn.commit()
    conn.close()
    logger.info(
        "call_edges: harvested %d files, added %d resolved + "
        "%d fuzzy edges from tree-sitter (of %d resolved-raw + %d fuzzy-raw)",
        len(harvested),
        inserted_resolved,
        inserted_fuzzy,
        len(edges_resolved),
        len(edges_fuzzy),
    )


# ─── Self-edge guard: genuine recursion vs fabricated self-loop ─────────────
#
# A row with caller_rowid == callee_rowid is NOT automatically noise, and the
# discriminator is NOT name-uniqueness. Measured on two real indexes:
#
#   clew (70 self rows / 37 callers)
#   ------------------------------------  ---------------------------------
#   genuine recursion       10 rows        genuine recursion         6 rows
#   `obj.name()` on ANOTHER 27 rows        anonymous-namespace     442 rows
#     object                                 doxygen artifact
#   `super().__init__()`    12 rows        `::close()` / `::open()`  10 rows
#   `__main__`-guard        21 rows          shadowing a member of
#     mis-scoping                            the same name
#
# `close`/`commit` are UNIQUE names and fabricated; `_classify` is unique and
# genuine — so uniqueness decides nothing. The CALL SHAPE does:
#
#   bare        `name(...)`        in name's body  ->  recursion, KEEP
#                                                       EXCEPT in a Python
#                                                       METHOD — see gh#30
#   self-rooted `this->name(...)`  in name's body  ->  recursion, KEEP
#               `self.name(...)`                       (the ONLY way a Python
#                                                        method recurses)
#   anything else, or NO same-named call site at all ->  fabricated, DROP
#
# gh#30 — THE BARE RULE IS LANGUAGE-CONDITIONAL, and only for methods. C++ has an
# implicit `this`, so a bare `compact(n - 1)` inside `Buffer::compact` really is
# recursion. Python has none: a bare `cull(registry)` inside a method named `cull`
# resolves to a module-level or imported `cull` and CANNOT reach the method. The
# measured instance is `DocsDbServer.cull`, whose body calls the `cull` it imports
# from `state`; it was the eighth of eight names this guard reported as genuine
# recursion, and the only fabricated one of the eight.
#
# The condition is (Python AND the enclosing function is a method), evaluated PER
# CALL SITE. Not per file: a module-level `descend(child)` is still recursion, so
# keying on the language alone would delete every recursive free function in every
# Python codebase. Not per function either: a method may make both a bare call and
# a real `self.name(...)` call, and the second still proves recursion.
#
# The two dominant fabrication mechanisms are pure doxygen artifacts —
# `warn_failure` in an anonymous namespace and `main()` invoked from a
# `if __name__ == "__main__":` guard both get a self `xrefs` row with
# context='inline' although neither function names itself anywhere — so the fix
# cannot live in the AST extractor. It has to be a post-pass that judges the
# doxygen-derived layers against AST evidence.

## The layers this guard has jurisdiction over: every layer that resolves a
## callee BY NAME from an observed call site. Their self-edge asserts "a call
## site inside F names F", which is exactly what a call-shape check can falsify.
## `fnptr` and `declared_dispatch` are DELIBERATELY absent: they assert an
## INDIRECTION (a stored function pointer, an author-declared virtual seam) that
## no call site names, so there is no shape to check and dropping them would be
## dropping on absence of evidence that could never exist. Neither produced a
## single self-edge on either codebase, so the exclusion costs nothing
## measured — it is a statement about jurisdiction, not a carve-out.
GUARDED_SELF_EDGE_SOURCES: tuple[str, ...] = (
    CALL_SOURCE_DOXYGEN_SQLITE,
    CALL_SOURCE_AST,
    CALL_SOURCE_AST_MEMBER,
)

## Receiver expressions that denote the object whose method is executing, so a
## call through them reaches the SAME function. `self`/`cls` come from
## `pyast.SELF_NAMES` rather than being respelled — one definition, so the
## Python dialect and this guard cannot drift apart.
_SELF_RECEIVERS: tuple[str, ...] = ("this", "*this", "(*this)", *SELF_NAMES)

## Both grammars' call node. The C/C++ walkers and the Python walker are kept
## apart elsewhere because their node NAMES differ throughout; here the only
## divergence is two table entries, so one walk serves both.
_CALL_NODES = ("call_expression", "call")
## Callee node type -> (receiver field, tail field). `field_expression` is
## C/C++'s `a->m()` / `a.m()`; `attribute` is Python's `a.m`.
_RECEIVER_FIELDS = {
    "field_expression": ("argument", "field"),
    "attribute": ("object", "attribute"),
}

## Python's class-body node, and the node Python's own grammar uses for a function.
## Their spelling is what makes gh#30's rule language-conditional WITHOUT a language
## parameter: tree-sitter-cpp spells a class `class_specifier` and never emits
## `class_definition`, so this walk cannot fire on C or C++ and the bare-name rule
## there is untouched by construction rather than by a flag someone must pass
## correctly. Verified against both grammars by `test_bare_call_in_a_cpp_method_is_kept`.
_PY_CLASS_NODE = "class_definition"
_PY_FUNCTION_NODE = "function_definition"
## Nodes Python interposes between a definition and the scope that owns it. A
## decorated method is `class_definition > block > decorated_definition >
## function_definition`, so both must be stepped over or every `@property` and
## `@staticmethod` would read as module-level and gh#30's rule would miss it.
_PY_SCOPE_SKIPS = ("block", "decorated_definition")


## @brief True when a node sits inside the body of a Python METHOD.
## @param node Any node, typically a `call` whose callee is a bare identifier.
## @return True if the nearest enclosing function is owned by a class definition.
## @version 1
## @dg_internal
def _inside_python_method(node: Any) -> bool:
    """gh#30's discriminator. Finds the NEAREST enclosing `function_definition` and
    asks whether a `class_definition` owns it, which keeps the two over-reach cases
    apart: a nested closure's parent is another `function_definition`, so a bare
    recursive call inside it is still recursion, and a module-level function has no
    owning class at all.

    Returns False for every C and C++ tree, since neither grammar emits
    `class_definition` — the language condition is the node spelling itself.

    @brief Report whether a bare call here could reach the enclosing function.
    @return True when the enclosing function is a Python method.
    @version 1
    """
    fn = node.parent
    while fn is not None and fn.type not in (_PY_FUNCTION_NODE, _PY_CLASS_NODE):
        fn = fn.parent
    if fn is None:
        return False
    if fn.type == _PY_CLASS_NODE:
        return True
    scope = fn.parent
    while scope is not None and scope.type in _PY_SCOPE_SKIPS:
        scope = scope.parent
    return scope is not None and scope.type == _PY_CLASS_NODE


## @brief The callee name of a call that is unambiguously directed at itself.
## @param node A `call_expression` (C/C++) or `call` (Python) node.
## @param src_bytes The file's raw bytes.
## @return The callee's name when the call is bare or self-rooted, else None.
## @version 3
## @dg_internal
def _self_directed_callee(node: Any, src_bytes: bytes) -> str | None:
    """Refuses every qualified form that is NOT rooted at the running object,
    including `A::m()` and `::close()`. `::close()` inside a member named
    `close` is the motivating case: the global-scope operator makes it a call
    to POSIX `close`, and accepting a qualified shape would have kept all ten of
    those rows as "recursion".

    The bare-identifier branch is refused inside a Python method (gh#30): with no
    implicit `this`, `cull(...)` in a method named `cull` names something else
    entirely, so accepting it fabricated recursion for `DocsDbServer.cull`.

    @brief Name a call's callee when the call targets the enclosing object.
    @return Callee name, or None when the shape is not self-directed.
    @version 3
    """
    callee = node.child_by_field_name("function")
    if callee is None:
        return None
    if callee.type == "identifier":
        return None if _inside_python_method(node) else node_text(callee, src_bytes)
    return _self_rooted_name(callee, src_bytes)


## @brief The tail name of a member call whose receiver is `this`/`self`/`cls`.
## @param callee The call's `function` child.
## @param src_bytes The file's raw bytes.
## @return The tail name, or None when the receiver is another object.
## @version 1
## @dg_internal
def _self_rooted_name(callee: Any, src_bytes: bytes) -> str | None:
    """The receiver is compared as EXACT text, so `self.conn.close()` — whose
    receiver is `self.conn`, a different object — is refused while
    `self.close()` is accepted. That one comparison is what separates the two
    largest classes in the measurement above.

    @brief Read a self-rooted member call's tail name.
    @return Tail name, or None.
    @version 1
    """
    spec = _RECEIVER_FIELDS.get(callee.type)
    if spec is None:
        return None
    receiver = callee.child_by_field_name(spec[0])
    tail = callee.child_by_field_name(spec[1])
    if receiver is None or tail is None or node_text(receiver, src_bytes) not in _SELF_RECEIVERS:
        return None
    return node_text(tail, src_bytes)


## @brief Every self-directed call site in one parsed file.
## @param tree The file's tree-sitter tree (C, C++, Rust or Python).
## @param src_bytes The file's raw bytes.
## @return (callee name, 1-based line) for each bare or self-rooted call.
## @version 2
## @dg_internal
def _self_directed_sites(tree: Any, src_bytes: bytes) -> list[tuple[str, int]]:
    """@brief Collect a file's bare and self-rooted call sites.

    @return List of (name, line).
    @version 2
    """
    sites: list[tuple[str, int]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type not in _CALL_NODES:
            continue
        name = _self_directed_callee(node, src_bytes)
        if name is not None:
            sites.append((name, node.start_point[0] + 1))
    return sites


## @brief Every function carrying a self-edge in a guarded layer.
## @param conn Open connection to the database being built.
## @return (rowid, name, body file rowid) per distinct self-edge caller.
## @version 2
## @dg_internal
def _self_edge_callers(conn: sqlite3.Connection) -> list[tuple[int, str, int]]:
    """Keyed on `bodyfile_id` (falling back to `file_id`) to match
    `_build_function_indexes`, so a function declared in one file and defined in
    another is looked for in the file its BODY lives in.

    @brief List the callers of every guarded self-edge.
    @return Distinct (rowid, name, file rowid) triples.
    @version 2
    """
    placeholders = ", ".join("?" for _ in GUARDED_SELF_EDGE_SOURCES)
    return conn.execute(
        "SELECT DISTINCT m.rowid, m.name, COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        "FROM call_edges e JOIN memberdef m ON m.rowid = e.caller_rowid "
        "WHERE e.caller_rowid = e.callee_rowid "
        f"AND e.source IN ({placeholders})",
        GUARDED_SELF_EDGE_SOURCES,
    ).fetchall()


## @brief Split one file's self-edge callers into proved-recursive and unverifiable.
## @param parsed (tree, src_bytes) for the file.
## @param funcs_in_file The file's (rowid, name, bodystart, bodyend) ranges.
## @param members This file's self-edge callers as (rowid, name).
## @return (rowids proved recursive, rowids with no usable body range).
## @version 1
## @dg_internal
def _file_self_edge_verdicts(
    parsed: tuple[Any, bytes],
    funcs_in_file: list[tuple[int, str, int, int]],
    members: list[tuple[int, str]],
) -> tuple[set[int], set[int]]:
    """A caller with no entry in `funcs_in_file` has no body range recorded
    (doxygen gives a declaration-only row no usable one), so there is nowhere to
    look for its call sites — that is UNVERIFIABLE, not fabricated, and the
    difference is the whole fail-closed contract: a claim about the DETECTOR
    must never be reported as a claim about the code.

    Attribution uses `_ast_caller_at_line`, the SAME line->rowid mapping Layer 3
    uses to build its edges, so the evidence is consistent with the edges it
    judges rather than being a second, differently-wrong opinion.

    @brief Judge one file's self-edge callers against its call shapes.
    @return (proved, unverifiable).
    @version 1
    """
    with_ranges = {rowid for rowid, _n, _bs, _be in funcs_in_file}
    unverifiable = {rowid for rowid, _name in members if rowid not in with_ranges}
    names = dict(members)
    proved: set[int] = set()
    for name, line in _self_directed_sites(parsed[0], parsed[1]):
        rowid = _ast_caller_at_line(funcs_in_file, line)
        if rowid is not None and names.get(rowid) == name:
            proved.add(rowid)
    return proved, unverifiable


## @brief Gather self-call evidence for every self-edge caller, file by file.
## @param conn Open connection to the database being built.
## @param repo_root Repository root, for resolving indexed paths.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param file_funcs bodyfile_id -> function ranges, from _build_function_indexes.
## @param by_file file rowid -> that file's self-edge callers.
## @return (rowids proved recursive, rowids that could not be checked).
## @version 3
## @dg_internal
def _gather_self_call_evidence(
    conn: sqlite3.Connection,
    repo_root: Path,
    ts_classes: tuple[Any, Any],
    file_funcs: dict[int, list[tuple[int, str, int, int]]],
    by_file: dict[int, list[tuple[int, str]]],
) -> tuple[set[int], set[int]]:
    """Re-parses ONLY the files that own a self-edge (37 of clew's 81, 106 of
    a large one's) rather than widening the cached `ast_calls` payload with a per-site
    flag. Two reasons: the payload is shared by a stage whose cache key is a
    content sha, so growing it would invalidate every file's cached extraction
    on every repo for a question that concerns well under 1% of call sites; and
    a receiver is needed here that no other consumer of that payload wants.

    @brief Parse the self-edge files and collect recursion evidence.
    @return (proved, unverifiable).
    @version 3
    """
    language_cls, parser_cls = ts_classes
    parser_cache: dict = {}
    paths = dict(conn.execute("SELECT rowid, name FROM path").fetchall())
    proved: set[int] = set()
    unverifiable: set[int] = set()
    for file_id, members in by_file.items():
        rel_path = paths.get(file_id)
        parsed = (
            _ast_parse_one_file(
                rel_path, repo_root / rel_path, parser_cache, parser_cls, language_cls
            )
            if rel_path
            else None
        )
        if parsed is None:
            unverifiable.update(rowid for rowid, _name in members)
            continue
        hit, missing = _file_self_edge_verdicts(parsed, file_funcs.get(file_id, []), members)
        proved.update(hit)
        unverifiable.update(missing)
    return proved, unverifiable


## @brief Delete the guarded self-edge rows of the given callers.
## @param conn Open connection to the database being built.
## @param rowids Callers whose self-edges were judged fabricated.
## @return Number of `call_edges` rows actually deleted.
## @version 2
## @dg_internal
def _delete_self_edges(conn: sqlite3.Connection, rowids: list[int]) -> int:
    """Counted from `total_changes` rather than `cursor.rowcount`, which is
    documented per-statement and is not a reliable aggregate across an
    `executemany`. Rows are deleted one caller at a time so the statement never
    approaches SQLite's bound-variable ceiling on a repo with thousands of them.

    @brief Remove fabricated self-edges and report how many rows went.
    @version 2
    """
    placeholders = ", ".join("?" for _ in GUARDED_SELF_EDGE_SOURCES)
    before = conn.total_changes
    conn.executemany(
        "DELETE FROM call_edges WHERE caller_rowid = ? AND callee_rowid = ? "
        f"AND source IN ({placeholders})",
        [(rowid, rowid, *GUARDED_SELF_EDGE_SOURCES) for rowid in rowids],
    )
    return conn.total_changes - before


## @brief Render self-edge callers as `name#rowid`, sorted, for a log line.
## @param names rowid -> function name for every self-edge caller.
## @param rowids The subset to render.
## @return Comma-joined `name#rowid` tokens, or "none" when the subset is empty.
## @version 1
## @dg_internal
def _self_edge_labels(names: dict[int, str], rowids: Iterable[int]) -> str:
    """gh#30. A BARE name in this log is ambiguous exactly where the guard is most
    likely to be doubted: three unrelated `_classify` functions exist in this repo,
    so `KEPT ... _classify` named a symbol the reader could not locate and was read
    as evidence for gh#26 — a DIFFERENT defect in a different layer — costing real
    investigation time. The rowid is the identity the guard actually judged, and it
    is what makes the claim checkable against `memberdef`.

    Sorted by (name, rowid) so two same-named callers appear adjacent rather than
    scattered, which is the case the bare name hid.

    @brief Label self-edge callers unambiguously for the verdict log.
    @return Comma-joined `name#rowid` tokens.
    @version 1
    """
    return (
        ", ".join(f"{names[r]}#{r}" for r in sorted(rowids, key=lambda r: (names[r], r))) or "none"
    )


## @brief Report what the self-edge guard kept, dropped and could not judge.
## @param names rowid -> function name for every self-edge caller.
## @param proved Callers with a genuine self-call in their own body.
## @param unverifiable Callers whose body could not be read.
## @param doomed Callers whose self-edges were deleted.
## @param deleted Number of rows deleted.
## @version 3
## @dg_internal
def _log_self_edge_verdict(
    names: dict[int, str],
    proved: set[int],
    unverifiable: set[int],
    doomed: list[int],
    deleted: int,
) -> None:
    """The dropped COUNT is at INFO because a silent truncation reads as
    "covered everything"; the full dropped NAME list is at DEBUG, untruncated,
    because on a large codebase it runs to hundreds of names and would drown the INFO
    stream. Kept and unverifiable names stay at INFO — both are small, and both
    are exactly what a reader needs to challenge the guard.

    Every caller is named `name#rowid` rather than by bare name — see
    `_self_edge_labels` for the incident that rule comes from.

    @brief Log the guard's verdict, counts at INFO and full drops at DEBUG.
    @version 3
    """
    logger.info(
        "call_edges: self-edge guard over layers %s — %d callers examined; "
        "KEPT %d as genuine recursion (%s); DROPPED %d as fabricated (%d rows deleted); "
        "left %d UNVERIFIABLE, body unreadable (%s)",
        ", ".join(GUARDED_SELF_EDGE_SOURCES),
        len(names),
        len(proved),
        _self_edge_labels(names, proved),
        len(doomed),
        deleted,
        len(unverifiable),
        _self_edge_labels(names, unverifiable),
    )
    if doomed:
        logger.debug(
            "call_edges: self-edge guard dropped these callers in full: %s",
            _self_edge_labels(names, doomed),
        )


## @brief Drop self-edges that no self-directed call site in the caller supports.
## @param conn Open connection to the database being built (not committed here).
## @param repo_root Repository root, for resolving indexed paths.
## @param ts_classes (Language, Parser) from tree_sitter.
## @param file_funcs bodyfile_id -> function ranges, from _build_function_indexes.
## @version 1
## @req REQ-DDB-PIPE-003
def prune_fabricated_self_edges(
    conn: sqlite3.Connection,
    repo_root: Path,
    ts_classes: tuple[Any, Any],
    file_funcs: dict[int, list[tuple[int, str, int, int]]],
) -> None:
    """The self-edge guard. A `caller_rowid == callee_rowid` row survives only
    when the caller's own body contains a BARE or SELF-ROOTED call naming it;
    every other self-edge in a name-resolving layer is deleted. See the block
    comment above `GUARDED_SELF_EDGE_SOURCES` for the measured mechanisms and
    why the shape, not name-uniqueness, is the discriminator.

    Runs at the end of Layer 3 because that is the first moment every layer in
    its jurisdiction has run AND the AST evidence exists in the same process. It
    therefore also runs BEFORE Layer 6, which reads `call_edges` to synthesize
    declared-dispatch edges and would otherwise propagate a fabricated self-loop
    into edges that carry an author's name.

    Fail-closed in BOTH directions: a caller whose file will not parse, or that
    has no recorded body range, is reported as UNVERIFIABLE and its edges are
    LEFT ALONE — an unreadable body is a fact about this detector, not about the
    code. Correspondingly, if tree_sitter is unavailable the guard never runs at
    all (`import_ast_call_edges` returns first) and says so.

    @brief Delete self-edges unsupported by a self-directed call site.
    @version 1
    """
    callers = _self_edge_callers(conn)
    if not callers:
        logger.info("call_edges: self-edge guard — no self-edges in the guarded layers")
        return
    by_file: dict[int, list[tuple[int, str]]] = {}
    for rowid, name, file_id in callers:
        by_file.setdefault(file_id, []).append((rowid, name))
    proved, unverifiable = _gather_self_call_evidence(
        conn, repo_root, ts_classes, file_funcs, by_file
    )
    doomed = [r for r, _n, _f in callers if r not in proved and r not in unverifiable]
    deleted = _delete_self_edges(conn, doomed)
    _log_self_edge_verdict({r: n for r, n, _f in callers}, proved, unverifiable, doomed, deleted)


## @brief rowid → doxygen `definition` signature, for #75's qualifier narrowing.
## @param conn Open connection to the database being built.
## @return Mapping of function rowid to its signature; {} when the column is absent.
## @version 1
## @dg_internal
def _definition_index(conn: sqlite3.Connection) -> dict[int, str]:
    """Built ONCE per build rather than queried per call site — a qualified narrowing
    happens thousands of times and each one only needs a dict lookup.

    DEGRADES TO {} when `memberdef` has no `definition` column, and that is not a
    hypothetical: several test fixtures hand-build a minimal `memberdef` with just the
    columns their assertion needs, and a bare `SELECT definition` turned one of them into
    an `OperationalError` from a layer it was not testing. An empty map means
    `_narrow_by_qualifier` cannot narrow, so every candidate survives and the normal
    fan-out applies — the pre-#75 behaviour, which is the right thing to fall back to.

    Same graceful-degradation contract `query._common.has_columns` gives a stale database,
    applied on the write side.

    @brief Build the rowid→signature map, tolerating a schema without `definition`.
    @return {rowid: signature}, or {} when unavailable.
    @version 1
    """
    present = {r[0] for r in conn.execute("SELECT name FROM pragma_table_info('memberdef')")}
    if "definition" not in present:
        return {}
    return {
        rowid: (definition or "")
        for rowid, definition in conn.execute(
            "SELECT rowid, definition FROM memberdef WHERE kind = 'function'"
        )
    }
