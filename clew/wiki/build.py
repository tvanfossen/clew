# SPDX-License-Identifier: MIT
"""`clew wiki build`: a self-contained static site, rendered by Sphinx + MyST.

1.4.0 Track 4, W5 and W6 (owner 2026-11-13: Sphinx + MyST behind the `clew-trace[wiki]` extra).
The build writes a Sphinx source tree — the repository's own prose copied as written, one page
per configured flow (an inline SVG diagram, the step table and the bodies of the functions it
reaches), and the requirement trace with its evidence tiers — then renders it with Sphinx's
built-in theme, whose assets ship inside Sphinx: no CDN, no runtime fetch.

AUDIENCES ARE A PROPERTY OF THE BUILD (W6). `--audience NAME` applies that audience's rules from
`wiki.audiences`: `exclude_bodies` writes no function body anywhere, `exclude_requirement_text`
no requirement titles. The tests assert redaction on the rendered HTML, not on a flag.

The trace page carries the W7–W9 targets: the nodes a requirement's model entries name, the
external rules that map onto requirements (rule → requirement → function → test), each pinned
sub-catalog's rows at their pin, and mutation outcomes. A `nodes` page lists every external node
with the functions that realise it.

VERSION-KEYED SITES (W11): `version=KEY` writes the site to `<out>/<KEY>/html`, records a snapshot
of what it traced (`<out>/<KEY>/site.json`), and refreshes `<out>/versions.json` and the
`<out>/index.html` that lists every version — see `clew.wiki.versions`.

Sphinx is imported only inside `_render`, so the rest of `clew.wiki` — `check` above all — runs
without the extra installed.

@brief Generate and render the wiki site.
@version 2
"""

from __future__ import annotations

import dataclasses
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .config import Audience, WikiConfig, load_wiki_config

## Markdown table cells may not carry a bare pipe or newline.
_CELL = str.maketrans({"|": "\\|", "\n": " "})


