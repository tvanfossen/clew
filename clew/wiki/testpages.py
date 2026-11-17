# SPDX-License-Identifier: MIT
"""A page per test: what it checks, what it reaches, and what the run said (round 4, R6/R7).

OWNER 2026-11-16: "tests dont link through properly from reqs", "a wall of tests in a giant bullet
list is also not very readable", and "at minimum, I want to see visually what a test is PROVING
red". Each test the evidence names gets ITS OWN PAGE:

  * the RESULT the packaged run recorded (JUnit), and its failure message, in red, when it failed;
  * its CHECKS — the assertion statements in its body, per framework (`testfacts.assertions`);
  * WHAT IT REACHES, drawn: one chain per requirement, from the test through the calls it makes to
    the requirement's implementer, tinted by the result — the code a failing check would point at;
  * the requirements it is linked to, how, and its EXTENT (which implementers it exercises);
  * mutation outcomes naming it, when records were given.

REACHING IS NOT PROVING, and the page says so: a test can execute code whose behaviour none of its
checks observe (pseudo-tested code — Niedermayr, Juergens & Wagner 2016; checked coverage — Schuler
& Zeller 2011). Only a mutation record (`wiki.tests.mutations`) shows a test FAILING when its
implementer breaks (DeMillo, Lipton & Sayward 1978); without one, the chain is labelled "reaches".

@brief Write one page per test.
@version 2
"""

from __future__ import annotations

import re
from collections import defaultdict
from html import escape
from pathlib import Path
from typing import Any

from ..query._common import connect, table_exists
from .htmltable import source_url, tag
from .symbols import Definition, _Edges, _lines, _path, symbol_href

## The most requirement chains drawn before the rest are counted.
_MAX_CHAINS = 12
## The most calls a chain is searched across: the extent is transitive, so the chain is too.
_CHAIN_DEPTH = 12
## Chain geometry.
_H, _GAP, _ROW = 30, 22, 46


## @brief The page name of a test.
## @param name The test.
## @param rel Its file.
## @return The page name (without .html).
## @version 1
## @req REQ-DDB-WIKI-026
def test_page_of(name: str, rel: str) -> str:
    """@brief Page name. @return Name."""
    return "test-" + re.sub(r"[^A-Za-z0-9_]+", "-", f"{rel}-{name}").strip("-")


## @brief Write a page per test the evidence names.
## @param db The index.
## @param repo_root The repository.
## @param ctx tests (name → facts), implementers (req → keys), results (name → CaseResult),
##        rules, template, commit, extent (req → {test: implementers}).
## @param source The Sphinx source directory.
## @return {test name: its page href}.
## v2: tests resolved by framework (Catch2 / GoogleTest macros), not by function name.
## @version 2
## @req REQ-DDB-WIKI-026
def test_pages(db: Path, repo_root: Path, ctx: dict[str, Any], source: Path) -> dict[str, str]:
    """ONE PAGE PER NAME: every definition of a test name in test code is drawn on it, so a link
    from a requirement never has to know which of two namesakes it meant.

    @brief Write test-*.md.
    @return Hrefs.
    """
    with connect(db) as conn:
        defs = _test_definitions(conn, set(ctx["tests"]))
        graph = _Edges(conn)
    by_name: dict[str, list] = defaultdict(list)
    for d in defs:
        by_name[d.name].append(d)
    hrefs = {}
    for name, ds in sorted(by_name.items()):
        page = test_page_of(name, ds[0].file)
        body = "".join(_definition(d, graph, ctx, Path(repo_root)) for d in ds)
        text = [
            "---",
            "orphan: true",
            "---",
            "",
            f"# {name}",
            "",
            "```{raw} html",
            '<p class="crumbs"><a href="requirements.html">← Requirements</a></p>',
            f'<div class="test-page">{_result(name, ctx)}{_replay(name, ctx)}{body}'
            f"{_requirements(name, ctx)}</div>",
            "```",
            "",
        ]
        (Path(source) / f"{page}.md").write_text("\n".join(text), encoding="utf-8")
        hrefs[name] = f"{page}.html"
    return hrefs


