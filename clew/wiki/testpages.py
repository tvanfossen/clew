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
& Zeller 2011). Only a mutation record (`tests.mutations`) shows a test FAILING when its
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
from .htmltable import plural, source_url, tag
from .testfacts import TestFacts as _Facts
from .symbols import _PATH_DEPTH, Definition, _Edges, _lines, _path, anchor, symbol_href

## The most requirement chains drawn before the rest are counted.
_MAX_CHAINS = 12
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
## v3 (round 5): what it exercises — its slices of the master flows, from per-test coverage.
## v4: each definition's own slices (2.0.0, W11)
## v5: tests category (2.0.0, owner Q/A 2026-11-20)
## v6: call flow plays in call order with briefs (X-3)
## v7: card at page level (owner review 3)
## v8: UX review group E (owner Q/A 2026-11-22)
## v9: the test flowchart (2.2, F2)
## @version 9
## @req REQ-DDB-WIKI-026
def test_pages(db: Path, repo_root: Path, ctx: dict[str, Any], source: Path) -> dict[str, str]:
    """ONE PAGE PER NAME: every definition of a test name in test code is drawn on it, so a link
    from a requirement never has to know which of two namesakes it meant.

    @brief Write test-*.md.
    @return Hrefs.
    """
    from .testfacts import TestFacts

    ## OWNER Q/A 2026-11-20: `linked` (default) is the tests the evidence names, implicit links
    ## included; `all` adds every recognised test; `none` writes no per-test page.
    mode = ctx.get("test_pages", "linked")
    if mode == "none":
        return {}
    from .entities import _briefs

    with connect(db) as conn:
        defs = _test_definitions(conn, None if mode == "all" else set(ctx["tests"]))
        graph = _Edges(conn)
        ## X-3: what each function does, for the call-flow boxes.
        ctx = {**ctx, "briefs": _briefs(conn)}
        ## 2.2: each test's declared failure modes, for its flowchart.
        from .flowchart import load_modes

        ctx = {**ctx, "modes": load_modes(conn)}
    ## An unlinked test (only under `all`) has no evidence facts: absent, no requirement.
    ctx = {**ctx, "tests": {**{d.name: TestFacts() for d in defs}, **ctx["tests"]}}
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
            ## E-21: the trail this page sits in — Tests › its file — not Requirements.
            f'<p class="crumbs"><a href="tests.html">Tests</a> › <code>{escape(ds[0].file)}</code></p>',
            f'<div class="test-page">{_result(name, ctx)}{_replay(name, ctx)}'
            ## OWNER REVIEW 3: WHY it exists and WHAT it checks, before anything it ran.
            f"{''.join(_card(d, graph, ctx, Path(repo_root)) for d in ds)}"
            f"{_exercises(name, ctx, ds)}{body}"
            f"{_requirements(name, ctx)}</div>",
            "```",
            "",
        ]
        (Path(source) / f"{page}.md").write_text("\n".join(text), encoding="utf-8")
        hrefs[name] = f"{page}.html"
    return hrefs


## @brief Every definition, in test code, of a test the evidence names — by framework.
## @param conn Open connection.
## @param names Test names (a function's, or a framework's: a Catch2 scenario's string), or None
##   for every test the index recognises.
## @return Definitions named by the test's own name.
## v2: test code from test_scope and declared shapes (2.0.0, P4 W1)
## v3 (2.0.0, owner Q/A 2026-11-20): None = every recognised test (`test_pages: all`, the Tests tab).
## @version 3
## @req REQ-DDB-WIKI-026
def _test_definitions(conn: object, names: set[str] | None) -> list[Definition]:
    """RESOLVED AS THE EVIDENCE RESOLVES THEM (`frameworks.recognise_test`): a Catch2 `SCENARIO` /
    `TEST_CASE`, a GoogleTest `TEST`, a Boost case is a macro row in the index, named by its
    string. Found on entropic: 2,009 Catch2 tests and 11 pages, because only functions literally
    named after the test were looked for. Test code only — a namesake in product code is not it.

    @brief Resolve tests to definitions.
    @return Definitions.
    """
    from .frameworks import TestRecognizer

    if names is not None and not names or not table_exists(conn, "test_scope"):
        return []
    rows = conn.execute(
        "SELECT m.rowid, m.name, COALESCE(m.argsstring, ''), p.name, m.definition, "
        "m.briefdescription, m.bodystart, m.bodyend, m.line FROM memberdef m JOIN path p "
        "ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) WHERE m.kind = 'function' "
        "AND p.rowid IN (SELECT path_rowid FROM test_scope) ORDER BY p.name, m.line"
    )
    out = []
    for rowid, name, args, rel, definition, brief, start, end, line in rows:
        test = TestRecognizer.for_conn(conn)(str(name), str(args), str(rel))
        if test and (names is None or test[0] in names):
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
## @utility
def _source_page(d: Definition) -> str:
    """@brief Href. @return Href."""
    return symbol_href(d.name, d.file).split("#", 1)[0]