## @brief Build the site for a repository.
## @param repo_root The repository.
## @param db Its index.
## @param out_dir Output directory; `<out_dir>/html` is the site.
## @param audience An audience name from `wiki.audiences`, or None for the full site.
## @param version A version key: the site goes to `<out>/<key>/` and is listed in `<out>`.
## @param config_path A file whose `wiki:` section applies instead of the repository's.
## @return The rendered site's directory.
## v2: nodes page, rules / catalogs / mutations on the trace, version-keyed output, config_path.
## v3: theme (W13), summary + charts (W14), burndown (W17), interactive flow pages (W18).
## v4: sections (Docs / Flows / Requirements / Model entries) instead of one page per top-bar
## entry; the trace from every source (catalog, impact.json) on one requirements page.
## v5: entry-point flows beside the declared ones.
## v6: sections ordered Requirements · Flows · Docs · Model entries — requirements front and
## centre (round 3, P1b; Change impact and Map slot in after Flows when they land).
## v7: the system map (round 3, P1c) after Flows.
## v8: the sidebar minimap, each flow page lighting the components it passes through.
## v9: flow traces on the map.
## v10: the requirements page gets the flow pages and the issue tracker (P1d).
## v11: flows grouped by role, steps badged with requirements (P1e).
## v12: Change impact section after Flows (P1g).
## v13: symbol pages (P1f); source permalinks dropped when the commit is known unpublished.
## v14: test sections and Gherkin feature pages (P2a).
## v15: directly linked tests drawn as flows (P2b).
## v16: open issues fetched and linked when `wiki.issues.fetch` (P3a).
## v17: exports — Mermaid / PlantUML flows, llms.txt, ReqIF, needs.json, Structurizr (P3b).
## v18: decisions (ADRs) and docs grouped by kind (P3c).
## v19: imported OTel traces drawn over their test flows; unmatched ones listed (P4b-2).
## v20: the product trace — the composite requirement tree across pinned dependencies (GH #68).
## v21 (round 4): the map is the repository web (R3); blocks declared or coupled (R1); a page
## per requirement (R4) and per test (R6/R7).
## v22 (round 4): a discovered flow that cannot be drawn is listed, not fatal; a traced test's
## flow is drawn past the cap.
## v23 (round 5): per-test coverage feeds the master flows; each test's slices go to its page; only
## a traced test keeps a flow of its own.
## @version 23
## @req REQ-DDB-WIKI-003
def build_wiki(
    repo_root: Path,
    db: Path,
    out_dir: Path,
    audience: str | None = None,
    version: str | None = None,
    config_path: Path | None = None,
) -> Path:
    """REFUSES rather than degrades: an invalid section, an unknown audience or a missing extra is
    an error naming itself, never a partial site that looks complete.

    @brief Write and render the site.
    @return The HTML directory.
    @version 18
    """
    from .flowpage import flow_page, flows_index
    from .impactpage import impact_page
    from .graph import build_graph
    from .issues import resolve_target
    from .web import minimap_html, web_page
    from . import testfacts
    from .imports import parse_features
    from .adr import find_decisions
    from .exports import write_exports
    from .tracerun import load_traces, root_name
    from .symbols import symbol_pages
    from .testpages import test_pages
    from .evidence import parse_junit
    from .tracepages import Trace, nodes_page, requirements_page
    from .versions import record_version, valid_key

    repo_root, out_dir = Path(repo_root), Path(out_dir)
    config, problems = load_wiki_config(repo_root, config_path)
    if problems:
        raise ValueError("wiki configuration problems: " + "; ".join(problems))
    rules = _audience(config, audience)
    site_dir = out_dir / valid_key(version) if version else out_dir
    source = site_dir / "_source"
    if source.exists():
        shutil.rmtree(source)
    source.mkdir(parents=True)
    commit = _commit(repo_root)
    if commit_published(repo_root, commit) is False:
        config = dataclasses.replace(config, link_template="")
    trace = Trace.gather(repo_root, db, config, commit)
    snapshot = trace.snapshot(version or "")
    milestones = _milestones(repo_root, config)
    burndown = _burndown(out_dir, version, snapshot, milestones) if version else ""
    req_of = _requirements_of(trace.evidence)
    facts = testfacts.gather(trace.evidence)
    traces = {
        root_name(otlp): (rel, otlp) for rel, otlp in load_traces(repo_root, config.inputs.traces)
    }
    test_specs = _test_flows(db, facts, frozenset(traces))
    specs = [*_all_flows(repo_root, db, config), *test_specs]
    coverage = _coverage(repo_root, config)
    pages, not_drawn, flow_of = [], [], {}
    for s in specs:
        try:
            pages.append(
                flow_page(
                    repo_root,
                    db,
                    _with_role(s, config),
                    source,
                    rules,
                    config,
                    commit,
                    req_of,
                    traces.get(s.entry),
                    coverage,
                )
            )
            flow_of.setdefault(s.entry, pages[-1].name)
        except ValueError as refused:
            ## Round 4: a DISCOVERED flow that cannot be drawn is listed with its reason; a
            ## DECLARED one is the repository's own statement and still fails the build.
            if s in config.flows:
                raise
            not_drawn.append((s.entry, s.file or "", str(refused)))
    unmatched = tuple(
        (rel, root)
        for root, (rel, _o) in sorted(traces.items())
        if root not in {s.entry for s in specs}
    )
    keys = {(n, f) for r in trace.evidence for n, f, _l in r.implementer_sites}
    keys |= {fn for p in pages for fn in p.functions}
    symbol_ctx = {
        "req_of": req_of,
        "flows": pages,
        "rules": rules,
        "template": config.link_template,
        "commit": commit,
        "tests": facts,
        "implementers": {
            r.req_id: {(n, f) for n, f, _l in r.implementer_sites} for r in trace.evidence
        },
    }
    written = symbol_pages(db, repo_root, keys, symbol_ctx, source)
    scenarios = parse_features(repo_root, config.inputs.features)
    written |= testfacts.feature_pages(repo_root, scenarios, facts, source)
    trace.symbols = set(written)
    ## Round 4, R6/R7: a test links to ITS OWN PAGE — result, checks, what it reaches.
    trace.test_href = test_pages(
        db,
        repo_root,
        {
            **symbol_ctx,
            "results": parse_junit(
                [repo_root / j for j in config.junit if (repo_root / j).is_file()]
            ),
            "extent": {r.req_id: dict(r.extent) for r in trace.evidence if r.extent is not None},
            "flow_of": flow_of,
            "traced": set(traces),
            "slices": _slices_by_test(pages),
        },
        source,
    )
    for (name, _rel), href in sorted(written.items()):
        if name in facts:
            trace.test_href.setdefault(name, href)
    decisions = find_decisions(repo_root, config.adrs, tuple(r.req_id for r in trace.evidence))
    trace.decisions = {
        r.req_id: [d for d in decisions if r.req_id in d.requirements] for r in trace.evidence
    }
    issues = resolve_target(config.issues, config.issues_enabled, repo_root)
    trace.issues, trace.unlinked, trace.issues_note = _fetch_issues(config, issues, trace.evidence)
    graph = build_graph(db, trace.evidence, trace.impact, config.components, exclude_tests=True)
    _issues_into(graph, trace.issues)
    sections = [
        requirements_page(trace, config, source, rules, burndown, tuple(pages), issues),
        flows_index(source, pages, unmatched, tuple(not_drawn)),
        impact_page(trace, pages, rules, source),
        web_page(db, graph, [n for n, _g in config.components], pages, written, source),
        _docs_page(source, _prose(repo_root, config, source), config, decisions),
    ]
    if config.catalogs:
        sections.insert(1, _product_section(repo_root, db, config, rules, source))
    if config.sources:
        sections.append(nodes_page(trace, config, source))
    _write_index(source, config, trace, [s for s in sections if s], len(pages))
    write_exports(
        source / "_extra",
        trace,
        pages,
        graph,
        {"title": config.title, "rules": rules, "summary": ""},
    )
    context = {
        "clew_minimap": minimap_html(graph, [n for n, _g in config.components])
        if "map" in sections
        else "",
        "clew_minimap_lit": _lit(pages, graph, config),
    }
    html = _render(source, site_dir / "html", config, repo_root, context)
    if version:
        record_version(out_dir, version, snapshot, config.title, milestones)
    return html


