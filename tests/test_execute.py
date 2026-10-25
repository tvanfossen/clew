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


## @brief An index cell that never touched the index is flagged.
## @return None.
## @version 1
def test_index_cell_with_no_index_calls_is_flagged() -> None:
    """THE ONLY DOWNSTREAM SIGNAL that the index arm ran WITHOUT its index. Measured: a relative
    --repo in the MCP config resolved inside the target checkout, the server started, found no
    database, registered no query tools, raised no error, and the run reported 4/4 ok.

    UNKNOWN IS NOT ZERO. A cell whose tool use could not be determined (-1) must not be flagged,
    or the alarm fires on a missing transcript and stops meaning anything.

    @brief Zero-index-call cells are reported.
    @return None.
    @version 1
    """
    from acceptance.execute import CellResult, index_cells_that_never_used_the_index

    rows = [
        CellResult("blind", "index", "m", True, tool_calls=8, non_index_tool_calls=8),
        CellResult("used", "index", "m", True, tool_calls=8, non_index_tool_calls=5),
        CellResult("baseline", "baseline", "m", True, tool_calls=8, non_index_tool_calls=8),
        CellResult("unknown", "index", "m", True, tool_calls=-1, non_index_tool_calls=-1),
        CellResult("failed", "index", "m", False, tool_calls=0, non_index_tool_calls=0),
    ]
    assert index_cells_that_never_used_the_index(rows) == ["blind"]


## @brief The blindness check covers the arm the 1.1.0 grid actually runs.
## @return None.
## @version 1
def test_an_index_only_cell_that_called_nothing_is_reported_as_blind():
    """THE ARM NAMED LITERALLY WAS THE WRONG ARM. `ARMS` is ("baseline", "index_only"), so a
    check written against "index" alone watched the arm the grid does not run — the same defect
    `runner.check_symmetry` already carries a comment about, which named its two arms literally
    and kept comparing the OLD pair after the compared arms changed.

    IT MATTERS MORE HERE THAN FOR THE BLENDED ARM. `index_only` is granted no Read, Grep, Glob or
    Bash at all, so a cell with zero index calls made zero tool calls of ANY kind: it answered
    from nothing. On the blended arm the same number means "preferred the shell", which is
    adoption. On this arm it means the answer was fabricated, and nothing else in the artifacts
    says so.

    @brief An index_only cell at zero calls is blind.
    @return None.
    @version 1
    """
    from acceptance.execute import CellResult, index_cells_that_never_used_the_index

    rows = [
        CellResult("fabricated", "index_only", "m", True, tool_calls=0, non_index_tool_calls=0),
        CellResult("worked", "index_only", "m", True, tool_calls=6, non_index_tool_calls=0),
        ## UNKNOWN IS STILL NOT ZERO, on this arm as on the other.
        CellResult("unknown", "index_only", "m", True, tool_calls=-1, non_index_tool_calls=-1),
    ]
    assert index_cells_that_never_used_the_index(rows) == ["fabricated"]


## @brief A usage document reaches the agent as a system prompt, and the cell records that it did.
## @return None.
## @version 1
def test_a_skills_document_is_appended_and_recorded(tmp_path, monkeypatch) -> None:
    """THE DOCUMENT IS A SEPARATE SURFACE FROM THE BRIEF, deliberately. `check_symmetry` guards
    the brief and must keep passing: an A/B of a usage document has to vary something the brief
    does not, or it becomes the coached-versus-uncoached asymmetry that invalidated an earlier
    run. `--append-system-prompt` is that surface, and it is also how an adopter actually loads
    a repo-level agent doc.

    AND THE CELL SAYS WHETHER IT HAD ONE. A run directory holding both variants is unreadable if
    a cell cannot say which it was; the stem alone cannot carry it, because the stem is the
    (question, model, arm, replicate) key both variants share.

    @brief The skills doc is appended and recorded.
    @return None.
    @version 1
    """
    import json
    import subprocess

    from acceptance import execute
    from acceptance.runner import Cell

    doc = tmp_path / "SKILLS.md"
    doc.write_text("ASK FOR EVERYTHING IN ONE CALL.", encoding="utf-8")
    seen = {}

    def fake(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"result": "an answer", "usage": {}, "session_id": "s"}), ""
        )

    monkeypatch.setattr(subprocess, "run", fake)
    cell = Cell("t", "Q1", "index_only", "m", 1, 0)
    out = tmp_path / "out"
    res = execute.run_cell(
        cell, "a question?", tmp_path, out, mcp_config=doc, skills=doc, timeout=5
    )
    assert res.ok

    argv = seen["argv"]
    assert "--append-system-prompt" in argv, "the document must reach the agent"
    assert "ASK FOR EVERYTHING IN ONE CALL." in argv[argv.index("--append-system-prompt") + 1]
    ## THE BRIEF IS UNTOUCHED — the document is a different surface, which is what keeps the
    ## comparison free of the brief asymmetry.
    assert "ASK FOR EVERYTHING" not in argv[argv.index("-p") + 1]

    meta = json.loads((out / f"{cell.stem()}.meta.json").read_text())
    assert meta["skills"], "a cell must record that it was given a usage document"


