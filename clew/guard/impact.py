"""Change-impact analysis from git diff.

@brief Collect @req tags from changed functions, generate impact reports.
@version 1.1
"""

from __future__ import annotations

import csv
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import (
    REQUIREMENTS_FORMAT_DEFAULT,
    REQUIREMENTS_ID_COLUMN_DEFAULT,
    REQUIREMENTS_NAME_COLUMN_DEFAULT,
    REQUIREMENTS_ROOT_KEY,
    get_impact,
    get_validate,
    parse_source_file,
    resolve_contained_path,
)
from .errors import RequirementsError
from .git import RunCommand, get_diff, get_staged_diff, parse_changed_lines

logger = logging.getLogger(__name__)


## @brief Tracks a changed function with its requirement tags and version info.
#  @version 1.0
#  @dg_internal
@dataclass
class ChangedFunction:
    name: str
    file_path: str
    reqs: list[str] = field(default_factory=list)
    old_version: str | None = None
    new_version: str | None = None


## @brief Groups changed functions by requirement for the impact report.
#  @version 1.1
#  @dg_internal
@dataclass
class ImpactEntry:
    req_id: str
    req_name: str | None = None
    functions: list[ChangedFunction] = field(default_factory=list)


## @brief Collect all changed lines for a file from branch diff and/or staged changes.
#  @version 1.0
#  @dg_internal
def _collect_changed_lines(
    file_path: str,
    staged: bool,
    diff_range: str | None,
    run_command: RunCommand | None,
) -> set[int]:
    changed: set[int] = set()
    diff_output = _get_file_diff(file_path, staged, diff_range, run_command)
    if diff_output:
        changed.update(parse_changed_lines(diff_output))
    if diff_range and not staged:
        staged_output = _get_file_diff(
            file_path, staged=True, diff_range=None, run_command=run_command
        )
        if staged_output:
            changed.update(parse_changed_lines(staged_output))
    return changed


## @brief Get raw diff output for a single file.
#  @version 1.2
#  @dg_internal
def _get_file_diff(
    file_path: str,
    staged: bool,
    diff_range: str | None,
    run_command: RunCommand | None,
) -> str | None:
    # git.run_git owns the failure contract and returns None; no local except tuple to
    # drift onto a narrower set.
    if staged:
        return get_staged_diff(file_path, run_command)
    if diff_range:
        return get_diff(file_path, diff_range, run_command)
    return None


## @brief Find changed functions in a single file given changed line numbers.
#  @version 1.2
#  @req REQ-DDB-GUARD-008
def _extract_changed_functions(
    file_path: str,
    config: dict[str, Any],
    changed_lines: set[int],
) -> list[ChangedFunction]:
    functions = parse_source_file(file_path, config)
    if functions is None:
        return []

    result: list[ChangedFunction] = []
    for func in functions:
        start = func.doxygen.start_line if func.doxygen else func.def_line
        func_lines = set(range(start, func.body_end + 1))
        if not func_lines & changed_lines:
            continue

        reqs = func.doxygen.tags.get("req", []) if func.doxygen else []
        version = None
        if func.doxygen and "version" in func.doxygen.tags:
            version = func.doxygen.tags["version"][0]

        result.append(
            ChangedFunction(
                name=func.name,
                file_path=file_path,
                reqs=reqs,
                new_version=version,
            )
        )
    return result


## @brief Parse source files and cross-reference with git diff to find changed functions.
#  @version 1.2
#  @req REQ-DDB-GUARD-008
def collect_changed_functions(
    file_paths: list[str],
    config: dict[str, Any],
    diff_range: str | None = None,
    staged: bool = False,
    run_command: RunCommand | None = None,
) -> list[ChangedFunction]:
    changed_funcs: list[ChangedFunction] = []

    for file_path in file_paths:
        if not Path(file_path).exists():
            logger.warning("File not found: %s", file_path)
            continue

        changed_lines = _collect_changed_lines(file_path, staged, diff_range, run_command)
        if changed_lines:
            changed_funcs.extend(_extract_changed_functions(file_path, config, changed_lines))

    return changed_funcs