## @brief The product trace page, when dependency catalogues are declared (GH #68).
## @param repo_root The repository.
## @param db Its index (the root rows' evidence).
## @param config The section.
## @param rules The audience rules.
## @param source The Sphinx source directory.
## @return The page name.
## @version 1
## @dg_internal
def _product_section(
    repo_root: Path, db: Path, config: WikiConfig, rules: Audience, source: Path
) -> str:
    """@brief Compose and write. @return Page name."""
    from .composite import compose
    from .productpage import product_page

    tree = compose(repo_root, repo_root.name, list(config.catalogs), root_db=db)
    return product_page(tree, rules, source)


## @brief The components each flow page lights on the minimap.
## @param pages The flow pages.
## @param graph The graph (only its components are lit).
## @param config The section (declared groupings).
## @return {page name: [component ids]}.
## v2 (round 4, R1): blocks from the graph's placement, inferred files included.
## @version 2
## @dg_internal
def _lit(pages: list, graph: dict, config: WikiConfig) -> dict[str, list[str]]:
    """THE GRAPH'S OWN PLACEMENT (round 4, R1), so a file joined to a block by coupling lights
    that block, as the map draws it.

    @brief Lit components.
    @return Map.
    """
    owner = graph.get("file_block") or {}
    known = {c["id"] for c in graph["components"]}
    return {p.name: sorted({owner[f] for f in p.files if f in owner} & known) for p in pages}


## @brief Open issues linked to requirements, when the section asks for them.
## @param config The section.
## @param target The tracker, or None.
## @param evidence Requirement evidence rows.
## @return ({requirement: issues} or None when not fetched, unlinked issues, a note).
## @version 1
## @dg_internal
def _fetch_issues(config: WikiConfig, target: Any, evidence: list) -> tuple[Any, list, str]:
    """THE BUILD'S ONLY NETWORK USE, and only when `wiki.issues.fetch` is true. A failure is SAID
    on the page — never a crash, and never an empty list that would read "no open issues".

    @brief Fetch and link issues.
    @return Linked, unlinked, note.
    """
    from . import issues as tracker

    if not config.issues_fetch:
        return None, [], ""
    if target is None:
        return None, [], "Issues were not fetched: no tracker is declared or found on `origin`."
    try:
        found = tracker.provider_for(target).list_open()
    except (OSError, ValueError, KeyError) as exc:
        return None, [], f"Issues were not fetched from {target[0]} `{target[1]}`: {exc}"
    linked, unlinked = tracker.link_issues(found, [r.req_id for r in evidence])
    return linked, unlinked, ""


## @brief Each component's count of open issues linked to the requirements it implements.
## @param graph The graph (components gain `issues`).
## @param linked {requirement: issues}, or None when not fetched (no count at all).
## @return None.
## @version 1
## @dg_internal
def _issues_into(graph: dict, linked: Any) -> None:
    """@brief Count per component. @return None."""
    if linked is None:
        return
    for comp in graph["components"]:
        ids = {i.id for r, _tier in comp.get("req_ids") or [] for i in linked.get(r, [])}
        comp["issues"] = len(ids)


