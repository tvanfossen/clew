# SPDX-License-Identifier: MIT
"""tree-sitter parsing through lang-parsing-substrate, in py-tree-sitter's shape.

WHY THIS MODULE EXISTS. Every harvester walks py-tree-sitter `Node`s, which meant one
Python grammar package per language, each pinned to py-tree-sitter's ABI. That pin held
the whole stack at tree-sitter 0.23. The substrate parses in Rust, with the grammars
knots, moldy and aurora-lint share, and its `parse_tree` returns a tree whose
`root_node` answers the slice of py-tree-sitter's `Node` API clew uses. A harvester
cannot tell the difference, so moving a language onto the substrate is a routing
change in `harvest.py`, not a rewrite of every walker.

THE SURFACE IS EXACTLY WHAT CLEW READS. Measured by grep over `clew/`: `type`,
`children`, `named_children`, `child_by_field_name`, `children_by_field_name`,
`parent`, `prev_named_sibling`, `start_byte`/`end_byte`, `start_point`/`end_point`
(indexed `[0]`, so tuples suffice), `text`, `id`, `is_named`, `is_missing`,
`is_error`, `has_error`; and on the tree, `root_node`. Nothing uses a `TreeCursor`.
A walker that reaches for anything else fails loudly with AttributeError, which is
the outcome we want: it marks the next attribute the substrate must add, rather than
a silent difference.

THE NODE IS NATIVE. A first version wrapped the substrate's flat columns in a Python
`Node` class. Its output was identical, but the parse-and-harvest stage ran 1.7-2.3x
slower than py-tree-sitter, all of it Python object overhead per node. The node class
now lives in the substrate (Rust), and this module only selects the grammar.

@brief Substrate-backed parser with py-tree-sitter's Parser/Tree/Node shape.
@version 1
"""

from __future__ import annotations

from typing import Any

import lang_parsing_substrate as _lps


## @brief A parser for one substrate language key, shaped like py-tree-sitter's Parser.
## @version 1
## @dg_internal
class Parser:
    """@brief `Parser(key).parse(source_bytes)` returns a tree with a `root_node`."""

    __slots__ = ("language_key",)

    ## @brief Bind the parser to one substrate language key.
    ## @param language_key A key `lang_parsing_substrate.parse_tree` accepts.
    ## @version 1
    ## @dg_internal
    def __init__(self, language_key: str) -> None:
        self.language_key = language_key

    ## @brief Parse UTF-8 source bytes.
    ## @param source File contents as bytes.
    ## @return The substrate's FlatTree, whose `root_node` walks like py-tree-sitter's.
    ## @version 1
    ## @dg_internal
    def parse(self, source: bytes) -> Any:
        """@brief Parse through the substrate."""
        return _lps.parse_tree(self.language_key, bytes(source))
