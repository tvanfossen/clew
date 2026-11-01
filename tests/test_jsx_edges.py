# SPDX-License-Identifier: MIT
"""Rendering a component in JSX is a use of it, and the index records it as one.

THE DEFECT. `<Card title="x" />` invokes `Card`, but `jsast.harvest_calls` visited only
`call_expression` and `new_expression`, so a component used only through JSX had no inbound edge.
"Where is this component used" returned nothing — on a React codebase, where rendering IS the call
graph. And because liveness and thread membership walk call edges, every such component also read
as unreachable: dead code that was in use.

A DISTINCT `source`, NOT A NEW RELATION. Harvest already tags each site (`ast`, `ast_member`,
`binding`) and the tag is served on every call edge, so a `jsx` tag lets an agent tell rendering
from invocation while "where is X used" stays one `dossier` call, with no new reply list to budget.

INTRINSICS ARE FILTERED, AND THIS WAS FOUND BY PARSING, NOT ASSUMED. `<div/>` has an `identifier`
name exactly like `<Card/>` does; a harvester taking every element would emit an edge per HTML
tag, all pointing at symbols that do not exist. React's own rule decides it: a capitalised name, or
a member expression like `<Menu.Item/>`, is a component; a lowercase one is a DOM element.

@brief Tests that JSX element usage becomes a `jsx` call edge.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import lang_parsing_substrate as lps

from clew.cli import _build_argparser, _run_pipeline
from clew.jsast import harvest_calls

## A component rendering three others — an opening tag with children, a self-closing tag, and a
## namespaced one — plus two intrinsics that must not become edges.
_PAGE = b"""export function Page() {
  return <Layout title="x"><Card /><Menu.Item /><div /><span>t</span></Layout>;
}
"""


## @brief The JSX sites a tsx source yields.
## @param src The source bytes.
## @return The harvested sites carrying the `jsx` tag.
## @version 1
def _jsx_sites(src: bytes) -> list[tuple]:
    """@brief Harvest and keep only the `jsx`-tagged sites.
    @return Site tuples.
    @version 1
    """
    tree = lps.parse_tree("tsx", src)
    sites = harvest_calls(tree, src, "ast", "ast_member", "binding", jsx="jsx")
    return [tuple(s) for s in sites if len(s) > 2 and s[2] == "jsx"]


## @brief Every component used in JSX is a site, tagged `jsx`.
## @return None.
## @version 1
def test_each_rendered_component_is_a_jsx_site() -> None:
    """@brief Opening, self-closing and namespaced components are all harvested.
    @return None.
    @version 1
    """
    names = {site[0] for site in _jsx_sites(_PAGE)}
    assert {"Layout", "Card", "Item"} <= names, names


## @brief A lowercase intrinsic element is never a site.
## @return None.
## @version 1
def test_intrinsic_elements_are_not_sites() -> None:
    """THE FILTER THAT KEEPS THIS FROM BEING NOISE. Without it a page of markup would emit one
    edge per `div`, each pointing at a function that does not exist.

    @brief `div` and `span` are not components.
    @return None.
    @version 1
    """
    names = {site[0] for site in _jsx_sites(_PAGE)}
    assert not names & {"div", "span"}, names


## @brief A component rendered in another file gains a `jsx` caller.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_rendered_component_has_its_renderer_as_a_jsx_caller(tmp_path: Path) -> None:
    """END TO END, because the harvest shape is necessary and not sufficient: the site must also
    resolve to the component's definition across files and land in `call_edges` with its tag.

    @brief "Where is Card used" is answerable.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/card.tsx").write_text(
        "export function Card() { return <div>card</div>; }\n", encoding="utf-8"
    )
    (repo / "src/page.tsx").write_text(
        "import { Card } from './card';\nexport function Page() { return <Card />; }\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    edges = set(
        sqlite3.connect(out).execute(
            "SELECT a.name, b.name, e.source FROM call_edges e "
            "JOIN memberdef a ON a.rowid = e.caller_rowid "
            "JOIN memberdef b ON b.rowid = e.callee_rowid"
        )
    )
    assert ("Page", "Card", "jsx") in edges, edges
