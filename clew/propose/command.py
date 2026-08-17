# SPDX-License-Identifier: MIT
"""`clew propose` — write a starter `.clew.yaml` draft for a repo.

Two behaviours here are safety properties rather than conveniences.

**STDOUT by default.** The draft is a proposal about a repo, and the repo's own
declaration is authoritative; a command that writes into the tree by default
turns "let me see what you would suggest" into an edit. (#53 was the same
mistake in the build path — output written into the target repo.)

**An existing file is never overwritten without `--force`.** The one file this
command is about is the one file it must not clobber: a hand-tuned declaration
represents an owner's measurements, and replacing it with an all-comments draft
would silently DISABLE every convention they had declared — a build that still
succeeds while answering differently, which is the worst available failure.

Logs go to stderr, always. The draft is stdout, so a log line on stdout would
land inside the YAML.

@brief CLI entry point for the declaration proposer.
@version 1
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys
from pathlib import Path

from ..declaration import DECLARATION_NAME
from .registry import propose

## The subcommand word `clew.cli` dispatches on.
COMMAND = "propose"

_EPILOG = (
    "The draft is ALL COMMENTS: written into a repo verbatim it changes nothing. "
    "Every proposed entry is printed under the evidence it came from and the "
    "measured delta it produced against a real index; every refused candidate is "
    "printed with the reason. Without a built index the dry-run-gated sections "
    "refuse to propose at all rather than guessing."
)


## @brief Build the `clew propose` argument parser.
## @return The configured parser.
## @version 4
## @req REQ-DDB-CONFIG-001
def build_parser() -> argparse.ArgumentParser:
    """@brief Construct the proposer's CLI parser."""
    parser = argparse.ArgumentParser(
        prog="clew propose",
        description="Propose a starter .clew.yaml for a repo, from evidence.",
        epilog=_EPILOG,
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repo to analyse (default: the current directory).",
    )
    parser.add_argument(
        "--db",
        help=(
            "Index to measure candidates against. Defaults to the registered "
            "database for this repo, then <repo-root>/clew.db. Without one, every "
            "dry-run-gated section refuses to propose."
        ),
    )
    parser.add_argument(
        "-o",
        "--output",
        help=(
            f"Write the draft here instead of stdout (typically <repo>/{DECLARATION_NAME}). "
            "An existing file is REFUSED unless --force is also given."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Overwrite the --output file if it exists. The repo's own declaration is "
            "authoritative, so this is never implied."
        ),
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help=(
            "Do not measure candidates against the index. FAIL-CLOSED: the gated "
            "sections then propose NOTHING, because an unmeasured shared-key "
            "declaration can mint a blob of fabricated causal edges."
        ),
    )
    parser.add_argument(
        "--ignore-declaration",
        action="store_true",
        help=(
            "Detect as if the repo declared nothing, so entries its .clew.yaml "
            "already covers are proposed again instead of being refused as covered. "
            "Use it to AUDIT an existing declaration against the evidence. The index "
            "scope is still derived normally — every measured number must come from "
            "the scope the build actually uses."
        ),
    )
    parser.add_argument("--verbose", action="store_true", help="Verbose logging (to stderr).")
    return parser


## @brief Run `clew propose`.
## @param argv Arguments after the subcommand word (defaults to sys.argv[1:]).
## @return Process exit code: 0 on success, 2 when the output would be clobbered.
## @version 4
## @req REQ-DDB-CONFIG-001
def propose_main(argv: list[str] | None = None) -> int:
    """Stdout is redirected to stderr FOR THE ANALYSIS. Every dry run re-runs a
    pipeline importer, and those render a rich progress bar onto the shared
    console — whose file is `sys.stdout`. Piping the draft (`clew propose >
    .clew.yaml`, the obvious first thing anyone does) would otherwise land
    progress bars inside the YAML, ahead of the header. Only the finished document
    reaches the real stdout.

    @brief Parse arguments, build the proposal, emit or refuse.
    @version 4
    """
    args = build_parser().parse_args(argv)
    _configure_logging(args.verbose)
    repo_root = Path(args.repo_root).expanduser().resolve()
    target = Path(args.output).expanduser().resolve() if args.output else None
    refusal = _refusal(target, args.force)
    if refusal:
        print(refusal, file=sys.stderr)
        return 2
    with contextlib.redirect_stdout(sys.stderr):
        proposal = propose(
            repo_root,
            _resolve_db(args.db, repo_root),
            dry_run=not args.no_dry_run,
            use_declaration=not args.ignore_declaration,
        )
    _emit(proposal.yaml_text, target)
    return 0


