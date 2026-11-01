# SPDX-License-Identifier: MIT
"""A doxygen failure costs the C/C++ layer, not the whole index — and says so.

THE DEFECT. `run_doxygen` ended a non-zero exit, a watchdog timeout and a missing database with
`sys.exit(1)`, and nothing on the build path caught it. So on a MIXED repository — a TypeScript
app carrying a little native code — one doxygen crash produced NO index, though every non-C
layer would have built: the TypeScript front end, the Python one, the prose, all discarded for
a layer that holds a handful of files.

AND THE FATAL VERSION IS THE ONE THAT LOOPS. A failed build never swaps its staged database in,
so the previous one stays older than its sources, the MCP server sees it as stale, and the
crashing build is retried on the next query and the next.

THE SKIP PATH ALREADY PROVED THE SHAPE. When no file in scope is one doxygen reads,
`_doxygen_stage` returns an empty doxygen-schema database and the rest of the build completes.
A failure now takes that same exit — but it is STAMPED `failed`, with the reason, because
"skipped, there was no C" and "failed, the C is missing" are opposite facts that must never look
alike. Before this, "skipped" was an INFO log line and nothing at all was recorded.

@brief Tests that a doxygen failure yields a stamped partial index.
@version 1
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

## The C++ allocation failure an over-wide scope actually produces.
_CRASH = "terminate called after throwing an instance of 'std::bad_alloc'"

_TS = b"export function greet(name: string): string {\n  return `hi ${name}`;\n}\n"


## @brief Write a file under a tree, creating directories.
## @param root Tree root.
## @param rel Relative path.
## @param text Contents.
## @return None.
## @version 1
def _write(root: Path, rel: str, text: bytes) -> None:
    """@brief Write one file.
    @return None.
    """
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text)


## @brief Put a doxygen on PATH that answers probes like the real one and crashes on a build.
## @param tmp_path Directory to hold the stub.
## @param monkeypatch Pytest monkeypatch fixture.
## @return None.
## @version 1
def _crashing_doxygen(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """`-g` AND `--version` ARE ANSWERED like the real binary, so the pipeline's own probes pass
    and the failure lands where a real crash does: in the run that reads the source.

    @brief Install a crashing doxygen stub.
    @return None.
    @version 1
    """
    stub_dir = tmp_path / "bin"
    stub_dir.mkdir()
    stub = stub_dir / "doxygen"
    stub.write_text(
        "#!/bin/sh\n"
        'if [ "$1" = "-g" ]; then echo "GENERATE_SQLITE3 = NO"; exit 0; fi\n'
        '[ "$1" = "--version" ] && { echo 1.9.8; exit 0; }\n'
        'echo "Parsing file native/add.c"\n'
        f'echo "{_CRASH}"\n'
        "exit 134\n"
    )
    stub.chmod(0o755)
    monkeypatch.setenv("PATH", f"{stub_dir}{os.pathsep}{os.environ['PATH']}")


## @brief Build an index and return a connection to it.
## @param repo Repository root.
## @param out Output database path.
## @return Connection.
## @version 1
def _build(repo: Path, out: Path) -> sqlite3.Connection:
    """@brief Run the build pipeline.
    @return Connection to the built database.
    """
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    return sqlite3.connect(out)


## @brief Read the build_meta table as a dict.
## @param conn Index connection.
## @return Key to value.
## @version 1
def _meta(conn: sqlite3.Connection) -> dict[str, str]:
    """@brief Read build_meta.
    @return Mapping.
    """
    return dict(conn.execute("SELECT key, value FROM build_meta"))


## @brief A mixed repo whose doxygen crashes still gets an index of everything else.
## @param tmp_path Pytest temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @return None.
## @version 1
def test_a_doxygen_crash_leaves_the_other_layers_indexed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief The TypeScript layer survives a doxygen crash.
    @return None.
    @version 1
    """
    _crashing_doxygen(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _write(repo, "native/add.c", b"int add(int a, int b) { return a + b; }\n")
    _write(repo, "src/app.ts", _TS)

    conn = _build(repo, tmp_path / "clew.db")

    names = {r[0] for r in conn.execute("SELECT name FROM memberdef WHERE kind='function'")}
    assert "greet" in names, f"the TypeScript layer was lost with the C one: {names}"


## @brief The partial index records that doxygen failed, and why.
## @param tmp_path Pytest temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @return None.
## @version 1
def test_a_doxygen_crash_is_stamped_as_failed_with_its_reason(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A PARTIAL INDEX THAT DOES NOT SAY SO IS WORSE THAN NONE. Without the stamp, "no such C
    function" from this index reads as a measured negative when the C layer never ran — the
    exact failure `absence is not emptiness` names.

    @brief The failure is a recorded fact, not a log line.
    @return None.
    @version 1
    """
    _crashing_doxygen(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _write(repo, "native/add.c", b"int add(int a, int b) { return a + b; }\n")
    _write(repo, "src/app.ts", _TS)

    meta = _meta(_build(repo, tmp_path / "clew.db"))

    assert meta.get("diagnostics.doxygen") == "failed", f"not stamped as failed: {meta}"
    assert "134" in meta.get("diagnostics.doxygen_reason", ""), f"no reason recorded: {meta}"


## @brief A repo with nothing doxygen reads is stamped skipped, never failed.
## @param tmp_path Pytest temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @return None.
## @version 1
def test_a_repo_with_no_c_is_stamped_skipped_not_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE OPPOSITE FACT, AND IT MUST NOT LOOK THE SAME. A TypeScript-only repo has no C to
    miss. Its index is complete, and stamping it `failed` — or leaving both unstamped — would
    make a reader distrust a whole index that is fine.

    @brief Skipped is its own recorded state.
    @return None.
    @version 1
    """
    _crashing_doxygen(tmp_path, monkeypatch)
    repo = tmp_path / "repo"
    _write(repo, "src/app.ts", _TS)

    meta = _meta(_build(repo, tmp_path / "clew.db"))

    assert meta.get("diagnostics.doxygen") == "skipped", f"not stamped as skipped: {meta}"
    assert "diagnostics.doxygen_reason" not in meta, f"a skip carries no failure reason: {meta}"