## @brief A link to the test's flow, and whether a recorded run is drawn on it.
## @param name The test.
## @param ctx The page context (flow_of, traced).
## @return HTML ("" when the test has no recorded run).
## v2 (round 5): only a traced test has a flow of its own, so only a replay is linked.
## @version 2
## @utility
def _replay(name: str, ctx: dict[str, Any]) -> str:
    """A PACKAGED RUN IS REPLAYED ON THE FLOW (owner 2026-11-16: "take run results/logs that were
    included/packaged with it and replay them"): the expected calls, the calls the run made, and
    each assertion as a checkpoint where it was checked — red at the one that failed.

    @brief Replay link.
    @return HTML.
    """
    page = (ctx.get("flow_of") or {}).get(name)
    if not page or name not in (ctx.get("traced") or set()):
        return ""
    words = "Replay its recorded run on its flow: the calls it made and each check, in order"
    return f'<p class="replay"><a href="{escape(page)}.html">{words} →</a></p>'


## How many of a test's master-flow slices are drawn on its page by default (`wiki.test_slices`);
## the rest are links. OWNER Q/A 2026-11-20 (after P6): 3 drawn cost 84 MB on clew's own site.
_SLICES_DRAWN = 1


## @brief What a test exercises: its slices of the master flows.
## @param name The test.
## @param ctx The build context (`slices`: {test key: [(flow page, slice)]}).
## @param defs The test's definitions on this page (each has a `file`).
## @return HTML, or "" when no master flow holds a step it ran.
## v2 (2.0.0, W11): slices are keyed `file::name`; each definition's are drawn under its file.
## v3: slice cap (owner Q/A 2026-11-20, after P6)
## v4: slices play (W-6)
## v5: call flow plays in call order with briefs (X-3)
## @version 5
## @req REQ-DDB-WIKI-041
def _exercises(name: str, ctx: dict[str, Any], defs: list | None = None) -> str:
    """OWNER 2026-11-17: "a test case is testing a portion OF a sequence diagram". Each master
    flow the test ran a step of is drawn as the window around its slice, most steps first; the
    title opens the whole flow with this test's steps lit.

    W11 (2.0.0): `test_x` in two files used to share one key and so one merged set of slices.
    The page for a name still holds every definition; each now shows its own, under its file. A
    key with no file (an LCOV `TN:` name) is drawn once for the page.

    @brief Draw the slices.
    @return HTML.
    """
    slices = ctx.get("slices") or {}
    groups = _slice_groups(name, slices, [d.file for d in defs or ()])
    if not groups:
        return ""
    parts = [
        "<h2>What it exercises</h2><p>The parts of the system's flows this test ran, measured by "
        "per-test coverage: lit steps ran in this test, dimmed ones did not, and ▶ marks where the "
        "test called in. Each title opens the whole flow with these steps lit.</p>",
        ## W-6 (owner review 2026-11-22): the slices play — the steps this test ran, in order,
        ## paced to reading speed (clew-views.js; the flow player's pace and speed control).
        _player_controls(),
    ]
    for file, key in groups:
        if file and len(groups) > 1:
            parts.append(f"<h3><code>{escape(file)}</code></h3>")
        parts.append(_slices_html(key, slices[key], ctx.get("test_slices") or _SLICES_DRAWN))
    return (
        '<section class="exercises" data-flow-play="slices">'
        + "".join(parts)
        + '</section><script src="_static/clew-views.js"></script>'
    )


