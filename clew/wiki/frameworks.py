# SPDX-License-Identifier: MIT
"""Standard test structures: which indexed functions are tests, and under what names.

Owner 2026-11-15: "allow for catch2, pytest, ceedling, gcovr, standard test structures". A test is
recognised by its FRAMEWORK'S OWN SHAPE:

  * Catch2 / doctest — `TEST_CASE`, `SCENARIO`, `TEMPLATE_TEST_CASE`, `TEST_CASE_METHOD`: the
    index holds a row named after the macro whose argument list carries the test's name;
  * GoogleTest — `TEST`, `TEST_F`, `TEST_P`, `TYPED_TEST`: `Suite.Name`, filed under `Name` too
    (the JUnit-shaped gtest report names the case `Name` in class `Suite`);
  * Boost.Test — `BOOST_AUTO_TEST_CASE`, `BOOST_FIXTURE_TEST_CASE`;
  * pytest, Unity / Ceedling and every `test_*` convention — the function's own name.

A MACRO ROW counts only inside test code (a path under a test directory or named like a test
file): `SCENARIO` is a plausible name for anyone's function. A function whose name does not start
with `test` is a helper, not a test.

@brief Recognise tests by framework shape.
@version 1
"""

from __future__ import annotations

import re

## Macros whose first argument is the test's name (a string literal).
_NAMED = {
    "TEST_CASE",
    "SCENARIO",
    "TEMPLATE_TEST_CASE",
    "TEMPLATE_PRODUCT_TEST_CASE",
    "TEST_CASE_METHOD",
    "TEMPLATE_TEST_CASE_METHOD",
}
## Macros whose first two arguments are suite and case identifiers.
_SUITE = {"TEST", "TEST_F", "TEST_P", "TYPED_TEST", "TYPED_TEST_P"}
## Macros whose first argument is the case identifier.
_BARE = {"BOOST_AUTO_TEST_CASE", "BOOST_FIXTURE_TEST_CASE", "BOOST_DATA_TEST_CASE"}
_STRING = re.compile(r'"((?:[^"\\]|\\.)*)"')
_IDENTS = re.compile(r"[A-Za-z_]\w*")
_TEST_PATH = re.compile(
    r"(^|/)(tests?|spec|specs|__tests__)(/|$)|(^|/)test_[^/]*$|_test\.\w+$", re.I
)


## @brief A function's test identity, if it is a test.
## @param name The indexed name.
## @param args Its argument string (`argsstring`).
## @param path Its repo-relative file.
## @return (display name, names results are filed under), or None for a non-test.
## @version 1
## @req REQ-DDB-WIKI-017
def recognise_test(name: str, args: str, path: str) -> tuple[str, tuple[str, ...]] | None:
    """@brief Recognise. @return Identity or None."""
    reader = _MACROS.get(name)
    if reader is not None:
        return reader(args or "") if _TEST_PATH.search(path or "") else None
    return (name, (name,)) if name.lower().startswith("test") else None


## @brief A named-macro test: its first string literal.
## @param args The argument string.
## @return Identity or None.
## @version 1
## @dg_internal
def _named(args: str) -> tuple[str, tuple[str, ...]] | None:
    """@brief Catch2 / doctest. @return Identity."""
    found = _STRING.search(args)
    return (found.group(1), (found.group(1),)) if found else None


## @brief A suite-and-case macro test: `Suite.Name`, filed under both spellings.
## @param args The argument string.
## @return Identity or None.
## @version 1
## @dg_internal
def _suite(args: str) -> tuple[str, tuple[str, ...]] | None:
    """@brief GoogleTest. @return Identity."""
    idents = _IDENTS.findall(args)
    if len(idents) < 2:
        return None
    return (f"{idents[0]}.{idents[1]}", (idents[1], f"{idents[0]}.{idents[1]}"))


## @brief A bare-identifier macro test.
## @param args The argument string.
## @return Identity or None.
## @version 1
## @dg_internal
def _bare(args: str) -> tuple[str, tuple[str, ...]] | None:
    """@brief Boost.Test. @return Identity."""
    idents = _IDENTS.findall(args)
    return (idents[0], (idents[0],)) if idents else None


_MACROS = {
    **dict.fromkeys(_NAMED, _named),
    **dict.fromkeys(_SUITE, _suite),
    **dict.fromkeys(_BARE, _bare),
}
