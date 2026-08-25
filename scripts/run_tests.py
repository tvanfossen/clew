"""THE ONE DEFINITION OF "RUN THE TESTS". Everything else calls this.

WHY IT EXISTS. The test command used to live as a literal `entry:` string in
`.pre-commit-config.yaml`. That is a fine single source for the GATE — CI runs
`pre-commit run --all-files` against a `.venv` built from each matrix interpreter, so local
and CI genuinely share one definition. What it is NOT is a single source for a HUMAN or an
agent, and that gap has cost this project twice:

  - running `pytest tests/ -q` by hand silently deselects the integration tier, reporting
    green on a tree the gate rejects. That cost most of one session.
  - reproducing a CI matrix leg locally meant re-typing the arguments against a different
    interpreter, which is the same duplication one directory over.

So the arguments live here, once, and `--python` makes "run the gate's suite on 3.10" a named
operation instead of an ad-hoc command someone has to get right from memory.

WHAT IT DOES NOT DO: replace the gate. `pre-commit run --all-files` is still the contract,
because pytest is one hook of many. This is the pytest hook's body and a way to aim it at
another interpreter.

WHY BOTH TIERS, ALWAYS. The integration tier was opt-in behind `--integration` and nothing in
the gate ran it, so a red test survived a release. There is deliberately no way to ask this
script for the unit tier alone.

A LOCAL PASS DOES NOT PROVE THE MATRIX. `.venv` is one interpreter — normally the system one.
CI's job is the other supported versions, and a green local gate says nothing about them: 1.0.8
was tagged with CI red on 3.10 because a 3.12-only gate looked like proof. Use `--python` before
a release, or trust CI and wait for it.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

## THE ARGUMENTS, ONCE. `--integration` is not optional: see the module docstring.
PYTEST_ARGS = ["-m", "pytest", "tests/", "-q", "--integration"]

## The interpreter the gate uses. Kept as the default so `run_tests.py` with no arguments is
## exactly what the pre-commit hook runs, rather than approximately it.
DEFAULT_PYTHON = REPO / ".venv" / "bin" / "python"


##
# @brief Resolve the interpreter to run the suite with.
# @param spec An explicit interpreter path or version like "3.10", or None for the venv's.
# @return Path to a usable interpreter.
# @version 1
def _interpreter(spec: str | None) -> Path:
    """A BARE VERSION IS ACCEPTED because that is how the CI matrix names its legs, and making
    the caller remember where 3.10 lives on this machine is how they end up not checking it.

    Refuses rather than falling back to the current interpreter: silently testing 3.12 when
    3.10 was asked for would report the exact false green this script exists to prevent.

    @brief Find the requested interpreter.
    @return Its path.
    @version 1
    """
    if spec is None:
        if not DEFAULT_PYTHON.exists():
            raise SystemExit(f"no venv interpreter at {DEFAULT_PYTHON} — create .venv first")
        return DEFAULT_PYTHON
    direct = Path(spec)
    if direct.exists():
        return direct
    from shutil import which

    found = which(spec) or which(f"python{spec}")
    if not found:
        raise SystemExit(
            f"no interpreter found for {spec!r}. Tried it as a path, as {spec!r} on PATH, and "
            f"as 'python{spec}'. Refusing to fall back to this process's interpreter, because "
            f"testing the wrong version is worse than not testing."
        )
    return Path(found)


##
# @brief Run the gate's pytest invocation, optionally under another interpreter.
# @return The suite's exit status.
# @version 1
def main() -> int:
    """@brief Run both test tiers.
    @return Exit status from pytest.
    @version 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--python",
        default=None,
        metavar="VERSION_OR_PATH",
        help=(
            "interpreter to run under: '3.10', 'python3.10', or a path. Defaults to .venv's, "
            "which is what the pre-commit hook uses. Use this to reproduce a CI matrix leg."
        ),
    )
    parser.add_argument(
        "extra",
        nargs=argparse.REMAINDER,
        help="further pytest arguments, appended after the mandatory ones",
    )
    args = parser.parse_args()

    python = _interpreter(args.python)
    cmd = [str(python), *PYTEST_ARGS, *args.extra]
    ## PRINTED, so the command in the scrollback is the command that ran. A wrapper that hides
    ## its invocation makes "what did you actually run?" unanswerable after the fact.
    print(f"$ {' '.join(cmd)}", flush=True)
    if args.python is not None:
        version = subprocess.run(
            [str(python), "-c", "import sys; print(sys.version.split()[0])"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        print(f"  interpreter: {python} ({version})", flush=True)
    return subprocess.run(cmd, cwd=str(REPO), check=False).returncode


if __name__ == "__main__":
    sys.exit(main())
