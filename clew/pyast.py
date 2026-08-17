# SPDX-License-Identifier: MIT
"""The Python tree-sitter dialect: call sites, spawn sites, and import bindings.

The R1 richness layers (call edges, thread spawns, reachability seeds) were
C/C++-shaped, so on a `.py` file they were EMPTY — measured on clew's own
index before this module existed: 904 functions, 1082 call_edges of which
**zero** carried `source='ast'` or `'ast_member'`, 0 threads, 0 spawn sites. The
core graph came entirely from doxygen (which does read Python), and every
tree-sitter layer contributed nothing.

This module is the Python half. It deliberately does NOT reshape the C walkers:
Python's grammar names different nodes (`call` not `call_expression`,
`attribute` not `field_expression`, `keyword_argument` at all) and its spawn
primitives pass the entry function by KEYWORD, so forcing one walker to serve
both would make each side's logic conditional on the other. The C/C++ path is
untouched and its output is pinned by test.

WHY A NAME IS RESOLVED THROUGH THE FILE'S OWN IMPORTS
-----------------------------------------------------
The single most important decision here. `threading.Thread(target=f)` is a
thread; `Thread(...)` may or may not be — clew's OWN `query/symbols.py` calls
`Thread(id=..., name=...)`, a **dataclass constructor** imported from
`.models`, and `the downstream explorer app` carries a second copy of it. A pattern keyed
on the bare tail `Thread` fabricates a thread row at both sites. That is the #47
failure mode exactly: a number that looks like a finding and is an artifact.

So a callee is resolved against the bindings the FILE ITSELF declares
(`import threading as th`, `from threading import Thread`, `from .models import
Thread`) and the pattern is matched against the RESOLVED dotted name. This is
the Python analogue of keying C++ on `std::thread` rather than a bare `thread`.
Consequences, all verified against real repos:
  - `threading.Thread` / `th.Thread` / `from threading import Thread` → all
    resolve to `threading.Thread` and match. (40 real sites across
    real Python codebases.)
  - `from .models import Thread` → resolves to `.models.Thread`, which matches
    nothing. The dataclass is correctly refused.
  - a name with NO binding (a module-local wrapper) resolves to nothing, and
    only then is the raw text tried — so a repo's declared `--thread-patterns`
    wrapper still matches, while no built-in default ever can (every default is
    a dotted stdlib path, which bare text cannot equal).

Receiver-typed spawns (`ex.submit(fn)`, `loop.run_in_executor(None, fn)`) need
the RECEIVER's type, which an import cannot give. A receiver bound in the same
file to a resolvable constructor (`ex = ThreadPoolExecutor()`, `with
ThreadPoolExecutor() as ex`) is resolved; `self._loop` and a function PARAMETER
are not, and both stay fail-closed. Both real instances found in the reference
repos are of the unresolvable kind (`loop = self._loop`, `executor` as a
parameter), so this layer reports them as nothing rather than guessing — the
honest answer, and the reason the receiver rule is evidence-gated instead of
matching any `.submit(`.

@brief Python tree-sitter dialect: bindings, call sites, spawn sites.
@version 1
"""

from __future__ import annotations

from typing import Any

# tree-sitter-python's root node type. Each grammar stamps its own root
# (`module` here, `translation_unit` for C/C++), so this is an observable fact
# about a parsed tree rather than plumbing the language down through every
# harvester's signature — which would have meant changing the `Harvester.harvest`
# contract shared by seven stages.
PY_ROOT_TYPE = "module"

## Node types that can name a callee statically. Anything else (a `call` result
## being called, a `subscript`) has no static name and belongs to no layer here.
_PY_NAME_NODES = ("identifier", "attribute", "dotted_name")

## The receiver names that mean "the object whose method is being defined". An
## entry argument `self.method` is qualified with the ENCLOSING class, which is
## what makes five different classes' `target=self._run` five distinct threads
## instead of one fabricated collision (measured: `target=self._run` occurs 5
## times in one Python codebase, in 5 unrelated classes).
##
## Public because `shared_key_edges` needs the same list for the OPPOSITE
## purpose: a `self.`-headed chain is a per-instance VARIABLE, so it may qualify
## a thread entry (the class is known from the enclosing `class` block) but must
## never be accepted as a shared KEY. One definition, so the two cannot drift.
SELF_NAMES = ("self", "cls")


