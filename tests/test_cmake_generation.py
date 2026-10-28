# SPDX-License-Identifier: MIT
"""THE RICHEST FACT IN A CMakeLists.txt WAS BEING DISCARDED.

mbedtls Q4 asks how a negative return becomes a human-readable string and what a contributor must
do to add one. Its weight-3 conclusion mark and three of its `set` members all cite ONE block,
`library/CMakeLists.txt:130-147`:

    add_custom_command(
        OUTPUT  ${CMAKE_CURRENT_BINARY_DIR}/error.c
        COMMAND ${PERL_EXECUTABLE} .../scripts/generate_errors.pl
                .../include/mbedtls .../scripts/data_files .../error.c
        DEPENDS .../scripts/generate_errors.pl ${error_headers}
                .../scripts/data_files/error.fmt)

`error.c` is generated, by that script, from those inputs. Every remaining failed mark on the
grid's worst cluster is in those eighteen lines.

**clew ROUTES CMake AND REPORTED THAT FILE HARVESTED.** `cmakeast` walks `function_def` and
`macro_def` only, so a file that defines no function yields nothing — and `is_cmake_tree` returns
False for it, which its own docstring defended: "a `CMakeLists.txt` that defines no function is
therefore not a 'CMake tree' by this test — correct, because there is nothing in it for this
module to harvest either way." That was true when written and this makes it false, which is the
third correct-when-written claim to age into a lie in this review.

**WHAT IS NOT CLAIMED.** `${CMAKE_CURRENT_BINARY_DIR}/error.c` is a variable reference. This
harvest does NOT resolve it — CMake variables depend on the configure step, and a resolved path
this never ran would be invention. The literal text is kept and a basename is offered beside it,
because `error.c` is what a reader and a graded mark actually name. `${error_headers}` is a glob
variable and stays exactly that: recorded, not reported as a file.

**FOUR GENERATED FILES, NOT ONE.** Parsed from the real tree: `error.c`,
`version_features.c`, `ssl_debug_helpers_generated.c`, and the `psa_crypto_driver_wrappers`
pair — with three different generators across Perl and Python. A harvest built for the one mark
would have missed three quarters of what the file says.

@brief CMake generation rules are harvested, without resolving variables.
@version 1
"""

from __future__ import annotations


from clew.cmakeast import harvest_generation, is_cmake_tree
from clew.tsnode import Parser

GEN = b"""
cmake_minimum_required(VERSION 3.10)

add_custom_command(
    OUTPUT
        ${CMAKE_CURRENT_BINARY_DIR}/error.c
    COMMAND
        ${PERL_EXECUTABLE}
            ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/generate_errors.pl
            ${CMAKE_CURRENT_SOURCE_DIR}/../include/mbedtls
    DEPENDS
        ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/generate_errors.pl
        ${error_headers}
        ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/data_files/error.fmt
)
"""

NO_COMMANDS = b"""
function(helper arg)
    message(STATUS "${arg}")
endfunction()
"""


##
# @brief Parse CMake source into a tree.
# @version 1
def _tree(src: bytes):
    return Parser("cmake").parse(src)


## @brief A command-only CMakeLists is recognised as CMake.
## @version 1
def test_a_command_only_cmakelists_is_a_cmake_tree() -> None:
    """RED BEFORE THE FIX: `is_cmake_tree` requires a `function_def` or `macro_def`, so this file
    — which is what a real `library/CMakeLists.txt` looks like — is not a CMake tree and nothing
    is offered to any harvester.

    `normal_command` is the signal, and it has to be: `source_file` is also Rust's root, so the
    root alone decides nothing. Rust trees carry no `normal_command`, verified against the real
    node-type set of the mbedtls file.
    """
    assert is_cmake_tree(_tree(GEN)), (
        "a CMakeLists.txt holding only commands must still be a CMake tree"
    )
    ## The definition-bearing case must keep working — it is the one this module shipped for.
    assert is_cmake_tree(_tree(NO_COMMANDS))


