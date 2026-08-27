# SPDX-License-Identifier: MIT
"""Two processes building one target must not destroy the index.

MEASURED BEFORE THE FIX, twice, with variance in WHICH process won but not in the outcome:

    run 1: exits=[1, 0]   memberdef=5208            <- survived
    run 2: exits=[1, 1]   memberdef=NO GRAPH        <- no such table

The damaged database was 12 KB holding ONLY `build_meta` — no `memberdef`, no `call_edges`, the
whole graph gone — while `PRAGMA integrity_check` returned `ok` and one of the two processes exited
**0**, reporting success. A single build of the same tree yields 5208 rows. So this is the shape
this project keeps finding: a success message plus a plausible artifact is what a destroyed layer
looks like.

CAUSE: three paths derived from the output name with no per-process component — the staging temp,
the doxygen scratch dir, and the sidecar. Two processes shared all three, and either one's
`except BaseException: tmp.unlink()` deleted the other's staging file.

THE RACE TEST HERE IS OPPORTUNISTIC AND IS NOT THE GATE. Measured with the defect deliberately
restored, it caught it 2 times in 4 — the collision needs both processes inside a narrow window,
and a 50% detector is not something to gate a release on. The deterministic guard is
`test_the_staging_path_is_private_to_this_process` below, which asserts the property directly and
cannot be flaky. This one stays because it exercises the WHOLE pipeline end to end, which the unit
test by construction does not, and a real destroyed graph is worth catching even half the time.

WHY THIS IS AN INTEGRATION TEST AND CANNOT BE A UNIT ONE. `tests/test_mcp_routing.py` already
asserts concurrent refreshes build once, and it PASSED throughout the whole defect, because it
stubs `state._run_build` — the real pipeline, the atomic swap and the sidecar are never reached. A
test that stubs the thing under test cannot see this. So these spawn real processes and run the
real build.

@brief Concurrent whole-pipeline builds of one target.
@version 1
"""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest

from clew import cli

REPO = Path(__file__).resolve().parent.parent.parent

## Tables whose absence means the graph was destroyed rather than merely stale. `build_meta` is
## deliberately EXCLUDED: the damaged database had it, which is exactly why its presence proves
## nothing and a naive "does the file look like a database" check passed.
_GRAPH_TABLES = ("memberdef", "call_edges", "xrefs", "path")