## @brief The test-page player's controls: play, pause, step, speed and the caption line.
## @return HTML.
## @version 1
## @utility
def _player_controls() -> str:
    """ONE SET for the slices and the call flow (W-6, X-3); `clew-views.js` drives both.

    @brief Player controls.
    @return HTML.
    """
    buttons = "".join(
        f'<button type="button" data-slice-control="{c}">{c}</button>'
        for c in ("play", "pause", "step")
    )
    return (
        f'<div class="flow-controls slice-controls">{buttons}'
        '<label class="flow-speed">speed <input type="range" min="0.25" max="2" step="0.25" '
        'value="1" data-flow-speed aria-label="playback speed"></label>'
        '<p class="slice-now" aria-live="polite"></p></div>'
    )


## @brief A test's callees in the order its body first calls them.
## @param repo_root The repository.
## @param d The test's definition (file, start, end).
## @param callees (name, file) pairs.
## @return The same pairs, in call order; any not found in the body after, in their given order.
## @version 1
## @utility
def _in_call_order(
    repo_root: Path, d: Any, callees: list[tuple[str, str]]
) -> list[tuple[str, str]]:
    """X-3 (owner review 2, 2026-11-22): a playback follows the test, not the alphabet.

    @brief Call order.
    @return Pairs.
    """
    try:
        lines = (
            (Path(repo_root) / d.file).read_text(encoding="utf-8", errors="replace").splitlines()
        )
    except OSError:
        return list(callees)
    body = "\n".join(lines[max(d.start, 1) - 1 : d.end or len(lines)])
    found = {c: body.find(f"{c[0]}(") for c in callees}
    return sorted(callees, key=lambda c: (found[c] < 0, found[c] if found[c] >= 0 else 0))


## @brief Which of a name's per-test keys belong to which of its definitions' files.
## @param name The test name.
## @param slices {test key: [(flow page, slice)]}.
## @param files The files of the name's definitions on this page.
## @return [(definition file or "", key)], definitions first, in their order.
## @version 1
## @utility
def _slice_groups(name: str, slices: dict, files: list[str]) -> list[tuple[str, str]]:
    """BY PATH SUFFIX, EITHER WAY: a pytest node id's file is relative to pytest's rootdir, which
    need not be the repository root, so `tests/test_a.py` and `pkg/tests/test_a.py` are one file.
    NOTHING IS DROPPED: a key matching no definition (an LCOV `TN:` name, a node id from another
    rootdir) is drawn for the page as a whole, as every key was before W11.

    @brief Group a name's keys by definition.
    @return Groups.
    """
    from .slices import test_name

    keys = sorted(k for k in slices if test_name(k) == name and slices[k])
    out: list[tuple[str, str]] = []
    for file in dict.fromkeys(files):
        for key in keys:
            where = key.rsplit("::", 1)[0] if "::" in key else ""
            if where and (file.endswith(where) or where.endswith(file)):
                out.append((file, key))
    claimed = {k for _f, k in out}
    return out + [("", k) for k in keys if k not in claimed]


## @brief One test key's slices: the first few drawn, the rest linked.
## @param key The per-test key (`file::name`, or a bare name).
## @param cuts [(flow page, slice)], most exercised first.
## @return HTML.
## v2: slice cap (owner Q/A 2026-11-20, after P6)
## @version 2
## @utility
def _slices_html(key: str, cuts: list, drawn: int = _SLICES_DRAWN) -> str:
    """OWNER Q/A 2026-11-20 (after P6): the top `drawn` slices are drawn; the rest are a
    `<details>` "N more", each linking its whole flow lit for this test — the V1–V6 pattern. The
    slices arrive most steps first.

    @brief Draw one key's slices.
    @return HTML.
    """
    from urllib.parse import quote

    from . import slices

    def heading(page: Any, cut: Any) -> str:
        href = f"{page.name}.html#test={quote(key)}"
        return (
            f'<a href="{escape(href)}">{escape(page.title)}</a> · {len(cut.exercised)} of '
            f"{page.steps} steps"
        )

    parts = [f"<h4>{heading(p, c)}</h4>{slices.slice_svg(p.flow, c)}" for p, c in cuts[:drawn]]
    rest = cuts[drawn:]
    if rest:
        items = "".join(f"<li>{heading(p, c)}</li>" for p, c in rest)
        parts.append(
            f'<details class="more-slices"><summary>{len(rest)} more</summary><ul>{items}</ul></details>'
        )
    return "".join(parts)


