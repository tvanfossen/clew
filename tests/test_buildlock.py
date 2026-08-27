# SPDX-License-Identifier: MIT
"""The cross-process build lock, and above all the ways it must NOT block (#497).

This lock is an OPTIMISATION. Since 1.0.12 staging paths carry the pid and the swap is atomic, so
two concurrent builds are already safe — the last writer wins with a complete index. All this
removes is the waste of building twice.

That makes the failure direction the important property, not the happy path: a lock that can only
ever save a duplicate build must never be able to prevent one. Three releases immediately before
this were hangs, so every test below is about proceeding rather than about excluding.

@brief Tests for cross-process build locking.
@version 1
"""

from __future__ import annotations

import multiprocessing
import time
from pathlib import Path

import pytest

from clew.buildlock import DEFAULT_WAIT_SECONDS, build_lock, lock_path


##
# @brief Hold the lock in a child process for a while, signalling when it is held.
# @param db The database path being guarded.
# @param acquired A shared flag set once the lock is held.
# @param seconds How long to keep holding it.
# @return None.
# @version 1
def _hold(db: str, acquired, seconds: float) -> None:  # noqa: ANN001
    """@brief Child that takes the lock and sleeps.
    @return None.
    @version 1
    """
    with build_lock(Path(db)) as held:
        acquired.value = 1 if held else 0
        time.sleep(seconds)


##
# @brief An uncontended build takes the lock.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_an_uncontended_build_holds_the_lock(tmp_path: Path) -> None:
    """@brief The ordinary case reports the lock held.
    @return None.
    @version 1
    """
    with build_lock(tmp_path / "clew.db") as held:
        assert held is True
        assert lock_path(tmp_path / "clew.db").exists()


##
# @brief A second process must not be blocked indefinitely by the first.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
@pytest.mark.integration
def test_a_contended_build_gives_up_and_proceeds(tmp_path: Path) -> None:
    """THE LOAD-BEARING TEST, because this is the failure this lock could introduce. A holder that
    outlasts the wait must leave the second process free to BUILD — reporting `held=False` — not
    waiting on it. The caller treats False as "proceed", so a lock that never returned would be a
    hang, and hangs are what the three releases before this were about.

    The wait is shortened to keep the test fast; the production bound is a backstop.

    @brief A waiter past the bound proceeds unlocked.
    @return None.
    @version 1
    """
    db = tmp_path / "clew.db"
    acquired = multiprocessing.Value("i", 0)
    child = multiprocessing.Process(target=_hold, args=(str(db), acquired, 5.0))
    child.start()
    try:
        for _ in range(100):  # wait for the child to actually hold it
            if acquired.value:
                break
            time.sleep(0.05)
        assert acquired.value == 1, "the child never acquired the lock — test would be vacuous"

        started = time.monotonic()
        with build_lock(db, wait_seconds=0.5) as held:
            elapsed = time.monotonic() - started
            assert held is False, (
                "the lock was reported held while a child process held it — that would let two "
                "builds run believing each was exclusive"
            )
        assert elapsed < 4.0, (
            f"waited {elapsed:.1f}s despite a 0.5s bound; an unbounded wait here is a hang"
        )
    finally:
        child.join(timeout=10)
        if child.is_alive():  # pragma: no cover
            child.kill()
            child.join()


##
# @brief A killed holder must not leave a lock that wedges the next build.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
@pytest.mark.integration
def test_a_killed_holder_leaves_no_stale_lock(tmp_path: Path) -> None:
    """WHY flock RATHER THAN AN O_EXCL LOCKFILE, proved rather than asserted. A lockfile needs a
    stale-lock story — a builder killed mid-run leaves the file, and every later process has to
    decide whether the holder still lives. Getting that wrong wedges a target permanently, which
    is exactly the class of failure this sequence of releases has been about.

    `flock` has no such story to get wrong: the kernel drops the lock when the descriptor closes,
    including on SIGKILL. So the next process acquires immediately.

    @brief SIGKILL releases the lock.
    @return None.
    @version 1
    """
    db = tmp_path / "clew.db"
    acquired = multiprocessing.Value("i", 0)
    child = multiprocessing.Process(target=_hold, args=(str(db), acquired, 60.0))
    child.start()
    try:
        for _ in range(100):
            if acquired.value:
                break
            time.sleep(0.05)
        assert acquired.value == 1, "the child never acquired the lock — test would be vacuous"

        child.kill()
        child.join(timeout=10)

        ## Immediately acquirable. A short wait proves it is not merely the bound expiring.
        started = time.monotonic()
        with build_lock(db, wait_seconds=30.0) as held:
            assert held is True, (
                "the lock was still unavailable after the holder was SIGKILLed — that is a stale "
                "lock, and it would wedge every later build of this target"
            )
        assert time.monotonic() - started < 5.0, "acquisition after a kill should be immediate"
    finally:
        if child.is_alive():  # pragma: no cover
            child.kill()
            child.join()


##
# @brief An unusable lock location must not stop a build.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_an_unwritable_location_proceeds_unlocked(tmp_path: Path) -> None:
    """FAILS OPEN. An unwritable state directory is a real deployment, and this component can only
    ever save a duplicate build — so it must degrade to "no lock" rather than to an error. Asserted
    by pointing at a path that cannot be created.

    @brief An unopenable lock path yields False rather than raising.
    @return None.
    @version 1
    """
    ## A REGULAR FILE WHERE A DIRECTORY MUST BE, rather than a chmod. The first version of this
    ## test made the OUTER directory read-only and still got the lock: traversal only needs +x, and
    ## the inner directory it actually wrote to was untouched. ENOTDIR needs no permission games and
    ## cannot be bypassed by running as root.
    obstacle = tmp_path / "not-a-dir"
    obstacle.write_text("", encoding="utf-8")

    with build_lock(obstacle / "clew.db") as held:
        assert held is False, (
            "an unusable lock location must report not-held rather than raise. This component can "
            "only ever save a duplicate build, so it must never be able to prevent one."
        )


##
# @brief The default wait is generous enough to earn a skip rather than force a duplicate.
# @return None.
# @version 1
def test_the_default_wait_is_a_backstop_not_a_budget() -> None:
    """The wait exists so the second process can SKIP after the first finishes; too short and it
    always duplicates, which is the waste this exists to remove. Measured builds: ~11 s on this
    repository, ~130 s on a 2,359-file C++ target. Pinned as an inequality rather than an exact
    value, so tuning is not a test failure.

    @brief The default wait exceeds a realistic build.
    @return None.
    @version 1
    """
    assert DEFAULT_WAIT_SECONDS >= 130, (
        f"a {DEFAULT_WAIT_SECONDS}s wait is shorter than a measured large-target build, so the "
        f"second process would give up and duplicate the work this lock exists to avoid"
    )