## @brief True when a parsed tree came from the Python grammar.
## @param tree A tree-sitter Tree.
## @return True for a Python parse, False for C/C++ (or any other root type).
## @version 1
## @req REQ-DDB-PIPE-003
def is_python_tree(tree: Any) -> bool:
    """Discriminates on the grammar's own root node type, so a stage can pick a
    dialect without the language being threaded through `Harvester.harvest`.

    @brief Detect a Python parse tree.
    @return Whether the tree's root is Python's `module`.
    @version 1
    """
    return tree.root_node.type == PY_ROOT_TYPE


## @brief Decode one node's source text.
## @param node Any tree-sitter node.
## @param src_bytes The file's raw bytes.
## @return The node's text, with undecodable bytes replaced.
## @version 1
## @req REQ-DDB-PIPE-003
def node_text(node: Any, src_bytes: bytes) -> str:
    """@brief Decode a node's byte span to text.

    @version 1
    """
    return src_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


## @brief Flatten an identifier/attribute/dotted_name chain to dotted text.
## @param node Candidate name node.
## @param src_bytes The file's raw bytes.
## @return The dotted name (`a.b.c`), or None when the node is not a static name.
## @version 1
## @req REQ-DDB-PIPE-003
def dotted_name(node: Any, src_bytes: bytes) -> str | None:
    """`attribute` nests left-recursively (`a.b.c` is `attribute(attribute(a,b),c)`),
    so the whole span's text IS the dotted name — but only once we know every
    link is a plain name. A chain containing a call or subscript (`f().b`,
    `d["k"].b`) has no static name and is refused rather than having its text
    taken literally.

    @brief Flatten a static name chain to dotted text.
    @return Dotted name or None.
    @version 1
    """
    if node is None or node.type not in _PY_NAME_NODES:
        return None
    return node_text(node, src_bytes) if _is_static_chain(node) else None


## @brief True when every link of a name chain is a plain identifier.
## @param node An identifier / attribute / dotted_name node.
## @return Whether the chain contains only names (no call, subscript, literal).
## @version 1
## @dg_internal
def _is_static_chain(node: Any) -> bool:
    """Walks down the `object` side of an `attribute` chain. `dotted_name` is
    always static (the grammar only builds it from identifiers), and an
    `identifier` is the base case.

    @brief Verify a name chain holds only identifiers.
    @return True when the chain is fully static.
    @version 1
    """
    cur = node
    while cur is not None and cur.type == "attribute":
        cur = cur.child_by_field_name("object")
    return cur is not None and cur.type in ("identifier", "dotted_name")


## @brief The trailing segment of a dotted name.
## @param dotted A dotted name such as `a.b.c`.
## @return The last segment (`c`), which is what `memberdef.name` stores.
## @version 1
## @req REQ-DDB-PIPE-003
def tail_name(dotted: str) -> str:
    """@brief Last segment of a dotted name.

    @version 1
    """
    return dotted.rsplit(".", 1)[-1]


## @brief The text of a Python string literal, without its quotes.
## @param node A candidate `string` node.
## @param src_bytes The file's raw bytes.
## @return The string's content, or None when the node is not a plain string.
## @version 1
## @req REQ-DDB-PIPE-003
def string_value(node: Any, src_bytes: bytes) -> str | None:
    """Python's grammar splits a string into `string_start` / `string_content` /
    `string_end`, so the C path's `text.strip('"')` would keep the quotes of a
    `'single'` or `f"..."` literal. Reading `string_content` also refuses an
    f-string with an interpolation (which has several content pieces) instead of
    recording a template as if it were a name.

    @brief Read a plain string literal's content.
    @return The content, or None.
    @version 1
    """
    if node is None or node.type != "string":
        return None
    parts = [c for c in node.children if c.type == "string_content"]
    if len(parts) != 1:
        return None
    return node_text(parts[0], src_bytes)


