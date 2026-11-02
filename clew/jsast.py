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


## @brief The function an anonymous class expression is the result of, or None.
## @param node A `class` expression node.
## @return The arrow function / function expression whose body is, or returns, the class.
## @version 1
## @dg_internal
def _mixin_function(node: Any) -> Any | None:
    """THE TWO FORMS A MIXIN TAKES, and only those: the class as an arrow's expression body
    (`(s) => class extends s {}`), and `return class ...` directly in a function's block. Any
    other anonymous class (an argument, an assignment) is not a mixin and keeps no name.

    @brief Find the mixin's function.
    @return The function node, or None.
    @version 1
    """
    parent = node.parent
    if parent is not None and parent.type == "return_statement":
        block = parent.parent
        parent = block.parent if block is not None and block.type == "statement_block" else None
    if parent is not None and parent.type in ("arrow_function", "function_expression", "function"):
        return parent
    return None


## @brief The name a class takes: its own, or the binding of the mixin that returns it.
## @param node A class-like node.
## @return The name, or "" for an anonymous class that is not a mixin.
## @version 1
## @dg_internal
def _class_name(node: Any) -> str:
    """A MIXIN'S CLASS IS NAMED FOR ITS BINDING. `const ClientFiles = (s) => class extends s {}`
    is how the codebase refers to it — `mix(Base).with(ClientFiles)` — so the binding is its
    name in every sense a reader uses.

    @brief Name a class.
    @return The name, or "".
    @version 1
    """
    own = _text(node.child_by_field_name("name"))
    if own or node.type != "class":
        return own
    func = _mixin_function(node)
    binding = func.parent if func is not None else None
    if binding is not None and binding.type == "variable_declarator":
        return _text(binding.child_by_field_name("name"))
    return ""


## @brief The class a mixin's `superclass` parameter is declared to construct.
## @param node A mixin's `class` expression.
## @return The constraint's class name, or "" when the chain is not declared.
## @version 1
## @dg_internal
def _mixin_base(node: Any) -> str:
    """FOLLOWS THE DECLARATION, NEVER THE NAME: `extends superclass` → the parameter
    `superclass: TBase` → the type parameter `TBase extends Constructor<ClientBase>` →
    `ClientBase`. Each link is the language's own statement; a missing one yields "" rather
    than a guess.

    @brief Resolve a mixin's base.
    @return The base class name, or "".
    @version 1
    """
    func = _mixin_function(node)
    extended = _heritage_identifier(node)
    if func is None or not extended:
        return ""
    param_type = _parameter_type(func, extended)
    return _constraint_class(func, param_type) if param_type else ""


## @brief The bare identifier a class expression extends, or "".
## @version 1
## @dg_internal
def _heritage_identifier(node: Any) -> str:
    """@brief The `extends <identifier>` name. @return The name or ""."""
    for heritage in node.named_children:
        if heritage.type != "class_heritage":
            continue
        clause = next((c for c in heritage.named_children if c.type == "extends_clause"), heritage)
        target = next((c for c in clause.named_children if c.type == "identifier"), None)
        return _text(target)
    return ""


## @brief The declared type name of one parameter of a function, or "".
## @version 1
## @dg_internal
def _parameter_type(func: Any, name: str) -> str:
    """@brief A parameter's type identifier. @return The type name or ""."""
    params = func.child_by_field_name("parameters")
    for param in params.named_children if params is not None else ():
        if _text(param.child_by_field_name("pattern")) != name:
            continue
        annotation = param.child_by_field_name("type")
        target = (
            annotation.named_children[0]
            if annotation is not None and annotation.named_children
            else None
        )
        return _text(target) if target is not None and target.type == "type_identifier" else ""
    return ""


