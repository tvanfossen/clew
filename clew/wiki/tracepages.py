# SPDX-License-Identifier: MIT
"""The requirement trace and the model entries, gathered once and written as the site's pages.

Owner 2026-11-15: the wiki is ENTIRELY GENERATED — from `.clew.yaml` (`wiki:` and `guard:`), from
the requirements catalog, from clew-guard's `impact.json`, from the clew index, and from the prose
the repository selects — and "requirements and summary are filling the same sort of role", so the
trace is ONE page:

  1. what the catalog declares and what the index found (counts, charts, the burndown);
  2. per requirement group: implemented, tested, tiers, single-layer coverage;
  3. (change impact is its own section since round 3, P1g — `impactpage`);
  4. every requirement — its tier, the functions implementing it (linked to source), its tests
     with their status, layers, the catalog's declared status and priority, model entries and
     mutation outcomes; the id opens the requirement's modal (round 3, P1d: `reqmodal`), which
     holds the acceptance criteria, the flows it is on and a prefilled issue link;
  5. external rules and pinned sub-catalogs.

Sources and where they are found:
  * the CATALOG — `requirements.resolve_catalog_path`, the same resolver the index uses
    (declaration in `guard:`, then the `requirements.yaml` convention);
  * IMPACT — `wiki.impact` when declared, else `<guard.output_dir>/impact/impact.json`; absent
    means no section, never an empty one claiming nothing changed.

@brief Gather the trace; write the requirements and model-entries pages.
@version 3
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalogs import declared_catalog
from .config import Audience, WikiConfig
from .htmltable import code, linked, source_url, table, tag, text
from .reqmodal import first, issue_links, requirement_cell, test_link, via

## Where clew-guard writes its impact report, under its `output_dir`.
_IMPACT = Path("impact") / "impact.json"


## @brief Everything the trace pages and the version snapshot are drawn from, gathered once.
## @version 2
class Trace:
    """@brief Evidence, nodes, catalogs, rules, the declared catalog, impact, symbols, test links. @version 4"""

    ## @brief Hold the gathered parts.
    ## @param parts Evidence, nodes, refs, catalogs, declared, impact, commit, catalog path.
    ## @param config The section (rules, link template).
    ## v2: `symbols` (P1f).
    ## v3: `test_href` (P2a).
    ## v4: `issues`, `unlinked`, `issues_note` (P3a).
    ## v5: `decisions` (P3c).
    ## v6: `missing`, the declared reports that were not there.
    ## @version 6
    ## @dg_internal
    def __init__(self, parts: dict[str, Any], config: WikiConfig) -> None:
        """@brief Store. @return None."""
        self.evidence = parts["evidence"]
        self.by_id = {r.req_id: r for r in self.evidence}
        self.nodes = parts["nodes"]
        self.refs = parts["refs"]
        self.catalogs = parts["catalogs"]
        ## Declared test reports that were not there: unmeasured, and the page says so.
        self.missing = parts.get("missing", [])
        self.declared: dict[str, dict] = parts["declared"]
        self.catalog_path: str = parts["catalog_path"]
        self.impact: list[dict] | None = parts["impact"]
        self.commit: str = parts["commit"]
        self.rules = config.rules
        self.template = config.link_template
        ## (function, file) pairs with a symbol section; `link` points there (round 3, P1f).
        self.symbols: set[tuple[str, str]] = set()
        ## {test name: its section} (round 3, P2a).
        self.test_href: dict[str, str] = {}
        ## Open issues by requirement; None when not fetched (round 3, P3a).
        self.issues: dict[str, list] | None = None
        ## Open issues linked to no requirement.
        self.unlinked: list = []
        ## Why issues were not fetched, when they were asked for and could not be.
        self.issues_note: str = ""
        ## {requirement: decisions naming it} (round 3, P3c).
        self.decisions: dict[str, list] = {}

    ## @brief Gather the trace for a repository.
    ## @param repo_root The repository.
    ## @param db The index.
    ## @param config The section.
    ## @param commit The commit the site describes.
    ## @return The trace.
    ## v2: a Sphinx-needs import (`wiki.needs`, round 3 P3c).
    ## v3: the declared reports that are missing (round 3, P6c).
    ## @version 3
    ## @dg_internal
    @classmethod
    def gather(cls, repo_root: Path, db: Path, config: WikiConfig, commit: str) -> Trace:
        """@brief Read every source. @return Trace."""
        from .catalogs import catalog_requirements, pin_problems
        from .evidence import requirement_evidence
        from .sources import load_nodes, node_references

        evidence = requirement_evidence(
            db,
            junit=[repo_root / j for j in config.junit],
            coverage=(repo_root / config.coverage) if config.coverage else None,
            target_only=config.target_only,
            mutations=(repo_root / config.mutations) if config.mutations else None,
            inputs=config.inputs,
            repo_root=repo_root,
        )
        catalog_path, declared = declared_catalog(repo_root)
        if config.needs:
            evidence, declared = _with_needs(evidence, declared, Path(repo_root) / config.needs)
        parts = {
            "evidence": evidence,
            "nodes": load_nodes(repo_root, config.sources)[0],
            "refs": node_references(db),
            "catalogs": [
                (spec, catalog_requirements(repo_root, spec)[0], pin_problems(repo_root, spec))
                for spec in config.catalogs
            ],
            "declared": declared,
            "catalog_path": catalog_path,
            "impact": load_impact(impact_path(repo_root, config)),
            "commit": commit,
            "missing": [
                r
                for r in (
                    *config.junit,
                    *([config.coverage] if config.coverage else []),
                    *(rel for _fmt, rel in config.inputs.results),
                )
                if not (Path(repo_root) / r).is_file()
            ],
        }
        return cls(parts, config)

    ## @brief The nodes that serve a requirement.
    ## @param req_id The requirement.
    ## @return Node addresses.
    ## @version 1
    ## @dg_internal
    def nodes_for(self, req_id: str) -> list[str]:
        """@brief Look up. @return Addresses."""
        return [n.ref for n in self.nodes if req_id in n.requirements]

    ## @brief The snapshot a version-keyed build records.
    ## @param key The version key.
    ## @return Plain data.
    ## @version 1
    ## @dg_internal
    def snapshot(self, key: str) -> dict:
        """@brief Snapshot. @return Data."""
        return {
            "key": key,
            "commit": self.commit,
            "requirements": {r.req_id: r.tier for r in self.evidence},
            "nodes": sorted(n.ref for n in self.nodes),
        }

    ## @brief A function linked to its source.
    ## @param name The name.
    ## @param rel Its file.
    ## @param line Its line.
    ## @return HTML.
    ## v2: a function with a symbol section links there — a dossier reference, whose page links
    ## the source (owner 2026-11-15) — else to its source.
    ## @version 2
    ## @dg_internal
    def link(self, name: str, rel: str, line: int) -> str:
        """@brief Link. @return HTML."""
        if (name, rel) in self.symbols:
            from .symbols import symbol_href

            return linked(name, symbol_href(name, rel))
        return linked(name, source_url(self.template, self.commit, rel, max(line, 1)))


## @brief Merge a Sphinx-needs import: the catalog wins; a need the index never saw is MISSING.
## @param evidence The evidence rows.
## @param declared The catalog's entries.
## @param path The needs.json.
## @return (evidence, declared) with the needs merged.
## @version 1
## @req REQ-DDB-WIKI-030
def _with_needs(evidence: list, declared: dict, path: Path) -> tuple[list, dict]:
    """A NEED NOTHING IMPLEMENTS IS A REQUIREMENT WITH NO IMPLEMENTER — MISSING, not absent: the
    import declares it, and the site says nobody has done it.

    @brief Merge needs.
    @return Evidence and entries.
    """
    from .evidence import RequirementEvidence
    from .imports import parse_needs

    needs = parse_needs(path)
    merged = {**{k: dict(v) for k, v in needs.items()}, **declared}
    for key, entry in declared.items():
        merged[key] = {**needs.get(key, {}), **entry}
    known = {r.req_id for r in evidence}
    extra = [
        RequirementEvidence(nid, needs[nid].get("name", ""), "MISSING", (), ())
        for nid in sorted(needs)
        if nid not in known
    ]
    return [*evidence, *extra], merged


## @brief Where the impact report is: declared, else clew-guard's output directory.
## @param repo_root The repository.
## @param config The section.
## @return The path.
## @version 1
## @req REQ-DDB-WIKI-015
def impact_path(repo_root: Path, config: WikiConfig) -> Path:
    """@brief Locate impact.json. @return Path."""
    if config.impact:
        return Path(repo_root) / config.impact
    from ..requirements import load_guard_config

    guard = load_guard_config(repo_root) or {}
    return Path(repo_root) / str(guard.get("output_dir") or "docs/generated/") / _IMPACT


## @brief Read clew-guard's impact report.
## @param path The report.
## @return Its entries, or None when there is no report.
## @version 1
## @req REQ-DDB-WIKI-015
def load_impact(path: Path) -> list[dict] | None:
    """ABSENT IS NOT EMPTY: no file → None (no section); `[]` → "no requirement affected".

    @brief Read impact.
    @return Entries or None.
    """
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, list) else None


## @brief Write the requirements page: summary, charts, impact, every requirement, rules, pins.
## @param trace The gathered trace.
## @param config The section.
## @param source The Sphinx source directory.
## @param rules The audience rules.
## @param burndown A burndown SVG for a versioned site, or "".
## @param flows The flow pages (a requirement lists the flows its implementers are on).
## @param issues The issue tracker, or None (no issue links).
## @return The page name.
## v2: requirements front and centre (round 3, P1d) — group cards that filter the list first,
## each requirement opening its whole trace in the shared modal, the group table kept below.
## v3: change impact moved to its own section (`impactpage`, P1g).
## v4: open issues (P3a).
## v5: names each declared test report that was not there — unmeasured (round 3, P6c).
## @version 5
## @req REQ-DDB-WIKI-012
def requirements_page(
    trace: Trace,
    config: WikiConfig,
    source: Path,
    rules: Audience,
    burndown: str = "",
    flows: tuple = (),
    issues: tuple[str, str] | None = None,
) -> str:
    """@brief Render the trace. @return Page name."""
    from .summary import charts_block, group_cards, group_table

    ev = trace.evidence
    origin = f" declared in `{trace.catalog_path}`" if trace.catalog_path else ""
    lines = [
        "# Requirements",
        "",
        f"{len(ev)} requirements{origin} or tagged in the code: "
        f"{sum(1 for r in ev if r.implementers)} implemented, "
        f"{sum(1 for r in ev if r.tests)} tested, {sum(1 for r in ev if r.tier == 'PASS')} passing.",
        "",
        _link_kinds(ev),
        "",
        *_missing_note(trace),
        "## Groups",
        "",
        "Each card is a requirement group; pick one to filter the list below to it.",
        "",
        *_raw(group_cards(ev)),
        "## Every requirement",
        "",
        "Open a requirement for its acceptance criteria, implementers, tests, flows and issues.",
        "",
        *_raw(
            _requirement_table(
                trace, {"trace": trace, "rules": rules, "flows": list(flows), "issues": issues}
            )
        ),
        "## Charts",
        "",
        *_raw(charts_block(ev)),
    ]
    if burndown:
        lines += ["## Burndown", "", *_raw(f'<div class="chart-card">{burndown}</div>')]
    lines += ["## Group counts", "", *_raw(group_table(ev, config.inputs.min_layers))]
    lines += _issues_section(trace)
    lines += _rules_section(trace, rules)
    lines += _catalogs_section(trace, rules)
    (source / "requirements.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "requirements"


## @brief A sentence saying how the tested requirements' links were made.
## @param ev Evidence rows.
## @return Markdown.
## @version 1
## @dg_internal
def _link_kinds(ev: list) -> str:
    """INFERENCE IS DISCLOSED: a requirement tested only through the call graph is counted apart,
    since reaching an implementer is weaker than verifying it.

    @brief Link-kind sentence.
    @return Text.
    """

    def only(attr: str) -> int:
        return sum(1 for r in ev if r.tests and set(getattr(r, attr)) == {t for t, _s in r.tests})

    tagged = sum(
        1
        for r in ev
        if any(
            t not in (*r.declared_tests, *r.measured_tests, *r.inferred_tests) for t, _s in r.tests
        )
    )
    return (
        f"Test links: {tagged} requirements by tag or mapping, {only('measured_tests')} only by "
        f"per-test coverage, {only('declared_tests')} only by the catalog's evidence files, "
        f"{only('inferred_tests')} only by call-graph inference."
    )


## @brief The per-requirement table.
## @param trace The gathered trace.
## @param ctx The modal context: trace, rules, flows, issue target.
## @return HTML.
## v2: the id opens the requirement's modal; rows carry their group for the cards' filter;
## a long test list is its counts (the modal lists it).
## v3: short test lists link to the tests' sections (P2a).
## v4: an issues column (P3a).
## @version 4
## @dg_internal
def _requirement_table(trace: Trace, ctx: dict[str, Any]) -> str:
    """@brief Render rows. @return HTML."""
    from .summary import group_of

    rows = []
    for row in trace.evidence:
        entry = trace.declared.get(row.req_id, {})
        rows.append(
            [
                requirement_cell(row, entry, ctx),
                tag(row.tier),
                _fold(
                    [trace.link(n, f, ln) for n, f, ln in row.implementer_sites],
                    f"{len(row.implementer_sites)} functions",
                ),
                _tests_cell(row, trace.test_href),
                ", ".join(f"{text(k)} {n}" for k, n in row.layers or ()),
                text(str(first(entry, "x-status", "status"))),
                text(str(first(entry, "x-priority", "priority"))),
                "<br>".join(code(n) for n in trace.nodes_for(row.req_id)),
                "<br>".join(f"{code(m)} → {code(t)} {text(o)}" for m, t, o in row.mutations or ()),
                issue_links((trace.issues or {}).get(row.req_id, [])),
            ]
        )
    head = ["requirement", "tier", "implemented by", "tests", "layers", "declared", "priority"]
    groups = [f' data-group="{text(group_of(r.req_id))}"' for r in trace.evidence]
    return table(
        [*head, "model entries", "mutations", "issues"],
        rows,
        cls="trace",
        keep=tuple(head[:4]),
        row_attrs=groups,
    )


## @brief A list, folded behind a summary when it is long.
## @param items Item HTML.
## @param summary The summary line.
## @return HTML.
## @version 1
## @dg_internal
def _fold(items: list[str], summary: str) -> str:
    """LONG LINKAGE FOLDS rather than stretching the row (owner 2026-11-15: hard to read).

    @brief Fold.
    @return HTML.
    """
    if len(items) <= 4:
        return "<br>".join(items)
    return f'<details class="fold"><summary>{text(summary)}</summary>{"<br>".join(items)}</details>'


## @brief The tests column: a short list inline, a long one as its counts (the modal lists it).
## @param row The evidence row.
## @param hrefs {test name: its section}.
## @return HTML.
## v2: tests link to their sections (P2a).
## @version 2
## @dg_internal
def _tests_cell(row: Any, hrefs: dict[str, str]) -> str:
    """ONE FULL LIST PER REQUIREMENT, in its modal: repeating hundreds of tests in a folded cell
    doubled the page (clew's own: 2.2 MB).

    @brief Tests cell.
    @return HTML.
    """
    if len(row.tests) <= 4:
        return "<br>".join(f"{test_link(t, hrefs)} {tag(s)}{via(row, t)}" for t, s in row.tests)
    return f'<span class="tsum">{text(_test_summary(row.tests))}</span>'


## @brief "N tests: a passed · b absent".
## @param tests (test, status) pairs.
## @return The summary.
## @version 1
## @dg_internal
def _test_summary(tests: tuple) -> str:
    """@brief Count by status. @return Text."""
    counts: dict[str, int] = {}
    for _t, status in tests:
        counts[status] = counts.get(status, 0) + 1
    return f"{len(tests)} tests: " + " · ".join(f"{n} {k}" for k, n in sorted(counts.items()))


## @brief Open issues: a note when they were asked for and not fetched; those linked to no
## requirement, when they were fetched.
## @param trace The gathered trace.
## @return Markdown lines ([] when issues were not asked for).
## @version 1
## @dg_internal
def _issues_section(trace: Trace) -> list[str]:
    """@brief Issues section. @return Lines."""
    if trace.issues_note:
        return ["## Open issues", "", f'<p class="not-measured">{text(trace.issues_note)}</p>', ""]
    if trace.issues is None:
        return []
    linked = len({i.id for found in trace.issues.values() for i in found})
    lines = ["## Open issues", "", f"{linked} open issues link a requirement.", ""]
    if trace.unlinked:
        lines += ["### Not linked to a requirement", "", *_raw(issue_links(trace.unlinked, True))]
    return lines


## @brief The rule → requirement → function → test chain.
## @param trace The gathered trace.
## @param rules The audience rules.
## @return Markdown lines; [] when no rule is declared.
## @version 1
## @dg_internal
def _rules_section(trace: Trace, rules: Audience) -> list[str]:
    """@brief Rules table. @return Lines."""
    if not trace.rules:
        return []
    rows = []
    for rule in trace.rules:
        rid = f'<a href="{text(rule.url)}">{text(rule.id)}</a>' if rule.url else text(rule.id)
        for req_id in rule.requirements or ("",):
            row = trace.by_id.get(req_id)
            rows.append(
                [
                    rid,
                    text(rule.status),
                    "" if rules.exclude_requirement_text else text(rule.title),
                    f'<a href="#{text(req_id)}">{text(req_id)}</a>' if req_id else "",
                    tag(row.tier if row else "MISSING"),
                    "<br>".join(code(n) for n in (row.implementers if row else ())),
                    "<br>".join(f"{code(t)} {tag(s)}" for t, s in (row.tests if row else ())),
                ]
            )
    head = ["rule", "status", "title", "requirement", "tier", "functions", "tests"]
    return ["## Rules", "", *_raw(table(head, rows))]


## @brief Each pinned sub-catalog's rows, at their pin.
## @param trace The gathered trace.
## @param rules The audience rules.
## @return Markdown lines; [] when no catalog is declared.
## @version 1
## @dg_internal
def _catalogs_section(trace: Trace, rules: Audience) -> list[str]:
    """@brief Catalog tables, with the pin problems `check` reports. @return Lines."""
    lines: list[str] = []
    for spec, reqs, problems in trace.catalogs:
        lines += [f"## Catalog `{spec.name}` at `{spec.pin}`", ""]
        lines += [f"Read from `{spec.repo}/{spec.catalog}` at the pin.", ""]
        lines += [f"**Check failure:** {p}" + "\n" for p in problems]
        rows = []
        for req in reqs:
            row = trace.by_id.get(req.req_id)
            rows.append(
                [
                    text(req.req_id),
                    "" if rules.exclude_requirement_text else text(req.title),
                    tag(row.tier) if row else "",
                    "<br>".join(code(n) for n in (row.implementers if row else ())),
                ]
            )
        lines += _raw(table(["requirement", "title", "tier here", "functions here"], rows))
    return lines


## @brief A "not measured" note naming each declared report that was not there.
## @param trace The gathered trace.
## @return Markdown lines; [] when every declared report was read.
## @version 1
## @dg_internal
def _missing_note(trace: Trace) -> list[str]:
    """@brief Note. @return Lines."""
    if not trace.missing:
        return []
    names = ", ".join(f"<code>{text(m)}</code>" for m in trace.missing)
    return _raw(
        f'<p class="not-measured"><b>Not measured.</b> Declared but not found: {names}. '
        "Results and coverage from them are absent, not zero; run the tests (and coverage) "
        "before building.</p>"
    ) + [""]


## @brief Write the model-entries page.
## @param trace The gathered trace.
## @param config The section (sources, for their files).
## @param source The Sphinx source directory.
## @return The page name.
## v2: a worked example diagram from a real entry (round 3, P1g).
## @version 2
## @req REQ-DDB-WIKI-004
def nodes_page(trace: Trace, config: WikiConfig, source: Path) -> str:
    """SAID WHAT IT IS (owner 2026-11-15: "model nodes is not well understood"): the page opens by
    explaining that each row is an entry of a declared model file, with a worked example drawn
    from a real row (round 3, P1g), and groups entries by source.

    @brief Render model entries.
    @return Page name.
    """
    lines = [
        "# Model entries",
        "",
        "Entries of the model files this repository declares in `wiki.sources` — a key table, a "
        "command list, a topic list. Code generated from a model should trace to the model entry, "
        "not stop at a generated setter: a function names the entry it realises with a "
        "`@node <source>:<id>` tag, and an entry may name the requirements it serves.",
        "",
        *_raw(_node_example(trace)),
    ]
    for spec in config.sources:
        mine = [n for n in trace.nodes if n.source == spec.name]
        lines += [f"## `{spec.name}` — `{spec.path}`", ""]
        rows = [
            [
                code(n.id),
                text(n.doc),
                "<br>".join(code(f) for f in trace.refs.get(n.ref, ())),
                "<br>".join(
                    f'<a href="requirements.html#{text(r)}">{text(r)}</a>' for r in n.requirements
                ),
            ]
            for n in mine
        ]
        lines += _raw(
            table(["entry", "doc", "realised by", "serves"], rows, keep=("entry", "realised by"))
        )
    (source / "nodes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return "nodes"


## @brief A worked example, drawn from the first entry a function realises: entry → function →
## requirement. Nothing when no entry is realised yet.
## @param trace The gathered trace.
## @return HTML.
## @version 1
## @req REQ-DDB-WIKI-024
def _node_example(trace: Trace) -> str:
    """A REAL ROW OF THIS REPOSITORY, not a made-up one: the example is what the reader will
    find in the table below.

    @brief Example diagram.
    @return HTML.
    """
    node = next((n for n in trace.nodes if trace.refs.get(n.ref)), None)
    if node is None:
        return ""
    func = sorted(trace.refs[node.ref])[0]
    reqs = list(node.requirements) or sorted(
        r.req_id for r in trace.evidence if any(n == func for n, _f, _l in r.implementer_sites)
    )
    boxes = [
        (node.ref, node.file, "model entry"),
        (func, "realises it", "function"),
        (reqs[0] if reqs else "—", "served", "requirement"),
    ]
    arrows = [f"@node {node.ref}", "@req" if reqs else ""]
    parts = []
    for i, (name, sub, kind) in enumerate(boxes):
        x = 10 + i * 270
        parts.append(
            f'<rect x="{x}" y="20" width="200" height="64" rx="10"/>'
            f'<text class="k" x="{x + 12}" y="40">{text(kind)}</text>'
            f'<text class="n" x="{x + 12}" y="60">{text(name)}</text>'
            f'<text class="k" x="{x + 12}" y="76">{text(sub)}</text>'
        )
    for i, label in enumerate(arrows):
        x = 210 + i * 270
        parts.append(
            f'<path d="M{x + 4} 52H{x + 64}" marker-end="url(#node-arrow)"/>'
            f'<text class="a" x="{x + 34}" y="14" text-anchor="middle">{text(label)}</text>'
        )
    return (
        '<svg class="node-example" xmlns="http://www.w3.org/2000/svg" width="760" height="100" '
        'viewBox="0 0 760 100" role="img" aria-label="How a model entry traces to a requirement">'
        '<defs><marker id="node-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" '
        'markerHeight="8" orient="auto"><path d="M0 0L10 5L0 10z"/></marker></defs>'
        f"{''.join(parts)}</svg>"
    )


## @brief An HTML block as MyST raw lines.
## @param html The HTML.
## @return Lines.
## @version 1
## @dg_internal
def _raw(html: str) -> list[str]:
    """@brief Wrap. @return Lines."""
    return ["```{raw} html", html, "```", ""]