## @brief The run's verdict on a test, and its failure message.
## @param name The test.
## @param ctx The page context.
## @return HTML.
## @version 1
## @utility
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
## v3: checks pinned by syntax tree (2.0.0, P5.5)
## v4: traced values on pinned checks (2.0.0, P5.5)
## v5: context paths (2.0.0, P5.5)
## v6: call-flow boxes (2.0.0, P5.5)
## v7: call flow plays in call order with briefs (X-3)
## v8: test card and declared-first requirements (owner review 3)
## v9: card at page level (owner review 3)
## v10: the test flowchart (2.2, F2)
## @version 10
## @utility
def _definition(d: Any, graph: _Edges, ctx: dict[str, Any], repo_root: Path) -> str:
    """@brief Definition block. @return HTML."""
    from .checkpins import pin_checks, traced_values
    from .flowchart import flowchart_section
    from .testfacts import assertions

    url = source_url(ctx["template"], ctx["commit"], d.file, max(d.start, 1))
    where = f"{escape(d.file)}:{d.start}"
    where = f'<a href="{escape(url)}">{where}</a>' if url else where
    out = f'<p class="where">{where} · <a href="{_source_page(d)}">its file\'s page</a></p>'
    lines = _lines(repo_root, d)
    candidates = {graph.names[c][0] for c in graph.callees.get(d.rowid, ()) if c in graph.names}
    checks = assertions(lines) if lines and not ctx["rules"].exclude_bodies else []
    ## P5.5: PINNED BY SYNTAX TREE when the language has a parser; the regex reading otherwise.
    pins = pin_checks(lines, d.file, candidates, d.start) if checks else []
    ## P5.5, TRACED VALUES: a packaged run of this test gives each pinned check its call's value.
    run = (ctx.get("traces") or {}).get(d.name)
    values = traced_values(pins, run[1], d.name) if run and pins else {}
    items = "".join(_pinned(p, values.get(i)) for i, p in enumerate(pins)) or "".join(
        f"<li><code>{escape(a)}</code></li>" for a in checks
    )
    count = len(pins) or len(checks)
    if count:
        out += f'<h2>What it checks ({count})</h2><ol class="asserts">{items}</ol>'
    ## 2.2: the flowchart, each check failing into its declared mode.
    by_test, meanings = ctx.get("modes") or ({}, {})
    if pins:
        out += flowchart_section(pins, lines, d.start, by_test.get(d.rowid, []), meanings)
    if candidates:
        out += _context(candidates, ctx.get("product_flows") or [])
        callees = sorted(graph.names[c] for c in graph.callees.get(d.rowid, ()) if c in graph.names)
        callees = _in_call_order(repo_root, d, callees)
        ran = (ctx.get("lines_by_test") or {}).get(f"{d.file}::{d.name}") or {}
        out += _callflow(d.name, callees, ran, ctx.get("written") or set(), ctx.get("briefs"))
    out += _proof(d, graph, ctx, count)
    return out


## @brief The product functions a test calls: its callees outside test code.
## @param d The test's definition.
## @param graph The call graph.
## @return Names.
## @version 1
## @utility
def _product(d: Any, graph: _Edges) -> set[str]:
    """Owner review 3: a helper in the test's own file, or anywhere under a test path, is the test's
    machinery, not the product it is checking.

    @brief Product callees.
    @return Names.
    """
    out = set()
    for c in graph.callees.get(d.rowid, ()):
        name, file = graph.names.get(c, ("", ""))
        parts = file.split("/")
        if name and file != d.file and not any(p.startswith("test") for p in parts):
            out.add(name)
    return out


