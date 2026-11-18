"""Requirement coverage analysis for doxygen-guard.

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
#  @version 2.1
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
    }


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
#  @version 2.1
#  @req REQ-DDB-GUARD-022
#  @return Set of function names with no requirement mapping
def _collect_unmapped_functions(all_tagged: list[TaggedFunction]) -> set[str]:
    return {tf.name for tf in all_tagged if not tf.reqs and not tf.is_exempt}


## @brief Format coverage report as text.
#  @details v1.2: exempt requirements listed with their status (round 3, P6c).
#  @version 1.2
#  @req REQ-DDB-GUARD-022
#  @return Formatted text report string
def format_coverage_text(report: dict[str, Any]) -> str:
    lines = [f"Requirements coverage: {len(report['covered'])}/{report['total_requirements']}"]
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
#  @version 1.2
#  @req REQ-DDB-GUARD-022
#  @return Markdown formatted coverage report string
def format_coverage_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Requirements Coverage: {len(report['covered'])}/{report['total_requirements']}"]
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
#  @version 1.4
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

    has_gaps = bool(report["uncovered"] or report["orphan_refs"])
    return 1 if has_gaps else 0
