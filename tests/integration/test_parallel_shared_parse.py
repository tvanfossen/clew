# SPDX-License-Identifier: MIT
"""N workers must build the same index as one.

WHY INVARIANCE AND NOT SPEED. The shared parse is the pipeline's dominant cost, so it is the
one stage worth parallelising — but a faster build that indexes something slightly different is
strictly worse than a slow one, and the difference would be invisible: every layer would still
be populated, every count still plausible. So the assertion here is EQUALITY against the serial
path, and speed is reported separately by the build's own stage timings.

The serial path is deliberately kept rather than reimplemented on top of the pool, so `CLEW_JOBS=1`
runs the exact code that shipped before and the two are independent implementations of one
contract. That is what makes this comparison worth anything.

WHAT THIS ALREADY CAUGHT. The first parallel implementation computed 9 payloads more than the
serial one for identical output. Cause: payloads are keyed by `content_sha`, and two indexed
paths held identical bytes — walking file-by-file, the second copy finds the first's row already
stored, but the pool plans every job BEFORE any result comes back, so both were queued and
parsed. Harmless output, wasted CPU, and on a vendored tree of copied headers it would be far
more than one file. `_plan_shared_jobs` now dedupes by sha.

`meta` IS EXCLUDED AND NOTHING ELSE IS. It is doxygen's own table and carries the wall-clock
time of the run, so two builds can never agree on it. Excluding anything further would start
hiding the differences this test exists to find.

@brief Integration test: the parallel shared parse is index-identical to the serial one.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import harvest
from clew.cli import JOBS_ENV, _build_argparser, _run_pipeline

pytestmark = pytest.mark.integration

## doxygen stamps its own run time here, so it differs between any two builds and says nothing
## about what was indexed. The ONLY exclusion.
_VOLATILE_TABLES = {"meta"}

## Build cost measured by the pipeline itself. Expected to differ — that is the point of the
## change under test.
_VOLATILE_META_PREFIX = "refresh."


## @brief Run the pipeline against the pinned target at a given worker count.
## @param root Target repository.
## @param out Database path for this build.
## @param jobs Worker processes for the shared parse.
## @return The output path.
## @version 1
def _build(root: Path, out: Path, jobs: int, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The worker count is an ENVIRONMENT setting, not a flag — the build surface is a pinned
    set of six arguments and a machine property has no business in a repo declaration. So a test
    sets it the way an operator would.

    @brief Build the target at an explicit worker count.
    @return The output database path.
    @version 1
    """
    monkeypatch.setenv(JOBS_ENV, str(jobs))
    args = _build_argparser().parse_args(["--repo-root", str(root), "--output", str(out)])
    _run_pipeline(args)
    return out


## @brief Every user table's rows, sorted, with volatile metadata dropped.
## @param db The database to snapshot.
## @return Mapping of table name to sorted row representations.
## @version 1
def _dump(db: Path) -> dict[str, list[str]]:
    """@brief Snapshot a database for equality assertions.
    @return Table name to sorted rows.
    @version 1
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        names = sorted(
            r[0]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
            if not r[0].startswith("sqlite_") and r[0] not in _VOLATILE_TABLES
        )
        out: dict[str, list[str]] = {}
        for name in names:
            rows = sorted(repr(r) for r in conn.execute(f"SELECT * FROM {name}"))
            if name == "build_meta":
                rows = [r for r in rows if f"'{_VOLATILE_META_PREFIX}" not in r]
            out[name] = rows
        return out
    finally:
        conn.close()


## @brief A parallel build produces the same index as a serial one.
## @version 2
def test_parallel_shared_parse_is_index_identical(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE LOAD-BEARING TEST FOR THE WHOLE CHANGE. Compared table by table rather than by a
    summary count, because a count that matches is the failure mode this is guarding against:
    a mis-parallelised harvest can easily produce the right NUMBER of rows attributed to the
    wrong file.

    @brief N workers equal one worker, row for row.
    @version 1
    """
    serial = _build(guard_repo, tmp_path / "serial.db", 1, monkeypatch)
    parallel = _build(guard_repo, tmp_path / "parallel.db", 4, monkeypatch)

    a, b = _dump(serial), _dump(parallel)
    assert set(a) == set(b), "the two builds produced different table sets"
    differing = {t for t in a if a[t] != b[t]}
    assert not differing, (
        f"parallel and serial builds disagree on table(s) {sorted(differing)} — a faster index "
        "that describes something else is worse than a slow one"
    )
    ## Anti-vacuity: a fixture that indexed nothing would make every table trivially equal.
    assert len(a["memberdef"]) > 0, "the fixture produced no symbols; the comparison is vacuous"


