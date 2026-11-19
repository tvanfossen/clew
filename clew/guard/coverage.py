"""Requirement coverage analysis for clew guard.

@brief Cross-reference @req tags against requirements file and report coverage gaps.
@version 1.0
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any

from .config import get_requirements
from .impact import load_requirements_full
from .tags import collect_tagged_functions

if TYPE_CHECKING:
    from .tags import TaggedFunction

logger = logging.getLogger(__name__)


## @brief Analyze requirement coverage across all documented functions.
#  @details v2.1: requirements whose declared status is exempt are listed under `exempt`,
#  not counted as uncovered (round 3, P6c).
#  v2.2: the requirement ratio and floor (2.0.0, PG3)
#  @version 2.2
#  @req REQ-DDB-GUARD-022
#  @return Dict with covered, uncovered, exempt, orphan_refs, unmapped_functions
def analyze_coverage(
    source_dirs: list[str],
    config: dict[str, Any],
) -> dict[str, Any]:
    full_reqs = load_requirements_full(config)
    all_tagged = collect_tagged_functions(source_dirs, config)

    all_req_ids = set(full_reqs.keys())
    tagged_reqs = _collect_req_ids(all_tagged)
    unmapped = _collect_unmapped_functions(all_tagged)
    exempt = _exempt(full_reqs, all_req_ids - tagged_reqs, config)

    return {
        "total_requirements": len(all_req_ids),
        "covered": sorted(tagged_reqs & all_req_ids),
        "uncovered": sorted(all_req_ids - tagged_reqs - {e["req_id"] for e in exempt}),
        "exempt": exempt,
        "orphan_refs": sorted(tagged_reqs - all_req_ids),
        "unmapped_functions": sorted(unmapped),
        "traceability": traceability(all_tagged, config),
    }


## @brief The requirement ratio: functions with a req tag among those with a req tag or an exemption.
#  @details 2.0.0 (PG3, owner). Over NON-TEST code (the declared `tests.paths`, else the index's
#  built-in test paths), one function per identity (`Class::name(params)`), so a declaration and
#  its definition count once. A function carrying a req tag is traced whatever else it carries.
#  The floor (`coverage.min_req_ratio`) is None unless declared: no built-in number.
#  @version 1.0
#  @req REQ-DDB-GUARD-022
#  @return {req, exempt, by_tag, ratio, floor, below_floor}
def traceability(all_tagged: list[TaggedFunction], config: dict[str, Any]) -> dict[str, Any]:
    from ..testscope import TEST_PATH_FACTS, is_test_path

    patterns = tuple(config.get("test_paths") or TEST_PATH_FACTS)
    traced: set[str] = set()
    tags_of: dict[str, set[str]] = {}
    for tf in all_tagged:
        if is_test_path(str(tf.file_path).lstrip("./"), patterns):
            continue
        key = tf.qualified or tf.name
        if tf.reqs:
            traced.add(key)
        tags_of.setdefault(key, set()).update(tf.exemptions)
    exempt = {k: tags for k, tags in tags_of.items() if k not in traced and tags}
    by_tag: dict[str, int] = {}
    for tags in exempt.values():
        for tag in tags:
            by_tag[tag] = by_tag.get(tag, 0) + 1
    total = len(traced) + len(exempt)
    ratio = round(len(traced) / total, 4) if total else None
    floor = (config.get("coverage") or {}).get("min_req_ratio")
    return {
        "req": len(traced),
        "exempt": len(exempt),
        "by_tag": dict(sorted(by_tag.items())),
        "ratio": ratio,
        "floor": floor,
        "below_floor": floor is not None and ratio is not None and ratio < floor,
    }


## @brief One line stating the requirement ratio, its per-tag counts and the floor.
#  @version 1.0
#  @utility
#  @return The line
def traceability_line(trace: dict[str, Any]) -> str:
    tags = ", ".join(f"@{t} {n}" for t, n in trace["by_tag"].items()) or "none"
    ratio = "n/a" if trace["ratio"] is None else f"{trace['ratio']:g}"
    if trace["floor"] is None:
        verdict = "no floor declared"
    elif trace["below_floor"]:
        verdict = f"below the floor {trace['floor']:g}"
    else:
        verdict = f"floor {trace['floor']:g} met"
    return (
        f"Traceability: {trace['req']} with @req, {trace['exempt']} exempt ({tags}) — "
        f"ratio {ratio} ({verdict})"
    )


## @brief The untagged requirements whose declared status exempts them from coverage.
#  v1.1: reads the top-level requirements: section (2.0.0, R5-CFG F7)
#  @version 1.1
#  @req REQ-DDB-GUARD-022
#  @return [{req_id, status}] sorted by id; [] when no exempt status is declared
def _exempt(
    rows: dict[str, dict[str, str]], untagged: set[str], config: dict[str, Any]
) -> list[dict[str, str]]:
    req = get_requirements(config)
    statuses = set(req.get("exempt_status") or [])
    field = req.get("status_field", "status")
    return [
        {"req_id": rid, "status": rows[rid].get(field, "")}
        for rid in sorted(untagged)
        if rows[rid].get(field) in statuses
    ]


## @brief Collect all requirement IDs referenced across tagged functions.
#  @version 1.1
#  @req REQ-DDB-GUARD-022
#  @return Set of all unique requirement IDs
def _collect_req_ids(all_tagged: list[TaggedFunction]) -> set[str]:
    result: set[str] = set()
    for tf in all_tagged:
        result.update(tf.reqs)
    return result


## @brief Find documented functions with no requirement mapping, skipping exempt ones.
#  @details v2.2 (2.0.0, PG2): by IDENTITY (`Class::name(params)`) across every entry. A
#  declaration and its definition share it, so a documented header prototype without `req` tag is
#  mapped when its definition carries one or is exempt. Unrelated namesakes with different
#  parameters stay apart.
#  @version 2.2
#  @req REQ-DDB-GUARD-022
#  @return Set of function names with no requirement mapping
def _collect_unmapped_functions(all_tagged: list[TaggedFunction]) -> set[str]:
    settled = {tf.qualified or tf.name for tf in all_tagged if tf.reqs or tf.is_exempt}
    return {tf.name for tf in all_tagged if (tf.qualified or tf.name) not in settled}


## @brief Format coverage report as text.
#  @details v1.2: exempt requirements listed with their status (round 3, P6c).
#  v1.3: the requirement ratio and floor (2.0.0, PG3)
#  @version 1.3
#  @req REQ-DDB-GUARD-022
#  @return Formatted text report string
def format_coverage_text(report: dict[str, Any]) -> str:
    lines = [f"Requirements coverage: {len(report['covered'])}/{report['total_requirements']}"]
    if report.get("traceability"):
        lines.append(traceability_line(report["traceability"]))
    sections = (
        ("Uncovered", report["uncovered"]),
        ("Exempt by status", [f"{e['req_id']} ({e['status']})" for e in report.get("exempt", [])]),
        ("Orphan @req refs", report["orphan_refs"]),
        ("Functions without @req", [f"{f}()" for f in report["unmapped_functions"]]),
    )
    for title, items in sections:
        if items:
            lines.append(f"\n{title} ({len(items)}):")
            lines += [f"  - {i}" for i in items]
    return "\n".join(lines)


## @brief Format coverage report as JSON.
#  @version 1.1
#  @req REQ-DDB-GUARD-022
#  @return JSON string of the coverage report
def format_coverage_json(report: dict[str, Any]) -> str:
    return json.dumps(report, indent=2)


## @brief Format coverage report as markdown.
#  @details v1.2: exempt requirements listed with their status.
#  v1.3: the requirement ratio and floor (2.0.0, PG3)
#  @version 1.3
#  @req REQ-DDB-GUARD-022
#  @return Markdown formatted coverage report string
def format_coverage_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Requirements Coverage: {len(report['covered'])}/{report['total_requirements']}"]
    if report.get("traceability"):
        lines.append(f"\n{traceability_line(report['traceability'])}")
    if report["uncovered"]:
        lines.append(f"\n## Uncovered ({len(report['uncovered'])})")
        for r in report["uncovered"]:
            lines.append(f"- {r}")
    if report.get("exempt"):
        lines.append(f"\n## Exempt by status ({len(report['exempt'])})")
        lines += [f"- {e['req_id']} ({e['status']})" for e in report["exempt"]]
    if report["orphan_refs"]:
        lines.append(f"\n## Orphan Refs ({len(report['orphan_refs'])})")
        for r in report["orphan_refs"]:
            lines.append(f"- `{r}`")
    if report["unmapped_functions"]:
        lines.append(f"\n## Unmapped Functions ({len(report['unmapped_functions'])})")
        for f in report["unmapped_functions"]:
            lines.append(f"- `{f}()`")
    return "\n".join(lines)


## @brief Run coverage analysis and return exit code.
#  v1.5: the requirement ratio and floor (2.0.0, PG3)
#  @version 1.5
#  @req REQ-DDB-GUARD-022
#  @return Exit code: 0 if no gaps, 1 if gaps exist
def run_coverage(
    source_dirs: list[str],
    config: dict[str, Any],
    output_format: str = "text",
) -> int:
    report = analyze_coverage(source_dirs, config)

    formatters = {
        "json": format_coverage_json,
        "markdown": format_coverage_markdown,
    }
    formatter = formatters.get(output_format, format_coverage_text)
    print(formatter(report))

    return 1 if coverage_gaps(report) else 0


## @brief Whether a coverage report fails the gate.
#  @details Uncovered catalog entries, `req` tag naming no entry, or a ratio below the declared floor
#  (2.0.0, PG3). Shared by `clew guard coverage` and the pre-commit hook.
#  @version 1.0
#  @req REQ-DDB-GUARD-022
#  @return True when the gate fails
def coverage_gaps(report: dict[str, Any]) -> bool:
    trace = report.get("traceability") or {}
    return bool(report["uncovered"] or report["orphan_refs"] or trace.get("below_floor"))
