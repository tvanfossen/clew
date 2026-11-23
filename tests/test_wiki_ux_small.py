# SPDX-License-Identifier: MIT
"""Consistency fixes from the independent UX review (group E, owner Q/A 2026-11-22).

Each test names its finding in .claude/tmp/r5/ux-review-2026-11-22.md.

@brief Tests the small consistency fixes.
@version 1
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import clew.wiki

_STATIC = Path(clew.wiki.__file__).parent / "themes" / "clew" / "static"


def test_plurals_read_as_english() -> None:
    """@brief E-22: "1 tests flows", "Also reaches 1 requirements" — one plural helper."""
    from clew.wiki.htmltable import plural

    assert (
        plural(1, "requirement") == "1 requirement" and plural(2, "requirement") == "2 requirements"
    )
    assert (
        plural(1, "flow", "test") == "1 test flow"
        and plural(3, "flow", "tooling") == "3 tooling flows"
    )


def test_the_speed_slider_takes_the_theme_accent() -> None:
    """@brief E-23: the browser-default blue range input clashed with the palette."""
    assert "input[type=range]{accent-color:var(--acc)}" in (_STATIC / "clew.css").read_text()


def test_frame_tags_are_neutral_and_dimmed_steps_stay_readable() -> None:
    """@brief E-17: red-brown frame tags read as failure; dimmed steps at .28 opacity failed contrast."""
    from clew.wiki.svg import _STYLE

    assert (
        "#A6502C" not in _STYLE
        and "--root" not in _STYLE.split(".seq .frame", 1)[1].split("}", 2)[1]
    )
    assert ".seq g.dim{opacity:.5}" in _STYLE


def test_the_test_card_keeps_three_columns_and_code_in_mono() -> None:
    """E-16 (owner-approved review): a fixed Given / When / Then (Given "—" when empty, not a reflow);
    Given folds past two statements; checks read in monospace like the code they describe.
    SPEC CHANGED: test_a_call_inside_the_assertion… required the empty Given to disappear.

    @brief Card layout.
    """
    from clew.wiki.testcard import test_card

    d = SimpleNamespace(name="test_s", file="tests/test_s.py", start=1)
    html = test_card(["def test_s():", "    assert f(1) == 2"], d, {"f"}, None)
    assert 'class="tc-given"' in html and '<li class="none">—</li>' in html
    assert "tc-strip no-given" not in html
    src = ["def test_g():"] + [f"    v{i} = {i}" for i in range(4)] + ["    assert f(v0) == 1"]
    given = test_card(src, SimpleNamespace(name="test_g", file="t.py", start=1), {"f"}, None).split(
        'class="tc-given"', 1
    )[1]
    assert "<details" in given and "2 more" in given
    assert (
        ".tc-then li.ck{" in (_STATIC / "clew.css").read_text()
        and "font-family:var(--mono)"
        in (_STATIC / "clew.css").read_text().split(".tc-then li.ck{", 1)[1].split("}", 1)[0]
    )


def test_a_short_call_flow_has_no_player() -> None:
    """@brief E-15: a player for one box is a control without purpose; it appears past five boxes."""
    from clew.wiki.testpages import _callflow

    one = _callflow("test_x", [("f", "a.py")], {}, set())
    many = _callflow("test_x", [(f"f{i}", "a.py") for i in range(6)], {}, set())
    assert "data-slice-control" not in one and "data-slice-control" in many


def test_flow_titles_read_one_way_and_an_empty_flow_says_so() -> None:
    """E-11: mixed registers ("Build this wiki…" beside `clew — main (clew/cli.py)`), and a 0-step
    flow listed as a peer. A discovered title shows its readable part, with the entry and file under
    it in small monospace; a flow with no steps is muted and says "not traced".

    @brief One title pattern; empty flows muted.
    """
    from clew.wiki.flowpage import FlowPage, _role_block

    pages = [
        FlowPage("flow-main", "clew — `main` (clew/cli.py)", frozenset(), role="product", steps=12),
        FlowPage("flow-s", "Find a name you do not have yet", frozenset(), role="product", steps=0),
    ]
    html = _role_block("product", pages)
    assert ">clew</a>" in html and '<span class="entry">`main` (clew/cli.py)</span>' not in html
    assert '<span class="entry"><code>main</code> (clew/cli.py)</span>' in html
    assert 'class="untraced"' in html and "not traced" in html


def test_a_file_page_names_the_file_and_says_what_it_is_for() -> None:
    """E-20: the page's title was a small grey path chip, with no purpose. The h1 is the file's name,
    the path follows in monospace, then the file's own documented purpose (first sentence).

    @brief File page header.
    """
    from clew.wiki.symbols import _file_header

    html = _file_header(
        "clew/wiki/flow.py", "Derive call flows from the index. More detail follows."
    )
    assert '<p class="sym-path"><code>clew/wiki/flow.py</code></p>' in html
    assert '<p class="sym-purpose">Derive call flows from the index.</p>' in html
    assert _file_header("a.py", "") == '<p class="sym-path"><code>a.py</code></p>'


def test_callers_and_tests_are_listed_apart() -> None:
    """@brief E-20: "Called by" is product code; tests that call it are "Tested by", folded."""
    from clew.wiki.symbols import _split_callers

    product, tests = _split_callers(
        [("flow_page", "clew/wiki/flowpage.py"), ("test_x", "tests/t.py")],
        {("test_x", "tests/t.py")},
    )
    assert product == [("flow_page", "clew/wiki/flowpage.py")] and tests == [
        ("test_x", "tests/t.py")
    ]


def test_a_signature_wraps_instead_of_clipping() -> None:
    """@brief E-20: the signature was clipped mid-word."""
    assert (
        "div.body pre.sig{white-space:pre-wrap;overflow-wrap:anywhere}"
        in (_STATIC / "clew.css").read_text()
    )


def test_the_sbom_drops_empty_columns_normalises_licences_and_states_coverage() -> None:
    """E-25 / E-22: an empty Digest column in every row; "Apache-2.0 AND License :: OSI Approved ::
    …" as a licence; "44344 indexed files carry no SPDX identifier" buried as a footnote.

    @brief SBOM table and coverage.
    """
    from clew.wiki.sbom import Component, _cdx_licence, sbom_html

    assert (
        _cdx_licence(
            {
                "licenses": [
                    {"license": {"id": "Apache-2.0"}},
                    {"license": {"name": "License :: OSI Approved :: Apache Software License"}},
                ]
            }
        )
        == "Apache-2.0"
    )
    comps = [
        Component("a", "1", "MIT", "library", "pkg:pypi/a", ""),
        Component("b", "2", "MIT", "library", "pkg:pypi/b", ""),
    ]
    html = sbom_html([("bom.cdx.json", ("clew", "MIT"), comps)], (), {"MIT": 600}, 44344)
    assert "<th>digest</th>" not in html and "<th>source</th>" in html
    assert '<p class="stat"><b>600 of 44,944</b> indexed files declare a licence (1%).</p>' in html


def test_a_small_architecture_diagram_has_no_zoom_and_a_main_names_its_file() -> None:
    """E-19: small diagrams sat in wide canvases with zoom controls they did not need; one container
    read `main.py` among console-script names. Pan/zoom only where the diagram is larger than the
    column; a `main` shows its file's path.

    @brief Architecture controls and names.
    """
    from clew.wiki.architecture import Entry, _svg

    assert "data-pz" not in _svg(600, 300, [], "small") and "data-pz" in _svg(1400, 300, [], "wide")
    e = Entry(kind="main", function="main", file="tools/run/main.py", label="", flow=None)
    assert e.shown() == "tools/run/main.py"


def test_on_a_phone_diagrams_keep_readable_text_and_unlabelled_tables_scroll() -> None:
    """UX review group B (owner Q/A 2026-11-22). Measured at 390 px on clew's site (be732054):
    architecture text drew at 1.9 px, an activity diagram at 2.1, the requirement evidence at 6.4
    — every diagram was scaled to the column. And a table whose cells carry no `data-label` was
    stacked into cards with no column names (357 such tables on the Tests tab). Under 760 px a
    diagram keeps its own size inside a box that scrolls sideways; only a table whose cells name
    their column becomes cards, the rest scroll; the flow speed control and long test names wrap.

    @brief Phone widths.
    """
    css = (_STATIC / "clew.css").read_text()
    phone = css[css.index("/* B: phone widths") :]
    assert "svg.c4-diagram,svg.activity,svg.req-evidence{max-width:none" in phone
    assert ".c4-fit,.pz,.req-evidence-fig,div:has(> svg.activity){overflow-x:auto" in phone
    assert "table.clew:not(:has(td[data-label]))" in phone
    assert (
        ".flow-speed{flex-wrap:wrap" in phone
        and "details.tgroup code{overflow-wrap:anywhere}" in phone
    )
    ## found by measuring: the controls row did not wrap; long test names under "Tested by" did not.
    assert ".flow-controls{flex-wrap:wrap}" in phone and ".near a{overflow-wrap:anywhere}" in phone
    stacked = css[css.index("@media(max-width:760px){table.clew") :].split("}}", 1)[0]
    assert "table.clew:has(td[data-label]) thead{display:none}" in stacked