# ── per-file import / receiver bindings ─────────────────────────────────────

## Functions that PRODUCE a receiver whose type is not their own name. A
## constructor call binds the receiver to the constructed type, but
## `asyncio.get_event_loop()` returns a loop, so the mapping has to be stated.
##
## These are STDLIB PRIMITIVES with NO declaration route, the same category as
## `pthread_create` in DEFAULT_SPAWN_PATTERNS: `asyncio` means one thing in every
## repo, so there is nothing repo-shaped here for an author to override. The
## comment here used to promise "a declared override available through
## `.clew.yaml`" and no such section ever existed — the override was a
## `collect_bindings(producers=...)` parameter that no caller, production or test,
## ever passed. The parameter is gone (gh#317); if a target ever does need its own
## receiver producers, that is a declaration section to add then, on evidence.
DEFAULT_RECEIVER_PRODUCERS: dict[str, str] = {
    "asyncio.get_event_loop": "asyncio.AbstractEventLoop",
    "asyncio.new_event_loop": "asyncio.AbstractEventLoop",
    "asyncio.get_running_loop": "asyncio.AbstractEventLoop",
}


## @brief One file's name → fully-qualified-name bindings.
## @version 1
class PyBindings:
    """What the FILE ITSELF says each bare name means: module aliases, imported
    names, and locals bound to a resolvable constructor.

    A name with no binding resolves to None — never to itself. That distinction
    is the whole anti-fabrication mechanism: `Thread` imported from `.models`
    resolves to `.models.Thread` (no match), while an unbound local resolves to
    nothing and only then may be matched as raw text.

    @brief Per-file dotted-name binding table.
    @version 1
    """

    __slots__ = ("names",)

    ## @brief Start with an empty binding table.
    ## @version 1
    ## @dg_internal
    def __init__(self) -> None:
        self.names: dict[str, str] = {}

    ## @brief Resolve a dotted callee to its fully-qualified name.
    ## @param dotted The callee's dotted text (`th.Thread`, `ex.submit`).
    ## @return The fully-qualified name, or None when the head is unbound.
    ## @version 1
    ## @req REQ-DDB-PIPE-003
    def resolve(self, dotted: str) -> str | None:
        """Rewrites only the HEAD segment, since that is the only part an import
        or an assignment can bind; the remaining segments are attribute access on
        whatever the head denotes and pass through unchanged.

        @brief Resolve a dotted name through this file's bindings.
        @return Fully-qualified dotted name, or None.
        @version 1
        """
        head, _, rest = dotted.partition(".")
        base = self.names.get(head)
        if base is None:
            return None
        return f"{base}.{rest}" if rest else base


## @brief Collect one file's import and receiver bindings.
## @param tree The parsed Python tree.
## @param src_bytes The file's raw bytes.
## @return The file's binding table.
## @version 2
## @req REQ-DDB-PIPE-003
def collect_bindings(tree: Any, src_bytes: bytes) -> PyBindings:
    """Two passes, because a receiver binding is resolved THROUGH the import
    bindings (`ex = ThreadPoolExecutor()` needs `ThreadPoolExecutor` to already
    mean `concurrent.futures.ThreadPoolExecutor`). Imports are collected first,
    then assignments and `with ... as` targets.

    DEFAULT_RECEIVER_PRODUCERS is read directly rather than taken as an override
    parameter (gh#317). The parameter existed from the start, was documented as the
    seam a `.clew.yaml` declaration would reach, and was never passed by
    anything — so it was not a seam, it was an untested branch that made the
    constant look configurable while the pipeline could only ever use the default.

    @brief Build a file's binding table from its imports and local constructions.
    @return Populated PyBindings.
    @version 2
    """
    bindings = PyBindings()
    nodes = _collect_by_type(
        tree.root_node,
        ("import_statement", "import_from_statement", "assignment", "as_pattern"),
    )
    for node in nodes:
        if node.type == "import_statement":
            _bind_import(node, src_bytes, bindings)
        elif node.type == "import_from_statement":
            _bind_import_from(node, src_bytes, bindings)
    for node in nodes:
        if node.type in ("assignment", "as_pattern"):
            _bind_receiver(node, src_bytes, bindings, DEFAULT_RECEIVER_PRODUCERS)
    return bindings


