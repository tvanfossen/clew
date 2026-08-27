# SPDX-License-Identifier: MIT
"""A cross-process advisory lock over one target's build.

WHAT IT IS FOR. `mcp_server/server.py` deduplicates concurrent refreshes with an `anyio.Lock`,
which is per PROCESS — and one `clew-mcp` runs per client session PLUS one per subagent, measured.
So two sessions sharing a target performed two full redundant builds where the design intended one
build and one skip. That is ~11 s wasted on this repository and ~130 s on a 2,359-file C++ target,
plus the shared doxygen scratch directory and sidecar written twice.

**IT IS AN OPTIMISATION, NOT A CORRECTNESS MECHANISM, AND THAT DECIDES EVERY DESIGN CHOICE HERE.**
Since 1.0.12 each build stages into `<output>.<pid>.tmp` and swaps with `os.replace`, so two
concurrent builds are already SAFE — the last writer wins with a complete index either way. This
only stops the waste. Which means: when anything about the lock is uncertain, the right answer is
always to build, never to wait and never to fail.

**flock, NOT A LOCKFILE, AND THAT IS THE WHOLE REASON THIS IS SAFE TO SHIP.** An `O_EXCL` lockfile
needs a stale-lock story: a builder killed mid-run leaves the file behind, and every later process
must decide whether the holder is alive. Get that wrong and a dead build wedges the target forever
— which is precisely the class of failure the three releases before this one were about. `flock` has
no such story to get wrong: the kernel drops the lock when the file descriptor closes, including on
SIGKILL, so a stale lock cannot exist.

**EVERY WAIT IS BOUNDED AND EVERY FAILURE OPENS.** `fcntl` is absent on Windows; a filesystem may
not support locking; the state directory may be unwritable. Each of those returns a no-op guard
that lets the build proceed. A component that can only ever cost a duplicate build must not be
able to block one.

@brief Cross-process advisory locking for a target's build.
@version 1
"""

from __future__ import annotations

import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from ._common import logger

## Suffix for the lock file, beside the database it guards. A SEPARATE FILE rather than the
## database itself: locking the db would contend with readers, and readers are explicitly never
## blocked by a build — they hold the old inode until the atomic swap.
LOCK_SUFFIX = ".buildlock"

## How long to wait for another process's build before giving up and building anyway. A BACKSTOP,
## not a budget: the point of waiting at all is that the other build usually finishes and this
## process can skip, and the point of the bound is that a pathological build cannot stall this one.
DEFAULT_WAIT_SECONDS = 180.0

## Polling interval while waiting. `flock` can block natively, but a bounded blocking wait needs
## either SIGALRM (not thread-safe, and this runs on an anyio worker thread) or a poll. Polling is
## the boring choice that works on a worker thread.
_POLL_SECONDS = 0.25


##
# @brief Path of the lock file guarding one target's build.
# @param output The database the build will write.
# @return Sibling lock path.
# @version 1
# @utility
def lock_path(output: Path) -> Path:
    """A sibling of the database, so it lands in a directory that already exists before any build
    (created by `TargetRegistry.register` or by the pipeline itself) and travels with the target
    rather than living in a global namespace someone has to clean up.

    @brief Derive the lock path.
    @return The lock file path.
    @version 1
    """
    return output.with_name(output.name + LOCK_SUFFIX)


##
# @brief Hold an exclusive cross-process lock on one target's build, or report not holding it.
# @param output The database the build will write.
# @param wait_seconds How long to wait for another builder before proceeding regardless.
# @return Yields True when this process holds the lock, False when it is proceeding unlocked.
# @version 1
# @req REQ-DDB-INDEX-002
@contextmanager
def build_lock(output: Path, wait_seconds: float = DEFAULT_WAIT_SECONDS) -> Iterator[bool]:
    """YIELDS A BOOLEAN RATHER THAN RAISING, so the caller decides what a contended target means.
    The MCP server re-checks freshness and skips; the CLI builds regardless. Neither can be
    blocked by this.

    `False` means "another process is building, or locking is unavailable here" — never "give up".
    A caller that treats False as a failure would reintroduce the hang this design avoids.

    THE WAIT EXISTS TO EARN A SKIP, and that is its only purpose. If the other builder finishes
    inside the bound, this process re-checks and finds the index current, which is the whole win.
    If it does not, this process builds too — wasteful, and still correct, because staging paths
    are per-process and the swap is atomic.

    @brief Acquire the cross-process build lock if possible.
    @return Yields whether the lock is held.
    @version 1
    """
    try:
        import fcntl
    except ImportError:  # pragma: no cover - Windows
        ## No advisory locking here. Proceed unlocked: a duplicate build is the cost, and it is
        ## the same cost this module exists to reduce rather than to guarantee away.
        logger.debug("build lock: fcntl unavailable — proceeding without a cross-process lock")
        yield False
        return

    path = lock_path(output)
    fd = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(str(path), os.O_CREAT | os.O_WRONLY, 0o644)
    except OSError as exc:
        ## An unwritable state directory is a real deployment, and it must not stop a build.
        logger.debug("build lock: cannot open %s (%s) — proceeding unlocked", path, exc)
        if fd is not None:
            os.close(fd)
        yield False
        return

    held = False
    try:
        deadline = time.monotonic() + max(0.0, wait_seconds)
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                held = True
                break
            except OSError:
                ## Held by another process. Wait for it, so this process can skip rather than
                ## duplicate — but only up to the bound.
                if time.monotonic() >= deadline:
                    logger.info(
                        "build lock: another process has been building %s for over %.0f s — "
                        "building anyway rather than waiting longer. Both builds are safe: "
                        "staging paths are per-process and the swap is atomic.",
                        output.name,
                        wait_seconds,
                    )
                    break
                time.sleep(_POLL_SECONDS)
        yield held
    finally:
        ## The kernel would release on close regardless; unlocking explicitly makes the intent
        ## legible and releases a fraction earlier.
        if held:
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except OSError:  # pragma: no cover - already gone
                pass
        try:
            os.close(fd)
        except OSError:  # pragma: no cover
            pass
