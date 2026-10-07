"""Tree-sitter based function detection and doxygen block extraction.

@brief Parse source files using tree-sitter AST to find functions and their doxygen blocks.
@version 1.0
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from .parser import DoxygenBlock, Function, apply_autobrief, parse_doxygen_tags
from .ts_languages import (
    get_language_spec,
    get_parser_for_language,
)

if TYPE_CHECKING:
    from lang_parsing_substrate import Node

    from .ts_languages import LanguageSpec

logger = logging.getLogger(__name__)


# JS/TS nodes that bind a name to a value, and the values that make the binding a function.
_JS_BINDINGS = ("variable_declarator", "public_field_definition", "field_definition")
_JS_FUNCTION_VALUES = ("arrow_function", "function_expression", "function", "generator_function")
# Wrappers a JSDoc block sits above rather than the definition itself: `export ...`, and the
# `const`/`let`/`var` statement around a declarator.
_JS_DOC_WRAPPERS = ("export_statement", "lexical_declaration", "variable_declaration")


## @brief The function a JS/TS binding names, e.g. the arrow in `const f = () => 1`.
#  @version 1.0
#  @req REQ-DDB-GUARD-025
#  @return The function-valued node, or None when the node is not such a binding
def _bound_function(node: Node) -> Node | None:
    if node.type not in _JS_BINDINGS:
        return None
    value = node.child_by_field_name("value")
    return value if value is not None and value.type in _JS_FUNCTION_VALUES else None


## @brief The node that carries a function's `body` and `parameters`.
#  @details Itself, except for a JS/TS binding, whose function is its value.
#  @version 1.0
#  @dg_internal
#  @return The node to read the body and parameters from
def _function_carrier(func_node: Node) -> Node:
    return _bound_function(func_node) or func_node


## @brief Resolve a child node to a function_definition, handling wrappers.
#  @details In JS/TS a name bound to an arrow function or function expression
#  (`const f = () => ...`, a class field `f = () => ...`) is a function too, and the
#  binding node stands for it.
#  @version 1.3
#  @req REQ-DDB-GUARD-020
#  @return The function_definition node, or None
def _resolve_function_node(child: Node, spec: LanguageSpec) -> Node | None:
    unwrapped = _unwrap_decorated(child)
    if unwrapped.type in spec.function_node_types:
        return unwrapped
    if spec.doc_style == "jsdoc" and _bound_function(child) is not None:
        return child
    if child.type in ("template_declaration", "linkage_specification"):
        for sub in child.children:
            if sub.type in spec.function_node_types:
                return sub
    return None


## @brief Resolve a preceding sibling to a comment node.
#  @details When a macro call like FSM_INITIAL_STATE() precedes a doxygen block,
#  tree-sitter parses the comment as a child of the expression_statement. This
#  function checks the last child of such nodes to find swallowed comments.
#  @version 1.0
#  @req REQ-DDB-GUARD-020
#  @return The comment node, or None
def _resolve_comment_node(prev: Node | None, spec: LanguageSpec) -> Node | None:
    if prev is None:
        return None
    if prev.type in spec.comment_node_types:
        return prev
    # Macro calls (e.g. FSM_INITIAL_STATE) can swallow trailing comments as children
    last = (
        prev.named_children[-1]
        if prev.type == "expression_statement" and prev.named_children
        else None
    )
    return last if last is not None and last.type in spec.comment_node_types else None


## @brief Unwrap a decorated_definition to get the inner definition.
#  @version 1.0
#  @dg_internal
def _unwrap_decorated(node: Node) -> Node:
    if node.type == "decorated_definition":
        for child in node.children:
            if child.type in ("function_definition", "class_definition"):
                return child
    return node


## @brief Extract function name from an AST function node.
#  @version 1.0
#  @dg_internal
def _extract_function_name(node: Node, spec: LanguageSpec) -> str | None:
    name_node = node.child_by_field_name("name")
    if name_node:
        return name_node.text.decode("utf-8")
    declarator = node.child_by_field_name("declarator")
    return _name_from_declarator(declarator) if declarator else None


## @brief Extract a normalized parameter-list signature from a function node.
#  @details Python's function_definition carries a "parameters" field directly; C/C++
#  carries it on the (possibly qualified) declarator chain instead. Whitespace is
#  collapsed so reformatting alone does not change the signature.
#  @version 1.1
#  @req REQ-DDB-GUARD-020
#  @return Normalized parameter-list text, e.g. "(Event const& e)", or "" if not found
def _extract_signature(node: Node) -> str:
    node = _function_carrier(node)
    params = node.child_by_field_name("parameters")
    declarator = node.child_by_field_name("declarator")
    while params is None and declarator is not None:
        params = declarator.child_by_field_name("parameters")
        declarator = declarator.child_by_field_name("declarator")
    if params is None or params.text is None:
        return ""
    return re.sub(r"\s+", " ", params.text.decode("utf-8")).strip()


## @brief Extract the identifier from a C/C++ function_declarator node.
#  @version 1.1
#  @dg_internal
def _name_from_declarator(declarator: Node) -> str | None:
    leaf_types = ("identifier", "field_identifier", "destructor_name")
    if declarator.type in leaf_types:
        return declarator.text.decode("utf-8") if declarator.text else None
    recurse_types = (
        "identifier",
        "function_declarator",
        "qualified_identifier",
        "field_identifier",
        "destructor_name",
    )
    match = next((c for c in declarator.children if c.type in recurse_types), None)
    return _name_from_declarator(match) if match is not None else None


# A doxygen block opens with exactly two hashes. Three or more is a section-header
# convention ("### Setup ###") and must not be read as documentation — a bare
# startswith("##") accepted those, producing an empty-tag block that reported as
# "missing @brief" instead of "no doxygen comment".
_PY_DOXYGEN_OPEN_RE = re.compile(r"^##(?!#)")

# A block declaring @file documents the file, never the next function. Anchored to a
# tag position (start of line, after the comment marker) so prose that merely mentions
# the tag is not treated as a declaration — the escape-aware lookbehind additionally
# honours the \@ convention.
_FILE_TAG_RE = re.compile(r"^\s*#+\s*(?<!\\)@file\b", re.MULTILINE)


## @brief Collect Python-style doxygen comment lines preceding a node.
#  @details The backward walk stops on a line-number gap. Without that, a blank line
#  did not terminate the block, so a file-level `## @file` header merged into the first
#  function's doxygen — producing duplicate brief/version tags, reporting every
#  violation for that function at line 1, and letting a diff touching the file header
#  satisfy the staleness gate. A block carrying `@file` is file-level by definition and
#  is never attributed to a function.
#  @version 2.0
#  @req REQ-DDB-GUARD-019
#  @return The comment nodes forming the block, or None if it is not a doxygen block
def _collect_python_comments(
    prev: Node | None,
    spec: LanguageSpec,
) -> list[Node] | None:
    lines: list[Node] = []
    expected_line: int | None = None
    while prev and prev.type in spec.comment_node_types:
        if expected_line is not None and prev.end_point[0] != expected_line:
            break
        lines.insert(0, prev)
        expected_line = prev.start_point[0] - 1
        prev = prev.prev_named_sibling
    if not lines:
        return None
    block_text = "\n".join(n.text.decode("utf-8") for n in lines)
    if _FILE_TAG_RE.search(block_text):
        return None
    first_text = lines[0].text.decode("utf-8").strip()
    return lines if _PY_DOXYGEN_OPEN_RE.match(first_text) else None


## @brief Collect C-style doxygen comment block preceding a node.
#  @version 1.1
#  @dg_internal
def _collect_c_comment(
    prev: Node | None,
    spec: LanguageSpec,
) -> list[Node] | None:
    comment = _resolve_comment_node(prev, spec)
    if comment is None:
        return None
    block_text = comment.text.decode("utf-8").strip()
    if not block_text.startswith("/**") or block_text.startswith("/***"):
        return None
    return [comment]


## @brief Find the doxygen comment block preceding a function node.
#  @details A JSDoc block sits above the outermost statement: `export ...`, or the
#  `const` declaration around a bound arrow function. Its summary stands in for brief.
#  @version 1.9
#  @req REQ-DDB-GUARD-020
def _find_preceding_doxygen(
    func_node: Node,
    spec: LanguageSpec,
    comment_start_pattern: str,
) -> DoxygenBlock | None:
    target = func_node
    if func_node.parent and func_node.parent.type in (
        "decorated_definition",
        "template_declaration",
        "linkage_specification",
    ):
        target = func_node.parent

    if spec.doc_style == "jsdoc":
        while target.parent is not None and target.parent.type in _JS_DOC_WRAPPERS:
            target = target.parent

    prev = _preceding_node(target)
    is_rust = spec.doc_style == "rust"
    is_python = not is_rust and "##" in comment_start_pattern
    if is_rust:
        comment_lines = _collect_rust_doc(_skip_rust_attributes(prev))
    elif is_python:
        comment_lines = _collect_python_comments(prev, spec)
    else:
        comment_lines = _collect_c_comment(prev, spec)
    if not comment_lines:
        if is_python:
            return _find_python_docstring_block(func_node)
        return None

    # Build raw as the contiguous file substring spanning the block so that
    # blank lines between comment nodes are preserved. This keeps
    # raw.splitlines() aligned 1-1 with file line numbers between
    # start_line and end_line, which the staleness check relies on.
    start_byte = comment_lines[0].start_byte
    end_byte = comment_lines[-1].end_byte
    root = func_node
    while root.parent is not None:
        root = root.parent
    source = root.text or b""
    raw = source[start_byte:end_byte].decode("utf-8", errors="replace")
    tags = parse_doxygen_tags(raw)
    if is_rust or spec.doc_style == "jsdoc":
        apply_autobrief(raw, tags)
    return DoxygenBlock(
        start_line=comment_lines[0].start_point[0],
        end_line=_last_row(comment_lines[-1]),
        tags=tags,
        raw=raw,
    )


# An outer doc comment: `///` but not `////` (rustdoc reads four or more slashes as a plain
# comment), or `/**` but not `/***`. Inner docs (`//!`, `/*!`) document the enclosing module,
# never the next item, so they are never attributed to a function.
_RUST_LINE_DOC_RE = re.compile(r"^///(?!/)")
_RUST_BLOCK_DOC_RE = re.compile(r"^/\*\*(?![*/])")


## @brief Step back over the `#[...]` attributes between a Rust item and its doc comment.
#  @details rustdoc attaches a doc comment to the next ITEM, and attributes are part of the
#  item, so `/// doc` / `#[inline]` / `fn f()` documents `f`. Without this step the
#  attribute is the preceding sibling and every attributed function reads as undocumented.
#  @version 1.0
#  @req REQ-DDB-GUARD-024
#  @return The first preceding sibling that is not an attribute, or None
def _skip_rust_attributes(prev: Node | None) -> Node | None:
    while prev is not None and prev.type == "attribute_item":
        prev = prev.prev_named_sibling
    return prev


## @brief Collect the rustdoc outer doc comment ending at `prev`.
#  @details A contiguous run of `///` lines, or a single `/** */` block. Contiguity is by
#  line number, as for Python: a blank line ends the block. Attributes interleaved with
#  `///` lines are stepped over, since rustdoc concatenates doc lines across them.
#  @version 1.0
#  @req REQ-DDB-GUARD-024
#  @return The comment nodes forming the block, or None if there is no outer doc comment
def _collect_rust_doc(prev: Node | None) -> list[Node] | None:
    if prev is not None and prev.type == "block_comment":
        text = (prev.text or b"").decode("utf-8", errors="replace").strip()
        return [prev] if _RUST_BLOCK_DOC_RE.match(text) else None
    lines: list[Node] = []
    expected_line: int | None = None
    while prev is not None and prev.type in ("line_comment", "attribute_item"):
        if expected_line is not None and _last_row(prev) < expected_line - 1:
            break
        if prev.type == "line_comment":
            text = (prev.text or b"").decode("utf-8", errors="replace").strip()
            if not _RUST_LINE_DOC_RE.match(text):
                break
            lines.insert(0, prev)
        expected_line = prev.start_point[0]
        prev = prev.prev_named_sibling
    return lines or None


## @brief The last row a node occupies.
#  @details A Rust line comment's node INCLUDES its newline, so it ends at column 0 of the
#  next row; counting that row would make a blank line after it look like no gap at all.
#  @version 1.0
#  @dg_internal
#  @return 0-indexed row of the node's last character
def _last_row(node: Node) -> int:
    row, column = node.end_point
    return row - 1 if column == 0 and row > node.start_point[0] else row


## @brief The attribute texts written directly above a Rust item, e.g. ["test", "cfg(test)"].
#  @version 1.0
#  @dg_internal
#  @return Attribute bodies (the text between `#[` and `]`), nearest first
def _rust_attributes(node: Node) -> list[str]:
    attrs: list[str] = []
    prev = node.prev_named_sibling
    while prev is not None and prev.type in ("attribute_item", "line_comment", "block_comment"):
        if prev.type == "attribute_item":
            text = (prev.text or b"").decode("utf-8", errors="replace").strip()
            attrs.append(re.sub(r"\s+", "", text.removeprefix("#[").removesuffix("]")))
        prev = prev.prev_named_sibling
    return attrs


# `#[test]`, `#[tokio::test]`, `#[rstest]`-style harness markers, and `#[cfg(test)]` on the
# inline test module. Inline unit tests are idiomatic Rust, so a source file normally carries
# its own tests, and a path exclude cannot separate them from the code under test.
_RUST_TEST_ATTR_RE = re.compile(r"^(?:[\w:]*::)?(?:test|rstest|bench)(?:\(|$)|^cfg\(test\)$")


## @brief Whether a Rust item is test code: a test function or the `#[cfg(test)]` module.
#  @version 1.0
#  @req REQ-DDB-GUARD-024
#  @return True when an attribute above the item marks it as test code
def _is_rust_test_item(node: Node) -> bool:
    return any(_RUST_TEST_ATTR_RE.match(a) for a in _rust_attributes(node))


# Body nodes whose first statement has no previous sibling. A doxygen block written
# above that first statement is parsed as a child of the *enclosing* declaration,
# positioned before the body, so it must be reached through the body node.
_BODY_NODE_TYPES = ("block", "field_declaration_list", "declaration_list", "compound_statement")


## @brief Find the node preceding a definition, stepping out of an enclosing body.
#  @details A definition that is the first statement in a class or namespace body has
#  no previous sibling: tree-sitter attaches any comment written above it to the
#  enclosing declaration, before the body node. Without this step-out, the first
#  method in a class appears undocumented.
#  @version 1.0
#  @req REQ-DDB-GUARD-019
#  @return The preceding named node, or None if there is genuinely nothing before it
def _preceding_node(target: Node) -> Node | None:
    prev = target.prev_named_sibling
    if prev is not None:
        return prev
    parent = target.parent
    if parent is not None and parent.type in _BODY_NODE_TYPES:
        return parent.prev_named_sibling
    return None


## @brief Find a docstring inside a Python function body and parse doxygen tags.
#  @details PEP 257 leads: a docstring IS the function's documentation, with or
#  without tags, and its summary line stands in for \@brief (PEP 257's own rule).
#  The tags the gate needs (`@version`, `@req`) go inside it. Upstream doxygen-guard
#  ignored a docstring with no `@brief`/`@version`, so an idiomatic docstring
#  reported "no doxygen comment" instead of naming the one missing tag. A preceding
#  `##` block still takes precedence when both exist.
#  @version 1.2
#  @req REQ-DDB-GUARD-021
#  @return DoxygenBlock for a non-empty docstring, else None
def _find_python_docstring_block(func_node: Node) -> DoxygenBlock | None:
    string_node = _find_python_docstring_node(func_node)
    if string_node is None or not string_node.text:
        return None
    raw = string_node.text.decode("utf-8", errors="replace")
    body = _strip_docstring_quotes(raw)
    if not body.strip():
        return None
    tags = parse_doxygen_tags(body)
    apply_autobrief(body, tags)
    return DoxygenBlock(
        start_line=string_node.start_point[0],
        end_line=string_node.end_point[0],
        tags=tags,
        raw=raw,
    )


## @brief Locate the docstring string-node at the head of a Python function body.
#  @version 1.0
#  @dg_internal
#  @return The string AST node, or None if the body has no leading docstring
def _find_python_docstring_node(func_node: Node) -> Node | None:
    body = func_node.child_by_field_name("body")
    if body is None:
        return None
    first_stmt = next((c for c in body.named_children if c.type != "comment"), None)
    if first_stmt is None or first_stmt.type != "expression_statement":
        return None
    return next((c for c in first_stmt.named_children if c.type == "string"), None)


_DOCSTRING_QUOTE_RE = re.compile(r'^[rRbBuU]{0,2}("""|\'\'\'|"|\')')


