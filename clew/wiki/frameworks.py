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
@version 3
"""

from __future__ import annotations

import re
from typing import Any

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
## v2 (round 4): a plain `test*` name is a test only in test code, as the macros already were.
## v3 (2.0.0, P4): delegates to `TestRecognizer` with no index (path regex only).
## @version 3
## @req REQ-DDB-WIKI-017
def recognise_test(name: str, args: str, path: str) -> tuple[str, tuple[str, ...]] | None:
    """THE PATH-ONLY FORM, for a caller with no index. Against an index, use
    `TestRecognizer.for_conn`, which reads test code from `test_scope` and the declared shapes.

    @brief Recognise. @return Identity or None.
    """
    return TestRecognizer(None, _MACROS, _FUNCTION_PREFIXES)(name, args, path)


## @brief A named-macro test: its first string literal.
## @param args The argument string.
## @return Identity or None.
## @version 1
## @utility
def _named(args: str) -> tuple[str, tuple[str, ...]] | None:
    """@brief Catch2 / doctest. @return Identity."""
    found = _STRING.search(args)
    return (found.group(1), (found.group(1),)) if found else None


## @brief A suite-and-case macro test: `Suite.Name`, filed under both spellings.
## @param args The argument string.
## @return Identity or None.
## @version 1
## @utility
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
## @utility
def _bare(args: str) -> tuple[str, tuple[str, ...]] | None:
    """@brief Boost.Test. @return Identity."""
    idents = _IDENTS.findall(args)
    return (idents[0], (idents[0],)) if idents else None


## @brief A Catch2 scenario: its string, filed also as "Scenario: <string>", Catch2's report name.
## @param args The argument string.
## @return Identity or None.
## @version 1
## @utility
def _scenario(args: str) -> tuple[str, tuple[str, ...]] | None:
    """ROUND 4, found on sassafras-class: Catch2's JUnit reporter and ctest's discovered tests
    both name a SCENARIO "Scenario: <string>"; without that form its result was never found.

    @brief Catch2 scenario.
    @return Identity.
    """
    named = _named(args)
    return (named[0], (named[0], f"Scenario: {named[0]}")) if named else None


_MACROS = {
    **dict.fromkeys(_NAMED, _named),
    **dict.fromkeys(_SUITE, _suite),
    **dict.fromkeys(_BARE, _bare),
    "SCENARIO": _scenario,
}

## The reader for each declarable macro shape (`tests.macros`).
_SHAPE_READERS = {"named": _named, "suite": _suite, "bare": _bare}
## The built-in plain-test name prefixes (`tests.function_prefixes` adds to them).
_FUNCTION_PREFIXES = ("test",)
## The `build_meta` key the build records the declared test shapes under (`scope.` section).
TEST_SHAPES_KEY = "scope.test_shapes"


## @brief Test recognition for one index: its test code and its declared test shapes.
## @version 1
class TestRecognizer:
    """P4 (2.0.0; W1, W2, C6 of the hard-coded-assumptions review).

    W1: TEST CODE IS `test_scope`, which already honours a declared `tests.paths`. `recognise_test`
    required its own `_TEST_PATH` regex on top, so an LLVM-shaped `unittests/ADT/FooTest.cpp`,
    in `test_scope`, failed the regex and its GoogleTest cases were not tests. The regex is now
    only the fallback for an index without the table.

    C6 / W2: the macro sets and the `test` prefix were closed. A repository declares more under
    `tests.macros` (`named` / `suite` / `bare`) and `tests.function_prefixes`, recorded by the
    build as `scope.test_shapes`; both ADD to the built-ins, as `blocking:` does.

    @brief Per-index test recogniser.
    @version 1
    """

    __test__ = False  # not a pytest class, whatever its name says

    ## @brief Hold the test files and the shapes.
    ## @param test_files Repo-relative test files, or None to fall back to the path regex.
    ## @param macros Macro name → reader.
    ## @param prefixes Plain-test name prefixes, lower-cased.
    ## @version 1
    ## @utility
    def __init__(
        self, test_files: frozenset[str] | None, macros: dict, prefixes: tuple[str, ...]
    ) -> None:
        self.test_files = test_files
        self.macros = macros
        self.prefixes = prefixes

    ## @brief The recogniser for an open index, built once per connection.
    ## @param conn Open connection.
    ## @return The recogniser.
    ## @version 1
    ## @req REQ-DDB-WIKI-017
    @classmethod
    def for_conn(cls, conn: Any) -> TestRecognizer:
        """IDENTITY-CHECKED CACHE: a connection supports no weak reference, and a wiki build asks
        on every step of a caller walk, so the last few are held and matched by identity.

        @brief Build or reuse.
        @return The recogniser.
        """
        for held, recogniser in _HELD:
            if held is conn:
                return recogniser
        made = cls(_test_files(conn), *_declared_shapes(conn))
        _HELD.insert(0, (conn, made))
        del _HELD[4:]
        return made

    ## @brief A function's test identity, if it is a test.
    ## @param name The indexed name.
    ## @param args Its argument string.
    ## @param path Its repo-relative file.
    ## @return (display name, names results are filed under), or None.
    ## @version 1
    ## @req REQ-DDB-WIKI-017
    def __call__(self, name: str, args: str, path: str) -> tuple[str, tuple[str, ...]] | None:
        """@brief Recognise. @return Identity or None."""
        in_test = (
            (path in self.test_files)
            if self.test_files is not None
            else bool(_TEST_PATH.search(path or ""))
        )
        if not in_test:
            return None
        reader = self.macros.get(name)
        if reader is not None:
            return reader(args or "")
        return (name, (name,)) if name.lower().startswith(self.prefixes) else None


## Recently built recognisers, most recent first: (connection, recogniser).
_HELD: list[tuple[Any, TestRecognizer]] = []


## @brief The index's test files, or None when it has no `test_scope`.
## @param conn Open connection.
## @return Paths or None.
## @version 1
## @utility
def _test_files(conn: Any) -> frozenset[str] | None:
    """@brief Read test_scope. @return Paths or None."""
    present = conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'test_scope'").fetchone()
    if not present:
        return None
    return frozenset(
        str(n)
        for (n,) in conn.execute(
            "SELECT p.name FROM test_scope t JOIN path p ON p.rowid = t.path_rowid"
        )
    )


## @brief The built-in shapes plus the declared ones the build recorded.
## @param conn Open connection.
## @return (macros, prefixes).
## @version 1
## @utility
def _declared_shapes(conn: Any) -> tuple[dict, tuple[str, ...]]:
    """@brief Merge declared shapes. @return Macros and prefixes."""
    import json

    macros = dict(_MACROS)
    prefixes = list(_FUNCTION_PREFIXES)
    row = None
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'build_meta'").fetchone():
        row = conn.execute(
            "SELECT value FROM build_meta WHERE key = ?", (TEST_SHAPES_KEY,)
        ).fetchone()
    shapes = json.loads(row[0]) if row and row[0] else {}
    for shape, names in (shapes.get("macros") or {}).items():
        macros.update(dict.fromkeys(names, _SHAPE_READERS[shape]))
    prefixes += [str(p).lower() for p in shapes.get("function_prefixes") or ()]
    return macros, tuple(dict.fromkeys(prefixes))