## @brief Every node of the given types in one subtree, in document order.
## @param root Node to walk.
## @param types Node types to collect.
## @return Matching nodes, ordered by start byte.
## @version 1
## @dg_internal
def _collect_by_type(root: Any, types: tuple[str, ...]) -> list[Any]:
    """Document order matters for bindings: a later rebinding of the same name
    should win, which only holds if the nodes are visited as written.

    @brief Collect nodes of given types in document order.
    @return Ordered node list.
    @version 1
    """
    found: list[Any] = []
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(reversed(node.children))
        if node.type in types:
            found.append(node)
    return found


## @brief Record `import a.b` / `import a.b as c` bindings.
## @param node An `import_statement` node.
## @param src_bytes The file's raw bytes.
## @param bindings Table mutated in place.
## @version 1
## @dg_internal
def _bind_import(node: Any, src_bytes: bytes, bindings: PyBindings) -> None:
    """`import a.b` binds the HEAD (`a`), because that is the name that becomes
    usable; `import a.b as c` binds `c` to the full path instead.

    @brief Bind a plain import statement's names.
    @version 1
    """
    for child in node.named_children:
        if child.type == "aliased_import":
            target = child.child_by_field_name("alias")
            module = child.child_by_field_name("name")
            if target is not None and module is not None:
                bindings.names[node_text(target, src_bytes)] = node_text(module, src_bytes)
        elif child.type == "dotted_name":
            path = node_text(child, src_bytes)
            bindings.names[path.partition(".")[0]] = path.partition(".")[0]


## @brief Record `from a import b [as c]` bindings.
## @param node An `import_from_statement` node.
## @param src_bytes The file's raw bytes.
## @param bindings Table mutated in place.
## @version 1
## @dg_internal
def _bind_import_from(node: Any, src_bytes: bytes, bindings: PyBindings) -> None:
    """The imported name binds to `<module>.<name>`, so a relative import
    (`from .models import Thread`) yields `.models.Thread` — deliberately a
    NON-matching fully-qualified name rather than None, which keeps the
    dataclass `Thread` from ever reaching the raw-text fallback.

    A `wildcard_import` binds nothing: `from x import *` states no name, so
    every call through it stays unresolved instead of being attributed to `x`.

    @brief Bind a from-import statement's names.
    @version 1
    """
    module_node = node.child_by_field_name("module_name")
    module = node_text(module_node, src_bytes) if module_node is not None else ""
    # Compared by SOURCE SPAN, never by `is`. py-tree-sitter constructs a NEW
    # Python wrapper object on every child access, so `child is module_node` is
    # false even for the same underlying node — the module name then falls
    # through as if it were an imported name and `from threading import Thread`
    # binds `threading -> threading.threading`, breaking every dotted match that
    # depends on it. A byte span identifies a node in a parse tree uniquely and
    # does not depend on the binding's object or `__eq__` semantics.
    skip = (module_node.start_byte, module_node.end_byte) if module_node is not None else None
    for child in node.named_children:
        if skip is not None and (child.start_byte, child.end_byte) == skip:
            continue
        local, imported = _import_from_pair(child, src_bytes)
        if local is not None and imported is not None:
            bindings.names[local] = f"{module}.{imported}" if module else imported


## @brief The (local name, imported name) pair for one from-import clause.
## @param child A `dotted_name` or `aliased_import` under a from-import.
## @param src_bytes The file's raw bytes.
## @return (local binding name, imported name), or (None, None) for a wildcard.
## @version 2
## @dg_internal
def _import_from_pair(child: Any, src_bytes: bytes) -> tuple[str | None, str | None]:
    """@brief Resolve one from-import clause to its local and imported names.

    @return (local, imported) or (None, None).
    @version 2
    """
    if child.type == "dotted_name":
        text = node_text(child, src_bytes)
        return text, text
    alias, name = (
        (child.child_by_field_name("alias"), child.child_by_field_name("name"))
        if child.type == "aliased_import"
        else (None, None)
    )
    if alias is None or name is None:
        return None, None
    return node_text(alias, src_bytes), node_text(name, src_bytes)


