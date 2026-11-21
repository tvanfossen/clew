# SPDX-License-Identifier: MIT
"""A Sphinx domain that puts every symbol section in the site's objects.inv (P5, S8; 2.0.0).

OWNER-APPROVED 2026-11-17 (standards research, S8). `objects.inv` is what intersphinx,
`sphobjinv` and documentation search tools read to turn a name into a URL; the site's held only
`std:doc` and `std:label`, so no tool could resolve a function to its section. The symbol pages
are raw HTML (`symbols.symbol_pages`), so there is no directive to hang an object on: the build
writes `_clew_objects.json` beside the sources and this domain reports its rows.

ONE OBJECT PER SECTION, named `<file>::<name>`, which is unique. The BARE NAME is added only where
one file defines it: a bare `helper` defined in two files would resolve to whichever was listed
first, which is a wrong link presented as a right one.

@brief The `clew` Sphinx domain: symbol sections as inventory objects.
@version 1
"""

from __future__ import annotations

import re

import json
from collections import Counter
from pathlib import Path
from typing import Any

from sphinx.domains import Domain, ObjType

## The file the build writes into the Sphinx source directory.
OBJECTS_FILE = "_clew_objects.json"


## @brief The `clew` domain: objects only, read from the build's list.
## @version 1
class ClewDomain(Domain):
    """@brief Symbol sections as inventory objects.
    @version 1
    """

    name = "clew"
    label = "clew"
    object_types = {"function": ObjType("function", "func")}

    ## @brief Every inventory object: (name, display name, type, page, anchor, priority).
    ## @return The objects.
    ## @version 1
    ## @req REQ-DDB-WIKI-025
    def get_objects(self) -> Any:
        """PRIORITY 1, Sphinx's "important" (the default for an object an index should list);
        a bare alias is priority 2, "unimportant", so a search ranks the qualified form first.

        @brief Yield objects.
        @return Objects.
        """
        rows = _rows(Path(self.env.srcdir) / OBJECTS_FILE)
        once = Counter(r["name"] for r in rows)
        for r in rows:
            yield (f"{r['file']}::{r['name']}", r["name"], "function", r["page"], r["anchor"], 1)
            if once[r["name"]] == 1:
                yield (r["name"], r["name"], "function", r["page"], r["anchor"], 2)

    ## @brief An `any` lookup finds nothing in this domain: it carries objects, not references.
    ## @param env The build environment.
    ## @param fromdocname The document asking.
    ## @param builder The builder.
    ## @param target The name looked up.
    ## @param node The pending reference.
    ## @param contnode Its content.
    ## @return No matches.
    ## @version 1
    ## @utility
    def resolve_any_xref(  # noqa: PLR0913 - Sphinx's signature
        self, env: Any, fromdocname: str, builder: Any, target: str, node: Any, contnode: Any
    ) -> list:
        """P6 (owner Q/A 2026-11-20): Sphinx warned once per build that the `clew` domain had not
        implemented this, because MyST asks every domain. Objects only, so nothing resolves here.

        @brief Resolve nothing.
        @return [].
        """
        return []

    ## @brief Nothing to forget: the objects are the build's list, not parsed state.
    ## @param docname A document being re-read.
    ## @return None.
    ## @version 1
    ## @utility
    def clear_doc(self, docname: str) -> None:
        """@brief No per-document state. @return None."""


## @brief The build's object rows, or none when it wrote no list.
## @param path The list.
## @return Rows.
## @version 1
## @utility
def _rows(path: Path) -> list[dict[str, str]]:
    """@brief Read the list. @return Rows."""
    if not path.is_file():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")))


## @brief Register the domain.
## @param app The Sphinx application.
## @return Extension metadata.
## v2: keeps source bodies and diagram text out of the search index (2.0.0, P5.1b)
## @version 2
## @req REQ-DDB-WIKI-025
def setup(app: Any) -> dict[str, Any]:
    """@brief Sphinx entry point. @return Metadata."""
    app.add_domain(ClewDomain)
    _keep_bodies_out_of_search()
    return {"version": "1", "parallel_read_safe": True, "parallel_write_safe": True}