## @brief The class a type parameter's `Constructor<X>`-style constraint names, or "".
## @version 1
## @dg_internal
def _constraint_class(func: Any, type_name: str) -> str:
    """ANY GENERIC CONSTRAINT WITH ONE TYPE ARGUMENT, not only one spelled `Constructor`: the
    alias is a project's own (`Constructor`, `Ctor`, `GConstructor`), and what identifies the
    class is the argument, so requiring the alias's spelling would be an allowlist.

    @brief Read the constraint's class. @return The class name or "".
    """
    tparams = func.child_by_field_name("type_parameters")
    for tparam in tparams.named_children if tparams is not None else ():
        if _text(tparam.child_by_field_name("name")) != type_name:
            continue
        constraint = tparam.child_by_field_name("constraint")
        generic = next(
            (
                c
                for c in (constraint.named_children if constraint is not None else ())
                if c.type == "generic_type"
            ),
            None,
        )
        args = generic.child_by_field_name("type_arguments") if generic is not None else None
        named = args.named_children if args is not None else []
        return _tail(named[0]) if len(named) == 1 else ""
    return ""


## @brief The mixin class a bound function produces, or None.
## @param func A function or binding node `_resolve_function_node` returned.
## @return The `class` expression node, or None.
## @version 1
## @dg_internal
def _produced_class(func: Any) -> Any | None:
    """@brief The class a mixin function returns. @return The class node or None."""
    from .guard.ts_parser import _function_carrier

    body = _function_carrier(func).child_by_field_name("body")
    if body is None:
        return None
    if body.type == "class":
        return body
    for stmt in body.named_children if body.type == "statement_block" else ():
        value = (
            stmt.named_children[0]
            if stmt.type == "return_statement" and stmt.named_children
            else None
        )
        if value is not None and value.type == "class":
            return value
    return None


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


## Version 4: descends into function bodies; a named closure is scoped under its function.
## Version 3: interface signatures and object-literal functions are recorded (`_member_record`).
## Version 2: descends into the mixin class a bound function produces, and names anonymous classes
## by their binding.
##
## @brief Recursive collection of classes and functions under a node.
## @version 4
## @dg_internal
def _walk(node: Any, spec: Any, cls: str | None, out: dict[str, list[dict[str, Any]]]) -> None:
    from .guard.ts_parser import _function_carrier, _resolve_function_node

    for child in node.children:
        kind = _COMPOUND_KINDS.get(child.type)
        if kind is not None:
            name = _class_name(child)
            if name:
                out["classes"].append(_class_record(child, spec, name, kind, cls))
            _walk(child, spec, name or cls, out)
            continue
        member = _member_record(child, spec, cls)
        if member is not None:
            out["functions"].append(member)
            continue
        func = _resolve_function_node(child, spec)
        if func is not None:
            record = _function_record(func, spec, cls)
            if record is not None:
                out["functions"].append(record)
            mixin = _produced_class(func)
            if mixin is not None:
                _walk(mixin.parent, spec, cls, out)
            elif record is not None:
                ## A CLOSURE IS NAMED UNDER ITS ENCLOSING FUNCTION: `outer.inner`, so two
                ## components that each declare `onPress` are two definitions, not one name.
                scope = f"{cls}.{record['name']}" if cls else record["name"]
                _walk(_function_carrier(func), spec, scope, out)
            continue
        _walk(child, spec, cls, out)


## Version 2: a mixin class's base is its declared constraint type, not the parameter it extends.
##
## @brief An interface signature or an object-literal function as a record, or None.
## @param node Any child node the walk visits.
## @param spec The jsdoc LanguageSpec.
## @param cls The enclosing class or interface name, or None.
## @return The record, or None when the node is neither.
## @version 1
## @dg_internal
def _member_record(node: Any, spec: Any, cls: str | None) -> dict[str, Any] | None:
    """INDEX-ONLY SHAPES, kept out of the gate's rule by living here (owner's ruling: the gate
    does not demand documentation for a type signature or an object's callback property).

    A SIGNATURE IS A DECLARATION: `decl` makes `synth` write it bodiless, as doxygen writes a C
    prototype, so no call site is ever attributed to it. Only a METHOD signature or a property
    typed as a function — `name: string` is data.

    AN OBJECT'S FUNCTION BELONGS TO ITS BINDING: `transitions = {idle: {guard: () => ...}}` gives
    `transitions.guard`, because `transitions` is the declared name a reader writes.

    @brief Record an interface signature or object-literal function.
    @return Record or None.
    @version 1
    """
    if node.type in ("method_signature", "property_signature") and cls:
        return _signature_record(node, spec, cls)
    if node.type == "pair":
        value = node.child_by_field_name("value")
        owner = _binding_of(node)
        if value is not None and value.type in _FUNCTION_VALUES and owner:
            return _value_record(_text(node.child_by_field_name("key")), value, node, owner)
    return None