## @brief Strip surrounding quotes from a Python string literal for tag parsing.
#  @version 1.0
#  @dg_internal
def _strip_docstring_quotes(raw: str) -> str:
    stripped = raw.strip()
    match = _DOCSTRING_QUOTE_RE.match(stripped)
    if not match:
        return raw
    quote = match.group(1)
    if stripped.endswith(quote) and len(stripped) >= 2 * len(quote):
        return stripped[match.end() : -len(quote)]
    return stripped[match.end() :]


## @brief Parse functions from source content using tree-sitter.
#  @version 1.1
#  @req REQ-DDB-GUARD-020
#  @return List of Function objects detected in the source content
def parse_functions_ts(
    content: str,
    lang_name: str,
    exclude_names: list[str] | None = None,
    comment_start_pattern: str = r"/\*\*(?!\*)",
) -> list[Function]:
    parser = get_parser_for_language(lang_name)
    if parser is None:
        logger.warning("No parser for language %s, skipping", lang_name)
        return []

    spec = get_language_spec(lang_name)
    if spec is None:
        return []

    exclude = set(exclude_names or [])
    tree = parser.parse(content.encode("utf-8"))
    functions: list[Function] = []

    _collect_functions(tree.root_node, spec, exclude, comment_start_pattern, functions)

    return functions