## @brief Bind a local name to the type of the constructor it was assigned.
## @param node An `assignment` or `as_pattern` node.
## @param src_bytes The file's raw bytes.
## @param bindings Table mutated in place (and read, to resolve the constructor).
## @param producers Receiver-producing functions → the type they return.
## @version 1
## @dg_internal
def _bind_receiver(
    node: Any,
    src_bytes: bytes,
    bindings: PyBindings,
    producers: dict[str, str],
) -> None:
    """Only a call whose callee RESOLVES through this file's imports binds a
    receiver, so `ex = ThreadPoolExecutor()` binds and `loop = self._loop` does
    not. That asymmetry is the point: without it, `.submit(` would match on any
    object with a `submit` method, which is a very common name.

    @brief Bind a local receiver name to its resolved constructed type.
    @version 1
    """
    target, value = _binding_target_and_value(node)
    if target is None or value is None or value.type != "call":
        return
    callee = dotted_name(value.child_by_field_name("function"), src_bytes)
    resolved = bindings.resolve(callee) if callee else None
    if resolved is None:
        return
    bindings.names[node_text(target, src_bytes)] = producers.get(resolved, resolved)


## @brief The (bound name node, assigned value node) of a binding construct.
## @param node An `assignment` or `as_pattern` node.
## @return (target, value), either element None when the shape is not a simple bind.
## @version 1
## @dg_internal
def _binding_target_and_value(node: Any) -> tuple[Any, Any]:
    """`assignment` names the target on the left; `as_pattern` puts it in an
    `as_pattern_target` AFTER the value. A destructuring target (a tuple
    pattern) is not a simple name and is refused.

    @brief Locate a binding's target and value nodes.
    @return (target node, value node).
    @version 1
    """
    if node.type == "assignment":
        target = node.child_by_field_name("left")
        value = node.child_by_field_name("right")
    else:
        kids = node.named_children
        target = next((c for c in kids if c.type == "as_pattern_target"), None)
        target = target.named_children[0] if target and target.named_children else None
        value = kids[0] if kids else None
    ok = target is not None and target.type == "identifier"
    return (target if ok else None), value


# ── enclosing class context ─────────────────────────────────────────────────


## @brief Byte ranges of every class body in a file, with the class name.
## @param tree The parsed Python tree.
## @param src_bytes The file's raw bytes.
## @return (start_byte, end_byte, class name) per class definition.
## @version 1
## @req REQ-DDB-PIPE-003
def class_ranges(tree: Any, src_bytes: bytes) -> list[tuple[int, int, str]]:
    """Ranges rather than a walk-time scope stack: the harvesters here use flat
    iterative stacks (matching the C walkers), and a containing-range lookup
    keeps that shape while still answering "which class is this call inside?".

    @brief Collect class-body byte ranges and names.
    @return List of (start, end, name).
    @version 1
    """
    ranges: list[tuple[int, int, str]] = []
    for node in _collect_by_type(tree.root_node, ("class_definition",)):
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            ranges.append((node.start_byte, node.end_byte, node_text(name_node, src_bytes)))
    return ranges


## @brief The innermost class whose body contains a byte offset.
## @param ranges Class ranges from `class_ranges`.
## @param offset Byte offset to locate.
## @return The enclosing class name, or None when the offset is at module scope.
## @version 1
## @req REQ-DDB-PIPE-003
def enclosing_class(ranges: list[tuple[int, int, str]], offset: int) -> str | None:
    """Innermost wins (a nested class shadows its outer), chosen by narrowest
    containing span.

    @brief Find the innermost class containing an offset.
    @return Class name or None.
    @version 1
    """
    best: tuple[int, str] | None = None
    for start, end, name in ranges:
        if start <= offset < end and (best is None or (end - start) < best[0]):
            best = (end - start, name)
    return best[1] if best is not None else None


