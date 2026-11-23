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


def test_a_pin_carries_its_lines_for_pairing_with_a_run() -> None:
    """2.0.0 (P5.5, traced values): the assertion's ABSOLUTE line, and for a via-variable check
    the line that bound the variable — the call sites a recorded run's spans are matched against.
    The body starts on line 10 of its file.

    @brief Pins carry absolute lines.
    """
    for rel, src in (("tests/test_store.py", _PY), ("tests/test_store.cpp", _CPP)):
        pins = pin_checks(src.splitlines(), rel, {"save", "clean"}, first_line=10)
        assert [p.line for p in pins] == [12, 13, 14, 15], rel
        assert pins[1].bound_line == 11 and pins[0].bound_line is None, rel


def _otlp(spans: list[dict]) -> dict:
    """@brief Wrap spans as OTLP JSON. @return Document."""
    return {"resourceSpans": [{"scopeSpans": [{"spans": spans}]}]}


def _span(sid: str, parent: str, name: str, call_line: str = "", ret: str = "") -> dict:
    """@brief One span with the attributes the pairing reads. @return Span."""
    attrs = [{"key": "clew.call_line", "value": {"stringValue": call_line}}] if call_line else []
    attrs += [{"key": "clew.return", "value": {"stringValue": ret}}] if ret else []
    return {"spanId": sid, "parentSpanId": parent, "name": name, "attributes": attrs}


def test_a_traced_run_gives_each_pinned_check_the_value_it_saw() -> None:
    """2.0.0 (P5.5, traced values): the span of the pinned function CALLED FROM THE TEST at the
    pin's call site — the assertion's own line when direct, the binding line when via a variable —
    gives the value the check observed. `save` is called twice; each check gets its own call's
    value. A check with no target, or a run without call lines, gets none.

    @brief Traced values pair by call site.
    """
    from clew.wiki.checkpins import traced_values

    pins = pin_checks(_PY.splitlines(), "tests/test_store.py", {"save", "clean"}, first_line=10)
    otlp = _otlp(
        [
            _span("t", "", "test_save"),
            _span("a", "t", "save", "11", "1"),
            _span("b", "t", "save", "12", "2"),
            _span("c", "t", "clean", "15", "1"),
        ]
    )
    assert traced_values(pins, otlp, "test_save") == {0: "2", 1: "1", 3: "1"}
    old_run = _otlp([_span("t", "", "test_save"), _span("a", "t", "save", "", "1")])
    assert traced_values(pins, old_run, "test_save") == {}, "no call line, no guessed pairing"


def test_a_pinned_check_shows_its_traced_value() -> None:
    """@brief On the page: "observes `save` — returned `2` in the recorded run"."""
    from clew.wiki.checkpins import Pin
    from clew.wiki.testpages import _pinned

    html = _pinned(Pin("assert save(2) == 2", "direct", "save", line=12), "2")
    assert '<span class="traced">returned <code>2</code> in the recorded run</span>' in html
    assert "traced" not in _pinned(Pin("assert x", "not attributed", line=13), None)


def test_a_test_no_product_flow_reaches_says_so() -> None:
    """ABSENCE IS STATED (P5.5): a test whose calls no product flow reaches gets the sentence, not
    an empty space; a tooling flow does not count as the product.

    @brief Context paths: the negative.
    """
    from clew.wiki.flowpage import FlowPage
    from clew.wiki.testpages import _context

    tool = FlowPage("flow-gen", "gen", frozenset(), calls=(("gen", "helper"),), role="tooling")
    product = FlowPage(
        "flow-main", "main", frozenset(), calls=(("main", "run"), ("run", "save")), role="product"
    )
    assert "No product flow reaches" in _context({"helper"}, [tool, product])
    html = _context({"save"}, [tool, product])
    assert (
        "<code>main</code> → <code>run</code> → <code>save</code>" in html
        and 'href="flow-main.html"' in html
    )


def test_a_flow_that_only_starts_at_the_function_is_the_fallback() -> None:
    """@brief A caller chain beats "is the entry"; the entry form is shown only alone."""
    from clew.wiki.flowpage import FlowPage
    from clew.wiki.testpages import _context

    own = FlowPage("flow-save", "save", frozenset(), calls=(("save", "write"),), role="product")
    main = FlowPage("flow-main", "main", frozenset(), calls=(("main", "save"),), role="product")
    assert "<code>main</code> → <code>save</code>" in _context({"save"}, [own, main])
    assert "<code>save</code> is the entry of the flow" in _context({"save"}, [own])