## @brief Recursively collect function definitions from the AST.
#  @details Rust test code (`#[test]` functions, the `#[cfg(test)]` module) is skipped.
#  A JS/TS function bound to a name is read through its value (_function_carrier).
#  @version 1.6
#  @req REQ-DDB-GUARD-020
def _collect_functions(
    node: Node,
    spec: LanguageSpec,
    exclude: set[str],
    comment_start_pattern: str,
    functions: list[Function],
    enclosing_class: str | None = None,
) -> None:
    for child in node.children:
        if spec.doc_style == "rust" and _is_rust_test_item(child):
            continue
        new_enclosing = _enclosing_class_for(child, enclosing_class)
        func_node = _resolve_function_node(child, spec)
        if func_node:
            name = _extract_function_name(func_node, spec)
            if name is None or name in exclude:
                continue
            body_node = _function_carrier(func_node).child_by_field_name("body")
            if body_node is None:
                continue
            doxygen = _find_preceding_doxygen(func_node, spec, comment_start_pattern)
            resolved_enclosing = new_enclosing or _qualified_enclosing(func_node)
            functions.append(
                Function(
                    name=name,
                    def_line=func_node.start_point[0],
                    body_end=func_node.end_point[0],
                    doxygen=doxygen,
                    enclosing_class=resolved_enclosing,
                    signature=_extract_signature(func_node),
                    returns_void=_js_returns_void(func_node) if spec.doc_style == "jsdoc" else None,
                )
            )
        else:
            _collect_functions(
                child, spec, exclude, comment_start_pattern, functions, new_enclosing
            )