## @brief A generation rule is harvested with its output, command and inputs.
## @version 1
def test_a_custom_command_is_harvested() -> None:
    """The three keyword sections are a FLAT argument list in the grammar, so they are split on
    the keywords rather than read as structure.
    """
    rules = harvest_generation(_tree(GEN), GEN)["generated"]

    assert len(rules) == 1, rules
    rule = rules[0]
    assert rule["kind"] == "custom_command"
    assert rule["line"] == 4, f"the rule's own line, for a reader to go read it: {rule}"
    assert [o["name"] for o in rule["outputs"]] == ["error.c"], rule["outputs"]
    assert "generate_errors.pl" in [c["name"] for c in rule["command"]], rule["command"]
    assert "error.fmt" in [d["name"] for d in rule["depends"]], rule["depends"]


## @brief A variable reference is kept verbatim and never resolved.
## @version 1
def test_variables_are_recorded_not_resolved() -> None:
    """`${CMAKE_CURRENT_BINARY_DIR}/error.c` depends on the configure step this harvest never
    ran. Resolving it would publish a path that may not exist; dropping it would lose the only
    name the mark wants. So both are kept: the literal, and the basename.

    `${error_headers}` is a bare glob variable with no basename at all, and it must be recorded
    as unresolved rather than reported as a file — the `absence is not emptiness` rule applied to
    a build variable.
    """
    rule = harvest_generation(_tree(GEN), GEN)["generated"][0]

    out = rule["outputs"][0]
    assert out["literal"] == "${CMAKE_CURRENT_BINARY_DIR}/error.c", out
    assert out["name"] == "error.c", out

    glob = next(d for d in rule["depends"] if "error_headers" in d["literal"])
    assert glob["name"] == "", f"a bare variable has no filename and must not be given one: {glob}"
    assert glob["unresolved"] is True, glob


## @brief A file with no generation rules yields nothing, not an empty claim.
## @version 1
def test_a_file_with_no_rules_harvests_nothing() -> None:
    """An empty payload rather than a `generated: []` row per file, for the reason
    `_ScriptSymbolHarvester` gives about partitions: a row per file recording that a C file
    generates nothing is 40,000 rows of nothing on a large target.
    """
    assert harvest_generation(_tree(NO_COMMANDS), NO_COMMANDS) == {}


## @brief add_custom_target's DEPENDS are harvested as the aggregate they are.
## @version 1
def test_a_custom_target_is_harvested_as_a_target() -> None:
    """`add_custom_target(... DEPENDS a b c)` names no OUTPUT — it is the aggregate that forces
    the rules above it to run, and mbedtls has two. Recording it as a `custom_command` would
    claim the target is a generated FILE.
    """
    src = b"""
add_custom_target(mbedcrypto_generated_files_target
    DEPENDS
        ${CMAKE_CURRENT_BINARY_DIR}/error.c
        ${CMAKE_CURRENT_BINARY_DIR}/version_features.c
)
"""
    rules = harvest_generation(_tree(src), src)["generated"]

    assert len(rules) == 1 and rules[0]["kind"] == "custom_target", rules
    assert rules[0]["outputs"] == [], "a target produces no file of its own"
    assert [d["name"] for d in rules[0]["depends"]] == ["error.c", "version_features.c"]


## @brief The real mbedtls file yields every rule in it.
## @version 1
def test_the_real_mbedtls_cmakelists_yields_all_four_generators() -> None:
    """PARSED FROM THE FROZEN CHECKOUT, not a fixture, because the fixture is mine and the file
    is theirs. Four `add_custom_command` rules and three distinct generators across two
    languages — a harvest written for mbedtls Q4's one mark would have missed three of them.
    """
    from pathlib import Path

    repo = Path(__file__).resolve().parent.parent / "acceptance/runs/2026-10-19-n3/mbedtls/repo"
    src = (repo / "library/CMakeLists.txt").read_bytes()

    rules = harvest_generation(_tree(src), src)["generated"]
    commands = [r for r in rules if r["kind"] == "custom_command"]
    produced = {o["name"] for r in commands for o in r["outputs"]}

    assert len(commands) == 4, [r["line"] for r in commands]
    assert "error.c" in produced and "version_features.c" in produced, produced
    generators = {c["name"] for r in commands for c in r["command"] if c["name"]}
    assert "generate_errors.pl" in generators, generators
