# SPDX-License-Identifier: MIT
"""Symbol pages (round 3, P1f; round 4, R3).

Owner 2026-11-15: links should be DOSSIER REFERENCES — a symbol's own page, which in turn links
its source — and the dossier drawn as a "spiderweb" of its links, a way of WALKING SOURCE. Every
symbol the site references (a requirement's implementers, a flow's functions) gets a section on
its FILE's page (`sym-<path>.html#s-<name>`), holding every definition of that name in the file:

  * signature and brief, and a source permalink when one resolves;
  * its callers and callees, each linked to its own section where it has one, and a link to the
    function ON THE REPOSITORY WEB (`map.html#n=`), where the walking happens. Round 4, R3: the
    per-symbol radial ego-graph was replaced by the one repository web (owner 2026-11-16: "the
    spiderweb is not really a true spiderweb");
  * the requirements it implements and the flows it is on;
  * its body, bundled from the file (withheld under `exclude_bodies`).

THE INDEX IS READ DIRECTLY (signature, body extent, resolved call edges) rather than through
`export_dossier`: that engine costs ~76 ms a symbol (measured on clew's own index, 64 symbols,
single and batched), and a site references ~900 — over a minute before rendering starts. A
binding is not a call and a fuzzy edge is a guess, as on the map.

@brief Write symbol pages.
@version 2
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any

from ..query._common import connect, table_exists

## Neighbours listed per side before the rest are counted.
_NEAR = 12
## The most calls a test-to-implementer path is searched across.
## The default path depth when a caller states none; the build passes `wiki.path_depth` (R5-CFG
## C3, 2.0.0 — it was 5 here and 12 on the test page, one question with two answers).
_PATH_DEPTH = 12
## The most body lines a section bundles.
_BODY_LINES = 120


## @brief One definition of a referenced symbol.
## @version 1
@dataclass(frozen=True)
class Definition:
    """@brief Rowid, name, file, signature, brief, body extent. @version 1"""

    rowid: int
    name: str
    file: str
    signature: str
    brief: str
    start: int
    end: int


## @brief The page a file's symbols live on.
## @param rel Repo-relative path.
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-025
def page_for(rel: str) -> str:
    """@brief Page name. @return Name."""
    return "sym-" + re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-")


## @brief A symbol's section link.
## @param name The function.
## @param rel Its file.
## @return The href.
## @version 1
## @req REQ-DDB-WIKI-025
def symbol_href(name: str, rel: str) -> str:
    """ONE SECTION PER NAME PER FILE, holding every definition of it — so a link never needs to
    know which of several same-named definitions it means.

    @brief Href.
    @return Href.
    """
    return f"{page_for(rel)}.html#{anchor(name)}"


## @brief A section's id.
## @param name The function.
## @return The id.
## @version 1
## @dg_internal
def anchor(name: str) -> str:
    """@brief Anchor id. @return Id."""
    return "s-" + re.sub(r"[^\w.-]", "_", name)


## @brief Write a page per file holding the referenced symbols.
## @param db The index.
## @param repo_root The repository (bodies are read from it).
## @param keys (function, file) pairs the site references.
## @param ctx req_of, flows (FlowPage list), rules (Audience), template, commit.
## @param source The Sphinx source directory.
## @return {(function, file): href} of the sections written.
## v2: test functions the evidence names get sections too (P2a).
## v3: `test_functions` is public (the build resolves directly linked tests to draw, P2b).
## v4: and the object list the `clew` domain puts in objects.inv (2.0.0, S8).
## v5: a file page names its owners, unless the audience withholds them (2.0.0, P5).
## @version 5
## @req REQ-DDB-WIKI-025
def symbol_pages(
    db: Path, repo_root: Path, keys: set[tuple[str, str]], ctx: dict[str, Any], source: Path
) -> dict[tuple[str, str], str]:
    """@brief Write sym-*.md. @return Hrefs."""
    with connect(db) as conn:
        tests = test_functions(conn, set(ctx.get("tests") or {}))
        defs = _definitions(conn, keys | tests)
        graph = _Edges(conn)
        owned = _owners_by_file(conn, {d.file for d in defs}, ctx["rules"])
    ctx = {**ctx, "test_keys": tests}
    by_file: dict[str, dict[str, list[Definition]]] = defaultdict(lambda: defaultdict(list))
    for d in defs:
        by_file[d.file][d.name].append(d)
    written = {(n, f) for f, names in by_file.items() for n in names}
    for rel, names in sorted(by_file.items()):
        sections = [
            _section(name, names[name], graph, written, ctx, Path(repo_root))
            for name in sorted(names)
        ]
        text = [
            "---",
            "orphan: true",
            "---",
            "",
            f"# `{rel}`",
            "",
            "```{raw} html",
            *_owners_line(owned.get(rel)),
            *sections,
            "```",
            "",
        ]
        (Path(source) / f"{page_for(rel)}.md").write_text("\n".join(text), encoding="utf-8")
    _write_objects(Path(source), sorted(written, key=lambda k: (k[1], k[0])))
    return {key: symbol_href(*key) for key in written}


## @brief Each written file's owners, unless the audience withholds them.
## @param conn Open connection.
## @param files The files with sections.
## @param rules The audience.
## @return {file: owner names, in rule order}.
## @version 1
## @dg_internal
def _owners_by_file(conn: Any, files: set[str], rules: Any) -> dict[str, list[str]]:
    """P5 (2.0.0): the owners layer on the page a reader opens to ask who to talk to. Empty under
    `exclude_owners`. @brief Read owners. @return Map."""
    from ..query.corpus import file_owners

    if getattr(rules, "exclude_owners", False):
        return {}
    out = {}
    for rel in files:
        names = list(dict.fromkeys(o.owner for o in file_owners(conn, rel) or ()))
        if names:
            out[rel] = names
    return out


## @brief The owners line at the top of a file page.
## @param names Owner names, or None.
## @return HTML lines (none when the file has no owners).
## @version 1
## @dg_internal
def _owners_line(names: list[str] | None) -> list[str]:
    """@brief Owners line. @return Lines."""
    if not names:
        return []
    return [
        f'<p class="owners">Owners: {", ".join(f"<code>{escape(n)}</code>" for n in names)}</p>'
    ]


## @brief The symbol sections, as the `clew` Sphinx domain lists them in objects.inv.
## @param source The Sphinx source directory.
## @param written (function, file) pairs, each one section.
## @return None.
## @version 1
## @dg_internal
def _write_objects(source: Path, written: list[tuple[str, str]]) -> None:
    """S8 (2.0.0): see `_sphinxsymbols`. @brief Write the object list. @return None."""
    import json

    from ._sphinxsymbols import OBJECTS_FILE

    rows = [{"name": n, "file": f, "page": page_for(f), "anchor": anchor(n)} for n, f in written]
    (source / OBJECTS_FILE).write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")


## @brief The test functions the evidence names, found in test code.
## @param conn Open connection.
## @param names Test names.
## @return (function, file) pairs.
## @version 1
## @req REQ-DDB-WIKI-026
def test_functions(conn: Any, names: set[str]) -> set[tuple[str, str]]:
    """A NAME OUTSIDE TEST CODE is not that test: a scenario title or a Catch2 string name has no
    function of that name, and a namesake in product code is not the test.

    @brief Resolve tests.
    @return Keys.
    """
    if not names or not table_exists(conn, "test_scope"):
        return set()
    scope = {r for (r,) in conn.execute("SELECT path_rowid FROM test_scope")}
    out = set()
    for name, rel, prow in conn.execute(
        "SELECT m.name, p.name, p.rowid FROM memberdef m JOIN path p ON p.rowid = "
        "COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function'"
    ):
        if name in names and int(prow) in scope:
            out.add((str(name), str(rel)))
    return out


## @brief Every definition of each referenced (function, file).
## @param conn Open connection.
## @param keys (function, file) pairs.
## @return Definitions.
## @version 1
## @dg_internal
def _definitions(conn: Any, keys: set[tuple[str, str]]) -> list[Definition]:
    """@brief Resolve keys. @return Definitions."""
    out = []
    for name, rel in sorted(keys):
        rows = conn.execute(
            "SELECT m.rowid, m.definition, m.argsstring, m.briefdescription, m.bodystart, "
            "m.bodyend, m.line FROM memberdef m JOIN path p ON p.rowid = "
            "COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
            "WHERE m.kind = 'function' AND m.name = ? AND p.name = ? ORDER BY m.line",
            (name, rel),
        ).fetchall()
        for rowid, definition, args, brief, start, end, line in rows:
            out.append(
                Definition(
                    int(rowid),
                    name,
                    rel,
                    f"{definition or ''}{args or ''}".strip(),
                    " ".join(re.sub(r"<[^>]+>", " ", str(brief or "")).split()),
                    int(start or line or 0),
                    int(end or 0),
                )
            )
    return out


## @brief The resolved call graph, loaded once.
## @version 1
class _Edges:
    """@brief Callers, callees and names of every function. @version 1"""

    ## @brief Load edges and names.
    ## @param conn Open connection.
    ## @version 1
    ## @dg_internal
    def __init__(self, conn: Any) -> None:
        """A BINDING IS NOT A CALL and a fuzzy edge is a guess: neither is drawn.

        @brief Load.
        @return None.
        """
        self.callers: dict[int, set[int]] = defaultdict(set)
        self.callees: dict[int, set[int]] = defaultdict(set)
        self.names: dict[int, tuple[str, str]] = {}
        self.by_key: dict[tuple[str, str], list[int]] = defaultdict(list)
        for rowid, name, rel in conn.execute(
            "SELECT m.rowid, m.name, p.name FROM memberdef m JOIN path p ON p.rowid = "
            "COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function'"
        ):
            self.names[int(rowid)] = (str(name), str(rel))
            self.by_key[(str(name), str(rel))].append(int(rowid))
        if table_exists(conn, "call_edges"):
            for a, b in conn.execute(
                "SELECT DISTINCT caller_rowid, callee_rowid FROM call_edges "
                "WHERE source != 'binding' AND confidence != 'fuzzy'"
            ):
                if int(a) != int(b):
                    self.callees[int(a)].add(int(b))
                    self.callers[int(b)].add(int(a))

    ## @brief Named neighbours of a function in one direction, sorted.
    ## @param rowid The function.
    ## @param side `callers` or `callees`.
    ## @return (name, file) pairs.
    ## @version 1
    ## @dg_internal
    def around(self, rowid: int, side: str) -> list[tuple[str, str]]:
        """@brief Neighbours. @return Pairs."""
        edges = self.callers if side == "callers" else self.callees
        return sorted({self.names[r] for r in edges.get(rowid, ()) if r in self.names})

    ## @brief The rowids a (name, file) pair names.
    ## @param key (function, file).
    ## @return Rowids.
    ## @version 1
    ## @dg_internal
    def rowids(self, key: tuple[str, str]) -> list[int]:
        """@brief Look up. @return Rowids."""
        return self.by_key.get(key, [])


## @brief One name's section: every definition of it in the file.
## @param name The function.
## @param defs Its definitions.
## @param graph The call graph.
## @param written Keys that have sections (graph nodes link to them).
## @param ctx The page context.
## @param repo_root The repository.
## @return HTML.
## v2: a test's section adds what it tests (round 3, P2a).
## v3: neighbours and the web link replace the ego-graph (round 4, R3).
## @version 3
## @dg_internal
def _section(
    name: str,
    defs: list[Definition],
    graph: _Edges,
    written: set[tuple[str, str]],
    ctx: dict[str, Any],
    repo_root: Path,
) -> str:
    """@brief Section. @return HTML."""
    from .htmltable import md_title, source_url

    key = (name, defs[0].file)
    reqs = sorted(set(ctx["req_of"].get(key, ())))
    flows = sorted((p for p in ctx["flows"] if key in p.functions), key=lambda p: p.title)
    parts = [f'<section class="symbol" id="{anchor(name)}"><h2><code>{escape(name)}</code></h2>']
    for d in defs:
        url = source_url(ctx["template"], ctx["commit"], d.file, max(d.start, 1))
        where = f"{escape(d.file)}:{d.start}"
        if url:
            where = f'<a href="{escape(url)}">{where}</a>'
        parts.append(
            f'<pre class="sig">{escape(d.signature or name)}</pre>'
            + (f"<p>{escape(d.brief)}</p>" if d.brief else "")
            + f'<p class="where">{where}</p>'
            + _near(d, graph, written)
        )
        if key in ctx.get("test_keys", ()):
            parts.append(_test_block(d, graph, ctx, repo_root))
        if not ctx["rules"].exclude_bodies:
            parts.append(_body(repo_root, d))
    if reqs:
        parts.append(
            "<h4>Requirements</h4><p>"
            + " ".join(
                f'<a class="req-badge" href="requirements.html#{escape(r)}">{escape(r)}</a>'
                for r in reqs
            )
            + "</p>"
        )
    if flows:
        parts.append(
            '<h4>Flows</h4><ul class="modal-list">'
            + "".join(
                f'<li><a href="{escape(p.name)}.html">{md_title(p.title)}</a></li>' for p in flows
            )
            + "</ul>"
        )
    return "".join(parts) + "</section>"


## @brief What a test tests: its assertions, result, verified requirements and call paths.
## @param d The test's definition.
## @param graph The call graph.
## @param ctx The page context (tests, implementers, rules).
## @param repo_root The repository.
## @return HTML.
## v2: one path depth, wiki.path_depth (2.0.0, R5-CFG C3)
## @version 2
## @dg_internal
def _test_block(d: Definition, graph: _Edges, ctx: dict[str, Any], repo_root: Path) -> str:
    """ASSERTIONS ARE SOURCE TEXT, withheld under `exclude_bodies`; the verified requirements and
    paths are the index's facts and stay.

    @brief Test block.
    @return HTML.
    """
    from .testfacts import assertions, verifies_block

    facts = ctx["tests"][d.name]
    paths = {
        req: _path(
            graph, d.rowid, ctx["implementers"].get(req, set()), ctx.get("path_depth", _PATH_DEPTH)
        )
        for req, _kind in facts.verifies
    }
    out = verifies_block(facts, {r: p for r, p in paths.items() if p})
    lines = _lines(repo_root, d)
    if lines and not ctx["rules"].exclude_bodies:
        found = assertions(lines)
        if found:
            items = "".join(f"<li><code>{escape(a)}</code></li>" for a in found)
            out = f'<h4>Checks</h4><ul class="asserts">{items}</ul>' + out
    return f'<div class="test-facts">{out}</div>'


## @brief The shortest call path from a test to any implementer of a requirement.
## @param graph The call graph.
## @param start The test's rowid.
## @param targets The implementers' (function, file) pairs.
## @param depth The most calls searched across.
## @return Function names along the path, or [] when none is found within the depth.
## v2 (round 4, R7): the depth is a parameter; test pages search as far as the extent reaches.
## @version 2
## @dg_internal
def _path(
    graph: _Edges, start: int, targets: set[tuple[str, str]], depth: int = _PATH_DEPTH
) -> list[str]:
    """BREADTH-FIRST over resolved calls, at most `_PATH_DEPTH` hops: the path a reader can walk
    from the test to the code it reaches.

    @brief Path.
    @return Names.
    """
    goal = {r for key in targets for r in graph.rowids(key)}
    prev: dict[int, int] = {start: start}
    frontier = [start]
    for _ in range(depth):
        nxt = []
        for node in frontier:
            for callee in sorted(graph.callees.get(node, ())):
                if callee in prev:
                    continue
                prev[callee] = node
                if callee in goal:
                    return _unwind(graph, prev, callee)
                nxt.append(callee)
        frontier = nxt
    return []


## @brief The names along a found path.
## @param graph The call graph.
## @param prev Predecessors.
## @param end The last node.
## @return Names, first to last.
## @version 1
## @dg_internal
def _unwind(graph: _Edges, prev: dict[int, int], end: int) -> list[str]:
    """@brief Unwind. @return Names."""
    out = [end]
    while prev[out[-1]] != out[-1]:
        out.append(prev[out[-1]])
    return [graph.names[r][0] for r in reversed(out)]


## @brief A definition's place on the web, and its neighbours linked when they have sections.
## @param d The definition.
## @param graph The call graph.
## @param written Keys with sections.
## @return HTML.
## Round 4, R3: replaces the per-symbol ego-graph; the repository web is the one graph view.
## @version 1
## @dg_internal
def _near(d: Definition, graph: _Edges, written: set[tuple[str, str]]) -> str:
    """@brief Neighbours. @return HTML."""
    from urllib.parse import quote

    def items(pairs: list[tuple[str, str]]) -> str:
        shown = [
            f'<a href="{symbol_href(n, f)}">{escape(n)}</a>'
            if (n, f) in written
            else f"<code>{escape(n)}</code>"
            for n, f in pairs[:_NEAR]
        ]
        more = f" and {len(pairs) - _NEAR} more" if len(pairs) > _NEAR else ""
        return (", ".join(shown) + more) or "none"

    web = f"map.html#n={quote(d.name)}@{quote(d.file)}"
    return (
        f'<div class="near"><p><a href="{web}">Show on the map →</a></p>'
        f"<p><b>Called by</b> {items(graph.around(d.rowid, 'callers'))}</p>"
        f"<p><b>Calls</b> {items(graph.around(d.rowid, 'callees'))}</p></div>"
    )


## @brief A definition's body, bundled from the file, cut at `_BODY_LINES` with the cut said.
## @param repo_root The repository.
## @param d The definition.
## @return HTML ("" when the file cannot be read or the extent is unknown).
## v2: the extent read and checked by `_lines`, shared with the test block.
## v3: collapsed in a details element (2.0.0, P5)
## @version 3
## @dg_internal
def _body(repo_root: Path, d: Definition) -> str:
    """END 0 IS EXTENT UNKNOWN, never "covers nothing": no body is bundled rather than a guess.
    A STALE EXTENT IS SAID: when the recorded lines no longer name the function (the file changed
    after the index was built), the section says so instead of bundling someone else's code.

    @brief Body.
    @return HTML.
    """
    lines = _lines(repo_root, d)
    if lines is None:
        return ""
    if not lines:
        return (
            '<p class="not-measured">The index is older than this file: the lines it records '
            "no longer hold this function. Refresh the index to bundle its body.</p>"
        )
    body = lines[:_BODY_LINES]
    more = d.end - d.start + 1 - len(body)
    note = f'<p class="none">{more} more lines, not shown</p>' if more > 0 else ""
    shown = f"{len(body)} line{'s' if len(body) != 1 else ''}"
    ## P5 (2.0.0): COLLAPSED. A closed <details> is parsed but not laid out, so a file page of
    ## hundreds of symbols no longer lays out every body on load. Inline rather than fetched: the
    ## site is opened as a FILE (`clew wiki open`), where a fetch is refused.
    return (
        f'<details class="body"><summary>Source · {shown}</summary>'
        f'<pre class="body">{escape(chr(10).join(body))}</pre></details>{note}'
    )


## @brief A definition's lines: None when unknown or unreadable, [] when stale.
## @param repo_root The repository.
## @param d The definition.
## @return Lines, [] or None.
## @version 1
## @dg_internal
def _lines(repo_root: Path, d: Definition) -> list[str] | None:
    """THE RECORDED EXTENT MUST STILL NAME THE FUNCTION in its first lines, else the file changed
    after the index was built and the lines are someone else's.

    @brief Read the extent.
    @return Lines.
    """
    if not d.start or not d.end or d.end < d.start:
        return None
    try:
        lines = (repo_root / d.file).read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    body = lines[d.start - 1 : d.end]
    if not any(re.search(rf"\b{re.escape(d.name)}\b", line) for line in body[:4]):
        return []
    return body
