# SPDX-License-Identifier: MIT
"""`clew wiki` — the documentation subcommand.

    clew wiki flow ENTRY [--qualified Q] [--depth N] [--lanes files|packages|threads]
                         [--stop-at NAME ...] [--index DB | --repo-root DIR]

`flow` prints the derived sequence flow (clew.wiki.flow) as JSON on stdout, stamped with
`flow_version`. Exit codes follow `clew query`: 0 printed, 1 no index (stdout empty), 2 refused
(unknown entry or lane strategy; the reason on stderr).

@brief The `clew wiki` subcommand.
@version 1
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

## The command word `cli.main()` dispatches on.
WIKI_COMMAND = "wiki"


## @brief The argument parser for `clew wiki`.
## @return The parser.
## @version 1
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
    return parser


## @brief Entry point for `clew wiki`.
## @param argv Arguments after `clew wiki`.
## @return Exit status.
## @version 1
## @req REQ-DDB-WIKI-001
def wiki_main(argv: list[str]) -> int:
    """@brief Dispatch a wiki verb. @return Exit status."""
    from ..query_command import _locate
    from .flow import derive_flow

    args = _parser().parse_args(argv)
    db, repo = _locate(args)
    if not db.is_file():
        sys.stderr.write(f"clew wiki: no index at {db} — build one with `clew --repo-root`\n")
        return 1
    try:
        flow = derive_flow(
            db,
            repo or db.parent,
            args.entry,
            qualified=args.qualified,
            depth=args.depth,
            lanes=args.lanes,
            stop_at=tuple(args.stop_at),
        )
    except ValueError as exc:
        sys.stderr.write(f"clew wiki: refused — {exc}\n")
        return 2
    sys.stdout.write(json.dumps(dataclasses.asdict(flow), indent=args.indent) + "\n")
    return 0
