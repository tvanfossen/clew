# SPDX-License-Identifier: MIT
"""Run one cell and freeze what it produced. Nothing here grades anything.

WHAT A CELL LEAVES BEHIND, and every piece is written because a previous generation could not
answer a question without it:

    <stem>.md          the answer prose — the only input grading ever reads
    <stem>.meta.json   the three axes plus the argv that produced them
    <stem>.raw.json    the runner's full JSON envelope, unedited

THE ARGV IS RECORDED. A grid once published a verdict from an arm pointed at the wrong
repository while every question asked about another, and all its cells recorded valid=True
because each validity term checked that tools were CALLED and none checked WHICH repository
answered. The argv is the only artifact that settles that afterwards.

COST IS TWO NUMBERS. `total_tokens` is a turn counter multiplied by a mostly-cached prompt, so
it tracks round trips far more closely than anything retrieved — and the two have disagreed in
SIGN on the same run. Both are recorded, and a reader quoting one alone is quoting half.

AN ERRORED CELL IS NOT AN EMPTY ANSWER. It writes no `.md` at all, so grading cannot mistake a
transport failure for an agent that said nothing.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from .runner import Cell, brief

DEFAULT_TIMEOUT = 1800

## Tool grants per arm. The BASELINE arm keeps its full repertoire deliberately: the comparison
## is a default agentic harness with the index against the same harness without it, not "index
## versus grep". Fencing the baseline to one command would measure a strawman, and a partial or
## full file read fails the same way a search does.
_ALLOWED = {
    "baseline": "Read,Grep,Glob,Bash",
    "index": "Read,Grep,Glob,Bash,mcp__clew__dossier,mcp__clew__search,mcp__clew__index",
}


## @brief What one cell produced.
## @version 1
@dataclass(frozen=True)
class CellResult:
    """@brief The three axes, plus whether the cell produced an answer at all.
    @version 1
    """

    stem: str
    arm: str
    model: str
    ok: bool
    seconds: float = 0.0
    total_tokens: int = 0
    result_bytes: int = 0
    turns: int = 0
    tool_calls: int = 0
    non_index_tool_calls: int = 0
    error: str = ""


## @brief Count tool calls in a runner transcript, split by whether they used the index.
## @param envelope The runner's JSON envelope.
## @return (total calls, calls that were not index tools).
## @version 1
def count_tools(envelope: dict) -> tuple[int, int]:
    """NON-INDEX CALLS ARE THE LEVER UNDER TEST, so they are counted rather than inferred.

    Returns -1 for both when the envelope carries no message list — a cell whose tool use is
    UNKNOWN must not report 0, because 0 reads as "used no tools", which is the best possible
    result on the axis being measured.

    @brief Tool-call counts.
    @return (total, non-index).
    @version 1
    """
    messages = envelope.get("messages")
    if not isinstance(messages, list):
        return -1, -1
    total = 0
    non_index = 0
    for message in messages:
        for block in (message.get("content") or []) if isinstance(message, dict) else []:
            if not isinstance(block, dict) or block.get("type") != "tool_use":
                continue
            total += 1
            if not str(block.get("name") or "").startswith("mcp__clew__"):
                non_index += 1
    return total, non_index


## @brief Run one cell and write its artifacts.
## @param cell The cell to run.
## @param question The question prompt text.
## @param repo_root The target working tree the agent is pointed at.
## @param out_dir Directory to write artifacts into.
## @param mcp_config Path to an MCP config, required for the index arm.
## @param timeout Seconds before the cell is abandoned.
## @return CellResult.
## @version 1
def run_cell(
    cell: Cell,
    question: str,
    repo_root: Path,
    out_dir: Path,
    mcp_config: Path | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> CellResult:
    """REFUSES rather than silently degrading when the index arm has no MCP config. An index arm
    that quietly ran without its index would produce a full set of plausible answers and a
    publishable-looking number, and nothing downstream could tell.

    @brief Execute one cell.
    @return CellResult.
    @version 1
    """
    import time

    if cell.arm == "index" and mcp_config is None:
        raise ValueError(
            f"{cell.stem()}: the index arm needs an MCP config. Running it without one "
            f"measures the baseline arm under the index arm's name"
        )
    out_dir.mkdir(parents=True, exist_ok=True)
    argv = [
        "claude",
        "-p",
        brief(cell.arm, str(repo_root), question),
        "--model",
        cell.model,
        "--output-format",
        "json",
        "--allowedTools",
        _ALLOWED[cell.arm],
    ]
    if cell.arm == "index" and mcp_config is not None:
        argv += ["--mcp-config", str(mcp_config)]

    started = time.monotonic()
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=timeout, cwd=str(repo_root), check=False
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return CellResult(cell.stem(), cell.arm, cell.model, False, error=f"transport: {exc}")
    elapsed = time.monotonic() - started
    if done.returncode != 0:
        return CellResult(
            cell.stem(),
            cell.arm,
            cell.model,
            False,
            seconds=elapsed,
            error=f"rc={done.returncode}: {done.stderr.strip()[:400]}",
        )
    try:
        envelope = json.loads(done.stdout)
    except json.JSONDecodeError as exc:
        return CellResult(
            cell.stem(), cell.arm, cell.model, False, seconds=elapsed, error=f"envelope: {exc}"
        )

    answer = str(envelope.get("result") or "")
    usage = envelope.get("usage") or {}
    calls, non_index = count_tools(envelope)
    result = CellResult(
        stem=cell.stem(),
        arm=cell.arm,
        model=cell.model,
        ok=bool(answer.strip()),
        seconds=elapsed,
        total_tokens=int(usage.get("total_tokens") or envelope.get("total_tokens") or 0),
        result_bytes=len(answer.encode("utf-8")),
        turns=int(envelope.get("num_turns") or 0),
        tool_calls=calls,
        non_index_tool_calls=non_index,
        error="" if answer.strip() else "the agent produced no answer text",
    )

    (out_dir / f"{cell.stem()}.raw.json").write_text(json.dumps(envelope, indent=2), "utf-8")
    (out_dir / f"{cell.stem()}.meta.json").write_text(
        json.dumps({**asdict(result), "argv": argv, "cell": asdict(cell)}, indent=2), "utf-8"
    )
    ## NO `.md` ON FAILURE. An empty answer file and a failed cell are different states, and
    ## grading must not be able to read the second as the first.
    if result.ok:
        (out_dir / f"{cell.stem()}.md").write_text(answer, "utf-8")
    return result
