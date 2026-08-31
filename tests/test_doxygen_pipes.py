# SPDX-License-Identifier: MIT
"""The doxygen spawn must service both pipes at once, and must not wait forever.

FIELD-OBSERVED, 2026-08-26: a single MCP call hung indefinitely with no concurrency involved. The
cause was a textbook pipe deadlock in the doxygen spawn — the config was written to stdin in full
BEFORE anything read stdout, so once both ~64 KiB pipe buffers filled, neither side could proceed.

THE CONFIG IS NOT SMALL, WHICH IS WHY THIS IS REACHABLE RATHER THAN THEORETICAL. clew writes
explicit file lists into `INPUT`, so config size scales with the repository: measured 356,077 bytes
for a 4,878-file input against a 65,536-byte buffer, and doxygen emits config-parse warnings while
it is still reading. That is the deadlock, and it is why a big target hung where a small one did
not.

These tests are STRUCTURAL where they can be, because the behavioural version needs a real
multi-hundred-KB doxygen run to reproduce and would be slow and flaky. The shape — a writer that
runs concurrently with the reader, and a bounded wait — is what must not regress.

@brief Tests for deadlock-freedom and boundedness of the doxygen subprocess.
@version 1
"""

from __future__ import annotations

import ast
import subprocess
import sys
import threading
from pathlib import Path

from clew import doxygen as dox
from clew.doxygen import _write_doxyfile_stdin

REPO = Path(__file__).resolve().parent.parent
DOX_SOURCE = REPO / "clew" / "doxygen.py"


##
# @brief The generated config really is larger than a pipe buffer.
# @param tmp_path Pytest temp dir.
# @return None.
# @version 1
def test_the_generated_config_exceeds_a_pipe_buffer(tmp_path: Path) -> None:
    """THE PREMISE OF THE WHOLE BUG, PINNED. If the config were always small the write-then-read
    ordering would have been harmless, and someone reading the fix later would reasonably ask why
    the extra thread exists. It exists because this number is bigger than 64 KiB.

    Asserted as an inequality against the buffer size rather than as an exact byte count, which
    would be a brittle restatement of the template.

    @brief A realistic INPUT list produces a config larger than 64 KiB.
    @return None.
    @version 1
    """
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text("PROJECT_NAME = t\nINPUT =\n", encoding="utf-8")
    ## Representative of a mid-size repo; clew lists every indexed file explicitly.
    files = [str(tmp_path / f"src/mod_{i}/file_{i}.c") for i in range(4000)]

    content = dox._build_doxyfile_content(doxyfile, files, [], True, tmp_path / "out", "")

    assert len(content) > 65536, (
        f"the generated config is only {len(content)} bytes, so this test no longer demonstrates "
        f"the condition the writer thread exists for. If INPUT stopped being written explicitly, "
        f"re-justify the thread rather than deleting this test."
    )


##
# @brief stdin must be written concurrently with reading stdout, not before it.
# @return None.
# @version 1
def test_stdin_is_written_concurrently_with_reading_stdout() -> None:
    """THE DEADLOCK FIX, ASSERTED STRUCTURALLY. The failing shape is a sequence:

        proc.stdin.write(config)      # blocks once the buffer fills
        proc.stdin.close()
        _consume_doxygen_output(proc)  # nobody was reading until now

    So the property is that the write does NOT happen inline in `run_doxygen` — it must be handed
    to a thread (or `communicate`, which this codebase rejects because it buffers away the live
    progress bar). Checked over the AST: no direct `proc.stdin.write` inside `run_doxygen`, and a
    `threading.Thread` started before the reader.

    A behavioural test would need a real 356 KB doxygen run; this pins the shape instead, which is
    what a future edit would actually break.

    @brief The config write is off the main thread and precedes the read.
    @return None.
    @version 1
    """
    tree = ast.parse(DOX_SOURCE.read_text(encoding="utf-8"))
    run = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_doxygen"
    )

    ## No inline stdin write: that is the deadlock, spelled exactly.
    inline_writes = [
        n
        for n in ast.walk(run)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "write"
        and isinstance(n.func.value, ast.Attribute)
        and n.func.value.attr == "stdin"
    ]
    assert not inline_writes, (
        "run_doxygen writes to proc.stdin inline. That is the deadlock: nothing reads stdout "
        "until the whole config is written, and both pipes are ~64 KiB while the config is "
        "measured at 356 KB."
    )

    ## And the writer must actually be started, before the reader consumes stdout.
    starts = [
        n.lineno
        for n in ast.walk(run)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "start"
    ]
    reads = [
        n.lineno
        for n in ast.walk(run)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_consume_doxygen_output"
    ]
    assert starts, "no thread is started in run_doxygen — the config write is not concurrent"
    assert reads, "run_doxygen no longer reads stdout — this test would be vacuous"
    assert min(starts) < min(reads), (
        "the writer thread must start BEFORE stdout is consumed, or the reader blocks with an "
        "unwritten config still queued"
    )