## @brief Every definition, in test code, of a test the evidence names — by framework.
## @param conn Open connection.
## @param names Test names (a function's, or a framework's: a Catch2 scenario's string).
## @return Definitions named by the test's own name.
## @version 1
## @req REQ-DDB-WIKI-026
def _test_definitions(conn: object, names: set[str]) -> list[Definition]:
    """RESOLVED AS THE EVIDENCE RESOLVES THEM (`frameworks.recognise_test`): a Catch2 `SCENARIO` /
    `TEST_CASE`, a GoogleTest `TEST`, a Boost case is a macro row in the index, named by its
    string. Found on entropic: 2,009 Catch2 tests and 11 pages, because only functions literally
    named after the test were looked for. Test code only — a namesake in product code is not it.

    @brief Resolve tests to definitions.
    @return Definitions.
    """
    from .frameworks import recognise_test

    if not names or not table_exists(conn, "test_scope"):
        return []
    rows = conn.execute(
        "SELECT m.rowid, m.name, COALESCE(m.argsstring, ''), p.name, m.definition, "
        "m.briefdescription, m.bodystart, m.bodyend, m.line FROM memberdef m JOIN path p "
        "ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function' "
        "AND p.rowid IN (SELECT path_rowid FROM test_scope) ORDER BY p.name, m.line"
    )
    out = []
    for rowid, name, args, rel, definition, brief, start, end, line in rows:
        test = recognise_test(str(name), str(args), str(rel))
        if test and test[0] in names:
            out.append(
                Definition(
                    int(rowid),
                    test[0],
                    str(rel),
                    f"{definition or ''}{args or ''}".strip(),
                    re.sub(r"<[^>]+>", " ", str(brief or "")).strip(),
                    int(start or line or 0),
                    int(end or 0),
                )
            )
    return out


## @brief The file page a test's definition is on.
## @param d The definition.
## @return Href.
## @version 1
## @dg_internal
def _source_page(d: Definition) -> str:
    """@brief Href. @return Href."""
    return symbol_href(d.name, d.file).split("#", 1)[0]


## @brief A link to the test's flow, and whether a recorded run is drawn on it.
## @param name The test.
## @param ctx The page context (flow_of, traced).
## @return HTML ("" when the test has no flow page).
## @version 1
## @dg_internal
def _replay(name: str, ctx: dict[str, Any]) -> str:
    """A PACKAGED RUN IS REPLAYED ON THE FLOW (owner 2026-11-16: "take run results/logs that were
    included/packaged with it and replay them"): the expected calls, the calls the run made, and
    each assertion as a checkpoint where it was checked — red at the one that failed.

    @brief Replay link.
    @return HTML.
    """
    page = (ctx.get("flow_of") or {}).get(name)
    if not page:
        return ""
    if name in (ctx.get("traced") or set()):
        words = "Replay its recorded run on its flow: the calls it made and each check, in order"
    else:
        words = "Its flow: the calls it is expected to make (no recorded run was packaged)"
    return f'<p class="replay"><a href="{escape(page)}.html">{words} →</a></p>'


## @brief The run's verdict on a test, and its failure message.
## @param name The test.
## @param ctx The page context.
## @return HTML.
## @version 1
## @dg_internal
def _result(name: str, ctx: dict[str, Any]) -> str:
    """ABSENT IS NOT PASSED: a test no packaged report names reads "not in the run".

    @brief Result banner.
    @return HTML.
    """
    found = (ctx.get("results") or {}).get(name)
    status = found.status if found else "absent"
    words = {
        "passed": "Passed in the packaged run.",
        "failed": "FAILED in the packaged run.",
        "error": "ERRORED in the packaged run.",
        "skipped": "Skipped in the packaged run.",
        "absent": "Not in the packaged run: no test report names it.",
    }
    message = escape(found.message) if found and found.message else ""
    detail = f'<pre class="fail-msg">{message}</pre>' if message else ""
    return (
        f'<div class="result-banner r-{status}">{tag(status)} {words.get(status, status)}'
        f"{detail}</div>"
    )