## @brief Per-test coverage, when the section names it and it is there.
## @param repo_root The repository.
## @param config The section.
## @return {file: {line: tests}}, or None (unmeasured).
## @version 1
## @dg_internal
def _coverage(repo_root: Path, config: Any) -> dict | None:
    """@brief Read contexts. @return Contexts or None."""
    from .imports import parse_contexts

    rel = config.inputs.contexts
    return (
        parse_contexts(repo_root / rel, repo_root) if rel and (repo_root / rel).is_file() else None
    )


## @brief Each test's slices of the master flows, most exercised first.
## @param pages The flow pages.
## @return {test: [(page, slice)]}.
## @version 1
## @req REQ-DDB-WIKI-041
def _slices_by_test(pages: list) -> dict[str, list]:
    """@brief Group slices by test. @return Slices."""
    out: dict[str, list] = {}
    for page in pages:
        for test, cut in (page.slices or {}).items():
            out.setdefault(test, []).append((page, cut))
    for cuts in out.values():
        cuts.sort(key=lambda pc: (-len(pc[1].exercised), pc[0].name))
    return out


## @brief Directly linked tests (by tag or measured coverage) with a packaged run, as flows.
## @param db The index.
## @param facts {test name: facts}.
## @param traced Tests with a packaged run.
## @return Flow specs.
## v2 (round 4): a traced test is drawn whatever the cap, so its replay has a flow to land on.
## v3 (OWNER 2026-11-17, round 5: "a test itself doesn't need a sequence diagram"): only a test
## with a packaged run keeps a flow, so its replay has somewhere to land until replays are drawn
## on the master flow; every other test is a slice of the master flows. The cap is gone.
## @version 3
## @req REQ-DDB-WIKI-027
def _test_flows(db: Path, facts: dict, traced: frozenset = frozenset()) -> list:
    """CATALOG AND INFERRED LINKS ARE NOT DIRECT: a catalog names a whole test file and inference
    reaches through the call graph; only a tagged or measured test is drawn by default.

    @brief Test flows.
    @return Specs.
    """
    from ..query._common import connect
    from .config import FlowSpec
    from .symbols import test_functions

    direct = {n for n, f in facts.items() if any(k in ("tag", "measured") for _r, k in f.verifies)}
    with connect(db) as conn:
        keys = sorted(test_functions(conn, direct))
    chosen = [k for k in keys if k[0] in traced]
    specs = [
        FlowSpec(entry=n, file=f, depth=2, title=f"test `{n}` ({f})", role="tests")
        for n, f in chosen
    ]
    return specs


## @brief A flow with its role settled: declared, else tooling by path, else product.
## @param spec The flow.
## @param config The section (`tooling` globs).
## @return The flow, its role set.
## @version 1
## @dg_internal
def _with_role(spec: Any, config: WikiConfig) -> Any:
    """@brief Classify. @return Spec."""
    import dataclasses
    import fnmatch

    if spec.role:
        return spec
    tooling = bool(spec.file) and any(fnmatch.fnmatch(spec.file, g) for g in config.tooling)
    return dataclasses.replace(spec, role="tooling" if tooling else "product")


## @brief Which requirements each implementing function carries.
## @param evidence Requirement evidence rows.
## @return {(function, file): [requirement ids]}.
## @version 1
## @dg_internal
def _requirements_of(evidence: list) -> dict[tuple[str, str], list[str]]:
    """@brief Invert implementer sites. @return Map."""
    out: dict[tuple[str, str], list[str]] = {}
    for row in evidence:
        for name, rel, _line in row.implementer_sites:
            out.setdefault((name, rel), []).append(row.req_id)
    return out


## @brief The declared flows, then every entry point's flow not already declared.
## @param repo_root The repository.
## @param db The index.
## @param config The section.
## @return Flow specs.
## v2 (2.0.0): `entry_points` renamed `entry_point_depth`.
## @version 2
## @dg_internal
def _all_flows(repo_root: Path, db: Path, config: WikiConfig) -> list:
    """A DECLARED FLOW WINS for its function: its title, depth and lanes are the repository's
    choice, so the derived one for the same entry is dropped.

    @brief Declared + entry-point flows.
    @return Specs.
    """
    from .entrypoints import entry_point_flows

    specs = list(config.flows)
    if config.entry_point_depth > 0:
        declared = {(s.entry, s.file) for s in specs} | {(s.entry, None) for s in specs}
        specs += [
            s
            for s in entry_point_flows(db, repo_root, config.entry_point_depth)
            if (s.entry, s.file) not in declared and (s.entry, None) not in declared
        ]
    return specs


