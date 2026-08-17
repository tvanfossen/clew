# SPDX-License-Identifier: MIT
"""Definition / parameter / forwarding-call extraction from a parse tree.

Split from `scanning` by responsibility: that module decides WHICH files to read
and folds the results; this one knows the node shapes.

The non-obvious part is macros. tree-sitter hands `preproc_function_def` its
body as a single unparsed `preproc_arg` token, so a macro forwarding to a spawn
primitive has no visible call at all. The body is therefore re-parsed inside a
synthetic function wrapper. Measured on a C/POSIX library, skipping that step takes
the thread detector from 8 candidates to 0 — its whole spawn chain runs through
a two-arm `#if` macro.

The census deliberately does NOT get the same treatment. `threads._walk_spawn_sites`
is equally blind to calls inside macro bodies, so counting them as spawn sites
would report attribution the real pipeline cannot deliver.

@brief Function/macro definitions, parameters and parameter-forwarding calls.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

## Definition node types. The macro arm is not an edge case — see the docstring.
DEF_TYPES = frozenset({"function_definition", "preproc_function_def"})

## Callee node shapes `threads._walk_spawn_sites` can key on. Harvesting a
## broader set would propose wrappers whose call sites the pipeline can never
## match.
CALLEE_TYPES = frozenset({"identifier", "qualified_identifier"})

_PARAM_TYPES = frozenset({"parameter_declaration", "optional_parameter_declaration"})

## Expression wrappers unwrapped when asking "is this argument a bare name?".
## `&fn`, `(fn)` and `(entry_t)fn` all name a function as plainly as `fn` does.
_UNWRAP_TYPES = frozenset({"pointer_expression", "parenthesized_expression", "cast_expression"})


## @brief One call that passes an enclosing definition's parameter through.
## @version 1
@dataclass(frozen=True)
class ForwardCall:
    """`arg_params` maps argument position -> the enclosing definition's
    parameter position, for every argument that names a parameter. That map is
    the whole derivation: a wrapper's `entry_arg_index` is the parameter sitting
    at the callee's own entry argument.

    @brief A parameter-forwarding call site inside a definition.
    @version 1
    """

    callee: str
    line: int
    arg_params: tuple[tuple[int, int], ...]


## @brief One function or macro definition, with its forwarding call evidence.
## @version 1
@dataclass(frozen=True)
class FuncDef:
    """`forwards` holds only calls whose arguments include a bare identifier
    equal to one of `params`. Filtering at harvest time is what keeps a
    whole-repo corpus small enough to hold in memory.

    @brief A definition plus the calls through which it forwards a parameter.
    @version 1
    """

    name: str
    rel_path: str
    line: int
    params: tuple[str, ...]
    is_macro: bool
    in_scope: bool
    forwards: tuple[ForwardCall, ...] = ()


## @brief Iterate every node of a tree-sitter subtree, depth first.
## @param root Node to start from.
## @return Generator over the subtree's nodes.
## @version 1
## @req REQ-DDB-CONFIG-001
def walk(root: Any) -> Any:
    """@brief Depth-first iteration over a parse subtree."""
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        yield node


## @brief The callee's text when it is an identifier / qualified identifier.
## @param node A call_expression node.
## @param src Raw file bytes.
## @return The callee text, or "" for a shape the pipeline cannot key on.
## @version 1
## @req REQ-DDB-CONFIG-001
def callee_name(node: Any, src: bytes) -> str:
    """@brief Decode a call's callee name, restricted to matchable shapes."""
    callee = node.child_by_field_name("function")
    if callee is None or callee.type not in CALLEE_TYPES:
        return ""
    return src[callee.start_byte : callee.end_byte].decode("utf-8", errors="replace")


## @brief Text of a node.
## @param node Any parse node.
## @param src Raw file bytes.
## @return The node's source text.
## @version 1
## @req REQ-DDB-CONFIG-001
def text_of(node: Any, src: bytes) -> str:
    """@brief Decode one node's source text."""
    return src[node.start_byte : node.end_byte].decode("utf-8", errors="replace")


## @brief Build the FuncDef for one definition node, or None when unusable.
## @param node A function_definition or preproc_function_def node.
## @param src Raw file bytes.
## @param rel Repo-relative path of the file.
## @param scoped Whether the file is inside the derived index scope.
## @param ts_classes (Language, Parser) from tree_sitter, for macro-body re-parse.
## @return The FuncDef, or None when the definition has no usable name.
## @version 1
## @req REQ-DDB-CONFIG-001
def definition_record(
    node: Any, src: bytes, rel: str, scoped: bool, ts_classes: tuple[Any, Any]
) -> FuncDef | None:
    """@brief Extract one definition's name, parameters and forwarding calls."""
    signature = _signature(node, src, ts_classes)
    if signature is None:
        return None
    name, params, body, body_src = signature
    line = node.start_point[0] + 1
    return FuncDef(
        name=name,
        rel_path=rel,
        line=line,
        params=params,
        is_macro=node.type == "preproc_function_def",
        in_scope=scoped,
        forwards=_forward_calls(body, body_src, params, line) if body is not None else (),
    )


