# SPDX-License-Identifier: MIT
"""THE PATH EVERY ADOPTER RUNS, which nothing exercised.

Group D, 1.1.0 MERGE REVIEW. `.pre-commit-hooks.yaml` publishes `entry: clew-guard` with no
subcommand, so pre-commit invokes `clew-guard <file> <file> …` — the no-subcommand
pre-commit mode. This repository dogfoods the gate through a different entry
(`.pre-commit-config.yaml` runs it from its own tree), so the mode an adopter gets was the
only entry point in the release with no test at all.

It is also the mode with the most to go wrong: it must treat bare paths as files rather than
as a subcommand, survive a retired subcommand name appearing as a filename, and return an exit
code pre-commit can read. A break here is invisible in this repo's own gate and visible to
every adopter on their first commit after bumping `rev:`.

INVOKED AS THE INSTALLED CONSOLE SCRIPT, not as `main([...])`, because the console script IS
the thing being tested: `cli_main` wraps `main` in `sys.exit`, and a published `entry:` that
raises rather than exiting is a pre-commit crash rather than a failed hook.

@brief The published `clew-guard` entry point, in the mode the hook uses.
@version 1
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from textwrap import dedent

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
## The console script as `pip install` lays it down, beside the interpreter running the tests.
CLEW_GUARD = Path(sys.executable).parent / "clew-guard"

pytestmark = pytest.mark.skipif(
    not CLEW_GUARD.exists(),
    reason=f"{CLEW_GUARD} is absent, so the published entry point is not installed to test",
)

_DOCUMENTED = dedent("""\
    /**
     * @brief Does the thing.
     * @version 1.0
     */
    void Documented_Func(void) {
        do_stuff();
    }
""")

_UNDOCUMENTED = "void Undocumented_Func(void) {\n    do_stuff();\n}\n"


## @brief Run the published console script in a scratch repo.
## @return The completed process.
## @version 1
def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """@brief Invoke `clew-guard` as pre-commit does. @return The result."""
    return subprocess.run(
        [str(CLEW_GUARD), *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_bare_paths_are_checked_without_a_subcommand(tmp_path: Path) -> None:
    """@brief `clew-guard <file>` validates it, as the published hook invokes it. @version 1"""
    bad = tmp_path / "thing.c"
    bad.write_text(_UNDOCUMENTED)

    result = _run(tmp_path, "thing.c")

    assert result.returncode == 1, (
        f"the published entry point did not report an undocumented function; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "Undocumented_Func" in result.stdout + result.stderr


def test_a_documented_file_passes_through_the_published_entry(tmp_path: Path) -> None:
    """THE SUCCESS PATH BESIDE THE FAILURE PATH. An entry point that always failed would
    satisfy the assertion above while making the hook unusable.

    @brief A documented file exits 0. @version 1
    """
    good = tmp_path / "thing.c"
    good.write_text(_DOCUMENTED)

    result = _run(tmp_path, "thing.c")

    assert result.returncode == 0, (
        f"a documented file failed the published entry point; "
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_several_files_are_all_checked(tmp_path: Path) -> None:
    """pre-commit passes the whole staged set at once, and `require_serial: true` means one
    invocation with many paths rather than many invocations.

    @brief Every path on the command line is checked. @version 1
    """
    (tmp_path / "ok.c").write_text(_DOCUMENTED)
    (tmp_path / "bad.c").write_text(_UNDOCUMENTED)

    result = _run(tmp_path, "ok.c", "bad.c")

    assert result.returncode == 1
    assert "bad.c" in result.stdout + result.stderr


def test_no_files_at_all_is_not_an_error(tmp_path: Path) -> None:
    """pre-commit can invoke a hook with an empty file list. Failing there fails every commit.

    @brief An empty invocation exits 0. @version 1
    """
    assert _run(tmp_path).returncode == 0


def test_the_entry_point_exits_rather_than_raising(tmp_path: Path) -> None:
    """`cli_main` wraps `main` in `sys.exit`, and that wrapper is what the `entry:` names. A
    traceback reaching pre-commit is a crash rather than a failed hook, and reads to an
    adopter as clew being broken rather than as their code being undocumented.

    @brief A failing check produces no traceback. @version 1
    """
    (tmp_path / "bad.c").write_text(_UNDOCUMENTED)

    result = _run(tmp_path, "bad.c")

    assert "Traceback (most recent call last)" not in result.stderr, (
        f"the published entry point raised instead of exiting: {result.stderr!r}"
    )