## @brief One definition's test card: WHY it exists, then Given / When / Then.
## @param d The definition.
## @param graph The call graph.
## @param ctx The page context.
## @param repo_root The repository.
## @return HTML.
## @version 1
## @utility
def _card(d: Any, graph: _Edges, ctx: dict[str, Any], repo_root: Path) -> str:
    """OWNER REVIEW 3 (2026-11-22): at the top of the page. Withheld bodies keep only WHY — Given /
    When / Then is the test's source.

    @brief Test card.
    @return HTML.
    """
    from .testcard import test_card

    lines = [] if ctx["rules"].exclude_bodies else (_lines(repo_root, d) or [])
    return test_card(
        lines,
        d,
        _product(d, graph),
        (ctx.get("tests") or {}).get(d.name),
        (ctx.get("briefs") or {}).get((d.name, d.file), ""),
    )


## @brief The test's call-flow boxes: each function it calls, linked to its activity diagram.
## @param test The test's name.
## @param callees (name, file) of each function it calls.
## @param ran {file: lines this test executed}, from per-test coverage, or {}.
## @param written (name, file) of every function whose page was written.
## @return HTML.
## v2: call flow plays in call order with briefs (X-3)
## v3: UX review group E (owner Q/A 2026-11-22)
## @version 3
## @req REQ-DDB-WIKI-045
def _callflow(
    test: str,
    callees: list[tuple[str, str]],
    ran: dict[str, set[int]],
    written: set,
    briefs: dict | None = None,
) -> str:
    """TWO ZOOM LEVELS (owner, round 5): a box per function the test calls; its link opens that
    function's activity diagram, on the function's own page, with the lines THIS test executed in
    `?lit=` for `clew.js` to light (owner Q/A 2026-11-20). A function without a written page gets a
    box and no link, never a broken one; without per-test coverage the link carries no lines.

    @brief Call-flow boxes.
    @return HTML.
    """
    boxes = []
    for name, rel in callees:
        ## X-3: each box says what its function does, for the reader and for the player's caption.
        brief = (briefs or {}).get((name, rel), "")
        about = f' data-brief="{escape(brief)}" title="{escape(brief)}"' if brief else ""
        if (name, rel) not in written:
            boxes.append(f'<span class="box"{about}>{escape(name)}</span>')
            continue
        page, _anchor = symbol_href(name, rel).split("#", 1)
        lit = _ranges(ran.get(rel, set()))
        query = f"?lit={lit}" if lit else ""
        boxes.append(
            f'<a class="box"{about} href="{page}{query}#act-{anchor(name)}">{escape(name)}</a>'
        )
    arrows = '<span class="arrow">→</span>'.join(boxes)
    return (
        ## E-15: a player only where there is something to play — more than five boxes.
        '<section class="callflow-block" data-flow-play="callflow"><h2>Call flow</h2>'
        f'{_player_controls() if len(callees) > 5 else ""}<div class="callflow"><span class="box test"><code>{escape(test)}'
        f'</code></span><span class="arrow">→</span>{arrows}</div></section>'
        '<script src="_static/clew-views.js"></script>'
    )


## @brief Lines as compact ranges.
## @param lines Line numbers.
## @return `12-15,20`, or "".
## @version 1
## @utility
def _ranges(lines: set[int]) -> str:
    """@brief Runs of consecutive lines. @return Ranges."""
    out: list[str] = []
    for n in sorted(lines):
        if out and "-" in out[-1] and int(out[-1].split("-")[1]) + 1 == n:
            out[-1] = f"{out[-1].split('-')[0]}-{n}"
        elif out and "-" not in out[-1] and int(out[-1]) + 1 == n:
            out[-1] = f"{out[-1]}-{n}"
        else:
            out.append(str(n))
    return ",".join(out)


