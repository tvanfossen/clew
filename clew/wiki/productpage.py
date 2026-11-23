# SPDX-License-Identifier: MIT
"""The product trace page: the composite requirement tree across pinned dependencies (GH #68).

Each requirement of this repository's catalogue is a root; under it hangs every dependency
requirement whose `satisfies` reaches it, transitively, each with its evidence state:

  * INDEXED — the dependency's index describes the pinned code: its functions and tests;
  * UNKNOWN — it does not, and the row says why and links the local checkout (owner 2026-11-16:
    "better to state unknown than show old/stale code by a bad ref");
  * ABSENT — no index of that dependency on this machine.

Below the tree: dangling links, pin conflicts, and — folded — the dependency requirements nothing
on the tree reaches.

@brief Render the composite requirement tree.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .composite import Composite, Node
from .config import Audience
from .htmltable import code, text
from .reqmodal import page_of


## @brief The requirement ids this site has a page for, and how the tree's refs map to them.
## @version 1
## @utility
@dataclass(frozen=True)
class _Links:
    """@brief Ids with a page; root catalogue names, whose requirements are keyed by bare id."""

    pages: frozenset[str] = frozenset()
    roots: frozenset[str] = frozenset()


_LEAD = (
    "This repository's requirements and, under each, the requirements of pinned dependencies that "
    "satisfy it. A dependency's functions and tests are shown only when its index is at the pin; "
    "otherwise the row says why not."
)


## @brief Write the product trace page.
## @param tree The composite.
## @param rules The audience rules.
## @param source The Sphinx source directory.
## @return The page name.
## v2: product tree requirement ids link to their pages (2.0.0, P5.4)
## @version 2
## @req REQ-DDB-WIKI-040
def product_page(
    tree: Composite, rules: Audience, source: Path, pages: frozenset[str] = frozenset()
) -> str:
    """@brief Write product.md. @return Page name."""
    lines = [
        "# Product trace",
        "",
        _LEAD,
        "",
        "```{raw} html",
        product_html(tree, rules, pages),
        "```",
        "",
    ]
    (Path(source) / "product.md").write_text("\n".join(lines), encoding="utf-8")
    return "product"


## @brief The page body.
## @param tree The composite.
## @param rules The audience rules.
## @return HTML.
## v2: dependency requirements implemented here, in their own open fold.
## v3: product tree requirement ids link to their pages (2.0.0, P5.4)
## @version 3
## @req REQ-DDB-WIKI-040
def product_html(tree: Composite, rules: Audience, pages: frozenset[str] = frozenset()) -> str:
    """A REQUIREMENT WITH A PAGE HERE LINKS TO IT (2.0.0, P5.4); one without a page stays text,
    so no link leads nowhere. Function and test names stay text: the tree carries bare names with
    no file, and a link to a same-named symbol elsewhere would be a confident wrong answer.

    @brief Tree, problems, unreached.
    @return HTML.
    """
    roots = frozenset(tree.nodes[r].catalog for r in tree.roots if r in tree.nodes)
    links = _Links(pages, roots)
    items = "".join(_item(tree, ref, rules, set(), links) for ref in tree.roots)
    parts = [f'<ul class="ptree">{items}</ul>', _problems(tree)]
    if tree.implemented_here:
        rows = "".join(_line(tree.nodes[r], rules, links=links) for r in tree.implemented_here)
        parts.append(
            f'<details class="implemented-here" open><summary>{len(tree.implemented_here)} '
            f"dependency requirement(s) this repository implements</summary><ul>{rows}</ul></details>"
        )
    if tree.unreached:
        rows = "".join(_line(tree.nodes[r], rules, links=links) for r in tree.unreached)
        parts.append(
            f'<details class="unreached"><summary>{len(tree.unreached)} dependency requirement(s) '
            f"nothing on this tree reaches</summary><ul>{rows}</ul></details>"
        )
    return "\n".join(p for p in parts if p)


## @brief One tree item and, recursively, what satisfies it.
## @param tree The composite.
## @param ref The node.
## @param rules The audience rules.
## @param path Refs above this one (a cycle is drawn once).
## @return HTML.
## v2: product tree requirement ids link to their pages (2.0.0, P5.4)
## @version 2
## @utility
def _item(
    tree: Composite, ref: str, rules: Audience, path: set[str], links: _Links = _Links()
) -> str:
    """@brief Item. @return HTML."""
    node = tree.nodes[ref]
    below = [r for r in node.satisfied_by if r not in path and r in tree.nodes]
    kids = "".join(_item(tree, r, rules, path | {ref}, links) for r in below)
    return _line(node, rules, f"<ul>{kids}</ul>" if kids else "", links)


## @brief One requirement's line: id, title, evidence.
## @param node The node.
## @param rules The audience rules.
## @param kids Nested HTML.
## @return HTML.
## v2: product tree requirement ids link to their pages (2.0.0, P5.4)
## @version 2
## @utility
def _line(node: Node, rules: Audience, kids: str = "", links: _Links = _Links()) -> str:
    """@brief Line. @return HTML."""
    title = "" if rules.exclude_requirement_text or not node.title else f" {text(node.title)}"
    chip = f'<span class="ev ev-{node.evidence}">{node.evidence}</span>'
    ref = code(node.ref)
    ## THIS SITE'S PAGES ARE KEYED BY THE BARE ID for the root catalogue's own requirements, and
    ## by the namespaced ref for a dependency's (as this repository's code tags one).
    key = node.req_id if node.catalog in links.roots else node.ref
    if key in links.pages:
        ref = f'<a href="{page_of(key)}.html">{ref}</a>'
    return f"<li>{ref}{title} {chip}{_evidence(node)}{kids}</li>"


## @brief A node's evidence detail: functions and tests, or why there are none.
## @param node The node.
## @return HTML.
## @version 1
## @utility
def _evidence(node: Node) -> str:
    """@brief Evidence. @return HTML."""
    if node.implementers is None:
        where = f" — local checkout {code(node.link)}" if node.link else ""
        return f'<div class="ev-note">{text(node.note)}{where}</div>' if node.note else ""
    funcs = ", ".join(code(n) for n in node.implementers) or "no function"
    tests = ", ".join(code(n) for n in node.tests or ()) or "no test"
    return f'<div class="ev-detail">{funcs} · {tests}</div>'


## @brief Dangling links and pin conflicts.
## @param tree The composite.
## @return HTML, or "" when there are none.
## @version 1
## @utility
def _problems(tree: Composite) -> str:
    """@brief Problems. @return HTML."""
    rows = [
        f"<li>{code(a)} satisfies {code(b)}, which no catalogue holds</li>"
        for a, b in tree.dangling
    ]
    rows += [f"<li>{text(c)}</li>" for c in tree.conflicts]
    if not rows:
        return ""
    return f'<div class="ptree-problems"><b>Problems</b><ul>{"".join(rows)}</ul></div>'
