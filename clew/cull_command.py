# SPDX-License-Identifier: MIT
"""`clew cull` — sweep aged and version-stale index databases from the registry (2.0.0).

The MCP `index(action='cull')` retired in 2.0.0 (owner 2026-11-16): deleting databases is an
operator's act, not something a model should be offered on every turn. The sweep is the same
function (`mcp_server.state.cull`) over the same per-user registry, printed as JSON.

    clew cull [--max-age-days N] [--keep-stale]

@brief The `clew cull` subcommand.
@version 1
"""

from __future__ import annotations

import argparse
import json
import sys

CULL_COMMAND = "cull"


## @brief Parse arguments, sweep the registry, print what went.
## @param argv Arguments after `clew cull`.
## @return Exit status: 0 swept, 2 a refused argument.
## @version 1
## @req REQ-DDB-WIKI-034
def cull_main(argv: list[str]) -> int:
    """A NON-POSITIVE AGE IS REFUSED, as the MCP schema refused it (1.1.0 audit, M4): 0 would mean
    "older than zero days", which is every database.

    @brief Entry point for `clew cull`.
    @return Exit status.
    """
    from .mcp_server.state import TargetRegistry, cull

    parser = argparse.ArgumentParser(
        prog=f"clew {CULL_COMMAND}",
        description="Delete aged and version-stale index databases from the registry.",
    )
    parser.add_argument("--max-age-days", type=float, default=30.0, help="age threshold (> 0)")
    parser.add_argument("--keep-stale", action="store_true", help="keep version-stale databases")
    args = parser.parse_args(argv)
    if args.max_age_days <= 0:
        sys.stderr.write("clew cull: --max-age-days must be > 0\n")
        return 2
    registry = TargetRegistry()
    culled = cull(registry, max_age_days=args.max_age_days, include_stale=not args.keep_stale)
    out = {"culled": culled, "remaining": len(registry.targets())}
    sys.stdout.write(json.dumps(out, default=str) + "\n")
    return 0
