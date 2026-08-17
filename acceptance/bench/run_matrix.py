## @brief Benchmark runner: (question x arm x model x run) sweeps of `claude -p`.
## @version 1
"""Drive the acceptance matrix as a grid of fresh headless `claude -p`
processes, one per cell, and record structured metrics for each.

Design points that matter:

- **A cell is a process, not a subagent.** Fresh context, real MCP stdio server, and
  `--allowedTools`/`--disallowedTools` fencing the tools that decide the comparison —
  source-reading tools on one side, index tools on the other, each denied to the other arm
  and audited afterwards from the transcript (`bench_arms.audit`). The flags are NOT a strict
  whitelist: a calibration cell used `TaskCreate`/`TaskUpdate`, which appear in neither allow
  list. Symmetric across arms, so not a bias — but the audit is what enforces isolation, not
  the flags alone.
- **Neutral working directory.** Cells run in an empty scratch dir with
  `--add-dir <target>`, so the target repo's own `CLAUDE.md`, `.mcp.json` and
  `.claude/settings*` cannot leak architecture knowledge into an answer or
  attach foreign MCP servers. Only the user's global memory applies, equally
  to both arms.
- **Resumable.** A cell whose answer file already exists is skipped, so an
  interrupted sweep is restarted by re-running the same command. An INVALID cell's stub is
  deleted, so a failure is retried rather than mistaken for finished work.
- **Validity means the index ANSWERED, not that it was called.** An `mcp` cell scores
  `valid=false` unless a `mcp__clew__*` tool actually returned. Counting attempts
  scored a cell VALID whose server never spawned and whose own answer said it could not reach
  the index.
- **Budgeted in TOKENS.** Session capacity is the binding constraint and it is metered in
  tokens; a dollar figure is that same number times a price sheet that drifts.

TARGET-AGNOSTIC BY CONSTRUCTION. `--target` and `--questions` are both required and neither has
a default; nothing here holds a target name, a target path or a target-derived figure, and no
code branches on which target is running. Adding a target is: clone it, build its index, write
`acceptance/targets/<target>/questions.md`, and pass the two paths below. No file in
`acceptance/bench/` or `acceptance/method/` changes. A predecessor of this module carried a
checked-in server config instead, pinned to one target; it invalidated a whole grid.

Usage:
  .venv/bin/python acceptance/bench/run_matrix.py run \
      --target <target repo root> \
      --questions acceptance/targets/<target>/questions.md \
      --arm both --model haiku --runs 1 --questions-filter Q1 --out <dir>
  .venv/bin/python acceptance/bench/run_matrix.py report --out <dir>

The MCP config is GENERATED from `--target`, never hand-written. A published
36-cell grid was invalidated because a checked-in config pinned the index arm to
a different repository than the questions asked about, and every validity term
verified that the agent CALLED database tools while none verified the database
held the RIGHT repository. `preflight_target` closes the same hole structurally.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import bench_publish
import target_check
from bench_rubric import (
    load_rubric,
    marks_on_the_exam,
    parse_questions_yaml,
    preflight_rubric_provenance,
    rubric_front_matter,
)
from bench_arms import (
    audit,
    bringup_ms,
    build_ms,
    db_tool_outcomes,
    result_bytes,
    find_transcript,
    permission_flags,
    tool_calls,
)

HERE = Path(__file__).resolve().parent


## @brief Locate the repo root by walking up to the marker file.
## @return Directory containing `pyproject.toml`.
## @version 1
## @dg_internal
def _repo_root() -> Path:
    """NOT a hardcoded `.parent` count, because this module has now been relocated twice.
    It once read `HERE.parent.parent.parent`, correct only while it lived three levels
    deep; moving it silently retargeted REPO_ROOT one level ABOVE the checkout, pointing
    the index arm's server command at a `.venv` that does not exist — an `mcp` arm with
    no server, answering from priors, scored as a valid cell.

    Anchoring on a marker makes the location a fact about the repo rather than an
    assumption about this file's depth, which is why the move to `acceptance/bench/`
    needed no edit here.

    @brief Find the checkout root.
    @return Repo root path.
    @version 1
    """
    for candidate in (HERE, *HERE.parents):
        if (candidate / "pyproject.toml").is_file():
            return candidate
    raise SystemExit(f"cannot locate repo root above {HERE} (no pyproject.toml)")


REPO_ROOT = _repo_root()


# THE SERVER CONFIG IS GENERATED PER RUN, FROM --target. It used to be a checked-in file,
# `mcp-bench.json`, whose own comment said it was "pinned to the sanitized target" — a
# leftover from an earlier grid against a sanitized copy of another repo. When the target
# changed, nobody updated it, so the server was launched against a SELF-INDEX of this
# repository's own Python while every question asked about a C++ engine an order of magnitude
# larger.
#
# 15 of 18 index-arm cells detected it and said so. The whole grid was retracted.
#
# A static file cannot be right for two targets, so there is no longer a static file. The
# server's repo is DERIVED from the same argument the questions are about, which makes the
# two impossible to disagree.
def mcp_config_for(target: Path, out_dir: Path) -> Path:
    """Write a per-run MCP server config pointing at THIS run's target.

    Absolute paths throughout, and a `--repo` per target. A cell runs in a scratch cwd
    (`<out>/wd`), so anything relative resolves against that rather than the repo and the
    server never launches at all — which is how an early sweep died in 223 ms with every
    row recorded `valid=False`.

    ONE PROCESS PER TARGET IS NOW A CHOICE, AND IT IS STILL THE RIGHT ONE HERE. The server
    takes a `target` per CALL, so a single process could serve every cell in a sweep — but
    a benchmark arm must not be able to answer about a repository the cell was not asked
    about. `--repo` makes the default target the only one a cell can reach without naming
    another, which is the property that keeps `metrics.csv` attributable to a target. The
    grid that had to be retracted was retracted for exactly the opposite failure.

    @brief Generate the arm's MCP config for one target.
    @return Path to the written config.
    @version 3
    """
    ## The SHIPPED entry builder, not a hand-rolled copy. A literal dict here is what went
    ## stale last time; if the entry shape ever gains a field, both surfaces move together.
    sys.path.insert(0, str(REPO_ROOT))
    from clew.mcp_config import server_entry

    config = out_dir / "mcp-bench.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    entry = server_entry(
        str(REPO_ROOT / ".venv" / "bin" / "clew-mcp"),
        repo=str(target),
    )
    ## THE ONE ARTIFACT WRITTEN UN-NORMALISED, and it must stay that way.
    ##
    ## This file is EXECUTED, not read. An MCP client spawns `command` directly — there is no
    ## shell, so a leading `~` is a literal directory name and the server simply never starts.
    ## Routing this through `bench_publish` (which every other artifact correctly uses) rewrote
    ## the command to `~/…/clew-mcp` and produced a cell that ran for a full minute,
    ## reported "No such tool available", and was scored VALID. The sanitiser broke the thing
    ## it was protecting.
    ##
    ## Committing it is still safe: `mcp_config_for` regenerates this file on EVERY cell, so
    ## `cmd_sanitise` may normalise it before a commit and a resumed sweep overwrites it with
    ## absolute paths again on the first cell it runs.
    config.write_text(
        json.dumps({"mcpServers": {"clew": entry}}, indent=2) + "\n", encoding="utf-8"
    )
    return config


## THE SCHEMA OF AN APPEND-ONLY FILE, so changing it is not free. `append_row` writes the
## header once and then appends; a run directory created under an older field list holds rows
## positioned by THAT header, so appending a wider row to it misaligns every value after the
## new column and every downstream reader silently reads the wrong field. `append_row`
## therefore compares the existing header against this list and REFUSES rather than appending
## — a resumed sweep whose `metrics.csv` predates a schema change must be given a fresh --out
## (the answer files are what resumption actually keys on, so re-running is cheap: complete
## cells are skipped and only the CSV starts over).
##
## `build_ms` was documented in `acceptance/method/methodology.md` before it existed here.
## It is EMPTY, not 0, for a cell that never built an index — see `bench_arms.build_ms`.
##
## `bringup_ms` is a FOURTH AXIS beside tokens, time and completeness (gh#360, owner: "bringup
## is a cost that must be quantified directly"). It is a superset of `build_ms` — the build
## plus the `propose_declaration` runs an agent needs to work out what this repository has to
## declare — and both are kept, because "what does a refresh cost" and "what does standing
## this up cost" are different questions and folding either into the other is how this
## project's earlier grids produced convenient verdicts.
CSV_FIELDS = [
    "target", "q", "arm", "model", "run",
    "tokens_in", "tokens_out", "cache_read", "cache_creation", "total_tokens",
    "tool_uses", "result_bytes", "db_result_bytes",
    "num_turns", "duration_ms", "build_ms", "bringup_ms", "cost_usd",
    "used_db_tools", "audit_clean", "review_count", "target_ok", "valid", "answer_path",
]  # fmt: skip

## Per-cell TOKEN estimates for the pre-flight guard. Owner decision 2026-07-31: budget in
## tokens, not dollars. A dollar figure is a direct conversion from a token count against a
## price sheet, so it stores the same information plus a dependency on rates that drift — and
## session capacity, the constraint that actually binds a sweep, is metered in tokens anyway.
##
## TARGET-AGNOSTIC BY CONSTRUCTION, and that is a correction rather than a nicety. This table
## used to be captioned with the specific repository and question its figures came from, which
## made a budget guard in a shared harness hold one target's numbers — the same shape as the
## checked-in config that pinned a whole grid to the wrong repository. A person adding a new
## target must not have to measure it before they can plan a sweep.
##
## So these are a CONSERVATIVE DEFAULT, not a measurement of anything: source-arm medians
## rounded up, because the guard exists to refuse a sweep that cannot finish and must therefore
## over-estimate. Taking the cheaper arm's figure would under-count every source cell.
##
## A target whose cells are known to cost more overrides with `--est-tokens-per-cell`, and
## `report` prints the observed medians per arm and model once a run exists. The measured
## figures for a given target belong in THAT TARGET'S result document, never here.
##
## This constant has been wrong in both directions before, and both times because it was
## guessed: the originals were 4x LOW; their replacement guessed opus at 4x sonnet and came out
## 2.5x HIGH, which is the direction that gets a grid refused for a budget it never needed.
DEFAULT_EST_TOKENS_PER_CELL = {"haiku": 1_900_000, "sonnet": 3_300_000, "opus": 3_500_000}

## THE MODEL ALIASES THE HARNESS ACCEPTS, split out from the estimate table on purpose. `_models`
## used to validate `--model` against the KEYS of the budget table, which quietly made "a tier we
## have a token estimate for" and "a tier that may be benchmarked" the same set. They are not the
## same question, and coupling them means adding a tier requires inventing a budget figure for it.
KNOWN_MODELS = ("haiku", "sonnet", "opus")

## Consecutive invalid cells that mean "systematic fault", not "one bad cell".
##
## Two is the right number because the failure this catches is CONFIGURATION, and a
## misconfiguration fails every cell identically. Measured: a relative `--out` killed the
## index arm in 223ms per cell while recording valid=False — and invalid rows are EXCLUDED
## from the report's aggregates, so 198 dead cells would have surfaced as a clean-looking
## source-arm-only table rather than as an error.
MAX_CONSECUTIVE_INVALID = 2

_Q_HEADING = re.compile(r"^#\s+(Q\d+)\s*[—–-]\s*(.+?)\s*$")


## An index-arm answer saying the served database is not the target repo. Detected from the
## ANSWER rather than by interrogating the server, because the agent is the one surface that
## actually noticed — 15 of 18 cells reported it in prose while every structural check passed.
## Belt and braces: `mcp_config_for` should make the mismatch impossible, and this catches the
## case where it does not.
## @brief Refuse to run a matrix against an index built by a different pipeline version.
## @param db Path to the index the MCP server will serve.
## @return None; raises SystemExit on any skew, including an unstamped index.
## @version 1
## @dg_internal
def _preflight_index_version(db: Path) -> None:
    """THE GUARD THAT WOULD HAVE CAUGHT THE 2026-08-05 NO-GO. Both grading keys were pinned to
    build 16/17 ground truth, both served indexes were still AT 17, and
    `CLEW_BUILD_VERSION` was 27. `preflight_target` checked existence, path count and
    sampled path resolution — every term passed, because a stale index is a perfectly valid
    index of the right repository. It just answers from an older pipeline.

    THE SKEW IS NOT SYMMETRIC, which is why this is fatal rather than a warning. The source
    arm reads an unmoved source tree and cannot be penalised by index drift; only the index
    arm can. A ~198-cell sweep would therefore have marked the arm under test wrong for being
    correct, and this project has already voided a 396-cell grid that way.

    AN UNSTAMPED INDEX IS ALSO FATAL. `read_build_signature` returns None for a database with
    no `build_meta` row, and "I cannot tell which pipeline built this" is not a pass — it is
    the same unchecked state the guard exists to remove.

    @brief Compare the served index's stamped build version against the pipeline's.
    @return None.
    @version 1
    """
    from clew.signature import (
        CLEW_BUILD_VERSION,
        read_build_signature,
    )

    stamped = read_build_signature(db)
    if stamped == CLEW_BUILD_VERSION:
        return
    held = "no build_version stamped" if stamped is None else str(stamped)
    raise SystemExit(
        "preflight: STALE INDEX — refusing to run a matrix against it.\n"
        f"  index build_meta.build_version : {held}\n"
        f"  CLEW_BUILD_VERSION     : {CLEW_BUILD_VERSION}\n"
        f"  index: {db}\n"
        "  A stale index answers every question without complaint, and the drift is "
        "ONE-DIRECTIONAL: the source arm reads an unmoved tree, so only the index arm can be "
        "penalised for it.\n"
        "  Rebuild with `clew build --repo <target>` (or `build_or_refresh`) and "
        "re-run."
    )


## @brief Refuse to run unless the served index actually indexes the target.
## @param target Resolved target repo root.
## @return None; raises SystemExit when the index does not match or is stale.
## @version 2
def preflight_target(target: Path) -> None:
    """Refuse to sweep against a missing or foreign index.

    WHAT IT DOES NOT CATCH, said first because overclaiming a guard is this project's
    recurring failure. It cannot detect the defect that invalidated the 2026-07-30 grid: the
    server was pinned by CONFIG to a different repo than the questions asked about, and
    `target_for(X)` resolves the index built FOR X, so target-and-its-own-index agree by
    construction. That defect is fixed structurally in `mcp_config_for`, which derives
    `--repo` from the same `--target` the questions use, so the two can no longer disagree.
    A check here would be theatre.

    A PROSE VERSION WAS WRITTEN AND DROPPED. Agents phrase "wrong repository" a dozen ways; a
    target-agnostic regex caught 4 of the 15 real cases and false-positived on a raw-arm
    cell. An unreliable guard is worse than none — it converts "unchecked" into "checked and
    fine", which is how the leak, the disarmed coverage gate and that grid all shipped.

    WHAT IT DOES CATCH, and it caught it immediately: a target with NO index, or one whose
    indexed paths do not exist under the target root. The first control run found the target
    had no index at its canonical location at all — every build had gone to a scratch path —
    so the sweep would have run against nothing and produced 36 confidently empty cells.

    AND, since 2026-08-05, A STALE INDEX. See `_preflight_index_version`: an index built by an
    older pipeline answers every question without complaint, and the resulting drift is
    one-directional against the arm under test.

    @brief Abort the sweep unless the served index belongs to the target and matches the build.
    @return None.
    @version 2
    """
    sys.path.insert(0, str(REPO_ROOT))
    import sqlite3

    from clew.mcp_server.state import target_for

    db = Path(target_for(target).db_path)
    if not db.is_file():
        raise SystemExit(f"preflight: no index for {target} at {db} — build it before running")
    _preflight_index_version(db)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        rows = [r[0] for r in conn.execute("SELECT name FROM path WHERE type = 1 LIMIT 40")]
    finally:
        conn.close()
    if not rows:
        raise SystemExit(f"preflight: {db} indexes no files — it cannot answer anything")
    ## Indexed paths are repo-root-relative (build 9 onward), so resolve each against the
    ## target and require it to exist there. A self-index served for a C++ target fails on
    ## the first row.
    missing = [name for name in rows if not (target / name).exists()]
    if len(missing) > len(rows) // 2:
        raise SystemExit(
            f"preflight: {db} does not index {target}\n"
            f"  {len(missing)} of {len(rows)} sampled paths do not exist under the target, "
            f"e.g. {missing[:3]}\n"
            "  This is the defect that invalidated the 2026-07-30 grid: the server was "
            "pinned to a different repository than the questions asked about."
        )
    print(f"preflight OK: {db} indexes {target} ({len(rows) - len(missing)}/{len(rows)} sampled)")


## Environment overrides applied to EVERY cell, both arms alike.
##
## ENABLE_TOOL_SEARCH=false is load-bearing. With tool search on, Claude Code
## defers *every* MCP tool behind a `ToolSearch` lookup while leaving built-ins
## (Read/Grep/Bash) directly callable. The first pilot caught the consequence:
## the mcp arm burned all 16 of its turns in a ToolSearch loop and never
## invoked a single docs-db tool, while the src arm was untouched. That is a
## harness artifact biased against exactly the thing being measured, so the
## feature is turned off for both arms.
CELL_ENV = {"ENABLE_TOOL_SEARCH": "false"}


## @brief Parse the frozen questions out of a matrix markdown file.
## @param path Matrix markdown path.
## @return Ordered list of {id, title, text} dicts.
## @version 1
def parse_questions(path: Path) -> list[dict[str, str]]:
    """A question is an `# Q<n> — <title>` heading followed by a blockquote
    whose first line marks it frozen. Only the blockquote is sent to the
    agent; the verified chain and mark checklist below it are grader-only and
    must never reach a candidate.

    @brief Extract the frozen question text for each Q section.
    @return List of question records.
    @version 1
    """
    ## THE YAML KEY IS THE LIVE ONE (P2). Dispatching HERE rather than at each call site means a
    ## consumer that passes `--questions .../questions.yaml` needs no change and cannot be
    ## half-migrated — the shape of defect this session spent its first four commits on.
    if path.suffix in (".yaml", ".yml"):
        return parse_questions_yaml(path)
    questions: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    quote: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _Q_HEADING.match(line)
        if heading:
            current = {"id": heading.group(1), "title": heading.group(2), "text": ""}
            quote = []
            questions.append(current)
            continue
        if current is None or current["text"]:
            continue
        if line.startswith(">"):
            quote.append(line.lstrip("> ").rstrip())
        elif quote:
            current["text"] = " ".join(q for q in quote if q)
    body = re.compile(r"\*\*Question \(frozen\)\.\*\*\s*")
    for q in questions:
        q["text"] = body.sub("", q["text"]).strip()
    return [q for q in questions if q["text"]]


## @brief Compose the prompt for one cell.
## @param arm Arm name.
## @param target Target repo root.
## @param question Question record.
## @return The full prompt text.
## @version 1
def build_prompt(arm: str, target: Path, question: dict[str, str]) -> str:
    """Brief verbatim (only `{TARGET}` substituted) plus the frozen question.
    Nothing arm-specific beyond the tool description is added — no strategy
    coaching, no stop rule — because that would change what is measured.

    @brief Build the arm's brief + the frozen question.
    @return Prompt string.
    @version 1
    """
    brief = (HERE / f"_brief_{arm}.md").read_text(encoding="utf-8")
    brief = brief.replace("{TARGET}", str(target))
    return f"{brief}\n\n---\n\n## QUESTION ({question['id']})\n\n{question['text']}\n"


## @brief Build the exact `claude` argv for one cell.
## @param arm Arm name.
## @param model Model alias.
## @param prompt Full prompt text.
## @return argv list.
## @version 1
def build_argv(arm: str, model: str, prompt: str, target: Path, mcp_config: Path) -> list[str]:
    """BOTH ARMS PASS `--strict-mcp-config`, AND THE SRC ARM'S IS THE LOAD-BEARING ONE. This
    docstring used to claim "the src arm never sees the server at all, which is a stronger
    guarantee than denying its tools". THAT CLAIM WAS FALSE, and it was false in the direction that
    silently destroys the comparison.

    `--strict-mcp-config` means "use ONLY the config given on this command line". WITHOUT it,
    `claude -p` loads the USER'S GLOBAL MCP CONFIGURATION — and on the machine this grid runs on,
    that configuration has clew connected. So omitting `--mcp-config` for the src arm did
    not remove the server; it handed the src arm the operator's own servers.

    MEASURED on the p5-both run, 2026-08-15, by reading the transcripts: the SOURCE arm's context
    carried the clew instructions block, including verbatim a sentence describing a prior
    measured result for the very question it was answering. `used_db_tools: 0` therefore recorded
    that the src arm CHOSE not to call the index, not that it COULD not — a behavioural check
    standing in for a structural one, which is the exact failure this project already recorded when
    a whole grid was invalidated by validity terms that verified behaviour instead of structure.

    The fix is one flag and it is unconditional. With no `--mcp-config` alongside it,
    `--strict-mcp-config` yields ZERO servers, which is what the src arm's brief has always
    claimed. Verified directly: `claude -p --strict-mcp-config` with no config file reports no
    `mcp__` tools available, while the same invocation without the flag inherits the global set.

    @brief Assemble the headless `claude -p` argv for a cell.
    @return argv list.
    @version 2
    """
    argv = [
        "claude", "-p", prompt,
        "--model", model,
        "--output-format", "json",
        "--add-dir", str(target),
        ## UNCONDITIONAL. On the mcp arm it scopes the server set to the config below; on the src
        ## arm it is the entire fence.
        "--strict-mcp-config",
    ]  # fmt: skip
    if arm == "mcp":
        ## Generated from THIS run's target rather than read from a checked-in file. The
        ## static file was pinned to a different repo and invalidated a whole grid.
        argv += ["--mcp-config", str(mcp_config)]
    return argv + permission_flags(arm)


## @brief Execute one cell and return its metrics row.
## @param arm Arm name.
## @param model Model alias.
## @param question Question record.
## @param run Run index (1-based).
## @param opts Parsed CLI options.
## @return Metrics row dict.
## @version 3
## The operator's OPT-IN to a destructive per-cell restore. `restore_target` runs
## `git checkout -- .` and `git clean -fd` inside the target, which DELETES uncommitted work
## and untracked files — so it must never be pointed at a live checkout. `--target` is an
## arbitrary path an operator types, and a path cannot be inspected for whether somebody is
## working in it, so the tree itself has to say it is disposable.
##
## A MARKER FILE rather than a path heuristic ("is it under acceptance/targets/?"), because a
## heuristic is satisfiable by accident — a symlink, a clone made somewhere convenient — and
## the failure mode here destroys a person's work rather than producing a wrong number. This
## file cannot appear by accident.
RESTORE_MARKER = ".acceptance-disposable"

## Environment variables that tell git WHICH repository to operate on, regardless of `cwd` or `-C`.
## Stripped before any destructive restore, because `GIT_DIR` silently wins over both — gh#386
## records git subprocesses in this harness inheriting exactly that from a pre-commit hook, and a
## `git clean -fd` pointed at the wrong repository deletes the operator's untracked work in it.
##
## `GIT_ASKPASS` and `GIT_EDITOR` are deliberately NOT here: they choose a helper program, not a
## repository, and stripping them would change unrelated behaviour for no safety gain.
_GIT_LOCATION_VARS = frozenset(
    {"GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR", "GIT_OBJECT_DIRECTORY"}
)


## @brief Is this target a clone the harness is permitted to reset destructively?
## @param target Target repo root.
## @return True when the disposable marker is present.
## @version 1
def target_is_disposable(target: Path) -> bool:
    """@brief Check the destructive-restore opt-in.

    @return True when the marker file exists.
    @version 1
    """
    return (target / RESTORE_MARKER).is_file()


## @brief Refuse the whole sweep up front when the target is not marked disposable.
## @param target Target repo root.
## @return None; raises SystemExit when the marker is absent.
## @version 1
def restore_target_preflight(target: Path) -> None:
    """THE ONE PLACE THE REFUSAL IS WRITTEN. `restore_target` calls this rather than repeating
    the check, because two copies of one rule is how a rule ends up defended in only one of
    them — measured on `pinned_guard_rev`, where the second copy could be stripped entirely
    with 867 tests still green.

    It deliberately does NOT restore anything. A preflight that mutated the tree would make
    `--dry-run` destructive, and a dry run exists to be safe.

    @brief Fail early when per-cell restore is impossible.
    @version 1
    """
    if not target_is_disposable(target):
        raise SystemExit(
            f"REFUSING to start: {target} carries no {RESTORE_MARKER} marker, so the per-cell\n"
            f"  tree+index restore cannot run — and without it a mutating cell's edits survive\n"
            f"  into every later cell of the sweep.\n"
            f"  Per-cell restore runs `git checkout -- .` and `git clean -fd` in that tree,\n"
            f"  which DELETES uncommitted work and untracked files.\n"
            f"  If and ONLY IF this is a disposable pinned clone, opt in with:\n"
            f"      touch {target / RESTORE_MARKER}\n"
            f"  Never do this in a checkout you work in. To measure without the restore and\n"
            f"  say so in the result, pass --no-restore."
        )


## The document a target's own conventions are stated in, and it lives BESIDE THE RUBRIC.
##
## THAT SIBLING RELATION IS THE STRUCTURAL PART. A third-party clone must stay byte-identical
## — the per-cell restore `git clean`s it — so the declaration cannot live in the target, and
## anything else would be a second path an operator states separately from `--questions`.
## Deriving it from the rubric's own directory means the grading key and the build policy
## cannot describe different targets, which is the same fix that made `mcp_config_for` derive
## `--repo` from `--target` after a config pinned to the wrong repository voided a 36-cell grid.
DECLARATION_NAME = "declaration.yaml"


## @brief The declaration document stated for a target, derived from its rubric's directory.
## @param questions Path to the target's questions.md.
## @return The declaration path when the target has one, else None.
## @version 1
def declaration_for(questions: Path) -> Path | None:
    """ABSENT IS THE NORM. Most targets declare nothing and build entirely on defaults, so a
    missing file is not an error — but a PRESENT one that never reaches the build is, which is
    what `preflight_declaration_applied` exists to catch.

    @brief Locate a target's stated declaration document.
    @return The path, or None when the target declares nothing.
    @version 1
    """
    candidate = questions.expanduser().resolve().parent / DECLARATION_NAME
    return candidate if candidate.is_file() else None


## @brief Refuse to run unless the target sits at the revision its rubric declares.
## @param target Resolved target repo root.
## @param questions Path to the rubric, whose front matter declares `commit:`.
## @return None; raises SystemExit on a mismatch or an unpinned rubric.
## @version 1
def preflight_target_revision(target: Path, questions: Path) -> None:
    """THE HARNESS PINNED THE WORKING TREE AND NEVER THE REVISION. `restore_target` runs
    `git checkout -- .` and `git clean -fd`, which restores modified files and never moves HEAD;
    `preflight_target` proves the index covers the right PATH. Nothing compared the target's HEAD
    against the rubric's own `commit:`.

    MEASURED 2026-08-15: entropic's rubric declares `6dcb4c8` and the clone sat at `ab163bf`
    (v2.10.4) — with the declared commit ABSENT FROM THE CLONE ENTIRELY. Every figure in that key,
    source-derived and index-derived alike, described a tree the run would not have used. mbedtls
    passes this only because its clone happens to sit at its rubric's commit, which is luck.

    THE SAME SHAPE AS THE DEFECT THAT VOIDED AN EARLIER GRID, one key over. There, every validity
    term verified the agent CALLED database tools and none verified the database held the RIGHT
    REPOSITORY. Here they verify the right repository and none verified the right REVISION. A grid
    is equally invalid pointed at the right repo at the wrong commit, and worse, it fails quietly:
    the figures simply drift, in whichever direction penalises the arm the rubric was written for.

    REFUSES AN UNPINNED RUBRIC TOO, and that half is deliberate. A key with no `commit:` cannot be
    validated against anything — "which tree were these numbers measured on" has no answer — so
    treating a missing pin as permission would make the guard vacuous on exactly the rubrics that
    need it most. Fail closed on absence, the same rule `preflight_rubric_provenance` applies to a
    missing provenance key.

    @brief Refuse a target whose HEAD is not the rubric's declared commit.
    @version 1
    """
    declared = (rubric_front_matter(questions) or {}).get("commit", "").strip()
    if not declared:
        raise SystemExit(
            f"preflight: UNPINNED GRADING KEY — {questions}\n"
            "  It declares no `commit:`, so nothing says which revision its figures describe.\n"
            "  A key that names no tree cannot be checked against one. Declare the commit the\n"
            "  ground truth was measured on."
        )
    head = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    ).stdout.strip()
    if not head:
        raise SystemExit(f"preflight: {target} is not a git checkout — cannot verify its revision")
    if not head.startswith(declared) and not declared.startswith(head):
        present = subprocess.run(
            ["git", "-C", str(target), "cat-file", "-t", declared],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        raise SystemExit(
            f"preflight: TARGET IS AT THE WRONG REVISION — refusing to run.\n"
            f"  rubric declares : {declared}\n"
            f"  target HEAD     : {head}\n"
            f"  target          : {target}\n"
            f"  declared commit is {'present in the clone' if present else 'NOT IN THE CLONE'}\n"
            "  Every figure in the key describes the declared tree. Check the target out at that\n"
            "  commit (fetch it first if absent), or re-measure the key against HEAD and re-declare."
        )


## @brief Refuse to run unless the served index was built with the target's declaration.
## @param target Resolved target repo root.
## @param declaration The stated declaration document, or None when the target has none.
## @return None; raises SystemExit when the document did not reach the index.
## @version 1
def preflight_declaration_applied(target: Path, declaration: Path | None) -> None:
    """THE GUARD THAT WOULD HAVE CAUGHT THE 2026-08-14 INVALID SPOT CHECK, and the defect is a
    new shape of an old one. `preflight_target` proves the index is of the right repository and
    `_preflight_index_version` proves it came from the current pipeline. Both passed. What
    neither could ask is whether the index was built with the POLICY the target requires: the
    committed mbedtls declaration states `locks`, `vendored` and `preprocessor`, and the graded
    index held `options.locks.tier=explicit` — replayed from an older build — beside
    `options.predefined.tier=heuristic` and no vendored row anywhere.

    The cause was in this file: `restore_target` rebuilt the index before every cell and passed
    no `declare=`, so each restore quietly replaced a declared index with an undeclared one.
    Three landed pipeline fixes were therefore invisible to the measurement built to test them,
    and fourteen of Q4's marks were unanswerable by any call the agent could make.

    A GRID CAN BE INVALID FOR POINTING AT THE RIGHT REPOSITORY BUILT THE WRONG WAY. That is one
    turn past the lesson this project already carries, and it is why the check is structural: it
    compares the document's SHA, not a count of sections and not whether the build "looks
    declared". A sha mismatch also catches the subtler half — the document edited after the
    build that stated it, which is exactly how `vendored` and `preprocessor` went missing while
    `locks` still reported explicit.

    @brief Compare the stated declaration against what the index records was stated.
    @return None.
    @version 1
    """
    if declaration is None:
        print("preflight OK: this target states no declaration document")
        return
    sys.path.insert(0, str(REPO_ROOT))
    import sqlite3

    import yaml

    from clew.declaration import stated_document_meta
    from clew.mcp_server.state import target_for

    raw = declaration.read_bytes()
    document = yaml.safe_load(raw.decode("utf-8")) or {}
    want = stated_document_meta(raw, document)
    db = Path(target_for(target).db_path)
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        held = {
            key.split(".", 1)[1]: value
            for key, value in conn.execute(
                "SELECT key, value FROM build_meta WHERE key LIKE 'declaration.%'"
            )
        }
    finally:
        conn.close()
    if held.get("stated_sha256") == want["stated_sha256"]:
        print(f"preflight OK: index was built with {declaration.name} ({want['stated_sections']})")
        return
    ## NAMED, not counted. "the declaration did not apply" sends an operator to re-read a file
    ## that is probably correct; naming the sections the index is missing says what to do.
    missing = sorted(
        set(want["stated_sections"].split(", ")) - set(held.get("stated_sections", "").split(", "))
    )
    raise SystemExit(
        "preflight: THE TARGET'S DECLARATION DID NOT REACH THIS INDEX — refusing to run.\n"
        f"  declaration : {declaration.name} — sections: {want['stated_sections']}\n"
        f"  index records: {held.get('stated_sections') or 'no declaration stated at all'}\n"
        f"  sha stated  : {want['stated_sha256'][:12]}\n"
        f"  sha in index: {(held.get('stated_sha256') or 'none')[:12]}\n"
        f"  sections the index never saw: {', '.join(missing) or 'none — the document was edited since the build'}\n"
        f"  index: {db}\n"
        "  An undeclared index answers every question without complaint, and it answers them\n"
        "  WITHOUT the conventions the target needs — so the arm under test is measured against\n"
        "  a policy nobody chose. Rebuild with `--declare` and re-run."
    )


## @brief Reset a disposable target's tree and rebuild its index before a cell.
## @param target Target repo root, which MUST carry the disposable marker.
## @param declaration The stated declaration document to rebuild with, or None.
## @return A short status string for the run log.
## @version 2
def restore_target(target: Path, declaration: Path | None = None) -> str:
    """EVERY CELL CAN NOW MUTATE THE TREE (gh#354), so every cell must START from the same
    state — not just the ones that a previous cell's audit happened to flag. Owner decision
    2026-08-10, choosing this over a mutation-triggered restore precisely because triggering
    off the audit would make correctness depend on the audit being right: a write driven
    through `Bash` (`sh -c 'echo > f'`) produces no `mutation:` finding at all.

    BOTH HALVES OR NEITHER. Resetting the tree without rebuilding the index leaves an index
    describing a file state that no longer exists, which is worse than either alone — the
    source arm would read the restored tree while the index arm answered from the mutated
    one, and the comparison would be between two different repositories.

    IT REFUSES WITHOUT THE MARKER, through `restore_target_preflight` so the refusal has ONE
    wording. `git clean -fd` deletes untracked files; this repo has already had a `restore()`
    implemented as `git checkout -- <dir>` revert ten files of uncommitted work, recoverable
    only because the edits were still in a session. The remedy is named rather than implied.

    @brief Reset tree and index so a cell starts from a known state.
    @return Status line for the log.
    @version 2
    """
    restore_target_preflight(target)
    ## THE DESTRUCTIVE COMMANDS ARE PINNED TO THE TARGET THREE WAYS, because `cwd=` ALONE IS NOT
    ## A GUARANTEE and this repo has a recorded instance of the failure. `GIT_DIR` in the
    ## environment overrides cwd discovery outright, and gh#386 records git subprocesses here
    ## inheriting exactly that from a pre-commit hook. A `git clean -fd` resolving to the WRONG
    ## repository deletes the operator's untracked work in it — and for an internal target that
    ## lives INSIDE this repository, the wrong repository would be docs-db itself.
    ##
    ## So: the env is stripped of every GIT_* pointer, `-C` states the directory explicitly, and
    ## the resolved toplevel is then CHECKED to be the target before anything destructive runs.
    ## The third is the load-bearing one — the first two make the right thing likely, and only a
    ## positive check makes the wrong thing impossible.
    env = {k: v for k, v in os.environ.items() if k not in _GIT_LOCATION_VARS}
    top = subprocess.run(
        ["git", "-C", str(target), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    ).stdout.strip()
    if not top or Path(top).resolve() != target.resolve():
        raise SystemExit(
            f"restore: REFUSING — git in {target} resolves to {top or '<no repository>'}.\n"
            "  The restore runs `git clean -fd`, which deletes untracked files. It will only run\n"
            "  against a repository whose toplevel IS the target."
        )
    ## `-e <marker>` IS LOAD-BEARING AND A CONTROL FOUND IT. The marker is untracked, so a bare
    ## `git clean -fd` deletes it — the first cell would restore and every cell after it would
    ## refuse, failing the sweep at cell 2 with a message about an opt-in the operator had
    ## already given. Excluding it makes the restore idempotent, which is the whole point of
    ## running it before every cell.
    for argv in (
        ["git", "-C", str(target), "checkout", "--", "."],
        ["git", "-C", str(target), "clean", "-fd", "-e", RESTORE_MARKER],
    ):
        proc = subprocess.run(
            argv, cwd=str(target), capture_output=True, text=True, check=False, env=env
        )  # fmt: skip
        if proc.returncode != 0:
            raise SystemExit(f"restore failed in {target}: {' '.join(argv)}: {proc.stderr}")
    ## The index is rebuilt through the SHIPPED path, not by deleting the database: a build is
    ## what an operator has. The db path is derived by `target_for`, the SAME derivation
    ## `preflight_target` uses — composing it here would let the restore rebuild one file while
    ## the cell's MCP server read another, which is the config-pinned-to-the-wrong-repo defect
    ## that invalidated a whole grid, in miniature.
    from clew.cli import build_index
    from clew.mcp_server.state import target_for
    from clew.scope import SCOPE_FROM_GUARD

    ## THE DECLARATION RIDES WITH THE REBUILD, and its absence here is what invalidated the
    ## 2026-08-14 spot check. Without it every restore replaced a DECLARED index with an
    ## undeclared one, silently: the target's own conventions — mbedtls's fnptr lock primitive,
    ## its vendored tree, its commented-out threading gates — were dropped before each cell, and
    ## the surviving `options.locks.tier=explicit` came from replay of an older build rather than
    ## from this one. `preflight_declaration_applied` now refuses if this line ever stops firing.
    build_index(
        output=Path(target_for(target).db_path),
        repo_root=target,
        scope=SCOPE_FROM_GUARD,
        declare=declaration,
    )
    stated = f" with {declaration.name}" if declaration is not None else ""
    return f"restored {target.name} (tree reset + index rebuilt{stated})"


## @brief Run one cell.
## @param arm Arm name.
## @param model Model alias.
## @param question Question record.
## @param run Repetition index.
## @param opts Parsed options.
## @return Metrics row.
## @version 4
def run_cell(arm: str, model: str, question: dict, run: int, opts) -> dict:
    """Run the process, persist the answer and the argv, then audit the
    transcript. A timeout is recorded as `valid=false` rather than raised, so
    one slow cell cannot abort a sweep.

    THE RESTORE HAPPENS BEFORE THE CELL, not after it (gh#354). After-the-fact cleanup leaves
    the LAST cell's mutations in place for whatever runs next — another sweep, a person
    inspecting the tree — and it cannot help the first cell of a sweep that inherited a dirty
    tree from something else. Before means every cell's premise is identical and stated.

    @brief Execute one benchmark cell end to end.
    @return Metrics row.
    @version 4
    """
    out = Path(opts.out)
    answer_path = out / f"{question['id']}_{model}_{arm}_r{run}.md"
    target = Path(opts.target).expanduser().resolve()
    if not getattr(opts, "no_restore", False):
        ## DERIVED FROM THE RUBRIC PATH the cell is graded against, not from a separate flag, so
        ## the policy the index is built with and the key it is scored against cannot name
        ## different targets.
        print(f"    {restore_target(target, declaration_for(Path(opts.questions)))}")
    prompt = build_prompt(arm, target, question)
    argv = build_argv(arm, model, prompt, target, mcp_config_for(target, out))
    bench_publish.write_json(out / "argv" / f"{answer_path.stem}.json", argv)
    started = time.time()
    try:
        proc = subprocess.run(
            argv, cwd=str(out / "wd"), capture_output=True, text=True,
            timeout=opts.timeout, check=False, env={**os.environ, **CELL_ENV},
        )  # fmt: skip
        payload = json.loads(proc.stdout) if proc.stdout.strip() else {}
    except subprocess.TimeoutExpired:
        payload = {"is_error": True, "result": f"TIMEOUT after {opts.timeout}s"}
    except ValueError:
        payload = {"is_error": True, "result": "UNPARSEABLE JSON on stdout"}
    return _record(arm, model, question, run, payload, answer_path, started, opts)


## @brief Preserve a cell's transcript, raw and rendered, beside its answer.
## @param transcript Transcript path reported by the run, or None.
## @param answer_path The cell's answer markdown path (its directory anchors the copies).
## @param title Heading for the rendered history.
## @return None.
## @version 1
## @dg_internal
def _preserve_history(transcript: Path | None, answer_path: Path, title: str) -> None:
    """PRESERVE THE AGENT'S HISTORY, both raw and readable.

    The transcript was previously READ for tool counts and then discarded. It lives under
    ~/.claude/projects/<slug>/<session>.jsonl, which rotates — so once a run finished there was
    no record of what the agent DID, only its final prose. That is exactly what makes a grade
    uncheckable, and the gap has already cost a whole grid: 15 of 18 cells stated in prose that
    they were querying the wrong repository and nobody read them.

    Both forms are kept on purpose. The `.history.md` is a convenience for a reviewer; the
    `.jsonl` is the authority, so no conclusion depends on the renderer being correct.

    @brief Copy and render a cell's transcript.
    @return None.
    @version 1
    """
    if not (transcript and transcript.is_file()):
        return
    kept = answer_path.parent / "history" / f"{answer_path.stem}.transcript.jsonl"
    ## Normalised on the way in, so the history is rendered FROM the same bytes a reviewer will
    ## read. Rendering from the original and sanitising afterwards would let the two disagree,
    ## and the whole point of keeping both is that they cannot.
    bench_publish.copy(transcript, kept)
    try:
        from evidence import _records
        from evidence import (
            render as render_history,
        )

        bench_publish.write(
            kept.with_suffix("").with_suffix(".history.md"),
            render_history(_records(kept), title),
        )
    except Exception as exc:
        print(f"    ! history render failed ({exc}) — raw transcript kept")


## @brief Audit a cell's transcript, report what it found, and persist its tool histogram.
## @param arm Arm name.
## @param transcript Transcript path, or None when the run reported none.
## @param answer_path The cell's answer markdown path (its directory anchors the histogram).
## @return The audit record, with a fail-closed stub when there is no transcript.
## @version 1
## @dg_internal
def _audit_and_report(arm: str, transcript: Path | None, answer_path: Path) -> dict:
    """NO TRANSCRIPT IS NOT A CLEAN AUDIT. The stub records `audit_clean=False` and a
    `transcript-not-found` violation, so a cell whose evidence is missing is visibly
    unverifiable rather than quietly counted as isolated.

    Unlisted tools are printed SEPARATELY from violations, and deliberately not folded into
    `audit_clean` or into `CSV_FIELDS`. A tool outside the allow list is a fact a reviewer
    should see; it is not a reason to distrust the cell's numbers unless `audit` classified it
    as an isolation break, in which case it is already above. It is not a CSV column because a
    per-cell LIST of tool names does not belong in a scalar field — the `.hist.json` written
    here records every tool NAME, which is what makes a retroactive re-audit possible
    (`bench_arms.py reaudit`) without a schema change.

    @brief Run the arm audit for one cell and report it.
    @return Audit record.
    @version 1
    """
    checked = audit(arm, tool_calls(transcript)) if transcript else {
        "tool_uses": -1, "used_db_tools": -1, "audit_clean": False,
        "violations": ["transcript-not-found"], "unlisted_tools": [],
        "review": [], "review_count": -1,
    }  # fmt: skip
    if checked["violations"]:
        print(f"    ! audit: {checked['violations']}")
    ## REVIEW findings print DIFFERENTLY from violations because they mean the opposite
    ## thing (gh#354): an index-arm cell that also read source is a valid measurement of the
    ## real question, and how often that happens is the reframe's own headline rather than a
    ## defect tally. Printing it as `!` would train a reviewer to read the result as broken.
    if checked.get("review"):
        print(f"    ~ review (index arm also read source or wrote): {checked['review']}")
    if checked.get("unlisted_tools"):
        print(f"    ? unlisted (reported, not a violation): {checked['unlisted_tools']}")
    ## Persist the per-tool histogram — the low-noise mechanistic signal.
    hist = checked.get("histogram", {})
    bench_publish.write_json(answer_path.parent / "raw" / f"{answer_path.stem}.hist.json", hist)
    if hist:
        top = ", ".join(f"{k}×{v}" for k, v in sorted(hist.items(), key=lambda kv: -kv[1])[:6])
        print(f"    tools: {top}")
    return checked


## @brief A measured-milliseconds column's value for one cell.
## @param transcript Transcript path reported by the run, or None.
## @param measure The bench_arms measurement to read (build_ms / bringup_ms).
## @return Measured milliseconds, or "" when the cell did none of that work.
## @version 2
## @dg_internal
def _ms_field(transcript: Path | None, measure) -> int | str:
    """EMPTY, NOT 0, when the cell did none of it — every source-arm cell, and any index-arm
    cell that found a warm index. A measured zero must not share a spelling with "not
    applicable", or the mean of the column silently includes cells that never built.

    ONE renderer for both columns rather than a copy per measurement: the empty-vs-zero rule
    is the load-bearing part and a second copy of it is a second chance to write `or 0`.

    @brief Render one measured duration for the metrics CSV.
    @return Milliseconds or "".
    @version 2
    """
    if not (transcript and transcript.is_file()):
        return ""
    return measure(transcript) or ""


## @brief Turn a raw `claude -p` JSON result into a persisted row.
## @param payload Parsed JSON result (possibly a synthesized error).
## @param answer_path Where the answer markdown is written.
## @param started Wall-clock start, used when the process reported no duration.
## @return Metrics row dict.
## @version 3
def _record(arm, model, question, run, payload, answer_path, started, opts) -> dict:
    """Extract usage, write the answer file, and fold in the transcript audit.

    @brief Persist a cell's answer and assemble its metrics row.
    @return Metrics row.
    @version 3
    """
    usage = payload.get("usage") or {}
    answer = payload.get("result") or ""
    header = f"# {question['id']} — {arm} — {model} — run {run}\n\n"
    bench_publish.write(answer_path, header + answer + "\n")
    bench_publish.write_json(answer_path.parent / "raw" / f"{answer_path.stem}.json", payload)

    transcript = find_transcript(payload.get("session_id", ""))
    _preserve_history(transcript, answer_path, f"{question['id']} — {arm} — {model} — run {run}")
    checked = _audit_and_report(arm, transcript, answer_path)
    tokens = [usage.get(k, 0) or 0 for k in
              ("input_tokens", "output_tokens", "cache_read_input_tokens",
               "cache_creation_input_tokens")]  # fmt: skip
    used_db = checked["used_db_tools"]
    ## TARGET CORRECTNESS IS NOW CHECKED PER CELL, STRUCTURALLY. It used to be checked once
    ## per sweep by `preflight_target`, and this comment used to argue that per-cell checking
    ## was impossible because the only version anyone had tried was a PROSE match — which
    ## caught 4 of the 15 real cases and false-positived on a source-arm cell.
    ##
    ## The prose route was the wrong instrument, not the wrong question. Every index reply
    ## STAMPS the repository that answered it, so the per-cell check is a path comparison
    ## against a JSON field (`target_check.verify`) with no natural-language term in it. That
    ## matters because `--repo` sets only the DEFAULT target: the server takes a `target`
    ## argument on every tool, so an agent can name another indexed repository and every
    ## once-per-sweep guard still passes.
    ##
    ## Three outcomes, never two: `ok`, `void`, and `unchecked` for a cell whose provenance
    ## could not be read at all. A source-arm cell is `n/a` — it was never subject to the
    ## check, which is not the same as having passed it.
    target_ok = target_check.verify(arm, transcript, Path(opts.target).expanduser().resolve())
    if target_ok["status"] != target_check.NOT_APPLICABLE:
        print(f"    target: {target_ok['status']} — {target_ok['reason']}")
    bench_publish.write_json(
        answer_path.parent / "raw" / f"{answer_path.stem}.target.json", target_ok
    )
    ## AN INDEX-ARM CELL IS VALID ONLY IF A DATABASE TOOL ACTUALLY RETURNED SOMETHING.
    ## `used_db_tools` counts ATTEMPTS, so a cell whose server failed to spawn — one
    ## `set_target` call answered with `No such tool available` — scored valid=True while
    ## its answer said, at length, that it could not answer. Measured, not hypothetical.
    db_ok = db_tool_outcomes(transcript)[1] if (arm == "mcp" and transcript) else 0
    valid = (
        not payload.get("is_error", False) and bool(answer.strip()) and (arm != "mcp" or db_ok > 0)
    )
    return {
        "target": Path(opts.target).name,
        "q": question["id"], "arm": arm, "model": model, "run": run,
        "tokens_in": tokens[0], "tokens_out": tokens[1],
        "cache_read": tokens[2], "cache_creation": tokens[3],
        "total_tokens": sum(tokens),
        "tool_uses": checked["tool_uses"],
        ## RETRIEVED BYTES, BECAUSE `total_tokens` IS NOT A RETRIEVAL MEASUREMENT. Measured on the
        ## p5-both run and reproduced exactly: `total_tokens` is the sum over API round trips of
        ## cache_read + cache_creation + in + out, and on this harness the static prompt is ~80k, so
        ## the figure is a TURN COUNTER times a constant belonging to neither arm. On Q2 the src arm
        ## took 16 round trips to the index arm's 6 — 2.67 — and their token totals differed by
        ## 2.60, while the INDEX arm had retrieved 21% MORE payload (17,259 chars vs 14,238) and
        ## ended with a larger context. Under 1% of the reported cost was the thing being compared.
        ##
        ## Turn count is also confounded by BATCHING: the index arm issued ~2.2 calls per message,
        ## the src arm one. A batched pair of lookups costs one round trip and reads the same bytes.
        ##
        ## So the axes are now separable and all three are reported: `total_tokens` (what a session
        ## actually bills), `num_turns` (why it billed that), and these two (what was actually
        ## read). A cost claim that means "retrieval efficiency" must cite the bytes.
        "result_bytes": result_bytes(transcript),
        "db_result_bytes": result_bytes(transcript, db_only=True),
        "num_turns": payload.get("num_turns", -1),
        "duration_ms": payload.get("duration_ms") or int((time.time() - started) * 1000),
        "build_ms": _ms_field(transcript, build_ms),
        "bringup_ms": _ms_field(transcript, bringup_ms),
        "cost_usd": round(payload.get("total_cost_usd", 0.0) or 0.0, 6),
        "used_db_tools": used_db,
        "audit_clean": checked["audit_clean"],
        ## gh#354's HEADLINE, and it belongs in the CSV rather than only in the transcript: an
        ## index arm that can also grep will grep when the index disappoints, so "the index
        ## arm fell back to source in N of 9 cells" is the measurement the reframe creates. It
        ## is NOT a defect count — see `bench_arms.review_finding`.
        "review_count": checked.get("review_count", 0),
        ## SEPARATE FROM `valid`, deliberately. `valid` means "this cell produced a usable
        ## measurement"; `target_ok` means "the measurement is about the right repository".
        ## Folding a void cell into `valid=False` would hide it inside the invalid count and
        ## it would be dropped silently — and this project's standing lesson is that a cell
        ## excluded without being named is a silent third of the exam.
        "target_ok": target_ok["status"],
        "valid": valid,
        "answer_path": answer_path.name,
    }  # fmt: skip


## @brief Refuse to append to a metrics.csv written under a different field list.
## @param path Existing metrics.csv.
## @return None; raises SystemExit when the header disagrees with CSV_FIELDS.
## @version 1
## @dg_internal
def _assert_csv_schema(path: Path) -> None:
    """An EMPTY existing file is accepted — it carries no rows to misalign, and the writer
    below will give it a header.

    @brief Compare an existing metrics.csv header against CSV_FIELDS.
    @return None.
    @version 1
    """
    with path.open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh), None)
    if header is None or header == CSV_FIELDS:
        return
    added = [f for f in CSV_FIELDS if f not in header]
    removed = [f for f in header if f not in CSV_FIELDS]
    raise SystemExit(
        f"metrics schema mismatch: {path} was written under a different field list.\n"
        f"  file header : {len(header)} fields\n"
        f"  CSV_FIELDS  : {len(CSV_FIELDS)} fields"
        + (f"\n  added since : {added}" if added else "")
        + (f"\n  missing now : {removed}" if removed else "")
        + "\n  metrics.csv is APPEND-ONLY, so appending a differently-shaped row shifts every "
        "value after the changed column and no reader can tell.\n"
        "  Re-run with a fresh --out (finished cells are skipped by their answer files), or "
        "move the old metrics.csv aside."
    )


## @brief Append one row to the metrics CSV, writing the header on first use.
## @param out Output directory.
## @param row Metrics row.
## @version 1
def append_row(out: Path, row: dict) -> None:
    """Append-only, so a resumed sweep never rewrites earlier rows — which is exactly why the
    HEADER is checked first. Appending `CSV_FIELDS`-shaped rows to a file written under a
    different field list shifts every value after the changed column, and nothing downstream
    can detect it: `csv.DictReader` reads the file's own header, so the old rows keep their
    meaning while the new ones quietly acquire different ones. Refusing names both schemas and
    costs a fresh --out; the answer files resumption keys on are untouched.

    @brief Append a metrics row, refusing on a schema mismatch.
    @version 2
    """
    path = out / "metrics.csv"
    new = not path.exists()
    if not new:
        _assert_csv_schema(path)
    with path.open("a", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        if new:
            writer.writeheader()
        writer.writerow(row)


## @brief Normalise --model into a validated list of aliases.
## @param raw Values collected by the repeatable --model flag.
## @return Ordered, de-duplicated model aliases.
## @version 1
## @dg_internal
def _models(raw: list[str]) -> list[str]:
    """Accepts BOTH spellings — repeated `--model a --model b` and comma-separated
    `--model a,b` — because the sibling `--questions-filter` takes commas and the
    inconsistency is a live footgun: `--model haiku,sonnet,opus` previously planned
    a perfectly plausible sweep whose model alias was the literal string
    "haiku,sonnet,opus". A wrong plan that PRINTS correctly is the failure mode this
    whole harness keeps relearning.

    Unknown aliases are refused rather than passed through, so a typo costs an error
    message instead of a session's capacity.

    @brief Split, de-duplicate and validate model aliases.
    @return Model alias list.
    @version 1
    """
    out: list[str] = []
    for value in raw:
        for alias in value.split(","):
            alias = alias.strip()
            if alias and alias not in out:
                out.append(alias)
    unknown = [a for a in out if a not in KNOWN_MODELS]
    if unknown:
        known = ", ".join(sorted(KNOWN_MODELS))
        raise SystemExit(f"unknown model alias(es): {', '.join(unknown)} — known: {known}")
    return out


## @brief Enumerate the cells a sweep will execute.
## @param opts Parsed CLI options.
## @return List of (question, arm, model, run) tuples.
## @version 3
def plan_cells(opts) -> list[tuple[dict, str, str, int]]:
    """Expand the grid in a stable order (question, arm, model, run) so a
    resumed sweep continues where it stopped.

    A (question, arm) pair whose every mark is fenced against that arm is DROPPED and said
    aloud — see `_on_this_arms_exam`. That is not tidying: such a cell is graded against zero
    marks while its tokens and wall time join that arm's means.

    @brief Expand the question x arm x model x run grid.
    @return Ordered cell list.
    @version 3
    """
    path = Path(opts.questions).expanduser()
    questions = parse_questions(path)
    if opts.questions_filter:
        wanted = {q.strip().upper() for q in opts.questions_filter.split(",")}
        questions = [q for q in questions if q["id"].upper() in wanted]
    arms = ["src", "mcp"] if opts.arm == "both" else [opts.arm]
    rubrics = load_rubric(path)
    return [
        (q, arm, model, run)
        for q in questions
        for arm in arms
        if _on_this_arms_exam(rubrics, q["id"], arm)
        for model in _models(opts.model)
        for run in range(1, opts.runs + 1)
    ]


## @brief Whether a question has any mark this arm can reach.
## @param rubrics Parsed rubric keyed by question id.
## @param qid Question id.
## @param arm Harness arm name.
## @return True when the cell is worth running for this arm.
## @version 1
## @dg_internal
def _on_this_arms_exam(rubrics: dict, qid: str, arm: str) -> bool:
    """A CELL WHOSE EVERY MARK IS FENCED AGAINST ITS ARM IS NOT A MEASUREMENT, AND IT IS NOT FREE.
    mbedtls Q0 is the live case: all 9 marks carry `[db-arm-only]`, so `--arm both` scheduled a
    source-arm Q0 cell that spends a full cell of session capacity to be graded against zero
    marks. Fencing was already right at the MARK level — excluded, never scored zero — which is
    exactly why this went unnoticed: the score was unaffected, while the cell's tokens and wall
    time landed in the source arm's aggregate means and skewed a cost comparison with a question
    that is never compared. The plan called this a check to verify; it was a defect.

    FAILS OPEN, DELIBERATELY. A question the rubric parsed NO marks for is scheduled, because
    "no marks parsed" is a rubric-parse problem (`parse_rubric` returns nothing for a heading
    that does not match `_Q_HEADING`) and treating it as "fenced" would silently drop a graded
    question from the grid — strictly worse than paying for a cell. The one thing this must never
    do is quietly shrink the exam.

    NOT SILENT. A dropped cell is logged with its arm and reason: this project's own rule is that
    a harness bounding coverage says what it dropped, because silent truncation reads as
    "covered everything".

    @brief Decide whether to schedule a (question, arm) cell.
    @return True to schedule.
    @version 1
    """
    rubric = rubrics.get(qid)
    if rubric is None or not rubric.marks:
        return True
    if marks_on_the_exam(rubric.marks, arm):
        return True
    print(
        f"  skipping {qid}/{arm}: all {len(rubric.marks)} marks are fenced off this arm, so the "
        f"cell would be graded against nothing while its cost joined the {arm} means"
    )
    return False


## @brief Pre-execution guards: dry run and the unattended-size refusal.
## @param opts Parsed CLI options.
## @param cells Planned cells.
## @return Exit code to stop on, or None to proceed with execution.
## @version 1
## @dg_internal
def _pre_execution_guard(opts, cells: list) -> int | None:
    """@brief Decide whether the sweep may proceed.
    @return Exit code to stop on, or None.
    @version 1
    """
    if opts.dry_run:
        for q, arm, model, run in cells:
            print(f"  {q['id']:>3} {arm:<3} {model:<7} r{run}")
        return 0
    if len(cells) > 12 and not opts.yes:
        print(f"refusing {len(cells)} cells (>12) without --yes")
        return 2
    return None


## @brief Normalise the run directory, then return the sweep's exit code.
## @param out Run output directory.
## @param code Exit code to return.
## @return The same exit code, after normalisation.
## @version 1
## @dg_internal
def _finish(out: Path, code: int) -> int:
    """EVERY exit path runs this, which is the whole point of it existing.

    `mcp-bench.json` is regenerated ABSOLUTE by every cell (it is executed, and an MCP client
    spawns `command` with no shell), so a run directory is not committable until it has been
    normalised. Normalisation used to sit inline before `return 0` — reachable only on a clean
    finish, and therefore missing from both ABORT paths.

    That is backwards. A sweep that aborts on capacity is EXACTLY when the operator commits:
    it is the natural boundary, the data is complete up to that point, and the loop's stop
    condition sends them straight there. The one exit that most needed a committable directory
    was the one that did not produce one.

    @brief Normalise on the way out, whatever the exit code.
    @return The exit code passed in.
    @version 1
    """
    rewritten, skipped = bench_publish.sanitise_tree(out)
    if rewritten:
        print(f"normalised {len(rewritten)} artifact(s) for commit")
    if skipped:
        print(f"WARNING: {len(skipped)} file(s) of unknown type were NOT inspected — check them")
    return code


## @brief Execute the planned cells, skipping any already answered.
## @param out Run output directory.
## @param cells Planned cells.
## @param opts Parsed CLI options.
## @return Exit code (1 if a cost ceiling or a systematic fault aborted the sweep).
## @version 2
## @dg_internal
def _execute_cells(out: Path, cells: list, opts) -> int:
    """Resumable by construction: a cell whose answer file exists is skipped, so an
    interrupted sweep is continued by re-running the identical command. Never delete a
    COMPLETED cell to "clean up" — that is how a run loses data it already paid for. An
    INVALID cell is the opposite case and its stub is removed, so the resume path retries
    it instead of mistaking a 223ms failure for finished work.

    @brief Run each planned cell.
    @return Exit code.
    @version 2
    """
    spent = 0
    consecutive_invalid = 0
    for index, (q, arm, model, run) in enumerate(cells, 1):
        answer = out / f"{q['id']}_{model}_{arm}_r{run}.md"
        if answer.exists() and not opts.force:
            print(f"[{index}/{len(cells)}] skip (exists) {answer.name}")
            continue
        print(f"[{index}/{len(cells)}] {q['id']} {arm} {model} r{run} ...", flush=True)
        row = run_cell(arm, model, q, run, opts)
        append_row(out, row)
        spent += int(row["total_tokens"])
        print(
            f"    tokens={row['total_tokens']} tools={row['tool_uses']} "
            f"turns={row['num_turns']} {row['duration_ms']}ms ${row['cost_usd']:.4f} "
            f"db_tools={row['used_db_tools']} valid={row['valid']}"
        )
        ## FAIL FAST ON A SYSTEMATIC FAULT. An invalid cell is cheap; 198 of them wearing
        ## the costume of a finished sweep is not. Delete the offending answer file so the
        ## resume path retries it rather than skipping it as "already done" — a broken cell
        ## that leaves a stub behind is a cell that never gets re-run.
        ## WRONG REPOSITORY IS AN INSTANT FAIL, and it stops the sweep on the FIRST cell
        ## rather than after a run of them. The other abort conditions tolerate one bad cell
        ## because they can be bad luck; this one cannot. A cell that answered about another
        ## repository proves the configuration is wrong for every cell that follows it, and
        ## the 36-cell grid this project retracted spent a whole session's capacity learning
        ## that lesson one cell at a time. The answer file is KEPT, unlike an invalid cell's,
        ## because a void answer is evidence of the misconfiguration and re-running it before
        ## the cause is fixed would only reproduce it.
        if row["target_ok"] == target_check.VOID:
            print(
                f"ABORT: VOID CELL — {answer.name} answered about a repository that is not "
                f"{opts.target}.\n"
                f"  {Path(opts.out) / 'raw' / (answer.stem + '.target.json')} names what it "
                f"reported.\n"
                "  Every later cell of this sweep would be void for the same reason, and a "
                "void cell cannot be scored low — it has to be excluded and counted.\n"
                "  Fix the target configuration, then re-run with a FRESH --out: the answers "
                "already written are not gradable."
            )
            return _finish(out, 1)
        consecutive_invalid = 0 if row["valid"] else consecutive_invalid + 1
        if not row["valid"]:
            answer.unlink(missing_ok=True)
        if consecutive_invalid >= MAX_CONSECUTIVE_INVALID:
            ## NAME BOTH CAUSES. This message used to assert "configuration fault, not bad
            ## luck" — and the first time it fired for real, the cause was session capacity
            ## (`api_error_status: 429`, "You've hit your session limit"). Telling an operator
            ## to go hunt a config bug when they should simply wait for a reset is worse than
            ## saying nothing: it sends them editing a harness that is working correctly.
            print(
                f"ABORT: {consecutive_invalid} consecutive INVALID cells. Two causes look "
                f"identical here — read raw/{answer.stem}.json to tell them apart:\n"
                f"  api_error_status 429 / 'session limit'  -> CAPACITY. Wait for the reset "
                f"named in the payload, then re-run the same command; completed cells are "
                f"skipped.\n"
                f"  anything else                           -> configuration fault. Check "
                f"argv/{answer.stem}.json before spending more capacity."
            )
            return _finish(out, 1)
        if opts.max_tokens and spent > opts.max_tokens:
            print(
                f"ABORT: spent {spent / 1e6:,.1f}M tokens > --max-tokens "
                f"{opts.max_tokens / 1e6:,.1f}M"
            )
            return _finish(out, 1)
    print(f"done; {spent / 1e6:,.1f}M tokens spent this invocation")
    return _finish(out, 0)


## @brief `run` subcommand: execute the planned sweep.
## @param opts Parsed CLI options.
## @return Process exit code.
## @version 3
def cmd_run(opts) -> int:
    """Guard on estimated cost, then execute cell by cell, skipping any whose
    answer file already exists unless --force.

    @brief Execute the benchmark sweep.
    @return Exit code.
    @version 3
    """
    if shutil.which("claude") is None:
        print("claude CLI not on PATH")
        return 2
    ## NORMALISE --out ONCE, HERE, so every downstream `Path(opts.out)` is absolute.
    ##
    ## This function used to resolve `out` for its own use while `run_cell` re-derived it
    ## from the raw string. With a RELATIVE --out that silently destroyed the entire index
    ## arm: cells run with `cwd=<out>/wd`, so the relative `--mcp-config` path resolved
    ## under the cell's working directory, `claude -p` exited in 223ms having done nothing,
    ## and the row was recorded valid=False. Invalid rows are excluded from the aggregates,
    ## so a full sweep would have produced a report quietly containing only source-arm data.
    ## Measured on the first calibration run, which is what a calibration is for.
    opts.out = str(Path(opts.out).expanduser().resolve())
    ## BEFORE ANY CELL, and before the dry-run exit too: a dry run that does not preflight
    ## reports a cell count for a sweep that cannot work. A sweep against the wrong index
    ## costs a full session's capacity and produces a result that READS as valid — which is
    ## exactly what happened on 2026-07-30.
    preflight_target(Path(opts.target).expanduser().resolve())
    ## AND THE GRADING KEY'S PROVENANCE, in front of the same spend. `preflight_target` proves
    ## the served INDEX is current; this proves the KEY the cells will be graded against says
    ## where its figures came from and that they have not drifted. On 2026-08-05 a ~198-cell
    ## sweep was refused by a human because both committed keys held figures measured at build
    ## 16/17 against a pipeline at 27, and only the arm under test can be penalised by that.
    ## Checked before the dry-run exit for the same reason the target is: `--dry-run` has to
    ## tell the truth about whether the real sweep would start.
    preflight_rubric_provenance(Path(opts.questions).expanduser().resolve())
    ## AND THAT THE TARGET IS AT THE REVISION THAT KEY DESCRIBES. The two above prove the index is
    ## of the right repository and from the current pipeline; neither looks at WHICH COMMIT the
    ## repository is checked out to. Measured 2026-08-15: entropic sat a full tag ahead of its
    ## rubric with the declared commit absent from the clone, and every preflight passed.
    preflight_target_revision(
        Path(opts.target).expanduser().resolve(), Path(opts.questions).expanduser().resolve()
    )
    ## AND THAT THE INDEX WAS BUILT WITH THE TARGET'S OWN CONVENTIONS. The two checks above ask
    ## whether the index is of the right repository and from the current pipeline; both passed
    ## on 2026-08-14 while the index had been rebuilt WITHOUT the target's declaration, which
    ## made three landed fixes unmeasurable and fourteen Q4 marks unanswerable. In front of the
    ## dry-run exit with the others, for the same reason.
    preflight_declaration_applied(
        Path(opts.target).expanduser().resolve(),
        declaration_for(Path(opts.questions)),
    )
    ## AT THE START, NOT AT CELL 1. `restore_target` refuses without the marker, and finding
    ## that out on the first cell means the operator has already paid a preflight, a config
    ## generation and a directory tree for a sweep that cannot proceed. Checking here also
    ## keeps the refusal in front of the dry-run exit, so `--dry-run` tells the truth about
    ## whether the real sweep would start.
    if not getattr(opts, "no_restore", False):
        restore_target_preflight(Path(opts.target).expanduser().resolve())
    out = Path(opts.out)
    for sub in ("", "argv", "wd"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for brief in ("_brief_src.md", "_brief_mcp.md"):
        bench_publish.copy(HERE / brief, out / brief)

    cells = plan_cells(opts)
    estimate = sum(
        opts.est_tokens_per_cell or DEFAULT_EST_TOKENS_PER_CELL.get(m, 2_000_000)
        for _, _, m, _ in cells
    )
    print(
        f"{len(cells)} cells planned; estimated ≈ {estimate / 1e6:,.0f}M tokens "
        f"(conservative guard from source-arm medians, not a quote)"
    )
    stop = _pre_execution_guard(opts, cells)
    return stop if stop is not None else _execute_cells(out, cells, opts)


## @brief `sanitise` subcommand: normalise machine paths in an existing run directory.
## @param opts Parsed CLI options.
## @return Process exit code (1 when a file type it cannot rewrite is present).
## @version 1
def cmd_sanitise(opts) -> int:
    """For run data produced before normalisation existed, and as a pre-commit reflex on any
    run directory. Idempotent, so running it twice is free.

    Returns NON-ZERO when it encounters a file it does not know how to rewrite. A sanitiser
    that reports success while silently skipping half a directory is the vacuous pass this
    repo has shipped three times: the disarmed coverage gate, the `**` pathspec that covered
    62% of the package, and a scrub that ran clean while eight files leaked.

    @brief Normalise an existing run directory in place.
    @return Exit code.
    @version 1
    """
    root = Path(opts.out).expanduser().resolve()
    if not root.is_dir():
        print(f"no such run directory: {root}")
        return 2
    rewritten, skipped = bench_publish.sanitise_tree(root)
    for path in rewritten:
        print(f"  normalised {path.relative_to(root)}")
    print(f"{len(rewritten)} file(s) normalised under {root.name}")
    if skipped:
        print(f"WARNING: {len(skipped)} file(s) of unknown type were NOT inspected:")
        for path in skipped[:20]:
            print(f"  ? {path.relative_to(root)}")
        return 1
    return 0


## @brief De-duplicate metric rows, keeping the last attempt of each cell.
## @param rows Rows read from metrics.csv.
## @return (deduplicated rows, number of superseded rows).
## @version 1
def latest_per_cell(rows: list[dict]) -> tuple[list[dict], int]:
    """`metrics.csv` is APPEND-ONLY, which is right for an audit trail and wrong for an
    average. A cell re-run after a failure leaves both rows behind, and every aggregate then
    counts it twice — biased rather than merely noisy, because a retried cell is usually the
    slower one and drags its own arm's mean.

    Observed on the first calibration: three rows for two cells, because one index-arm cell
    was re-run twice while its configuration faults were diagnosed.

    The superseded count is RETURNED rather than swallowed, so a retry stays visible to a
    reader instead of quietly disappearing into a cleaner-looking table. Lives here because
    this module owns `metrics.csv`; `tier_report` imports it rather than reimplementing it,
    since two copies of a de-duplication rule is two chances to disagree about the answer.

    @brief Keep the last row per (q, arm, model, run).
    @return (rows, superseded count).
    @version 1
    """
    latest: dict[tuple[str, str, str, str], dict] = {}
    for row in rows:
        latest[(row["q"], row["arm"], row["model"], row["run"])] = row
    return list(latest.values()), len(rows) - len(latest)


## @brief Mean of one numeric CSV column across a group of rows.
## @param rows Metric rows for one (arm, model) group.
## @param key Column name.
## @return Arithmetic mean as a float.
## @version 1
## @dg_internal
def _mean(rows: list[dict], key: str) -> float:
    """A module-level function rather than a lambda bound inside the grouping loop.
    The lambda closed over the loop variable, which ruff flags (B023) — harmless
    only because it happened to be called within the same iteration, and a
    correctness argument that rests on "happened to" is one refactor from being
    wrong.

    @brief Average one column.
    @return Mean value.
    @version 1
    """
    return statistics.mean(float(row[key]) for row in rows)


## @brief The worst value of one column, ignoring rows that never measured it.
## @param rows Metric rows.
## @param key Column name.
## @return The maximum, or -1 when no row carries a measurement.
## @version 1
def _worst(rows: list[dict], key: str) -> int:
    """A MAXIMUM, NOT A MEAN, and that is the point rather than a convenience. `review_count`
    answers "how bad did one cell get", and worst case is what governs whether a tool is
    reached for again: one useless response resets the preference for the rest of a context
    window, and averaging that away with five good cells hides exactly the event that matters.

    `-1` MEANS UNMEASURED, not zero — `_audit_cell` writes it when no transcript was found —
    so those rows are skipped rather than counted as clean. Folding "we could not look" into
    "we looked and it was fine" is the disarmed-gate shape this harness keeps rediscovering.

    @brief Worst-case value of a column.
    @return The maximum measured value, or -1 when nothing was measured.
    @version 1
    """
    measured = [int(float(row[key])) for row in rows if int(float(row.get(key) or -1)) >= 0]
    return max(measured) if measured else -1


## @brief The report's bringup section: what standing the index up cost, kept out of the means.
## @param scored Last-attempt rows.
## @return Markdown lines.
## @version 1
def _bringup_note(scored: list[dict]) -> list[str]:
    """REPORTED SEPARATELY AND NEVER FOLDED IN, which is the owner's ruling made structural
    (gh#360: "bringup is a cost that must be quantified directly"). `build_ms` and `bringup_ms`
    have been collected since the schema gained them and reported NOWHERE, which is how a
    fourth axis becomes invisible: the number exists, no report prints it, and the comparison
    quietly reads as though bringup were free.

    THE TWO NUMBERS ANSWER DIFFERENT QUESTIONS and both are printed. `build_ms` is what a
    refresh costs — the figure an agent would quote to a user. `bringup_ms` adds the
    `propose_declaration` runs it takes to work out what a repository has to declare in the
    first place, which is step 0 of using this tool on any repo. Folding either into the other,
    or into `duration_ms`, is how this project's earlier grids produced convenient verdicts.

    UNMEASURED IS SAID, NOT OMITTED. A sweep where no cell built anything prints that it did
    not, because a missing section reads as "bringup was free" rather than "bringup was not
    measured here" — the same substitution the void-cell note exists to prevent one axis over.

    @brief Build the bringup-cost section.
    @return Markdown lines.
    @version 1
    """
    built = [r for r in scored if (r.get("build_ms") or "") or (r.get("bringup_ms") or "")]
    if not built:
        return ["", "## Bringup cost", "",
                "NOT MEASURED in this sweep — no cell built or extended an index, so there is no "
                "bringup figure. This is not a claim that bringup is free.",]  # fmt: skip
    lines = ["", "## Bringup cost (EXCLUDED from every mean above)", "",
             "`build_ms` is what a refresh costs; `bringup_ms` adds the `propose_declaration` "
             "runs needed to work out what the repository has to declare. Paid once per "
             "(tool version, index version, repo@sha), so folding it into a per-question "
             "comparison would charge one cell for a cost every later cell reuses.", "",
             "| Q | arm | model | run | build_ms | bringup_ms |",
             "|---|---|---|---|---|---|"]  # fmt: skip
    for r in built:
        lines.append(
            f"| {r['q']} | {r['arm']} | {r['model']} | {r['run']} | "
            f"{r.get('build_ms') or '—'} | {r.get('bringup_ms') or '—'} |"
        )
    return lines


## @brief The report's void-cell preamble: named exclusions, or the unchecked note.
## @param scored Last-attempt rows.
## @param voids The rows whose index answered about another repository.
## @return Markdown lines.
## @version 1
## @dg_internal
def _void_note(scored: list[dict], voids: list[dict]) -> list[str]:
    """THREE STATES, PRINTED AS THREE. A run whose CSV has no `target_ok` column at all predates
    the wrong-repository check, and saying nothing about it would let "not measured" read as
    "measured and clean" — the exact substitution behind this project's disarmed coverage gate
    and its identifier leak.

    @brief Describe the run's target-correctness state above the aggregates.
    @return Markdown lines.
    @version 1
    """
    if scored and "target_ok" not in scored[0]:
        return ["", "> **UNCHECKED for target correctness.** This run predates the "
                "wrong-repository check; that is not the same as clean."]  # fmt: skip
    if not voids:
        return []
    named = ", ".join(f"{r['q']}/{r['arm']}/{r['model']}/r{r['run']}" for r in voids)
    return ["", f"> **{len(voids)} VOID cell(s) EXCLUDED** — the index answered about another "
            f"repository: {named}.", ">",
            "> A void cell is excluded from every mean and named here. Its cost is meaningless "
            "too: a cell that discovers the wrong repository and bails is cheap, and averaging "
            "bail-outs is how a wrong 'cheaper and faster' headline was published."]  # fmt: skip


## @brief `report` subcommand: compile the CSV into markdown.
## @param opts Parsed CLI options.
## @return Process exit code.
## @version 4
def cmd_report(opts) -> int:
    """Emit the per-cell table then per-(arm,model) aggregates over VALID, NON-VOID rows only.

    TWO EXCLUSIONS, NOT ONE, AND THE SECOND WAS MISSING. An invalid row flatters whichever arm
    failed, so it was already dropped. A VOID row does the same thing and was NOT: a void cell
    is recorded `valid=True` on purpose — `target_ok` is deliberately a separate column, because
    folding it into `valid` would bury it in the invalid count — so every void cell's tokens and
    wall time were landing in these means.

    That is not a hypothetical. A published "3.4x cheaper, 2.9x faster" headline was measuring
    exactly this: a cell that discovers the wrong repository and bails costs a fraction of a
    working one, so including bail-outs makes the arm that bailed look efficient. The grader and
    the tier report both exclude void cells; this report did not, and it is the one an operator
    reads first, straight after a sweep.

    NAMED, NEVER SILENTLY DROPPED. The count and the coordinates print above the table.

    `review_count` IS REPORTED HERE, AS A WORST CASE. It was collected from the first sweep and
    reached only `metrics.csv`, so nobody read it: the index arm's per-question figures were
    Q1 0, Q2 2, and one Q2 cell at SEVEN. That last number is the one that matters and it is the
    one a mean erases — see `_worst`. It is EXPLANATORY, not a pass/fail term (owner, 2026-08-10):
    grep is always available in a real session, so an index arm that also read source has still
    won if it was cheaper, faster and at least as complete. The count says where the next gap is.

    @brief Compile metrics into a markdown report.
    @return Exit code.
    @version 4
    """
    path = Path(opts.out).expanduser().resolve() / "metrics.csv"
    if not path.exists():
        print(f"no metrics at {path}")
        return 2
    ## Per-cell table shows EVERY attempt (the audit trail); aggregates use the last
    ## attempt only, so a retried cell is not counted twice.
    rows = list(csv.DictReader(path.open(encoding="utf-8")))
    scored, superseded = latest_per_cell(rows)
    lines = ["| Q | arm | model | run | tokens | tools | turns | ms | $ | db_tools | review | audit | valid |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for r in rows:
        lines.append(
            f"| {r['q']} | {r['arm']} | {r['model']} | {r['run']} | {r['total_tokens']} | "
            f"{r['tool_uses']} | {r['num_turns']} | {r['duration_ms']} | {float(r['cost_usd']):.4f} | "
            f"{r['used_db_tools']} | {r.get('review_count', '')} | {r['audit_clean']} | "
            f"{r['valid']} |"
        )
    note = f" — {superseded} superseded row(s) excluded (cells re-run)" if superseded else ""
    voids = [r for r in scored if (r.get("target_ok") or "") == target_check.VOID]
    lines += _void_note(scored, voids)
    lines += ["", f"## Aggregates (valid, non-void rows, last attempt per cell{note})", "",
              "| arm | model | n | mean tokens | mean tools | mean turns | mean ms | mean $ "
              "| worst review |",
              "|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    groups: dict[tuple[str, str], list[dict]] = {}
    for r in scored:
        if r["valid"] == "True" and (r.get("target_ok") or "") != target_check.VOID:
            groups.setdefault((r["arm"], r["model"]), []).append(r)
    for (arm, model), items in sorted(groups.items()):
        lines.append(
            f"| {arm} | {model} | {len(items)} | {_mean(items, 'total_tokens'):.0f} | "
            f"{_mean(items, 'tool_uses'):.1f} | {_mean(items, 'num_turns'):.1f} | "
            f"{_mean(items, 'duration_ms'):.0f} | {_mean(items, 'cost_usd'):.4f} | "
            f"{_worst(items, 'review_count')} |"
        )
    lines += _bringup_note(scored)
    report = "\n".join(lines) + "\n"
    bench_publish.write(path.parent / "report.md", report)
    print(report)
    return 0


## @brief Parse CLI arguments.
## @return Parsed namespace.
## @version 1
def parse_args(argv: list[str]):
    """Two subcommands: `run` executes cells, `report` compiles them.

    @brief Build and run the argument parser.
    @return Parsed options namespace.
    @version 1
    """
    parser = argparse.ArgumentParser(description="docs-db acceptance matrix benchmark runner")
    subs = parser.add_subparsers(dest="cmd", required=True)

    run = subs.add_parser("run", help="execute benchmark cells")
    run.add_argument("--target", required=True, help="target repo root")
    run.add_argument("--questions", required=True, help="matrix markdown with the frozen questions")
    run.add_argument("--arm", choices=("src", "mcp", "both"), default="both")
    run.add_argument("--model", action="append", default=[], help="repeatable model alias")
    run.add_argument("--questions-filter", default="", help="e.g. Q1,Q3")
    run.add_argument("--runs", type=int, default=1)
    run.add_argument("--out", required=True)
    run.add_argument("--timeout", type=int, default=600, help="seconds per cell")
    ## DEFAULT ON, because a sweep without it is not a clean measurement now that every cell
    ## can mutate the tree (gh#354). The escape hatch exists for a target that is genuinely
    ## read-only-by-construction, and the RESULT MUST SAY SO when it is used — which is why the
    ## help text says it rather than leaving a reader to notice the flag in an argv dump.
    run.add_argument(
        "--no-restore",
        action="store_true",
        help="skip the per-cell tree+index restore. NOT a clean measurement: a mutating cell's "
        "edits survive into every later cell, and the result must state that it was used.",
    )
    run.add_argument(
        "--max-tokens", type=int, default=0, help="abort once this many tokens are spent"
    )
    run.add_argument(
        "--est-tokens-per-cell", type=int, default=0, help="override the pre-flight estimate"
    )
    run.add_argument("--force", action="store_true", help="re-run cells whose answer exists")
    run.add_argument("--yes", action="store_true", help="required for more than 12 cells")
    run.add_argument("--dry-run", action="store_true")
    run.set_defaults(func=cmd_run)

    report = subs.add_parser("report", help="compile metrics.csv into markdown")
    report.add_argument("--out", required=True)
    report.set_defaults(func=cmd_report)

    sanitise = subs.add_parser("sanitise", help="normalise machine paths in an existing run dir")
    sanitise.add_argument("--out", required=True)
    sanitise.set_defaults(func=cmd_sanitise)

    opts = parser.parse_args(argv)
    if opts.cmd == "run" and not opts.model:
        opts.model = ["sonnet"]
    return opts


if __name__ == "__main__":
    _opts = parse_args(sys.argv[1:])
    raise SystemExit(_opts.func(_opts))
