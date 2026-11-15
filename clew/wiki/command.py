# SPDX-License-Identifier: MIT
"""`clew wiki` — the documentation subcommand.

    clew wiki flow ENTRY [--qualified Q] [--depth N] [--lanes files|packages|threads]
                         [--stop-at NAME ...] [--index DB | --repo-root DIR]

    clew wiki trace [--junit X.xml ...] [--coverage cov.xml] [--target-only GLOB ...]
    clew wiki trace ... [--mutations M.yaml]
    clew wiki check [--config FILE]      # validate the `wiki:` section; no Sphinx import
    clew wiki build --out DIR [--audience NAME] [--version KEY] [--config FILE]
    clew wiki diff --out DIR FROM TO     # compare two version-keyed builds

`--config FILE` reads that file's `wiki:` section instead of `<repo>/.clew.yaml`, so a repository
can be documented without writing into it. `--version KEY` writes `<out>/<KEY>/` and lists it in
`<out>/index.html`; `diff` prints the changes between two keys as JSON and writes
`<out>/diff-FROM-TO.html`.

`flow` prints the derived sequence flow (clew.wiki.flow) as JSON on stdout, stamped with
`flow_version`; `trace` prints every requirement's evidence tier (clew.wiki.evidence), stamped
`trace_version`. Exit codes follow `clew query`: 0 printed, 1 no index (stdout empty), 2 refused
(unknown entry or lane strategy; the reason on stderr).

@brief The `clew wiki` subcommand.
@version 4
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

## The command word `cli.main()` dispatches on.
WIKI_COMMAND = "wiki"


## @brief The argument parser for `clew wiki`.
## @return The parser.
## v2: the `trace` verb.
## v3: `check` and `build`.
## v4: `diff`, `--version`, `--config`, `--mutations`, `flow --svg --animate`.
## v5: `trace --config` (W15/W16 imports).
## v6: `check --refresh` / `build --refresh` (the pre-commit hook has no index yet).
## @version 6
## @dg_internal
def _parser() -> argparse.ArgumentParser:
    """@brief Build the parser. @return Parser."""
    from .flow import LANES

    parser = argparse.ArgumentParser(prog=f"clew {WIKI_COMMAND}")
    sub = parser.add_subparsers(dest="verb", required=True)
    flow = sub.add_parser("flow", help="a sequence flow derived from the index, as JSON")
    flow.add_argument("entry")
    flow.add_argument("--qualified")
    flow.add_argument("--depth", type=int, default=3)
    flow.add_argument("--lanes", default="files", help=", ".join(LANES))
    flow.add_argument("--stop-at", nargs="*", default=[])
    flow.add_argument("--index")
    flow.add_argument("--repo-root")
    flow.add_argument("--indent", type=int, default=None)
    flow.add_argument("--svg", action="store_true", help="print the SVG diagram, not JSON")
    flow.add_argument("--animate", action="store_true", help="with --svg: play the steps in order")
    trace = sub.add_parser("trace", help="requirement evidence from JUnit and Cobertura, as JSON")
    trace.add_argument("--junit", nargs="*", default=[], help="JUnit XML report(s)")
    trace.add_argument("--coverage", help="a Cobertura XML report")
    trace.add_argument(
        "--target-only", nargs="*", default=[], help="test-name globs needing hardware"
    )
    trace.add_argument("--mutations", help="a mutation record: [{mechanism, test, killed}]")
    trace.add_argument("--config", help="a file whose wiki.tests imports (W15/W16) apply")
    trace.add_argument("--index")
    trace.add_argument("--repo-root")
    trace.add_argument("--indent", type=int, default=None)
    check = sub.add_parser("check", help="validate the wiki: section against the index (no Sphinx)")
    check.add_argument("--index")
    check.add_argument("--repo-root")
    check.add_argument("--config", help="a file whose wiki: section applies")
    check.add_argument("--refresh", action="store_true", help="bring the index current first")
    build = sub.add_parser("build", help="render the site (needs clew-trace[wiki])")
    build.add_argument("--out", required=True, help="output directory; the site is <out>/html")
    build.add_argument("--audience", help="an audience from wiki.audiences")
    build.add_argument("--version", help="a version key: the site goes to <out>/<key>/")
    build.add_argument("--config", help="a file whose wiki: section applies")
    build.add_argument("--refresh", action="store_true", help="bring the index current first")
    build.add_argument("--index")
    build.add_argument("--repo-root")
    diff = sub.add_parser("diff", help="compare two version-keyed builds")
    diff.add_argument("--out", required=True, help="the versioned output root")
    diff.add_argument("old")
    diff.add_argument("new")
    diff.add_argument("--indent", type=int, default=None)
    return parser


## @brief Entry point for `clew wiki`.
## @param argv Arguments after `clew wiki`.
## @return Exit status.
## v2: dispatches `trace` too.
## v3: and `check` / `build`.
## v4: and `diff`, which needs no index.
## v5: `trace` gets the repository (for `--config` imports).
## v6: `--refresh` refreshes the index before `check` / `build`.
## @version 6
## @req REQ-DDB-WIKI-001
def wiki_main(argv: list[str]) -> int:
    """@brief Dispatch a wiki verb. @return Exit status."""
    from ..query_command import _locate

    args = _parser().parse_args(argv)
    if args.verb == "diff":
        return _diff(args)
    db, repo = _locate(args)
    if getattr(args, "refresh", False):
        from ..refresh_command import refresh_main

        refresh_main(["--repo-root", str(repo or Path.cwd()), "--output", str(db)])
    if not db.is_file():
        sys.stderr.write(f"clew wiki: no index at {db} — build one with `clew --repo-root`\n")
        return 1
    if args.verb in ("check", "build"):
        return _site(args, db, repo or Path.cwd())
    try:
        text = _flow(args, db, repo) if args.verb == "flow" else _json(_trace(args, db, repo), args)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"clew wiki: refused — {exc}\n")
        return 2
    sys.stdout.write(text + "\n")
    return 0


## @brief A payload as JSON text.
## @param payload Plain data.
## @param args Parsed arguments (for `--indent`).
## @return JSON text.
## @version 1
## @dg_internal
def _json(payload: dict[str, Any], args: argparse.Namespace) -> str:
    """@brief Serialise. @return Text."""
    return json.dumps(payload, indent=args.indent)


## @brief The `flow` verb's output: JSON, or the SVG diagram with `--svg`.
## @param args Parsed arguments.
## @param db The index.
## @param repo The working tree, or None.
## @return The text to print.
## v2: `--svg` / `--animate` (W12).
## @version 2
## @dg_internal
def _flow(args: argparse.Namespace, db: Path, repo: Path | None) -> str:
    """@brief Derive and render the flow. @return Text."""
    flow = _flow_object(args, db, repo)
    if args.svg:
        from .svg import flow_svg

        return flow_svg(flow, animate=args.animate)
    return _json(dataclasses.asdict(flow), args)


## @brief Derive the flow the arguments name.
## @param args Parsed arguments.
## @param db The index.
## @param repo The working tree, or None.
## @return The Flow.
## @version 1
## @dg_internal
def _flow_object(args: argparse.Namespace, db: Path, repo: Path | None) -> Any:
    """@brief Derive the flow. @return Flow."""
    from .flow import derive_flow

    return derive_flow(
        db,
        repo or db.parent,
        args.entry,
        qualified=args.qualified,
        depth=args.depth,
        lanes=args.lanes,
        stop_at=tuple(args.stop_at),
    )


## @brief The `trace` verb's payload.
## @param args Parsed arguments.
## @param db The index.
## @param repo The repository (the imports' paths are relative to it).
## @return Evidence rows as plain data, stamped `trace_version`.
## v2: `--mutations` (rows gain `mutations`, additive: trace_version stays 1).
## v3: `--config` applies the section's W15/W16 imports (rows gain `layers`, additive).
## @version 3
## @dg_internal
def _trace(args: argparse.Namespace, db: Path, repo: Path | None) -> dict[str, Any]:
    """THE IMPORTS COME FROM A `wiki:` SECTION, never from a flag per format, so the trace a CLI
    prints and the one a site shows read the same declaration.

    @brief Grade the requirements.
    @return Plain data.
    """
    from .config import EvidenceInputs, load_wiki_config
    from .evidence import requirement_evidence

    root = repo or Path.cwd()
    inputs = EvidenceInputs()
    if args.config:
        config, problems = load_wiki_config(root, Path(args.config))
        if problems:
            raise ValueError("wiki configuration problems: " + "; ".join(problems))
        inputs = config.inputs
    rows = requirement_evidence(
        db,
        junit=[Path(p) for p in args.junit],
        coverage=Path(args.coverage) if args.coverage else None,
        target_only=tuple(args.target_only),
        mutations=Path(args.mutations) if args.mutations else None,
        inputs=inputs,
        repo_root=root,
    )
    return {"trace_version": 1, "requirements": [dataclasses.asdict(r) for r in rows]}


## @brief The `check` and `build` verbs.
## @param args Parsed arguments.
## @param db The index.
## @param repo The repository.
## @return Exit status: 0 clean / built, 1 problems found, 2 refused.
## v2: `--config` and `--version`.
## @version 2
## @dg_internal
def _site(args: argparse.Namespace, db: Path, repo: Path) -> int:
    """`check` PRINTS EVERY PROBLEM, one per line on stdout, and exits 1 when there is any — the
    shape a pre-commit hook wants. `build` prints the site's path.

    @brief Check or build the site.
    @return Exit status.
    @version 2
    """
    config = Path(args.config) if args.config else None
    if args.verb == "check":
        from .check import check_wiki

        problems = check_wiki(repo, db, config)
        for problem in problems:
            sys.stdout.write(f"{problem}\n")
        return 1 if problems else 0
    from .build import build_wiki

    try:
        site = build_wiki(
            repo,
            db,
            Path(args.out),
            audience=args.audience,
            version=args.version,
            config_path=config,
        )
    except ValueError as exc:
        sys.stderr.write(f"clew wiki: refused — {exc}\n")
        return 2
    sys.stdout.write(f"{site}\n")
    return 0


## @brief The `diff` verb: compare two version-keyed builds.
## @param args Parsed arguments.
## @return Exit status: 0 printed, 2 refused (a key never recorded).
## @version 1
## @dg_internal
def _diff(args: argparse.Namespace) -> int:
    """@brief Diff two versions. @return Exit status."""
    from .versions import diff_versions

    try:
        diff = diff_versions(Path(args.out), args.old, args.new)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"clew wiki: refused — {exc}\n")
        return 2
    sys.stdout.write(json.dumps(diff, indent=args.indent) + "\n")
    return 0
