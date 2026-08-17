# SPDX-License-Identifier: MIT
## @brief Per-cell STRUCTURAL proof that the index arm answered about the target repository.
## @version 1
"""A cell whose database describes a DIFFERENT repository than the questions ask about is
**VOID** — not low-scoring. Its marks are meaningless and averaging them corrupts the grid.

WHY THIS EXISTS, and why the existing guards are not it. `run_matrix.mcp_config_for` derives
the server's `--repo` from the same `--target` the questions use, and `preflight_target`
samples the resolved index's paths against the target root. Both are ONCE-PER-SWEEP and both
constrain the DEFAULT target only. Neither can see what a cell actually did, and the server's
own contract says every query tool takes an optional `target` argument — so an agent that
calls `list_targets` and then names another repository answers about it, from a correctly
configured server, and every existing check passes.

WHY IT IS NOT A PROSE CHECK. A prose version of exactly this check was written, measured and
DROPPED: agents phrase "wrong repository" a dozen ways, the regex caught 4 of the 15 real
cases and false-positived on a source-arm cell. A guard that unreliable converts "unchecked"
into "checked and fine", which is how this project's identifier leak, its disarmed coverage
gate and a 36-cell grid all shipped.

WHAT MAKES THIS ONE STRUCTURAL. Every reply the server emits stamps the repository that
answered it — `tools_query` writes `out["target"]` on the way out of every query reply,
`build_or_refresh` writes `result["target"]`, and `status` writes `repo_path`. Those values are
repository PATHS in a JSON payload, so the check is a path comparison against the cell's target,
with no natural-language term anywhere in it. An agent cannot phrase around a field the server
writes.

TWO KEYS, BECAUSE ONE OF THEM WAS BLIND TO THE FIRST TOOL A CELL CALLS. Reading `target` alone
missed `status` entirely, and `status` is the tool a bringup or Q0 cell reaches for FIRST. A
control settled it rather than a reading: a synthetic transcript whose only index call was a
`status` reply naming the WRONG repository came back `unchecked`, indistinguishable from a cell
whose provenance could not be read — the owner's hard-gate case, silently downgraded. With
`repo_path` read as well it comes back `void`.

BOTH ARE TOP-LEVEL-ONLY, and that restriction is what keeps the check from false-positiving.
`list_targets` returns EVERY registered repository, several of which are legitimately foreign,
each as a `repo_path` inside a nested list — a scan for "any absolute path in the payload" would
void every cell that merely looked at the registry. The two keys are read at the top level of the
reply object, where they name the repository that answered THIS call and nothing else. The same
control exercises a `list_targets` reply carrying two foreign `repo_path` values and requires it
NOT to be void.

WHAT IT CANNOT DO, said plainly rather than overclaimed. It reads the PRESERVED TRANSCRIPT. A
cell with no transcript, or whose index replies carried no `target` field, is reported
`unchecked` — never `ok`. "I could not look" and "I looked and it was fine" have different
spellings here on purpose.

`build_meta` DOES NOT STAMP THE REPO PATH — verified against three live indexes at build 30;
the stamped sections are `build_version`, `scope.*`, `coverage.*`, `preprocessor.*`,
`kconfig.*`, `refresh.*` and `options.*`. So "compare the database's own stamped repo path to
the target" is not available, and the reply stamp is used instead. It is the stronger signal
anyway: it records the repository that answered THIS CELL, not the one some database was built
from.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from bench_arms import MCP_TOOL_PREFIX

## The TOP-LEVEL keys under which a reply names the repository that answered it.
##
## `target`    — every tier-1 query reply (`tools_query._stamp`) and `build_or_refresh`.
## `repo_path` — `status`, whose payload IS a `db_status()` record for the active target.
##
## Order matters only for the reason recorded: a reply carrying both would be reporting one
## repository twice, so the first hit is taken and the other ignored rather than double-counted.
_TARGET_KEYS = ("target", "repo_path")

## The three states a cell can be in, and they are three rather than two on purpose.
OK = "ok"
VOID = "void"
UNCHECKED = "unchecked"
NOT_APPLICABLE = "n/a"


## @brief Pull the text out of one `tool_result` block, whatever shape it took.
## @param block A transcript content block.
## @return The result text, or "" when there is none.
## @version 1
## @dg_internal
def _result_text(block: dict) -> str:
    """A tool result's `content` is a string in some transcript versions and a list of
    `{"type": "text", "text": ...}` parts in others. Both are read rather than one being
    assumed, because assuming the wrong one yields zero observations and this module reports
    zero observations as `unchecked` — a silent downgrade rather than a visible failure.

    @brief Normalise a tool_result payload to text.
    @return Result text.
    @version 1
    """
    content = block.get("content")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts = [p.get("text", "") for p in content if isinstance(p, dict) and p.get("text")]
    return "\n".join(parts)


## @brief Every repository an index tool reported answering from, in call order.
## @param transcript Preserved transcript jsonl path.
## @return Ordered, de-duplicated list of raw repository stamps.
## @version 2
def served_targets(transcript: Path) -> list[str]:
    """Two passes over one read, because a `tool_result` names only the id of the call it
    answers. The first pass records which ids belong to a clew tool; the second reads
    only those results, so a foreign MCP server's own `target` field can never be mistaken for
    this one's.

    Malformed lines are skipped rather than fatal, matching `bench_arms._events` — a
    partially-flushed transcript must not take a sweep down. It will, correctly, reduce the
    verdict to `unchecked`.

    @brief Collect the repository stamp of every index-tool reply.
    @return Raw stamp values.
    @version 2
    """
    events = []
    for line in transcript.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    db_ids: set[str] = set()
    for event in events:
        for block in _blocks(event):
            if block.get("type") == "tool_use" and str(block.get("name", "")).startswith(
                MCP_TOOL_PREFIX
            ):
                db_ids.add(str(block.get("id", "")))
    seen: list[str] = []
    for event in events:
        for block in _blocks(event):
            if block.get("type") != "tool_result":
                continue
            if str(block.get("tool_use_id", "")) not in db_ids:
                continue
            value = _target_of(_result_text(block))
            if value and value not in seen:
                seen.append(value)
    return seen


## @brief The message content blocks of one transcript event.
## @param event A transcript event dict.
## @return Block list.
## @version 1
## @dg_internal
def _blocks(event: dict) -> list[dict]:
    """@brief Extract an event's content blocks.
    @return Block list.
    @version 1
    """
    content = (event.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


## @brief Read the repository stamp out of one index reply's JSON text.
## @param text Reply text.
## @return The stamped repository path, or "" when the reply is not JSON or carries none.
## @version 2
## @dg_internal
def _target_of(text: str) -> str:
    """TOP LEVEL ONLY — `payload.get`, never a walk. A recursive search would find the
    `repo_path` of every registry entry inside a `list_targets` reply and void the cell for
    looking at a list.

    @brief Decode a reply and return its repository stamp.
    @return Stamp value or "".
    @version 2
    """
    try:
        payload = json.loads(text)
    except ValueError:
        return ""
    if not isinstance(payload, dict):
        return ""
    for key in _TARGET_KEYS:
        value = payload.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


## @brief Classify observed target stamps against the cell's target.
## @param observed Raw target values from `served_targets`.
## @param target Resolved target repo root.
## @return (status, reason) where status is OK / VOID / UNCHECKED.
## @version 1
def classify(observed: list[str], target: Path) -> tuple[str, str]:
    """THE RULE IS ONE-SIDED AND DELIBERATELY SO. A single reply naming a repository that is
    not the target makes the cell VOID, however many other replies were correct — an answer
    assembled partly from a foreign repository is not a partly-correct answer, it is an answer
    whose provenance no grade can separate.

    A value that is neither the target nor a resolvable foreign path (a bare database name,
    which the server emits for a tool set constructed without a repo provider) is recorded and
    counted as neither. It cannot prove the cell right and it cannot prove it wrong.

    @brief Decide a cell's target verdict.
    @return (status, reason).
    @version 1
    """
    wanted = target.expanduser().resolve()
    matched: list[str] = []
    foreign: list[str] = []
    other: list[str] = []
    for raw in observed:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            other.append(raw)
        elif candidate.resolve() == wanted:
            matched.append(raw)
        else:
            foreign.append(raw)
    if foreign:
        return VOID, f"index replies named {foreign}, but this cell's target is {wanted}"
    if matched:
        return OK, f"{len(matched)} distinct index reply target(s), all {wanted}"
    if other:
        return UNCHECKED, f"index replies stamped no resolvable repository path: {other}"
    return UNCHECKED, "no index reply carried a target stamp"


## @brief Verify one cell answered about the target repository.
## @param arm Arm name.
## @param transcript Preserved transcript path, or None when the run reported none.
## @param target Resolved target repo root.
## @return Record with status, reason and the raw observations.
## @version 1
def verify(arm: str, transcript: Path | None, target: Path) -> dict:
    """The source arm has no counterpart and none is invented: it never reaches a database, so
    there is nothing to point at the wrong repository. `n/a` says that, and it must not share a
    spelling with `ok` — a source-arm cell has not passed this check, it was never subject to
    it.

    @brief Produce a cell's target verdict record.
    @return Verdict record.
    @version 1
    """
    if arm != "mcp":
        return {"status": NOT_APPLICABLE, "reason": "source arm reaches no index", "observed": []}
    if not (transcript and transcript.is_file()):
        return {
            "status": UNCHECKED,
            "reason": "no transcript preserved — the cell's provenance cannot be read",
            "observed": [],
        }
    observed = served_targets(transcript)
    status, reason = classify(observed, target)
    return {"status": status, "reason": reason, "observed": observed}


## @brief The void cells recorded in a finished run directory.
## @param run_dir Run output directory holding metrics.csv.
## @return Mapping answer-file stem -> reason, empty when the column is absent.
## @version 1
def void_cells(run_dir: Path) -> dict[str, str]:
    """READ FROM THE CSV, not recomputed, so the grader and the runner cannot disagree about
    which cells were void. A run directory written before this column existed yields an empty
    mapping and the caller must say the run is UNCHECKED for this term rather than clean —
    absence of the column is absence of the measurement.

    @brief List a run's void cells by answer stem.
    @return Stem -> reason mapping.
    @version 1
    """
    path = run_dir / "metrics.csv"
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    with path.open(newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row.get("target_ok") or "") == VOID:
                out[Path(row.get("answer_path", "")).stem] = f"{row.get('q')} {row.get('arm')}"
    return out


## @brief Whether a run directory records the target column at all.
## @param run_dir Run output directory.
## @return True when metrics.csv carries `target_ok`.
## @version 1
def records_target_column(run_dir: Path) -> bool:
    """@brief Report whether the wrong-repo term was measured for this run.
    @return True when the column exists.
    @version 1
    """
    path = run_dir / "metrics.csv"
    if not path.is_file():
        return False
    with path.open(newline="", encoding="utf-8") as fh:
        return "target_ok" in (next(csv.reader(fh), []) or [])
