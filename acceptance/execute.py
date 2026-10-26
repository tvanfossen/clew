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
    ## THE INDEX ALONE, NO SHELL. This WAS described here as a ceiling arm standing beside the
    ## grid; the owner ruling of 2026-08-22 put it IN the grid as the comparison arm, and
    ## `runner.ARMS` is where that is stated. The comment outlived the ruling by two months.
    ##
    ## Stripping the shell is what makes a miss attributable: the arm cannot read a line of
    ## source, so a component it does not reach is one the index does not carry, rather than one
    ## the agent chose not to look up.
    "index_only": "mcp__clew__dossier,mcp__clew__search,mcp__clew__index",
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
    ## WHICH USAGE DOCUMENT THIS CELL WAS GIVEN, by path, or "" for none. A run directory holding
    ## both halves of a documentation A/B is unreadable if a cell cannot say which half it is —
    ## the stem cannot carry it, being the (question, model, arm, replicate) key both share.
    ## Recorded as "" rather than omitted, so "no document" and "nobody recorded" differ.
    skills: str = ""
    ## WHAT ACTUALLY ANSWERED, as the provider named it — `modelUsage`'s own key, not the id this
    ## harness asked for. These are usually the same string and the day they differ is the day
    ## this field is the only evidence of it.
    ##
    ## THIS IS THE PROVENANCE THAT REPLACED A DATE REQUIREMENT. 1.1.0 asked for
    ## `claude-haiku-5-5` and recorded only that it had asked; a fix then demanded a dated id and
    ## rejected every current-family model, because the provider publishes none. The resolution is
    ## to accept the canonical id and record what came back, so drift is visible rather than
    ## either silent or forbidden.
    ##
    ## "" MEANS THE ENVELOPE DID NOT SAY, never "the asked-for model answered". A cell whose
    ## provenance is unknown must not read as a cell that confirmed it.
    answered_by: str = ""
    seconds: float = 0.0
    ## FOUR TOKEN NUMBERS, NEVER ONE. Blending them hides that cached prefix dominates: measured
    ## at 534,192 cache-read against 7,292 output on a single cell.
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    cost_usd: float = 0.0
    result_bytes: int = 0
    turns: int = 0
    tool_calls: int = 0
    non_index_tool_calls: int = 0
    ## A DENIED CALL IS EVIDENCE, not noise: it is an arm reaching for something it was fenced
    ## from, and a non-zero count on the BASELINE arm means the fencing is doing work it should
    ## not have to do.
    denied_tool_calls: int = 0
    error: str = ""


