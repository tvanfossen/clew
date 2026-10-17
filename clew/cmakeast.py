# SPDX-License-Identifier: MIT
"""The CMake dialect: function and macro definitions for the parse-built front end.

`CMakeLists.txt` is where an embedded repository states what it builds, with which flags,
against which dependencies — and doxygen does not read it, so the one file a reader needs
for "how is this target built" had no rows at all. `clew/synth.py` writes these rows from
this harvest.

FUNCTION AND MACRO ARE NOT THE SAME THING, and the distinction is recorded rather than
flattened. A CMake `function` gets its own variable scope and real named parameters; a
`macro` pastes its body into the caller's scope, so a variable it sets leaks outward and
its arguments are textual substitutions. A reader debugging exactly that leak needs the
answer to say which one it was, so the payload carries `kind` and the writer maps it onto
doxygen's own vocabulary.

WHY THE LANGUAGE TEST IS A NODE SHAPE, NOT THE ROOT TYPE. A CMake tree is rooted at
`source_file`, which is also Rust's root. `function_def` and `macro_def` exist in no other
grammar clew routes, so their presence is the discriminator — the same reasoning as
`clew/shast.py`, where bash shares `program` with JavaScript.

THE NAME IS AN ARGUMENT, NOT A FIELD. CMake's grammar gives `function_def` a
`function_command` child holding an `argument_list`; the first argument is the definition's
name and the rest are its parameters. There is no `name` field to read, so this walks the
argument list.

@brief CMake function and macro definitions over substrate trees.
@version 1
"""

from __future__ import annotations

from typing import Any

from .scriptast import comment_block_above, node_text, walk_nodes

## CMake shares this root with rust — see the module docstring. A cheap pre-filter, never
## the discriminator.
CMAKE_ROOT = "source_file"

## Definition node → the command node holding its argument list, and what the definition
## IS. The kind strings are this module's own vocabulary; `clew/synth.py` maps them onto
## doxygen's, and `tests/test_cmake_macro_kind_parity.py` holds the two together.
_DEFINITIONS: dict[str, tuple[str, str]] = {
    "function_def": ("function_command", "function"),
    "macro_def": ("macro_command", "macro"),
}

_ARGUMENT_LIST = "argument_list"
_ARGUMENT = "argument"


## @brief Whether a tree holds CMake definitions this module can harvest.
## @param tree A parsed tree.
## @return True for a `source_file`-rooted tree containing a definition node.
## @version 1
## @dg_internal
def is_cmake_tree(tree: Any) -> bool:
    """A Rust tree is also `source_file`-rooted, so the root alone decides nothing. A
    `CMakeLists.txt` that defines no function is therefore not a "CMake tree" by this
    test — correct, because there is nothing in it for this module to harvest either way,
    and the file is registered and searchable regardless.

    @brief A CMake definition node is present.
    """
    if tree.root_node.type != CMAKE_ROOT:
        return False
    return any(node.type in _DEFINITIONS for node in walk_nodes(tree.root_node))


## @brief Harvest one CMake file's function and macro definitions.
## @param tree The parsed tree.
## @param src_bytes The file's bytes.
## @return The definitions payload, in `clew/synth.py`'s shape.
## @version 1
## @req REQ-DDB-PIPE-012
def harvest_definitions(tree: Any, src_bytes: bytes) -> dict[str, list[dict[str, Any]]]:
    """Positions are 1-based lines and 0-based columns, as doxygen writes them, and the
    payload is rowid-free JSON so it caches per file content like every other stage.

    `classes` is present and empty: CMake has no class-like construct, and the shape is
    shared with the JS/TS payload the same writer consumes.

    @brief Harvest CMake definitions.
    @return The definitions payload.
    """
    out: dict[str, list[dict[str, Any]]] = {"functions": [], "classes": []}
    if tree.root_node.type != CMAKE_ROOT:
        return out
    lines = src_bytes.decode("utf-8", errors="replace").splitlines()
    for node in walk_nodes(tree.root_node):
        record = _definition_record(node, lines)
        if record is not None:
            out["functions"].append(record)
    out["functions"].sort(key=lambda fn: (fn["line"], fn["name"]))
    return out


## @brief One CMake definition as a JSON-safe record, or None for any other node.
## @param node A tree node.
## @param lines The file's lines, for the comment block above.
## @return The record, or None.
## @version 1
## @dg_internal
def _definition_record(node: Any, lines: list[str]) -> dict[str, Any] | None:
    """A definition with no name at all — `function()`, which CMake itself rejects — is
    skipped rather than written under an empty name.

    @brief The record for one CMake definition.
    @return The record, or None.
    """
    spec = _DEFINITIONS.get(node.type)
    if spec is None:
        return None
    command_type, kind = spec
    names = _command_arguments(node, command_type)
    if not names:
        return None
    return {
        "name": names[0],
        "kind": kind,
        "cls": "",
        "line": node.start_point[0] + 1,
        "end": node.end_point[0] + 1,
        "col": node.start_point[1],
        "args": f"({' '.join(names[1:])})",
        "ret": "",
        "static": 0,
        "doc": comment_block_above(node.start_point[0], lines),
    }


## @brief The argument texts of a definition's command node, in source order.
## @param node The `function_def` or `macro_def` node.
## @param command_type The command child to read (`function_command`/`macro_command`).
## @return The argument texts: the name first, then the parameters.
## @version 1
## @dg_internal
def _command_arguments(node: Any, command_type: str) -> list[str]:
    """Only the definition's OWN command is read, not the whole subtree: the body holds
    commands with argument lists of their own, and `add_executable(${NAME} …)` inside the
    body is not a parameter of the function that contains it.

    @brief The declared name and parameters.
    @return The argument texts.
    """
    command = next((c for c in node.children if c.type == command_type), None)
    if command is None:
        return []
    arg_list = next((c for c in command.children if c.type == _ARGUMENT_LIST), None)
    if arg_list is None:
        return []
    return [node_text(arg) for arg in arg_list.children if arg.type == _ARGUMENT]