## @brief Why the output path must not be written, if it must not.
## @param target Resolved output path, or None for stdout.
## @param force Whether --force was given.
## @return The refusal message, or "" when writing is allowed.
## @version 1
## @dg_internal
def _refusal(target: Path | None, force: bool) -> str:
    """Checked BEFORE the analysis runs: a scan of a large tree takes tens of
    seconds, and refusing after it has finished wastes the wait for an outcome
    that was decidable up front.

    @brief Decide whether the requested output path may be written.
    @version 1
    """
    if target is None or force or not target.exists():
        return ""
    return (
        f"refusing to overwrite {target} — it already exists.\n"
        "That file is the repo's own authoritative declaration; replacing it with a "
        "draft would DISABLE every convention it declares while the build kept "
        "succeeding.\n"
        "Write elsewhere, review, and merge by hand — or pass --force if you really "
        "mean to replace it."
    )


## @brief Write the draft to a file or to stdout.
## @param text The rendered draft.
## @param target Output path, or None for stdout.
## @version 1
## @dg_internal
def _emit(text: str, target: Path | None) -> None:
    """@brief Emit the draft, reporting a file write on stderr."""
    if target is None:
        sys.stdout.write(text)
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target} ({len(text.splitlines())} lines, all comments)", file=sys.stderr)


## @brief Resolve the index to measure candidates against.
## @param explicit The --db value, or None.
## @param repo_root Repo being analysed.
## @return Path to an existing index, or None when there is none.
## @version 2
## @dg_internal
def _resolve_db(explicit: str | None, repo_root: Path) -> Path | None:
    """Discovery order: the explicit flag, then the MCP server's registry (the
    database an agent would already have built for this repo), then
    `<repo>/clew.db`. Never invented — a nonexistent path is reported as "no
    index" so the gated sections refuse, rather than as a measurement of nothing.

    @brief Find the database a proposal can be measured against.
    @version 2
    """
    if explicit:
        candidate = Path(explicit).expanduser().resolve()
        return candidate if candidate.is_file() else None
    registered = _registered_db(repo_root)
    local = repo_root / "clew.db"
    return registered or (local if local.is_file() else None)


## @brief The database the MCP target registry has allocated for a repo.
## @param repo_root Repo being analysed.
## @return Path to the registered database when it exists, else None.
## @version 2
## @dg_internal
def _registered_db(repo_root: Path) -> Path | None:
    """Imported lazily and guarded: the registry lives under `mcp_server`, whose
    package import pulls the optional MCP SDK. A core-only install must still be
    able to run the proposer — it just cannot find an agent-built database.

    @brief Look up the registered database for a repo.
    @version 2
    """
    try:
        from ..mcp_server.state import TargetRegistry
    except ImportError:
        return None
    wanted = str(repo_root)
    for target in TargetRegistry().targets():
        path = Path(target.db_path)
        if str(Path(target.repo_path).expanduser().resolve()) == wanted and path.is_file():
            return path
    return None


## @brief Send logging to stderr so the draft on stdout stays parseable.
## @param verbose Whether to log at INFO rather than WARNING.
## @version 1
## @dg_internal
def _configure_logging(verbose: bool) -> None:
    """Deliberately NOT the pipeline's rich handler, which writes to stdout — a
    single INFO line there lands inside the emitted YAML.

    @brief Configure stderr logging for the proposer.
    @version 1
    """
    logging.basicConfig(
        level=logging.INFO if verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
        stream=sys.stderr,
    )
