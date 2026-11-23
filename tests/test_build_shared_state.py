# SPDX-License-Identifier: MIT
"""The build lock OWNS a target's shared build state (2.0.0; owner Q/A 2026-11-20).

FOUND IN THE PG4 GATE. `tests/integration/test_concurrent_builds.py` failed once: one of two
concurrent builds died on `sqlite3.OperationalError: database is locked` and the other exited 0
holding 43 of 10,430 memberdef rows. Reproduced deterministically afterwards (4 of 4 overlapping
pairs, `.claude/tmp/r5/race_repro.py`): one build crashed every time, at `IndexCache.__init__`
(twice), at `extract_put` (twice) — and the gate's run at `record_splice`. The 43-row outcome was
not reproduced in 4 tries; doxygen replaces its output atomically (probe:
`.claude/tmp/r5/reader_probe.py`), so the open-reader case is safe.

THE CAUSE IS SHARED STATE NO LOCK GUARDED. Staging is per-process (1.0.12), but every build of one
output shares `<output>.idxcache` and `<stem>.doxygen/` (`cli._doxygen_out_dir` v4 keyed it to the
output so a warm build finds the previous doxygen run). `buildlock.py` called the lock "an
optimisation, not a correctness mechanism", and only the MCP server took it.

THE RULING: the lock owns the shared state. The holder uses the shared cache and doxygen scratch
directory; a build that cannot get the lock within the bound builds with NO shared cache and a
PRIVATE scratch directory — slower, always correct, never blocked and never failed. Locking that is
unavailable on the platform (`fcntl` absent) yields None and keeps the shared path, as before,
because a lock that cannot exist cannot tell contention from its absence. The lock is re-entrant
within a process, so the MCP server, which takes it before building in-process, takes it once.

@brief Tests that the build lock owns the shared cache and doxygen scratch directory.
@version 1
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from contextlib import contextmanager
from pathlib import Path
from unittest import mock

from clew import cli, fasttier
from clew.buildlock import build_lock


def test_the_lock_is_reentrant_within_a_process(tmp_path: Path) -> None:
    """@brief The MCP server holds it, then builds in-process: the inner take is held at once."""
    db = tmp_path / "clew.db"
    with build_lock(db) as outer:
        started = time.monotonic()
        with build_lock(db, wait_seconds=2.0) as inner:
            elapsed = time.monotonic() - started
    assert (outer, inner) == (True, True)
    assert elapsed < 1.0, f"the process waited {elapsed:.1f}s on a lock it already held"


def test_a_released_lock_is_taken_again(tmp_path: Path) -> None:
    """@brief Re-entrancy tracks the hold: after release, the next take really locks."""
    db = tmp_path / "clew.db"
    with build_lock(db) as first:
        pass
    with build_lock(db) as second:
        assert (first, second) == (True, True)


def test_unavailable_locking_yields_none(tmp_path: Path) -> None:
    """@brief No `fcntl`: None, which is neither held nor contended."""
    with mock.patch.dict(sys.modules, {"fcntl": None}):
        with build_lock(tmp_path / "clew.db") as held:
            assert held is None


@contextmanager
def _lock_yielding(value):
    """@brief A stand-in for `build_lock` that yields `value`."""

    @contextmanager
    def fake(_output, wait_seconds=None):  # noqa: ARG001
        yield value

    with mock.patch.object(cli, "build_lock", fake):
        yield


def _pipeline_args(tmp_path: Path) -> argparse.Namespace:
    """@brief Parsed build arguments for an output under tmp_path. @return Namespace."""
    return cli._build_argparser().parse_args(["--output", str(tmp_path / "clew.db")])


def _seen_by_inner(tmp_path: Path, held) -> argparse.Namespace:
    """@brief Run `_run_pipeline` with the lock yielding `held`; return the args the stages saw."""
    seen = {}

    def inner(args):
        seen["args"] = argparse.Namespace(**vars(args))
        seen["scratch"] = cli._doxygen_out_dir(args)

    args = _pipeline_args(tmp_path)
    with _lock_yielding(held), mock.patch.object(cli, "_run_pipeline_inner", inner):
        cli._run_pipeline(args)
    seen["args"].scratch = seen["scratch"]
    return seen["args"]


def test_a_build_that_holds_the_lock_uses_the_shared_state(tmp_path: Path) -> None:
    """@brief Held: the shared cache and `<stem>.doxygen`, as before."""
    args = _seen_by_inner(tmp_path, True)
    assert args.no_index_cache is False
    assert args.scratch == tmp_path / "clew.doxygen"


def test_a_build_that_cannot_get_the_lock_builds_privately(tmp_path: Path) -> None:
    """@brief Contended: no shared cache, and a scratch directory carrying this process's pid."""
    args = _seen_by_inner(tmp_path, False)
    assert args.no_index_cache is True, "a build without the lock must not open the shared cache"
    assert args.scratch != tmp_path / "clew.doxygen"
    assert str(os.getpid()) in args.scratch.name and args.scratch.parent == tmp_path


def test_unavailable_locking_keeps_the_shared_state(tmp_path: Path) -> None:
    """@brief None (no locking on this platform): unchanged behaviour, the shared cache kept."""
    args = _seen_by_inner(tmp_path, None)
    assert args.no_index_cache is False
    assert args.scratch == tmp_path / "clew.doxygen"


def test_a_private_scratch_directory_is_removed_after_the_build(tmp_path: Path) -> None:
    """@brief No-FS-bloat: the per-process doxygen directory does not outlive its build."""
    made = {}

    def inner(args):
        made["dir"] = cli._doxygen_out_dir(args)
        made["dir"].mkdir(parents=True)
        (made["dir"] / "doxygen_sqlite3.db").write_text("x")

    with _lock_yielding(False), mock.patch.object(cli, "_run_pipeline_inner", inner):
        cli._run_pipeline(_pipeline_args(tmp_path))
    assert not made["dir"].exists()


def test_the_fast_tier_does_not_touch_the_cache_without_the_lock(tmp_path: Path) -> None:
    """@brief Contended: the fast tier declines (None) before opening the shared cache."""
    db, cache = tmp_path / "clew.db", tmp_path / "clew.db.idxcache"
    db.write_text("")
    cache.write_text("")

    @contextmanager
    def contended(_output, wait_seconds=None):  # noqa: ARG001
        yield False

    with (
        mock.patch.object(fasttier, "build_lock", contended),
        mock.patch.object(fasttier, "_current_build", return_value=True),
        mock.patch.object(fasttier, "IndexCache", side_effect=AssertionError("cache opened")),
    ):
        assert fasttier.try_fast_refresh(db, tmp_path, cache) is None