## @brief Name, parameters and walkable body of one definition node.
## @param node A function_definition or preproc_function_def node.
## @param src Raw file bytes.
## @param ts_classes (Language, Parser) from tree_sitter.
## @return (name, params, body node, bytes the body was parsed from), or None.
## @version 1
## @dg_internal
def _signature(
    node: Any, src: bytes, ts_classes: tuple[Any, Any]
) -> tuple[str, tuple[str, ...], Any, bytes] | None:
    """A macro's body lives in a different byte buffer than the file's, because
    it had to be re-parsed — so the buffer travels with the body node rather
    than being assumed to be `src`.

    @brief Resolve one definition to (name, params, body, body bytes).
    @version 1
    """
    if node.type == "preproc_function_def":
        named = _macro_signature(node, src)
        body, body_src = _macro_body(node, src, ts_classes) if named else (None, b"")
        return (*named, body, body_src) if named else None
    signature = _function_signature(node, src)
    return signature


## @brief Name, parameters and body of a `function_definition`.
## @param node The function_definition node.
## @param src Raw file bytes.
## @return (name, params, body node, src), or None when there is no declarator.
## @version 1
## @dg_internal
def _function_signature(node: Any, src: bytes) -> tuple[str, tuple[str, ...], Any, bytes] | None:
    """@brief Read a C/C++ function definition's name, parameters and body."""
    declarator = _function_declarator(node.child_by_field_name("declarator"))
    if declarator is None:
        return None
    name_node = declarator.child_by_field_name("declarator")
    name = _tail_name(name_node, src) if name_node is not None else ""
    if not name:
        return None
    params = _param_names(declarator.child_by_field_name("parameters"), src)
    return name, params, node.child_by_field_name("body") or node, src


## @brief Name and parameters of a `preproc_function_def`.
## @param node The preproc_function_def node.
## @param src Raw file bytes.
## @return (name, params), or None when the macro has no name.
## @version 1
## @dg_internal
def _macro_signature(node: Any, src: bytes) -> tuple[str, tuple[str, ...]] | None:
    """@brief Read a function-like macro's name and parameter identifiers."""
    name_node = node.child_by_field_name("name")
    if name_node is None:
        return None
    params_node = node.child_by_field_name("parameters")
    params = (
        tuple(text_of(c, src) for c in params_node.named_children if c.type == "identifier")
        if params_node is not None
        else ()
    )
    return text_of(name_node, src), params


## @brief Re-parse a macro's body so its calls become visible.
## @param node The preproc_function_def node.
## @param src Raw file bytes.
## @param ts_classes (Language, Parser) from tree_sitter.
## @return (parsed body root, the bytes it was parsed from); (None, b"") when empty.
## @version 1
## @dg_internal
def _macro_body(node: Any, src: bytes, ts_classes: tuple[Any, Any]) -> tuple[Any, bytes]:
    """Wrap the body in a synthetic function so an expression-shaped body parses
    as a statement. A body that still fails to parse yields ERROR nodes, and the
    `call_expression` nodes inside it are usually recovered anyway — which is
    strictly better than the alternative of not looking at all.

    @brief Parse a function-like macro's replacement text.
    @version 1
    """
    arg = node.child_by_field_name("value")
    body_text = text_of(arg, src).replace("\\\n", "\n").strip() if arg is not None else ""
    if not body_text:
        return None, b""
    wrapped = b"void __docsdb_macro__(void){\n" + body_text.encode("utf-8") + b"\n;}\n"
    parser = _macro_parser(ts_classes)
    if parser is None:
        return None, b""
    return parser.parse(wrapped).root_node, wrapped


_MACRO_PARSER: list[Any] = []


## @brief Memoised C parser used for macro replacement text.
## @param ts_classes (Language, Parser) from tree_sitter.
## @return A Parser, or None when the C grammar is not installed.
## @version 2
## @dg_internal
def _macro_parser(ts_classes: tuple[Any, Any]) -> Any:
    """Always the C grammar: a replacement list is preprocessor text, and the
    C++ grammar buys nothing for the call shapes this module reads.

    @brief Build (once) the parser for macro bodies.
    @version 2
    """
    if not _MACRO_PARSER:
        language_cls, parser_cls = ts_classes
        try:
            import tree_sitter_c

            _MACRO_PARSER.append(parser_cls(language_cls(tree_sitter_c.language())))
        except ImportError:
            _MACRO_PARSER.append(None)
    return _MACRO_PARSER[0]


## @brief Descend a declarator chain to its `function_declarator`.
## @param node The definition's declarator node, or None.
## @return The function_declarator, or None when there is none.
## @version 1
## @dg_internal
def _function_declarator(node: Any) -> Any:
    """`void *f(void)` and `int (*g(void))(void)` wrap the function declarator in
    pointer/parenthesized declarators, so the chain has to be walked rather than
    assumed one level deep.

    @brief Locate the function_declarator of a definition.
    @version 1
    """
    cur = node
    while cur is not None and cur.type != "function_declarator":
        nxt = cur.child_by_field_name("declarator")
        if nxt is None:
            return None
        cur = nxt
    return cur


