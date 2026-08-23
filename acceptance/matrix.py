# SPDX-License-Identifier: MIT
"""Provision, generate and grade every target of a grid from ONE invocation.

WHY THIS EXISTS. Running the four phases per target by hand is sixteen commands, each carrying
its own paths, and every path defect this harness has shipped came from that sequence: a
relative `--mcp-config` the agent could not resolve, a `--repo` in the config that named the
wrong tree, and a build that inherited the operator's own `CLEW_STATE_HOME` and overwrote their
personal index. None of those were logic errors. They were an operator typing sixteen commands.

Every path here is DERIVED from one `--out` root and the target's own directory name, so the
provisioner's output and the generator's input cannot disagree — they are the same expression.

IT DOES NOT GRADE INLINE. Generation and grading stay separate phases for the reason
`runner.py` gives: the judge must be arm-blind, and grading is cheap and re-runnable while
generation is neither. This runs generation for every target first, then grading for every
target, so a scorer fix costs a regrade rather than a regeneration.

A TARGET THAT REFUSES DOES NOT STOP THE GRID. Its failure is recorded and the rest run, because
a provisioning problem on one repository is not a reason to spend nothing on the other three.
The count of failed targets is the exit code, and the names are printed at the end — never
summarised as "some targets failed".

@brief Drive a whole grid.
@version 1
"""

from __future__ import annotations

import argparse
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .grader.rubric import Rubric, RubricError, load
from .provision import ProvisionError, provision


## LINE-BUFFERED BEFORE ANY WORK HAPPENS. Measured on the first weekend run: launched detached
## with stdout to a file, the grid generated 22 cells while its log held one line, because Python
## buffers stdout when it is not a tty. A five-hour run whose only progress signal is "the process
## is still alive" cannot be supervised — an operator cannot tell generation from a hang.
##
## Done HERE rather than by asking for `python -u`, because the invocation is exactly where this
## driver exists to stop putting requirements. Before `drive` is defined, so the provisioning
## output — the part that refuses, and the part that matters most — is flushed too.
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, ValueError):  # pragma: no cover - a replaced stream may not support it
    pass


## @brief One target's outcome across the phases this driver ran.
## @version 1
@dataclass(frozen=True)
class TargetOutcome:
    """@brief What happened to one target.
    @version 1
    """

    name: str
    ok: bool
    phase: str
    detail: str = ""


## @brief Every rubric under a targets root, one level deep.
## @param targets_root Directory holding one subdirectory per target.
## @return Sorted rubric paths.
## @version 1
def discover(targets_root: Path) -> list[Path]:
    """ONE LEVEL DEEP, which structurally excludes the private tree — it nests a repository
    directory under `internal/` — without this module naming it. `internal` is skipped by name
    as well, so a future flat layout there is still excluded rather than accidentally included.

    @brief Find the shipped rubrics.
    @return Rubric paths.
    @version 1
    """
    return sorted(p for p in targets_root.glob("*/questions.yaml") if p.parent.name != "internal")


## @brief Provision one target and return its rubric and root.
## @param rubric_path The target's rubric.
## @param out Grid output root.
## @return (rubric, target root, provisioned) or a failure outcome.
## @version 1
def _prepare(rubric_path: Path, out: Path) -> tuple[Rubric, Path, object] | TargetOutcome:
    """@brief Load and provision one target.
    @return Prepared triple, or the outcome that stopped it.
    @version 1
    """
    name = rubric_path.parent.name
    try:
        rubric = load(rubric_path)
    except RubricError as exc:
        return TargetOutcome(name, False, "rubric", str(exc))
    root = out / name
    try:
        prepared = provision(rubric, root)
    except ProvisionError as exc:
        return TargetOutcome(name, False, "provision", str(exc))
    return rubric, root, prepared


## @brief Build the argv a phase would have been invoked with by hand.
## @param phase Subcommand name.
## @param rubric_path The target's rubric.
## @param root The target's run directory.
## @param args Parsed driver arguments.
## @return Argument list for `acceptance.__main__`.
## @version 1
def phase_argv(phase: str, rubric_path: Path, root: Path, args) -> list[str]:
    """THE PATHS ARE DERIVED, NEVER RETYPED, and they are ABSOLUTE. A relative `--mcp-config`
    resolved against the agent's working directory rather than the operator's and produced an
    index arm with no index and no error — the exact failure `check_index_tools_reachable`
    exists to catch, reached by a path that never got that far.

    @brief One phase's argument list.
    @return Argv.
    @version 1
    """
    answers = (root / "answers").resolve()
    common = ["--rubric", str(rubric_path.resolve())]
    if phase == "generate":
        return common + [
            "--models",
            *args.models,
            "--replicates",
            str(args.replicates),
            "--seed",
            str(args.seed),
            "--repo",
            str((root / "repo").resolve()),
            "--out",
            str(answers),
            "--mcp-config",
            str((root / "mcp.json").resolve()),
            "--timeout",
            str(args.timeout),
        ]
    return common + ["--answers", str(answers)]


