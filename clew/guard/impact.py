# SPDX-License-Identifier: MIT
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
from ..owners import OwnerResolver

from .config import (
    REQUIREMENTS_FORMAT_DEFAULT,
    REQUIREMENTS_ID_COLUMN_DEFAULT,
    REQUIREMENTS_NAME_COLUMN_DEFAULT,
    REQUIREMENTS_ROOT_KEY,
    get_requirements,
    get_validate,
    parse_source_file,
    resolve_contained_path,
)
from .errors import RequirementsError
from .git import RunCommand, get_diff, get_staged_diff, parse_changed_lines

logger = logging.getLogger(__name__)


## @brief Tracks a changed function with its requirement tags and version info.
#  v1.1: `via`, the callers through which an untagged change reaches this entry (2.1, clew#74)
#  @version 1.1
#  @utility
@dataclass
class ChangedFunction:
    name: str
    file_path: str
    reqs: list[str] = field(default_factory=list)
    old_version: str | None = None
    new_version: str | None = None
    ## None: linked by its own `@req`. A list: reached through these callers (`reach.Reach.via`).
    via: list[str] | None = None


## @brief Groups changed functions by requirement for the impact report.
#  v1.2: `reviewers`, the owners of the changed files; None when the repo names no owners (2.0.0)
#  v1.3: `tests`, the covering tests; None when the report did not read them (2.1, clew#74)
#  @version 1.3
#  @utility
@dataclass
class ImpactEntry:
    req_id: str
    req_name: str | None = None
    functions: list[ChangedFunction] = field(default_factory=list)
    reviewers: list[str] | None = None
    tests: list[Any] | None = None


## @brief What a report names beside its entries: changes and files that reach no requirement.
#  @details 2.1 (clew#74 items 3, 4). Present only when the reach step ran: an empty list then
#  means "looked, found none", where an absent key means "never looked".
#  @version 1.0
#  @utility
@dataclass
class ImpactExtras:
    unmapped: list[dict[str, str]] = field(default_factory=list)
    unmapped_files: list[str] = field(default_factory=list)


## @brief Collect all changed lines for a file from branch diff and/or staged changes.
#  @version 1.0
#  @utility
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
#  @utility
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
#  v1.3: the changes come from `collect_changes` (2.1, clew#74)
#  @version 1.3
#  @req REQ-DDB-GUARD-008
def collect_changed_functions(
    file_paths: list[str],
    config: dict[str, Any],
    diff_range: str | None = None,
    staged: bool = False,
    run_command: RunCommand | None = None,
) -> list[ChangedFunction]:
    return collect_changes(file_paths, config, diff_range, staged, run_command)[0]


## @brief The changed functions, and the changed files that hold none of them.
#  @details 2.1 (clew#74 item 4): a header of declarations, a CMake file, a YAML file and a
#  deleted file change the build without changing a function, so a consumer selecting tests must
#  be told about them rather than left to assume nothing changed.
#  @version 1.0
#  @req REQ-DDB-GUARD-010
#  @return (changed functions, changed files with no changed function)
def collect_changes(
    file_paths: list[str],
    config: dict[str, Any],
    diff_range: str | None = None,
    staged: bool = False,
    run_command: RunCommand | None = None,
) -> tuple[list[ChangedFunction], list[str]]:
    changed_funcs: list[ChangedFunction] = []
    unmapped_files: list[str] = []
    for file_path in file_paths:
        if not Path(file_path).exists():
            logger.warning("File not found: %s", file_path)
            unmapped_files.append(file_path)
            continue
        changed_lines = _collect_changed_lines(file_path, staged, diff_range, run_command)
        found = (
            _extract_changed_functions(file_path, config, changed_lines) if changed_lines else []
        )
        changed_funcs.extend(found)
        if changed_lines and not found:
            unmapped_files.append(file_path)
    return changed_funcs, unmapped_files


