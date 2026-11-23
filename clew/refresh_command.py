# SPDX-License-Identifier: MIT
"""`clew refresh` — bring an index current after an edit: fast in place when it can, full when not.

1.3.5, Track 2 (two-tier refresh; owner 2026-11-13: a new verb, so the build's six arguments stay
as `tests/test_cli_surface.py` pins them). An editor saving a file runs this. It tries
`clew.fasttier.try_fast_refresh` — the edited files' own layers updated in place, the whole-index
layers disclosed stale — and when the fast tier refuses (a changed set of definitions, a
configuration input, too many files, no previous build) it runs the ordinary full build.

    clew refresh [--repo-root DIR] [--output DB]

The index is found exactly where a plain `clew` build writes it (`target_for`), unless named.
Exit 0 either way; the log says which tier ran and why.

@brief The `clew refresh` subcommand.
@version 1
"""

from __future__ import annotations

import argparse
from pathlib import Path

from ._common import logger

## The command word `cli.main()` dispatches on.
REFRESH_COMMAND = "refresh"


## @brief Refresh an index, fast tier first.
## @param argv Arguments after `clew refresh`.
## @return Exit status.
## @version 1
## @req REQ-DDB-INDEX-006
def refresh_main(argv: list[str]) -> int:
    """THE FALLBACK IS THE ORDINARY BUILD, through the same `_run_pipeline` a plain `clew` runs,
    so a refused fast tier produces exactly the index a full build would — and that build drops
    any pending `fast.*` record, because it writes a fresh database.

    @brief Entry point for `clew refresh`.
    @return 0.
    @version 1
    """
    from .cli import _build_argparser, _run_pipeline
    from .fasttier import try_fast_refresh

    parser = argparse.ArgumentParser(
        prog=f"clew {REFRESH_COMMAND}",
        description="Refresh an index after an edit: in place when possible, else a full build.",
    )
    parser.add_argument("--repo-root", help="working tree (default: the current directory)")
    parser.add_argument("--output", help="index path (default: where a plain build writes it)")
    args = parser.parse_args(argv)
    repo = Path(args.repo_root).expanduser().resolve() if args.repo_root else Path.cwd().resolve()
    if args.output:
        output = Path(args.output).expanduser().resolve()
    else:
        from .mcp_server.state import target_for

        output = Path(target_for(repo).db_path)
    if try_fast_refresh(output, repo, output.with_name(output.name + ".idxcache")) is None:
        logger.info("refresh: running a full build")
        _run_pipeline(
            _build_argparser().parse_args(["--output", str(output), "--repo-root", str(repo)])
        )
    return 0