## @brief The roadmap's milestones, or none when no roadmap is declared.
## @param repo_root The repository.
## @param config The section.
## @return (version, heading) pairs.
## @version 1
## @dg_internal
def _milestones(repo_root: Path, config: WikiConfig) -> list[tuple[str, str]]:
    """@brief Read milestones. @return Pairs."""
    from .charts import roadmap_milestones

    return roadmap_milestones(repo_root / config.roadmap) if config.roadmap else []


## @brief The burndown for a versioned build: earlier recorded versions, then this one.
## @param out_dir The versioned output root.
## @param version This build's key.
## @param snapshot This build's snapshot.
## @param milestones Roadmap milestones.
## @return SVG markup.
## @version 1
## @dg_internal
def _burndown(out_dir: Path, version: str, snapshot: dict, milestones: list) -> str:
    """@brief Draw the burndown. @return SVG."""
    from .charts import burndown
    from .versions import series

    return burndown(series(out_dir, version, snapshot), milestones)


## @brief The rules for the requested audience.
## @param config The section.
## @param audience The name, or None.
## @return The rules.
## @version 1
## @dg_internal
def _audience(config: WikiConfig, audience: str | None) -> Audience:
    """@brief Resolve an audience. @return Rules."""
    if audience is None:
        return Audience()
    if audience not in config.audiences:
        known = ", ".join(sorted(config.audiences)) or "none declared"
        raise ValueError(f"unknown audience {audience!r} (known: {known})")
    return config.audiences[audience]


## @brief Copy the configured prose into the source tree.
## @param repo_root The repository.
## @param config The section.
## @param source The Sphinx source directory.
## @return (page name, repo-relative path) pairs, in configured order.
## v2: `.html` prose — its body is embedded in a themed page (owner 2026-11-15: user-selected
## html / md content).
## v3: AGENTS.md included; ADRs copied; pages returned with their paths (round 3, P3c).
## @version 3
## @dg_internal
def _prose(repo_root: Path, config: WikiConfig, source: Path) -> list[tuple[str, str]]:
    """AS WRITTEN: Markdown through MyST, reStructuredText natively, HTML embedded as it is.
    AGENTS.md is included when present even if no glob names it — agent docs are kept apart on
    the Docs page, not left out.

    @brief Copy prose.
    @return (page name, repo-relative path) pairs.
    """
    from .config import DEFAULT_ADRS

    root = Path(repo_root)
    found = [p for pattern in config.docs for p in sorted(root.glob(pattern))]
    found += [root / "AGENTS.md"]
    pages: dict[str, str] = {}
    for path in found:
        rel = path.relative_to(root).as_posix() if path.is_absolute() else str(path)
        if not path.is_file() or path.suffix.lower() not in (".md", ".rst", ".html", ".htm"):
            continue
        page = copy_prose(root, rel, source)
        pages.setdefault(page, rel)
    for pattern in config.adrs or DEFAULT_ADRS:
        for path in sorted(root.glob(pattern)):
            if path.is_file():
                copy_prose(root, path.relative_to(root).as_posix(), source)
    return list(pages.items())


## @brief Copy one prose file into the source tree.
## @param root The repository.
## @param rel Its repo-relative path.
## @param source The Sphinx source directory.
## @return Its page name.
## @version 1
## @dg_internal
def copy_prose(root: Path, rel: str, source: Path) -> str:
    """@brief Copy prose. @return Page name."""
    path = root / rel
    target = source / "prose" / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.lower() in (".html", ".htm"):
        target = target.with_suffix(".md")
        target.write_text(_html_page(path), encoding="utf-8")
    else:
        shutil.copyfile(path, target)
    return str(Path("prose") / Path(rel).with_suffix(""))


