# SPDX-License-Identifier: MIT
"""Shell functions are definitions, and a shell tree is not a JavaScript tree.

1.1.0. A repository's `.sh` files hold its deploy, release and CI logic — the code an
agent is most often asked about and the only code in the tree that had no rows at all.
`clew/shast.py` harvests them for the parse-built front end, the way `clew/jsast.py` does
for JS/TS.

WHY THE DISCRIMINATOR IS A NODE SHAPE AND NOT THE ROOT TYPE. A bash tree is rooted at
`program` — the same root as JavaScript, TypeScript and TSX, which is what `is_js_tree`
tests. Measured before this module existed: `is_js_tree(parse_tree("bash", …))` returns
**True**, and the JS definition harvester then ran over a shell script. It happened to
emit nothing, because JS spells its declaration `function_declaration` while bash spells
it `function_definition` — silence by luck, not by design.

The shape test is exact rather than lucky:

| language | definition node | `name` field |
|---|---|---|
| bash | `function_definition` | `word` |
| C / C++ | `function_definition` | absent — the name is under `declarator` |
| JavaScript | `function_declaration` | `identifier` |

So "a `function_definition` whose `name` field is a `word`" names bash and nothing else
clew routes to a grammar. Both tests below pin that, in both directions.

@brief Bash definition harvesting, and its separation from JS and C.
@version 1
"""

from __future__ import annotations

import lang_parsing_substrate as lps
import pytest

from clew.shast import harvest_definitions, is_sh_tree
from clew.substrate import has_language

pytestmark = pytest.mark.skipif(
    not has_language("bash"),
    reason="substrate has no bash grammar; clew requires lang-parsing-substrate>=0.12.0",
)

_SCRIPT = b"""#!/bin/bash
# Deploy the built artefact to one target.
#
# @version 3
# @req REQ-DDB-PIPE-012
deploy() {
  local target="$1"
  rsync -a build/ "$target"
}

# Undo the last deploy.
function rollback {
  git revert --no-edit HEAD
}

deploy "$@"
"""


## @brief Parse one shell source and harvest it.
## @version 1
def _harvest(src: bytes) -> dict:
    return harvest_definitions(lps.parse_tree("bash", src), src)


def test_both_spellings_of_a_shell_function_are_definitions() -> None:
    """`name()` and `function name` are the two forms POSIX sh and bash accept.

    @brief Both function forms are harvested, with their line spans. @version 1
    """
    out = _harvest(_SCRIPT)

    by_name = {fn["name"]: fn for fn in out["functions"]}
    assert sorted(by_name) == ["deploy", "rollback"]
    assert by_name["deploy"]["line"] == 6
    assert by_name["deploy"]["end"] == 9
    assert by_name["rollback"]["line"] == 12


def test_a_hash_comment_block_above_the_function_is_its_doc() -> None:
    """Shell has no doxygen comment, so the convention IS the `#` block immediately above,
    and the tags inside it are kept as literal text the way doxygen keeps an unknown tag.

    @brief The preceding `#` block becomes the function's doc. @version 1
    """
    out = _harvest(_SCRIPT)

    deploy = next(fn for fn in out["functions"] if fn["name"] == "deploy")
    assert "Deploy the built artefact to one target." in deploy["doc"]
    assert "@version 3" in deploy["doc"]
    assert "#" not in deploy["doc"], "comment markers must be stripped, not served"
    rollback = next(fn for fn in out["functions"] if fn["name"] == "rollback")
    assert "Undo the last deploy." in rollback["doc"]


def test_a_comment_block_separated_by_a_blank_line_is_not_the_doc() -> None:
    """@brief A detached comment belongs to nothing. @version 1"""
    out = _harvest(b"# Unrelated note.\n\nfoo() {\n  :\n}\n")

    assert out["functions"][0]["doc"] == ""


def test_shell_defines_no_classes() -> None:
    """The payload shape is shared with JS/TS, which has classes; shell has none, so the
    key must be present and empty rather than absent.

    @brief The classes list is present and empty. @version 1
    """
    assert _harvest(_SCRIPT)["classes"] == []


def test_a_javascript_tree_yields_no_shell_definitions() -> None:
    """THE COLLISION, pinned. Both trees are rooted at `program`, so this harvester is
    offered JS trees by the shared parse and must return nothing for them.

    @brief A JS tree harvests no shell functions. @version 1
    """
    src = b"function foo(a) { return a; }\nconst bar = () => 1;\n"
    tree = lps.parse_tree("javascript", src)

    assert tree.root_node.type == "program", "the premise of this test"
    assert not is_sh_tree(tree)
    assert harvest_definitions(tree, src) == {"functions": [], "classes": []}


def test_a_c_tree_yields_no_shell_definitions() -> None:
    """C spells its definition `function_definition` too — the same node name — and is
    separated only by the absence of a `word` name field.

    @brief A C tree harvests no shell functions. @version 1
    """
    src = b"int main(void) { return 0; }\n"
    tree = lps.parse_tree("c", src)

    assert "function_definition" in set(tree.kinds), "the premise of this test"
    assert not is_sh_tree(tree)
    assert harvest_definitions(tree, src) == {"functions": [], "classes": []}


def test_the_payload_is_json_serializable_and_rowid_free() -> None:
    """Every harvest payload is cached as JSON, so a node object anywhere in it is a bug
    that only shows up on the second build.

    @brief The payload survives a JSON round trip. @version 1
    """
    import json

    out = _harvest(_SCRIPT)
    assert json.loads(json.dumps(out)) == out