# ── Layer 3: call sites ─────────────────────────────────────────────────────


## @brief The callee's bare tail name plus whether it was attribute-qualified.
## @param callee A `call` node's `function` child (may be None).
## @param src_bytes The file's raw bytes.
## @return (tail name, was_qualified), or None when the callee names nothing.
## @version 1
## @req REQ-DDB-PIPE-003
def callee_tail(callee: Any, src_bytes: bytes) -> tuple[str, bool] | None:
    """Reads the tail out of the `attribute` field DIRECTLY rather than going
    through `dotted_name`, and that difference is the whole point.

    `dotted_name` refuses a chain whose receiver is not itself a static name —
    correct for pattern matching, where `threading.Thread` must be told apart
    from `.models.Thread`. For a CALL EDGE the receiver is irrelevant: only the
    tail is ever matched against `memberdef.name`. Routing call harvest through
    `dotted_name` therefore dropped every chained call outright — measured on the
    committed fixture, `threading.Thread(target=..., name=...).start()` produced
    NO `start` site at all, because its receiver is a `call`. The C path already
    unwraps `field_expression -> field` for exactly this shape
    (`make_obj()->run()`), so refusing it on Python was a dialect inconsistency,
    not a safety property.

    @brief Reduce a Python callee to its tail name and qualification flag.
    @return (tail, qualified) or None.
    @version 1
    """
    if callee is None:
        return None
    if callee.type == "identifier":
        return node_text(callee, src_bytes), False
    field = callee.child_by_field_name("attribute") if callee.type == "attribute" else None
    return (node_text(field, src_bytes), True) if field is not None else None


## @brief Harvest a call's keyword-argument function BINDINGS as call sites.
## @param call_node A Python `call` node.
## @param src_bytes The file's raw bytes.
## @param source_binding Provenance tag for a bound (not called) reference.
## @return One [name, line, source_binding] row per bare-identifier keyword value.
## @version 2
## @dg_internal
def _keyword_bindings(call_node: Any, src_bytes: bytes, source_binding: str) -> list[list[Any]]:
    """gh#1's Python instance. `sub.set_defaults(func=cmd_rubric)` hands a function
    reference to argparse, which calls it later; no layer looking for a CALL to
    `cmd_rubric` finds one, so every argparse subcommand handler in this repo's own
    `acceptance/bench/` reported ZERO callers while its binding sat in plain sight.

    Restricted to a bare `identifier` value, deliberately. An `attribute` value
    (`func=self._cmd`) would have to be matched on its unwrapped tail, which is the
    `ast_member` situation — a name that may belong to any of several classes — and
    grading a BINDING that weakly would put a guess into a layer whose whole claim is
    that the reference is written down. Fail closed instead.

    Known and accepted imprecision: an identifier is not proven to name a function
    here. `cfg(mode=timeout)` where a local `timeout` shadows a function of that name
    yields a spurious edge. This is the same name-resolution bet Layer 3 already makes
    for a bare-identifier call site, and `_ast_record_call_edge` still has to find an
    indexed function of that name before any row is written.

    @brief Harvest keyword-argument function bindings from one call.
    @version 2
    """
    args_node = call_node.child_by_field_name("arguments")
    rows: list[list[Any]] = []
    for child in args_node.named_children if args_node is not None else []:
        if child.type != "keyword_argument":
            continue
        value = child.child_by_field_name("value")
        if value is None or value.type != "identifier":
            continue
        name = src_bytes[value.start_byte : value.end_byte].decode("utf-8", errors="replace")
        rows.append([name, value.start_point[0] + 1, source_binding])
    return rows