## Function-valued expression nodes.
_FUNCTION_VALUES = ("arrow_function", "function_expression", "function", "generator_function")


## @brief An interface method or function-typed property signature as a declaration record.
## @return The record, or None for a data property.
## @version 1
## @dg_internal
def _signature_record(node: Any, spec: Any, cls: str) -> dict[str, Any] | None:
    """@brief Record one interface signature. @return Record or None."""
    shape = node
    if node.type == "property_signature":
        annotation = node.child_by_field_name("type")
        shape = next(
            (
                c
                for c in (annotation.named_children if annotation is not None else ())
                if c.type == "function_type"
            ),
            None,
        )
        if shape is None:
            return None
    params = shape.child_by_field_name("parameters")
    ret = shape.child_by_field_name("return_type")
    line = node.start_point[0] + 1
    return {
        "name": _text(node.child_by_field_name("name")),
        "cls": cls,
        "line": line,
        "end": line,
        "col": node.start_point[1],
        "args": _text(params),
        "ret": _text(ret).lstrip(":").strip(),
        "static": 0,
        "doc": _doc_raw(node, spec),
        "decl": True,
    }


## @brief The nearest enclosing `const`/`let` binding's name, or "".
## @version 1
## @dg_internal
def _binding_of(node: Any) -> str:
    """@brief Enclosing binding name. @return The name or ""."""
    parent = node.parent
    while parent is not None and parent.type in ("object", "pair"):
        parent = parent.parent
    if parent is not None and parent.type == "variable_declarator":
        return _text(parent.child_by_field_name("name"))
    return ""


## @brief A function-valued property as a definition record.
## @version 1
## @dg_internal
def _value_record(name: str, value: Any, node: Any, owner: str) -> dict[str, Any] | None:
    """@brief Record an object-literal function. @return Record or None."""
    if not name or value.child_by_field_name("body") is None:
        return None
    return {
        "name": name.strip("'\""),
        "cls": owner,
        "line": node.start_point[0] + 1,
        "end": value.end_point[0] + 1,
        "col": node.start_point[1],
        "args": _text(value.child_by_field_name("parameters")),
        "ret": _text(value.child_by_field_name("return_type")).lstrip(":").strip(),
        "static": 0,
        "doc": "",
    }


