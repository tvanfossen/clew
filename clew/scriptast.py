# SPDX-License-Identifier: MIT
"""What the shell and CMake front ends share: a tree walk, node text, and the `#` doc block.

Two front ends arrived together in 1.1.0 — `clew/shast.py` for bash and
`clew/cmakeast.py` for CMake — and both need the same three primitives. Shell and CMake
also share a documentation convention, because neither language has a comment form
doxygen recognises: THE DOC IS THE `#` BLOCK IMMEDIATELY ABOVE THE DEFINITION. Stating
that rule once is the point of this module; a second copy of it would let the two
languages drift into disagreeing about what documents a definition.

`clew/jsast.py` keeps its own copies of the walk and the text helper. It is shipped code
with a different doc convention (JSDoc, read through the gate's own lookup so the index
and the gate cannot disagree), and folding it in here would mean editing a front end this
release does not otherwise touch.

@brief Shared AST primitives for the script front ends.
@version 1
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


## @brief Every node under a root, depth first, including the root.
## @param root The node to walk from.
## @return An iterator over the root and its descendants.
## @version 1
## @dg_internal
def walk_nodes(root: Any) -> Iterator[Any]:
    """Iterative rather than recursive: a generated or vendored file can nest deeply
    enough to exhaust the interpreter's stack, and a parser front end must not be the
    thing that takes a build down.

    @brief Depth-first node walk.
    """
    stack = [root]
    while stack:
        node = stack.pop()
        stack.extend(node.children)
        yield node


## @brief Decoded text of a node, or "" when there is none.
## @param node A tree node, or None.
## @return The node's UTF-8 text, replacing undecodable bytes.
## @version 1
## @dg_internal
def node_text(node: Any) -> str:
    """`errors="replace"` because the substrate hands back the file's real bytes and a
    source file is not required to be valid UTF-8.

    @brief Node text.
    """
    return node.text.decode("utf-8", errors="replace") if node is not None and node.text else ""


## @brief The `#` comment block immediately above a line, with its markers stripped.
## @param line_index 0-based index of the definition's first line.
## @param lines The file's lines.
## @return The block's text, or "" when the line above is not a comment.
## @version 1
## @req REQ-DDB-PIPE-012
def comment_block_above(line_index: int, lines: list[str]) -> str:
    """THE SHARED RULE. Immediately above, with no blank line between — a detached comment
    documents nothing, which is what every other front end here already enforces for its
    own comment form.

    A shebang is not documentation: it addresses the kernel, not a reader, so a block that
    reaches one stops there. That matters for the common shape of a script whose first
    line is `#!/bin/bash` followed by a title comment: the title documents the FILE, and
    attributing it to whatever function happens to be defined first would be wrong.

    @brief The preceding comment block, markers stripped.
    @return The block text.
    """
    collected: list[str] = []
    index = line_index - 1
    while index >= 0:
        stripped = lines[index].strip()
        if not stripped.startswith("#") or stripped.startswith("#!"):
            break
        collected.append(stripped.lstrip("#").strip())
        index -= 1
    return "\n".join(reversed(collected)).strip()
