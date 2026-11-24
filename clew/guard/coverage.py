# SPDX-License-Identifier: MIT
"""Requirement coverage analysis for clew guard.

@brief Cross-reference @req tags against requirements file and report coverage gaps.
@version 1.0
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
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
#  v2.3: `covered_via` when `coverage.through_dependencies` is set (2.1, #73 item 2)
#  @version 2.3
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
    uncovered = all_req_ids - tagged_reqs - {e["req_id"] for e in exempt}

    report: dict[str, Any] = {
        "total_requirements": len(all_req_ids),
        "covered": sorted(tagged_reqs & all_req_ids),
        "uncovered": sorted(uncovered),
        "exempt": exempt,
        "orphan_refs": sorted(tagged_reqs - all_req_ids),
        "unmapped_functions": sorted(unmapped),
        "traceability": traceability(all_tagged, config),
    }
    ## 2.1 (#73 item 2): ABSENT unless opted in, so a report that never looked says nothing.
    if (config.get("coverage") or {}).get("through_dependencies"):
        via = covered_via(uncovered, config)
        report["covered_via"] = via
        report["uncovered"] = sorted(uncovered - {v["req_id"] for v in via})
    return report


## @brief The uncovered requirements a pinned dependency realises: implemented or exempt at its pin.
#  @details 2.1 (#73 item 2, owner Q/A 2026-11-24). A dependency requirement whose `satisfies` /
#  `serves` names one of ours counts when its own code tags it AT THE PIN (`git grep` in the local
#  clone at that revision — measured, never the dependency's own status claim), or when THIS
#  repository's exemption rules exempt it. The first match wins; an unreadable dependency
#  contributes nothing and says so.
#  @version 1.0
#  @req REQ-DDB-GUARD-022
#  @return [{req_id, via: "<catalog>:<id>", how: implemented|exempt}] sorted by req_id
def covered_via(uncovered: set[str], config: dict[str, Any]) -> list[dict[str, str]]:
    from ..requirements import read_catalog_at

    req = get_requirements(config)
    found: dict[str, dict[str, str]] = {}
    for source in req.get("external") or []:
        if not isinstance(source, dict) or not {"repo", "rev", "path"} <= set(source):
            continue
        name = str(source.get("name") or Path(str(source["repo"])).name)
        try:
            rows = read_catalog_at(Path.cwd(), source)
        except ValueError as exc:
            logger.warning("coverage through %s skipped: %s", name, exc)
            continue
        for dep_id, row in rows.items():
            for target, how in _realised(uncovered, dep_id, row, source, req):
                found.setdefault(target, {"req_id": target, "via": f"{name}:{dep_id}", "how": how})
    return [found[r] for r in sorted(found)]


## @brief The uncovered requirements one dependency row realises, and how.
#  @version 1.0
#  @utility
#  @return [(our requirement id, implemented|exempt)]
def _realised(
    uncovered: set[str],
    dep_id: str,
    row: dict[str, Any],
    source: dict[str, Any],
    req: dict[str, Any],
) -> list[tuple[str, str]]:
    from ..requirements import link_ids
    from .config import exemption

    targets = [t.split(":", 1)[-1] for t in link_ids(row) if t.split(":", 1)[-1] in uncovered]
    if not targets:
        return []
    if _tagged_at_pin(source, dep_id):
        return [(t, "implemented") for t in targets]
    if exemption(row, req) is not None:
        return [(t, "exempt") for t in targets]
    return []


## @brief Whether a dependency's code tags a requirement at its pinned revision.
#  @version 1.0
#  @utility
#  @return True when `@req <id>` appears in its tree at that revision
def _tagged_at_pin(source: dict[str, Any], dep_id: str) -> bool:
    from ..requirements import git_text

    found = git_text(
        Path.cwd() / str(source["repo"]),
        "grep",
        "-l",
        "-w",
        "-F",
        f"@req {dep_id}",
        str(source["rev"]),
        "--",
    )
    return bool(found and found.strip())


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
#  v1.2: `exempt_when` fields too, each with its reason (2.1, #72 item 14)
#  @version 1.2
#  @req REQ-DDB-GUARD-022
#  @return [{req_id, status}] sorted by id; [] when no exempt status is declared
def _exempt(
    rows: dict[str, dict[str, str]], untagged: set[str], config: dict[str, Any]
) -> list[dict[str, str]]:
    from .config import exemption

    req = get_requirements(config)
    field = req.get("status_field", "status")
    out = []
    for rid in sorted(untagged):
        reason = exemption(rows[rid], req)
        if reason is not None:
            out.append({"req_id": rid, "status": rows[rid].get(field, ""), "reason": reason})
    return out


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
#  v1.4: each exempt row says why — its status or an `exempt_when` field (2.1, #72 item 14)
#  v1.5: requirements covered through dependencies (2.1, #73 item 2)
#  @version 1.5
#  @req REQ-DDB-GUARD-022
#  @return Formatted text report string
def format_coverage_text(report: dict[str, Any]) -> str:
    lines = [f"Requirements coverage: {len(report['covered'])}/{report['total_requirements']}"]
    if report.get("traceability"):
        lines.append(traceability_line(report["traceability"]))
    sections = (
        ("Uncovered", report["uncovered"]),
        (
            "Exempt by status or field",
            [f"{e['req_id']} ({_why(e)})" for e in report.get("exempt", [])],
        ),
        ("Covered through dependencies", [_via(v) for v in report.get("covered_via", [])]),
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


## @brief One requirement covered through a dependency, as a report line.
#  @version 1.0
#  @utility
#  @return Text
def _via(row: dict[str, str]) -> str:
    return f"{row['req_id']} via {row['via']} ({row['how']})"


## @brief Why one exempt requirement is exempt: its reason, else its status.
#  @version 1.0
#  @utility
#  @return Text
def _why(row: dict[str, Any]) -> str:
    return str(row.get("reason") or row.get("status") or "")


## @brief Format coverage report as markdown.
#  @details v1.2: exempt requirements listed with their status.
#  v1.3: the requirement ratio and floor (2.0.0, PG3)
#  v1.4: each exempt row says why (2.1, #72 item 14)
#  v1.5: requirements covered through dependencies (2.1, #73 item 2)
#  @version 1.5
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
        lines.append(f"\n## Exempt by status or field ({len(report['exempt'])})")
        lines += [f"- {e['req_id']} ({_why(e)})" for e in report["exempt"]]
    if report.get("covered_via"):
        lines.append(f"\n## Covered through dependencies ({len(report['covered_via'])})")
        lines += [f"- {_via(v)}" for v in report["covered_via"]]
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