## @brief Without the document nothing is appended, and the record says so.
## @return None.
## @version 1
def test_without_a_skills_document_nothing_is_appended(tmp_path, monkeypatch) -> None:
    """The default must produce the argv every earlier measurement used, or the two halves of
    the A/B are not comparable to the baseline that motivated it.

    @brief No doc, no flag.
    @return None.
    @version 1
    """
    import json
    import subprocess

    from acceptance import execute
    from acceptance.runner import Cell

    seen = {}

    def fake(argv, **kw):
        seen["argv"] = argv
        return subprocess.CompletedProcess(
            argv, 0, json.dumps({"result": "an answer", "usage": {}, "session_id": "s"}), ""
        )

    monkeypatch.setattr(subprocess, "run", fake)
    cell = Cell("t", "Q1", "baseline", "m", 1, 0)
    out = tmp_path / "out2"
    execute.run_cell(cell, "a question?", tmp_path, out, timeout=5)
    assert "--append-system-prompt" not in seen["argv"]
    meta = json.loads((out / f"{cell.stem()}.meta.json").read_text())
    assert meta["skills"] == "", "absent is recorded as absent, not omitted"


## @brief A tool call recorded twice in the transcript is counted once.
## @return None.
## @version 1
def test_a_repeated_transcript_row_does_not_double_count_a_tool_call(tmp_path, monkeypatch):
    """MEASURED ON THE 1.1.0 GRID, and it inflated every tool figure the matrix produced. One
    cell's session JSONL held 118 rows against 64 distinct uuids and 30 `tool_use` blocks against
    **16 distinct ids** — so `tool_calls` was recorded as 30 when the agent made 16. Uniform at
    1.92-1.94x across all three arms, which is why it hid: every cross-arm RATIO looked right
    while every absolute count was nearly double.

    THE ID IS THE IDENTITY. A `tool_use` block carries an id the model assigned; the same id
    appearing twice is the same call written down twice, whatever caused the transcript to repeat
    a row. Counting blocks instead of ids trusts the file's shape rather than its content.

    A non-index tool counted twice is doubly wrong: `non_index_tool_calls` drives the shell
    displacement column, and `tool_calls == non_index_tool_calls` is the blind-cell test.

    @brief Duplicate transcript rows are de-duplicated by tool_use id.
    @return None.
    @version 1
    """
    import json

    from acceptance.execute import count_tools

    slug = "-" + str(tmp_path).lstrip("/").replace("/", "-")
    proj = tmp_path / "home" / ".claude" / "projects" / slug
    proj.mkdir(parents=True)
    row = {
        "message": {
            "content": [
                {"type": "tool_use", "id": "toolu_A", "name": "mcp__clew__dossier"},
                {"type": "tool_use", "id": "toolu_B", "name": "Grep"},
            ]
        }
    }
    ## The same row written twice, which is what the real transcripts do.
    (proj / "sid.jsonl").write_text(json.dumps(row) + "\n" + json.dumps(row) + "\n", "utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path / "home"))

    total, non_index = count_tools({}, "sid", tmp_path)
    assert total == 2, f"two distinct calls written twice must count as 2, got {total}"
    assert non_index == 1, f"one non-index call written twice must count as 1, got {non_index}"