## @brief Extract requirements config, raising if a declared catalog is unusable.
#  @version 2.1
#  @req REQ-DDB-GUARD-011
#  @return Catalog path, format, id column and name column, or None if unconfigured
def _get_requirements_config(
    config: dict[str, Any],
) -> tuple[str, str, str, str] | None:
    req_config = get_impact(config).get("requirements")
    if not req_config:
        logger.info("No impact.requirements section declared; catalog features are off")
        return None

    req_file = req_config.get("file")
    if not req_file:
        raise RequirementsError(
            "impact.requirements is declared but impact.requirements.file is not"
        )
    # Containment before open(): the catalog path is repo-controlled, and its rows are
    # echoed back in validation errors. Without this, pointing it at any readable file
    # turned the error channel into a file-disclosure primitive.
    resolve_contained_path(req_file, setting="impact.requirements.file")
    if not Path(req_file).exists():
        raise RequirementsError(f"Requirements catalog not found: {req_file}")

    fmt = req_config.get("format", REQUIREMENTS_FORMAT_DEFAULT)
    logger.info("Requirements catalog: %s (format=%s)", req_file, fmt)
    return (
        req_file,
        fmt,
        req_config.get("id_column", REQUIREMENTS_ID_COLUMN_DEFAULT),
        req_config.get("name_column", REQUIREMENTS_NAME_COLUMN_DEFAULT),
    )


## @brief Load full requirement rows from the configured catalog.
#  @version 2.1
#  @req REQ-DDB-GUARD-011
#  @return Mapping of requirement ID to its full field row, empty if unconfigured
def load_requirements_full(config: dict[str, Any]) -> dict[str, dict[str, str]]:
    req_info = _get_requirements_config(config)
    if req_info is None:
        return {}

    path, fmt, id_col, name_col = req_info
    loaders = {
        "csv": _load_csv_full,
        "json": _load_json_full,
        "yaml": _load_yaml_full,
    }
    loader = loaders.get(fmt)
    if not loader:
        raise RequirementsError(
            f"Unknown requirements format '{fmt}' for {path}; "
            f"expected one of {', '.join(sorted(loaders))}"
        )
    try:
        reqs = loader(path, id_col)
    except RequirementsError:
        raise
    except (OSError, UnicodeDecodeError, ValueError, AttributeError, KeyError) as e:
        # One wrapper for all three loaders: previously only the YAML path wrapped its
        # failures, so a malformed CSV or JSON catalog escaped the GuardError boundary
        # as a raw traceback for the same class of user error.
        raise RequirementsError(f"Could not parse requirements catalog {path}: {e}") from e
    if not reqs:
        raise RequirementsError(f"Requirements catalog {path} declared no requirements")
    _validate_requirements(reqs, path, config, name_col)
    logger.info("Loaded %d requirement(s) from %s", len(reqs), path)
    return reqs


# A malformed catalog should tell you what is wrong without echoing the file back.
# Reported problems are capped and each key is truncated, so the error channel cannot
# be used to read a file the caller pointed the catalog setting at.
_MAX_REPORTED_PROBLEMS = 10
_MAX_ID_CHARS = 60


## @brief Render a catalog key for an error message, truncated and single-line.
#  @version 1.0
#  @req REQ-DDB-GUARD-016
#  @return A quoted, length-capped, newline-free rendering of the key
def _summarise_id(req_id: str) -> str:
    flat = " ".join(str(req_id).split())
    if len(flat) > _MAX_ID_CHARS:
        flat = flat[:_MAX_ID_CHARS] + "..."
    return repr(flat)


## @brief Enforce the name field and the configured ID pattern across a catalog.
#  @version 2.0
#  @req REQ-DDB-GUARD-011
def _validate_requirements(
    reqs: dict[str, dict[str, str]],
    path: str,
    config: dict[str, Any],
    name_col: str,
) -> None:
    id_pattern = get_validate(config).get("tags", {}).get("req", {}).get("pattern")
    problems: list[str] = []

    for req_id, row in reqs.items():
        shown = _summarise_id(req_id)
        if id_pattern and not re.fullmatch(id_pattern, req_id):
            problems.append(f"{shown}: does not match validate.tags.req.pattern '{id_pattern}'")
        if not str(row.get(name_col, "")).strip():
            problems.append(f"{shown}: missing required field '{name_col}'")

    if not problems:
        return

    reported = problems[:_MAX_REPORTED_PROBLEMS]
    if len(problems) > len(reported):
        reported.append(f"... and {len(problems) - len(reported)} more problem(s)")
    for p in reported:
        logger.error("Requirements catalog error in %s: %s", path, p)
    raise RequirementsError(f"Invalid requirements catalog {path}", reported)