## @brief The trailing simple name of a declarator node.
## @param node Declarator node (identifier / qualified / pointer / field).
## @param src Raw file bytes.
## @return The bare name, or "" when the node names nothing simple.
## @version 1
## @dg_internal
def _tail_name(node: Any, src: bytes) -> str:
    """C++ member definitions declare `Class::method`; the corpus keys on the
    bare name because that is what a call site writes.

    @brief Reduce a declarator to its bare trailing name.
    @version 1
    """
    found = _first_identifier(node, src, ("identifier", "field_identifier"))
    return found or ""


## @brief The first identifier of a subtree in document order.
## @param node Subtree root, or None.
## @param src Raw file bytes.
## @param kinds Node types that count as an identifier.
## @return The identifier text, or None when the subtree has none.
## @version 1
## @dg_internal
def _first_identifier(node: Any, src: bytes, kinds: tuple[str, ...]) -> str | None:
    """Document order matters: a function-pointer parameter nests its name
    (`(*task_fn)`) BEFORE its own parameter list, so the first identifier is the
    parameter's name and not something from its signature.

    @brief Find a subtree's first identifier in document order.
    @version 1
    """
    found: str | None = None
    stack = [node] if node is not None else []
    while stack and found is None:
        cur = stack.pop()
        if cur.type in kinds:
            found = text_of(cur, src)
        else:
            # Reversed so `pop()` yields the FIRST child — a plain stack walk
            # would return the last identifier, not the first.
            stack.extend(reversed(cur.children))
    return found


## @brief Parameter identifiers of a parameter list, in declaration order.
## @param params_node The parameter_list node, or None.
## @param src Raw file bytes.
## @return One entry per parameter; "" for an unnamed one.
## @version 1
## @dg_internal
def _param_names(params_node: Any, src: bytes) -> tuple[str, ...]:
    """@brief Read a parameter list's declared identifiers."""
    if params_node is None:
        return ()
    return tuple(
        _first_identifier(child, src, ("identifier",)) or ""
        for child in params_node.named_children
        if child.type in _PARAM_TYPES
    )


## @brief Calls inside a body that pass one of the definition's parameters on.
## @param body Body node to walk.
## @param src Bytes the body node was parsed from.
## @param params The definition's parameter identifiers.
## @param line Line to attribute macro-body calls to.
## @return One ForwardCall per qualifying call site.
## @version 1
## @dg_internal
def _forward_calls(
    body: Any, src: bytes, params: tuple[str, ...], line: int
) -> tuple[ForwardCall, ...]:
    """@brief Collect the parameter-forwarding calls inside one definition."""
    positions = {name: idx for idx, name in enumerate(params) if name}
    if not positions:
        return ()
    found: list[ForwardCall] = []
    for node in walk(body):
        if node.type != "call_expression":
            continue
        call = _forward_call(node, src, positions, line)
        if call is not None:
            found.append(call)
    return tuple(found)


## @brief One call's parameter-forwarding map, or None when it forwards nothing.
## @param node The call_expression node.
## @param src Bytes the node was parsed from.
## @param positions Parameter name -> declaration position.
## @param line Line to attribute macro-body calls to.
## @return A ForwardCall, or None.
## @version 1
## @dg_internal
def _forward_call(
    node: Any, src: bytes, positions: dict[str, int], line: int
) -> ForwardCall | None:
    """@brief Map a call's arguments onto the enclosing definition's parameters."""
    name = callee_name(node, src)
    args = node.child_by_field_name("arguments")
    if not name or args is None:
        return None
    mapped = [
        (index, positions[ident])
        for index, arg in enumerate(args.named_children)
        if (ident := _bare_identifier(arg, src)) in positions
    ]
    if not mapped:
        return None
    return ForwardCall(name, line, tuple(mapped))


## @brief The bare identifier an argument names, unwrapping &/casts/parentheses.
## @param node An argument node.
## @param src Bytes the node was parsed from.
## @return The identifier text, or "" when the argument is not a bare name.
## @version 1
## @dg_internal
def _bare_identifier(node: Any, src: bytes) -> str:
    """@brief Reduce an argument expression to the plain name it passes."""
    cur = node
    while cur is not None and cur.type in _UNWRAP_TYPES:
        inner = cur.child_by_field_name("value")
        cur = inner if inner is not None else next(iter(cur.named_children), None)
    if cur is None or cur.type != "identifier":
        return ""
    return text_of(cur, src)


## @brief The definition enclosing a node, as (name, parameters).
## @param node Node to search upward from.
## @param src Raw file bytes.
## @return (definition name, its parameters); ("", ()) at file scope.
## @version 1
## @req REQ-DDB-CONFIG-001
def enclosing_definition(node: Any, src: bytes) -> tuple[str, tuple[str, ...]]:
    """@brief Walk up to the enclosing function definition."""
    cur = node.parent
    while cur is not None:
        if cur.type == "function_definition":
            signature = _function_signature(cur, src)
            return (signature[0], signature[1]) if signature is not None else ("", ())
        cur = cur.parent
    return "", ()