## @brief One definition: where it is, its checks, and the chains to what it reaches.
## @param d The definition.
## @param graph The call graph.
## @param ctx The page context.
## @param repo_root The repository.
## @return HTML.
## v2: links its file's page.
## @version 2
## @dg_internal
def _definition(d: Any, graph: _Edges, ctx: dict[str, Any], repo_root: Path) -> str:
    """@brief Definition block. @return HTML."""
    from .testfacts import assertions

    url = source_url(ctx["template"], ctx["commit"], d.file, max(d.start, 1))
    where = f"{escape(d.file)}:{d.start}"
    where = f'<a href="{escape(url)}">{where}</a>' if url else where
    out = f'<p class="where">{where} · <a href="{_source_page(d)}">its file\'s page</a></p>'
    lines = _lines(repo_root, d)
    checks = assertions(lines) if lines and not ctx["rules"].exclude_bodies else []
    if checks:
        items = "".join(f"<li><code>{escape(a)}</code></li>" for a in checks)
        out += f'<h2>What it checks ({len(checks)})</h2><ol class="asserts">{items}</ol>'
    out += _proof(d, graph, ctx, len(checks))
    return out


## @brief The chains from a test to each linked requirement's implementer, drawn.
## @param d The test's definition.
## @param graph The call graph.
## @param ctx The page context.
## @param checks How many checks the test makes.
## @return HTML.
## @version 1
## @dg_internal
def _proof(d: Any, graph: _Edges, ctx: dict[str, Any], checks: int) -> str:
    """ONE ROW PER REQUIREMENT: test → the calls it makes → the implementer. A requirement it is
    linked to with no call path (a tag, a mapping, a scenario) is listed, never drawn as a path
    that does not exist.

    @brief Proof chains.
    @return HTML.
    """
    facts = ctx["tests"][d.name]
    found = (ctx.get("results") or {}).get(d.name)
    status = found.status if found else "absent"
    chains = []
    for req, kind in facts.verifies:
        path = _path(graph, d.rowid, ctx["implementers"].get(req, set()), _CHAIN_DEPTH)
        chains.append((req, kind, path))
    drawn = [c for c in chains if c[2]][:_MAX_CHAINS]
    lead = (
        "<p>Each row runs from this test, through the calls it makes, to the code a requirement "
        "names. If that code breaks, the test's checks are what should catch it. "
        "<strong>Reaching is not proving:</strong> a check only proves what it observes. "
        + (
            "Mutation records below say which breaks this test actually caught."
            if facts.mutations
            else "No mutation records were given, so these rows say what the test REACHES."
        )
        + "</p>"
    )
    svg = _chains_svg(d.name, drawn, status, checks) if drawn else ""
    rest = len([c for c in chains if c[2]]) - len(drawn)
    more = f"<p>and {rest} more requirement paths, listed below.</p>" if rest > 0 else ""
    return f"<h2>What it reaches</h2>{lead}{svg}{more}" if chains else ""


