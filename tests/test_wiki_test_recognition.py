# SPDX-License-Identifier: MIT
"""The wiki recognises tests where the repository declares them, by the shapes it declares (P4;
2.0.0: W1, W2, C6 of the hard-coded-assumptions review).

W1 (CONFIRMED): `frameworks.recognise_test` required its own path regex, `_TEST_PATH`, on top of
`test_scope`, which already honours a declared `tests.paths`. An LLVM-shaped
`unittests/ADT/FooTest.cpp` is in `test_scope` (declared `unittests/**`) and failed the regex (no
`tests?` segment, no `_test.` suffix), so its GoogleTest cases were not tests on the site.
`test_scope` is now the answer; the regex is only the fallback for an index without the table.

C6 / W2 (CONFIRMED): the framework macro sets and the `test` name prefix were closed. A
repository declares more under `tests.macros` (`named`, `suite`, `bare`) and
`tests.function_prefixes`; both ADD to the built-ins, as `blocking:` does.

@brief Tests declared test paths and shapes in the wiki's test recognition.
@version 1
"""

from __future__ import annotations


import pytest

from clew.cli import _build_argparser, _run_pipeline
from clew.wiki.frameworks import TestRecognizer

_FOO = """\
#include "gtest/gtest.h"

TEST(FooSuite, Works) {
    EXPECT_EQ(1, 1);
}

MY_CHECK_CASE(Grows) {
    EXPECT_EQ(2, 2);
}

void spec_handles_empty() {
}

void helper() {
}
"""
_DECL = """\
tests:
  paths:
    - "unittests/**"
  macros:
    bare: [MY_CHECK_CASE]
  function_prefixes: [spec_]
"""


@pytest.fixture(scope="module")
def recognise(tmp_path_factory: pytest.TempPathFactory):
    """@brief Index an LLVM-shaped tree with a declaration. @return The recogniser."""
    import sqlite3

    base = tmp_path_factory.mktemp("w1")
    repo = base / "repo"
    (repo / "unittests/ADT").mkdir(parents=True)
    (repo / "unittests/ADT/FooTest.cpp").write_text(_FOO)
    (repo / "lib").mkdir()
    (repo / "lib/test_like.c").write_text("int test_not_in_test_code(void) { return 0; }\n")
    (repo / ".clew.yaml").write_text(_DECL)
    db = base / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return TestRecognizer.for_conn(sqlite3.connect(db))


def test_a_declared_test_path_is_test_code(recognise) -> None:
    """@brief W1: a GoogleTest case in unittests/ADT/FooTest.cpp is a test."""
    assert recognise("TEST", "(FooSuite, Works)", "unittests/ADT/FooTest.cpp") == (
        "FooSuite.Works",
        ("Works", "FooSuite.Works"),
    )


def test_a_declared_macro_and_prefix_are_tests(recognise) -> None:
    """@brief C6 and W2: declared shapes add to the built-ins."""
    assert recognise("MY_CHECK_CASE", "(Grows)", "unittests/ADT/FooTest.cpp") == (
        "Grows",
        ("Grows",),
    )
    assert recognise("spec_handles_empty", "()", "unittests/ADT/FooTest.cpp") == (
        "spec_handles_empty",
        ("spec_handles_empty",),
    )


def test_a_helper_and_product_code_are_not_tests(recognise) -> None:
    """@brief A helper in test code, and a `test_` name outside it, are not tests."""
    assert recognise("helper", "()", "unittests/ADT/FooTest.cpp") is None
    assert recognise("test_not_in_test_code", "(void)", "lib/test_like.c") is None