## @brief Count tool calls in a runner transcript, split by whether they used the index.
## @param envelope The runner's JSON envelope.
## @return (total calls, calls that were not index tools).
## @version 1
def count_tools(envelope: dict, session_id: str | None, repo_root: Path) -> tuple[int, int]:
    """NON-INDEX CALLS ARE THE LEVER UNDER TEST, so they are counted rather than inferred.

    THE JSON ENVELOPE DOES NOT CARRY THE MESSAGES. Measured on the first real run: it holds
    `usage`, `num_turns`, `permission_denials` and the result text, and nothing else. The tool
    calls live in the SESSION TRANSCRIPT, which the envelope names by `session_id`.

    Returns -1 for both when the transcript cannot be read. A cell whose tool use is UNKNOWN must
    not report 0, because 0 reads as "used no tools" — the best possible result on the very axis
    being measured, handed out for a missing file.

    @brief Tool-call counts from the session transcript.
    @return (total, non-index).
    @version 3
    """
    if not session_id:
        return -1, -1
    slug = "-" + str(repo_root).lstrip("/").replace("/", "-")
    path = Path.home() / ".claude" / "projects" / slug / f"{session_id}.jsonl"
    if not path.is_file():
        found = list((Path.home() / ".claude" / "projects").glob(f"*/{session_id}.jsonl"))
        if not found:
            return -1, -1
        path = found[0]
    ## COUNTED BY tool_use ID, NOT BY BLOCK, because a transcript repeats rows. Measured on the
    ## 1.1.0 grid: one cell's JSONL held 118 rows against 64 distinct uuids and 30 `tool_use`
    ## blocks against SIXTEEN distinct ids, so this reported 30 calls for an agent that made 16.
    ##
    ## IT HID BECAUSE IT WAS UNIFORM — 1.92x to 1.94x on all three arms — so every cross-arm
    ## ratio looked right while every absolute count was nearly double. A figure that is wrong
    ## by the same factor everywhere is the hardest kind to notice and the easiest to publish.
    ##
    ## The id is the call's identity: the model assigns it, and the same id twice is one call
    ## written down twice, whatever made the file repeat a row. Counting blocks trusts the
    ## file's shape; counting ids trusts its content.
    seen: dict[str, str] = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            content = ((row.get("message") or {}).get("content")) or []
            for block in content if isinstance(content, list) else []:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                ## A block with no id cannot be de-duplicated, so it is kept under a key of its
                ## own rather than silently collapsing every such block into one.
                key = str(block.get("id") or f"anon:{len(seen)}")
                seen.setdefault(key, str(block.get("name") or ""))
    except OSError:
        return -1, -1
    total = len(seen)
    non_index = sum(1 for name in seen.values() if "clew" not in name)
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
    skills: Path | None = None,
) -> CellResult:
    """REFUSES rather than silently degrading when the index arm has no MCP config. An index arm
    that quietly ran without its index would produce a full set of plausible answers and a
    publishable-looking number, and nothing downstream could tell.

    @brief Execute one cell.
    @return CellResult.
    @version 2
    """
    import time

    if cell.arm in ("index", "index_only") and mcp_config is None:
        raise ValueError(
            f"{cell.stem()}: the index arm needs an MCP config. Running it without one "
            f"measures the baseline arm under the index arm's name"
        )
    out_dir = out_dir.resolve()
    repo_root = repo_root.resolve()
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
        ## THE BASELINE ARM MUST NOT INHERIT THE OPERATOR'S MCP SERVERS. Measured on the first
        ## real run: the baseline arm attempted `mcp__plugin_clew_clew__index` and was denied by
        ## --allowedTools, so no index data reached the answer — but it could SEE that an index
        ## existed, which is a hint the comparison cannot afford to give it. Denying a call is
        ## not the same as never offering it.
        ##
        ## `--strict-mcp-config` loads ONLY what is passed on the command line, so the baseline
        ## arm gets an empty server set rather than whatever the launching session happened to
        ## have configured.
        "--strict-mcp-config",
    ]
    ## A SEPARATE SURFACE FROM THE BRIEF, deliberately. `check_symmetry` guards the brief and
    ## must keep passing: a usage document that varied the brief would be the coached-versus-
    ## uncoached asymmetry that invalidated an earlier run. The SYSTEM prompt is also how an
    ## adopter actually loads a repo-level agent doc, so this measures the real mechanism.
    if skills is not None:
        argv += ["--append-system-prompt", skills.read_text(encoding="utf-8")]
    ## ABSOLUTE, because the subprocess runs with cwd set to the TARGET REPO. A relative config
    ## path resolved against that tree, the file was not there, and every index cell failed
    ## while the baseline cells succeeded — a failure mode that silently produces a one-armed
    ## run if the errors are not read.
    if cell.arm in ("index", "index_only") and mcp_config is not None:
        argv += ["--mcp-config", str(mcp_config.resolve())]

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
    calls, non_index = count_tools(envelope, envelope.get("session_id"), repo_root)
    ## THE ENVELOPE HAS NO `total_tokens`, and assuming one read the cost axis as ZERO on every
    ## cell of the first real run. It carries the four components separately, and they must stay
    ## separate: measured on one baseline cell, cache_read was 534,192 against 7,292 output.
    ## Summing them into one number is the "turn counter times a mostly-cached prompt" the
    ## hypothesis warns about — it would have been dominated by cached prefix and said nothing
    ## about retrieval.
    ## ONE KEY OR NONE. `modelUsage` is keyed by the model that served the call, so a single key
    ## is the answer; several would mean the run fanned across models and the field must not pick
    ## one and imply it was the only one.
    usage_models = sorted((envelope.get("modelUsage") or {}).keys())
    answered_by = usage_models[0] if len(usage_models) == 1 else ",".join(usage_models)

    result = CellResult(
        stem=cell.stem(),
        arm=cell.arm,
        model=cell.model,
        answered_by=answered_by,
        ok=bool(answer.strip()),
        seconds=elapsed,
        input_tokens=int(usage.get("input_tokens") or 0),
        output_tokens=int(usage.get("output_tokens") or 0),
        cache_read_tokens=int(usage.get("cache_read_input_tokens") or 0),
        cache_creation_tokens=int(usage.get("cache_creation_input_tokens") or 0),
        cost_usd=float(envelope.get("total_cost_usd") or 0.0),
        result_bytes=len(answer.encode("utf-8")),
        turns=int(envelope.get("num_turns") or 0),
        tool_calls=calls,
        non_index_tool_calls=non_index,
        denied_tool_calls=len(envelope.get("permission_denials") or []),
        skills=str(skills) if skills is not None else "",
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


## @brief Flag index cells that never touched the index.
## @param results Cell results from a generate pass.
## @return List of stems that are suspect.
## @version 1
def index_cells_that_never_used_the_index(results: list[CellResult]) -> list[str]:
    """THE ONLY DOWNSTREAM SIGNAL THAT THE INDEX ARM RAN WITHOUT ITS INDEX.

    Measured: a relative `--repo` in the MCP config resolved inside the target checkout, so the
    server started, found no database, and registered no query tools. It emitted no error, the
    agent raised no denial, and the run reported 4/4 ok — the index arm answered the question
    without its index and produced prose indistinguishable from a real cell.

    A cell that used the index zero times is NOT automatically broken: an agent may genuinely
    choose not to reach for it, and whether it wants to is adoption, which the hypothesis puts
    out of scope. So this REPORTS rather than refuses. But an index arm at zero across a whole
    run is a configuration failure until proven otherwise, and nothing else in the artifacts
    says so.

    A cell whose tool use could not be determined (-1) is not counted here — unknown is not zero,
    and treating it as zero would manufacture the very alarm this exists to raise honestly.

    BOTH INDEX-BEARING ARMS, DERIVED FROM `_ALLOWED` RATHER THAN NAMED. This read `arm == "index"`
    while `ARMS` is ("baseline", "index_only"), so the one check that catches a fabricating index
    arm watched the arm the 1.1.0 grid does not run. `runner.check_symmetry` carries a comment
    about this exact defect — it named its two arms literally and kept comparing the OLD pair
    after the compared arms changed — which is why the set is derived here.

    AND IT MATTERS MORE ON `index_only` THAN ON THE BLENDED ARM. That arm is granted no Read,
    Grep, Glob or Bash, so zero index calls means zero tool calls of any kind: the answer came
    from nothing. On the blended arm the same number means the agent preferred the shell, which
    is adoption; here it means the prose was fabricated.

    @brief Index cells with no index calls.
    @return Suspect cell stems.
    @version 2
    """
    index_bearing = {arm for arm, tools in _ALLOWED.items() if "mcp__clew__" in tools}
    return [
        r.stem
        for r in results
        if r.arm in index_bearing
        and r.ok
        and r.tool_calls >= 0
        and r.tool_calls == r.non_index_tool_calls
    ]
