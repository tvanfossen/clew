# SPDX-License-Identifier: MIT
"""A symbol defined in a generated file carries the rule that generates it (T4; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mbedtls F4), confirmed: `generated_by` was present on
`dossier("library/error.c")` and ABSENT on `dossier("mbedtls_strerror")`, the function a reader
actually asks about. mbedtls Q4's rubric turns on knowing that `error.c` is generated, because the
file carries no banner saying so, and a reader who arrives by the function's name had no route to
that fact short of asking for the file.

The function's dossier now carries the same `GenerationRule` the file's does, looked up from the
file `file` names (the body's, since T2). ABSENT when the file is not generated.

@brief Tests build provenance on symbol dossiers.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.query.subject import dossier

_CMAKE = """\
add_custom_command(
    OUTPUT ${CMAKE_CURRENT_BINARY_DIR}/error.c
    COMMAND perl ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/generate_errors.pl
    DEPENDS ${CMAKE_CURRENT_SOURCE_DIR}/../scripts/generate_errors.pl
)
add_library(demo ${CMAKE_CURRENT_BINARY_DIR}/error.c handwritten.c)
"""
_ERROR_C = '/** @brief Describe an error. */\nconst char *demo_strerror(int code)\n{\n    return code ? "bad" : "ok";\n}\n'
_HAND_C = "/** @brief Written by hand. */\nint demo_hand(void)\n{\n    return 0;\n}\n"


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """@brief Index the CMake-generated demo. @return (db, repo)."""
    base = tmp_path_factory.mktemp("t4")
    repo = base / "repo"
    (repo / "library").mkdir(parents=True)
    (repo / "scripts").mkdir()
    (repo / "library/CMakeLists.txt").write_text(_CMAKE)
    (repo / "library/error.c").write_text(_ERROR_C)
    (repo / "library/handwritten.c").write_text(_HAND_C)
    (repo / "scripts/generate_errors.pl").write_text("print 1;\n")
    db = base / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db, repo


def test_a_function_in_a_generated_file_names_the_rule(built) -> None:
    """@brief The function carries the same rule its file does."""
    db, repo = built
    fn = dossier(db, "demo_strerror", repo_root=repo).function
    whole = dossier(db, "library/error.c", kind="file", repo_root=repo).file
    assert whole.generated_by is not None
    assert fn.generated_by == whole.generated_by
    assert fn.generated_by.source_file == "library/CMakeLists.txt"


def test_a_hand_written_function_has_no_generated_by(built) -> None:
    """@brief Absent, not an empty rule."""
    db, repo = built
    assert dossier(db, "demo_hand", repo_root=repo).function.generated_by is None
