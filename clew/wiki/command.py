# SPDX-License-Identifier: MIT
"""`clew wiki` — the documentation subcommand.

    clew wiki flow ENTRY [--qualified Q] [--depth N] [--lanes files|packages|threads]
                         [--stop-at NAME ...] [--index DB | --repo-root DIR]

    clew wiki trace [--junit X.xml ...] [--coverage cov.xml] [--target-only GLOB ...]
    clew wiki check                      # validate the `wiki:` section; no Sphinx import
    clew wiki build --out DIR [--audience NAME]   # render the site (needs clew-trace[wiki])

`flow` prints the derived sequence flow (clew.wiki.flow) as JSON on stdout, stamped with
`flow_version`; `trace` prints every requirement's evidence tier (clew.wiki.evidence), stamped
`trace_version`. Exit codes follow `clew query`: 0 printed, 1 no index (stdout empty), 2 refused
(unknown entry or lane strategy; the reason on stderr).

@brief The `clew wiki` subcommand.
@version 3
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
## @version 3
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
    trace = sub.add_parser("trace", help="requirement evidence from JUnit and Cobertura, as JSON")
    trace.add_argument("--junit", nargs="*", default=[], help="JUnit XML report(s)")
    trace.add_argument("--coverage", help="a Cobertura XML report")
    trace.add_argument(
        "--target-only", nargs="*", default=[], help="test-name globs needing hardware"
    )
    trace.add_argument("--index")
    trace.add_argument("--repo-root")
    trace.add_argument("--indent", type=int, default=None)
    check = sub.add_parser("check", help="validate the wiki: section against the index (no Sphinx)")
    check.add_argument("--index")
    check.add_argument("--repo-root")
    build = sub.add_parser("build", help="render the site (needs clew-trace[wiki])")
    build.add_argument("--out", required=True, help="output directory; the site is <out>/html")
    build.add_argument("--audience", help="an audience from wiki.audiences")
    build.add_argument("--index")
    build.add_argument("--repo-root")
    return parser


## @brief Entry point for `clew wiki`.
## @param argv Arguments after `clew wiki`.
## @return Exit status.
## v2: dispatches `trace` too.
## v3: and `check` / `build`.
## @version 3
## @req REQ-DDB-WIKI-001
def wiki_main(argv: list[str]) -> int:
    """@brief Dispatch a wiki verb. @return Exit status."""
    from ..query_command import _locate

    args = _parser().parse_args(argv)
    db, repo = _locate(args)
    if not db.is_file():
        sys.stderr.write(f"clew wiki: no index at {db} — build one with `clew --repo-root`\n")
        return 1
    if args.verb in ("check", "build"):
        return _site(args, db, repo or Path.cwd())
    try:
        payload = _flow(args, db, repo) if args.verb == "flow" else _trace(args, db)
    except (ValueError, OSError) as exc:
        sys.stderr.write(f"clew wiki: refused — {exc}\n")
        return 2
    sys.stdout.write(json.dumps(payload, indent=args.indent) + "\n")
    return 0


## @brief The `flow` verb's payload.
## @param args Parsed arguments.
## @param db The index.
## @param repo The working tree, or None.
## @return The flow as plain data.
## @version 1
## @dg_internal
def _flow(args: argparse.Namespace, db: Path, repo: Path | None) -> dict[str, Any]:
    """@brief Derive the flow. @return Plain data."""
    from .flow import derive_flow

    flow = derive_flow(
        db,
        repo or db.parent,
        args.entry,
        qualified=args.qualified,
        depth=args.depth,
        lanes=args.lanes,
        stop_at=tuple(args.stop_at),
    )
    return dataclasses.asdict(flow)


## @brief The `trace` verb's payload.
## @param args Parsed arguments.
## @param db The index.
## @return Evidence rows as plain data, stamped `trace_version`.
## @version 1
## @dg_internal
def _trace(args: argparse.Namespace, db: Path) -> dict[str, Any]:
    """@brief Grade the requirements. @return Plain data."""
    from .evidence import requirement_evidence

    rows = requirement_evidence(
        db,
        junit=[Path(p) for p in args.junit],
        coverage=Path(args.coverage) if args.coverage else None,
        target_only=tuple(args.target_only),
    )
    return {"trace_version": 1, "requirements": [dataclasses.asdict(r) for r in rows]}


## @brief The `check` and `build` verbs.
## @param args Parsed arguments.
## @param db The index.
## @param repo The repository.
## @return Exit status: 0 clean / built, 1 problems found, 2 refused.
## @version 1
## @dg_internal
def _site(args: argparse.Namespace, db: Path, repo: Path) -> int:
    """`check` PRINTS EVERY PROBLEM, one per line on stdout, and exits 1 when there is any — the
    shape a pre-commit hook wants. `build` prints the site's path.

    @brief Check or build the site.
    @return Exit status.
    @version 1
    """
    if args.verb == "check":
        from .check import check_wiki

        problems = check_wiki(repo, db)
        for problem in problems:
            sys.stdout.write(f"{problem}\n")
        return 1 if problems else 0
    from .build import build_wiki

    try:
        site = build_wiki(repo, db, Path(args.out), audience=args.audience)
    except ValueError as exc:
        sys.stderr.write(f"clew wiki: refused — {exc}\n")
        return 2
    sys.stdout.write(f"{site}\n")
    return 0