## @brief How the product reaches the functions a test calls, or that it does not.
## @param candidates The names of the functions the test calls.
## @param flows The site's flow pages (only `product` ones count).
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-044
def _context(candidates: set[str], flows: list) -> str:
    """CONTEXT PATHS (owner, round 5, P5.5): for each function the test calls, the shortest path a
    PRODUCT flow takes from its entry to it, along that flow's own drawn steps, linked to the flow.
    A tooling or thread flow is not the product. ABSENCE IS STATED: when no product flow reaches
    any of them the page says so — a test of code the product never runs is worth knowing about.

    @brief Context paths.
    @return HTML.
    """
    lines = []
    for name in sorted(candidates):
        found = _shortest([f for f in flows if f.role == "product"], name)
        if found:
            page, path = found
            chain = (
                " → ".join(f"<code>{escape(n)}</code>" for n in path)
                if len(path) > 1
                else f"<code>{escape(name)}</code> is the entry of the flow"
            )
            lines.append(f'<li>{chain} <a href="{escape(page)}.html">(flow)</a></li>')
    body = (
        f"<ul>{''.join(lines)}</ul>"
        if lines
        else "<p>No product flow reaches this code: no product entry point's flow calls any of "
        "the functions this test calls.</p>"
    )
    return f'<h2>Where the product reaches it</h2><div class="context">{body}</div>'


