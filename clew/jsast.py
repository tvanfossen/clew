# SPDX-License-Identifier: MIT
"""The JavaScript / TypeScript dialect: definitions for the parse-built front end, and call sites.

Doxygen does not read JS or TS, so nothing produced their `memberdef` rows; and every
harvester sent their trees down the C path, where only a bare `f()` is a call. This module
is both halves for `program`-rooted trees (javascript, typescript, tsx, all from
lang-parsing-substrate):

* `harvest_definitions` — the functions and classes a file defines, with their JSDoc,
  for `clew/synth.py` to write as rows. WHAT COUNTS AS A FUNCTION IS THE GATE'S
  DEFINITION (clew/guard/ts_parser.py): declarations, methods, and names bound to an arrow
  function or function expression. One definition for both is the point: the index and
  the gate must not disagree about whether `const f = () => 1` is a function. Anonymous
  functions (callbacks, IIFEs) are not definitions; calls inside them belong to the
  enclosing named function, which is where a reader looks for them.
* `harvest_calls` — call sites in the `[name, line, source, qualifier, receiver]` shape
  `call_edges._fold_call_payload` already folds for Python: `f()` is plain, `this.m()`
  and `super.m()` are qualified by the enclosing class, `obj.m()` carries `obj` as its
  receiver, `new Foo()` is a call to `Foo.constructor`, and a bare function name passed
  as an argument (`arr.map(fn)`, `setTimeout(tick)`) is a `binding`.

@brief JS/TS definitions and call sites over substrate trees.
@version 1
"""

from __future__ import annotations

from typing import Any

## The root node type of every JS/TS/TSX tree. Python's is `module`, C's and C++'s
## `translation_unit`, Rust's `source_file`; this is how a harvester tells them apart.
JS_ROOT = "program"

## Class-like declarations, and the doxygen compound kind each becomes.
_COMPOUND_KINDS = {
    "class_declaration": "class",
    "abstract_class_declaration": "class",
    "class": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
}


## @brief Whether a tree is JavaScript / TypeScript.
## @param tree A parsed tree.
## @return True for a `program`-rooted tree.
## @version 1
## @dg_internal
def is_js_tree(tree: Any) -> bool:
    """@brief JS/TS/TSX trees are rooted at `program`."""
    return tree.root_node.type == JS_ROOT


## @brief Decoded text of a node, or "" for None.
## @return The node's UTF-8 text.
## @version 1
## @dg_internal
def _text(node: Any) -> str:
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


## @brief The last identifier of an expression: `b` for `a.b`, `Foo` for `ns.Foo`.
## @param node An identifier or member expression.
## @return The tail name, or "" when the expression has none.
## @version 1
## @dg_internal
def _tail(node: Any) -> str:
    """@brief Tail name of a dotted expression."""
    while node is not None and node.type == "member_expression":
        node = node.child_by_field_name("property")
    if node is not None and node.type in ("identifier", "property_identifier", "type_identifier"):
        return _text(node)
    return ""


## @brief The base names a class or interface declares (extends / implements).
## @param node A class-like declaration.
## @return Tail names of every base, in order.
## @version 1
## @dg_internal
def _bases(node: Any) -> list[str]:
    """JavaScript writes `class A extends B` as a `class_heritage` holding the expression;
    TypeScript nests `extends_clause` / `implements_clause` inside it, and an interface uses
    `extends_type_clause`. All three are read the same way: every identifier-ish leaf.

    @brief Read extends/implements names.
    @return The names.
    """
    bases: list[str] = []
    for child in node.named_children:
        if child.type not in ("class_heritage", "extends_type_clause"):
            continue
        stack = list(reversed(child.named_children))
        while stack:
            part = stack.pop()
            name = _tail(part)
            if name:
                bases.append(name)
            elif part.type in ("extends_clause", "implements_clause", "generic_type"):
                stack.extend(reversed(part.named_children))
    return bases


## @brief Every function and class a JS/TS file defines.
## @param tree Parsed program tree.
## @param src_bytes The file's bytes.
## @return {"functions": [...], "classes": [...]}, each entry a JSON-safe dict.
## @version 1
## @req REQ-DDB-PIPE-012
def harvest_definitions(tree: Any, src_bytes: bytes) -> dict[str, list[dict[str, Any]]]:
    """Positions are 1-based lines and 0-based columns, as doxygen writes them. A doc
    is the raw JSDoc block text; `clew/synth.py` renders it, so a rendering fix does not
    have to re-parse every file.

    @brief Harvest one file's JS/TS definitions.
    @return The definitions payload.
    """
    from .guard.ts_languages import LANGUAGE_SPECS

    spec = LANGUAGE_SPECS["typescript"]
    out: dict[str, list[dict[str, Any]]] = {"functions": [], "classes": []}
    _walk(tree.root_node, spec, None, out)
    return out


## @brief Recursive collection of classes and functions under a node.
## @version 1
## @dg_internal
def _walk(node: Any, spec: Any, cls: str | None, out: dict[str, list[dict[str, Any]]]) -> None:
    from .guard.ts_parser import _resolve_function_node

    for child in node.children:
        kind = _COMPOUND_KINDS.get(child.type)
        if kind is not None:
            name = _text(child.child_by_field_name("name"))
            if name:
                out["classes"].append(_class_record(child, spec, name, kind, cls))
            _walk(child, spec, name or cls, out)
            continue
        func = _resolve_function_node(child, spec)
        if func is not None:
            record = _function_record(func, spec, cls)
            if record is not None:
                out["functions"].append(record)
            continue
        _walk(child, spec, cls, out)


