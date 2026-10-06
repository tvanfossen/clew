"""CLI entry point for doxygen-guard.

@brief Argument parsing, file iteration, and subcommand dispatch.
@version 1.1
"""

from __future__ import annotations

import argparse
import logging
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from .checks import (
    Violation,
    check_duplicate_tags,
    check_file_presence,
    check_presence,
    check_req_coverage,
    check_req_exists,
    check_return_presence,
    check_tags,
    check_unknown_tags,
    check_version_staleness,
)
from .config import (
    get_impact,
    get_validate,
    load_config,
    parse_content_for_file,
    parse_source_file,
    validate_output_path,
)
from .errors import ConfigError, GuardError
from .git import get_branch_diff_range, get_file_at_revision, git_add
from .impact import (
    build_impact_report,
    collect_changed_functions,
    format_json,
    format_markdown,
    run_impact,
)

logger = logging.getLogger(__name__)

_SUBCOMMANDS = {"validate", "impact", "coverage", "config", "files", "doxyfile"}
_FLAGS_WITH_VALUE = {"--config"}

# Retired subcommands are rejected explicitly so an upgrade cannot silently
# reinterpret them as file paths and exit 0.
_RETIRED_SUBCOMMANDS = {
    "trace": "sequence diagram generation is out of scope for this tool",
}


## @brief Create argparse parser with validate/impact/coverage subcommands.
#  @version 1.4
#  @dg_internal
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="clew guard",
        description="Validate doxygen comments for presence, version staleness, and custom tags",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to .doxygen-guard.yaml (default: .doxygen-guard.yaml in cwd)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable verbose output")

    subparsers = parser.add_subparsers(dest="command")
    _add_validate_parser(subparsers)
    _add_impact_parser(subparsers)
    _add_coverage_parser(subparsers)
    _add_config_parser(subparsers)
    _add_files_parser(subparsers)
    _add_doxyfile_parser(subparsers)
    return parser


## @brief Add the validate subcommand to the parser.
#  @version 1.1
#  @dg_internal
def _add_validate_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("validate", help="Validate doxygen comments (pre-commit gate)")
    p.add_argument("files", nargs="*", help="Files to validate (passed by pre-commit)")
    p.add_argument("--no-git", action="store_true", help="Skip git-based staleness checks")
    p.add_argument("--exclude", action="append", default=[], help="Exclude patterns (repeatable)")


## @brief Add the impact subcommand to the parser.
#  @version 1.1
#  @dg_internal
def _add_impact_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("impact", help="Change-impact analysis from git diff")
    group = p.add_mutually_exclusive_group()
    group.add_argument("--staged", action="store_true", help="Analyze staged changes")
    group.add_argument("--range", dest="diff_range", help="Git revision range (e.g., HEAD~3..HEAD)")
    p.add_argument("files", nargs="*", help="Files to analyze")


## @brief Add the coverage subcommand to the parser.
#  @version 1.0
#  @dg_internal
def _add_coverage_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("coverage", help="Report requirement coverage gaps")
    p.add_argument("source_dirs", nargs="*", default=["."], help="Source directories to scan")
    p.add_argument(
        "--format", dest="output_format", default="text", choices=["text", "json", "markdown"]
    )


## @brief Add the config subcommand exposing the machine-readable consumer contract.
#  @version 1.0
#  @dg_internal
def _add_config_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("config", help="Emit the consumer contract as JSON")
    group = p.add_mutually_exclusive_group()
    group.add_argument(
        "--schema",
        action="store_true",
        help="Emit the config schema, defaults and catalog constants",
    )
    group.add_argument(
        "--effective",
        action="store_true",
        help="Emit the merged config actually in force and what it resolved to",
    )


## @brief Add the doxyfile subcommand emitting a Doxyfile fragment.
#  @version 1.0
#  @dg_internal
def _add_doxyfile_parser(subparsers: argparse._SubParsersAction) -> None:
    subparsers.add_parser(
        "doxyfile",
        help="Emit Doxyfile settings that make this tool's tags valid doxygen",
    )


