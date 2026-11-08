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
from clew.jsast import harvest_calls, harvest_definitions

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


_WRAPPED = b"""\
import React, {forwardRef, memo} from 'react';
export const Header = forwardRef<Ref, Props>(({title}, ref) => <div ref={ref}>{title}</div>);
export const Row = memo(function Row({x}) { return <span>{x}</span>; });
export const Card = React.memo(React.forwardRef((props, ref) => <div ref={ref} />));
const getStyleSheet = makeStyleSheetFromTheme((theme) => ({color: theme.x}));
const Gutter = typedMemo((props: Props) => <View />);
export const debounced = debounce((ids: string[]) => { return ids; }, 200);
const getMatchTerm = (() => {
    let last = '';
    return (value: string) => { last = value; return last; };
})();
const notAFunction = compute(1, 2);
const passedByName = wrap(Header);
const ids = posts.map((p) => p.id);
const ready = load().then((r) => r.ok);
const handle = setTimeout(() => tick(), 10);
const {result} = renderHook(() => useThing());
const displayName = channel.pipe(map((c) => c.displayName));
const subscription = manager.observe().subscribe((state) => state);
"""


## @brief A name bound to a wrapper call around a function literal is that function.
## @return None.
## @version 2
def test_a_component_wrapped_in_forwardref_or_memo_is_a_definition() -> None:
    """FOUND ON THE REAL TREE, not on a fixture. The mattermost-mobile acceptance rubric asks where
    `NavigationHeader` is rendered; eight files render it, and the index recorded NO callers —
    because `const NavigationHeader = forwardRef<SearchRef, Props>((...) => {...})` binds the
    name to a CALL, and only a binding to an arrow or function expression counted. With no
    definition there was nothing for a `jsx` edge to resolve to.

    VERSION 2 — THE OWNER'S RULING REPLACED THE ALLOWLIST (2026-11-02). Version 1 accepted
    React's own wrappers only and asserted that a style factory stays out. A TypeScript audit then
    found the allowlist missing real definitions — `typedMemo` components, `debounce`d and
    `preventDoubleTap`ped handlers — and the owner ruled for the general rule: a name bound to a
    call whose first argument is a function literal IS that function, whatever the wrapper is
    called. That makes the 466 `getStyleSheet = makeStyleSheetFromTheme(...)` bindings on
    mattermost-mobile function rows too; they are real callables, one per file. A function bound
    by an immediately-invoked expression is the function it returns.

    Still NOT a definition: a call with no function-literal argument (`compute(1, 2)`), and a
    function passed BY NAME (`wrap(Header)`), whose definition is `Header`'s own.

    MEASURED, then refined, without returning to an alias list. The first cut added 1,480 rows on
    mattermost-mobile against ~475 expected: `const ids = posts.map((p) => p.id)` binds an ARRAY,
    `setTimeout(() => ...)` a handle, `{result} = renderHook(...)` a destructured value. A
    callback CONSUMED by a call that returns something else is not the binding's function; the
    consumers excluded are fixed by the ECMAScript and DOM specifications (array/promise methods,
    timers), not by any project's naming, and a pattern is not a name.

    AND A METHOD ON A LOCAL VALUE IS NOT A WRAPPER. `channel.pipe(map((c) => ...))` binds an
    Observable and `x.subscribe(fn)` a Subscription — RxJS, 30-odd rows on that tree. Nesting
    cannot tell them apart from `memo(forwardRef(fn))`; the CALLEE can. A wrapper is a free
    function (`memo`, `debounce`) or a member of an IMPORTED module (`React.memo`), and which names
    the file imports is read from its own import statements.

    @brief Wrapped bindings are definitions; plain call results are not.
    @return None.
    @version 2
    """
    out = harvest_definitions(lps.parse_tree("tsx", _WRAPPED), _WRAPPED)
    names = sorted(f["name"] for f in out["functions"])
    assert names == [
        "Card",
        "Gutter",
        "Header",
        "Row",
        "debounced",
        "getMatchTerm",
        "getStyleSheet",
    ], names


## @brief A `forwardRef` component's renderer is its `jsx` caller.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_a_forwardref_component_has_its_renderer_as_a_jsx_caller(tmp_path: Path) -> None:
    """@brief "Where is NavigationHeader used" is answerable.
    @return None.
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src/header.tsx").write_text(
        "import {forwardRef} from 'react';\n"
        "const Header = forwardRef((props, ref) => <div ref={ref} />);\n"
        "export default Header;\n",
        encoding="utf-8",
    )
    (repo / "src/page.tsx").write_text(
        "import Header from './header';\nexport function Page() { return <Header />; }\n",
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
    assert ("Page", "Header", "jsx") in edges, edges