## @brief Run one phase for one target through the CLI's own entry point.
## @param phase Subcommand name.
## @param argv Its argument list.
## @return True when the phase exited 0.
## @version 1
def run_phase(phase: str, argv: list[str]) -> bool:
    """THROUGH THE SAME ENTRY POINT AN OPERATOR WOULD USE, deliberately. Calling the cmd_*
    functions directly would let this driver drift from the documented invocation, and the
    documented invocation is what every runbook and every past measurement used.

    @brief Execute one phase.
    @return Success.
    @version 1
    """
    from . import __main__ as cli

    saved = sys.argv
    sys.argv = ["acceptance", phase, *argv]
    try:
        return cli.main() == 0
    except SystemExit as exc:
        return exc.code in (0, None)
    finally:
        sys.argv = saved


## @brief Run every phase for every target.
## @param args Parsed driver arguments.
## @return Exit code — the number of targets that failed.
## @version 1
def drive(args) -> int:
    """PHASE-MAJOR, NOT TARGET-MAJOR, for generation and grading: every target generates before
    any target grades. A stop midway then leaves whole targets ungenerated rather than every
    target half-graded, and an ungenerated target is a gap a reader can see.

    @brief Drive the grid.
    @return Number of failed targets.
    @version 1
    """
    rubrics = discover(args.targets)
    if not rubrics:
        print(f"REFUSED — no rubrics under {args.targets}", file=sys.stderr)
        return 1
    print(f"{len(rubrics)} target(s): {', '.join(p.parent.name for p in rubrics)}")

    outcomes: list[TargetOutcome] = []
    ready: list[tuple[Path, Path]] = []
    for rubric_path in rubrics:
        name = rubric_path.parent.name
        print(f"\n=== provision {name}")
        prepared = _prepare(rubric_path, args.out)
        if isinstance(prepared, TargetOutcome):
            print(f"REFUSED — {prepared.detail}", file=sys.stderr)
            outcomes.append(prepared)
            continue
        _, root, _ = prepared
        ready.append((rubric_path, root))

    ## STOP HERE ON REQUEST. Provisioning is where a grid fails CHEAPLY — a pin that moved, a
    ## declaration the build did not record, an MCP config whose tools never register — and each
    ## of those is worth finding before a weekend of agent calls rather than on cell 40 of 120.
    ## `check_index_tools_reachable` already runs inside provision(), so this is a real
    ## end-to-end pre-flight and not merely a clone.
    if getattr(args, "provision_only", False):
        failed = [o for o in outcomes if not o.ok]
        print(f"\nprovisioned {len(ready)}/{len(rubrics)} target(s); no phases run")
        for o in failed:
            print(f"  FAILED {o.name} at {o.phase}: {o.detail[:200]}")
        return len(failed)

    for phase in ("generate", "grade", "report"):
        for rubric_path, root in list(ready):
            name = rubric_path.parent.name
            print(f"\n=== {phase} {name}")
            started = time.perf_counter()
            ok = run_phase(phase, phase_argv(phase, rubric_path, root, args))
            print(
                f"--- {phase} {name} {'ok' if ok else 'FAILED'} "
                f"in {time.perf_counter() - started:.0f}s"
            )
            if not ok:
                outcomes.append(TargetOutcome(name, False, phase))
                ready = [r for r in ready if r[0] != rubric_path]

    failed = [o for o in outcomes if not o.ok]
    print(f"\n{len(rubrics) - len(failed)}/{len(rubrics)} target(s) completed every phase")
    for o in failed:
        print(f"  FAILED {o.name} at {o.phase}: {o.detail[:200]}")
    return len(failed)


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """@brief Drive a grid from one invocation.
    @return Exit code.
    @version 1
    """
    here = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(prog="acceptance.matrix", description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="grid output root")
    parser.add_argument("--targets", type=Path, default=here / "targets")
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--replicates", type=int, default=1)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--timeout", type=int, default=1800)
    parser.add_argument(
        "--provision-only",
        action="store_true",
        help="fetch, build and verify every target, then stop before spending any agent calls",
    )
    return drive(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