## @brief Add the files subcommand exposing the exact post-exclude file set.
#  @version 1.0
#  @dg_internal
def _add_files_parser(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("files", help="Emit the file set the gate walks, as JSON")
    p.add_argument("source_dirs", nargs="*", default=["."], help="Source directories to scan")


## @brief Orchestrate presence, staleness, and tag checks for one file.
#  @version 1.11
#  @req REQ-DDB-GUARD-001
def validate_file(
    file_path: str,
    config: dict[str, Any],
    no_git: bool = False,
    req_ids: set[str] | None = None,
) -> list[Violation]:
    validate = get_validate(config)
    for pattern in validate.get("exclude", []):
        if re.search(pattern, file_path):
            logger.debug("Skipping %s — matches exclude pattern '%s'", file_path, pattern)
            return []

    functions = parse_source_file(file_path, config)
    if functions is None:
        logger.debug("Skipping %s — no matching language config", file_path)
        return []

    violations: list[Violation] = []
    content: str | None = None
    try:
        content = Path(file_path).read_text(errors="replace")
        violations.extend(check_file_presence(file_path, content, config))
    except OSError:
        pass
    violations.extend(check_presence(functions, file_path, config, content))
    if content is not None:
        violations.extend(check_return_presence(functions, file_path, config, content))
    violations.extend(check_tags(functions, file_path, config))
    violations.extend(check_req_coverage(functions, file_path, config))
    for func in functions:
        violations.extend(check_unknown_tags(func, file_path, config))
        violations.extend(check_duplicate_tags(func, file_path, config))
        violations.extend(check_req_exists(func, file_path, config, req_ids))

    if not no_git and content is not None:
        head_content = get_file_at_revision(file_path)
        head_functions = (
            parse_content_for_file(file_path, head_content, config)
            if head_content is not None
            else None
        )
        violations.extend(
            check_version_staleness(
                functions, file_path, config, content, head_functions, head_content
            )
        )

    return violations


## @brief Validate a list of files and report violations.
#  @version 1.2
#  @dg_internal
def _validate_files(
    file_paths: list[str],
    config: dict[str, Any],
    no_git: bool = False,
) -> list[Violation]:
    from .impact import load_requirements_full

    req_ids = set(load_requirements_full(config).keys()) or None
    violations: list[Violation] = []
    for file_path in file_paths:
        if not Path(file_path).exists():
            logger.warning("File not found: %s", file_path)
            continue
        violations.extend(validate_file(file_path, config, no_git=no_git, req_ids=req_ids))
    return violations


## @brief Print violations to stderr and return exit code.
#  @version 1.0
#  @dg_internal
def _report_violations(violations: list[Violation]) -> int:
    for v in violations:
        print(v, file=sys.stderr)
    if violations:
        print(f"\nclew guard: {len(violations)} violation(s) found", file=sys.stderr)
        return 1
    return 0


## @brief Run validation checks on all specified files and report violations.
#  @version 1.4
#  @req REQ-DDB-GUARD-001
#  @return Exit code: 0 if no violations, 1 if violations found
def run_validate(args: argparse.Namespace, config: dict[str, Any]) -> int:
    files = args.files or []
    if not files:
        logger.warning("No files specified for validation")
        return 0
    # Resolve here too: this path previously skipped resolution entirely, so the
    # documented `doxygen-guard validate` invocation ran with no @req coverage gate.
    resolve_version_gate(config)
    cli_excludes = getattr(args, "exclude", [])
    if cli_excludes:
        validate = config.setdefault("validate", {})
        existing = validate.get("exclude", [])
        validate["exclude"] = existing + cli_excludes
    return _report_violations(_validate_files(files, config, no_git=args.no_git))


## @brief Detect version from git describe --tags.
#  @version 1.2
#  @dg_internal
def _detect_git_version() -> str | None:
    try:
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            check=True,
            timeout=10,
        )
        return result.stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        logger.warning("Could not detect version from git tags")
        return None


## @brief Detect version from CMakeLists.txt project() directive.
#  @version 1.1
#  @dg_internal
def _detect_cmake_version() -> str | None:
    try:
        cmake = Path("CMakeLists.txt").read_text()
        match = re.search(r"project\s*\([^)]*VERSION\s+([\d.]+)", cmake)
        return f"v{match.group(1)}" if match else None
    except (OSError, re.error):
        logger.warning("Could not detect version from CMakeLists.txt")
        return None


## @brief Resolve the current project version from config, git tag, or CMake.
#  @version 1.3
#  @dg_internal
def _detect_current_version(config: dict[str, Any]) -> str | None:
    gate = get_validate(config).get("version_gate", {})
    version_str = gate.get("current_version")
    if not version_str:
        return None
    detectors = {"auto:git": _detect_git_version, "auto:cmake": _detect_cmake_version}
    detector = detectors.get(version_str)
    return detector() if detector else version_str