## @brief Harvest one Python file's call sites as [callee_name, line, source].
## @param tree The parsed Python tree.
## @param src_bytes The file's raw bytes.
## @param source_plain Provenance tag for a bare-identifier callee.
## @param source_member Provenance tag for an attribute-qualified callee.
## @param source_binding Provenance tag for a keyword-argument function binding (gh#1).
## @return Rowid-free call sites in walk order.
## @version 3
## @req REQ-DDB-PIPE-003
def harvest_calls(
    tree: Any,
    src_bytes: bytes,
    source_plain: str,
    source_member: str,
    source_binding: str,
) -> list[list[Any]]:
    """Emits exactly the shape the C harvester does — `[name, line, source]`,
    rowid-free so it caches on the file's content sha — and reuses the SAME two
    provenance tags rather than inventing Python-specific ones.

    That reuse is a judgement, not a convenience: `ast_member` means "the callee
    was recovered by unwrapping a qualified form down to its unqualified tail,
    which may match several classes". `obj.method()` in Python is precisely that,
    and `memberdef.name` stores the tail for both languages, so the two are the
    same fact about the same kind of edge. A separate value would split one
    concept across two tokens and force every consumer to know both.

    Comprehension bodies, decorator calls (`@app.route(...)`) and calls inside
    lambdas need no special case: each is a `call` node and the flat walk reaches
    all of them.

    Keyword-argument BINDINGS (gh#1) are collected from the same `call` node and
    BEFORE the callee is resolved — a call whose own callee is unreadable can still
    carry a perfectly readable binding, and the original `continue` skipped both.

    @brief Harvest Python call sites with call/member/binding provenance.
    @return List of [callee_name, line, source].
    @version 3
    """
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        if node.type != "call":
            continue
        sites.extend(_keyword_bindings(node, src_bytes, source_binding))
        tail = callee_tail(node.child_by_field_name("function"), src_bytes)
        if tail is None:
            continue
        name, qualified = tail
        sites.append([name, node.start_point[0] + 1, source_member if qualified else source_plain])
    return sites


# ── thread spawn sites ──────────────────────────────────────────────────────


## @brief Read a call's Nth POSITIONAL argument, skipping keyword arguments.
## @param call_node A Python `call` node.
## @param index 0-based positional index.
## @return The argument node, or None when there is no such positional argument.
## @version 1
## @req REQ-DDB-PIPE-003
def positional_argument(call_node: Any, index: int) -> Any | None:
    """The C helper counts every named child, which in Python's `argument_list`
    includes `keyword_argument` nodes — so `Thread(target=f)` would report `f` at
    position 0 when `target` is really the second POSITIONAL parameter. Counting
    only positional nodes keeps an index meaning what the callee's signature says.

    @brief Fetch a call's Nth positional argument.
    @return Argument node or None.
    @version 1
    """
    args = call_node.child_by_field_name("arguments")
    if args is None:
        return None
    positional = [
        c
        for c in args.named_children
        if c.type not in ("keyword_argument", "dictionary_splat", "list_splat", "comment")
    ]
    return positional[index] if 0 <= index < len(positional) else None


## @brief Read a call's keyword argument by name.
## @param call_node A Python `call` node.
## @param keyword The keyword to find (`target`, `name`).
## @return The keyword's value node, or None when the call does not pass it.
## @version 2
## @req REQ-DDB-PIPE-003
def keyword_argument(call_node: Any, keyword: str) -> Any | None:
    """Real Python passes the thread entry by keyword essentially always — all 40
    `threading.Thread` sites measured across the two real codebases use
    `target=` — so this, not the positional index, is the common path.

    @brief Fetch a call's keyword-argument value.
    @return Value node or None.
    @version 2
    """
    args = call_node.child_by_field_name("arguments")
    if args is None:
        return None
    for child in args.named_children:
        if child.type != "keyword_argument":
            continue
        name = child.child_by_field_name("name")
        if name is not None and name.text == keyword.encode():
            return child.child_by_field_name("value")
    return None


