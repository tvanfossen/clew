# SPDX-License-Identifier: MIT
"""CMake functions and macros are definitions, and a CMake tree is not a Rust tree.

1.1.0. `CMakeLists.txt` is where an embedded repository says what it builds, with what
flags, against which dependencies — and it had no rows at all, so the one file an agent
needs for "how is this target built" was invisible.

WHY `macro` AND `function` BOTH, AND WHY THEY ARE NOT THE SAME THING. CMake's `macro`
pastes its body into the caller's scope and its arguments are textual substitutions;
`function` gets its own scope and real parameters. The index records which one a
definition is (`kind`), because a reader debugging a variable that leaks into the caller
needs that distinction to be in the answer rather than inferred.

The discriminator, as in `clew/shast.py`, is a node shape and not the root type: a CMake
tree is rooted at `source_file`, which is also Rust's root. `function_def` and `macro_def`
exist in no other grammar clew routes.

@brief CMake definition harvesting, and its separation from Rust.
@version 1
"""

from __future__ import annotations

import json

import lang_parsing_substrate as lps
import pytest

from clew.cmakeast import harvest_definitions, is_cmake_tree
from clew.substrate import has_language

pytestmark = pytest.mark.skipif(
    not has_language("cmake"),
    reason="substrate has no cmake grammar; clew requires lang-parsing-substrate>=0.12.0",
)

_LISTS = b"""cmake_minimum_required(VERSION 3.20)
project(demo C)

# Register one firmware image and its map file.
#
# @version 2
function(add_firmware NAME SOURCES)
  add_executable(${NAME} ${SOURCES})
endfunction()

# Paste the common warning flags into the caller.
macro(strict_warnings TARGET)
  target_compile_options(${TARGET} PRIVATE -Wall -Werror)
endmacro()

add_firmware(blinky src/main.c)
"""


## @brief Parse one CMake source and harvest it.
## @version 1
def _harvest(src: bytes) -> dict:
    return harvest_definitions(lps.parse_tree("cmake", src), src)


def test_a_function_and_a_macro_are_both_definitions() -> None:
    """@brief Both definition forms are harvested with their spans. @version 1"""
    out = _harvest(_LISTS)

    by_name = {fn["name"]: fn for fn in out["functions"]}
    assert sorted(by_name) == ["add_firmware", "strict_warnings"]
    assert by_name["add_firmware"]["line"] == 7
    assert by_name["add_firmware"]["end"] == 9
    assert by_name["strict_warnings"]["line"] == 12


def test_a_macro_is_recorded_as_a_macro_not_a_function() -> None:
    """A `macro` body runs in the CALLER's scope. A reader chasing a variable that leaks
    needs that in the answer, so the distinction is a field and not a guess.

    @brief The `kind` field separates macro from function. @version 1
    """
    out = _harvest(_LISTS)

    kinds = {fn["name"]: fn["kind"] for fn in out["functions"]}
    assert kinds == {"add_firmware": "function", "strict_warnings": "macro"}


def test_the_declared_parameters_are_the_signature() -> None:
    """Unlike shell, CMake declares named parameters, so withholding them would be a gap
    in the harvest rather than a fact about the language.

    @brief Parameters are reported. @version 1
    """
    out = _harvest(_LISTS)

    args = {fn["name"]: fn["args"] for fn in out["functions"]}
    assert args["add_firmware"] == "(NAME SOURCES)"
    assert args["strict_warnings"] == "(TARGET)"


def test_a_definition_with_no_parameters_reports_empty_parentheses() -> None:
    """@brief No parameters is `()`, not a missing signature. @version 1"""
    out = _harvest(b"function(no_args)\nendfunction()\n")

    assert out["functions"][0]["args"] == "()"


def test_the_hash_block_above_the_definition_is_its_doc() -> None:
    """@brief The preceding `#` block documents the definition. @version 1"""
    out = _harvest(_LISTS)

    fn = next(f for f in out["functions"] if f["name"] == "add_firmware")
    assert "Register one firmware image and its map file." in fn["doc"]
    assert "@version 2" in fn["doc"]
    assert "#" not in fn["doc"]


def test_a_rust_tree_yields_no_cmake_definitions() -> None:
    """THE COLLISION, pinned: both grammars root at `source_file`.

    @brief A Rust tree harvests no CMake definitions. @version 1
    """
    src = b'fn main() { println!("hi"); }\n'
    tree = lps.parse_tree("rust", src)

    assert tree.root_node.type == "source_file", "the premise of this test"
    assert not is_cmake_tree(tree)
    assert harvest_definitions(tree, src) == {"functions": [], "classes": []}


def test_a_cmake_file_that_only_calls_commands_defines_nothing() -> None:
    """The common case — most `CMakeLists.txt` files define no function at all. The file
    is still indexed and still searchable; it simply contributes no symbols.

    @brief A command-only CMake file yields no definitions. @version 1
    """
    out = _harvest(b"project(demo C)\nadd_library(mylib src/a.c)\n")

    assert out == {"functions": [], "classes": []}


def test_the_payload_is_json_serializable() -> None:
    """@brief The payload survives a JSON round trip. @version 1"""
    out = _harvest(_LISTS)
    assert json.loads(json.dumps(out)) == out