## Raw-HTML regions the search index skips (P5.1b): folded source bodies, activity diagrams, and
## every SVG's labels. Sphinx strips the tags off raw HTML and indexes the rest; these were 6.35 MB
## of clew's own 8.2 MB searchindex.js (80,285 terms).
_NOT_SEARCHED = re.compile(
    r'<details class="(?:body|activity)".*?</details>|<svg\b.*?</svg>'
    ## Owner Q/A 2026-11-20: tests are searched from the Tests tab's own filter, not here.
    r'|<table class="clew tests-all".*?</table>',
    re.DOTALL | re.IGNORECASE,
)
## Owner Q/A 2026-11-20: test pages (68% of clew's search postings) leave the main search.
_UNSEARCHED_PAGES = ("test-",)


## @brief Make Sphinx's search indexer skip source bodies and diagram text in raw HTML.
## @return None.
## v1 (2.0.0, P5.1b): measured above; the page output is untouched, only the indexer's copy.
## v2: test pages out of the main search (tests category (2.0.0, owner Q/A 2026-11-20))
## @version 2
## @req REQ-DDB-WIKI-022
def _keep_bodies_out_of_search() -> None:
    """THE INDEXER SEES A STRIPPED COPY, the page keeps every byte: the original raw node is not
    changed, so the HTML written is exactly as before. Sphinx itself strips `<style>` and
    `<script>` the same way.

    TWO SPHINX PATHS, both private, so both are covered and a test pins the result: Sphinx 8 feeds
    the index through the module function `sphinx.search._feed_visit_nodes` (it recurses through
    its global name, so the wrapper sees every child); 7.x through `WordCollector.dispatch_visit`.
    The pinned range is `sphinx>=7.3,<9`; a release that drops both fails
    `test_source_bodies_and_diagrams_are_not_in_the_search_index` loudly. Idempotent.

    @brief Patch the search indexer.
    @return None.
    """
    import sphinx.search as search

    feed_page = search.IndexBuilder.feed
    if not getattr(feed_page, "_clew_wrapped", False):

        def feed(self: Any, docname: str, *args: Any, **kwargs: Any) -> None:
            if docname.startswith(_UNSEARCHED_PAGES):
                return None
            return feed_page(self, docname, *args, **kwargs)

        feed._clew_wrapped = True  # type: ignore[attr-defined]
        search.IndexBuilder.feed = feed
    if hasattr(search, "_feed_visit_nodes"):
        original = search._feed_visit_nodes
        if not getattr(original, "_clew_wrapped", False):

            def feed(node: Any, **kwargs: Any) -> None:
                return original(_stripped(node), **kwargs)

            feed._clew_wrapped = True  # type: ignore[attr-defined]
            search._feed_visit_nodes = feed
    collector = getattr(search, "WordCollector", None)
    visit = getattr(collector, "dispatch_visit", None)
    if visit is not None and not getattr(visit, "_clew_wrapped", False):

        def dispatch_visit(self: Any, node: Any) -> None:
            return visit(self, _stripped(node))

        dispatch_visit._clew_wrapped = True  # type: ignore[attr-defined]
        collector.dispatch_visit = dispatch_visit


## @brief A raw HTML node without the regions the index skips; any other node unchanged.
## @param node A doctree node.
## @return The node, or a stripped copy.
## @version 1
## @utility
def _stripped(node: Any) -> Any:
    """NO DOCUTILS IMPORT: it arrives only through Sphinx and is not a declared dependency (#77),
    so the node is recognised by its class name and copied through its own class.

    @brief Copy, never mutate.
    @return Node.
    """
    if type(node).__name__ == "raw" and "html" in node.get("format", "").split():
        text = _NOT_SEARCHED.sub("", node.astext())
        return node.__class__(text, text, format=node.get("format", ""))
    return node