## @brief Extract requirements config, raising if a declared catalog is unusable.
#  @details v2.2: `file` is optional beside `external` (GH #68).
#  v2.3: reads the top-level requirements: section (2.0.0, R5-CFG F7)
#  @version 2.3
#  @req REQ-DDB-GUARD-011
#  @return Catalog path, format, id column and name column, or None if unconfigured
def _get_requirements_config(
    config: dict[str, Any],
) -> tuple[str, str, str, str] | None:
    req_config = get_requirements(config)
    if not req_config:
        logger.info("No requirements section declared; catalog features are off")
        return None

    req_file = req_config.get("file")
    if not req_file:
        # GH #68: a repository whose catalogue its consumer owns names only `external`.
        if req_config.get("external"):
            return None
        raise RequirementsError(
            "impact.requirements is declared but neither impact.requirements.file nor "
            "impact.requirements.external is"
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


## @brief The requirement ids of the external catalogues this repository names (GH #68).
#  v1.1: reads the top-level requirements: section (2.0.0, R5-CFG F7)
#  v1.2: a `parent: true` catalogue whose clone is absent is recorded unchecked (2.1, #73 item 3)
#  @version 1.2
#  @req REQ-DDB-GUARD-027
#  @return Mapping of requirement ID to its row; empty when none is named
def load_external_requirements(
    config: dict[str, Any], unchecked: list[str] | None = None
) -> dict[str, dict[str, str]]:
    """The consumer's catalogue, read where it is pinned: each entry is a path or {repo, rev,
    path} relative to the repository, through the reader the wiki uses. An unreadable one or a
    URL is an error naming it, never an empty catalogue that would pass every tag.

    A PARENT (`parent: true`, #73 item 3, owner Q/A 2026-11-24) is the one exception: a module's
    gate runs where the product's clone may not be, so an unreadable parent is recorded in
    `unchecked` (by name) and its links are reported unchecked, never refused. The product's own
    gate, where the clone is, still checks them."""
    from ..requirements import read_catalog_at

    req_config = get_requirements(config)
    out: dict[str, dict[str, str]] = {}
    for source in req_config.get("external") or []:
        try:
            out.update(read_catalog_at(Path.cwd(), source))
        except ValueError as exc:
            if isinstance(source, dict) and source.get("parent") is True and unchecked is not None:
                name = str(source.get("name") or Path(str(source.get("repo", "parent"))).name)
                logger.warning(
                    "parent catalogue %s is not readable here (%s); its links are unchecked",
                    name,
                    exc,
                )
                unchecked.append(name)
                continue
            raise RequirementsError(f"impact.requirements.external: {exc}") from exc
    if out:
        logger.info("Loaded %d requirement(s) from external catalogues", len(out))
    return out


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


## @brief Every failure-mode id the local catalogue declares.
#  @details 2.2: read from each entry's `failure_modes` through `failuremodes.modes_of`, the
#  parser the index uses, so the two cannot disagree on a shape. A CSV catalogue cannot nest a
#  mapping and declares none. A malformed `failure_modes` is refused by name.
#  @version 1.0
#  @req REQ-DDB-GUARD-001
#  @return Mode ids; empty when no catalogue is declared or it declares none
def load_failure_mode_ids(config: dict[str, Any]) -> set[str]:
    from ..failuremodes import modes_of

    req_info = _get_requirements_config(config)
    if req_info is None or req_info[1] == "csv":
        return set()
    path, fmt, id_col, _name = req_info
    try:
        with open(path) as f:
            data = json.load(f) if fmt == "json" else yaml.safe_load(f)
        entries = _raw_entries(data, id_col)
        return {m.mode_id for rid, fields in entries for m in modes_of(rid, fields)}
    except ValueError as e:
        raise RequirementsError(f"Requirements catalog {path}: {e}") from e
    except (OSError, yaml.YAMLError) as e:
        raise RequirementsError(f"Could not read requirements catalog {path}: {e}") from e


## @brief A catalogue's entries as (id, raw fields), in either catalogue shape.
#  @version 1.0
#  @utility
#  @return Pairs; nested values kept as the catalogue holds them
def _raw_entries(data: Any, id_col: str) -> list[tuple[str, dict[str, Any]]]:
    if isinstance(data, dict) and isinstance(data.get(REQUIREMENTS_ROOT_KEY), dict):
        node = data[REQUIREMENTS_ROOT_KEY]
        return [(str(k), v) for k, v in node.items() if isinstance(v, dict)]
    if isinstance(data, list):
        return [(str(r[id_col]), r) for r in data if isinstance(r, dict) and r.get(id_col)]
    return []


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
#  v1.3: reads the top-level requirements: section (2.0.0, R5-CFG F7)
#  @version 1.3
#  @req REQ-DDB-GUARD-009
def filter_requirements_by_version(
    reqs: dict[str, dict[str, str]],
    config: dict[str, Any],
) -> dict[str, dict[str, str]]:
    from .config import compare_versions, parse_version

    validate = get_validate(config)
    current_str = validate.get("_current_version_resolved") or validate.get("current_version")
    version_field = get_requirements(config).get("version_field")

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
            f"requirements.version_field is {version_field!r} but these "
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
#  @utility
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
#  v1.2: names each requirement's reviewers through `owners` (2.0.0, S2/S3 served)
#  v1.3: built by `build_report` with no reach step (2.1, clew#74)
#  @version 1.3
#  @req REQ-DDB-GUARD-010
def build_impact_report(
    changed_functions: list[ChangedFunction],
    config: dict[str, Any],
    owners: OwnerResolver | None = None,
) -> list[ImpactEntry]:
    return build_report(changed_functions, config, owners)[0]


## @brief Group changes by requirement, and with a reach step, add tests, `via` and unmapped.
#  @details 2.1 (clew#74 items 2-4). Without `reach`: the 2.0.0 entries and no extras. With it,
#  a change with no `@req` is walked to the requirements its callers carry (`via`), each entry
#  lists its covering tests, and whatever reaches nothing is reported, never dropped.
#  @version 1.0
#  @req REQ-DDB-GUARD-010
#  @return (entries, extras or None when the reach step did not run)
def build_report(
    changed_functions: list[ChangedFunction],
    config: dict[str, Any],
    owners: OwnerResolver | None = None,
    reach: Any = None,
    unmapped_files: list[str] | None = None,
) -> tuple[list[ImpactEntry], ImpactExtras | None]:
    req_names = load_requirements(config)
    extras = ImpactExtras(unmapped_files=list(unmapped_files or [])) if reach else None
    req_funcs: dict[str, list[ChangedFunction]] = {}
    for cf in changed_functions:
        for req in cf.reqs:
            req_funcs.setdefault(req, []).append(cf)
        if not cf.reqs and reach is not None:
            _place_untagged(cf, reach, req_funcs, extras)
    tests = reach.tests_for(set(req_funcs), set(req_names)) if reach else {}
    entries = [
        ImpactEntry(
            req_id=req_id,
            req_name=req_names.get(req_id),
            functions=funcs,
            reviewers=_reviewers(owners, funcs),
            tests=list(tests.get(req_id, [])) if reach else None,
        )
        for req_id, funcs in sorted(req_funcs.items())
    ]
    return entries, extras


## @brief File an untagged change under the requirements its callers reach, else as unmapped.
#  @version 1.0
#  @utility
def _place_untagged(
    cf: ChangedFunction, reach: Any, req_funcs: dict[str, list[ChangedFunction]], extras: Any
) -> None:
    from .reach import NO_CALLER, NO_INDEX, TEST_CODE

    if reach.is_test(cf.file_path):
        extras.unmapped.append({"name": cf.name, "file": cf.file_path, "reason": TEST_CODE})
        return
    reached = reach.via(cf)
    for req_id, chain in reached:
        req_funcs.setdefault(req_id, []).append(
            ChangedFunction(cf.name, cf.file_path, [], cf.old_version, cf.new_version, chain)
        )
    if not reached:
        reason = NO_INDEX if reach.db is None else NO_CALLER
        extras.unmapped.append({"name": cf.name, "file": cf.file_path, "reason": reason})


## @brief The owners of a requirement's changed files, first-seen order, each once.
#  @details None when the repository keeps no owners file: "nobody" and "this repository names no
#  owners" are different answers, so the key is left out rather than emptied.
#  @version 1.0
#  @utility
#  @return Owner names, or None
def _reviewers(owners: OwnerResolver | None, funcs: list[ChangedFunction]) -> list[str] | None:
    if owners is None or not owners.has_sources():
        return None
    names: dict[str, None] = {}
    for cf in funcs:
        for owner, *_rest in owners.owners_of(cf.file_path):
            names.setdefault(owner, None)
    return list(names)


## @brief Make one table cell out of repo-controlled text.
#  @details Requirement names and function names come from the TARGET'S catalog and source,
#  and this table is written to `docs/generated/impact/`, `git add`ed, and printed to stderr —
#  where it lands in the context of whatever agent is watching the commit. A `|` forges a
#  column and a newline forges a ROW, so unescaped text can write arbitrary content into a
#  file the developer is about to commit (1.1.0 audit, M6). ESCAPED, NOT FILTERED: the text is
#  still reported, because a name a gate silently rewrote is a name nobody can grep for.
#  `clew.guard` shares no code with the pipeline, so `_inlineable` is deliberately not reused.
#  @version 1.0
#  @utility
#  @return The text with CR/LF/tab collapsed and pipes escaped
def _cell(text: str) -> str:
    collapsed = text.replace("\r", " ").replace("\n", " ").replace("\t", " ")
    return collapsed.replace("|", "\\|")


## @brief Render impact entries as a markdown table with summary.
#  v1.4: reviewers from the owners files (2.0.0, S2/S3 served)
#  v1.5: a Tests column, `via` beside a function, and the unmapped sections (2.1, clew#74)
#  @version 1.5
#  @req REQ-DDB-GUARD-010
#  @return Markdown-formatted impact report string
def format_markdown(entries: list[ImpactEntry], extras: ImpactExtras | None = None) -> str:
    if not entries:
        return ("No requirements affected.\n" + _unmapped_markdown(extras)).rstrip("\n") + "\n"

    ## A Reviewers column only when the repository names owners: see `_reviewers`. A Tests column
    ## only when the report read them.
    owned = any(e.reviewers is not None for e in entries)
    tested = any(e.tests is not None for e in entries)
    head = "| REQ | Name | Functions Changed |" + (" Reviewers |" if owned else "")
    rule = "|-----|------|-------------------|" + ("-----------|" if owned else "")
    lines = ["## Change Impact Report", "", head + (" Tests |" if tested else "")]
    lines.append(rule + ("-------|" if tested else ""))
    total_funcs = 0
    for entry in entries:
        total_funcs += len(entry.functions)
        lines.append(_markdown_row(entry, owned, tested))
    lines.append("")
    lines.append(
        f"**Total: {len(entries)} requirement(s) affected, {total_funcs} function(s) changed**"
    )
    return "\n".join(lines) + "\n" + _unmapped_markdown(extras)


## @brief One requirement's table row.
#  @version 1.0
#  @utility
#  @return The row.
def _markdown_row(entry: ImpactEntry, owned: bool, tested: bool) -> str:
    name = _cell(entry.req_name or "\u2014")
    func_names = ", ".join(
        _cell(f.name) + (f" (via {_cell(' → '.join(f.via))})" if f.via else "")
        for f in entry.functions
    )
    dash = chr(0x2014)
    who = f" {', '.join(_cell(r) for r in entry.reviewers or []) or dash} |" if owned else ""
    tests = f" {', '.join(_cell(t.name) for t in entry.tests or []) or dash} |" if tested else ""
    return f"| {_cell(entry.req_id)} | {name} | {func_names} |{who}{tests}"


## @brief The unmapped sections: changes and files that reach no requirement.
#  @version 1.0
#  @utility
#  @return Markdown, "" when the reach step did not run or found nothing.
def _unmapped_markdown(extras: ImpactExtras | None) -> str:
    if extras is None:
        return ""
    lines: list[str] = []
    if extras.unmapped:
        lines += ["", "### Changes that reach no requirement", ""]
        lines += [
            f"- `{_cell(u['name'])}` ({_cell(u['file'])}): {_cell(u['reason'])}"
            for u in extras.unmapped
        ]
    if extras.unmapped_files:
        lines += ["", "### Changed files with no changed function", ""]
        lines += [f"- {_cell(f)}" for f in extras.unmapped_files]
    return "\n".join(lines) + ("\n" if lines else "")


## PS3 (2.0.0, owner Q/A 2026-11-19): impact.json's format version and its keys, which
## docs/wire-keys.json covers. A removed or renamed key moves the version; an added one is additive.
IMPACT_SCHEMA_VERSION = 1
IMPACT_ENTRY_KEYS = ("functions", "req_id", "req_name", "reviewers", "tests")
IMPACT_FUNCTION_KEYS = ("file", "name", "version", "via")
## 2.1 (clew#74): the report's own keys; `unmapped` and `unmapped_files` only after a reach step.
IMPACT_REPORT_KEYS = ("entries", "schema_version", "unmapped", "unmapped_files")


## @brief Render impact entries as a versioned JSON object.
#  v1.3: reviewers from the owners files (2.0.0, S2/S3 served)
#  v2.0 (2.0.0, PS3): `{"schema_version": 1, "entries": [...]}` — the bare array had no version.
#  v2.1 (2.1, clew#74): `tests`, `via`, `unmapped`, `unmapped_files`, each only when computed;
#  additive, so schema_version stays 1.
#  @version 2.1
#  @req REQ-DDB-GUARD-010
#  @return JSON-formatted impact report string
def format_json(entries: list[ImpactEntry], extras: ImpactExtras | None = None) -> str:
    rows = [
        {
            "req_id": entry.req_id,
            "req_name": entry.req_name,
            "functions": [
                {
                    "name": f.name,
                    "file": f.file_path,
                    "version": f.new_version,
                    **({"via": f.via} if f.via is not None else {}),
                }
                for f in entry.functions
            ],
            **({"reviewers": entry.reviewers} if entry.reviewers is not None else {}),
            **(
                {"tests": [{"name": t.name, "file": t.file} for t in entry.tests]}
                if entry.tests is not None
                else {}
            ),
        }
        for entry in entries
    ]
    data: dict[str, Any] = {"schema_version": IMPACT_SCHEMA_VERSION, "entries": rows}
    if extras is not None:
        data.update(unmapped=extras.unmapped, unmapped_files=extras.unmapped_files)
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
#  v1.3: the format is a parameter, not impact.output.format (2.0.0, R5-CFG F9)
#  v1.4: the extras ride along to the formats that show them (2.1, clew#74)
#  @version 1.4
#  @utility
def format_report(
    entries: list[ImpactEntry], fmt: str = "markdown", extras: ImpactExtras | None = None
) -> str:
    if fmt == "text":
        return format_text(entries)
    return (format_json if fmt == "json" else format_markdown)(entries, extras)


## @brief Orchestrate diff analysis, requirement mapping, and report generation.
#  1.2 (round 4, R11): no files with a range or --staged means every file that changed there;
#  an empty report then means nothing changed, never that nothing was read.
#  1.3 (2.0.0, R5-CFG F9): the format is the caller's (`fmt`), not a config key; the entries are
#  built by `impact_entries`, which `clew guard impact --write` also uses.
#  1.4 (2.1, clew#74): built by `impact_report`, with tests, `via` and the unmapped lists.
#  @version 1.4
#  @req REQ-DDB-GUARD-010
def run_impact(
    file_paths: list[str],
    config: dict[str, Any],
    staged: bool = False,
    diff_range: str | None = None,
    run_command: RunCommand | None = None,
    fmt: str = "markdown",
) -> str:
    entries, extras = impact_report(file_paths, config, staged, diff_range, run_command)
    return format_report(entries, fmt, extras)


## @brief Collect the changed functions and map them to the requirements they implement.
#  v1.1: reviewers from the owners files (2.0.0, S2/S3 served)
#  v1.2: the entries of `impact_report` (2.1, clew#74)
#  @version 1.2
#  @req REQ-DDB-GUARD-010
#  @return One entry per changed function
def impact_entries(
    file_paths: list[str],
    config: dict[str, Any],
    staged: bool = False,
    diff_range: str | None = None,
    run_command: RunCommand | None = None,
) -> list[ImpactEntry]:
    return impact_report(file_paths, config, staged, diff_range, run_command)[0]


## @brief The full report: entries with covering tests and `via`, and the unmapped lists.
#  @details 2.1 (clew#74). The gate runs at the repository root (pre-commit's working
#  directory); the caller walk reads that repository's existing index, never builds one.
#  @version 1.0
#  @req REQ-DDB-GUARD-010
#  @return (entries, extras)
def impact_report(
    file_paths: list[str],
    config: dict[str, Any],
    staged: bool = False,
    diff_range: str | None = None,
    run_command: RunCommand | None = None,
) -> tuple[list[ImpactEntry], ImpactExtras | None]:
    from ..indexlocate import find_index
    from .reach import Reach

    if not file_paths and (staged or diff_range):
        from .git import get_changed_files

        file_paths = get_changed_files(diff_range, staged, run_command) or []
    changed, unmapped_files = collect_changes(file_paths, config, diff_range, staged, run_command)
    root = Path.cwd()
    owners = OwnerResolver.from_repo(root, config.get("owners"))
    reach = Reach(find_index(root), repo_root=root, config=config)
    return build_report(changed, config, owners, reach, unmapped_files)
