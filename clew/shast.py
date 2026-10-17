# SPDX-License-Identifier: MIT
"""The shell dialect: function definitions for the parse-built front end.

A repository's `.sh` files hold its deploy, release, bootstrap and CI logic — frequently
the code an agent is asked about first, and until 1.1.0 the only code in an indexed tree
with no rows at all. Doxygen does not read shell, so nothing produced their `memberdef`
rows; `clew/synth.py` writes them from this harvest, exactly as it does for JS/TS.

WHAT COUNTS AS A DEFINITION. Both spellings bash accepts — `name() { … }` and
`function name { … }` — and nothing else. A shell "function" has no parameter list to
report (arguments arrive as `$1`, `$@`), so `args` is empty and that is the truth about
the language rather than a gap in the harvest.

THE DOC CONVENTION IS THE `#` BLOCK IMMEDIATELY ABOVE, because shell has no comment form
doxygen would recognise. A block separated by a blank line documents nothing, the same
rule every other front end here applies. Tags inside it (`@version`, `@req`) are kept as
literal text, which is what doxygen does with a tag it does not define.

WHY THE LANGUAGE TEST IS A NODE SHAPE, NOT THE ROOT TYPE. A bash tree is rooted at
`program` — the same root as JavaScript, TypeScript and TSX. `is_js_tree` tests exactly
that, so it answers True for a shell script, and before this module existed the JS
definition harvester really did run over `.sh` trees; it emitted nothing only because JS
spells its declaration `function_declaration` where bash spells it `function_definition`.
Silence by luck. The discriminator here is exact instead:

| language | definition node | `name` field |
|---|---|---|
| bash | `function_definition` | `word` |
| C / C++ | `function_definition` | absent — the name is under `declarator` |
| JavaScript | `function_declaration` | `identifier` |

@brief Bash function definitions over substrate trees.
@version 1
"""

from __future__ import annotations

from typing import Any

from .scriptast import comment_block_above, node_text, walk_nodes

## Bash shares this root with javascript, typescript and tsx — see the module docstring.
## It is a cheap pre-filter, never the discriminator.
SH_ROOT = "program"

## The one definition node, and the field whose `word` value separates it from C's node of
## the same name.
_DEFINITION = "function_definition"
_NAME_FIELD = "name"
_NAME_TYPE = "word"


## @brief Whether a tree holds shell definitions this module can harvest.
## @param tree A parsed tree.
## @return True for a `program`-rooted tree containing a bash `function_definition`.
## @version 1
## @dg_internal
def is_sh_tree(tree: Any) -> bool:
    """A JS tree is also `program`-rooted, so the root alone decides nothing: the answer
    is whether a definition node of bash's shape is present. A shell script that defines
    no function is therefore not a "shell tree" by this test — correct, because there is
    nothing in it for this module to harvest either way.

    @brief Bash-shaped definition present.
    """
    if tree.root_node.type != SH_ROOT:
        return False
    return any(_definition_name(node) for node in walk_nodes(tree.root_node))


## @brief The name of a bash function definition node, or "" for any other node.
## @param node A tree node.
## @return The function's name, or "".
## @version 1
## @dg_internal
def _definition_name(node: Any) -> str:
    """THE DISCRIMINATOR. C's `function_definition` has no `name` field at all (its name
    lives under `declarator`), so the field test alone separates the two grammars; the
    `word` type check is what keeps a future grammar reusing the same node name from
    being read as shell.

    @brief Bash definition name, or empty.
    """
    if node.type != _DEFINITION:
        return ""
    name = node.child_by_field_name(_NAME_FIELD)
    if name is None or name.type != _NAME_TYPE:
        return ""
    return node_text(name)


## @brief Harvest one shell file's function definitions.
## @param tree The parsed tree.
## @param src_bytes The file's bytes.
## @return The definitions payload, in `clew/synth.py`'s shape.
## @version 1
## @req REQ-DDB-PIPE-012
def harvest_definitions(tree: Any, src_bytes: bytes) -> dict[str, list[dict[str, Any]]]:
    """Positions are 1-based lines and 0-based columns, as doxygen writes them, and the
    payload is rowid-free JSON so it caches per file content like every other stage.

    `classes` is present and empty: shell has no class-like construct, and the shape is
    shared with the JS/TS payload the same writer consumes.

    @brief Harvest shell definitions.
    @return The definitions payload.
    """
    out: dict[str, list[dict[str, Any]]] = {"functions": [], "classes": []}
    if tree.root_node.type != SH_ROOT:
        return out
    lines = src_bytes.decode("utf-8", errors="replace").splitlines()
    for node in walk_nodes(tree.root_node):
        name = _definition_name(node)
        if name:
            out["functions"].append(_function_record(node, name, lines))
    out["functions"].sort(key=lambda fn: (fn["line"], fn["name"]))
    return out


## @brief One shell function as a JSON-safe record.
## @param node The `function_definition` node.
## @param name The function's name.
## @param lines The file's lines, for the comment block above.
## @return The record.
## @version 1
## @dg_internal
def _function_record(node: Any, name: str, lines: list[str]) -> dict[str, Any]:
    """`args` is empty because the language has no parameter list — arguments arrive as
    `$1`/`$@` — and `ret` for the same reason. Reporting an invented signature would put a
    claim in the index that the source does not make.

    @brief The record for one shell function.
    """
    return {
        "name": name,
        "cls": "",
        "line": node.start_point[0] + 1,
        "end": node.end_point[0] + 1,
        "col": node.start_point[1],
        "args": "",
        "ret": "",
        "static": 0,
        "doc": comment_block_above(node.start_point[0], lines),
    }
