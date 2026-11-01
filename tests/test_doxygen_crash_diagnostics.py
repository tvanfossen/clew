# SPDX-License-Identifier: MIT
"""A doxygen that crashes must leave the user something to act on.

THE DEFECT. `_consume_doxygen_output` buckets every line as warning, file, phase or OTHER, and
keeps only a warning count, the first three warning lines, and a running file count. Everything
classified OTHER is discarded as it streams past. A crash is always OTHER — `terminate called
after throwing`, `Segmentation fault`, an assertion — so the one line that says what happened was
the one line guaranteed not to survive. The failure branch then logged, in full:

    Doxygen exited with code 134

and exited. No cause, no input size, no hint that an over-wide scope is the usual reason. The
file count WAS being computed for the progress bar and was thrown away with the rest.

A TIMEOUT IS ALREADY HANDLED WELL, and is the model here: `run_doxygen` keeps a flag so a
watchdog kill is not mistaken for a crash, and says what happened and that the previous index
is untouched. A crash deserved the same, and got one line.

THE STUB CRASHES ON PURPOSE AND EXITS 134, the status a C++ `abort()` produces. It follows
`tests/test_doxygen_timeout.py`: a shell script on PATH answering `-g` and `--version` the way
the real binary does, so `run_doxygen` reaches the spawn.

@brief Tests that a doxygen crash is reported with its cause and input size.
@version 1
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pytest

from clew import doxygen

## The crash text a C++ allocation failure prints. Chosen because it is what an over-wide scope
## actually produces: doxygen runs out of memory on a tree nobody meant to hand it.
_CRASH = "terminate called after throwing an instance of 'std::bad_alloc'"

## Files the stub claims to parse before dying. Distinct from the line count on purpose, since
## real doxygen prints a `Preprocessing` AND a `Parsing file` line per file.
_PARSED = 3


## @brief Write a fake doxygen that parses a few files and then aborts.
## @param tmp_path Directory to build the stub and a minimal Doxyfile in.
## @return The directory to prepend to PATH.
## @version 1
def _write_crashing_stub(tmp_path: Path) -> Path:
    """BOTH PREFIXES PER FILE, like the real binary, so a diagnostic that counted every
    file-shaped line would report double and this test would catch it.

    @brief Build the crashing doxygen stub.
    @return Directory containing the stub.
    @version 1
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir(parents=True, exist_ok=True)
    stub = stub_dir / "doxygen"
    parsed = "".join(
        f'echo "Preprocessing /probe/f{i}.c"\necho "Parsing file /probe/f{i}.c"\n'
        for i in range(_PARSED)
    )
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-g" ]; then echo "GENERATE_SQLITE3 = NO"; exit 0; fi\n'
        '[ "$1" = "--version" ] && { echo 1.9.8; exit 0; }\n'
        f"{parsed}"
        f'echo "{_CRASH}"\n'
        'echo "  what():  std::bad_alloc"\n'
        "exit 134\n"
    )
    stub.chmod(0o755)
    (tmp_path / "Doxyfile").write_text("PROJECT_NAME = probe\nINPUT = .\n")
    return stub_dir


## @brief Run the crashing stub and return the error log it produced.
## @param tmp_path Pytest temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @param caplog Pytest log capture fixture.
## @return Every ERROR-level message joined.
## @version 1
def _crash_log(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> str:
    """@brief Drive run_doxygen into the crash branch.
    @return Error text.
    @version 1
    """
    stub_dir = _write_crashing_stub(tmp_path)
    monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ['PATH']}")
    with caplog.at_level(logging.ERROR), pytest.raises(SystemExit):
        doxygen.run_doxygen(tmp_path / "Doxyfile", tmp_path, output_dir=tmp_path / "out")
    return "\n".join(r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)


## @brief The crash message itself reaches the user.
## @return None.
## @version 1
def test_a_doxygen_crash_reports_what_doxygen_said(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """@brief The line saying what went wrong is not discarded.
    @return None.
    @version 1
    """
    errors = _crash_log(tmp_path, monkeypatch, caplog)
    assert _CRASH in errors, f"the crash message was discarded; the user saw only: {errors!r}"


## @brief The crash report says how much doxygen was given.
## @return None.
## @version 1
def test_a_doxygen_crash_reports_how_many_files_it_parsed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """THE INPUT SIZE IS THE USUAL CAUSE. A doxygen that dies on a tree nobody meant to hand it
    is the common case, and "it got through N files" is what tells the reader to check scope
    rather than file a doxygen bug. Counted from `Parsing file` lines ONLY, because the binary
    prints two lines per file and a doubled count would point the reader at the wrong size.

    @brief The parsed-file count is in the error.
    @return None.
    @version 1
    """
    errors = _crash_log(tmp_path, monkeypatch, caplog)
    assert f"{_PARSED} file" in errors, f"no input size in the crash report: {errors!r}"
    assert f"{_PARSED * 2} file" not in errors, f"the file count was doubled: {errors!r}"


## @brief A crash is not reported as a timeout, and vice versa.
## @return None.
## @version 1
def test_a_doxygen_crash_is_not_reported_as_a_timeout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """@brief The crash branch keeps its own wording.
    @return None.
    @version 1
    """
    errors = _crash_log(tmp_path, monkeypatch, caplog)
    assert "did not finish" not in errors, f"a crash was reported as a timeout: {errors!r}"
    assert "134" in errors, f"the exit status was lost: {errors!r}"
