# SPDX-License-Identifier: MIT
"""MEASURE ONE STAGE BY RE-RUNNING IT, not by diffing two builds.

`dominated_edges` records why this exists, and it cost a wrong number to learn:
diffing two full builds reported the self-index's non-fuzzy edge count moving by
+1 for a delete-only pass, because two doxygen/tree-sitter runs over one tree are
not bit-identical. A build is not a reproducible measuring instrument.

So: copy a built index, delete the rows one stage owns, re-run THAT stage against
the copy, and diff. Everything else in the database is held fixed by construction,
so whatever moved is attributable to the stage. Every figure in the 1.0.27 release
notes was produced this way — `resolved 4428 -> 4873` among them.

The original index is never opened for writing, and the copy lands wherever you
point `--out`, so this is safe to run against a target you care about.

    .venv/bin/python scripts/stage_probe.py --target ~/Projects/foo --stage ast_call_edges

@brief Re-run one pipeline stage against a copy of an index and diff the result.
@version 1
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
from collections.abc import Callable
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from clew.call_edges import import_ast_call_edges  # noqa: E402
from clew.mcp_server.state import TargetRegistry, db_status  # noqa: E402


## What each probeable stage owns: the rows to clear, and how to re-run it.
##
## KEYED BY THE ROWS IT WRITES, because that is what makes the diff attributable — a stage
## whose deletion predicate is wrong measures the wrong thing silently. Add a stage here
## only once you can state exactly which rows are its output.
_STAGES: dict[str, tuple[str, Callable[[Path, Path], None]]] = {
    "ast_call_edges": (
        "DELETE FROM call_edges WHERE source LIKE 'ast%'",
        import_ast_call_edges,
    ),
}


## @brief Count the rows of interest for a stage, before and after.
## @param db Path to the database copy.
## @return {label: count} for the diff report.
## @version 1
def _counts(db: Path) -> dict[str, int]:
    """@brief Snapshot the edge counts a stage diff is read from.
    @return Label to count.
    @version 1
    """
    conn = sqlite3.connect(db)
    try:
        rows = dict(
            conn.execute(
                "SELECT confidence, COUNT(*) FROM call_edges "
                "WHERE source LIKE 'ast%' GROUP BY confidence"
            )
        )
        extra = {}
        for table in ("unresolved_inbound",):
            try:
                extra[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()
    return {**{f"ast/{k}": v for k, v in rows.items()}, **extra}


## @brief Copy an index, re-run one stage against the copy, and print the diff.
## @return Process exit code.
## @version 1
def main() -> int:
    """@brief Re-run one stage in isolation and report what moved.
    @return 0 on success, 2 on a bad argument.
    @version 1
    """
    parser = argparse.ArgumentParser(prog="stage_probe", description=__doc__)
    parser.add_argument("--target", required=True, help="Repo root whose index to copy.")
    parser.add_argument("--stage", default="ast_call_edges", choices=sorted(_STAGES))
    parser.add_argument(
        "--out",
        default=".claude/tmp/stage_probe.db",
        help="Where to write the working COPY. The source index is never modified.",
    )
    parser.add_argument(
        "--allow-stale",
        action="store_true",
        help=(
            "Measure even when the target's sources have moved since the index was built. "
            "The diff is then not attributable to the stage — use it to explore, never to "
            "quote a figure."
        ),
    )
    args = parser.parse_args()

    target = Path(args.target).expanduser().resolve()
    registry = TargetRegistry()
    entry = registry.register(str(target))
    source = Path(entry.db_path)
    if not source.exists():
        print(f"no index for {target} at {source} — build it first", file=sys.stderr)
        return 2

    ## REFUSES ON A DRIFTED BASELINE, and that guard is the difference between a measurement
    ## and a number. Caught the first time this script was run: entropic's index read
    ## `resolved 4889` while a re-run produced 4839, because the working tree had moved since
    ## the index was built — so "before" described one source tree and "after" another, and
    ## the -50 was attributable to nothing. A diff whose two sides do not share a source tree
    ## is exactly the unreproducible instrument this approach was adopted to replace.
    status = db_status(entry)
    drifted = int(status.get("source_changed_files") or 0)
    if drifted and not args.allow_stale:
        print(
            f"REFUSING: {drifted} indexed source file(s) have changed since this index was "
            f"built, so a before/after diff would compare two different trees. Refresh the "
            f"target first, or pass --allow-stale to measure anyway and read the numbers as "
            f"indicative only.",
            file=sys.stderr,
        )
        return 2

    dest = Path(args.out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(source, dest)
    ## The harvest sidecar rides along, so the re-run reuses cached per-file parses and
    ## measures the RESOLUTION logic rather than the cost of parsing the tree again.
    sidecar = source.with_suffix(source.suffix + ".idxcache")
    if sidecar.exists():
        shutil.copy(sidecar, dest.with_suffix(dest.suffix + ".idxcache"))

    predicate, run = _STAGES[args.stage]
    before = _counts(dest)
    conn = sqlite3.connect(dest)
    conn.execute(predicate)
    conn.commit()
    conn.close()

    run(dest, target)

    after = _counts(dest)
    print(f"\n{args.stage} on {target.name}, re-run against a copy:\n")
    for key in sorted(set(before) | set(after)):
        was, now = before.get(key, 0), after.get(key, 0)
        arrow = "" if was == now else f"   ({now - was:+d})"
        print(f"  {key:<24} {was:>7} -> {now:<7}{arrow}")
    print(f"\ncopy left at {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