## @brief Resolve a spawn call's entry argument to (qualified, tail) names.
## @param arg The entry argument node (may be None).
## @param src_bytes The file's raw bytes.
## @param class_name Enclosing class, used to qualify a `self.method` entry.
## @return (qualified name, bare tail), or None when the entry is not resolvable.
## @version 2
## @req REQ-DDB-PIPE-003
def entry_names(arg: Any, src_bytes: bytes, class_name: str | None) -> tuple[str, str] | None:
    """Four shapes resolve, and everything else fails closed:
      - `worker` → (`worker`, `worker`).
      - `self.method` with a known enclosing class → (`Class.method`, `method`).
        This is what separates five classes' `target=self._run`; without it they
        either all vanish or one borrows another's rowid.
      - a deeper chain (`self._server.serve_forever`, `params.get`) → the
        receiver's type is unknown, so only the TAIL is offered and rowid
        resolution succeeds solely when that name is unique in the index.
      - `lambda: self.loop()` / `create_task(coro())` → unwrapped to the single
        called function; a lambda with several calls is ambiguous and refused,
        exactly as the C++ layer refuses a multi-call lambda body.

    Dispatched through a table rather than an if-chain so the shapes stay one
    exit apiece (house limit: at most three returns per function).

    @brief Resolve a Python spawn entry argument to its names.
    @return (qualified, tail) or None.
    @version 2
    """
    if arg is None:
        return None
    handlers = {"lambda": _lambda_entry, "call": _awaited_call_entry}
    return handlers.get(arg.type, _named_entry_names)(arg, src_bytes, class_name)


## @brief (qualified, tail) for an entry argument that is itself a call.
## @param arg A `call` node (`create_task(coro())` passes the coroutine OBJECT).
## @param src_bytes The file's raw bytes.
## @param class_name Enclosing class, for a `self.`-qualified callee.
## @return (qualified, tail), or None when the inner callee names nothing.
## @version 1
## @dg_internal
def _awaited_call_entry(
    arg: Any, src_bytes: bytes, class_name: str | None
) -> tuple[str, str] | None:
    """`asyncio.create_task(worker())` passes the RESULT of calling `worker` — a
    coroutine object — so the entry function is that call's own callee. Recurses
    through `entry_names` so a nested `create_task(self.loop())` qualifies the
    same way a direct `target=self.loop` does.

    @brief Unwrap a call-valued entry argument to the function it calls.
    @return (qualified, tail) or None.
    @version 1
    """
    return entry_names(arg.child_by_field_name("function"), src_bytes, class_name)


## @brief (qualified, tail) for an identifier/attribute entry argument.
## @param arg An `identifier` or `attribute` node.
## @param src_bytes The file's raw bytes.
## @param class_name Enclosing class, for a `self.`-qualified entry.
## @return (qualified, tail), or None when the node names nothing static.
## @version 1
## @dg_internal
def _named_entry_names(
    arg: Any, src_bytes: bytes, class_name: str | None
) -> tuple[str, str] | None:
    """@brief Resolve a static-name entry argument, qualifying `self.method`.

    @return (qualified, tail) or None.
    @version 1
    """
    dotted = dotted_name(arg, src_bytes)
    if dotted is None:
        return None
    tail = tail_name(dotted)
    head = dotted.partition(".")[0]
    if head in SELF_NAMES and dotted.count(".") == 1 and class_name:
        return f"{class_name}.{tail}", tail
    return dotted, tail


## @brief (qualified, tail) for a lambda entry whose body is a single call.
## @param node A `lambda` node.
## @param src_bytes The file's raw bytes.
## @param class_name Enclosing class, for a `self.`-qualified callee.
## @return (qualified, tail), or None when the body has zero or several calls.
## @version 1
## @dg_internal
def _lambda_entry(node: Any, src_bytes: bytes, class_name: str | None) -> tuple[str, str] | None:
    """A body with EXACTLY ONE call is that thread's entry; more than one is
    ambiguous ("which is the loop?") and stays fail-closed so a thread is never
    attributed to an arbitrary leading helper.

    @brief Resolve a single-call lambda entry.
    @return (qualified, tail) or None.
    @version 1
    """
    body = node.child_by_field_name("body")
    calls: list[Any] = []
    stack = [body] if body is not None else []
    while stack and len(calls) < 2:
        current = stack.pop()
        stack.extend(current.children)
        if current.type == "call":
            calls.append(current)
    if len(calls) != 1:
        return None
    return _named_entry_names(calls[0].child_by_field_name("function"), src_bytes, class_name)
