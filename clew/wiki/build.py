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

from .config import DEFAULT_MAX_REPORT_MB, Audience, WikiConfig, load_wiki_config

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
## v24 (2.0.0): the body moved to `_build_site`; this scopes the report limit around it (R5-CFG C9).
## @version 24
## @req REQ-DDB-WIKI-003
def build_wiki(
    repo_root: Path,
    db: Path,
    out_dir: Path,
    audience: str | None = None,
    version: str | None = None,
    config_path: Path | None = None,
) -> Path:
    """THE REPORT SIZE LIMIT (`tests.max_report_mb`) IS THIS BUILD'S: every report reader below
    consults it, so it is set around the whole build rather than threaded through each parser.

    @brief Write and render the site, within this build's report limit.
    @return The HTML directory.
    @version 24
    """
    from .evidence import report_limit

    config, problems = load_wiki_config(Path(repo_root), config_path)
    with report_limit(config.max_report_mb if not problems else DEFAULT_MAX_REPORT_MB):
        return _build_site(repo_root, db, out_dir, audience, version, config_path)


## @brief Write and render the site.
## @param repo_root The repository.
## @param db The index.
## @param out_dir Where the site goes.
## @param audience Redaction rules, by name.
## @param version The version key, when versioned.
## @param config_path An out-of-tree config.
## @return The HTML directory.
## The body of `build_wiki` before 2.0.0 (its history is recorded there).
## v2: the map honours exclude_owners (2.0.0, P5)
## v3: product tree requirement ids link to their pages (2.0.0, P5.4)
## v4: test pages get the packaged runs (2.0.0, P5.5)
## v5: test pages get the product flows (2.0.0, P5.5)
## v6: test pages get per-test lines and written pages (2.0.0, P5.5)
## v7: Architecture tab (2.0.0, P5.6)
## v8: graph before flows; block lanes and actors (2.0.0, P5.6)
## v9: quick views second pass (2.0.0, P5.6)
## v10: SBOM page (2.0.0, P5.8)
## v11: tests category (2.0.0, owner Q/A 2026-11-20)
## v12: public-API reference (2.0.0, PAPI)
## v13: viewer caps V3/V5/V6 (2.0.0, owner Q/A 2026-11-20)
## v14: doc tags to the API pages (entropic's PAPI gaps 1-3 (2.0.0))
## @version 14
## @utility
def _build_site(
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
    @version 1
    """
    from .architecture import architecture_page
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
    test_specs = _test_flows(db, facts, frozenset(traces), config.trace_depth)
    specs = [*_all_flows(repo_root, db, config), *test_specs]
    coverage = _coverage(repo_root, config)
    ## P5.6: THE GRAPH BEFORE THE FLOWS, so a flow's block lanes are the map's blocks.
    graph = build_graph(
        db,
        trace.evidence,
        trace.impact,
        config.components,
        exclude_tests=True,
        component_depth=config.component_depth,
    )
    blocks = graph.get("file_block") or {}
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
                    blocks,
                    _actor_of(s, config),
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
        ## V6 (owner Q/A 2026-11-20): how many body lines a symbol page bundles.
        "body_lines": config.body_lines,
        "req_of": req_of,
        "flows": pages,
        "rules": rules,
        "template": config.link_template,
        ## R5-CFG C3 (2.0.0): ONE test → implementer path depth for the symbol and test pages.
        "path_depth": config.path_depth,
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
            ## P5.5: the runs themselves, for each pinned check's traced value.
            "traces": traces,
            ## P5.5: context paths — the product flows a test's calls are reached by.
            "product_flows": [p for p in pages if p.role == "product"],
            ## P5.5: the call-flow boxes — what each test ran, and which functions have a page.
            "lines_by_test": _lines_by_test(coverage),
            "written": set(written),
            "test_pages": config.test_pages,
            "slices": _slices_by_test(pages),
        },
        source,
    )
    for (name, _rel), href in sorted(written.items()):
        if name in facts:
            trace.test_href.setdefault(name, href)
    ## P5.6: QUICK VIEWS, a second pass once every flow and test page exists.
    from .entities import write_quick_views

    write_quick_views(db, source, pages, blocks, trace.test_href, req_of)
    decisions = find_decisions(repo_root, config.adrs, tuple(r.req_id for r in trace.evidence))
    trace.decisions = {
        r.req_id: [d for d in decisions if r.req_id in d.requirements] for r in trace.evidence
    }
    issues = resolve_target(config.issues, config.issues_enabled, repo_root)
    trace.issues, trace.unlinked, trace.issues_note = _fetch_issues(config, issues, trace.evidence)
    _issues_into(graph, trace.issues)
    sections = [
        requirements_page(trace, config, source, rules, burndown, tuple(pages), issues),
        flows_index(source, pages, unmatched, tuple(not_drawn)),
        impact_page(trace, pages, rules, source),
        web_page(
            db,
            graph,
            [n for n, _g in config.components],
            pages,
            written,
            source,
            config.web_max_ring,
            owners=not rules.exclude_owners,
        ),
        _docs_page(source, _prose(repo_root, config, source), config, decisions),
    ]
    ## Owner Q/A 2026-11-20: tests are their own category — the Tests tab, after Flows.
    from .testpages import tests_index

    sections.insert(
        sections.index("flows") + 1 if "flows" in sections else len(sections),
        tests_index(
            db,
            {"tests": facts, "results": _test_results(repo_root, config)},
            trace.test_href,
            source,
        ),
    )
    ## PAPI (owner Q/A 2026-11-19): the public-API reference, when public headers are declared.
    from .apiref import api_pages

    sections.append(api_pages(db, config.api, source, config.doc_tags))
    ## #70 (P5.8): the SBOM page, rendered from the repository's own SBOM (never written).
    from .sbom import sbom_page

    sections.append(sbom_page(repo_root, db, config, source))
    ## P5.6: the C4 Architecture tab, after the map it zooms into.
    sections.insert(
        sections.index("map") + 1 if "map" in sections else len(sections),
        architecture_page(
            config.title, graph, _architecture_entries(db, repo_root, config, flow_of), source
        ),
    )
    if config.catalogs:
        linked = frozenset(r.req_id for r in trace.evidence)
        sections.insert(1, _product_section(repo_root, db, config, rules, source, linked))
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
## @param pages Requirement ids that have a page in this site (P5.4: the tree links to them).
## @return The page name.
## @version 2
## @utility
def _product_section(
    repo_root: Path,
    db: Path,
    config: WikiConfig,
    rules: Audience,
    source: Path,
    pages: frozenset[str] = frozenset(),
) -> str:
    """@brief Compose and write. @return Page name."""
    from .composite import compose
    from .productpage import product_page

    tree = compose(repo_root, repo_root.name, list(config.catalogs), root_db=db)
    return product_page(tree, rules, source, pages)


## @brief The components each flow page lights on the minimap.
## @param pages The flow pages.
## @param graph The graph (only its components are lit).
## @param config The section (declared groupings).
## @return {page name: [component ids]}.
## v2 (round 4, R1): blocks from the graph's placement, inferred files included.
## @version 2
## @utility
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
## v2: a listing cut at its page cap is disclosed (2.0.0, R5-CFG D14)
## @version 2
## @utility
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
    provider = tracker.provider_for(target)
    try:
        found = provider.list_open()
    except (OSError, ValueError, KeyError) as exc:
        return None, [], f"Issues were not fetched from {target[0]} `{target[1]}`: {exc}"
    linked, unlinked = tracker.link_issues(found, [r.req_id for r in evidence])
    ## D14 (2.0.0): a listing cut at its page cap is SAID — the counts below are a floor.
    note = (
        f"Only the first {len(found)} open issues were read from {target[0]} `{target[1]}` (the "
        f"listing stops at its page cap); counts on this page are a lower bound."
        if getattr(provider, "truncated", False)
        else ""
    )
    return linked, unlinked, note


## @brief Each component's count of open issues linked to the requirements it implements.
## @param graph The graph (components gain `issues`).
## @param linked {requirement: issues}, or None when not fetched (no count at all).
## @return None.
## @version 1
## @utility
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
## @utility
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
## v4: the traced flow depth is wiki.trace_depth (2.0.0, R5-CFG C4)
## @version 4
## @req REQ-DDB-WIKI-027
def _test_flows(db: Path, facts: dict, traced: frozenset = frozenset(), depth: int = 2) -> list:
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
        FlowSpec(entry=n, file=f, depth=depth, title=f"test `{n}` ({f})", role="tests")
        for n, f in chosen
    ]
    return specs


## @brief A flow with its role settled: declared, else tooling by path, else product.
## @param spec The flow.
## @param config The section (`tooling` globs).
## @return The flow, its role set.
## @version 1
## @utility
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
## @utility
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
## @utility
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
## @utility
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
## @utility
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
## @utility
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
## v4: the gate's report dir is not prose (entropic's audit of 19f439fb (2.0.0))
## @version 4
## @utility
def _prose(repo_root: Path, config: WikiConfig, source: Path) -> list[tuple[str, str]]:
    """AS WRITTEN: Markdown through MyST, reStructuredText natively, HTML embedded as it is.
    AGENTS.md is included when present even if no glob names it — agent docs are kept apart on
    the Docs page, not left out.

    @brief Copy prose.
    @return (page name, repo-relative path) pairs.
    """
    from .config import DEFAULT_ADRS

    from .tracepages import impact_path

    root = Path(repo_root)
    ## ENTROPIC'S AUDIT (12 toctree warnings): the gate's own report directory is not prose — its
    ## title-less `impact.md` was swept in by a `docs/**` glob.
    report = impact_path(root, config).parent.resolve()
    found = [
        p
        for pattern in config.docs
        for p in sorted(root.glob(pattern))
        if not p.resolve().is_relative_to(report)
    ]
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
## @utility
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
## @utility
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
## @utility
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
## v8: Architecture card (2.0.0, P5.6)
## v9: SBOM card (2.0.0, P5.8)
## v10: Tests card (tests category (2.0.0, owner Q/A 2026-11-20))
## v11: API card (public-API reference (2.0.0, PAPI))
## @version 11
## @utility
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
        "architecture": (
            "Architecture",
            "The system at C4's four levels: context, containers, components, code.",
        ),
        "api": (
            "API",
            "The public API, header by header: functions, enums, types, macros, classes.",
        ),
        "tests": (
            "Tests",
            "Every test the index recognises: its result, its requirements, its page.",
        ),
        "sbom": (
            "SBOM",
            "The software bill of materials this repository carries, and its files' licences.",
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
## @utility
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
## @utility
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
## v5 (2.0.0, P5): no source copies; doctrees beside the site; built fresh and swapped in.
## v6 (2.0.0, S8): the `clew` domain extension.
## @version 6
## @utility
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
        ## S8 (2.0.0): the `clew` domain puts every symbol section in objects.inv.
        "extensions": ["myst_parser", "clew.wiki._sphinxsymbols"],
        "source_suffix": {".rst": "restructuredtext", ".md": "markdown"},
        "exclude_patterns": ["_build"],
        "html_context": context or {},
        "html_extra_path": ["_extra"] if (source / "_extra").is_dir() else [],
        ## P5 (2.0.0): no markdown copy of every page (37.6 MB of 191 on clew's own site).
        "html_copy_source": False,
        "html_show_sourcelink": False,
        **sphinx_settings(config.theme, repo_root, source),
    }
    (source / "conf.py").write_text(
        "".join(f"{k} = {v!r}\n" for k, v in settings.items()), encoding="utf-8"
    )
    ## THE BUILD CACHE BESIDE THE SITE, NOT IN IT: with no `-d`, sphinx-build wrote its pickled
    ## doctrees into the published directory (87.1 MB of 191). And A FRESH DIRECTORY, SWAPPED IN:
    ## building over the old one kept every page an earlier build wrote, and deleting first
    ## would leave the live hub serving a half-empty site for the length of a build.
    fresh = html.with_name(html.name + ".new")
    if fresh.exists():
        shutil.rmtree(fresh)
    doctrees = html.with_name("_doctrees")
    if build_main(["-q", "-b", "html", "-d", str(doctrees), str(source), str(fresh)]) != 0:
        raise ValueError(f"sphinx-build failed for {source}")
    if html.exists():
        shutil.rmtree(html)
    fresh.rename(html)
    return html


## @brief Each test's executed lines, from per-test coverage.
## @param coverage The parsed contexts, or None.
## @return {test key: {file: lines}}, {} without coverage.
## @version 1
## @utility
def _lines_by_test(coverage: dict | None) -> dict:
    """@brief Group by test. @return Lines."""
    from .slices import lines_per_test

    return lines_per_test(coverage) if coverage else {}


## @brief The entry points, as the Architecture page reads them.
## @param db The index.
## @param repo_root The repository.
## @param config The section.
## @param flow_of Entry name → its flow page.
## @return Entries.
## @version 1
## @req REQ-DDB-WIKI-046
def _architecture_entries(db: Path, repo_root: Path, config: WikiConfig, flow_of: dict) -> list:
    """THE KIND FROM THE DISCOVERY that found it: a console script's title is `script — `func``,
    a thread entry carries the `threads` role, anything else is a `main`.

    @brief Classify entry points.
    @return Entries.
    """
    from .architecture import Entry
    from .entrypoints import entry_point_flows

    out = []
    for spec in entry_point_flows(db, repo_root, config.entry_point_depth):
        if spec.role == "threads":
            kind, label = "thread", ""
        elif " — " in spec.title:
            kind, label = "script", spec.title.split(" — ", 1)[0]
        else:
            kind, label = "main", ""
        ## THE SAME ROLE THE FLOWS GET (`_with_role`): a `tooling`-glob entry is not a container.
        role = _with_role(spec, config).role
        out.append(Entry(kind, spec.entry, spec.file or "", label, flow_of.get(spec.entry), role))
    return out


## @brief Who starts a flow, for its actor lane (P5.6).
## @param spec The flow's spec.
## @param config The section (its declared flows).
## @return The actor's name.
## @version 1
## @req REQ-DDB-WIKI-047
def _actor_of(spec: Any, config: WikiConfig) -> str:
    """FROM WHERE THE SPEC CAME: a test flow is started by the test runner, a thread entry by its
    thread, a console script (title `script — `func``) by a command-line user, a discovered `main`
    by a program launcher; a flow the repository declares by its caller.

    @brief Actor of a flow.
    @return Name.
    """
    if spec.role == "tests":
        return "test runner"
    if spec.role == "threads":
        return "thread start"
    if spec in config.flows:
        return "caller"
    return "command-line user" if " — " in (spec.title or "") else "program launcher"


## @brief The JUnit results the build reads, by test name.
## @param repo_root The repository.
## @param config The section.
## @return Test name → result.
## @version 1
## @utility
def _test_results(repo_root: Path, config: WikiConfig) -> dict:
    """@brief Parse the declared JUnit files. @return Results."""
    from .evidence import parse_junit

    return parse_junit([repo_root / j for j in config.junit if (repo_root / j).is_file()])
