# SPDX-License-Identifier: MIT
"""An abandoned doxygen run must not outlive the call that started it.

FIELD-OBSERVED, TWICE. Aborting a slow refresh returned "Successfully stopped task" while the
doxygen child kept running, still parented to the MCP server and holding multi-GB of resident
memory:

    406123  parent 173333  doxygen -
    458440  parent 173333  doxygen -   13:54 elapsed, 4.14 GB

Both had to be killed by hand. An operator who aborts a slow build a few times is silently
accumulating those, and the next attempt then competes with its own orphans for the machine —
which is how one of them got misread as a concurrency bug.

THIS SESSION'S OWN TIMEOUT PROBE HIT IT TOO, reporting "reaped 1 stub process" after abandoning
a call. That is the same defect observed from a third direction, and it is what makes this worth
a test rather than a one-line change.

WHY A PROCESS GROUP AND NOT `proc.kill()`. doxygen is spawned as `doxygen -`; killing that pid
does not reach anything it spawned, and the shape that actually leaked was the child surviving
its parent's teardown entirely. `start_new_session=True` makes the child a group leader, so one
`killpg` reaches it and everything under it, whatever the failure path was.

WHAT THE TEST DELIBERATELY DOES NOT ASSERT: that cancellation of an `anyio` task reaps the
child. `anyio.to_thread.run_sync` is not cancellable, so the worker thread runs on regardless
and the reap has to be reachable from the THREAD's own teardown — which is what is tested here,
by raising inside the call. Testing the cancellation path would test anyio, not clew.

@brief Tests that an aborted doxygen run leaves no surviving child.
@version 1
"""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

from clew import doxygen

## THE DURATION IS THE MARKER, and it has to be — which the first version of this test learned
## the hard way. An extra argv token (`sleep 3600 clew-reap-marker`) is not a label: `sleep`
## rejects the non-numeric argument and exits IMMEDIATELY, so there was never a survivor to find
## and the test passed in 0.34 s against completely unfixed code. A distinctive number is both
## valid to `sleep` and specific enough not to match another process on the machine.
_STUB_SLEEP = 3671


## @brief Write a doxygen stub that sleeps forever with a findable marker in its argv.
## @param tmp_path Directory for the stub and a minimal Doxyfile.
## @return The directory to prepend to PATH.
## @version 1
def _write_stub(tmp_path: Path) -> Path:
    """The stub leaves TWO processes — itself and a `sleep` child — and that is the point. With
    `exec` the stub IS the sleeper, so a plain `proc.kill()` would reap it and the test would
    pass without any process group, proving nothing about the field failure where the survivor
    outlived its parent. Without `exec`, only a group kill reaches both.

    @brief Build a long-sleeping doxygen stub.
    @return Directory containing the stub.
    @version 1
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / "doxygen"
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-g" ]; then echo "GENERATE_SQLITE3 = NO"; exit 0; fi\n'
        '[ "$1" = "--version" ] && { echo 1.9.8; exit 0; }\n'
        'echo "Parsing file /probe/a.c"\n'
        ## THE TRAILING `:` IS LOAD-BEARING. `dash` execs the FINAL command of a script, so a
        ## stub ending in `sleep N` becomes one process and a pid-only kill reaps it — the
        ## mutation control passed against exactly that, proving nothing. A command after the
        ## sleep forces the shell to stay alive as a real parent, which is the shape that leaked.
        f"sleep {_STUB_SLEEP}\n"
        ":\n"
    )
    stub.chmod(0o755)
    (tmp_path / "Doxyfile").write_text("PROJECT_NAME = probe\nINPUT = .\n")
    return stub_dir


## @brief Pids of every surviving process this test's stub is responsible for.
## @param stub_dir The unique per-test directory holding the stub.
## @return The matching pids.
## @version 2
def _survivors(stub_dir: Path) -> list[int]:
    """BOTH PATTERNS, BECAUSE THE STUB LEAVES TWO PROCESSES AND ONE IS EASY TO MISS. Matching
    only `sleep <duration>` finds the child and not the SHELL that spawned it — and the shell is
    the one holding the inherited stdout, which surfaced as the test harness hanging on its own
    output pipe rather than as a failed assertion. A leak check that sees half the leak reports a
    clean run while a process still holds a terminal open.

    The stub directory is under a per-test tmp path, so matching it cannot collide with anything
    else on the machine.

    @brief Find every leaked process belonging to this test.
    @return Their pids.
    @version 2
    """
    found: set[int] = set()
    for pattern in (f"sleep {_STUB_SLEEP}", str(stub_dir)):
        out = subprocess.run(["pgrep", "-f", pattern], capture_output=True, text=True).stdout
        found.update(int(p) for p in out.split() if p.isdigit())
    return sorted(found)


## @brief An exception during the run must not leave the child behind.
## @version 1
def test_an_aborted_doxygen_run_leaves_no_survivor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAILS BEFORE THE FIX with the stub still running. The abort is raised from inside the
    output reader, which is where a real abandonment lands: that loop is what the call is sitting
    in for the whole of a long doxygen run, so it is the realistic place for a cancellation, a
    KeyboardInterrupt, or any other unwind to arrive.

    `BaseException` rather than `Exception` on purpose — the interesting cases (KeyboardInterrupt,
    SystemExit, anyio's cancellation) are all outside `Exception`, and a `finally` that only
    survives `Exception` would leak on exactly the paths that matter.

    @brief An unwinding run reaps its child.
    @version 1
    """
    stub_dir = _write_stub(tmp_path)
    monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ['PATH']}")

    def _abort(*_args: object, **_kwargs: object) -> None:
        """WAITS FOR THE GRANDCHILD BEFORE ABORTING, and without that this test passes against
        completely unfixed code. Raising the instant the reader is entered kills the stub shell
        BEFORE it has forked its `sleep`, so there is nothing to leak and a pid-only kill looks
        indistinguishable from a process-group kill. Verified with a probe: the same stub leaks a
        `sleep` under `proc.kill()` when given a second to get there, and leaks nothing when
        killed immediately.

        That is the shape of a real abandonment too — the call is abandoned some way into a long
        doxygen run, not in the microsecond after spawn.
        """
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline and not _survivors(stub_dir):
            time.sleep(0.05)
        assert _survivors(stub_dir), "the stub never spawned; this test would be vacuous"
        raise KeyboardInterrupt("abandoned mid-run")

    monkeypatch.setattr(doxygen, "_consume_doxygen_output", _abort)

    try:
        with pytest.raises(BaseException):
            doxygen.run_doxygen(tmp_path / "Doxyfile", tmp_path, output_dir=tmp_path / "out")

        ## The child is killed asynchronously; give the kernel a moment to reap it before
        ## concluding it survived. A bare check here would be flaky in the passing direction,
        ## which is the worse direction for a leak test.
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline and _survivors(stub_dir):
            time.sleep(0.1)

        leaked = _survivors(stub_dir)
        assert not leaked, (
            f"doxygen child(ren) {leaked} survived an aborted run. In the field this accumulated "
            "multi-GB processes parented to the MCP server, which then competed with the next "
            "build attempt for the machine."
        )
    finally:
        ## Never leave a 3600 s sleeper behind, whatever the assertion did.
        for pid in _survivors(stub_dir):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