## @brief Load requirement id -> name mapping (convenience wrapper).
#  @version 1.3
#  @req REQ-DDB-GUARD-009
#  @return Dict mapping requirement IDs to their display names, empty if unconfigured
def load_requirements(config: dict[str, Any]) -> dict[str, str]:
    req_info = _get_requirements_config(config)
    if req_info is None:
        return {}
    name_col = req_info[3]
    full = load_requirements_full(config)
    return {rid: row.get(name_col, "") for rid, row in full.items()}


## @brief Filter requirements to those active at the configured current version.
#  @version 1.2
#  @req REQ-DDB-GUARD-009
def filter_requirements_by_version(
    reqs: dict[str, dict[str, str]],
    config: dict[str, Any],
) -> dict[str, dict[str, str]]:
    from .config import compare_versions, parse_version

    version_gate = get_validate(config).get("version_gate", {})
    current_str = version_gate.get("_resolved") or version_gate.get("current_version")
    version_field = version_gate.get("version_field")

    if not current_str or not version_field:
        return reqs

    # A missing field used to default to "v0.0.0", so a typo'd version_field — or rows
    # that simply omit it — silently made EVERY requirement active. The gate then
    # appeared to work while enforcing nothing.
    missing = sorted(
        rid for rid, row in reqs.items() if not str(row.get(version_field, "")).strip()
    )
    if missing:
        problems = [_summarise_id(rid) for rid in missing[:_MAX_REPORTED_PROBLEMS]]
        if len(missing) > len(problems):
            problems.append(f"... and {len(missing) - len(problems)} more")
        logger.error("version_field %r missing on %d requirement(s)", version_field, len(missing))
        raise RequirementsError(
            f"validate.version_gate.version_field is {version_field!r} but these "
            f"requirements do not declare it",
            problems,
        )

    current = parse_version(current_str)
    return {
        rid: row
        for rid, row in reqs.items()
        if compare_versions(parse_version(row[version_field]), current) <= 0
    }


## @brief Convert a list of flat row mappings into req_id -> row form.
#  @details Shared by the JSON and legacy-YAML-list loaders. These were separate
#  comprehensions and had already diverged: only one guarded against a non-dict element,
#  so a JSON array containing a bare string crashed on .get.
#  @version 1.0
#  @req REQ-DDB-GUARD-011
#  @return Mapping of requirement ID to its row
def _rows_from_list(data: list, id_col: str) -> dict[str, dict[str, str]]:
    return {str(row[id_col]): row for row in data if isinstance(row, dict) and row.get(id_col)}


## @brief Parse CSV file into req_id -> full row mapping.
#  @version 1.2
#  @req REQ-DDB-GUARD-011
#  @return Mapping of requirement ID to its row
def _load_csv_full(path: str, id_col: str) -> dict[str, dict[str, str]]:
    reqs: dict[str, dict[str, str]] = {}
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is not None and id_col not in reader.fieldnames:
            raise RequirementsError(
                f"Requirements catalog {path}: id_column {id_col!r} is not in the header "
                f"({', '.join(reader.fieldnames)})"
            )
        for row in reader:
            # A row shorter than the header yields None values (csv restval), which
            # used to raise AttributeError on .strip().
            req_id = (row.get(id_col) or "").strip()
            if req_id:
                reqs[req_id] = {k: (v or "").strip() for k, v in row.items()}
    return reqs


## @brief Parse JSON array into req_id -> full row mapping.
#  @version 1.2
#  @dg_internal
def _load_json_full(path: str, id_col: str) -> dict[str, dict[str, str]]:
    with open(path) as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise RequirementsError(
            f"Requirements catalog {path} must contain a list of rows, got {type(data).__name__}"
        )
    return _rows_from_list(data, id_col)


## @brief Parse a YAML catalog into req_id -> full row mapping.
#  @version 2.1
#  @req REQ-DDB-GUARD-011
#  @return Mapping of requirement ID to its field row
def _load_yaml_full(path: str, id_col: str) -> dict[str, dict[str, str]]:
    try:
        with open(path) as f:
            data = yaml.safe_load(f)
    except (OSError, yaml.YAMLError) as e:
        raise RequirementsError(f"Could not read requirements catalog {path}: {e}") from e

    if isinstance(data, dict) and REQUIREMENTS_ROOT_KEY in data:
        return _rows_from_mapping(data[REQUIREMENTS_ROOT_KEY], path)
    if isinstance(data, list):
        logger.info("%s uses the flat list form; the mapping form is preferred", path)
        return _rows_from_list(data, id_col)
    raise RequirementsError(
        f"Requirements catalog {path} must be a mapping with a top-level "
        f"'{REQUIREMENTS_ROOT_KEY}:' key, or a list of rows"
    )