## @brief The Docs page: the repository's prose grouped by kind, agent docs apart, decisions linked.
## @param source The Sphinx source directory.
## @param pages (page, repo-relative path) pairs.
## @param config The section (doc kinds).
## @param decisions The repository's decision records.
## @return The page name, or "" when there is nothing to show.
## @version 1
## @dg_internal
def _docs_page(
    source: Path, pages: list[tuple[str, str]], config: WikiConfig, decisions: list
) -> str:
    """OWNER 2026-11-15: human docs and agent docs are different classes of information — the
    agent-facing ones (AGENTS.md and kin) are their own group, after the human ones.

    @brief Write docs.md.
    @return Page name.
    """
    from html import escape

    from .adr import decisions_page, doc_kind

    decided = decisions_page(decisions, source)
    if not pages and not decided:
        return ""
    lines = ["# Docs", "", _DOCS_LEAD, ""]
    if decided:
        lines += [f"[Decisions](decisions.md): {len(decisions)} architecture decision records.", ""]
    for kind, heading in _KINDS:
        members = [(p, rel) for p, rel in pages if (doc_kind(rel, config.doc_kinds) or "") == kind]
        if not members:
            continue
        items = "".join(
            f'<li><a href="{escape(p)}.html">{escape(rel)}</a></li>' for p, rel in members
        )
        block = (
            f'<section class="doc-kind" data-kind="{kind or "other"}"><ul>{items}</ul></section>'
        )
        lines += [f"## {heading}", "", "```{raw} html", block, "```", ""]
    toc = [p for p, _rel in pages] + ([decided] if decided else [])
    lines += ["```{toctree}", ":hidden:", ":maxdepth: 1", "", *toc, "```", ""]
    (source / "docs.md").write_text("\n".join(lines), encoding="utf-8")
    return "docs"


## (kind, heading) in page order; "" is a document no kind was declared for.
_KINDS = (
    ("tutorial", "Tutorials"),
    ("howto", "How-to guides"),
    ("reference", "Reference"),
    ("explanation", "Explanation"),
    ("", "More"),
    ("agents", "For agents"),
)


## @brief An HTML document as a page: its title as the heading, its body embedded.
## @param path The document.
## @return MyST text.
## @version 1
## @dg_internal
def _html_page(path: Path) -> str:
    """@brief Embed HTML. @return Page text."""
    import re

    doc = path.read_text(encoding="utf-8", errors="replace")
    title = re.search(r"<title[^>]*>(.*?)</title>", doc, re.S | re.I)
    body = re.search(r"<body[^>]*>(.*)</body>", doc, re.S | re.I)
    heading = (title.group(1).strip() if title else "") or path.stem
    return f"# {heading}\n\n```{{raw}} html\n{(body.group(1) if body else doc).strip()}\n```\n"


_DOCS_LEAD = "The repository's own documentation, as written."


## @brief Write the home page: a card per section, and the toctree the top bar is built from.
## @param source The Sphinx source directory.
## @param config The section (title).
## @param trace The gathered trace (the requirements card's counts).
## @param sections Section page names, in order.
## @param flow_count How many flow pages were written (declared and entry-point).
## @return None.
## v2: section cards; the top bar names sections, not every page (owner 2026-11-15).
## v3: each card carries its section's icon (round 3, P1b); the flows card counts every flow page,
## not only the declared ones (it read "2" on a site with 30).
## v4: the map card (round 3, P1c).
## v5: the change-impact card (P1g).
## v6: the Product trace card (GH #68).
## v7 (round 4): the map card describes the repository web.
## @version 7
## @dg_internal
def _write_index(
    source: Path, config: WikiConfig, trace: object, sections: list[str], flow_count: int
) -> None:
    """@brief Root page. @return None."""
    from html import escape

    from .icons import icon

    ev = trace.evidence
    blurbs = {
        "docs": ("Docs", "The repository's own documentation."),
        "flows": ("Flows", f"{flow_count} sequence diagrams derived from the index."),
        "requirements": (
            "Requirements",
            f"{len(ev)} requirements · {sum(1 for r in ev if r.implementers)} implemented · "
            f"{sum(1 for r in ev if r.tests)} tested · {sum(1 for r in ev if r.tier == 'PASS')} "
            "passing.",
        ),
        "nodes": ("Model entries", "Entries of declared model files and the code realising them."),
        "product": (
            "Product trace",
            "This repository's requirements and the pinned dependency requirements serving them.",
        ),
        "impact": (
            "Change impact",
            "What the last change touched: functions, requirements, flows.",
        ),
        "map": (
            "Map",
            "Every function in one zoomable web: blocks, calls, and where each test reaches.",
        ),
    }
    cards = "".join(
        f'<a class="card-link" href="{name}.html"><h3>{icon(name, 22)}'
        f"{escape(blurbs[name][0])}</h3><p>{escape(blurbs[name][1])}</p></a>"
        for name in sections
    )
    text = [
        f"# {config.title}",
        "",
        "```{raw} html",
        f'<div class="cards">{cards}</div>',
        "```",
        "",
        "```{toctree}",
        ":hidden:",
        ":maxdepth: 1",
        "",
        *sections,
        "```",
        "",
    ]
    (source / "index.md").write_text("\n".join(text), encoding="utf-8")