## @brief Draw the chains: the test once on the left, one row per requirement to its right.
## @param test The test's name.
## @param chains (requirement, link kind, path names) with a path.
## @param status The run's result.
## @param checks How many checks the test makes.
## @return SVG.
## @version 1
## @dg_internal
def _chains_svg(test: str, chains: list, status: str, checks: int) -> str:
    """A LONG CHAIN IS SHORTENED IN THE MIDDLE, never at its ends: the implementer is what a reader
    needs; "… 4 calls …" stands for what was folded. The test is drawn ONCE, its checks counted
    on it, and every row branches from it.

    @brief Chains SVG.
    @return SVG.
    """
    label = f"{test} · {checks} checks" if checks else test
    tw = _width(label)
    height = max(len(chains) * _ROW, _ROW) + 8
    ty = height / 2 - _H / 2
    parts = [
        f'<g class="pn test"><rect x="0" y="{ty:.0f}" width="{tw:.0f}" height="{_H}" rx="8"/>'
        f'<text x="10" y="{ty + 19:.0f}">{escape(label)}</text></g>'
    ]
    width = 0.0
    for i, (req, kind, path) in enumerate(chains):
        rest = path[1:]
        names = rest if len(rest) <= 4 else [rest[0], f"… {len(rest) - 2} calls …", rest[-1]]
        y = i * _ROW + 8
        x = tw + 3 * _GAP
        parts.append(
            f'<path class="pe" d="M{tw:.0f} {ty + _H / 2:.0f} C{tw + 1.5 * _GAP:.0f} '
            f'{ty + _H / 2:.0f} {tw + 1.5 * _GAP:.0f} {y + _H / 2:.0f} {x:.0f} {y + _H / 2:.0f}" '
            'marker-end="url(#pa)"/>'
        )
        for j, name in enumerate(names):
            w = _width(name)
            role = "impl" if j == len(names) - 1 else "mid"
            parts.append(
                f'<g class="pn {role}"><rect x="{x:.0f}" y="{y}" width="{w:.0f}" height="{_H}" '
                f'rx="8"/><text x="{x + 10:.0f}" y="{y + 19}">{escape(name)}</text></g>'
            )
            if j < len(names) - 1:
                parts.append(
                    f'<line class="pe" x1="{x + w:.0f}" y1="{y + _H / 2}" '
                    f'x2="{x + w + _GAP:.0f}" y2="{y + _H / 2}" marker-end="url(#pa)"/>'
                )
            x += w + _GAP
        tag_text = f"{req} · {kind}"
        parts.append(
            f'<a href="req-{escape(req)}.html"><text class="preq" x="{x + 2:.0f}" '
            f'y="{y + 19}">{escape(tag_text)}</text></a>'
        )
        width = max(width, x + _width(tag_text))
    return (
        f'<div class="proof-wrap"><svg class="proof s-{escape(status)}" xmlns="http://www.w3.org/'
        f'2000/svg" width="{width:.0f}" height="{height:.0f}" viewBox="0 0 {width:.0f} '
        f'{height:.0f}" role="img" aria-label="What {escape(test)} reaches"><defs><marker id="pa" '
        'viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" '
        'orient="auto"><path d="M0 0L10 5L0 10z"/></marker></defs>'
        f"{''.join(parts)}</svg></div>"
    )


## @brief The drawn width of a label in the 12px monospace the chains use.
## @param label The label.
## @return Width in px.
## @version 1
## @dg_internal
def _width(label: str) -> float:
    """@brief Width. @return Px."""
    return 22 + 7.6 * len(label)


## @brief The requirements a test is linked to, with how and how much.
## @param name The test.
## @param ctx The page context.
## @return HTML.
## @version 1
## @dg_internal
def _requirements(name: str, ctx: dict[str, Any]) -> str:
    """@brief Requirement table. @return HTML."""
    facts = ctx["tests"][name]
    rows = "".join(
        f'<tr><td><a href="req-{escape(req)}.html">{escape(req)}</a></td>'
        f'<td><span class="via via-{kind}">{kind}</span></td>'
        f"<td>{_extent(ctx, req, name)}</td></tr>"
        for req, kind in facts.verifies
    )
    out = (
        f"<h2>Requirements ({len(facts.verifies)})</h2>"
        '<table class="clew"><thead><tr><th>requirement</th><th>linked by</th>'
        f"<th>implementers exercised</th></tr></thead><tbody>{rows}</tbody></table>"
    )
    if facts.mutations:
        items = "".join(
            f'<li><code>{escape(m)}</code> <span class="mut-{escape(o)}">{escape(o)}</span></li>'
            for m, o in facts.mutations
        )
        out += f"<h2>Mutations</h2><ul>{items}</ul>"
    return out


## @brief "k of n: names" for one test on one requirement.
## @param ctx The page context.
## @param req The requirement.
## @param test The test.
## @return HTML.
## @version 1
## @dg_internal
def _extent(ctx: dict[str, Any], req: str, test: str) -> str:
    """@brief Extent. @return HTML."""
    known = ctx["extent"].get(req)
    total = len(ctx["implementers"].get(req, ()))
    if known is None or test not in known:
        return '<span class="none">unknown</span>'
    names = known[test]
    shown = ", ".join(f"<code>{escape(n)}</code>" for n in names[:4])
    more = f" and {len(names) - 4} more" if len(names) > 4 else ""
    return f"{len(names)} of {total}" + (f": {shown}{more}" if names else "")