## @brief Resolve the version gate in place, failing if it is declared but unresolvable.
#  @version 1.0
#  @req REQ-DDB-GUARD-014
def resolve_version_gate(config: dict[str, Any]) -> None:
    gate = get_validate(config).get("version_gate", {})
    declared = gate.get("current_version")
    if not declared:
        logger.info("No version gate declared; all catalogued requirements are active")
        return

    resolved = _detect_current_version(config)
    if not resolved:
        # Previously this just skipped, leaving current_version as the literal
        # "auto:git". parse_version then failed, every requirement filtered out as
        # not-yet-active, and the @req coverage gate silently disabled itself while
        # reporting success — worst on shallow CI clones with no tags.
        logger.error("Version gate %r declared but could not be resolved", declared)
        raise ConfigError(
            f"validate.version_gate.current_version is {declared!r} but no version "
            f"could be resolved. On a shallow or tagless clone, fetch tags "
            f"(git fetch --tags) or set a literal version."
        )

    logger.info("Version gate resolved: %s -> %s", declared, resolved)
    config.setdefault("validate", {}).setdefault("version_gate", {})["_resolved"] = resolved


## @brief Run all configured checks in pre-commit mode (no subcommand).
#  @version 2.5
#  @req REQ-DDB-GUARD-001
#  @return Exit code: 0 if no violations, 1 if violations found
def run_precommit(file_paths: list[str], config: dict[str, Any]) -> int:
    logger.info("Pre-commit mode: %d file(s)", len(file_paths))
    logger.info("Config: output_dir=%s", config.get("output_dir", "docs/generated/"))

    resolve_version_gate(config)

    rc = _report_violations(_validate_files(file_paths, config))

    base_dir = config.get("output_dir", "docs/generated/")
    validate_output_path(base_dir)

    impact_config = get_impact(config)
    if impact_config.get("requirements"):
        diff_range = get_branch_diff_range()
        if diff_range:
            changed = collect_changed_functions(file_paths, config, diff_range=diff_range)
        else:
            changed = collect_changed_functions(file_paths, config, staged=True)
        entries = build_impact_report(changed, config)
        impact_dir = Path(base_dir) / "impact"
        impact_dir.mkdir(parents=True, exist_ok=True)
        md_path = impact_dir / "impact.md"
        json_path = impact_dir / "impact.json"
        md_path.write_text(format_markdown(entries))
        json_path.write_text(format_json(entries))
        git_add([str(md_path), str(json_path)])
        print(format_markdown(entries), file=sys.stderr)

    return rc


_HELP_FLAGS = frozenset(("-h", "--help"))


## @brief Detect whether the first positional arg is a known subcommand.
#  @version 1.1
#  @dg_internal
def _has_subcommand(raw_argv: list[str]) -> bool:
    return _first_positional(raw_argv) in _SUBCOMMANDS


## @brief Return the first positional arg, ignoring flags and their values.
#  @version 1.0
#  @dg_internal
#  @return The first positional argument, or None if the argv is all flags
def _first_positional(raw_argv: list[str]) -> str | None:
    skip_next = False
    for arg in raw_argv:
        if skip_next:
            skip_next = False
            continue
        if arg in _FLAGS_WITH_VALUE:
            skip_next = True
            continue
        if arg.startswith("-"):
            continue
        return arg
    return None


## @brief Reject retired subcommands loudly instead of treating them as file paths.
#  @version 1.0
#  @req REQ-DDB-GUARD-013
#  @return Exit code 1 if a retired subcommand was invoked, else None
def _check_retired_subcommand(raw_argv: list[str]) -> int | None:
    first = _first_positional(raw_argv)
    reason = _RETIRED_SUBCOMMANDS.get(first) if first else None
    if reason is None:
        return None
    logger.error("Retired subcommand invoked: %s", first)
    print(f"clew guard: the '{first}' subcommand was removed — {reason}", file=sys.stderr)
    return 1


## @brief Parse pre-commit mode args (no subcommand) into components.
#  @version 1.0
#  @dg_internal
def _parse_precommit_args(
    raw_argv: list[str],
) -> tuple[Path | None, list[str], bool]:
    config_path = None
    file_paths: list[str] = []
    verbose = False
    i = 0
    while i < len(raw_argv):
        if raw_argv[i] == "--config" and i + 1 < len(raw_argv):
            config_path = Path(raw_argv[i + 1])
            i += 2
        elif raw_argv[i] in ("-v", "--verbose"):
            verbose = True
            i += 1
        elif raw_argv[i].startswith("-"):
            i += 1
        else:
            file_paths.append(raw_argv[i])
            i += 1
    return config_path, file_paths, verbose