##
# @brief The bound on doxygen is a watchdog, started before the blocking read.
# @return None.
# @version 2
def test_the_bound_on_doxygen_starts_before_the_read() -> None:
    """THIS TEST USED TO ASSERT THE DEFECT AND CALL IT A BOUND, which is the reason its
    replacement is written the way it is.

    The old version walked `run_doxygen` for a `proc.wait(...)` carrying a `timeout=` keyword and
    passed the entire time the timeout was UNREACHABLE. The call really did have the argument;
    what it did not have was a way to be evaluated, because `_consume_doxygen_output` blocks on
    `for raw in proc.stdout` until the child closes the pipe, and a live doxygen never does. So a
    structural check on the SHAPE of a call said "bounded" while six consecutive builds of a real
    target ran until a human killed them.

    THE LESSON, AND WHY THE SPLIT: reachability cannot be asserted from the AST. Only driving the
    thing proves it, and that is `tests/test_doxygen_timeout.py`, whose `pipe-held-open` case
    fails against the old code and passes against this one. What is still worth pinning here is
    the ORDERING that made the old arrangement wrong — the bound must be armed BEFORE the read
    that can block, which is a property the AST can see and a reader can get wrong again.

    The timeout VALUE is deliberately not asserted: it is a backstop, not a budget.

    @brief A timer arms the bound before stdout is consumed.
    @return None.
    @version 2
    """
    tree = ast.parse(DOX_SOURCE.read_text(encoding="utf-8"))
    run = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "run_doxygen"
    )

    ## A `threading.Timer(...)` constructed with the timeout constant is the only thing that can
    ## interrupt a blocked read; `proc.wait(timeout=)` demonstrably cannot.
    timers = [
        n
        for n in ast.walk(run)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "Timer"
        and any(isinstance(a, ast.Name) and a.id == "_DOXYGEN_TIMEOUT" for a in n.args)
    ]
    assert timers, (
        "run_doxygen has no threading.Timer armed with _DOXYGEN_TIMEOUT. A timeout passed to "
        "proc.wait() is NOT a bound here: the read loop upstream of it blocks until the child "
        "closes its pipe, so the wait is never reached while doxygen is alive."
    )

    ## The ordering that was the defect: arming after the blocking read bounds nothing.
    starts = [
        n.lineno
        for n in ast.walk(run)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "start"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "watchdog"
    ]
    reads = [
        n.lineno
        for n in ast.walk(run)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_consume_doxygen_output"
    ]
    assert starts, "the watchdog is never started"
    assert reads, "run_doxygen no longer reads stdout — this test would be vacuous"
    assert min(starts) < min(reads), (
        "the watchdog must be armed BEFORE the blocking read of doxygen's output. Armed after, "
        "it is exactly the unreachable bound this replaced."
    )

    ## A bound that does not kill the child leaks a process and leaves the pipes open — and the
    ## kill is also what UNBLOCKS the reader, by closing the fds it is waiting on.
    ##
    ## MATCHED ON THE REAP HELPER, NOT ON `.kill`. The literal `proc.kill()` that used to sit
    ## here moved into `_reap_process_group` when the reap became a process-group kill (#499b),
    ## and a `.kill`-shaped check would have failed on a change that made the reaping STRONGER.
    ## That is the same mistake as the assertion this test replaced: pinning a spelling rather
    ## than the property.
    reapers = [
        n
        for n in ast.walk(run)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id == "_reap_process_group"
    ]
    assert reapers, (
        "the timeout path must reap the child rather than leaking it. `proc.kill()` alone is "
        "not sufficient — it reaches the pid we hold and nothing that pid spawned."
    )


##
# @brief The real deadlock condition, reproduced against the fixed spawn shape.
# @return None.
# @version 1
def test_the_spawn_shape_survives_an_oversized_config() -> None:
    """THE BEHAVIOURAL PROOF, WITHOUT NEEDING doxygen. A stand-in child reproduces the exact
    condition: it writes far more than a pipe buffer to stdout while its stdin is still being
    filled. Under the old ordering this hung until killed — verified, exit 124. Under the writer
    thread it completes.

    This is the closest a fast test gets to the field failure, and it needs no doxygen binary, so
    it runs everywhere.

    @brief A writer thread survives what the inline write deadlocked on.
    @return None.
    @version 1
    """
    child = (
        "import sys\n"
        "for i in range(20000): sys.stdout.write('warning: noisy %d\\n' % i)\n"
        "sys.stdout.flush()\n"
        "sys.stdin.read()\n"
    )
    proc = subprocess.Popen(
        [sys.executable, "-c", child],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    ## The production shape: hand the write to a thread, then read.
    writer = threading.Thread(target=_write_doxyfile_stdin, args=(proc, "X" * 500_000), daemon=True)
    writer.start()
    consumed = 0
    assert proc.stdout is not None
    for _ in proc.stdout:
        consumed += 1
    rc = proc.wait(timeout=30)
    writer.join(timeout=5)

    assert rc == 0, f"the child failed: {rc}"
    assert consumed > 19000, f"only {consumed} lines read — the reader did not drain stdout"
    assert not writer.is_alive(), "the writer thread did not finish"
