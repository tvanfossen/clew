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

from pathlib import Path

from .composite import Composite, Node
from .config import Audience
from .htmltable import code, text

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
## @version 1
## @req REQ-DDB-WIKI-040
def product_page(tree: Composite, rules: Audience, source: Path) -> str:
    """@brief Write product.md. @return Page name."""
    lines = [
        "# Product trace",
        "",
        _LEAD,
        "",
        "```{raw} html",
        product_html(tree, rules),
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
## @version 2
## @req REQ-DDB-WIKI-040
def product_html(tree: Composite, rules: Audience) -> str:
    """@brief Tree, problems, unreached. @return HTML."""
    items = "".join(_item(tree, ref, rules, set()) for ref in tree.roots)
    parts = [f'<ul class="ptree">{items}</ul>', _problems(tree)]
    if tree.implemented_here:
        rows = "".join(_line(tree.nodes[r], rules) for r in tree.implemented_here)
        parts.append(
            f'<details class="implemented-here" open><summary>{len(tree.implemented_here)} '
            f"dependency requirement(s) this repository implements</summary><ul>{rows}</ul></details>"
        )
    if tree.unreached:
        rows = "".join(_line(tree.nodes[r], rules) for r in tree.unreached)
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
## @version 1
## @utility
def _item(tree: Composite, ref: str, rules: Audience, path: set[str]) -> str:
    """@brief Item. @return HTML."""
    node = tree.nodes[ref]
    below = [r for r in node.satisfied_by if r not in path and r in tree.nodes]
    kids = "".join(_item(tree, r, rules, path | {ref}) for r in below)
    return _line(node, rules, f"<ul>{kids}</ul>" if kids else "")


## @brief One requirement's line: id, title, evidence.
## @param node The node.
## @param rules The audience rules.
## @param kids Nested HTML.
## @return HTML.
## @version 1
## @utility
def _line(node: Node, rules: Audience, kids: str = "") -> str:
    """@brief Line. @return HTML."""
    title = "" if rules.exclude_requirement_text or not node.title else f" {text(node.title)}"
    chip = f'<span class="ev ev-{node.evidence}">{node.evidence}</span>'
    return f"<li>{code(node.ref)}{title} {chip}{_evidence(node)}{kids}</li>"


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