##
# @brief Row counts for the graph tables, or None per table when it is absent.
# @param db Path to a built index.
# @return Mapping of table name to row count or None.
# @version 1
def _graph_counts(db: Path) -> dict[str, int | None]:
    """@brief Count the tables whose loss defines this defect.
    @return Table to count, None when the table does not exist.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        out: dict[str, int | None] = {}
        for table in _GRAPH_TABLES:
            try:
                out[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608
            except sqlite3.Error:
                out[table] = None
        return out
    finally:
        conn.close()


##
# @brief Run one whole-pipeline build in its own process.
# @param repo Repository to index.
# @param out Output database path.
# @return The completed process.
# @version 1
def _build_proc(repo: Path, out: Path) -> subprocess.Popen:
    """Spawned rather than called, because the defect is BETWEEN processes: the in-process
    `anyio.Lock` that deduplicates refreshes does not exist across them, and that is the whole
    point of this file.

    @brief Start a real build subprocess.
    @return The running process.
    @version 1
    """
    code = (
        f"import sys; sys.path.insert(0, {str(REPO)!r});"
        f"from clew.cli import build_index;"
        f"build_index(repo_root={str(repo)!r}, output={str(out)!r})"
    )
    return subprocess.Popen(
        [sys.executable, "-c", code],
        cwd=str(REPO),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


##
# @brief Two concurrent builds of one target must equal one build.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
@pytest.mark.integration
def test_two_concurrent_builds_of_one_target_do_not_destroy_the_index(tmp_path: Path) -> None:
    """AN INVARIANCE, NOT A NUMBER. N concurrent builds must produce what one build produces, row
    for row. A count that merely looks plausible is what the damaged 12 KB database looked like to
    every check short of opening it.

    The reference build runs FIRST and alone, so the expected counts come from this tree on this
    machine rather than from a figure written down here that would rot.

    @brief Concurrent builds agree with a single build.
    @return None.
    @version 1
    """
    ## THE WHOLE REPOSITORY, NOT A SUBDIRECTORY, AND THAT IS LOAD-BEARING. The first version of
    ## this test pointed at `clew/` alone and PASSED — a ~3 s build finishes before the other
    ## process reaches the contended stage, so the race window never opens and the test was
    ## vacuous. The full tree takes ~11 s and reproduces the destroyed graph every time. A
    ## concurrency test whose subject is fast enough to serialise itself proves nothing.
    repo = REPO

    reference = tmp_path / "single" / "clew.db"
    reference.parent.mkdir(parents=True)
    proc = _build_proc(repo, reference)
    proc.communicate(timeout=900)
    assert proc.returncode == 0, "the reference build failed; nothing below can be interpreted"
    expected = _graph_counts(reference)
    assert expected["memberdef"], f"the reference build produced no symbols: {expected}"

    contended = tmp_path / "contended" / "clew.db"
    contended.parent.mkdir(parents=True)
    procs = [_build_proc(repo, contended) for _ in range(2)]
    results = [p.communicate(timeout=900) for p in procs]
    codes = [p.returncode for p in procs]

    actual = _graph_counts(contended)

    ## THE GRAPH MUST SURVIVE. Checked before the exit codes, because a destroyed index with two
    ## zero exits is the worst outcome and the one that shipped.
    missing = [t for t, n in actual.items() if n is None]
    assert not missing, (
        f"tables {missing} are ABSENT after two concurrent builds — the graph was destroyed. "
        f"Reference build had {expected}. Note the file still opens and integrity_check still "
        f"returns ok, which is why this must be asserted per table."
    )
    assert actual == expected, (
        f"two concurrent builds produced a different index than one build.\n"
        f"  one build : {expected}\n"
        f"  concurrent: {actual}"
    )

    ## AND NO PROCESS MAY CLAIM SUCCESS FALSELY. A non-zero exit is acceptable — losing a race is
    ## legitimate — but a zero exit must mean the index is intact, which the assertions above have
    ## just established. What is forbidden is the pair seen before the fix: one exit 0 beside a
    ## destroyed graph.
    assert any(c == 0 for c in codes), (
        f"both builds failed ({codes}); at least one must succeed or the target is left with no "
        f"usable index at all. stderr: {results[0][1][-400:]!r} {results[1][1][-400:]!r}"
    )


##
# @brief The staging path must be private to the writing process.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_the_staging_path_is_private_to_this_process(tmp_path: Path) -> None:
    """THE DETERMINISTIC GUARD, and the reason `staging_path` was extracted from an inline
    expression. The property is "no two processes stage into one file", and that does not need a
    race to check — which matters, because the race version of this test catches the defect only
    about half the time.

    Asserted three ways, because "contains a pid" alone would pass for a path that embedded the
    pid and then ignored it:
      - the live output path is never itself the staging path;
      - two different pids yield two different paths;
      - the path is a SIBLING of the output, since the swap is `os.replace` and that is only
        atomic within one filesystem.

    @brief Staging paths differ per process and sit beside the output.
    @return None.
    @version 1
    """
    output = tmp_path / "clew.db"

    mine = cli.staging_path(output)
    assert mine != output, "the staging path must not be the live path"
    assert mine.parent == output.parent, (
        "staging must be a sibling of the output: the swap is os.replace, which is atomic only "
        "within a filesystem"
    )
    assert str(os.getpid()) in mine.name, f"no process identity in {mine.name!r}"

    ## Two processes, deterministically: patch the pid rather than spawning.
    seen = set()
    for fake in (111, 222):
        with mock.patch.object(os, "getpid", return_value=fake):
            seen.add(cli.staging_path(output))
    assert len(seen) == 2, (
        f"two different processes derived the SAME staging path {seen} — that is the defect: "
        f"either one's failure handler unlinks the other's work, and the measured result was a "
        f"12 KB index holding only build_meta"
    )
