# SPDX-License-Identifier: MIT
"""Time a one-file-edit refresh on a real repository, stage by stage, and leave nothing behind.

1.3.3, Track 2 (LSP-speed refresh, target < 1 s for a one-file save). The baseline the track is
measured against, per repository. Method, in full, so the number carries it:

  1. `git clone --shared` the target at HEAD into a scratch directory — the target's own tree and
     `.git` are never written to;
  2. one cold build of the clone (`python -m clew --repo-root <clone> --output <scratch>/clew.db`);
  3. N times: append one comment line to the named file, rebuild, read `refresh.duration_ms` and
     `refresh.stages` from the index's `build_meta`;
  4. delete the scratch directory (clone, index, idxcache, doxygen output) unless `--keep`.

    .venv/bin/python scripts/refresh_bench.py <repo> <file relative to repo> [--reps 3]

Prints one JSON object: cold ms, each refresh's total ms, and the per-stage ms of the median
refresh, slowest first.

@brief One-file refresh benchmark with per-stage timings.
@version 2
"""

from __future__ import annotations

import argparse
import json
import shutil
import sqlite3
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

## Line-comment prefix by extension, so the edit is valid source in the file's language.
_COMMENT = {".py": "#", ".sh": "#", ".cmake": "#", ".txt": "#"}

## PR1 (2.0.0): `--edit function` appends a NEW FUNCTION instead of a comment, the structural edit
## the fast tier used to refuse. One template per language family, `{i}` making each rep's unique.
_FUNCTION = {
    ".py": "\n\ndef refresh_bench_fn_{i}():\n    return {i}\n",
    ".ts": "\nexport function refreshBenchFn{i}(): number {{\n  return {i};\n}}\n",
    ".tsx": "\nexport function refreshBenchFn{i}(): number {{\n  return {i};\n}}\n",
    ".js": "\nexport function refreshBenchFn{i}() {{\n  return {i};\n}}\n",
    ".c": "\nint refresh_bench_fn_{i}(void)\n{{\n    return {i};\n}}\n",
    ".cpp": "\nint refresh_bench_fn_{i}()\n{{\n    return {i};\n}}\n",
    ".cc": "\nint refresh_bench_fn_{i}()\n{{\n    return {i};\n}}\n",
}


##
# @brief The text one rep appends: a comment, or a new function.
# @param target The edited file.
# @param edit `comment` or `function`.
# @param i The rep.
# @return The text.
# @version 1
def _edit_text(target: Path, edit: str, i: int) -> str:
    """@brief One rep's edit. @return Text."""
    if edit == "function":
        template = _FUNCTION.get(target.suffix)
        if template is None:
            raise SystemExit(f"--edit function has no template for {target.suffix}")
        return template.format(i=i)
    return f"\n{_COMMENT.get(target.suffix, '//')} refresh_bench edit {i}\n"


##
# @brief Build the clone once through the real CLI.
# @param clone The tree to index.
# @param db The index path.
# @return Elapsed milliseconds.
# @version 1
def _build(clone: Path, db: Path, verb: str = "") -> int:
    """THROUGH THE CLI, as `incremental_probe` does: the number must be what a user's build costs.

    @brief Run one build.
    @return Elapsed ms.
    @version 1
    """
    started = time.monotonic()
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "clew",
            *([verb] if verb else []),
            "--repo-root",
            str(clone),
            "--output",
            str(db),
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr[-4000:])
        raise SystemExit(f"build failed ({proc.returncode})")
    return int((time.monotonic() - started) * 1000)


##
# @brief Read the refresh total and stage breakdown the build stamped.
# @param db The index.
# @return (duration ms, {stage: ms}).
# @version 1
def _stamped(db: Path) -> tuple[int, dict[str, int]]:
    """@brief Read refresh.* from build_meta. @return Duration and stages."""
    conn = sqlite3.connect(db)
    try:
        meta = dict(conn.execute("SELECT key, value FROM build_meta WHERE key LIKE 'refresh.%'"))
    finally:
        conn.close()
    stages = {}
    for part in str(meta.get("refresh.stages", "")).split():
        name, _, ms = part.partition("=")
        stages[name] = int(ms)
    return int(meta.get("refresh.duration_ms", -1)), stages


##
# @brief The recorded cost of the last fast refresh, if one is pending.
# @param db The index.
# @return Milliseconds, or None.
# @version 1
def _fast_ms(db: Path) -> int | None:
    """@brief Read fast.ms. @return Ms or None."""
    conn = sqlite3.connect(db)
    try:
        row = conn.execute("SELECT value FROM build_meta WHERE key = 'fast.ms'").fetchone()
    finally:
        conn.close()
    return int(row[0]) if row else None


##
# @brief Clone, build, edit-and-refresh N times, report, clean up.
# @return Process exit code.
# v2: --edit function; fast_ran per rep (2.0.0, PR1)
# @version 2
def main() -> int:
    """@brief Entry point. @return 0."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("repo", type=Path)
    parser.add_argument("file")
    parser.add_argument("--reps", type=int, default=3)
    parser.add_argument("--keep", action="store_true", help="keep the scratch directory")
    parser.add_argument(
        "--fast", action="store_true", help="refresh with `clew refresh` (fast tier first)"
    )
    parser.add_argument(
        "--edit",
        choices=("comment", "function"),
        default="comment",
        help="what each rep appends: a comment line, or a new function (PR1)",
    )
    args = parser.parse_args()
    work = Path(tempfile.mkdtemp(prefix="clew-bench-"))
    try:
        clone, db = work / "clone", work / "clew.db"
        subprocess.run(
            ["git", "clone", "-q", "--shared", str(args.repo.resolve()), str(clone)], check=True
        )
        cold = _build(clone, db)
        target = clone / args.file
        runs = []
        for i in range(args.reps):
            with target.open("a") as handle:
                handle.write(_edit_text(target, args.edit, i))
            wall = _build(clone, db, "refresh" if args.fast else "")
            stamped, stages = _stamped(db)
            ## A FAST REFRESH STAMPS `fast.ms`, not `refresh.*` (those describe the last FULL
            ## build), so its cost is read from there. `fast_ran` SAYS WHICH: a refusal is a full
            ## build, and its time must not be reported as the fast tier's.
            fast_ms = _fast_ms(db) if args.fast else None
            stamped = fast_ms if fast_ms is not None else stamped
            runs.append(
                {
                    "wall_ms": wall,
                    "duration_ms": stamped,
                    "stages": stages,
                    "fast_ran": fast_ms is not None,
                }
            )
        median = sorted(runs, key=lambda r: r["duration_ms"])[len(runs) // 2]
        print(
            json.dumps(
                {
                    "repo": str(args.repo),
                    "file": args.file,
                    "cold_ms": cold,
                    "refresh_ms": [r["duration_ms"] for r in runs],
                    "refresh_wall_ms": [r["wall_ms"] for r in runs],
                    "edit": args.edit,
                    "fast_ran": [r["fast_ran"] for r in runs],
                    "median_refresh_ms": statistics.median(r["duration_ms"] for r in runs),
                    "median_stages": dict(sorted(median["stages"].items(), key=lambda kv: -kv[1])),
                },
                indent=1,
            )
        )
    finally:
        if args.keep:
            print(f"scratch kept at {work}", file=sys.stderr)
        else:
            shutil.rmtree(work, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
