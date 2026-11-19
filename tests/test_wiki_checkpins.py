# SPDX-License-Identifier: MIT
"""A test's checks, pinned by syntax tree to the function each one observes (round 5, P5.5).

OWNER (round 5): checks are pinned by syntax tree — direct, via a variable, or not attributed. A
check observes a function DIRECTLY when the function's call is inside the assertion
(`assert save(1) == 1`), VIA A VARIABLE when the assertion reads a name assigned from that call
earlier in the body (`r = save(1)` … `assert r == 1`), and is NOT ATTRIBUTED otherwise — said, not
guessed. The candidates are the functions the test calls, from the index.

Read by a parser, never by regex over lines: `assert r == 1` mentions no function, and only the
assignment's tree says which call produced `r`.

@brief Tests check pinning for Python and C/C++ test bodies.
@version 1
"""

from __future__ import annotations

from clew.wiki.checkpins import pin_checks

_PY = """\
def test_save():
    r = save(1)
    assert save(2) == 2
    assert r == 1
    assert len([]) == 0
    assert clean(r) is not None
"""

_CPP = """\
TEST_CASE("store saves") {
    auto r = save(1);
    REQUIRE(save(2) == 2);
    CHECK(r == 1);
    REQUIRE(true);
    EXPECT_EQ(clean(r), 1);
}
"""


def _kinds(pins) -> list[tuple[str, str | None]]:
    """@brief (kind, target) per check. @return Pairs."""
    return [(p.kind, p.target) for p in pins]


def test_python_checks_are_pinned_direct_via_variable_or_not() -> None:
    """@brief `ast`: direct, via `r`, not attributed, direct (the innermost known call)."""
    pins = pin_checks(_PY.splitlines(), "tests/test_store.py", {"save", "clean"})
    assert _kinds(pins) == [
        ("direct", "save"),
        ("via variable", "save"),
        ("not attributed", None),
        ("direct", "clean"),
    ]
    assert pins[1].variable == "r"
    assert pins[0].statement == "assert save(2) == 2"


def test_cpp_checks_are_pinned_through_the_assertion_macros() -> None:
    """@brief tree-sitter: REQUIRE / CHECK / EXPECT_EQ, the same three kinds."""
    pins = pin_checks(_CPP.splitlines(), "tests/test_store.cpp", {"save", "clean"})
    assert _kinds(pins) == [
        ("direct", "save"),
        ("via variable", "save"),
        ("not attributed", None),
        ("direct", "clean"),
    ]


def test_an_unknown_language_pins_nothing() -> None:
    """@brief No parser for the file: [] — the page then lists the checks unpinned, as before."""
    assert pin_checks(["assert x"], "tests/t.zig", {"x"}) == []
