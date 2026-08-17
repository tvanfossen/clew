## @brief Arm policy + post-hoc transcript audit for the matrix runner.
## @version 3
"""THE ARMS ARE PRIORITISATION AND AUDIT, NOT PROHIBITION (owner reframe, gh#354).

They used to be a prohibition: the `src` arm lost the index, the `mcp` arm lost
`Grep`/`Glob`/`Bash`, and the grid therefore measured "index vs grep". That is not
the question. In real work an agent keeps every instrument; the claim under test is
that it should reach for the INDEX FIRST. So both arms now carry the default
toolset, and the comparison is "index+grep vs grep" — the honest question, and the
HARDER one to win, because an index arm that can also grep will grep when the index
disappoints, raising its floor and shrinking the measurable gap.

THE ONE STRUCTURAL DIFFERENCE IS THE ONLY ONE THAT WAS EVER REAL: `build_argv`
attaches `--mcp-config` to the `mcp` arm alone, so the `src` arm cannot reach the
index because the server is not there. The deny list beside it was a second net over
a door that does not exist.

WHAT THIS COSTS, and it must be stated in the result rather than inherited: the
"isolation is enforced, not audited" property `methodology.md` claims as better than
the reference approach is RETIRED. With the denials gone, transparency is post-hoc
again — `audit` observes, it does not prevent. A deliberate trade.

TWO SEVERITIES, because one flag cannot carry both:

INCOMPARABLE — clears `audit_clean`. The cell's numbers cannot be compared.
  spawn:<t>          work handed to a sub-agent whose transcript we never see.
                     Matched by PREFIX (`Task*`, `Agent*`) so a spawner under a NEW
                     name is caught fail-closed.
  foreign_mcp:<t>    an `mcp__*` tool from a server that is not ours: an unaudited
                     oracle, structurally the same problem as a sub-agent. (One real
                     attempt exists in the 0.5.0 evidence.)
  tool:<t>           a name on the arm's derived deny list. After gh#354 that list is
                     the two WEB tools — a third information source that measures
                     neither arm.
  db_direct:<t>:<w>  `sqlite3` or a `clew.db` path outside the MCP surface. THE HARD
                     BAN THAT SURVIVES, and it is about measuring the PRODUCT: SQL
                     over the schema is not the tool a user has.

REVIEW — does NOT clear `audit_clean`. The ordering evidence the hypothesis rests on.
  source_read:<t>    the index arm read source. Legitimate fallback, and the only
                     record of whether the index came first.
  mutation:<t>       the index arm wrote to the tree. Required by the
                     edit-to-queryable question; worth a look anywhere else.

REPORTED ONLY.
  unlisted:<t>       outside the pre-approval list and none of the above.

THE PERMISSION FLAGS ARE PRE-APPROVAL, NOT A WHITELIST — measured, and the reason
the audit classifies every observed tool rather than a handful of bad names: cells in
a completed run used `TaskCreate`, `TaskUpdate` and `LSP`, which appeared in NO allow
list. Any claim that the flags "prevent" contamination is false as stated, and this
file used to make it.

None of this replaces the runner's own check: an `mcp` run that never got a
`mcp__clew__*` tool to RETURN is INVALID, because a prompt that does not
force a tool call can be answered before the server has finished connecting.

EVERY CELL CAN NOW MUTATE THE TREE. Tree and index restore between cells stops being
a nicety — see the runner.
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

from clew.mcp_server.descriptions import load_descriptions

MCP_SERVER = "clew"  # the server registers under the package name

## EVERY SERVER NAME A COMMITTED TRANSCRIPT WAS RECORDED UNDER, newest first. A transcript
## stamps the tool names in force when it ran, so renaming the server retires no artifact —
## it only changes what the artifact's names look like.
##
## THIS IS NOT HOUSEKEEPING; ITS ABSENCE VOIDED EVERY COMMITTED MEASUREMENT. `MCP_SERVER`
## became "clew" while all 102 tracked transcripts hold `mcp__doxyguard-db__`, so
## `MCP_TOOL_PREFIX` matched nothing in any of them: `db_tool_outcomes` returned (0, 0) for a
## cell that made eleven index calls, and `result_bytes(db_only=True)` returned 0 — the
## RETRIEVAL measure, the one figure this project requires be reported beside `total_tokens`
## because the two have disagreed in sign. The published numbers were computed before the
## rename and are unaffected; what broke is the ability to RE-DERIVE them, which is the whole
## reason the transcripts are committed rather than summarised.
##
## The failure is silent in the direction that reads as a result: zero index calls is a
## legitimate value for a source-arm cell, so nothing looked wrong.
MCP_SERVER_ALIASES: tuple[str, ...] = (MCP_SERVER, "doxyguard-db", "doxyguard_db")

## Tier-0 lifecycle tools plus every tier-1 query tool, DERIVED from the same JSON
## directory the server registers from, so the deny list cannot disagree with the surface
## it is denying.
##
## IT WAS HAND-ENUMERATED AND IT LIED TWICE. First it omitted five tier-1 tools that real
## 0.5.0 cells called (`lock_nestings`, `locks_held_when`, `runs_under_lock`, `sections_in`,
## `propose_declaration`) — caught, and appended. Re-reading it during the tool cull found
## the SAME defect still present in the patched list: `graph_stats` and `kconfig` were
## never in it, and `set_target` was in it though no such tool has ever existed. Appending
## to a stale enumeration produces a less-stale enumeration, not a correct one.
##
## Denial never depended on this — `MCP_TOOL_PREFIX` covers the whole server and is what
## the isolation test asserts — so what the enumeration is actually for is being readable
## and greppable. Derived, it is still both, and `sorted` keeps it stable across runs
## rather than following registration priority.
MCP_TOOLS: tuple[str, ...] = tuple(
    sorted(set(load_descriptions(tier=0)) | set(load_descriptions(tier=1)))
)

MCP_TOOL_NAMES: tuple[str, ...] = tuple(f"mcp__{MCP_SERVER}__{t}" for t in MCP_TOOLS)

## THE PREFIX FOR A RUN BEING LAUNCHED — one server, the current name. Permission flags and
## the deny list must name the server that is about to be registered and no other.
MCP_TOOL_PREFIX = f"mcp__{MCP_SERVER}__"

## THE PREFIXES FOR READING A TRANSCRIPT, which is a different question and needs a different
## answer: an artifact on disk may predate the rename. Anything that MEASURES a recorded run
## matches against these; anything that CONFIGURES a new run uses `MCP_TOOL_PREFIX`.
MCP_READ_PREFIXES: tuple[str, ...] = tuple(f"mcp__{alias}__" for alias in MCP_SERVER_ALIASES)

## THE ONLY DENIAL LEFT, and it is not about arm purity (gh#354). The open internet is a
## THIRD information source that measures neither arm: a cell answering an entropic question
## from GitHub is reading neither the local source nor the local index, and its tokens and
## time describe a fetch. Kept for BOTH arms so the comparison stays between the two things
## the hypothesis is about.
##
## Everything else that used to live here — `Write`, `Edit`, `NotebookEdit`, `Task` — is now
## ALLOWED and AUDITED instead. See `ARM_POLICY`.
_ALWAYS_DENIED: tuple[str, ...] = ("WebSearch", "WebFetch")

## What an out-of-the-box Claude Code session can reach. This is PRE-APPROVAL, not a
## whitelist: measured in a completed run, cells used `TaskCreate`, `TaskUpdate` and `LSP`,
## which appeared in NO allow list, so listing a tool grants it without withholding the rest.
## Enumerated anyway, because the argv is what a reviewer audits and an empty flag reads as
## an oversight rather than as a decision.
_DEFAULT_TOOLSET: tuple[str, ...] = (
    "Read",
    "Grep",
    "Glob",
    "Bash",
    "Write",
    "Edit",
    "NotebookEdit",
    "TodoWrite",
    "Task",
)

## Sub-agent-spawning FAMILIES, matched by prefix. `"Task"` as an exact name missed
## `TaskCreate`/`TaskUpdate` in a completed 396-cell run, which was harmless — but the
## same exact-match rule would have missed a spawner named `TaskDelegate` just as
## silently, and that would be a real isolation break producing a result nobody could
## see was invalid.
##
## DELIBERATELY OVER-BROAD, and that is the design: a name these prefixes catch is an
## isolation break UNTIL it is listed in `_NOT_SUBAGENTS` below. Fail-closed, so a tool
## added to the harness surfaces instead of being silently permitted.
_SUBAGENT_PREFIXES: tuple[str, ...] = ("Task", "Agent")

## Members of those families that demonstrably spawn NOTHING: the session todo-list
## tools. Enumerated, greppable, and the ONLY escape from the prefix rule — adding a
## name here is an explicit claim, reviewable in a diff, that it cannot delegate work.
_NOT_SUBAGENTS: frozenset[str] = frozenset(
    {"TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskStop"}
)

## Any `mcp__*` tool NOT from our own server. Kept as a bare prefix rather than a list of
## known-foreign servers, because the point is to catch the one we did not anticipate.
_ANY_MCP_PREFIX = "mcp__"

## arm -> (allowed, denied). Deny always beats allow in Claude Code, so the two
## lists must not overlap.
##
## THE ARMS ARE NO LONGER A PROHIBITION (owner reframe, gh#354). They were: the `src` arm
## lost the index and the `mcp` arm lost `Grep`/`Glob`/`Bash`, so the grid measured
## "index vs grep". A crippled arm does not measure real usage — in real work an agent keeps
## every instrument, and the claim under test is that it should reach for the INDEX FIRST.
##
## So both arms now carry the default toolset and the ONE structural difference stays:
## `run_matrix.build_argv` attaches `--mcp-config` to the `mcp` arm ALONE, so the `src` arm
## cannot reach the index because the server is not there. That was always the real guarantee;
## the deny list beside it was a second net over a door that does not exist.
##
## WHAT THIS CHANGES ABOUT THE MEASUREMENT, and it must be stated in the result rather than
## inherited: the question moves from "index vs grep" to "index+grep vs grep". The second is
## the honest real-world question and it is HARDER TO WIN, because an index arm that can also
## grep will grep when the index disappoints — which raises its floor and shrinks the gap.
##
## IT ALSO RETIRES "isolation is enforced, not audited". With the denials gone, transparency
## is post-hoc again: `audit` OBSERVES rather than prevents. A deliberate trade, and
## `methodology.md` must stop claiming the stronger property.
## THE INDEX STAYS DENIED TO THE `src` ARM, and that is NOT one of the denials gh#354
## removed. Not having the index IS the experiment — the arm is defined by its absence, so a
## `mcp__clew__*` call there is not a capability question but the control failing.
## `--mcp-config` already makes it structurally unreachable; this keeps the AUDIT able to say
## so if a globally-registered server ever leaks into a cell, which is a real failure mode in
## this project (a repo-local `.mcp.json` duplicating a global registration was removed once
## already). Without the entry such a call would classify as merely `unlisted` — reported,
## and not disqualifying, for the one event that must disqualify a cell outright.
ARM_POLICY: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "src": (
        _DEFAULT_TOOLSET,
        _ALWAYS_DENIED + (f"mcp__{MCP_SERVER}",) + MCP_TOOL_NAMES,
    ),
    "mcp": (
        _DEFAULT_TOOLSET + (f"mcp__{MCP_SERVER}",) + MCP_TOOL_NAMES,
        _ALWAYS_DENIED,
    ),
}

## THE ONE HARD BAN THAT SURVIVES gh#354: the index arm must reach the index through the
## SHIPPED MCP SURFACE and nothing else. Not about crippling an arm — about measuring the
## PRODUCT. A cell that opens `clew.db` with the `sqlite3` CLI, or `import sqlite3`, or a
## hand-written query script, is measuring SQL-over-a-schema rather than the tool a user has,
## and its tokens and time describe neither arm.
##
## THE OLD SHELL-VERB LIST IS DELETED, not weakened. It matched `grep|rg|find|sed|awk|cat|
## head|tail` because the `mcp` arm had no `Bash`; now it has, so every one of those is a
## legitimate call and the regex would fire on all of them. A guard that fires on the ordinary
## case is worse than no guard — it is precisely how the disarmed coverage gate and the
## contaminated grid each got past someone.
##
## `clew.db` is included because the filename is the giveaway whatever tool opens it, and
## because a `Read` of the database is the quiet route that no shell verb catches.
_DB_DIRECT_ACCESS = re.compile(r"\b(sqlite3|docs\.db)\b")

## Tool names the mcp arm may use to READ SOURCE. Not denied — FLAGGED, because the owner's
## reframe is prioritisation plus audit: the index should be reached for FIRST, and a source
## read is evidence about ordering rather than a rule break. `Bash` is here because a `Bash`
## call is overwhelmingly a source read in practice (`cat`, `grep`, `ls`).
_SOURCE_READING_TOOLS: frozenset[str] = frozenset({"Read", "Grep", "Glob", "Bash"})

## Tools whose whole purpose is mutating the tree. The index arm needs them for the
## edit-to-queryable-latency question (Q7), and using them ANYWHERE ELSE is the case the
## owner asked to have surfaced for closer human review.
_MUTATING_TOOLS: frozenset[str] = frozenset({"Write", "Edit", "NotebookEdit"})


## @brief Build the tool-permission flags for one arm.
## @param arm Arm name ("src" or "mcp").
## @return argv fragment carrying --allowedTools/--disallowedTools.
## @version 1
def permission_flags(arm: str) -> list[str]:
    """Render the arm's policy as CLI flags. Comma-separated single arguments
    keep the argv readable in the run log, which is what a reviewer audits.

    @brief Render an arm's allow/deny lists as CLI flags.
    @return Flag list for `claude -p`.
    @version 1
    """
    allowed, denied = ARM_POLICY[arm]
    return ["--allowedTools", *allowed, "--disallowedTools", *denied]


## @brief Locate the session transcript `claude -p` wrote for a run.
## @param session_id Session id reported in the run's JSON result.
## @return Path to the transcript jsonl, or None when it cannot be found.
## @version 1
def find_transcript(session_id: str) -> Path | None:
    """Claude Code stores transcripts under `~/.claude/projects/<cwd-slug>/`.
    The slug is derived from the working directory, so rather than reproduce
    that derivation we glob for the session id itself.

    @brief Find a run's transcript by session id.
    @return Transcript path or None.
    @version 1
    """
    root = Path.home() / ".claude" / "projects"
    if not session_id or not root.is_dir():
        return None
    hits = sorted(root.glob(f"*/{session_id}.jsonl"))
    return hits[0] if hits else None


## @brief Collect every tool invocation recorded in a transcript.
## @param path Transcript jsonl path.
## @return List of (tool_name, serialized_input) pairs in call order.
## @version 1
def tool_calls(path: Path) -> list[tuple[str, str]]:
    """Walk the jsonl, pulling `tool_use` blocks out of assistant messages.
    Malformed lines are skipped rather than fatal — a partially-flushed
    transcript must not take the sweep down.

    @brief Extract the tool_use blocks from a transcript.
    @return Ordered (name, input-as-text) pairs.
    @version 1
    """
    calls: list[tuple[str, str]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        message = event.get("message") or {}
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                calls.append((str(block.get("name", "")), json.dumps(block.get("input", {}))))
    return calls


## @brief Count docs-db tool calls that were ATTEMPTED versus ones that actually returned.
## @param path Transcript jsonl path.
## @return (attempted, succeeded).
## @version 1
def db_tool_outcomes(path: Path) -> tuple[int, int]:
    """`tool_calls` reads `tool_use` blocks, which record what the agent TRIED. That is the
    wrong question for validity, and the gap was measured rather than imagined: an index-arm
    cell whose MCP server failed to spawn emitted one `set_target` call, received
    `No such tool available`, wrote a full page explaining it could not answer — and was
    scored `valid=True`, because `used_db_tools` was 1.

    A cell that reached for the index and got an error did not use the index. Pairing each
    `tool_use` id with its `tool_result` is the only way to tell those apart, and it is the
    difference between "the index answered badly" and "the index was not there".

    @brief Count attempted and successful index tool calls.
    @return (attempted, succeeded).
    @version 1
    """
    attempted: set[str] = set()
    errored: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use" and str(block.get("name", "")).startswith(
                MCP_READ_PREFIXES
            ):
                attempted.add(str(block.get("id", "")))
            elif block.get("type") == "tool_result" and block.get("is_error"):
                errored.add(str(block.get("tool_use_id", "")))
    return len(attempted), len(attempted - errored)


## The tools whose wall time IS bringup: making the index exist, and working out what this
## repository needs stated before it can answer. `propose_declaration` belongs here because
## it is the correction surface (gh#360) — an agent that discovers at question one what
## bringup missed pays for the discovery, and charging that to the first QUESTION instead of
## to bringup is exactly the folding the owner ruled out.
##
## AN ENTRY IS (tool, actions) AND THE SECOND HALF IS WHY THIS SHAPE EXISTS. Building is no
## longer a tool of its own: `build_or_refresh` was folded into `index(action='refresh')`, so
## the tool NAME `index` covers `status`, `targets` and `cull` as well — none of which is
## bringup, and `status` is the DEFAULT action. Matching on the name alone would charge every
## routine status call to build time.
##
## `actions=None` means the name alone settles it, which is correct for `propose_declaration`
## and for the historical `build_or_refresh` that committed transcripts still hold.
##
## A CALL WHOSE `action` IS ABSENT IS NOT COUNTED, deliberately fail-closed: absent resolves to
## `status` at the server, so treating it as a build would invent build time out of a read.
##
## The previous version of this comment claimed matching "by suffix … so a server rename cannot
## silently empty the set". The suffix was the right instinct against the wrong rename: the
## server kept its shape and the TOOL was renamed, which emptied the set exactly as described.
BUILD_TOOLS: tuple[tuple[str, frozenset[str] | None], ...] = (
    ("index", frozenset({"refresh"})),
    ("build_or_refresh", None),
)

## The tools whose wall time IS bringup: making the index exist, and working out what this
## repository needs stated before it can answer. `propose_declaration` belongs here because
## it is the correction surface (gh#360) — an agent that discovers at question one what
## bringup missed pays for the discovery, and charging that to the first QUESTION instead of
## to bringup is exactly the folding the owner ruled out.
BRINGUP_TOOLS: tuple[tuple[str, frozenset[str] | None], ...] = BUILD_TOOLS + (
    ("propose_declaration", None),
)


## @brief Does one `tool_use` block belong to a named (tool, actions) set?
## @param block A transcript `tool_use` content block.
## @param tools The (tool, actions) entries to test against.
## @return True when the block's tool and action are both covered.
## @version 1
def _is_one_of(block: dict, tools: tuple[tuple[str, frozenset[str] | None], ...]) -> bool:
    """Suffix on the tool name so any server alias matches, then the ACTION when the entry
    constrains one. The action is read from the call's own `input`, which is what a transcript
    records; a block with no `input` cannot be a constrained match and says so by failing.

    @brief Test a tool_use block against a (tool, actions) set.
    @return True when covered.
    @version 1
    """
    name = str(block.get("name", ""))
    payload = block.get("input")
    action = payload.get("action") if isinstance(payload, Mapping) else None
    return any(
        name.endswith(f"__{tool}") and (actions is None or action in actions)
        for tool, actions in tools
    )


## @brief Wall-clock ms a cell spent inside a named set of MCP tools, or None when it called none.
## @param path Transcript jsonl path.
## @param tools (tool, actions) entries whose calls should be summed.
## @return Summed elapsed milliseconds, or None when the cell called none of them.
## @version 2
def tool_wall_ms(path: Path, tools: tuple[tuple[str, frozenset[str] | None], ...]) -> int | None:
    """MEASURED FROM THE TRANSCRIPT, by pairing each `tool_use` with the `tool_result`
    carrying its id and differencing the two events' timestamps. It is the only place the
    figure exists: the work happens inside the cell's own MCP server process, and the runner
    never sees it.

    NONE, NOT ZERO, when there is no such call. A measured zero and "not applicable" must not
    share a spelling; the column writes empty for None, the same discipline `build_meta` uses
    when it drops falsy values so an absent key reads as "not recorded" rather than as a
    decision that was blank.

    @brief Sum the wall time a cell spent inside one set of tools.
    @return Elapsed milliseconds, or None.
    @version 2
    """
    started: dict[str, float] = {}
    total = 0.0
    for event in _events(path):
        stamp = _stamp(event.get("timestamp"))
        for block in _blocks_of(event):
            kind = block.get("type")
            if kind == "tool_use" and _is_one_of(block, tools):
                started[str(block.get("id", ""))] = stamp
            elif kind == "tool_result" and str(block.get("tool_use_id", "")) in started:
                total += max(0.0, stamp - started.pop(str(block.get("tool_use_id", ""))))
    ## Unpaired calls (a transcript truncated mid-build) contribute nothing rather than a
    ## guess. `started` non-empty with `total` 0.0 therefore reads as None, i.e. unmeasured.
    return round(total * 1000) if total else None


## @brief Wall-clock ms a cell spent inside `build_or_refresh`, or None when it called none.
## @param path Transcript jsonl path.
## @return Summed elapsed milliseconds, or None when the cell never built an index.
## @version 2
def build_ms(path: Path) -> int | None:
    """INCLUDES THE DOXYGEN RUN AND IS REPORTED UNSPLIT (owner decision, gh#360). It is what
    an operator actually waits for, so hiding doxygen behind a pre-warm would measure
    something no user experiences — and a cold mbedtls bringup being ~32 s of doxygen is
    allowed to be the headline, because that keeps the pressure on task #363 where it
    belongs. There is deliberately no doxygen sub-figure here; `status.refresh.stages`
    already carries the per-stage breakdown for anyone diagnosing rather than reporting.

    NONE, NOT ZERO, when there is no such call — which is EVERY source-arm cell and every
    index-arm cell that found a warm index.

    @brief Sum the wall time a cell spent building or refreshing its index.
    @return Elapsed milliseconds, or None.
    @version 2
    """
    return tool_wall_ms(path, BUILD_TOOLS)


## @brief Wall-clock ms a cell spent on BRINGUP — building plus working out what to declare.
## @param path Transcript jsonl path.
## @return Summed elapsed milliseconds, or None when the cell did no bringup.
## @version 1
def bringup_ms(path: Path) -> int | None:
    """ "BRINGUP IS A COST THAT MUST BE QUANTIFIED DIRECTLY" (owner, gh#360), and `build_ms`
    alone under-reports it by exactly the mechanism gh#360 adds. Step 0 of using this tool
    on any repository is the question "what do you want indexed?", and answering it costs
    `propose_declaration` runs — each of which re-runs pipeline importers against a copy of
    the index — as well as the build itself. Counting only the build would charge the
    discovery to whichever question happened to expose the gap, which is the folding the
    owner ruled out, and would make the mid-session-extension feature look free.

    A SUPERSET OF `build_ms`, reported BESIDE it rather than replacing it: they answer
    different questions ("what does a refresh cost" vs "what does standing this up cost")
    and one number cannot carry both. `bringup_ms == build_ms` is the honest reading for a
    cell that built and declared nothing, and it is the common case.

    @brief Sum the wall time a cell spent on index bringup.
    @return Elapsed milliseconds, or None.
    @version 1
    """
    return tool_wall_ms(path, BRINGUP_TOOLS)


## @brief Parse a transcript event's ISO-8601 timestamp into epoch seconds.
## @param raw The event's `timestamp` value.
## @return Epoch seconds, or 0.0 when absent or unparseable.
## @version 1
## @dg_internal
def _stamp(raw: object) -> float:
    """@brief Epoch seconds for a transcript timestamp.
    @return Seconds, 0.0 when unusable.
    @version 1
    """
    try:
        return datetime.fromisoformat(str(raw).replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


## @brief Yield each parseable JSON event of a transcript.
## @param path Transcript jsonl path.
## @return Iterator of event dicts, malformed lines skipped.
## @version 1
## @dg_internal
def _events(path: Path):
    """Malformed lines are skipped rather than fatal, matching `tool_calls` — a
    partially-flushed transcript must not take the sweep down.

    @brief Iterate a transcript's events.
    @return Generator of dicts.
    @version 1
    """
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            yield event


## @brief The message content blocks of one transcript event.
## @param event A transcript event dict.
## @return List of block dicts (empty when the event carries none).
## @version 1
## @dg_internal
def _blocks_of(event: dict) -> list[dict]:
    """@brief Extract an event's content blocks.
    @return Block list.
    @version 1
    """
    content = (event.get("message") or {}).get("content")
    return [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []


## @brief Test one tool name against a policy list, honouring MCP server entries.
## @param name Observed tool name.
## @param entries An allow or deny list out of ARM_POLICY.
## @return True when the list covers this name.
## @version 1
def _matches(name: str, entries: tuple[str, ...]) -> bool:
    """Exact match, OR an entry that names an MCP *server* covering one of its tools —
    the policy lists carry a bare `mcp__clew` alongside the per-tool names, and
    Claude Code reads that as "every tool on that server". Matching it exactly only
    would have reported five real tier-1 tools as unlisted.

    Non-MCP entries match EXACTLY on purpose. Prefix-matching `"Task"` out of the deny
    list would drag in the todo-list tools, which is the false positive
    `_SUBAGENT_PREFIXES` + `_NOT_SUBAGENTS` exist to keep separable.

    @brief Does a policy list cover this tool name?
    @return True when covered.
    @version 1
    """
    return any(name == entry or name.startswith(f"{entry}__") for entry in entries)


## @brief Does this tool name belong to a sub-agent-spawning family?
## @param name Observed tool name.
## @return True when the prefix rule catches it and nothing exempts it.
## @version 1
def _spawns_subagents(name: str) -> bool:
    """Prefix first, exemption second, so an UNKNOWN member of a known family is a
    violation by default. `TaskDelegate` would be caught; `TaskCreate` is exempt only
    because it is written down as exempt.

    @brief Prefix-match a spawner, minus the enumerated non-spawners.
    @return True when the name can delegate work off-transcript.
    @version 1
    """
    return name not in _NOT_SUBAGENTS and name.startswith(_SUBAGENT_PREFIXES)


## @brief Classify one observed tool name against an arm's policy.
## @param arm Arm the run belongs to.
## @param name Observed tool name.
## @return A labelled finding, or None when the arm was entitled to the tool.
## @version 1
def classify_tool(arm: str, name: str) -> str | None:
    """Order is severity order, and first match wins so one call yields one label.

    THE DENY CHECK IS DERIVED FROM `ARM_POLICY`, not restated. The bug this replaces was
    a restated literal — `{"Grep", "Glob", "Bash", "Task"}` — that had drifted from the
    policy it was meant to mirror: it omitted the whole of `_ALWAYS_DENIED` bar `Task`,
    so an `Edit` attempt in the `src` arm was invisible to the audit even though the
    deny flag itself had refused it. Deriving makes that class of drift impossible.

    AFTER gh#354 THE DERIVED DENY LIST IS TWO WEB TOOLS, which is not a weakening of this
    function — it is the policy that shrank. What used to be `tool:Grep` on the index arm is
    now a REVIEW finding from `review_findings`, because a source read is evidence about
    ordering rather than a rule break. This still fires on the web tools and would still fire
    on anything a future policy denies, without being told twice.

    @brief Label a tool call as spawn / denied / foreign-mcp / unlisted, or clear it.
    @return Finding label or None.
    @version 1
    """
    allowed, denied = ARM_POLICY[arm]
    label = None
    if _spawns_subagents(name):
        label = f"spawn:{name}"
    elif _matches(name, denied):
        label = f"tool:{name}"
    elif name.startswith(_ANY_MCP_PREFIX) and not name.startswith(MCP_READ_PREFIXES):
        label = f"foreign_mcp:{name}"
    elif not _matches(name, allowed):
        label = f"unlisted:{name}"
    return label


## @brief Scan a tool's arguments for DIRECT database access, bypassing the MCP surface.
## @param arm Arm the run belongs to.
## @param name Observed tool name.
## @param payload Serialized tool input.
## @return A finding label, or None.
## @version 2
def _text_violation(arm: str, name: str, payload: str) -> str | None:
    """THE HARD BAN, and now the only text-level one (gh#354). It fires on `sqlite3` or a
    `clew.db` path inside any non-index tool's arguments, because reaching the index outside
    the shipped MCP surface measures SQL-over-a-schema rather than the product.

    STILL SKIPS THE INDEX TOOLS THEMSELVES, and that exemption is load-bearing for the same
    reason it always was: a legitimate `search(text="clew.db")` — asking the index about its
    own filename, which the questions do — must not read as a violation. That false positive
    is the reference matrix's own recorded trap.

    `Read` IS NOW SCANNED, where it used to be exempt. With `Read` allowed on both arms it
    became the quiet route to the database: no shell verb appears, and the old regex could
    not have seen it.

    @brief Find direct database access outside the MCP surface.
    @return Finding label or None.
    @version 2
    """
    if arm != "mcp" or name.startswith(MCP_READ_PREFIXES):
        return None
    hit = _DB_DIRECT_ACCESS.search(payload)
    return f"db_direct:{name}:{hit.group(1)}" if hit else None


## @brief Findings that warrant a human look without invalidating the cell.
## @param arm Arm the run belongs to.
## @param name Observed tool name.
## @return A review label, or None.
## @version 1
def review_finding(arm: str, name: str) -> str | None:
    """THE OWNER'S REFRAME, MADE OBSERVABLE (gh#354): "a read on any other question should be
    immediately flagged for closer human review — the goal here is optimization to prove core
    hypothesis, but on a real usage, that doesnt mean that bash/read/write/edit go away, just
    that the index/db should be prioritized first".

    So neither of these is a rule break and neither clears `audit_clean`:

      source_read:<t>  the index arm read SOURCE. Legitimate — an agent that cannot answer
                       from the index should fall back rather than guess.
      mutation:<t>     the index arm wrote to the tree. Required by the edit-to-queryable
                       question and worth a look anywhere else.

    THESE ARE EXPLANATORY, NOT A PASS/FAIL TERM — owner, 2026-08-10, correcting an earlier
    framing in this file that called them "the evidence the hypothesis needs":

      "the intent here is that the hypothesis is that the index is better/cheaper than the
       straight bash tooling GENERALLY -> if the index arm is hitting grep 50 times vs
       defaults 60 times, that doesnt inherently fail the tool, so long as the index is still
       cheaper/better/faster-or-equal time to answer"

    `grep` is always available in a real session, so an index arm using it is not a defect and
    a high `review_count` is not a failing grade. The verdict is decided on tokens, time and
    completeness; this count EXPLAINS a verdict rather than contributing to it — a cheaper,
    faster, equally complete arm that fell back 50 times has still won, and knowing it fell
    back 50 times is how you find the next gap to close.

    Reading it as a score would invert the measurement: it would reward an arm that answered
    badly from the index alone over one that answered well by reaching for the right tool.

    ONLY THE INDEX ARM PRODUCES THESE. A source read by the source arm is the whole method,
    and labelling it would bury the signal under 100% noise — the shape of a guard that fires
    on the ordinary case.

    @brief Label a call that needs review rather than refusal.
    @return Review label or None.
    @version 1
    """
    if arm != "mcp":
        return None
    if name in _SOURCE_READING_TOOLS:
        return f"source_read:{name}"
    if name in _MUTATING_TOOLS:
        return f"mutation:{name}"
    return None


## @brief Audit one run's transcript against its arm's constraints.
## @param arm Arm the run belongs to.
## @param calls Tool calls extracted from the transcript.
## @return Dict with tool_uses, used_db_tools, audit_clean, violations and unlisted_tools.
## @version 4
def audit(arm: str, calls: list[tuple[str, str]]) -> dict:
    """Classify EVERY observed tool rather than looking for a handful of bad names, so a
    tool the harness gains later surfaces instead of being silently permitted.

    WHY `unlisted_tools` IS REPORTED BUT DOES NOT CLEAR `audit_clean`. `audit_clean`
    answers exactly one question: can this cell's numbers be compared against the other
    arm's? A tool that reads no source, queries no index and is equally reachable from
    both arms cannot bias that comparison — `TaskCreate` is bookkeeping, and failing 15
    cells of a completed run over it would discard sound measurements. A sub-agent
    spawner or a foreign MCP oracle CAN bias it, because the work happens somewhere the
    transcript does not record.

    So the two are kept in SEPARATE fields instead of being collapsed either way.
    Collapsing them into `violations` would make the flag fire on cases that are fine —
    and a guard that fires on the wrong cases is worse than no guard, because it teaches
    a reviewer to ignore it. Dropping them entirely would restore the silence this whole
    change exists to remove: an unexpected tool must be VISIBLE, and being visible is
    not the same as being disqualifying.

    THIS READS ATTEMPTS, NOT OUTCOMES, ON PURPOSE. Its input is `tool_use` blocks, so a
    denied tool that the flag refused still flags — and in the 0.5.0 evidence all four
    newly-flagged cells are exactly that: two refused `Edit` attempts, a foreign MCP call
    that errored because the server was not connected, and a typo'd tool name that cannot
    have existed. Nothing was contaminated. Flagging anyway is deliberate: verifying
    refusal would make `audit_clean` depend on the permission flags holding, and the flags
    are the layer this module has just finished documenting as NOT the enforcement. A cell
    that reached for a fenced tool is a cell a reviewer should look at, whatever came back.
    `db_tool_outcomes` pairs results where the question genuinely is "did it RETURN".

    THREE FIELDS NOW, NOT TWO (gh#354), because the arms stopped being a prohibition and a
    single flag can no longer carry the difference:

      violations     things that make a cell's numbers INCOMPARABLE — a sub-agent or foreign
                     oracle working off-transcript, a web fetch answering from neither arm,
                     direct database access measuring the wrong product. Clears `audit_clean`.
      review         the index arm read source or wrote to the tree. NEITHER is a rule break;
                     both are the ordering evidence the hypothesis rests on. Does NOT clear
                     `audit_clean`, because a cell that fell back to grep is a valid
                     measurement OF THE REAL QUESTION and discarding it would bias the result
                     toward the cells where the index happened to suffice.
      unlisted_tools outside the pre-approval list and none of the above. Reported only.

    THE COLLAPSE TO AVOID IS FOLDING `review` INTO `violations`. Post-gh#354 the index arm has
    `Read`/`Grep`/`Bash`, so on a hard question it will use them — a flag that fires there
    would mark most of the arm invalid and teach a reviewer to ignore it, which is this
    project's most-repeated defect and the reason `unlisted_tools` was split out first.

    @brief Audit a transcript for incomparability, ordering evidence and unlisted tools.
    @return Audit summary dict.
    @version 5
    """
    used_db = sum(1 for name, _ in calls if name.startswith(MCP_READ_PREFIXES))
    violations: list[str] = []
    review: list[str] = []
    unlisted: set[str] = set()
    for name, payload in calls:
        label = classify_tool(arm, name)
        if label is not None and label.startswith("unlisted:"):
            unlisted.add(name)
        elif label is not None:
            violations.append(label)
        text_hit = _text_violation(arm, name, payload)
        if text_hit:
            violations.append(text_hit)
        review_hit = review_finding(arm, name)
        if review_hit:
            review.append(review_hit)
    from collections import Counter

    # Per-tool histogram — the mechanistic signal that is far less noisy than
    # the token count. "Did the agent reach for chain_trace/dossier or use the
    # index as a slower grep (search+source)?" is answerable only from this.
    histogram = dict(sorted(Counter(name for name, _ in calls).items()))
    return {
        "tool_uses": len(calls),
        "used_db_tools": used_db,
        "audit_clean": not violations,
        "violations": violations,
        ## Counted as well as listed, because "the index arm fell back to source in 7 of 9
        ## cells" is the headline the reframe creates and a list of labels does not state it.
        "review": review,
        "review_count": len(review),
        "unlisted_tools": sorted(unlisted),
        "histogram": histogram,
    }


## @brief Re-audit every preserved transcript under an evidence directory.
## @param root Directory holding (or containing) `history/*.transcript.jsonl` files.
## @return Ordered (cell, arm, audit-dict) triples, one per transcript found.
## @version 1
def reaudit(root: Path) -> list[tuple[str, str, dict]]:
    """`evidence.py` preserves each cell's raw transcript precisely so a verdict can be
    RE-DERIVED when the checker changes, and this is that path. It exists because the
    alternative — trusting a recorded `audit_clean` that an older, weaker classifier
    produced — is how a wrong verdict survives a fix to the thing that made it wrong.

    The arm is read from the cell name (`Q7_haiku_src_r1`) rather than from the
    directory, because a directory can be renamed and a filename carries the fact.
    A transcript whose name encodes no known arm is SKIPPED and reported by absence
    rather than guessed at.

    Callers compare the result against the recorded `metrics.csv` themselves. This
    function NEVER writes: re-auditing published evidence must not be able to edit it.

    @brief Re-run the current audit over preserved transcripts.
    @return (cell, arm, audit) per transcript.
    @version 1
    """
    out: list[tuple[str, str, dict]] = []
    for path in sorted(root.rglob("*.transcript.jsonl")):
        cell = path.name.removesuffix(".transcript.jsonl")
        arms = [a for a in ARM_POLICY if f"_{a}_" in cell]
        if len(arms) == 1:
            out.append((cell, arms[0], audit(arms[0], tool_calls(path))))
    return out


if __name__ == "__main__":
    import sys

    ## Usage: .venv/bin/python acceptance/bench/bench_arms.py reaudit <evidence-dir>...
    if len(sys.argv) < 3 or sys.argv[1] != "reaudit":
        raise SystemExit("usage: bench_arms.py reaudit <evidence-dir> [<evidence-dir>...]")
    flagged = 0
    reviewable = 0
    for target in sys.argv[2:]:
        rows = reaudit(Path(target))
        print(f"== {target}: {len(rows)} transcripts")
        for cell, arm, result in rows:
            notes = [
                *result["violations"],
                *result["review"],
                *(f"unlisted:{t}" for t in result["unlisted_tools"]),
            ]
            if notes:
                flagged += bool(result["violations"])
                reviewable += bool(result["review"])
                print(f"  {cell} [{arm}] clean={result['audit_clean']} {notes}")
    ## REPORTED APART, because they mean opposite things: a violation says the cell cannot be
    ## compared, while a review count is the RESULT — how often the index arm fell back to
    ## source is the reframe's own headline, not a defect tally.
    print(f"cells that cannot be compared: {flagged}")
    print(f"cells where the index arm also read source or wrote: {reviewable}")


## @brief Characters of tool RESULT text a cell actually received.
## @param path Transcript jsonl path, or None.
## @param db_only True to count only results from index tools.
## @return Total result characters; 0 when the transcript is absent.
## @version 1
def result_bytes(path: Path | None, db_only: bool = False) -> int:
    """WHAT `total_tokens` IS NOT. Measured on the p5-both run and reproduced exactly:
    `total_tokens` sums cache_read + cache_creation + in + out over API round trips, and this
    harness carries a ~80k static prompt, so the figure is a ROUND-TRIP COUNTER times a constant
    that belongs to neither arm. On one question the source arm took 16 round trips to the index
    arm's 6 (2.67x) and their token totals differed by 2.60x — while the INDEX arm had retrieved
    21% MORE result text and finished with a larger context. Under 1% of the reported difference
    was retrieval.

    Round trips are also confounded by BATCHING, which is not a controlled variable: two
    independent lookups issued in one message cost one round trip and read the same bytes as two.
    The index arm batches naturally (independent symbol lookups); an adaptive grep sequence cannot.

    So this counts the one thing neither of those distorts: the characters of tool output the model
    was actually given. CHARACTERS, NOT TOKENS, deliberately — a token count here would need a
    tokenizer this harness does not carry, and the comparison is a ratio between arms, which the
    unit does not change.

    PAIRING IS NOT NEEDED and is deliberately skipped: every `tool_result` counts, errors included,
    because an error message is text the model had to read. `db_only` restricts to results whose
    `tool_use` carried the index prefix, which DOES require pairing — that is the one case where it
    matters, since the question is what the INDEX delivered.

    @brief Sum the tool-result text a cell received.
    @return Result characters.
    @version 1
    """
    if path is None or not path.exists():
        return 0
    wanted: set[str] = set()
    total = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        content = (event.get("message") or {}).get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "tool_use":
                if str(block.get("name", "")).startswith(MCP_READ_PREFIXES):
                    wanted.add(str(block.get("id", "")))
            elif block.get("type") == "tool_result":
                if db_only and str(block.get("tool_use_id", "")) not in wanted:
                    continue
                total += len(_result_text(block.get("content")))
    return total


## @brief Flatten a tool result's content to plain text.
## @param content Result content: a string, or a list of blocks.
## @return Flattened text.
## @version 1
## @dg_internal
def _result_text(content: object) -> str:
    """@brief Reduce result content to one string.
    @return Text.
    @version 1
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""
