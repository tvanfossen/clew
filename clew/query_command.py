# SPDX-License-Identifier: MIT
"""`clew query` — the stable export API as a command that prints JSON.

1.3.2, Track 1. `clew.query.export_dossier` / `export_search` are the MCP replies without the MCP
boundary, for a Python caller. A host that is not Python — a C++ editor front end, a build step —
needs the same answer across a process boundary, so this verb prints exactly what those functions
return, as JSON on stdout, and nothing else. It adds no wording of its own to any answer.

    clew query dossier NAME [NAME ...] [--index DB | --repo-root DIR] [--kind K] [--qualified Q]
                        [--depth N] [--direction forward|back] [--max-body-lines N]
                        [--max-neighbors N]
    clew query search [TEXT] [--corpus C] [--limit N] [--index DB | --repo-root DIR]

WHICH INDEX. `--index` names a database; otherwise the index for `--repo-root` (default: the
working directory) is found where the MCP server and a plain `clew` build put it, through the same
`target_for` rule — never a second copy of it. Bodies and code snippets are read from the working
tree named by `--repo-root`; with `--index` alone and no `--repo-root`, every index-only panel is
still served.

EXIT CODES ARE PART OF THE CONTRACT: 0 with a payload on stdout; 1 when there is no index — stdout
stays EMPTY, because an empty-looking payload would read as "nothing here" when nothing was
looked at; 2 when the library refused the request (an unknown corpus, a batch over the cap,
`--qualified` with several subjects), the library's own reason on stderr.

A long-lived host should keep one `clew-mcp` process instead (MCP is JSON-RPC 2.0 over stdio, and
its wire keys are semver-covered): this verb pays an interpreter start per call.

@brief The `clew query` subcommand: export payloads as JSON on stdout.
@version 1
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

## The command word `cli.main()` dispatches on.
QUERY_COMMAND = "query"


## @brief The argument parser for `clew query`.
## @return The parser.
## @version 1
## @dg_internal
def _parser() -> argparse.ArgumentParser:
    """@brief Build the parser. @return Parser with `dossier` and `search` subcommands."""
    from .query import DEFAULT_BODY_LINES, EXPORT_CORPORA

    parser = argparse.ArgumentParser(
        prog=f"clew {QUERY_COMMAND}",
        description="Print a dossier or search reply from a clew index as JSON.",
    )
    sub = parser.add_subparsers(dest="verb", required=True)
    dossier = sub.add_parser("dossier", help="everything the index holds about named subjects")
    dossier.add_argument("subjects", nargs="+", help="one name or path; several = one batch")
    dossier.add_argument("--kind")
    dossier.add_argument("--qualified")
    dossier.add_argument("--depth", type=int, default=1)
    dossier.add_argument("--direction", default="forward")
    dossier.add_argument("--max-body-lines", type=int, default=DEFAULT_BODY_LINES)
    dossier.add_argument("--max-neighbors", type=int, default=8)
    search = sub.add_parser("search", help="search or enumerate one corpus")
    search.add_argument("text", nargs="?", default="")
    search.add_argument("--corpus", default="symbols", help=", ".join(EXPORT_CORPORA))
    search.add_argument("--limit", type=int, default=25)
    for each in (dossier, search):
        each.add_argument("--index", help="path to a built clew.db")
        each.add_argument("--repo-root", help="working tree (default: the current directory)")
        each.add_argument("--indent", type=int, default=None, help="pretty-print JSON")
    return parser


## @brief Resolve which database answers and which working tree bodies come from.
## @param args Parsed arguments.
## @return (database path, working tree or None).
## @version 1
## @dg_internal
def _locate(args: argparse.Namespace) -> tuple[Path, Path | None]:
    """DERIVED THROUGH `target_for`, NEVER REIMPLEMENTED, as `cli._resolve_output` does for a
    build — so `clew query` reads exactly where a build wrote. Imported here because `mcp_server`
    is a view over the pipeline and must not be on this module's import path otherwise.

    @brief Resolve the index and the tree.
    @return The pair.
    @version 1
    """
    repo = Path(args.repo_root).expanduser().resolve() if args.repo_root else None
    if args.index:
        return Path(args.index).expanduser().resolve(), repo
    from .mcp_server.state import target_for

    tree = repo or Path.cwd().resolve()
    return Path(target_for(tree).db_path), tree


## @brief Build the payload the parsed request asks for.
## @param args Parsed arguments.
## @param db The index.
## @param repo The working tree, or None.
## @return The export payload.
## @version 1
## @dg_internal
def _payload(args: argparse.Namespace, db: Path, repo: Path | None) -> dict[str, Any]:
    """@brief Dispatch to the export function. @return The payload."""
    from . import query as q

    if args.verb == "search":
        return q.export_search(db, args.text, corpus=args.corpus, limit=args.limit, repo_root=repo)
    subject: str | list[str] = args.subjects[0] if len(args.subjects) == 1 else args.subjects
    return q.export_dossier(
        db,
        subject,
        kind=args.kind,
        qualified=args.qualified,
        repo_root=repo,
        max_body_lines=args.max_body_lines,
        depth=args.depth,
        direction=args.direction,
        max_neighbors=args.max_neighbors,
    )


## @brief Parse arguments, answer, and print JSON.
## @param argv Arguments after `clew query`.
## @return Exit status: 0 answered, 1 no index, 2 refused.
## @version 1
## @req REQ-DDB-QUERY-014
def query_main(argv: list[str]) -> int:
    """NOTHING ON STDOUT UNLESS IT IS THE ANSWER, so a host can parse stdout without filtering.

    @brief Entry point for `clew query`.
    @return Exit status.
    @version 1
    """
    args = _parser().parse_args(argv)
    db, repo = _locate(args)
    if not db.is_file():
        sys.stderr.write(f"clew query: no index at {db} — build one with `clew --repo-root`\n")
        return 1
    try:
        payload = _payload(args, db, repo)
    except ValueError as exc:
        sys.stderr.write(f"clew query: refused — {exc}\n")
        return 2
    sys.stdout.write(json.dumps(payload, indent=args.indent) + "\n")
    return 0