## @brief Execute the impact subcommand.
#  @version 1.4
#  @req REQ-DDB-GUARD-010
#  @return Exit code: 0 on success, 1 if output path is invalid
def _run_impact_command(args: argparse.Namespace, config: dict[str, Any]) -> int:
    file_paths = args.files or []
    report = run_impact(
        file_paths=file_paths,
        config=config,
        staged=args.staged,
        diff_range=args.diff_range,
    )
    output_file = get_impact(config).get("output", {}).get("file")
    if output_file:
        validate_output_path(output_file)
        out_path = Path(output_file).resolve()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report)
        print(f"Wrote report: {out_path}")
    else:
        print(report)
    return 0


## @brief Configure logging based on verbosity flag.
#  @version 1.0
#  @dg_internal
def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")


## @brief Run the coverage subcommand.
#  @version 1.1
#  @dg_internal
def _run_coverage_command(args: argparse.Namespace, config: dict[str, Any]) -> int:
    from .coverage import run_coverage

    return run_coverage(args.source_dirs, config, args.output_format)


## @brief Emit the consumer contract as JSON.
#  @version 1.0
#  @req REQ-DDB-GUARD-015
#  @return Exit code 0
def _run_config_command(args: argparse.Namespace, config: dict[str, Any]) -> int:
    from .contract import (
        build_effective_contract,
        build_schema_contract,
        render,
    )

    payload = build_schema_contract() if args.schema else build_effective_contract(config)
    print(render(payload))
    return 0


## @brief Emit the exact post-exclude file set the gate walks, as JSON.
#  @version 1.0
#  @req REQ-DDB-GUARD-015
#  @return Exit code 0
def _run_files_command(args: argparse.Namespace, config: dict[str, Any]) -> int:
    from .contract import build_files_contract, render

    print(render(build_files_contract(args.source_dirs, config)))
    return 0


## @brief Emit the Doxyfile fragment for the current config.
#  @version 1.0
#  @req REQ-DDB-GUARD-017
#  @return Exit code 0
def _run_doxyfile_command(_args: argparse.Namespace, config: dict[str, Any]) -> int:
    from .doxyfile import build_fragment

    print(build_fragment(config), end="")
    return 0


## @brief Dispatch an explicit subcommand to its handler.
#  @version 1.3
#  @dg_internal
def _dispatch_subcommand(args: argparse.Namespace, config: dict[str, Any]) -> int:
    handlers = {
        "validate": lambda: run_validate(args, config),
        "impact": lambda: _run_impact_command(args, config),
        "coverage": lambda: _run_coverage_command(args, config),
        "config": lambda: _run_config_command(args, config),
        "files": lambda: _run_files_command(args, config),
        "doxyfile": lambda: _run_doxyfile_command(args, config),
    }
    handler = handlers.get(args.command)
    if handler:
        return handler()
    return 1


## @brief Parse arguments and dispatch to the appropriate subcommand.
#  @version 2.0
#  @dg_internal
def main(argv: list[str] | None = None) -> int:
    raw_argv = list(argv if argv is not None else sys.argv[1:])

    retired = _check_retired_subcommand(raw_argv)
    if retired is not None:
        return retired

    try:
        return _run(raw_argv)
    except GuardError as e:
        print(f"clew guard: {e.details()}", file=sys.stderr)
        return 1


## @brief Load config and dispatch, letting GuardError propagate to the CLI boundary.
#  @details `--help` without a subcommand used to fall into pre-commit mode, which skips
#  unknown flags: asking for help ran the gate over nothing and wrote an impact report.
#  @version 1.1
#  @dg_internal
def _run(raw_argv: list[str]) -> int:
    if not _has_subcommand(raw_argv) and _HELP_FLAGS.intersection(raw_argv):
        build_parser().print_help()
        return 0
    if not _has_subcommand(raw_argv):
        config_path, file_paths, verbose = _parse_precommit_args(raw_argv)
        _setup_logging(verbose)
        return run_precommit(file_paths, load_config(config_path))

    parser = build_parser()
    args = parser.parse_args(raw_argv)
    _setup_logging(args.verbose)
    return _dispatch_subcommand(args, load_config(args.config))


## @brief Wrapper for setuptools console_scripts entry point.
#  @version 1.0
#  @dg_internal
def cli_main() -> None:
    sys.exit(main())


if __name__ == "__main__":
    cli_main()