## @brief The parallel path is actually taken when CLEW_JOBS > 1.
## @version 1
def test_jobs_greater_than_one_takes_the_pooled_path(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE OTHER HALF OF THE ANTI-VACUITY ARGUMENT, and it is not paranoia. If `CLEW_JOBS` failed to
    reach `run_shared_parse` — a plumbing slip anywhere between argparse and the plan — the
    equality test above would compare two SERIAL builds and pass forever while the feature did
    nothing. It asserts equality, so it cannot tell the difference on its own.

    @brief CLEW_JOBS=4 reaches the pool.
    @version 1
    """
    calls: list[int] = []
    real = harvest._shared_parse_pooled

    def _spy(*args: object, **kwargs: object) -> None:
        calls.append(args[5] if len(args) > 5 else kwargs["workers"])  # type: ignore[arg-type]
        return real(*args, **kwargs)  # type: ignore[arg-type,no-any-return]

    monkeypatch.setattr(harvest, "_shared_parse_pooled", _spy)
    _build(guard_repo, tmp_path / "pooled.db", 4, monkeypatch)
    assert calls == [4], f"the pooled path was not taken with CLEW_JOBS=4 (calls={calls})"


## @brief CLEW_JOBS=1 keeps the serial path entirely.
## @version 1
def test_jobs_one_never_starts_a_pool(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The switch-off must be real. `CLEW_JOBS=1` is what an operator reaches for when the pool is
    suspected, so it has to bypass the pool rather than run one worker through it.

    @brief CLEW_JOBS=1 starts no pool.
    @version 1
    """
    started: list[object] = []

    def _spy(*args: object, **kwargs: object) -> None:
        started.append(args)

    monkeypatch.setattr(harvest, "_shared_parse_pooled", _spy)
    _build(guard_repo, tmp_path / "serial-only.db", 1, monkeypatch)
    assert started == [], "CLEW_JOBS=1 started a process pool"


## @brief A pooled build warms every stage, so no stage parses in the parent.
## @version 1
def test_the_pool_warms_every_stage_so_no_stage_reparses(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE ONLY CHECK THAT CATCHES A POOL WHICH SILENTLY WARMS NOTHING, and it took two failed
    mutations to find. Dropping a payload in the pooled path leaves the INDEX identical, because
    a stage that misses simply re-parses the file itself; and it leaves the sidecar ROW COUNT
    identical too, because that fallback also stores what it parsed. The optimisation can
    therefore be entirely lost with every other assertion in this file still green.

    WHERE the parse happens is the signal that survives. With `CLEW_JOBS > 1` the shared parse
    runs in worker processes, so this patch — installed in the PARENT — sees nothing from it.
    Anything it does see is a stage falling back to its own parse, which is exactly the waste
    the shared pass exists to remove.

    @brief A pooled shared parse leaves no work for the stages.
    @version 1
    """
    parsed: list[str] = []
    real = harvest._ast_parse_one_file

    def _counting(rel_path: str, *args: object, **kwargs: object) -> object:
        parsed.append(rel_path)
        return real(rel_path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(harvest, "_ast_parse_one_file", _counting)
    _build(guard_repo, tmp_path / "warmed.db", 4, monkeypatch)

    assert parsed == [], (
        f"{len(parsed)} file(s) were parsed in the parent process after a pooled shared parse "
        f"(first: {parsed[:3]}). Every stage should have read a warmed cache row; parsing here "
        "means the pool failed to store payloads and the whole optimisation was silently lost, "
        "which no index comparison can detect because the fallback produces identical rows."
    )
