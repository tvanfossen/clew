# SPDX-License-Identifier: MIT
"""A test page opens with WHY the test exists and WHAT it checks (owner review 3, 2.0.0).

OWNER REVIEW 2026-11-22: "there is still an inherent miss in the tests - its just showing a
highlighted box change - its not showing WHAT the test is checking, what its asserted, WHY does the
test exist? what EXACTLY in a visual sense is the test there for". Owner Q/A the same day: WHY from
the test's own docstring and the requirements it is DECLARED for (coverage reach folded); Given /
When / Then read from the test's syntax — structure, never invented prose; visual. (The playable
flowchart and declared failure modes are 2.1.)

@brief Tests the test card.
@version 1
"""

from __future__ import annotations

from types import SimpleNamespace

_TEST = '''def test_a_trace_is_drawn(tmp_path):
    """An imported trace is drawn over its flow.

    @brief Trace overlay.
    """
    repo = make_repo(tmp_path)
    site = build_wiki(repo)
    panel = site["flow-x.html"]
    assert "traces/run.json" in panel and "confirmed" in panel
    assert len(site) == 3
    assert not site.get("error")
'''


def _card(**kw):
    from clew.wiki.testcard import test_card

    d = SimpleNamespace(name="test_a_trace_is_drawn", file="tests/test_t.py", start=1)
    facts = SimpleNamespace(
        verifies=[("REQ-W-001", "tag"), ("REQ-X-002", "measured")], status="passed"
    )
    args = {
        "lines": _TEST.splitlines(),
        "d": d,
        "product": {"build_wiki", "make_repo"},
        "facts": facts,
    }
    args.update(kw)
    return test_card(**args)


def test_why_is_the_docstring_and_the_declared_requirements() -> None:
    """@brief The docstring's first paragraph and only the declared (tag/catalog) requirements."""
    html = _card()
    why = html.split('class="tc-why"', 1)[1].split("</div>", 1)[0]
    assert "An imported trace is drawn over its flow." in why and "@brief" not in why
    assert "REQ-W-001" in why and "REQ-X-002" not in why


def test_given_when_then_come_from_the_syntax() -> None:
    """@brief Given = setup before the first product call; When = the product calls; Then = asserts."""
    html = _card()
    given, rest = html.split('class="tc-when"', 1)
    when, then = rest.split('class="tc-then"', 1)
    assert "make_repo(tmp_path)" in when and "build_wiki(repo)" in when
    assert "panel = site[&quot;flow-x.html&quot;]" in when, (
        "a statement after the first product call is When"
    )
    assert (
        "panel contains &quot;traces/run.json&quot;" in then
        and "panel contains &quot;confirmed&quot;" in then
    )
    assert "len(site) equals 3" in then and "site.get(&quot;error&quot;) is false" in then
    assert then.count('class="ck passed"') == 4


def test_a_test_in_another_language_still_says_why() -> None:
    """@brief No Python syntax to read: the card keeps WHY (the index's brief) and draws no G/W/T."""
    d = SimpleNamespace(name="test_c", file="tests/test_c.c", start=1)
    html = _card(lines=["void test_c(void) {", "  TEST_ASSERT(1);", "}"], d=d, brief="Checks c.")
    assert "Checks c." in html and 'class="tc-when"' not in html


def test_the_requirements_table_puts_declared_first_and_folds_reach() -> None:
    """@brief Declared links (tag/catalog) are the table; coverage reach is a folded list."""
    from clew.wiki.testpages import _requirements

    facts = SimpleNamespace(
        verifies=[("REQ-W-001", "tag"), ("REQ-X-002", "measured"), ("REQ-Y-003", "inferred")],
        mutations=[],
    )
    ctx = {"tests": {"t": facts}, "extent": {}, "implementers": {}}
    html = _requirements("t", ctx)
    table, rest = html.split("<details", 1)
    assert "REQ-W-001" in table and "REQ-X-002" not in table
    assert "Also reaches 2 requirements" in rest and "REQ-X-002" in rest and "REQ-Y-003" in rest


def test_a_call_inside_the_assertion_is_the_when_and_no_empty_given_is_drawn() -> None:
    """Owner review 3, found on test_strip_xml: `assert strip_xml(...) == ...` drew empty Given and
    When panels. The product call inside an assertion is the When; a Given with nothing in it is not
    drawn.

    @brief Calls in assertions are the When.
    """
    src = ["def test_s():", '    assert strip_xml("<p>a < 2</p>") == "a < 2"']
    d = SimpleNamespace(name="test_s", file="tests/test_s.py", start=1)
    html = _card(lines=src, d=d, product={"strip_xml"})
    assert 'class="tc-given"' not in html
    when = html.split('class="tc-when"', 1)[1].split('class="tc-then"', 1)[0]
    assert "strip_xml(&quot;&lt;p&gt;a &lt; 2&lt;/p&gt;&quot;)" in when


def test_setup_noise_is_kept_out_of_the_card() -> None:
    """Owner review 3, found on test_an_imported_trace_is_drawn_over_its_test_flow: Given listed the
    test's own imports, and When began at a helper defined in the test file. Imports are not setup;
    a long panel shows three statements and folds the rest.

    @brief Imports dropped; long panels folded.
    """
    src = (
        ["def test_n(tmp_path):", "    from x import y"]
        + [f"    v{i} = {i}" for i in range(7)]
        + ["    assert v1 == 1"]
    )
    d = SimpleNamespace(name="test_n", file="tests/test_n.py", start=1)
    html = _card(lines=src, d=d, product=set())
    given = html.split('class="tc-given"', 1)[1]
    assert "from x import y" not in given and "v0 = 0" in given
    assert "<details" in given and "4 more" in given


def test_product_excludes_the_test_s_own_code() -> None:
    """@brief Callees in the test's file or under a test path are not product calls."""
    from clew.wiki.testpages import _product

    names = {
        1: ("_span", "tests/test_t.py"),
        2: ("build_wiki", "clew/wiki/build.py"),
        3: ("make", "tests/conftest.py"),
    }
    graph = SimpleNamespace(names=names, callees={9: {1, 2, 3}})
    d = SimpleNamespace(rowid=9, file="tests/test_t.py")
    assert _product(d, graph) == {"build_wiki"}


def test_the_checks_are_never_folded() -> None:
    """@brief Seven assertions: every check is shown, none behind "more"."""
    src = ["def test_m():", "    v = make()"] + [f"    assert v == {i}" for i in range(7)]
    d = SimpleNamespace(name="test_m", file="tests/test_m.py", start=1)
    then = _card(lines=src, d=d, product={"make"}).split('class="tc-then"', 1)[1]
    assert then.count('class="ck ') == 7 and "<details" not in then
