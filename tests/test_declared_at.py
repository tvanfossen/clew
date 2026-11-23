# SPDX-License-Identifier: MIT
"""A function's `file` is where its BODY is, and `declared_at` names where it is declared (T2;
2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW, two findings with one cause, both confirmed:

- entropic F1: `pattern_matches` reported `permission_manager.h:101-125`, a 90-line header. The
  file came from the DECLARATION (`memberdef.file_id`) and the lines from the `.cpp` body
  (`bodystart`), so the location named a range that does not exist in that file.
- mbedtls F2: `mbedtls_ct_memcmp` carried only `library/constant_time.c`, and nothing said its
  prototype lives in `constant_time_internal.h`, the header a caller includes.

`file` is now the body's file wherever a body is known, so `file:line_start` is always a real
place. The declaration is served beside it as `declared_at`, and is ABSENT when the function is
declared only where it is defined.

@brief Tests the definition file and the declaration sites on a function dossier.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.query.subject import dossier

_FILES = {
    "include/pm.h": (
        "#pragma once\n"
        "/** @brief Permissions. */\n"
        "class PermissionManager {\n"
        "public:\n"
        "    /** @brief Match a pattern. */\n"
        "    bool pattern_matches(int pattern) const;\n"
        "};\n"
    ),
    "src/pm.cpp": (
        '#include "pm.h"\n'
        "\n"
        "bool PermissionManager::pattern_matches(int pattern) const {\n"
        "    int folded = pattern * 2;\n"
        "    return folded > 3;\n"
        "}\n"
    ),
    "include/ct.h": (
        "#pragma once\n"
        "/** @brief Constant-time compare. */\n"
        "int ct_memcmp(const void *a, const void *b, unsigned n);\n"
    ),
    "library/ct.c": (
        '#include "ct.h"\n'
        "\n"
        "int ct_memcmp(const void *a, const void *b, unsigned n)\n"
        "{\n"
        "    unsigned diff = 0;\n"
        "    (void) a; (void) b; (void) n;\n"
        "    return (int) diff;\n"
        "}\n"
        "\n"
        "/** @brief Only here. */\n"
        "static int local_only(void) { return 0; }\n"
    ),
}


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """@brief Index the header/source pairs. @return (db, repo)."""
    base = tmp_path_factory.mktemp("t2")
    repo = base / "repo"
    for rel, text in _FILES.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text, encoding="utf-8")
    db = base / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db, repo


def _function(built, name: str):
    """@brief The function section of a dossier. @return Dossier."""
    db, repo = built
    d = dossier(db, name, kind="function", repo_root=repo)
    assert d is not None and d.function is not None, name
    return d.function


def test_an_out_of_line_member_is_located_in_its_cpp(built) -> None:
    """@brief file:line_start is the .cpp body; the header declaration is `declared_at`."""
    f = _function(built, "pattern_matches")
    assert (f.file, f.line_start) == ("src/pm.cpp", 3)
    assert [(d.file, d.line) for d in f.declared_at] == [("include/pm.h", 6)]


def test_a_c_function_names_the_header_that_declares_it(built) -> None:
    """@brief The definition is the .c; the prototype's header is `declared_at`."""
    f = _function(built, "ct_memcmp")
    assert f.file == "library/ct.c"
    assert [(d.file, d.line) for d in f.declared_at] == [("include/ct.h", 3)]


def test_a_function_declared_only_where_it_is_defined_has_no_declared_at(built) -> None:
    """@brief Absent, not a list holding the definition again."""
    assert _function(built, "local_only").declared_at == []