## @brief The shortest entry → name path over the product flows, and the flow it is in.
## @param flows Product flow pages.
## @param name The function to reach.
## @return (flow page name, path), or None.
## @version 1
## @utility
def _shortest(flows: list, name: str) -> tuple[str, list[str]] | None:
    """@brief Breadth-first over each flow's steps from its entry. @return Best path."""
    best: tuple[str, list[str]] | None = None
    for flow in flows:
        if not flow.calls:
            continue
        entry = flow.calls[0][0]
        nexts: dict[str, list[str]] = {}
        for a, b in flow.calls:
            nexts.setdefault(a, []).append(b)
        seen, queue = {entry}, [[entry]]
        while queue:
            path = queue.pop(0)
            if path[-1] == name and _better(path, best):
                best = (flow.name, path)
                break
            for nxt in nexts.get(path[-1], ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append([*path, nxt])
    return best


## @brief Whether a found path beats the best so far.
## @param path The new path.
## @param best The best (flow, path) so far, or None.
## @return True when the new one is better.
## @version 1
## @utility
def _better(path: list[str], best: tuple[str, list[str]] | None) -> bool:
    """A CALLER CHAIN BEATS A FLOW THAT MERELY STARTS AT THE FUNCTION: a one-step path says
    nothing about how the product gets there, so it is kept only when no flow reaches it from above.
    Among caller chains, the shorter wins.

    @brief Rank paths.
    @return Better.
    """
    if best is None:
        return True
    old = best[1]
    if (len(path) == 1) != (len(old) == 1):
        return len(old) == 1
    return len(path) < len(old)


## @brief One pinned check: the statement, what it observes, and its traced value.
## @param pin The Pin.
## @param value The value its call returned in a recorded run, or None.
## @return HTML.
## v2 (2.0.0, P5.5): the traced value.
## @version 2
## @req REQ-DDB-WIKI-043
def _pinned(pin: Any, value: str | None = None) -> str:
    """@brief `observes f`, `observes f via r`, or `not attributed`. @return HTML."""
    from .checkpins import DIRECT, VIA_VARIABLE

    if pin.kind == DIRECT:
        badge = f"observes <code>{escape(pin.target)}</code>"
    elif pin.kind == VIA_VARIABLE:
        badge = (
            f"observes <code>{escape(pin.target)}</code> via <code>{escape(pin.variable)}</code>"
        )
    else:
        badge = "not attributed"
    kind = pin.kind.replace(" ", "-")
    seen = (
        f' <span class="traced">returned <code>{escape(value)}</code> in the recorded run</span>'
        if value is not None
        else ""
    )
    return (
        f"<li><code>{escape(pin.statement)}</code> "
        f'<span class="pin pin-{kind}">{badge}</span>{seen}</li>'
    )


## @brief The chains from a test to each linked requirement's implementer, drawn.
## @param d The test's definition.
## @param graph The call graph.
## @param ctx The page context.
## @param checks How many checks the test makes.
## @return HTML.
## v2: one path depth, wiki.path_depth (2.0.0, R5-CFG C3)
## @version 2
## @utility
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
        path = _path(
            graph, d.rowid, ctx["implementers"].get(req, set()), ctx.get("path_depth", _PATH_DEPTH)
        )
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
## @utility
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
## @utility
def _width(label: str) -> float:
    """@brief Width. @return Px."""
    return 22 + 7.6 * len(label)


## @brief The requirements a test is linked to, with how and how much.
## @param name The test.
## @param ctx The page context.
## @return HTML.
## v2: test card and declared-first requirements (owner review 3)
## v3: UX review group E (owner Q/A 2026-11-22)
## @version 3
## @utility
def _requirements(name: str, ctx: dict[str, Any]) -> str:
    """@brief Requirement table. @return HTML."""
    from .testcard import DECLARED_LINKS

    facts = ctx["tests"][name]
    ## OWNER REVIEW 3 (2026-11-22): WHAT IT IS FOR, then what it merely reaches. Declared links
    ## (tag, catalog) are the table; coverage reach (measured, inferred) folds under it.
    declared = [(r, k) for r, k in facts.verifies if k in DECLARED_LINKS]
    reach = [(r, k) for r, k in facts.verifies if k not in DECLARED_LINKS]
    rows = "".join(
        f'<tr><td><a href="req-{escape(req)}.html">{escape(req)}</a></td>'
        f'<td><span class="via via-{kind}">{kind}</span></td>'
        f"<td>{_extent(ctx, req, name)}</td></tr>"
        for req, kind in declared
    )
    out = (
        (
            f"<h2>Requirements it verifies ({len(declared)})</h2>"
            '<table class="clew"><thead><tr><th>requirement</th><th>linked by</th>'
            f"<th>implementers exercised</th></tr></thead><tbody>{rows}</tbody></table>"
        )
        if declared
        else ""
    )
    if reach:
        items = "".join(
            f'<li><a href="req-{escape(r)}.html">{escape(r)}</a> <span class="via via-{k}">{k}</span></li>'
            for r, k in reach
        )
        out += (
            f'<details class="reach"><summary>Also reaches {plural(len(reach), "requirement")}</summary>'
            f"<p>Its run touches their code; that is reach, not proof.</p><ul>{items}</ul></details>"
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
## @utility
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


## The results a test can have, in the order the Tests tab's chips show them.
_RESULTS = ("failed", "error", "passed", "skipped", "absent")
## A test file under one of these directory names is fixture data, not a test the suite runs.
_FIXTURE_DIRS = {"data", "fixtures", "fixture", "testdata"}


## @brief A test's result in the packaged run ("absent" when no report names it).
## @param d The definition.
## @param results Test name → its result.
## @return The status.
## @version 1
## @utility
def _status(d: Any, results: dict) -> str:
    """@brief Status. @return Text."""
    found = results.get(d.name)
    return found.status if found else "absent"


## @brief The Tests tab's result chips, each with its count; a chip filters the tab.
## @param counts Result → tests.
## @return HTML.
## @version 1
## @utility
def _result_chips(counts: dict[str, int]) -> str:
    """UX review D-8: the tab opens on what matters — how many failed — not on 3,356 rows.

    @brief Result chips.
    @return HTML.
    """
    chips = "".join(
        f'<button type="button" class="chip r-{s}" data-filter-chip="{s}">{s} {counts[s]}</button>'
        for s in _RESULTS
        if counts.get(s)
    )
    return f'<p class="chips">{chips}</p>'


## @brief The Tests tab's groups: one collapsed section per test file, fixture data apart at the end.
## @param defs Every recognised test definition.
## @param results Test name → its result.
## @param facts Test name → its facts.
## @param hrefs Test name → its page.
## @return HTML.
## @version 1
## @utility
def _tests_groups(defs: list, results: dict, facts: dict, hrefs: dict) -> str:
    """UX review D-8 (owner Q/A 2026-11-22): GROUPED BY FILE, each group collapsed with its count and
    results, so the tab is browsable; files under a fixture-data directory (`tests/data/...`) are
    code the suite does not run as tests, so they fold together at the end. Every group's table
    keeps the class the filter box reads (`tests-all`).

    @brief Test groups.
    @return HTML.
    """
    by_file: dict[str, list] = defaultdict(list)
    for d in sorted(defs, key=lambda d: (d.file, d.start, d.name)):
        by_file[d.file].append(d)
    real = [f for f in by_file if not _FIXTURE_DIRS & set(f.split("/")[:-1])]
    fixtures = [f for f in by_file if f not in real]
    out = [_test_group(f, by_file[f], results, facts, hrefs) for f in real]
    if fixtures:
        inner = "".join(_test_group(f, by_file[f], results, facts, hrefs) for f in fixtures)
        n = sum(len(by_file[f]) for f in fixtures)
        out.append(
            f'<details class="tgroup fixtures"><summary>Fixture data: {n} test-shaped functions in '
            f"{len(fixtures)} files the suite does not run</summary>{inner}</details>"
        )
    return "".join(out)


## @brief One file's group on the Tests tab.
## @param file The test file.
## @param tests Its definitions.
## @param results Test name → its result.
## @param facts Test name → its facts.
## @param hrefs Test name → its page.
## @return HTML.
## @version 1
## @utility
def _test_group(file: str, tests: list, results: dict, facts: dict, hrefs: dict) -> str:
    """@brief One group. @return HTML."""
    counts: dict[str, int] = {}
    rows = []
    for d in tests:
        status = _status(d, results)
        counts[status] = counts.get(status, 0) + 1
        name = f"<code>{escape(d.name)}</code>"
        cell = f'<a href="{escape(hrefs[d.name])}">{name}</a>' if d.name in hrefs else name
        linked = len((facts.get(d.name) or _NO_FACTS).verifies)
        rows.append(
            f'<tr data-result="{escape(status)}"><td>{cell}</td><td>:{d.start}</td>'
            f'<td><span class="res r-{escape(status)}">{escape(status)}</span></td>'
            f'<td class="n">{linked or "—"}</td></tr>'
        )
    noun = "test" if len(tests) == 1 else "tests"
    tally = " · ".join(f"{counts[s]} {s}" for s in _RESULTS if counts.get(s))
    return (
        f'<details class="tgroup"><summary><code>{escape(file)}</code> <span class="tc">{len(tests)} '
        f"{noun} · {tally}</span></summary>"
        '<div class="table-wrap"><table class="clew tests-all"><thead><tr><th>test</th><th>line</th>'
        f'<th>result</th><th class="n">requirements</th></tr></thead><tbody>{"".join(rows)}'
        "</tbody></table></div></details>"
    )


## @brief Write the Tests tab: every test the index recognises, linked to its page, filterable.
## @param db The index.
## @param ctx The test-page context (`tests`, `results`).
## @param hrefs Test name → its page, for the tests that have one.
## @param source The Sphinx source directory.
## @return The page name.
## v2: UX review group E (owner Q/A 2026-11-22)
## @version 2
## @req REQ-DDB-WIKI-052
def tests_index(db: Path, ctx: dict[str, Any], hrefs: dict[str, str], source: Path) -> str:
    """TESTS ARE THEIR OWN CATEGORY (owner Q/A 2026-11-20): every recognised test, linked or not,
    with its file, result and how many requirements it is linked to (implicit links included).
    The main search leaves this table and the test pages out; the filter box here is the search
    for tests (`clew-views.js`).

    @brief Write tests.md.
    @return Page name.
    """
    with connect(db) as conn:
        defs = _test_definitions(conn, None)
    results = ctx.get("results") or {}
    facts = ctx.get("tests") or {}
    counts: dict[str, int] = {}
    for d in defs:
        status = _status(d, results)
        counts[status] = counts.get(status, 0) + 1
    lines = [
        "# Tests",
        "",
        f"{len(defs)} tests the index recognises; {len(hrefs)} have a page of their own. Type to "
        "filter by name, file, result or requirement count.",
        "",
        "```{raw} html",
        ## UX review D-8 (owner Q/A 2026-11-22): result chips, then one collapsed group per file.
        _result_chips(counts),
        '<input type="search" class="filter" data-filter-table="tests-all" '
        'placeholder="Filter tests" aria-label="Filter tests">',
        _tests_groups(defs, results, facts, hrefs),
        '<script src="_static/clew-views.js"></script>',
        "```",
        "",
    ]
    (Path(source) / "tests.md").write_text("\n".join(lines), encoding="utf-8")
    return "tests"


## The facts of a test the evidence never named: absent, no requirement.
_NO_FACTS = _Facts()
