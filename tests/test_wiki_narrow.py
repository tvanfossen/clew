# SPDX-License-Identifier: MIT
"""Pages fit a phone, and the symbol domain answers Sphinx's `any` lookup (P6 findings, 2.0.0).

OWNER Q/A 2026-11-20, after P6, "fix all 5". Measured at 390px with headless Chromium
(`.claude/tmp/r5/p6_shots.py`): entropic's API page scrolled sideways because `dl.api-doc`'s grid
(`max-content 1fr`) let an unbreakable `<code>` stretch it to 844px, and a clew test page did
because its 446px `<code>` title could not wrap. Sphinx warned that the `clew` domain had not
implemented `resolve_any_xref`.

@brief Tests the 390px layout rules and the domain's any-lookup.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import clew.wiki

_CSS = Path(clew.wiki.__file__).parent / "themes" / "clew" / "static" / "clew.css"


def test_the_api_grid_cannot_be_stretched_by_its_content() -> None:
    """@brief The definition column is `minmax(0,1fr)`, so long code wraps inside it."""
    css = _CSS.read_text(encoding="utf-8")
    assert "dl.api-doc{display:grid;grid-template-columns:max-content minmax(0,1fr)" in css


def test_code_in_headings_and_definitions_wraps() -> None:
    """@brief A long identifier in a title or an API definition breaks instead of overflowing."""
    css = _CSS.read_text(encoding="utf-8")
    assert (
        "div.body h1 code,div.body h2 code,div.body h3 code,div.body h4 code,dl.api-doc code{overflow-wrap:anywhere}"
        in css
    )


def test_a_call_flow_box_shrinks_and_wraps() -> None:
    """@brief The test's own box (a long test name in `<code>`) is a flex item that may shrink and wrap."""
    css = _CSS.read_text(encoding="utf-8")
    assert ".callflow .box{min-width:0;max-width:100%;overflow-wrap:anywhere;" in css


def test_the_clew_domain_resolves_no_any_reference() -> None:
    """@brief Objects only: an `any` lookup finds nothing here, said rather than unimplemented."""
    from sphinx.domains import Domain

    from clew.wiki._sphinxsymbols import ClewDomain

    assert ClewDomain.resolve_any_xref is not Domain.resolve_any_xref
    assert ClewDomain.resolve_any_xref(None, None, None, "x", None, None, None) == []


def test_a_sequence_diagram_is_never_letterboxed() -> None:
    """Owner review 2026-11-22 (screenshot of the dossier flow): the diagram opened under ~1,000 px of
    empty space. The SVG's width was capped by a generic max-width while its height attribute stayed
    8,701 px, so the drawing was scaled down and centred vertically. A sequence diagram keeps its own
    size (the wrapper scrolls) and its height follows its width.

    @brief svg.seq is never letterboxed.
    """
    css = _CSS.read_text(encoding="utf-8")
    assert ".flow-wrap svg.seq{max-width:none;height:auto}" in css
