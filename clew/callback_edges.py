# SPDX-License-Identifier: MIT
"""Layer 4: resolve callback-registration function-pointer calls into
real `call_edges` rows.

Confirmed real pattern, observed in a C/POSIX firmware repo whose generated
data-model layer (`gen/model/model.c`) is wired to a platform layer in a vendored
submodule. Symbol names and paths below are the real SHAPE with illustrative names:

    DataModel_Event_Callback dm_event_callback = NULL;   // a global

    void DataModel_Initialize(DataModel_Event_Callback event_callback) {
        dm_event_callback = event_callback;              // REGISTRATION
        ...
    }

    // elsewhere, inside a generated per-key setter:
    if (value_changed) {
        dm_event_callback(key);                          // INDIRECT CALL
    }

Existing call_edges layers (doxygen, XML, AST) only resolve DIRECT calls
by literal callee name — `dm_event_callback` is a variable, not a
function, so `dm_event_callback(key)` resolves to zero candidates under
every existing layer even when the generated source is fully indexed.
This module closes exactly that gap with a small, generic (no
target-repo-specific names) two-step resolution:

  1. REGISTRATION detection: inside any function F, an assignment
     `GLOBAL = PARAM;` where PARAM is one of F's OWN parameters (a
     plain-identifier match, no type information needed).
  2. BINDING resolution: at every call site of F, look at the argument
     passed for PARAM's position. If it's a literal identifier naming an
     already-indexed function, GLOBAL is now known to be bound to that
     function. If instead the argument is itself a parameter of the
     CALLING function (pure pass-through, the confirmed real shape:
     `System_Initialize`'s own `dmEventHandler` param forwarded
     into `DataModel_Initialize(dmEventHandler)`), resolution recurses
     into the caller's own call sites — unbounded depth, guarded by a
     visited (function, param) set so mutual/self recursion terminates.
     Anything else (a literal NULL, a struct member, a computed
     expression) is left unresolved at that call site — fail-closed,
     never guessed.

Once GLOBAL is bound to one or more concrete functions, every call site
`GLOBAL(...)` anywhere becomes a `call_edges` row: caller = the enclosing
function of that call, callee = the resolved function, source='fnptr'.
Reuses `_ast_record_call_edge`'s existing resolved/fuzzy tiering (a
resolved name with exactly one candidate rowid is 'resolved'; multiple
same-named candidates are 'fuzzy', matching Layer 3's own convention).

Runs unconditionally as part of the standard pipeline (no CLI flag) —
the pattern is purely structural, not repo-specific, so there is nothing
to configure. Graceful no-op when tree_sitter isn't installed, mirroring
Layer 3.

R1: the previously-discarded unresolved-external case (a registration whose
binding forwards a parameter out of repo and dead-ends) is now recorded in an
`external_boundaries` terminus table instead of being silently dropped.

gh#1 — A THIRD binding shape, alongside the two-step registration above: the
global is bound DIRECTLY to a named function, needing no argument resolution
at all.

    int (*mbedtls_mutex_lock)(mbedtls_threading_mutex_t *) = threading_mutex_lock_pthread;

Both spellings were blind spots, for different reasons. At FILE SCOPE this is a
`declaration`/`init_declarator`, and the harvest only ever looked for an
`assignment_expression`, so no row existed; written in a function
(`mutex_lock = impl;`) the row WAS harvested and the fold then dropped it,
because it kept only a row whose RHS named one of the enclosing function's
PARAMETERS. That discard is why this repo's own build log read
`callback_edges: resolved 0 registrations`.

A direct binding is confirmed by `_is_known_function` at EMISSION time rather
than at fold time — every file's signatures are collected by then, so a binding
whose target lives in another file resolves. Confirming is also what keeps an
ordinary `int x = y;` harmless, since the harvest is deliberately type-blind.

gh#35 — BRANCH SELECTION. A global bound in two mutually exclusive `#if` branches
USED TO yield an edge to EACH target, both graded 'resolved'. They are alternatives,
not a conjunction, and one of Mbed-TLS's two is a failure stub:

    #if defined(MBEDTLS_THREADING_PTHREAD)
    int (*mbedtls_mutex_lock)(...) = threading_mutex_lock_pthread;
    #endif
    #if defined(MBEDTLS_THREADING_ALT)
    int (*mbedtls_mutex_lock)(...) = threading_mutex_fail;
    #endif

The harvest now records each binding's enclosing preprocessor GUARD CHAIN, and
emission evaluates it against the configuration gh#17 resolves. Three outcomes:

  branch LIVE and certain    -> 'resolved', as before
  branch DEAD                -> no edge at all
  branch UNDECIDABLE         -> 'fuzzy', even when the name resolves uniquely

Undecidable covers both "the target declared no configuration" and "the guard is an
expression the evaluator cannot read" (`#if _POSIX_VERSION >= 200809L`). It is
never read as dead: `defined(X)` against an empty macro set is legitimately False,
and treating that as a dead branch would empty this layer for every repository that
declares no configuration, which is most of them.

Measured on Mbed-TLS v3.6.7 over 1,277 conditional bindings, 37 call sites through
`mbedtls_mutex_lock`:

  before                     151 resolved,   0 fuzzy — `threading_mutex_fail` AND
                                                       `..._lock_pthread` both 'resolved'
  after, nothing declared      0 resolved, 151 fuzzy — both alternatives, neither claimed
  after, PTHREAD declared     93 resolved,   0 fuzzy — `threading_mutex_fail` ABSENT

A FOURTH CASE, and the one a real declaration reaches: the configuration names
NEITHER alternative. gh#17 harvests Mbed-TLS's PREDEFINED from its own
`include/mbedtls/mbedtls_config.h`, which ships `MBEDTLS_THREADING_C` COMMENTED
OUT — so neither `MBEDTLS_THREADING_PTHREAD` nor `MBEDTLS_THREADING_ALT` is
declared, all 8 bindings of the four `mbedtls_mutex_*` pointers graded dead, and:

  142-macro config header      0 resolved,   0 fuzzy — the layer, entire, deleted

That is not selection, it is erasure, and it contradicted the same build's other
half: gh#11 had recovered `threading_mutex_lock_pthread` from the source text
BECAUSE the preprocessor skipped it, so one index said "this code exists, reason
about it" and "nothing reaches it" about the same `#if`. 38 of the deleted rows
were that function's callers.

So SELECTION NEVER ELIMINATES A GLOBAL ENTIRELY. When every alternative of one
global grades dead, all of them are restored at 'fuzzy'
(`_branch_eliminated_bindings`). Dropping a loser and dropping the last one are
different claims: the first says which implementation is live, the second asserts
the global is unbound in an index that still holds every implementation. The three
measurements above are unchanged — each has a live alternative.

The alternatives-vs-conjunction distinction is carried by CONFIDENCE, not by a new
column. Declared, the question dissolves — only the live edge exists. Undeclared,
'fuzzy' already means "may be wrong" to every consumer AND is skipped by both
`mark_reachability` and the thread BFS, which is the traversal semantics wanted. A
new `alt_group` column would have to reach `query/` and the MCP payload to be usable,
and an unread column is a promise a consumer cannot cash — gh#37 is that exact defect.

REGISTRATIONS are deliberately exempt. Their target comes from the registering
function's call sites, not from the branch they were written in, and
`mbedtls_threading_set_alt` is itself inside `#if defined(MBEDTLS_THREADING_ALT)` —
honouring its guard would delete the registration path whenever pthread is declared.

@brief Callback-registration call-edge resolver (Layer 4, source='fnptr').
@version 6
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .call_edges import (
    SOURCE_FNPTR,
    _ast_caller_at_line,
    _ast_record_call_edge,
    _build_function_indexes,
)
from .harvest import Harvester, run_harvest, try_import_tree_sitter
from .indexcache import IndexCache
from .preprocessor import PreprocessorConfig, evaluate_condition
from .pyast import node_text
from .vocabulary import STAGE_FNPTR, check


## @brief One function's resolved name + ordered parameter names.
## @version 1
class _FunctionSignature:
    """A function's name and ordered parameter names (None where a
    parameter's declarator isn't a plain identifier — best-effort, never
    guessed).

    @brief Function name + ordered parameter name list.
    @version 1
    """

    __slots__ = ("name", "param_names")

    ## @brief Store a function's name and ordered parameter-name list.
    ## @version 1
    ## @dg_internal
    def __init__(self, name: str, param_names: list[str | None]) -> None:
        self.name = name
        self.param_names = param_names


## @brief Mutable output collected while walking every file once.
## @version 2
class _CallbackCollector:
    """Accumulates function signatures, registrations, and call-site
    argument lists across every file in one pass, so resolution (which
    needs cross-file, cross-function data) runs once at the end rather
    than re-parsing per query.

    @brief Cross-file collector for callback-edge resolution.
    @version 2
    """

    __slots__ = ("call_sites", "direct_bindings", "registrations", "signatures")

    ## @brief Initialize empty signature, registration, and call-site maps.
    ## @version 3
    ## @dg_internal
    def __init__(self) -> None:
        self.signatures: dict[int, _FunctionSignature] = {}
        # global_name -> list of (registering_func_rowid, param_index)
        self.registrations: dict[str, list[tuple[int, int]]] = {}
        ## global_name -> candidate function names bound DIRECTLY by
        ## `GLOBAL = some_function;` (gh#1), each with the preprocessor GUARD CHAIN it
        ## was written under (gh#35). Kept apart from `registrations` because these need
        ## no call-site argument resolution at all: the binding already names its target.
        ## Filtered against the collected signatures at emission time, not here — a file
        ## folded early cannot yet know about a function defined in a file folded later.
        ##
        ## A LIST of (name, guards), not a `set[str]`: the same function may be bound in
        ## two branches, and two different functions bound in two branches is the whole of
        ## gh#35. A set keyed on the name alone erased the branch before anything could
        ## read it, which is why the defect was invisible at emission.
        self.direct_bindings: dict[str, list[tuple[str, tuple]]] = {}
        # callee_name -> list of (caller_rowid, ordered arg identifier
        # texts, None where an argument isn't a plain identifier)
        self.call_sites: dict[str, list[tuple[int, list[str | None]]]] = {}


## @brief Find the innermost function_declarator inside a possibly-wrapped declarator.
## @return The function_declarator node, or None if none is found by descending declarator wrappers.
## @version 1
## @dg_internal
def _find_function_declarator(declarator: Any) -> Any | None:
    """Return the `function_declarator` node, descending through a
    pointer return-type wrapper (`char *foo(...)`) if present.

    @brief Locate the function_declarator under a function_definition's declarator.
    @version 1
    """
    node = declarator
    while node is not None and node.type != "function_declarator":
        node = node.child_by_field_name("declarator")
    return node


## @brief Descend through wrapper declarators to the innermost identifier.
## @return The innermost identifier node, or None if the declarator chain dead-ends before one.
## @version 2
## @dg_internal
def _innermost_identifier(node: Any) -> Any | None:
    """Unwrap `function_declarator`/`pointer_declarator` (both expose a
    `declarator` field) and `parenthesized_declarator` (no field, just
    one named child) until a plain `identifier` is reached — the shape a
    RAW (non-typedef'd) function-pointer declarator produces, e.g.
    `void (*dmEventHandler)(uint32_t)` parses as `function_declarator ->
    parenthesized_declarator -> pointer_declarator -> identifier`.
    Confirmed live: this is the real registration-signature shape a generated
    data-model layer produces (`System_Initialize`'s own params), which a plain
    `declarator.type == "identifier"` check misses entirely.

    @brief Unwrap nested declarators to their innermost identifier.
    @version 1
    """
    while node is not None and node.type != "identifier":
        nxt = node.child_by_field_name("declarator")
        if nxt is None:
            named = node.named_children
            nxt = named[0] if named else None
        if nxt is None:
            return None
        node = nxt
    return node


## @brief Extract one parameter_declaration's declared name, if any.
## @return The decoded parameter name, or None for a bare-type/unnamed or unrecognized declarator.
## @version 2
## @dg_internal
def _param_name(param_node: Any, src_bytes: bytes) -> str | None:
    """Return the parameter's declared name — handling both a plain
    identifier declarator (`int x`, or any typedef'd type) and a raw
    function-pointer declarator (`void (*cb)(int)`) via
    `_innermost_identifier`. None for a bare-type param with no name at
    all (e.g. the lone `void` in a `(void)` parameter list, or an array/
    other unhandled shape) — best-effort, never guessed.

    @brief Resolve one parameter_declaration's name.
    @version 2
    """
    declarator = param_node.child_by_field_name("declarator")
    if declarator is None:
        return None
    ident = _innermost_identifier(declarator)
    if ident is None:
        return None
    return src_bytes[ident.start_byte : ident.end_byte].decode(
        "utf-8",
        errors="replace",
    )


## @brief Extract a function_definition's signature (name + param names).
## @return A (name, ordered param-name list) tuple, or None if the declarator shape isn't recognized.
## @version 1
## @dg_internal
def _function_signature(func_def: Any, src_bytes: bytes) -> tuple[str, list[str | None]] | None:
    """Return (name, ordered param names), or None if the declarator
    shape isn't recognized (best-effort).

    @brief Extract one function's name + parameter name list.
    @version 1
    """
    declarator = func_def.child_by_field_name("declarator")
    func_decl = _find_function_declarator(declarator)
    if func_decl is None:
        return None
    name_node = func_decl.child_by_field_name("declarator")
    if name_node is None or name_node.type != "identifier":
        return None
    name = src_bytes[name_node.start_byte : name_node.end_byte].decode(
        "utf-8",
        errors="replace",
    )
    params_node = func_decl.child_by_field_name("parameters")
    param_names = (
        [_param_name(p, src_bytes) for p in params_node.named_children]
        if params_node is not None
        else []
    )
    return name, param_names


## @brief Harvest one function_definition's body line + name + parameter names.
## @return [body_line, name, param_names], or None when the shape isn't recognized.
## @version 1
## @dg_internal
def _harvest_signature(func_def: Any, src_bytes: bytes) -> list[Any] | None:
    """Record the signature against its BODY START LINE — the same line the
    original rowid resolution used — so the fold can map it to a memberdef
    rowid on any later build.

    @brief Per-file signature harvest.
    @version 1
    """
    body = func_def.child_by_field_name("body")
    if body is None:
        return None
    sig = _function_signature(func_def, src_bytes)
    if sig is None:
        return None
    name, param_names = sig
    return [body.start_point[0] + 1, name, param_names]


## @brief Harvest one `identifier = identifier;` assignment as a candidate registration.
## @return [line, lhs_name, rhs_name], or None when either side isn't a bare identifier.
## @version 2
## @dg_internal
def _harvest_registration(assign_node: Any, src_bytes: bytes) -> list[Any] | None:
    """The RHS-is-a-parameter test needs the enclosing function's signature,
    which is rowid-resolved, so it moves to the fold; the harvest only records
    the plain-identifier assignments.

    @brief Per-file registration-candidate harvest.
    @version 2
    """
    left = assign_node.child_by_field_name("left")
    right = assign_node.child_by_field_name("right")
    if left is None or right is None:
        return None
    if left.type != "identifier" or right.type != "identifier":
        return None
    global_name = src_bytes[left.start_byte : left.end_byte].decode("utf-8", errors="replace")
    rhs_name = src_bytes[right.start_byte : right.end_byte].decode("utf-8", errors="replace")
    return [
        assign_node.start_point[0] + 1,
        global_name,
        rhs_name,
        _guard_chain(assign_node, src_bytes),
    ]


## @brief Harvest one `TYPE (*name)(...) = identifier;` initializer as a candidate binding.
## @param decl_node An `init_declarator` node.
## @param src_bytes The file's bytes, for slicing.
## @return [line, bound_name, rhs_name], or None when the shape isn't a name-to-name bind.
## @version 2
## @dg_internal
def _harvest_init_binding(decl_node: Any, src_bytes: bytes) -> list[Any] | None:
    """The FILE-SCOPE half of gh#1, and the shape Mbed-TLS uses:

        int (*mbedtls_mutex_lock)(mbedtls_threading_mutex_t *) = threading_mutex_lock_pthread;

    parses as `declaration -> init_declarator`, NOT as `assignment_expression`, so
    `_harvest_registration` never saw it and the binding produced no edge at all.
    The declarator side nests
    `function_declarator -> parenthesized_declarator -> pointer_declarator -> identifier`
    — exactly the chain `_innermost_identifier` already unwraps for a raw
    function-pointer PARAMETER, so the same helper serves both.

    Deliberately NOT restricted to function-pointer declarators: an ordinary
    `int x = y;` is harvested too. That is fail-closed rather than sloppy, because a
    row only ever becomes an edge when `y` resolves to an indexed function AND some
    call site invokes `x(...)`, which a scalar cannot satisfy. Type-matching here
    would need the typedef table and would buy nothing.

    @brief Per-file harvest of a declaration-with-initializer binding.
    @version 2
    """
    declarator = decl_node.child_by_field_name("declarator")
    value = decl_node.child_by_field_name("value")
    if declarator is None or value is None or value.type != "identifier":
        return None
    ident = _innermost_identifier(declarator)
    if ident is None:
        return None
    bound_name = src_bytes[ident.start_byte : ident.end_byte].decode("utf-8", errors="replace")
    rhs_name = src_bytes[value.start_byte : value.end_byte].decode("utf-8", errors="replace")
    return [decl_node.start_point[0] + 1, bound_name, rhs_name, _guard_chain(decl_node, src_bytes)]


# ─── gh#35: which preprocessor branch a binding sits in ─────────────────────
#
# Mbed-TLS `library/threading.c` binds ONE pointer twice, in two branches that cannot
# both exist:
#
#     #if defined(MBEDTLS_THREADING_PTHREAD)
#     int (*mbedtls_mutex_lock)(...) = threading_mutex_lock_pthread;   /* line 103 */
#     #endif
#     #if defined(MBEDTLS_THREADING_ALT)
#     int (*mbedtls_mutex_lock)(...) = threading_mutex_fail;           /* line 127 */
#     #endif
#
# Before this, every call site through `mbedtls_mutex_lock` got a 'resolved' edge to
# BOTH, one of which is a failure stub. They are alternatives; the graph asserted a
# conjunction, and `mark_reachability` and the thread BFS traverse 'resolved'.
#
# The harvest records each binding's enclosing guard CHAIN as text. It cannot evaluate
# it — a harvester returns JSON-serializable, rowid-free data and has no access to the
# declared configuration — so evaluation happens at emission, where the config is in
# hand. That split is also why the guard text is stored rather than a verdict: the same
# cached payload has to remain correct when the declared configuration CHANGES.
_GUARD_NODES = {"preproc_if": "condition", "preproc_elif": "condition"}
_IFDEF_NODE = "preproc_ifdef"
## A node in the `#else`/`#elif` arm is a DESCENDANT of that arm's node, which is in turn
## a child of the `#if` it negates — so the chain walk sees the arm first and flips the
## polarity of the guard it then reaches.
_NEGATING_ARMS = ("preproc_else", "preproc_elif")
## An `#elif` body additionally requires every PRECEDING condition to be false, which
## this model does not carry. Emitting an unevaluable token keeps it honestly UNKNOWN
## rather than being read as "the elif condition alone decides it".
_UNEVALUABLE = "#elif"


## @brief The chain of preprocessor guards enclosing a node, outermost last.
## @param node The AST node whose conditional context is wanted.
## @param src_bytes The file's raw bytes.
## @return List of [condition text, negated] pairs; empty when the node is unguarded.
## @version 1
## @dg_internal
def _guard_chain(node: Any, src_bytes: bytes) -> list[list[Any]]:
    """`#ifdef X` / `#ifndef X` are NORMALISED to `defined(X)` with a polarity, so the
    evaluator has one atom form to decide instead of three spellings of the same test.

    An EMPTY chain is the load-bearing value: it means the binding is unconditional, and
    those must keep grading exactly as they did before gh#35 — the change is about
    conditional bindings only, and an unconditional one that started grading down would
    be a regression dressed as a fix.

    @brief Collect a node's enclosing `#if`/`#ifdef` guards.
    @return Guard chain as [text, negated] pairs.
    @version 1
    """
    chain: list[list[Any]] = []
    negate_next = False
    cur = node.parent
    while cur is not None:
        if cur.type in _NEGATING_ARMS:
            if cur.type == "preproc_elif":
                chain.append([_UNEVALUABLE, False])
            negate_next = True
        elif cur.type in _GUARD_NODES or cur.type == _IFDEF_NODE:
            chain.append(_guard_of(cur, src_bytes, negate_next))
            negate_next = False
        cur = cur.parent
    return chain


## @brief One guard directive's condition text and polarity.
## @param node A `preproc_if`, `preproc_elif` or `preproc_ifdef` node.
## @param src_bytes The file's raw bytes.
## @param negated True when the node of interest sits in this guard's `#else` arm.
## @return [condition text, negated] for this directive.
## @version 1
## @dg_internal
def _guard_of(node: Any, src_bytes: bytes, negated: bool) -> list[Any]:
    """`#ifndef X` inverts on TOP of an `#else`, so the two polarities compose rather
    than one overwriting the other — a binding in the `#else` of an `#ifndef` is live
    when X IS defined.

    @brief Read a guard directive as a normalised condition plus polarity.
    @return [text, negated].
    @version 1
    """
    if node.type == _IFDEF_NODE:
        name_node = node.child_by_field_name("name")
        text = "" if name_node is None else f"defined({node_text(name_node, src_bytes)})"
        first = node_text(node.children[0], src_bytes) if node.children else ""
        return [text, negated != first.strip().endswith("ifndef")]
    cond = node.child_by_field_name(_GUARD_NODES[node.type])
    return [_UNEVALUABLE if cond is None else node_text(cond, src_bytes).strip(), negated]


## @brief Harvest one call_expression's callee name + argument identifiers.
## @return [line, callee_name, arg_texts], or None when the callee isn't an identifier.
## @version 1
## @dg_internal
def _harvest_call_site(call_node: Any, src_bytes: bytes) -> list[Any] | None:
    """Argument slots that aren't plain identifiers record as None — the raw
    material both registration resolution and final edge emission read from.

    @brief Per-file call-site harvest.
    @version 1
    """
    callee_node = call_node.child_by_field_name("function")
    if callee_node is None or callee_node.type != "identifier":
        return None
    callee_name = src_bytes[callee_node.start_byte : callee_node.end_byte].decode(
        "utf-8",
        errors="replace",
    )
    args_node = call_node.child_by_field_name("arguments")
    arg_texts: list[str | None] = []
    for arg in args_node.named_children if args_node is not None else []:
        if arg.type == "identifier":
            arg_texts.append(
                src_bytes[arg.start_byte : arg.end_byte].decode("utf-8", errors="replace"),
            )
        else:
            arg_texts.append(None)
    return [call_node.start_point[0] + 1, callee_name, arg_texts]


## @brief Route one AST node into the matching harvest bucket.
## @version 3
## @dg_internal
def _harvest_callback_node(node: Any, src_bytes: bytes, out: dict[str, list]) -> None:
    """Dispatch by node type — extracted from `_harvest_callback_file` to keep
    that function's complexity low.

    @brief Dispatch one node in the callback-edge harvest.
    @version 3
    """
    handlers = {
        "function_definition": ("sigs", _harvest_signature),
        "assignment_expression": ("regs", _harvest_registration),
        ## gh#1: a file-scope `int (*cb)(void) = impl;` is a `declaration`, not an
        ## assignment. Same `[line, bound_name, rhs_name, guards]` payload shape, so it
        ## shares the `regs` bucket and the cached-payload format does not change.
        "init_declarator": ("regs", _harvest_init_binding),
        "call_expression": ("calls", _harvest_call_site),
    }
    entry = handlers.get(node.type)
    if entry is None:
        return
    bucket, harvest_fn = entry
    record = harvest_fn(node, src_bytes)
    if record is not None:
        out[bucket].append(record)


## @brief Walk one parsed file's AST, harvesting signatures/registrations/call sites.
## @return {"sigs": [...], "regs": [...], "calls": [...]} in walk order.
## @version 3
## @dg_internal
def _harvest_callback_file(tree: Any, src_bytes: bytes) -> dict[str, list]:
    """Single stack-based walk collecting everything Layer 4 needs from one
    file, keyed by SOURCE LINE rather than memberdef rowid so the result is
    cacheable across builds.

    @brief Walk one file for callback-edge source material.
    @version 3
    """
    out: dict[str, list] = {"sigs": [], "regs": [], "calls": []}
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        _harvest_callback_node(node, src_bytes, out)
    return out


## @brief Layer 4's cacheable per-file harvester.
## @version 1
class _CallbackHarvester(Harvester):
    """Records signatures / registration candidates / call sites per file.

    @brief Layer 4 per-file harvester.
    @version 1
    """

    stage = STAGE_FNPTR
    # Bump when _harvest_callback_file's extraction changes.
    # 2: gh#1 — `init_declarator` bindings join the `regs` bucket, so a payload
    #    cached at 1 is missing every file-scope `TYPE (*cb)(...) = impl;`.
    # 3: gh#35 — a `regs` record gains a fourth element, its enclosing preprocessor
    #    GUARD CHAIN. A payload cached at 2 has no branch information at all, so every
    #    conditional binding in it would read as unconditional and keep grading
    #    'resolved' — the exact defect, served out of cache.
    stage_version = 3
    label = "callback edges"

    ## @brief Harvest one file's callback-edge source material.
    ## @return The per-file {"sigs","regs","calls"} payload.
    ## @version 1
    ## @req REQ-DDB-PIPE-003
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        return _harvest_callback_file(tree, src_bytes)


## @brief Layer 4's per-file harvester.
## @return A Harvester whose cache key this stage will look for.
## @version 1
## @req REQ-DDB-PIPE-003
def callback_harvester() -> Harvester:
    """Public factory for gh#358's shared parse pass. This stage's `extra_key` is
    empty ONLY because the harvest stores the raw preprocessor guard chain and the
    `PreprocessorConfig` is applied after it; the shared pass changes nothing about
    that, and branch selection must stay out of `harvest` or the empty key becomes a
    lie.

    @brief Build this stage's harvester.
    @version 1
    """
    return _CallbackHarvester()


## @brief Resolve one file's harvested signatures into the collector.
## @version 1
## @dg_internal
def _fold_signatures(
    payload: dict[str, list],
    funcs_in_file: list[tuple[int, str, int, int]],
    collector: _CallbackCollector,
) -> None:
    """@brief Map each harvested signature's body line to a memberdef rowid."""
    for body_line, name, param_names in payload["sigs"]:
        rowid = _ast_caller_at_line(funcs_in_file, body_line)
        if rowid is not None:
            collector.signatures[rowid] = _FunctionSignature(name, list(param_names))


## @brief Resolve one file's harvested registrations into the collector.
## @version 3
## @dg_internal
def _fold_registrations(
    payload: dict[str, list],
    funcs_in_file: list[tuple[int, str, int, int]],
    collector: _CallbackCollector,
) -> None:
    """Two dispositions per harvested `GLOBAL = RHS` row, and every row now lands in
    one of them — before gh#1 a row whose RHS was not a parameter was DROPPED, which
    is why this repo's build log read `callback_edges: resolved 0 registrations`:

      * RHS names one of the enclosing function's own PARAMETERS — a registration.
        The concrete target is unknown here and comes from the registering
        function's own call sites, so file (func_rowid, param_index).
      * RHS is anything else — a candidate DIRECT binding. The name is recorded
        verbatim and filtered against the collected signatures at emission time,
        because a function defined in a not-yet-folded file is not knowable now.

    A direct binding deliberately does NOT require an enclosing function: the
    Mbed-TLS shape binds at FILE SCOPE, where `_ast_caller_at_line` returns None.
    That is exactly the case the old `continue` discarded first.

    A REGISTRATION carries no guard chain even when it has one. Its target comes from the
    registering function's call sites, not from the branch it was written in, so the
    branch does not select between alternatives there — and `mbedtls_threading_set_alt`,
    the one real instance, is itself inside `#if defined(MBEDTLS_THREADING_ALT)`, so
    honouring the guard would delete the registration path entirely whenever the declared
    configuration is pthread. gh#35 is about DIRECT bindings.

    @brief Fold harvested registration and direct-binding candidates.
    @version 3
    """
    for line, global_name, rhs_name, guards in payload["regs"]:
        func_rowid = _ast_caller_at_line(funcs_in_file, line)
        sig = collector.signatures.get(func_rowid) if func_rowid is not None else None
        if sig is not None and rhs_name in sig.param_names:
            collector.registrations.setdefault(global_name, []).append(
                (func_rowid, sig.param_names.index(rhs_name)),
            )
            continue
        entry = (rhs_name, tuple(tuple(g) for g in guards))
        bindings = collector.direct_bindings.setdefault(global_name, [])
        if entry not in bindings:
            bindings.append(entry)


## @brief Fold one file's cached callback payload into the cross-file collector.
## @version 1
## @dg_internal
def _fold_callback_payload(
    payload: dict[str, list],
    funcs_in_file: list[tuple[int, str, int, int]],
    collector: _CallbackCollector,
) -> None:
    """Signatures resolve first (registrations read them), then registrations,
    then call sites — the same dependency order the single-pass walk enforced
    via ancestor-before-descendant traversal.

    @brief Fold one file's callback harvest.
    @version 1
    """
    _fold_signatures(payload, funcs_in_file, collector)
    _fold_registrations(payload, funcs_in_file, collector)
    for line, callee_name, arg_texts in payload["calls"]:
        caller_rowid = _ast_caller_at_line(funcs_in_file, line)
        if caller_rowid is not None:
            collector.call_sites.setdefault(callee_name, []).append(
                (caller_rowid, list(arg_texts)),
            )


## @brief Recursively resolve a (function, parameter) binding to concrete function names.
## @version 1
## @dg_internal
def _resolve_binding(
    func_name: str,
    param_index: int,
    collector: _CallbackCollector,
    rowid_to_name: dict[int, str],
    visited: set[tuple[str, int]],
) -> set[str]:
    """Resolve what concrete function(s) reach parameter `param_index`
    of `func_name` across all of its call sites — recursing through
    pure parameter-forwarding chains, `visited`-guarded against
    mutual/self recursion. Fail-closed: an argument that's neither a
    known function name nor a forwarded parameter contributes nothing.

    @brief Resolve a function-pointer parameter binding transitively.
    @version 1
    """
    if (func_name, param_index) in visited:
        return set()
    visited.add((func_name, param_index))
    resolved: set[str] = set()
    for caller_rowid, args in collector.call_sites.get(func_name, []):
        if param_index >= len(args):
            continue
        arg = args[param_index]
        if arg is None:
            continue
        resolved |= _resolve_one_call_site(
            caller_rowid,
            arg,
            collector,
            rowid_to_name,
            visited,
        )
    return resolved


## @brief Resolve one call site's contribution to a binding.
## @version 1
## @dg_internal
def _resolve_one_call_site(
    caller_rowid: int,
    arg: str,
    collector: _CallbackCollector,
    rowid_to_name: dict[int, str],
    visited: set[tuple[str, int]],
) -> set[str]:
    """A literal known function resolves directly; a forwarded parameter
    of the calling function recurses; anything else contributes nothing.

    @brief Resolve one call site's argument to a set of concrete functions.
    @version 1
    """
    if _is_known_function(arg, collector):
        return {arg}
    caller_sig = _caller_signature(caller_rowid, rowid_to_name, collector)
    if caller_sig is None or arg not in caller_sig.param_names:
        return set()
    return _resolve_binding(
        caller_sig.name,
        caller_sig.param_names.index(arg),
        collector,
        rowid_to_name,
        visited,
    )


## @brief True if `name` is a known indexed function (per collected signatures).
## @return True if `name` is non-None and matches a collected function signature, else False.
## @version 1
## @dg_internal
def _is_known_function(name: str | None, collector: _CallbackCollector) -> bool:
    """A name is "known" if some collected function signature uses it —
    cheaper than a DB round-trip, and sufficient since only indexed
    functions ever get a signature recorded.

    @brief Check whether a name matches a collected function signature.
    @version 1
    """
    return name is not None and any(sig.name == name for sig in collector.signatures.values())


## @brief Return the calling function's signature, if known.
## @version 1
## @dg_internal
def _caller_signature(
    caller_rowid: int,
    rowid_to_name: dict[int, str],
    collector: _CallbackCollector,
) -> _FunctionSignature | None:
    """@brief Look up a caller rowid's own collected signature."""
    caller_name = rowid_to_name.get(caller_rowid)
    if caller_name is None:
        return None
    return next(
        (s for s in collector.signatures.values() if s.name == caller_name),
        None,
    )


## @brief One recorded external-boundary (terminus) row.
## @version 1
class _ExternalBoundary:
    """A registered callback global that is invoked in-repo but whose
    binding dead-ended at an out-of-repo supplier (a forwarded parameter
    chain that never reached an indexed function). This is the causal
    TERMINUS the explorer matrix asks about — recorded instead of silently
    dropped at the `if not bound` discard point.

    @brief External-boundary terminus record.
    @version 1
    """

    __slots__ = (
        "global_name",
        "memberdef_rowid",
        "registered_by_rowid",
        "registered_param_index",
    )

    ## @brief Store an external-boundary terminus record's identifying fields.
    ## @version 1
    ## @dg_internal
    def __init__(
        self,
        memberdef_rowid: int,
        global_name: str,
        registered_by_rowid: int | None,
        registered_param_index: int | None,
    ) -> None:
        self.memberdef_rowid = memberdef_rowid
        self.global_name = global_name
        self.registered_by_rowid = registered_by_rowid
        self.registered_param_index = registered_param_index


## @brief True if a registration's binding chain forwards a param out of repo.
## @version 3
## @req REQ-DDB-SCHEMA-003
def _registration_forwards_externally(
    func_name: str,
    param_index: int,
    collector: _CallbackCollector,
    rowid_to_name: dict[int, str],
    visited: set[tuple[str, int]],
) -> bool:
    """Distinguish a genuinely-external terminus (a forwarded-parameter
    chain that dead-ends at an out-of-repo caller — the `svc_notify_cb` shape)
    from a NULL-only registration (`DataModel_Initialize(NULL)`), which must
    NOT be recorded. Returns True as soon as any call site forwards one of
    the caller's OWN parameters into `param_index`: since this is only ever
    called when the overall binding resolved to nothing, a forward hop means
    the callback is passed through but never bound in-repo.

    @brief Detect a forwarded-parameter (external) binding dead-end.
    @version 3
    """
    if (func_name, param_index) in visited:
        return False
    visited.add((func_name, param_index))
    for caller_rowid, args in collector.call_sites.get(func_name, []):
        if param_index >= len(args):
            continue
        arg = args[param_index]
        if arg is None or _is_known_function(arg, collector):
            continue
        caller_sig = _caller_signature(caller_rowid, rowid_to_name, collector)
        if caller_sig is not None and arg in caller_sig.param_names:
            return True
    return False


## @brief Record an external-boundary row for a dead-ended registration.
## @version 2
## @req REQ-DDB-SCHEMA-003
def _record_external_boundary(
    global_name: str,
    registrations: list[tuple[int, int]],
    collector: _CallbackCollector,
    rowid_to_name: dict[int, str],
    boundaries: list[_ExternalBoundary],
) -> None:
    """Gate to the genuinely-external case (a forwarded-param dead-end, NOT
    a NULL-only registration) and, when it applies, record one terminus row
    per in-repo invoking function — capturing the registering function +
    param index (in-hand at this exact point) per the consumer-fit add.

    @brief Record terminus rows for a dead-ended callback registration.
    @version 2
    """
    call_sites = collector.call_sites.get(global_name, [])
    if not call_sites:
        return  # never invoked in-repo — nothing to terminate a chain at
    external = any(
        _registration_forwards_externally(
            collector.signatures[func_rowid].name,
            param_index,
            collector,
            rowid_to_name,
            set(),
        )
        for func_rowid, param_index in registrations
        if func_rowid in collector.signatures
    )
    if not external:
        return  # NULL-only / non-forwarding registration — not a terminus
    registered_by_rowid, registered_param_index = registrations[0]
    for caller_rowid, _args in call_sites:
        boundaries.append(
            _ExternalBoundary(
                memberdef_rowid=caller_rowid,
                global_name=global_name,
                registered_by_rowid=registered_by_rowid,
                registered_param_index=registered_param_index,
            ),
        )


## @brief Whether one preprocessor guard holds under a configuration.
## @param text The guard's condition expression.
## @param negated True when the binding sits in this guard's negative arm.
## @param defined The macro names the declared configuration defines.
## @return True (holds), False (does not), or None (undecidable).
## @version 1
## @dg_internal
def _guard_holds(text: str, negated: bool, defined: frozenset[str]) -> bool | None:
    """@brief Apply a guard's polarity to its evaluated condition.

    @return True, False, or None when the condition cannot be decided.
    @version 1
    """
    verdict = evaluate_condition(text, defined)
    return None if verdict is None else verdict != negated


## @brief Whether a binding's preprocessor branch is live under a configuration.
## @param guards The binding's guard chain, innermost first.
## @param config The resolved preprocessor configuration.
## @return True (live and certain), False (definitively dead), None (unknown).
## @version 1
## @req REQ-DDB-PIPE-003
## @dg_internal
def _binding_branch(guards: tuple, config: PreprocessorConfig) -> bool | None:
    """gh#35's three-way answer, and each value means something different downstream:
    True emits a 'resolved' edge, None emits a 'fuzzy' one, False emits NOTHING.

    AN UNDECLARED CONFIGURATION RETURNS None, NEVER False, and the `declared` check is
    what makes that so. `defined(X)` against an empty macro set evaluates to False
    perfectly correctly — that is what doxygen parses — but reading that as "the branch is
    dead" would DELETE every conditional binding on every target that declares no
    configuration, i.e. empty the layer for most repositories in exchange for fixing a
    double edge. The declaration is what turns a False into evidence.

    An EMPTY chain returns True unconditionally and before anything else is consulted, so
    a branch-free binding grades exactly as it did before gh#35 whatever the config says.

    @brief Decide a binding's branch under the declared configuration.
    @return True, False, or None.
    @version 1
    """
    if not guards:
        return True
    if not config.declared:
        return None
    verdicts = [_guard_holds(text, negated, config.defined_names) for text, negated in guards]
    dead = any(v is False for v in verdicts)
    unknown = any(v is None for v in verdicts)
    return False if dead else (None if unknown else True)


## @brief The direct bindings of one global that survive branch selection.
## @param global_name The bound global's name.
## @param collector The cross-file collector.
## @param config The resolved preprocessor configuration.
## @return name -> True when its branch is certain, False when it is unknown.
## @version 2
## @dg_internal
def _live_direct_bindings(
    global_name: str,
    collector: _CallbackCollector,
    config: PreprocessorConfig,
) -> dict[str, bool]:
    """Collapses to ONE entry per bound name reporting the STRONGEST evidence, the same
    rule the query layer applies to a call edge several layers found. A name bound both
    unconditionally and inside a branch is certain: the unconditional binding happens
    whatever the configuration, and emitting the pair twice would race
    `INSERT OR IGNORE` against the UNIQUE constraint and keep whichever row went first.

    @brief Select a global's live direct bindings and grade each one's certainty.
    @return Bound name -> branch-certain flag.
    @version 2
    """
    live: dict[str, bool] = {}
    for name, guards in collector.direct_bindings.get(global_name, []):
        if not _is_known_function(name, collector):
            continue
        branch = _binding_branch(guards, config)
        if branch is False:
            continue
        live[name] = live.get(name, False) or branch is True
    return live


## @brief The bindings of one global that branch selection eliminated entirely.
## @param global_name The bound global's name.
## @param collector The cross-file collector.
## @param config The resolved preprocessor configuration.
## @return name -> False (never branch-certain), for every eliminated binding.
## @version 1
## @req REQ-DDB-PIPE-003
## @dg_internal
def _branch_eliminated_bindings(
    global_name: str,
    collector: _CallbackCollector,
    config: PreprocessorConfig,
) -> dict[str, bool]:
    """BRANCH SELECTION IS A SELECTION AMONG ALTERNATIVES, NEVER AN ERASER, and this is
    the function that says so. It is consulted only when selection left a global with
    nothing at all — at which point the configuration did not tell us which
    implementation is live, it told us this variant binds none of them, while the index
    still carries every one of the bound functions because gh#11 recovered them from the
    source text precisely BECAUSE the preprocessor skipped them.

    Emitting nothing there is the fallback-to-False that `evaluate_condition` refuses one
    level down, arrived at by a different route: not "we could not read the guard" but
    "we read every guard and they were all dead". The honest statement is the same one,
    and 'fuzzy' is what it already means to every consumer — skipped by both
    `mark_reachability` and the thread BFS, so no traversal reads a branch this build
    cannot compile as fact.

    EVERY value is False, never `branch is None`. A restored binding is by construction
    one whose branch evaluated dead, so it is the weakest premise this layer emits; a
    True here would grade a definitively-dead branch above an undecidable one.

    Measured on Mbed-TLS v3.6.7 with the 142 macros harvested from its own
    `include/mbedtls/mbedtls_config.h`: that header ships `MBEDTLS_THREADING_C` commented
    out, so all 8 bindings of the four `mbedtls_mutex_*` pointers graded dead and this
    layer went from 157 rows to 0 — including the 38 callers of
    `threading_mutex_lock_pthread`, a function the same build indexes.

    @brief Restore the bindings a configuration eliminated, at the undecided grading.
    @return Bound name -> False, for every branch-eliminated binding.
    @version 1
    """
    return {
        name: False
        for name, guards in collector.direct_bindings.get(global_name, [])
        if _is_known_function(name, collector) and _binding_branch(guards, config) is False
    }


## @brief Emit call_edges rows for every resolved callback global.
## @version 6
## @dg_internal
def _emit_resolved_edges(
    collector: _CallbackCollector,
    name_to_rowids: dict[str, list[int]],
    config: PreprocessorConfig | None = None,
) -> tuple[list[tuple[int, int, str]], list[tuple[int, int, str]], list[_ExternalBoundary]]:
    """For each bound global, every call site of that global becomes a call_edges row
    to each bound function — tiered resolved/fuzzy exactly like Layer 3. A
    registration that resolves to nothing but forwards a parameter out of
    repo is recorded as an external_boundaries terminus instead of being
    silently dropped (R1 D4).

    TWO binding sources are unioned per global (gh#1). A PARAMETER registration
    resolves through the registering function's call sites; a DIRECT binding
    (`GLOBAL = impl;`) already names its target and only has to be confirmed to BE an
    indexed function — `_is_known_function` is the confirmation, and it is what keeps
    an ordinary `int x = y;` from ever reaching `_ast_record_call_edge`.

    Confirming here rather than at fold time is not incidental: every file's
    signatures are collected by then, so a binding whose target lives in another
    file resolves, and one whose target is out of repo stays honestly unbound and
    can still be reported as a terminus.

    BRANCH SELECTION (gh#35) applies to the direct half only. A binding whose enclosing
    `#if` is DEAD under the declared configuration emits nothing; one whose branch cannot
    be decided emits at 'fuzzy' even when its name resolves uniquely, because both
    `mark_reachability` and the thread BFS traverse non-fuzzy edges and a binding of
    unknown branch is a weaker premise than a branch-free one. That is this repo's
    weakest-link rule applied to the preprocessor.

    SELECTION NEVER ELIMINATES A GLOBAL ENTIRELY. When it would — every alternative dead
    under the declared configuration — `_branch_eliminated_bindings` restores them all at
    'fuzzy'. Dropping the last one is a different claim from dropping a loser: it asserts
    the global is unbound in a build whose index still holds every implementation, and it
    is what took this layer from 157 rows to 0 on Mbed-TLS under its own config header.

    The order of the two is load-bearing and is the property the tests pin. The terminus
    is recorded off the SELECTION result, before the fallback, so a global that is both
    dead-branch-bound and settable from outside keeps both answers.

    The alternatives-vs-conjunction distinction gh#35 asks for is carried by CONFIDENCE
    rather than by a new column, deliberately. When the configuration IS declared the
    question dissolves — only the live branch's edge exists, so there is nothing to
    distinguish. When it is not, the honest statement is "we do not know which of these
    happens", which is what 'fuzzy' already means to every existing consumer and to both
    BFS traversals. A new `alt_group` column would additionally have to be plumbed
    through `query/` and the MCP payload to be usable at all, and an unread column is a
    promise a consumer cannot cash — gh#37 is that exact defect, `candidates` describing a
    choice no accessor lets anyone make.

    @brief Resolve every registration and direct binding; emit call_edges + terminus rows.
    @version 5
    """
    config = config or PreprocessorConfig()
    rowid_to_name = {r: n for n, rowids in name_to_rowids.items() for r in rowids}
    edges_resolved: list[tuple[int, int, str]] = []
    edges_fuzzy: list[tuple[int, int, str]] = []
    boundaries: list[_ExternalBoundary] = []
    for global_name in collector.registrations.keys() | collector.direct_bindings.keys():
        registrations = collector.registrations.get(global_name, [])
        bound = _live_direct_bindings(global_name, collector, config)
        for func_rowid, param_index in registrations:
            sig = collector.signatures.get(func_rowid)
            if sig is None:
                continue
            ## A registration resolves through call sites rather than through a branch,
            ## so it is certain by the same standard it always was.
            for name in _resolve_binding(sig.name, param_index, collector, rowid_to_name, set()):
                bound[name] = True
        if not bound:
            ## THE FALLBACK LIVES INSIDE THIS BLOCK, and that placement is the whole
            ## mechanism: the terminus decision is already taken, off the SELECTION
            ## result, by the time anything is restored. Hoisting the fallback above the
            ## `if not bound` test would skip the block and silently cost the boundary
            ## row — a global bound behind a dead `#if` AND settable from outside is both
            ## things at once, and a reader wants both answers.
            ## (The order of the two statements WITHIN the block is inert:
            ## `_record_external_boundary` never reads `bound`. A mutation control that
            ## swapped them was recorded MISS and was itself the wrong mutation.)
            _record_external_boundary(
                global_name, registrations, collector, rowid_to_name, boundaries
            )
            bound = _branch_eliminated_bindings(global_name, collector, config)
        if not bound:
            continue
        for caller_rowid, _args in collector.call_sites.get(global_name, []):
            for resolved_name, certain in bound.items():
                _ast_record_call_edge(
                    caller_rowid,
                    resolved_name,
                    name_to_rowids,
                    edges_resolved if certain else edges_fuzzy,
                    edges_fuzzy,
                    SOURCE_FNPTR,
                )
    return edges_resolved, edges_fuzzy, boundaries


## @brief Create the external_boundaries table if it doesn't exist.
## @param conn Open connection to the database being built.
## @return None.
## @version 3
## @req REQ-DDB-SCHEMA-003
## @req REQ-DDB-SCHEMA-007
def _ensure_external_boundaries_table(conn: sqlite3.Connection) -> None:
    """Always-create the terminus table (empty when nothing dead-ends), so
    R2/R4 never branch on its existence — the requirements.py precedent.

    `source` gained a CHECK here: it was `TEXT NOT NULL DEFAULT 'callback_edges'`
    with nothing constraining it, i.e. free text on a column a consumer reads as
    provenance. Only the default was ever written, so the constraint is a
    tightening no existing row can violate.

    @brief Idempotent external_boundaries table creation.
    @version 3
    """
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS external_boundaries (
            memberdef_rowid        INTEGER NOT NULL REFERENCES memberdef(rowid),
            global_name            TEXT NOT NULL,
            kind                   TEXT NOT NULL {check("external_boundaries", "kind")},
            registered_by_rowid    INTEGER REFERENCES memberdef(rowid),
            registered_param_index INTEGER,
            note                   TEXT,
            source                 TEXT NOT NULL DEFAULT 'callback_edges'
                                     {check("external_boundaries", "source")},
            confidence             TEXT NOT NULL {check("external_boundaries", "confidence")},
            UNIQUE(memberdef_rowid, global_name)
        )
        """,
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_external_boundaries_member "
        "ON external_boundaries(memberdef_rowid)",
    )
    conn.commit()


## @brief Insert recorded external-boundary terminus rows.
## @version 2
## @req REQ-DDB-SCHEMA-003
def _insert_external_boundaries(
    conn: sqlite3.Connection,
    boundaries: list[_ExternalBoundary],
) -> int:
    """Bulk-insert terminus rows (kind='unresolved_callback', 'high').

    @brief Insert external_boundaries rows, ignoring duplicates.
    @version 2
    """
    return conn.executemany(
        """
        INSERT OR IGNORE INTO external_boundaries
            (memberdef_rowid, global_name, kind, registered_by_rowid,
             registered_param_index, source, confidence)
        VALUES (?, ?, 'unresolved_callback', ?, ?, 'callback_edges', 'high')
        """,
        [
            (
                b.memberdef_rowid,
                b.global_name,
                b.registered_by_rowid,
                b.registered_param_index,
            )
            for b in boundaries
        ],
    ).rowcount


## @brief Report what preprocessor branch selection did to the conditional bindings.
## @param collector The cross-file collector, after every file is folded.
## @param config The resolved preprocessor configuration.
## @version 2
## @dg_internal
def _log_branch_verdicts(collector: _CallbackCollector, config: PreprocessorConfig) -> None:
    """Says nothing at all when the target has NO conditional binding, which is most of
    them — a line reading "0 dropped, 0 weakened" on every build trains a reader to skip
    it, and this one has to be read on the builds where it matters.

    Names the global AND the bound function for each decision, because "3 bindings
    dropped" is unactionable: the question a reader has is which implementation the graph
    now claims, and only the names answer it.

    THREE buckets, not two, because the per-global fallback means a dead verdict no longer
    implies a deleted edge. A binding whose global kept at least one live alternative is
    genuinely DROPPED; one whose global lost every alternative is RESTORED at 'fuzzy'.
    Reporting both as "dropped" is how a log stops being evidence: the first version of
    this line reported all 8 `mbedtls_mutex_*` bindings as dropped on a build that, after
    the fix, emits 157 rows through them.

    @brief Log dropped, restored and weakened conditional bindings, when there are any.
    @version 2
    """
    buckets: dict[str, list[str]] = {"dropped": [], "restored": [], "weakened": []}
    conditional = 0
    for global_name, bindings in collector.direct_bindings.items():
        eliminated = not _live_direct_bindings(global_name, collector, config)
        for name, guards in bindings:
            if not guards:
                continue
            conditional += 1
            branch = _binding_branch(guards, config)
            if branch is None:
                buckets["weakened"].append(f"{global_name}={name}")
            elif branch is False:
                buckets["restored" if eliminated else "dropped"].append(f"{global_name}={name}")
    if not conditional:
        return
    logger.info(
        "callback_edges: preprocessor branch selection over %d conditional binding(s) "
        "(config source=%s, %d macros) — DROPPED %d as dead branches beaten by a live "
        "alternative (%s); RESTORED %d at fuzzy, dead but their global had no live "
        "alternative (%s); WEAKENED %d to fuzzy, branch undecidable (%s)",
        conditional,
        config.source,
        len(config.macros),
        len(buckets["dropped"]),
        ", ".join(sorted(buckets["dropped"])) or "none",
        len(buckets["restored"]),
        ", ".join(sorted(buckets["restored"])) or "none",
        len(buckets["weakened"]),
        ", ".join(sorted(buckets["weakened"])) or "none",
    )


## @brief Layer 4: resolve callback-registration calls into call_edges rows.
## @param db_path Path to the clew.db being built.
## @param repo_root Repository root (for resolving indexed relative paths).
## @param cache Optional incremental index cache; None disables caching.
## @param preprocessor The resolved preprocessor configuration, for gh#35 branch selection.
## @version 6
## @req REQ-DDB-PIPE-003
def import_callback_registration_edges(
    db_path: Path,
    repo_root: Path,
    cache: IndexCache | None = None,
    preprocessor: PreprocessorConfig | None = None,
) -> None:
    """Walk every indexed C/C++ file, detect `GLOBAL = PARAM;` callback
    registrations, resolve each to its concrete function(s), and insert
    `call_edges` rows for every call site of the registered global.
    No-ops cleanly when tree_sitter isn't installed. Runs unconditionally
    — no CLI flag, since the pattern is structural, not repo-specific.

    The per-file harvest is content-sha cached; the rowid resolution and the
    cross-file binding resolution always rerun.

    `preprocessor` selects which `#if` branch a conditional binding belongs to (gh#35).
    Defaulting it to None rather than requiring it keeps every existing caller working, and
    the default is the SAFE direction: an undeclared configuration grades conditional
    bindings DOWN to 'fuzzy', so a caller that forgets to pass one under-states an edge
    rather than asserting the wrong branch as fact.

    @brief Import callback-registration call edges (Layer 4).
    @version 5
    """
    ts_classes = try_import_tree_sitter()
    if ts_classes is None:
        logger.info(
            "tree_sitter not available — skipping callback-edge resolution",
        )
        # Still create the terminus table (empty) so consumers never branch
        # on its existence — mirrors the always-create tables elsewhere.
        conn = sqlite3.connect(str(db_path))
        _ensure_external_boundaries_table(conn)
        conn.close()
        return

    conn = sqlite3.connect(str(db_path))
    _ensure_external_boundaries_table(conn)
    name_to_rowids, file_funcs = _build_function_indexes(conn)
    collector = _CallbackCollector()
    for path_rowid, payload in run_harvest(
        conn,
        repo_root,
        callback_harvester(),
        ts_classes,
        cache,
    ):
        _fold_callback_payload(payload, file_funcs.get(path_rowid, []), collector)

    edges_resolved, edges_fuzzy, boundaries = _emit_resolved_edges(
        collector, name_to_rowids, preprocessor
    )
    inserted_resolved = conn.executemany(
        "INSERT OR IGNORE INTO call_edges "
        "(caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, ?, 'resolved')",
        edges_resolved,
    ).rowcount
    inserted_fuzzy = conn.executemany(
        "INSERT OR IGNORE INTO call_edges "
        "(caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, ?, 'fuzzy')",
        edges_fuzzy,
    ).rowcount
    inserted_boundaries = _insert_external_boundaries(conn, boundaries)
    conn.commit()
    conn.close()
    logger.info(
        "callback_edges: resolved %d registrations, added %d resolved + "
        "%d fuzzy call_edges rows, %d external-boundary terminus rows",
        len(collector.registrations),
        inserted_resolved,
        inserted_fuzzy,
        inserted_boundaries,
    )
    _log_branch_verdicts(collector, preprocessor or PreprocessorConfig())