## @brief One class-like declaration as a JSON-safe record.
## @return The record.
## @version 1
## @dg_internal
def _class_record(node: Any, spec: Any, name: str, kind: str, outer: str | None) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "outer": outer or "",
        "line": node.start_point[0] + 1,
        "col": node.start_point[1],
        "bases": _bases(node),
        "doc": _doc_raw(node, spec),
    }


## @brief One function as a JSON-safe record, or None without a name or body.
## @return The record, or None.
## @version 1
## @dg_internal
def _function_record(func: Any, spec: Any, cls: str | None) -> dict[str, Any] | None:
    from .guard.ts_parser import _extract_function_name, _extract_signature, _function_carrier

    name = _extract_function_name(func, spec)
    carrier = _function_carrier(func)
    if not name or carrier.child_by_field_name("body") is None:
        return None
    annotation = _text(carrier.child_by_field_name("return_type")).lstrip(":").strip()
    is_static = any(c.type == "static" for c in func.children)
    return {
        "name": name,
        "cls": cls or "",
        "line": func.start_point[0] + 1,
        "end": func.end_point[0] + 1,
        "col": func.start_point[1],
        "args": _extract_signature(func),
        "ret": annotation,
        "static": int(is_static),
        "doc": _doc_raw(func, spec),
    }


## @brief The raw JSDoc block above a node, or "".
## @param node A function, binding or class node.
## @param spec The jsdoc LanguageSpec.
## @return The block's raw text.
## @version 1
## @dg_internal
def _doc_raw(node: Any, spec: Any) -> str:
    """Reuses the gate's lookup, which already climbs `export` and `const` wrappers."""
    from .guard.ts_parser import _find_preceding_doxygen

    block = _find_preceding_doxygen(node, spec, r"/\*\*(?!\*)")
    return block.raw if block is not None else ""


## @brief Byte ranges of every named class in a tree, innermost last.
## @param root The program node.
## @return (start_byte, end_byte, name) per class.
## @version 1
## @dg_internal
def _class_ranges(root: Any) -> list[tuple[int, int, str]]:
    """@brief Class spans, for `this.m()` qualification."""
    ranges = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _COMPOUND_KINDS:
            name = _text(node.child_by_field_name("name"))
            if name:
                ranges.append((node.start_byte, node.end_byte, name))
        stack.extend(node.children)
    return sorted(ranges)


## @brief The innermost class whose span holds a byte offset.
## @return The class name, or "".
## @version 1
## @dg_internal
def _enclosing_class(ranges: list[tuple[int, int, str]], byte: int) -> str:
    inside = [r for r in ranges if r[0] <= byte < r[1]]
    return max(inside)[2] if inside else ""


## @brief Every call site in a JS/TS tree, in `_fold_call_payload`'s shape.
## @param tree Parsed program tree.
## @param src_bytes The file's bytes.
## @param plain Source tag for `f()`.
## @param member Source tag for `obj.m()` / `this.m()` / `new C()`.
## @param binding Source tag for a function passed by name.
## @return Sites as `[name, line, source, qualifier, receiver]`, bindings as
##         `[name, line, binding]`.
## @version 1
## @req REQ-DDB-PIPE-012
def harvest_calls(
    tree: Any, src_bytes: bytes, plain: str, member: str, binding: str
) -> list[list[Any]]:
    """@brief Harvest JS/TS call sites."""
    ranges = _class_ranges(tree.root_node)
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        line = node.start_point[0] + 1
        if node.type == "call_expression":
            site = _call_site(node, ranges, plain, member)
            if site is not None:
                sites.append([*site[:1], line, *site[1:]])
            sites += _argument_bindings(node, line, binding)
        elif node.type == "new_expression":
            cls = _tail(node.child_by_field_name("constructor"))
            if cls:
                sites.append(["constructor", line, member, f"{cls}.constructor", ""])
    return sites


## @brief A call expression as [name, source, qualifier, receiver], or None.
## @return The site without its line, or None.
## @version 1
## @dg_internal
def _call_site(node: Any, ranges: list, plain: str, member: str) -> list[Any] | None:
    callee = node.child_by_field_name("function")
    if callee is None:
        return None
    if callee.type == "identifier":
        return [_text(callee), plain, "", ""]
    if callee.type != "member_expression":
        return None
    name = _text(callee.child_by_field_name("property"))
    if not name:
        return None
    obj = callee.child_by_field_name("object")
    if obj is not None and obj.type in ("this", "super"):
        cls = _enclosing_class(ranges, node.start_byte)
        return [name, member, f"{cls}.{name}" if cls else "", ""]
    return [name, member, "", _tail(obj)]


## @brief Bare function names passed as arguments, as binding sites.
## @return Binding sites.
## @version 1
## @dg_internal
def _argument_bindings(node: Any, line: int, binding: str) -> list[list[Any]]:
    args = node.child_by_field_name("arguments")
    if args is None:
        return []
    return [[_text(a), line, binding] for a in args.named_children if a.type == "identifier"]
