# SPDX-License-Identifier: MIT
"""The requirement trace and the model entries, gathered once and written as the site's pages.

Owner 2026-11-15: the wiki is ENTIRELY GENERATED — from `.clew.yaml` (`wiki:` and `guard:`), from
the requirements catalog, from clew-guard's `impact.json`, from the clew index, and from the prose
the repository selects — and "requirements and summary are filling the same sort of role", so the
trace is ONE page:

  1. what the catalog declares and what the index found (counts, charts, the burndown);
  2. per requirement group: implemented, tested, tiers, single-layer coverage;
  3. the latest change impact (`impact.json`): requirements whose implementing functions changed;
  4. every requirement — its tier, the functions implementing it (linked to source), its tests
     with their status, layers, the catalog's declared status and priority, model entries and
     mutation outcomes; the acceptance criteria fold out under the id;
  5. external rules and pinned sub-catalogs.

Sources and where they are found:
  * the CATALOG — `requirements.resolve_catalog_path`, the same resolver the index uses
    (declaration in `guard:`, then the `requirements.yaml` convention);
  * IMPACT — `wiki.impact` when declared, else `<guard.output_dir>/impact/impact.json`; absent
    means no section, never an empty one claiming nothing changed.

@brief Gather the trace; write the requirements and model-entries pages.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .catalogs import declared_catalog
from .config import Audience, WikiConfig
from .htmltable import code, linked, source_url, table, tag, text

## Where clew-guard writes its impact report, under its `output_dir`.
_IMPACT = Path("impact") / "impact.json"


## @brief Everything the trace pages and the version snapshot are drawn from, gathered once.
## @version 2
class Trace:
    """@brief Evidence, nodes, catalogs, rules, the declared catalog and impact. @version 2"""

    ## @brief Hold the gathered parts.
    ## @param parts Evidence, nodes, refs, catalogs, declared, impact, commit, catalog path.
    ## @param config The section (rules, link template).
    ## @version 1
    ## @dg_internal
    def __init__(self, parts: dict[str, Any], config: WikiConfig) -> None:
        """@brief Store. @return None."""
        self.evidence = parts["evidence"]
        self.by_id = {r.req_id: r for r in self.evidence}
        self.nodes = parts["nodes"]
        self.refs = parts["refs"]
        self.catalogs = parts["catalogs"]
        self.declared: dict[str, dict] = parts["declared"]
        self.catalog_path: str = parts["catalog_path"]
        self.impact: list[dict] | None = parts["impact"]
        self.commit: str = parts["commit"]
        self.rules = config.rules
        self.template = config.link_template

    ## @brief Gather the trace for a repository.
    ## @param repo_root The repository.
    ## @param db The index.
    ## @param config The section.
    ## @param commit The commit the site describes.
    ## @return The trace.
    ## @version 1
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
    ## @version 1
    ## @dg_internal
    def link(self, name: str, rel: str, line: int) -> str:
        """@brief Link. @return HTML."""
        return linked(name, source_url(self.template, self.commit, rel, max(line, 1)))


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
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-012
def requirements_page(
    trace: Trace, config: WikiConfig, source: Path, rules: Audience, burndown: str = ""
) -> str:
    """@brief Render the trace. @return Page name."""
    from .summary import charts_block, group_table

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
        *_raw(charts_block(ev)),
    ]
    if burndown:
        lines += ["## Burndown", "", *_raw(f'<div class="chart-card">{burndown}</div>')]
    lines += ["## By group", "", *_raw(group_table(ev, config.inputs.min_layers))]
    lines += _impact_section(trace, rules)
    lines += ["## Every requirement", "", *_raw(_requirement_table(trace, rules))]
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
## @param rules The audience rules.
## @return HTML.
## @version 1
## @dg_internal
def _requirement_table(trace: Trace, rules: Audience) -> str:
    """@brief Render rows. @return HTML."""
    rows = []
    for row in trace.evidence:
        entry = trace.declared.get(row.req_id, {})
        rows.append(
            [
                _requirement_cell(row, entry, rules),
                tag(row.tier),
                _fold(
                    [trace.link(n, f, ln) for n, f, ln in row.implementer_sites],
                    f"{len(row.implementer_sites)} functions",
                ),
                _fold(
                    [f"{code(t)} {tag(s)}{_via(row, t)}" for t, s in row.tests],
                    _test_summary(row.tests),
                ),
                ", ".join(f"{text(k)} {n}" for k, n in row.layers or ()),
                text(str(_first(entry, "x-status", "status"))),
                text(str(_first(entry, "x-priority", "priority"))),
                "<br>".join(code(n) for n in trace.nodes_for(row.req_id)),
                "<br>".join(f"{code(m)} → {code(t)} {text(o)}" for m, t, o in row.mutations or ()),
            ]
        )
    head = ["requirement", "tier", "implemented by", "tests", "layers", "declared", "priority"]
    return table([*head, "model entries", "mutations"], rows, cls="trace", keep=tuple(head[:4]))


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


## @brief How a test was linked, when weaker than a tag.
## @param row The evidence row.
## @param test The test.
## @return HTML ("" for a tagged link).
## @version 1
## @dg_internal
def _via(row: Any, test: str) -> str:
    """@brief Link kind. @return HTML."""
    for kind, tests in (
        ("measured", row.measured_tests),
        ("catalog", row.declared_tests),
        ("inferred", row.inferred_tests),
    ):
        if test in tests:
            return f' <span class="via via-{kind}" title="linked by {kind}">{kind}</span>'
    return ""


## @brief The requirement cell: id, title and folded acceptance criteria.
## @param row The evidence row.
## @param entry Its catalog entry ({} when undeclared).
## @param rules The audience rules (no text when requirement text is excluded).
## @return HTML.
## @version 1
## @dg_internal
def _requirement_cell(row: Any, entry: dict, rules: Audience) -> str:
    """@brief Render the id cell. @return HTML."""
    cell = f'<span class="rid" id="{text(row.req_id)}">{text(row.req_id)}</span>'
    if rules.exclude_requirement_text:
        return cell
    title = row.title or str(_first(entry, "name", "title"))
    if title:
        cell += f'<div class="rtitle">{text(title)}</div>'
    criteria = str(_first(entry, "acceptance_criteria", "acceptance", "description"))
    if criteria:
        cell += f"<details><summary>acceptance</summary>{text(criteria)}</details>"
    return cell


## @brief The latest change impact from clew-guard's report.
## @param trace The gathered trace.
## @param rules The audience rules.
## @return Markdown lines; [] when there is no report.
## @version 1
## @dg_internal
def _impact_section(trace: Trace, rules: Audience) -> list[str]:
    """@brief Impact table. @return Lines."""
    if trace.impact is None:
        return []
    lines = ["## Change impact", "", "From clew-guard's latest impact report.", ""]
    if not trace.impact:
        return [*lines, "No requirement was affected by the last change.", ""]
    rows = [
        [
            f'<a href="#{text(str(e.get("req_id")))}">{text(str(e.get("req_id")))}</a>',
            "" if rules.exclude_requirement_text else text(str(e.get("req_name") or "")),
            "<br>".join(
                f"{trace.link(str(f.get('name')), str(f.get('file') or ''), 0)} "
                f'<span class="ver">v{text(str(f.get("version") or "?"))}</span>'
                for f in e.get("functions") or []
            ),
        ]
        for e in trace.impact
    ]
    return [*lines, *_raw(table(["requirement", "name", "functions changed"], rows))]


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


## @brief Write the model-entries page.
## @param trace The gathered trace.
## @param config The section (sources, for their files).
## @param source The Sphinx source directory.
## @return The page name.
## @version 1
## @req REQ-DDB-WIKI-004
def nodes_page(trace: Trace, config: WikiConfig, source: Path) -> str:
    """SAID WHAT IT IS (owner 2026-11-15: "model nodes is not well understood"): the page opens by
    explaining that each row is an entry of a declared model file, and groups entries by source.

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


## @brief An HTML block as MyST raw lines.
## @param html The HTML.
## @return Lines.
## @version 1
## @dg_internal
def _raw(html: str) -> list[str]:
    """@brief Wrap. @return Lines."""
    return ["```{raw} html", html, "```", ""]


## @brief The first non-empty field of a catalog entry.
## @param entry The entry.
## @param keys Field names, in preference order.
## @return The value, or "".
## @version 1
## @dg_internal
def _first(entry: dict, *keys: str) -> Any:
    """@brief Pick a field. @return Value or ""."""
    return next((entry[k] for k in keys if entry.get(k) not in (None, "")), "")
