# SPDX-License-Identifier: MIT
"""Tests for cell execution and the artifacts it freezes.

No agent runs: `subprocess.run` is replaced, because what matters here is what the code does
with an envelope, not that `claude -p` works.

@brief Tests for acceptance.execute.
@version 1
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import execute
from acceptance.runner import Cell

CELL = Cell("owner/repo", "Q1", "baseline", "sonnet", 1, 0)
INDEX_CELL = Cell("owner/repo", "Q1", "index", "sonnet", 1, 1)


## @brief Build a fake completed subprocess carrying an envelope.
## @param envelope What the runner would have printed.
## @param rc Return code.
## @return A callable standing in for subprocess.run.
## @version 1
def _fake_run(envelope: dict, rc: int = 0):
    """@brief Stand in for the runner subprocess.
    @return Callable.
    @version 1
    """

    def run(argv, **_kwargs):
        return subprocess.CompletedProcess(argv, rc, json.dumps(envelope), "boom" if rc else "")

    return run


## @brief The index arm refuses to run without an MCP config.
## @return None.
## @version 1
def test_index_arm_without_mcp_config_is_refused(tmp_path: Path) -> None:
    """An index arm that quietly ran WITHOUT its index would produce a full set of plausible
    answers and a publishable-looking number, and nothing downstream could tell. This is the one
    failure that has to be impossible rather than merely detectable.

    @brief Index arm needs its index.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="needs an MCP config"):
        execute.run_cell(INDEX_CELL, "q?", tmp_path, tmp_path / "out")


## @brief A successful cell writes prose, metadata and the raw envelope.
## @return None.
## @version 1
def test_successful_cell_freezes_three_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief Artifacts are written and metadata carries the argv.
    @return None.
    @version 1
    """
    envelope = {
        "result": "The threading macros are commented out.",
        "usage": {"output_tokens": 4321, "cache_read_input_tokens": 99},
        "num_turns": 5,
        "session_id": "no-such-session",
    }
    monkeypatch.setattr(subprocess, "run", _fake_run(envelope))
    out = tmp_path / "out"
    result = execute.run_cell(CELL, "What runs?", tmp_path, out)

    assert result.ok and result.output_tokens == 4321 and result.turns == 5
    assert result.cache_read_tokens == 99, "cached prefix is recorded separately, never blended"
    assert result.result_bytes == len(envelope["result"].encode())
    assert (result.tool_calls, result.non_index_tool_calls) == (-1, -1), (
        "an unreadable transcript reports UNKNOWN, never zero"
    )
    assert (out / "Q1_sonnet_baseline_r1.md").read_text() == envelope["result"]
    meta = json.loads((out / "Q1_sonnet_baseline_r1.meta.json").read_text())
    assert meta["argv"][0] == "claude", (
        "the argv is recorded, or nothing settles which repo answered"
    )
    assert (out / "Q1_sonnet_baseline_r1.raw.json").is_file()


## @brief A failed cell writes no answer file.
## @return None.
## @version 1
def test_failed_cell_writes_no_answer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AN EMPTY ANSWER AND A FAILED CELL ARE DIFFERENT STATES. Writing an empty `.md` would let
    grading read a transport failure as an agent that said nothing, which scores it against the
    arm instead of against the infrastructure.

    @brief No answer file on failure.
    @return None.
    @version 1
    """
    monkeypatch.setattr(subprocess, "run", _fake_run({}, rc=2))
    out = tmp_path / "out"
    result = execute.run_cell(CELL, "q?", tmp_path, out)
    assert not result.ok and "rc=2" in result.error
    assert not (out / "Q1_sonnet_baseline_r1.md").exists()


## @brief An empty answer is a failure, not a zero-length success.
## @return None.
## @version 1
def test_blank_answer_is_not_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief Blank prose fails the cell.
    @return None.
    @version 1
    """
    monkeypatch.setattr(subprocess, "run", _fake_run({"result": "   "}))
    result = execute.run_cell(CELL, "q?", tmp_path, tmp_path / "out")
    assert not result.ok
    assert not (tmp_path / "out" / "Q1_sonnet_baseline_r1.md").exists()


## @brief Unknown tool use reports -1, never 0.
## @return None.
## @version 1
def test_unknown_tool_use_is_minus_one_not_zero() -> None:
    """0 READS AS "USED NO TOOLS", which is the best possible result on the axis under test. A
    cell whose tool use could not be determined must not be indistinguishable from the ideal.

    @brief Unknown is not zero.
    @return None.
    @version 1
    """
    assert execute.count_tools({}, None, Path("/nowhere")) == (-1, -1)
    assert execute.count_tools({}, "absent-session", Path("/nowhere")) == (-1, -1)


## @brief The baseline arm keeps its full tool repertoire.
## @return None.
## @version 1
def test_baseline_arm_is_not_fenced_to_one_command() -> None:
    """The comparison is a default agentic harness WITH the index against the same harness
    WITHOUT it. Fencing the baseline to grep would measure a strawman, and a full file read
    fails the same way a search does.

    @brief Baseline keeps Read, Grep, Glob and Bash.
    @return None.
    @version 1
    """
    baseline = execute._ALLOWED["baseline"].split(",")
    assert set(baseline) == {"Read", "Grep", "Glob", "Bash"}
    index = execute._ALLOWED["index"].split(",")
    assert set(baseline) < set(index), "the index arm is the baseline arm PLUS the index"
    assert not [t for t in baseline if t.startswith("mcp__")]
