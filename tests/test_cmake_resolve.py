# SPDX-License-Identifier: MIT
"""CMake variables in generation rules expanded where the build file alone settles them (2.1).

FOUND in the 2.0.0 grid (mbedtls Q4 −22.7 points): `library/CMakeLists.txt` builds `error.c` with
`${CMAKE_CURRENT_SOURCE_DIR}/../scripts/generate_errors.pl` and `.../data_files/error.fmt`, stored
only as written, so nothing joined them to the indexed `scripts/generate_errors.pl`. Expanded:
`CMAKE_CURRENT_SOURCE_DIR` / `CMAKE_CURRENT_LIST_DIR` (the file's own directory), `CMAKE_SOURCE_DIR`
/ `PROJECT_SOURCE_DIR` (the root, when its CMakeLists.txt is there), and a literal `set()` /
`file(GLOB)` variable in the same file. NEVER guessed: `CMAKE_CURRENT_BINARY_DIR`, a found program,
anything left unexpanded or escaping the tree resolves to "".

@brief Tests CMake argument resolution.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.cmakeast import resolve_argument


def test_the_files_own_directory_and_the_root_expand() -> None:
    """@brief Source-dir variables expand; the path is normalised inside the tree."""
    assert (
        resolve_argument("${CMAKE_CURRENT_SOURCE_DIR}/../scripts/gen.pl", "library", {}, True)
        == "scripts/gen.pl"
    )
    assert resolve_argument("${CMAKE_CURRENT_LIST_DIR}/gen.py", "tools", {}, True) == "tools/gen.py"
    assert resolve_argument("${CMAKE_SOURCE_DIR}/include/a.h", "library", {}, True) == "include/a.h"
    assert resolve_argument("${PROJECT_SOURCE_DIR}/x.fmt", "", {}, True) == "x.fmt"


def test_a_variable_set_in_the_file_expands() -> None:
    """@brief `set()` / `file(GLOB)` values, one level of nesting."""
    variables = {"hdrs": "${CMAKE_CURRENT_SOURCE_DIR}/../include/*.h", "GEN": "gen.pl"}
    assert resolve_argument("${hdrs}", "library", variables, True) == "include/*.h"
    assert (
        resolve_argument("${CMAKE_CURRENT_SOURCE_DIR}/${GEN}", "scripts", variables, True)
        == "scripts/gen.pl"
    )


def test_what_the_build_file_does_not_settle_stays_unresolved() -> None:
    """@brief The binary dir, a found program, an unknown variable, a path out of the tree: ""."""
    assert resolve_argument("${CMAKE_CURRENT_BINARY_DIR}/error.c", "library", {}, True) == ""
    assert resolve_argument("${PERL_EXECUTABLE}", "library", {}, True) == ""
    assert (
        resolve_argument("${CMAKE_CURRENT_SOURCE_DIR}/../../outside.pl", "library", {}, True) == ""
    )
    assert resolve_argument("${CMAKE_SOURCE_DIR}/a.h", "library", {}, False) == "", (
        "no root CMakeLists"
    )


def test_an_indexed_build_records_the_resolved_path(tmp_path: Path) -> None:
    """@brief `generated_files.arg_resolved`, beside the literal as written."""
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    (repo / "library").mkdir(parents=True)
    (repo / "scripts" / "data").mkdir(parents=True)
    (repo / "include").mkdir()
    (repo / "CMakeLists.txt").write_text("project(demo C)\nadd_subdirectory(library)\n")
    (repo / "library" / "CMakeLists.txt").write_text(
        "file(GLOB hdrs ${CMAKE_CURRENT_SOURCE_DIR}/../include/*.h)\n"
        "add_custom_command(\n  OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/error.c\n"
        "  COMMAND ${PERL_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/gen.pl\n"
        "  DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/data/error.fmt ${hdrs}\n)\n"
    )
    (repo / "scripts" / "gen.pl").write_text("print 1;\n")
    (repo / "scripts" / "data" / "error.fmt").write_text("x\n")
    (repo / "include" / "a.h").write_text("int a(void);\n")
    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    rows = dict(
        sqlite3.connect(db)
        .execute(
            "SELECT arg_literal, arg_resolved FROM generated_files WHERE output_name = 'error.c'"
        )
        .fetchall()
    )
    assert rows["${CMAKE_CURRENT_SOURCE_DIR}/../scripts/gen.pl"] == "scripts/gen.pl"
    assert rows["${CMAKE_CURRENT_SOURCE_DIR}/../scripts/data/error.fmt"] == "scripts/data/error.fmt"
    assert rows["${hdrs}"] == "include/*.h"
    assert rows["${PERL_EXECUTABLE}"] == ""


def test_only_an_expanded_variable_resolves() -> None:
    """FOUND MEASURING mbedtls: 67 of 94 "resolved" values were command words (`sed`, `-i.bak`,
    `ctest`) passed through because they held no variable. Only an expanded variable resolves;
    a plain literal already says all it can.

    @brief Plain words do not resolve.
    """
    for word in ("sed", "-i.bak", "ctest", "scripts/gen.pl"):
        assert resolve_argument(word, "library", {}, True) == "", word


def test_a_quoted_argument_resolves_without_its_quotes() -> None:
    """@brief FOUND MEASURING mbedtls: `"./framework/x.py"` kept its quotes as part of the path."""
    assert (
        resolve_argument('"${CMAKE_CURRENT_SOURCE_DIR}/gen.py"', "tests", {}, True)
        == "tests/gen.py"
    )
    assert resolve_argument('"${CMAKE_SOURCE_DIR}/./x.py"', "tests", {}, True) == "x.py"


def test_a_quoted_set_value_expands_without_its_quotes() -> None:
    """@brief FOUND MEASURING mbedtls: `set(x "${CMAKE_CURRENT_SOURCE_DIR}/gen.sh")` kept its quotes."""
    from tests.test_cmake_generation import _tree

    from clew.cmakeast import _variables

    tree = _tree(b'set(gen "${CMAKE_CURRENT_SOURCE_DIR}/gen.sh")\nset(empty "")\n')
    variables = _variables(tree.root_node)
    assert variables["gen"] == "${CMAKE_CURRENT_SOURCE_DIR}/gen.sh"
    assert resolve_argument('"${gen}"', "programs/test", variables, True) == "programs/test/gen.sh"
    assert resolve_argument("${empty}", "programs/test", variables, True) == ""
