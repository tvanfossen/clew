# SPDX-License-Identifier: MIT
"""The doxygen timeout must be reachable while the child is still alive.

THE DEFECT THIS PINS SHIPPED LOOKING CORRECT. `run_doxygen` read the child's output and then
called `proc.wait(timeout=_DOXYGEN_TIMEOUT)`. Every reviewer sees a bounded wait; there isn't
one. The read is `for raw in proc.stdout`, which blocks until the child closes the pipe, so on a
doxygen that is still running — working OR wedged — the line carrying the timeout is never
reached and the bound cannot be evaluated. In the field this was six consecutive builds of one
target, every one ended by a human or a client timeout, none by clew.

THE TWO VARIANTS ARE THE TEST. A single "does it hang" case cannot distinguish a working
watchdog from a stub that happened to exit:

  * `open`   — the stub emits a line and sleeps with its pipe OPEN, which is what a live doxygen
               looks like. The timeout must fire anyway. This is the case that failed before.
  * `closed` — the stub closes BOTH fds and then sleeps, so the read loop takes EOF on its own.
               The timeout must still fire, proving the bound is on the process and not an
               artifact of how the reader ended.

BOTH FDS, AND THAT IS NOT PEDANTRY. `run_doxygen` spawns with `stderr=subprocess.STDOUT`, so one
pipe has two write descriptors. The first version of the `closed` control closed only stdout and
hung exactly like `open` — which briefly read as the mechanism being broken when the control was.

BOUNDED ON BOTH SIDES. The call runs on a thread joined with a deadline, so a regression makes
this test FAIL rather than hang the suite; and every stub descendant is reaped in a finally,
because a leaked `sleep 3600` per run is how a test suite quietly fills a machine.

@brief Tests that the doxygen watchdog fires while the child holds its pipe open.
@version 1
"""

from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

import pytest

from clew import doxygen

## Long enough that the stub is unambiguously "still running" rather than racing the deadline.
_STUB_SLEEP = 3600

## The patched timeout. Small so the test is quick; the ratio to `_OUTER_DEADLINE` is what makes
## a failure unambiguous rather than a slow machine.
_INNER_TIMEOUT = 3.0

## How long the test waits for the call to return. ~7x the timeout, so an ordinary scheduling
## delay cannot fail this while a genuinely unreachable timeout always does.
_OUTER_DEADLINE = 20.0


## @brief Write a fake doxygen that emits a line, optionally closes its fds, then sleeps forever.
## @param tmp_path Directory to build the stub and a minimal Doxyfile in.
## @param close_fds Whether the stub closes stdout AND stderr before sleeping.
## @return The directory to prepend to PATH.
## @version 1
def _write_stub(tmp_path: Path, close_fds: bool) -> Path:
    """`exec sleep` REPLACES the shell, so the process the watchdog kills is the one holding the
    pipe — with a surviving shell in between, `proc.kill()` would leave the real holder alive and
    the test would pass for the wrong reason.

    @brief Build the doxygen stub.
    @return Directory containing the stub.
    @version 1
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / "doxygen"
    ## BOTH descriptors: `run_doxygen` merges stderr into stdout, so closing one leaves the pipe
    ## open through the other and the reader never sees EOF.
    close = "exec 1>&- 2>&-\n" if close_fds else ""
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-g" ]; then echo "GENERATE_SQLITE3 = NO"; exit 0; fi\n'
        '[ "$1" = "--version" ] && { echo 1.9.8; exit 0; }\n'
        'echo "Parsing file /probe/a.c"\n'
        f"{close}"
        f"exec sleep {_STUB_SLEEP}\n"
    )
    stub.chmod(0o755)
    (tmp_path / "Doxyfile").write_text("PROJECT_NAME = probe\nINPUT = .\n")
    return stub_dir


## @brief Kill any surviving stub descendant.
## @return Number of processes reaped.
## @version 1
def _reap() -> int:
    """@brief Reap leaked stub sleepers.
    @return How many were killed.
    @version 1
    """
    found = subprocess.run(
        ["pgrep", "-f", f"sleep {_STUB_SLEEP}"], capture_output=True, text=True
    ).stdout.split()
    for pid in found:
        try:
            os.kill(int(pid), signal.SIGKILL)
        except (ProcessLookupError, ValueError, PermissionError):
            pass
    return len(found)


@pytest.mark.parametrize("close_fds", [False, True], ids=["pipe-held-open", "fds-closed"])
def test_the_doxygen_timeout_fires_while_the_child_lives(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, close_fds: bool
) -> None:
    """`pipe-held-open` IS THE REGRESSION CASE and it failed before the watchdog: the call was
    still running at 20 s against a 3 s bound, because the blocking read sat upstream of the
    timeout. `fds-closed` passed even then, which is exactly why both are here — one of them
    alone would have called this fixed.

    `SystemExit` is the pass condition, not an accident: `run_doxygen` reports the timeout and
    exits non-zero, and asserting the EXIT distinguishes "the watchdog fired" from "the stub
    happened to end".

    @brief The watchdog bounds a live child.
    @version 1
    """
    stub_dir = _write_stub(tmp_path, close_fds)
    monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setattr(doxygen, "_DOXYGEN_TIMEOUT", _INNER_TIMEOUT)

    box: dict[str, BaseException] = {}

    def _call() -> None:
        try:
            doxygen.run_doxygen(tmp_path / "Doxyfile", tmp_path, output_dir=tmp_path / "out")
        except BaseException as exc:  # SystemExit is the expected outcome
            box["exc"] = exc

    thread = threading.Thread(target=_call, daemon=True)
    started = time.monotonic()
    thread.start()
    try:
        thread.join(timeout=_OUTER_DEADLINE)
        elapsed = time.monotonic() - started
        assert not thread.is_alive(), (
            f"run_doxygen was still running after {elapsed:.0f} s against a "
            f"{_INNER_TIMEOUT} s timeout — the bound is unreachable, which is the whole defect: "
            "the blocking read of the child's output sits upstream of the wait that carries it"
        )
        assert isinstance(box.get("exc"), SystemExit), (
            f"expected the timeout path to exit; got {box.get('exc')!r}"
        )
    finally:
        _reap()