## @brief One class-like declaration as a JSON-safe record.
## @return The record.
## @version 2
## @dg_internal
def _class_record(node: Any, spec: Any, name: str, kind: str, outer: str | None) -> dict[str, Any]:
    return {
        "name": name,
        "kind": kind,
        "outer": outer or "",
        "line": node.start_point[0] + 1,
        "col": node.start_point[1],
        "bases": [_mixin_base(node)] if _mixin_base(node) else _bases(node),
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


## Version 2: an anonymous mixin class takes its binding's name, so `this.m()` inside it is qualified.
##
## @brief Byte ranges of every named class in a tree, innermost last.
## @param root The program node.
## @return (start_byte, end_byte, name) per class.
## @version 2
## @dg_internal
def _class_ranges(root: Any) -> list[tuple[int, int, str]]:
    """@brief Class spans, for `this.m()` qualification."""
    ranges = []
    stack = [root]
    while stack:
        node = stack.pop()
        if node.type in _COMPOUND_KINDS:
            name = _class_name(node)
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


## Version 3: member sites carry whether the receiver is an imported module.
##
## @brief Every call site in a JS/TS tree, in `_fold_call_payload`'s shape.
## @param tree Parsed program tree.
## @param src_bytes The file's bytes.
## @param plain Source tag for `f()`.
## @param member Source tag for `obj.m()` / `this.m()` / `new C()`.
## @param binding Source tag for a function passed by name.
## @param jsx Source tag for a component rendered in JSX; empty harvests none.
## @return Sites as `[name, line, source, qualifier, receiver]`, bindings as
##         `[name, line, binding]`.
##
## v2: also harvests JSX element usage as `jsx` sites. `<Card />` is a use of `Card`, and a
## component reached only through JSX had no inbound edge — so "where is it used" answered nothing
## and liveness read it as dead.
## @version 3
## @req REQ-DDB-PIPE-012
def harvest_calls(
    tree: Any, src_bytes: bytes, plain: str, member: str, binding: str, jsx: str = ""
) -> list[list[Any]]:
    """@brief Harvest JS/TS call sites. @version 3"""
    from .guard.ts_parser import _imported_names

    ranges = _class_ranges(tree.root_node)
    imported = _imported_names(tree.root_node)
    sites: list[list[Any]] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        line = node.start_point[0] + 1
        if node.type == "call_expression":
            site = _call_site(node, ranges, plain, member, imported)
            if site is not None:
                sites.append([*site[:1], line, *site[1:]])
            sites += _argument_bindings(node, line, binding)
        elif node.type == "new_expression":
            cls = _tail(node.child_by_field_name("constructor"))
            if cls:
                sites.append(["constructor", line, member, f"{cls}.constructor", ""])
        elif jsx and node.type in _JSX_ELEMENTS:
            component = _jsx_component(node)
            if component:
                sites.append([component, line, jsx, "", ""])
    return sites


## The two element shapes that name a component. A `jsx_element` is an opening tag, children and a
## closing tag, so visiting the OPENING tag covers it once; the closing tag is never visited.
_JSX_ELEMENTS = ("jsx_opening_element", "jsx_self_closing_element")


## @brief The component a JSX element renders, or None for an intrinsic DOM element.
## @param node A `jsx_opening_element` or `jsx_self_closing_element`.
## @return The component's bare name, or None.
## @version 1
## @dg_internal
def _jsx_component(node: Any) -> str | None:
    """REACT'S OWN RULE DECIDES WHAT IS A COMPONENT. A capitalised identifier (`<Card/>`) or a
    member expression (`<Menu.Item/>`) is a component; a lowercase identifier (`<div/>`) is a DOM
    element. Verified against the parser rather than assumed: `<div/>` has an `identifier` name
    exactly like `<Card/>`, so without this test a page of markup emits an edge per tag.

    A member expression resolves by its TAIL, as a member call's name does — `Item` for
    `<Menu.Item/>` — because that is the name a definition carries.

    @brief Name the rendered component.
    @return Component name or None.
    @version 1
    """
    name = node.child_by_field_name("name")
    if name is None:
        return None
    if name.type == "member_expression":
        return _tail(name) or None
    text = _text(name)
    return text if text[:1].isupper() else None


## @brief A call expression as [name, source, qualifier, receiver], or None.
## @return The site without its line, or None.
## @version 1
## @dg_internal
def _call_site(
    node: Any, ranges: list, plain: str, member: str, imported: frozenset[str] = frozenset()
) -> list[Any] | None:
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
    ## The EIGHTH element says whether the receiver is a module this file imports — the one way a
    ## member call can reach a free function. argc and construction are unknown here (-1, 0).
    receiver = _tail(obj)
    via_import = obj is not None and obj.type == "identifier" and receiver in imported
    return [name, member, "", receiver, -1, 0, int(via_import)]


## @brief Bare function names passed as arguments, as binding sites.
## @return Binding sites.
## @version 1
## @dg_internal
def _argument_bindings(node: Any, line: int, binding: str) -> list[list[Any]]:
    args = node.child_by_field_name("arguments")
    if args is None:
        return []
    return [[_text(a), line, binding] for a in args.named_children if a.type == "identifier"]