## @brief Convert a requirements mapping node into id -> row form.
#  @version 1.0
#  @req REQ-DDB-GUARD-011
#  @return Mapping of requirement ID to its field row
def _rows_from_mapping(node: Any, path: str) -> dict[str, dict[str, str]]:
    if not isinstance(node, dict):
        raise RequirementsError(
            f"Requirements catalog {path}: '{REQUIREMENTS_ROOT_KEY}' must be a mapping "
            f"keyed by requirement ID, got {type(node).__name__}"
        )
    rows: dict[str, dict[str, str]] = {}
    for req_id, fields in node.items():
        if not isinstance(fields, dict):
            raise RequirementsError(
                f"Requirements catalog {path}: {req_id} must be a mapping of fields, "
                f"got {type(fields).__name__}"
            )
        rows[str(req_id)] = {k: str(v) for k, v in fields.items()}
    return rows


## @brief Group changed functions by requirement for the impact report.
#  @version 1.1
#  @req REQ-DDB-GUARD-010
def build_impact_report(
    changed_functions: list[ChangedFunction],
    config: dict[str, Any],
) -> list[ImpactEntry]:
    req_names = load_requirements(config)

    req_funcs: dict[str, list[ChangedFunction]] = {}
    for cf in changed_functions:
        for req in cf.reqs:
            req_funcs.setdefault(req, []).append(cf)

    return [
        ImpactEntry(req_id=req_id, req_name=req_names.get(req_id), functions=funcs)
        for req_id, funcs in sorted(req_funcs.items())
    ]


## @brief Render impact entries as a markdown table with summary.
#  @version 1.2
#  @req REQ-DDB-GUARD-010
#  @return Markdown-formatted impact report string
def format_markdown(entries: list[ImpactEntry]) -> str:
    if not entries:
        return "No requirements affected.\n"

    lines = ["## Change Impact Report", ""]
    lines.append("| REQ | Name | Functions Changed |")
    lines.append("|-----|------|-------------------|")

    total_funcs = 0
    for entry in entries:
        name = entry.req_name or "\u2014"
        func_names = ", ".join(f.name for f in entry.functions)
        total_funcs += len(entry.functions)
        lines.append(f"| {entry.req_id} | {name} | {func_names} |")

    lines.append("")
    lines.append(
        f"**Total: {len(entries)} requirement(s) affected, {total_funcs} function(s) changed**"
    )
    return "\n".join(lines) + "\n"


## @brief Render impact entries as a JSON array.
#  @version 1.2
#  @req REQ-DDB-GUARD-010
#  @return JSON-formatted impact report string
def format_json(entries: list[ImpactEntry]) -> str:
    data = [
        {
            "req_id": entry.req_id,
            "req_name": entry.req_name,
            "functions": [
                {"name": f.name, "file": f.file_path, "version": f.new_version}
                for f in entry.functions
            ],
        }
        for entry in entries
    ]
    return json.dumps(data, indent=2) + "\n"


## @brief Render impact entries as human-readable text.
#  @version 1.2
#  @req REQ-DDB-GUARD-010
#  @return Plain-text summary of affected requirement IDs
def format_text(entries: list[ImpactEntry]) -> str:
    if not entries:
        return "No requirements affected.\n"
    req_ids = [e.req_id for e in entries]
    return f"REQs affected: {', '.join(req_ids)}\n"


## @brief Dispatch to the appropriate formatter based on config.
#  @version 1.2
#  @dg_internal
def format_report(entries: list[ImpactEntry], config: dict[str, Any]) -> str:
    fmt = get_impact(config).get("output", {}).get("format", "markdown")
    formatters = {"json": format_json, "text": format_text}
    return formatters.get(fmt, format_markdown)(entries)


## @brief Orchestrate diff analysis, requirement mapping, and report generation.
#  @version 1.1
#  @req REQ-DDB-GUARD-010
def run_impact(
    file_paths: list[str],
    config: dict[str, Any],
    staged: bool = False,
    diff_range: str | None = None,
    run_command: RunCommand | None = None,
) -> str:
    changed = collect_changed_functions(
        file_paths,
        config,
        diff_range=diff_range,
        staged=staged,
        run_command=run_command,
    )
    entries = build_impact_report(changed, config)
    return format_report(entries, config)