# A TypeScript return annotation that means "no value": `void`, `never`, `undefined`,
# and the same wrapped in `Promise<...>`.
_TS_VOID_RETURN_RE = re.compile(r"^:\s*(?:Promise\s*<\s*)?(?:void|never|undefined)\s*>?\s*$")


## @brief Whether a JS/TS function returns no value, as far as its annotation says.
#  @details Plain JavaScript has no annotation, so it is treated as void: the gate cannot
#  know, and demanding \@return of every JS function would be noise rather than policy.
#  @version 1.0
#  @req REQ-DDB-GUARD-025
#  @return True when unannotated or annotated void-like
def _js_returns_void(func_node: Node) -> bool:
    annotation = _function_carrier(func_node).child_by_field_name("return_type")
    if annotation is None or annotation.text is None:
        return True
    return bool(_TS_VOID_RETURN_RE.match(annotation.text.decode("utf-8", errors="replace")))


## @brief Resolve enclosing class name when entering a class/struct node.
#  @details Rust has no class: an `impl` block names its self type and a `trait` its own
#  name, and those play the role of the enclosing class. JS/TS classes name themselves.
#  @version 1.3
#  @dg_internal
#  @return Class/struct name if node is a class definition, else parent value
def _enclosing_class_for(child: Node, parent: str | None) -> str | None:
    if child.type in (
        "class_specifier",
        "struct_specifier",
        "class_definition",
        "trait_item",
        "class_declaration",
        "abstract_class_declaration",
        "class",
    ):
        name_node = child.child_by_field_name("name")
        if name_node and name_node.text:
            return name_node.text.decode("utf-8")
    if child.type == "impl_item":
        return _rust_impl_self_type(child) or parent
    return parent


## @brief The self type an `impl` block is for, without generic arguments: `Foo` for
#  `impl<T> Trait for Foo<T>`.
#  @details Keys overloads apart in the staleness check: two impls each defining `new`
#  must not share an identity.
#  @version 1.0
#  @dg_internal
#  @return The type name, or None when the impl has no readable type
def _rust_impl_self_type(impl_node: Node) -> str | None:
    type_node = impl_node.child_by_field_name("type")
    if type_node is None:
        return None
    inner = type_node.child_by_field_name("type") if type_node.type == "generic_type" else None
    named = inner or type_node
    return named.text.decode("utf-8") if named.text else None


## @brief Extract enclosing class from a qualified function declarator (Foo::bar).
#  @version 1.0
#  @dg_internal
#  @return Class name from qualifier prefix, or None if not qualified
def _qualified_enclosing(func_node: Node) -> str | None:
    declarator = func_node.child_by_field_name("declarator")
    while declarator is not None:
        if declarator.type == "qualified_identifier":
            ns = declarator.child_by_field_name("scope")
            if ns and ns.text:
                return ns.text.decode("utf-8")
            return None
        declarator = declarator.child_by_field_name("declarator")
    return None
