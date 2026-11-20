# SPDX-License-Identifier: MIT
"""Entity quick views: a modal per function on a flow, with the view strip (round 5, P5.6).

OWNER (round 5): every entity gets a page plus a QUICK-VIEW MODAL with the view strip
Map · Block · Flow · Replay · Source · Tests · Reqs. The quick view is a summary that links to the full
views, NOT a copy of them: each view carries small inline facts, and a list longer than `_SHOWN`
says how many more there are and links the function's own page. The evidence diagram drawn in full
on every requirement page cost 14.6 MB; nothing per entity is drawn in full where it is mentioned.

Without script every view is shown, stacked under its heading; `clew-views.js` turns the strip into
tabs (owner Q/A 2026-11-20: a second, budgeted script loaded only where a quick view exists).

@brief Build the quick view for one function.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape
from urllib.parse import quote

## The view strip, in the owner's order.
VIEWS = ("map", "block", "flow", "replay", "source", "tests", "reqs")
_LABELS = {
    "map": "Map",
    "block": "Block",
    "flow": "Flow",
    "replay": "Replay",
    "source": "Source",
    "tests": "Tests",
    "reqs": "Reqs",
}
## How many items a list shows inline before "N more on its page".
_SHOWN = 5


## @brief What a function's quick view says about it.
## @version 1
@dataclass(frozen=True)
class EntityFacts:
    """`flows` and `replays` are (page name, title); `tests` (test name, page file).

    @brief Name, file, brief, block, flows, recorded runs, tests, requirements, page, anchor.
    """

    name: str
    file: str
    brief: str
    block: str
    flows: tuple[tuple[str, str], ...]
    replays: tuple[tuple[str, str], ...]
    tests: tuple[tuple[str, str], ...]
    reqs: tuple[str, ...]
    page: str
    anchor: str


## @brief The quick view's HTML: the strip, then one panel per view.
## @param facts The function's facts.
## @return HTML for a modal template's body.
## @version 1
## @req REQ-DDB-WIKI-048
def quick_view(facts: EntityFacts) -> str:
    """@brief Strip and panels. @return HTML."""
    home = f"{facts.page}#{facts.anchor}"
    panels = {
        "map": _map(facts),
        "block": f"<p><strong>{escape(facts.block)}</strong> is the block holding "
        f"<code>{escape(facts.file)}</code>.</p>"
        if facts.block
        else f"<p>No block holds <code>{escape(facts.file)}</code>.</p>",
        "flow": _list(_titled(facts.flows), home, "No flow on this site calls this function."),
        "replay": _list(_titled(facts.replays), home, "No recorded run reaches this function."),
        "source": f'<p><a href="{home}">Its page</a>: signature, body, callers and callees. '
        f'<a href="{facts.page}#act-{facts.anchor}">Its activity diagram</a>.</p>',
        "tests": _list(
            tuple((n, h.removesuffix(".html")) for n, h in facts.tests),
            home,
            "No test calls this function directly.",
            code=True,
        ),
        "reqs": _reqs(facts.reqs),
    }
    strip = "".join(
        f'<button type="button" class="view-tab" data-view="{v}">{_LABELS[v]}</button>'
        for v in VIEWS
    )
    body = "".join(
        f'<section class="view" data-view-panel="{v}"><h4>{_LABELS[v]}</h4>{panels[v]}</section>'
        for v in VIEWS
    )
    brief = f'<p class="brief">{escape(facts.brief)}</p>' if facts.brief else ""
    return f'{brief}<nav class="views" aria-label="Views">{strip}</nav>{body}'


## @brief The Map view: where the function sits, and a link that flies there.
## @param facts The function's facts.
## @return HTML.
## @version 1
## @utility
def _map(facts: EntityFacts) -> str:
    """@brief The map focuses `name@file` (`web.js`'s `#n=`). @return HTML."""
    target = quote(f"{facts.name}@{facts.file}", safe="")
    return f'<p><a href="map.html#n={target}">Show it on the map</a>, in its block\'s wedge.</p>'


## @brief (page, title) pairs as the (label, page) pairs `_list` draws.
## @param pages (page name, title) pairs.
## @return (title, page name) pairs.
## @version 1
## @utility
def _titled(pages: tuple[tuple[str, str], ...]) -> tuple[tuple[str, str], ...]:
    """@brief Swap. @return Pairs."""
    return tuple((title, page) for page, title in pages)


## @brief A capped list of (label, page) links, or the sentence for none.
## @param items (label, page name without `.html`).
## @param home The function's page, for "N more on its page".
## @param empty The sentence when there are none.
## @param code Render labels as code.
## @return HTML.
## @version 1
## @utility
def _list(items: tuple[tuple[str, str], ...], home: str, empty: str, code: bool = False) -> str:
    """@brief First `_SHOWN`, then the count of the rest. @return HTML."""
    if not items:
        return f'<p class="none">{escape(empty)}</p>'
    wrap = (lambda s: f"<code>{escape(s)}</code>") if code else escape
    lis = "".join(
        f'<li><a href="{escape(p)}.html">{wrap(label)}</a></li>' for label, p in items[:_SHOWN]
    )
    more = len(items) - _SHOWN
    tail = f'<p class="more"><a href="{home}">{more} more on its page</a></p>' if more > 0 else ""
    return f"<ul>{lis}</ul>{tail}"


## @brief The requirement badges, or the sentence for none.
## @param reqs Requirement ids.
## @return HTML.
## @version 1
## @utility
def _reqs(reqs: tuple[str, ...]) -> str:
    """@brief Badges linking each requirement's page. @return HTML."""
    if not reqs:
        return '<p class="none">No requirement names this function as an implementer.</p>'
    from .reqmodal import page_of

    return (
        "<p>"
        + " ".join(f'<a class="req-badge" href="{page_of(r)}.html">{escape(r)}</a>' for r in reqs)
        + "</p>"
    )


## @brief Append each flow page's quick views: a trigger and a template per function on it.
## @param db The index.
## @param source The Sphinx source directory (the flow pages' `.md` are appended to).
## @param pages The flow pages.
## @param file_block File → block, from the build graph.
## @param test_href Test name → its page.
## @param req_of (function, file) → the requirements it implements.
## @return How many quick views were written.
## @version 1
## @req REQ-DDB-WIKI-048
def write_quick_views(
    db, source, pages: list, file_block: dict, test_href: dict, req_of: dict
) -> int:  # noqa: ANN001
    """A SECOND PASS, after every flow and test page exists: a quick view lists the OTHER flows a
    function is on and the tests that call it, which no single flow page knows while it is drawn.
    The page's own text is untouched; the section is appended to its source before rendering.

    @brief Write quick views.
    @return Count.
    """
    from pathlib import Path

    from ..query._common import connect
    from .modal import modal
    from .symbols import _Edges, anchor, symbol_href

    with connect(db) as conn:
        edges = _Edges(conn)
        briefs = _briefs(conn)
    flows_of: dict = {}
    for p in pages:
        for key in p.functions:
            flows_of.setdefault(key, []).append(p)
    written = 0
    for page in pages:
        items = []
        for i, (name, rel) in enumerate(sorted(page.functions, key=lambda k: (k[1], k[0]))):
            facts = _facts_of(name, rel, flows_of, edges, file_block, test_href, req_of, briefs)
            href, _a = symbol_href(name, rel).split("#", 1)
            facts = EntityFacts(**{**facts.__dict__, "page": href, "anchor": anchor(name)})
            items.append(f"<li>{modal(f'q-{i}', name, f'{name} ({rel})', quick_view(facts))}</li>")
            written += 1
        if items:
            block = (
                "\n## Quick views\n\n```{raw} html\n"
                f'<ul class="modal-list quick-views">{"".join(items)}</ul>\n'
                '<script src="_static/clew-views.js"></script>\n```\n'
            )
            path = Path(source) / f"{page.name}.md"
            path.write_text(path.read_text(encoding="utf-8") + block, encoding="utf-8")
    return written


## @brief One function's facts from the site's pages and the index.
## @param name The function.
## @param rel Its file.
## @param flows_of (function, file) → the flow pages it is on.
## @param edges The call graph.
## @param file_block File → block.
## @param test_href Test name → page.
## @param req_of (function, file) → requirements.
## @param briefs (function, file) → brief.
## @return Facts (page and anchor filled by the caller).
## @version 1
## @utility
def _facts_of(name, rel, flows_of, edges, file_block, test_href, req_of, briefs) -> EntityFacts:  # noqa: ANN001
    """THE TESTS ARE ITS DIRECT CALLERS that have a test page, from the index's call edges.

    @brief Gather facts.
    @return Facts.
    """
    on = flows_of.get((name, rel), [])
    callers = {
        edges.names[c][0]
        for r in edges.by_key.get((name, rel), ())
        for c in edges.callers.get(r, ())
    }
    return EntityFacts(
        name=name,
        file=rel,
        brief=briefs.get((name, rel), ""),
        block=file_block.get(rel, ""),
        flows=tuple((p.name, p.title) for p in on if p.role != "tests"),
        replays=tuple((p.name, p.title) for p in on if p.role == "tests"),
        tests=tuple((t, test_href[t]) for t in sorted(callers) if t in test_href),
        reqs=tuple(sorted(set(req_of.get((name, rel), ())))),
        page="",
        anchor="",
    )


## @brief Each function's brief, from the index.
## @param conn Open connection.
## @return (function, file) → brief.
## @version 1
## @utility
def _briefs(conn) -> dict:  # noqa: ANN001
    """PLAIN TEXT: doxygen stores a brief as XML (`<para>…</para>`), which the quick view printed
    verbatim (found by looking); `strip_xml` is the one cleaner the step modal already uses.

    @brief Read briefs.
    @return Map.
    """
    from ..query._common import strip_xml

    rows = conn.execute(
        "SELECT m.name, p.name, COALESCE(m.briefdescription, '') FROM memberdef m JOIN path p "
        "ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function'"
    )
    return {(str(n), str(f)): " ".join(strip_xml(str(b)).split()) for n, f, b in rows if b}