## @brief A source link for a file and line, or the bare location when no template is set.
## @param template The link template.
## @param commit The commit the site describes.
## @param rel Repo-relative file.
## @param line Line number.
## @return Markdown.
## @version 1
## @dg_internal
def _link(template: str, commit: str, rel: str, line: int) -> str:
    """@brief Format a link. @return Markdown."""
    where = f"{rel}:{line}"
    if not template or not rel:
        return f"`{where}`"
    return f"[{where}]({template.format(commit=commit, file=rel, line=line)})"


## @brief The repository's HEAD commit, or "HEAD" when it cannot be read.
## @param repo_root The repository.
## @return The full sha.
## @version 1
## @dg_internal
def _commit(repo_root: Path) -> str:
    """FULL IDS, through the hardened git environment (#67: commit-correct links).

    @brief Read HEAD.
    @return Sha.
    """
    from ..gitenv import git_argv

    try:
        out = subprocess.run(
            git_argv("rev-parse", "HEAD"),
            cwd=repo_root,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "HEAD"
    return out.stdout.strip() or "HEAD"


## @brief Whether a commit is on one of the repository's remotes.
## @param repo_root The repository.
## @param commit The commit.
## @return True when a remote branch contains it, False when there are remotes and none does,
## None when it cannot be known (no git, no remote, an unknown commit).
## @version 1
## @req REQ-DDB-WIKI-025
def commit_published(repo_root: Path, commit: str) -> bool | None:
    """OWNER 2026-11-15: "GH link broken (local unpushed commits)" — a permalink to a commit no
    remote has is a 404. Only a KNOWN negative drops links: with nothing to go on they stay.

    @brief Published?
    @return Tri-state.
    """
    from ..gitenv import git_argv

    if not commit or commit == "HEAD":
        return None
    try:
        remotes = subprocess.run(
            git_argv("remote"), cwd=repo_root, capture_output=True, text=True, timeout=30
        )
        if remotes.returncode != 0 or not remotes.stdout.strip():
            return None
        found = subprocess.run(
            git_argv("branch", "-r", "--contains", commit),
            cwd=repo_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return bool(found.stdout.strip()) if found.returncode == 0 else None


## @brief Render the source tree to HTML with Sphinx.
## @param source The Sphinx source directory.
## @param html The output directory.
## @param config The section (title, theme).
## @param repo_root The repository (theme files are relative to it).
## @param context Template variables for every page (`html_context`).
## @return The output directory.
## v2: the configured theme (W13), clew's own by default.
## v3: `context` (the minimap, round 3 P1c-2).
## v4: `_extra` (the exports) copied to the site root.
## @version 4
## @dg_internal
def _render(
    source: Path, html: Path, config: WikiConfig, repo_root: Path, context: dict | None = None
) -> Path:
    """THE ONLY SPHINX IMPORT, so everything else runs without the extra.

    @brief Run sphinx-build.
    @return HTML dir.
    """
    from .theme import sphinx_settings

    try:
        from sphinx.cmd.build import build_main
    except ImportError as exc:
        raise ValueError(
            "clew wiki build needs the wiki extra: pip install 'clew-trace[wiki]'"
        ) from exc
    settings = {
        "project": config.title,
        "extensions": ["myst_parser"],
        "source_suffix": {".rst": "restructuredtext", ".md": "markdown"},
        "exclude_patterns": ["_build"],
        "html_context": context or {},
        "html_extra_path": ["_extra"] if (source / "_extra").is_dir() else [],
        **sphinx_settings(config.theme, repo_root, source),
    }
    (source / "conf.py").write_text(
        "".join(f"{k} = {v!r}\n" for k, v in settings.items()), encoding="utf-8"
    )
    if build_main(["-q", "-b", "html", str(source), str(html)]) != 0:
        raise ValueError(f"sphinx-build failed for {source}")
    return html
