# SPDX-License-Identifier: MIT
"""Plan and preflight a run. Generation only — grading is a separate phase, deliberately.

WHY THE PHASES ARE SEPARATE. The judge must be arm-blind, and grading inline puts the grader
next to the process that knows the arm. Grading is also cheap and re-runnable, so coupling it to
generation means a scorer fix costs a regeneration — which is how a previous set of grids ended
up spanning two scorer versions with no way to reconcile them.

THE NESTING IS THE DESIGN. From outermost:

    model tier      one tier fully measured across all targets is a real result;
                    three tiers at 40% is not
    target
    question        shuffled from a recorded seed, so position is not correlated with
                    question across a long run
    replicate       all R for a question before the next question — a stop leaves FEWER
                    QUESTIONS AT USABLE n rather than every question at n=1, and n=1 is
                    exactly the state that tells you nothing
    arm             innermost, always a pair, run back to back and counterbalanced

Arm innermost is not a preference. An unpaired cell is uninterpretable — you cannot compare arms
with one of them — and back-to-back minimises any drift between the two things being subtracted.
Counterbalancing the order within the pair is what stops that drift being confounded with arm.
"""

from __future__ import annotations

import difflib
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .grader.rubric import Rubric

## THE TWO ARMS 1.1.0 COMPARES (owner ruling, 2026-08-22).
##
## `index_only` rather than the blended `index` arm, because the blend is confounded with
## ADOPTION and adoption is an independent problem. Measured: index arms made between 0 and 5
## index calls out of 6 to 14 total, and one cell made none at all despite an explicit directive.
## A score built on that measures an agent's habits at least as much as a tool's capability.
##
## Strip the shell and the ambiguity goes with it — a miss belongs to the tool. The question
## 1.1.0 answers is "can the index alone match a full agentic harness", which is fully
## falsifiable in a way the blend is not.
##
## THE CORE HYPOTHESIS DOES NOT CHANGE. H1 is about the retrieval substrate, not about whether an
## agent thinks to reach for it; 1.1.0 simply does not aim to answer it in full. The blended arm
## is a 1.2.0 target, once adoption is solved.
ARMS = ("baseline", "index_only")

## THE BLENDED ARM. Still runnable and still the shipped product's shape, but NOT part of the
## 1.1.0 comparison for the reason above. Kept so 1.2.0 has a prior measurement to improve on
## rather than starting from nothing.
BLENDED_ARM = "index"
ALL_ARMS = ARMS + (BLENDED_ARM,)

## THE ONLY PERMITTED DIFFERENCE BETWEEN THE TWO BRIEFS. Everything else is byte-identical and
## `check_symmetry` refuses on any other delta. Asymmetry in what an arm is TOLD is a handicap
## built into the instrument, and "is the baseline arm good enough" is otherwise an opinion.
_TOOLS = {
    "baseline": "You have the usual shell and file tools: Read, Grep, Glob and Bash.",
    ## A DIRECTIVE, NOT AN OFFER, and the measurements forced it in two steps.
    ##
    ## First: a brief saying only "a queryable index is available as MCP tools" produced TWO
    ## index cells that never touched the index, answering entirely from Grep and Read.
    ##
    ## Second, and this corrected the diagnosis: naming the tools took it to one cell of two. The
    ## cell that used them called all three with ZERO ToolSearch — so the tools were in the tool
    ## list the entire time and discovery was never the problem. Its twin, same config and same
    ## brief, simply did not reach for them. That is ADOPTION VARIANCE between otherwise
    ## identical cells.
    ##
    ## The hypothesis puts adoption OUT OF SCOPE: the claim under test is whether the index
    ## yields better answers more cheaply, not whether an agent thinks to use it. An index arm
    ## that silently answers from source is therefore not a weak result — it is a cell that
    ## measured the wrong thing, and blending it into the arm's score makes the quality axis
    ## meaningless. Instructing the arm is the CONTROL that holds adoption constant, which is why
    ## this reads as an instruction rather than an inventory.
    "index": (
        "You have the usual shell and file tools — Read, Grep, Glob and Bash — and additionally a "
        "queryable index of this repository: mcp__clew__dossier for everything known about a "
        "named symbol, mcp__clew__search to find a name or enumerate a layer, mcp__clew__index "
        "for status. USE THE INDEX FIRST for any question about a symbol, its callers or callees, "
        "what it touches, or where something lives; fall back to reading source only where the "
        "index cannot answer."
    ),
    ## NO SHELL AT ALL. The arm cannot read a line of source, so a mark it misses is a mark the
    ## index does not carry — which is the whole point. It also means marks whose ANSWER FORM
    ## needs source (quote this comment, show these lines) will fail here even when the index
    ## holds the fact, and that is informative rather than a defect: it partitions the rubric
    ## into what the index can answer and what it can only point at.
    "index_only": (
        "You have ONLY a queryable index of this repository — no shell, no file reading, no "
        "search over the source. The tools are mcp__clew__dossier for everything known about a "
        "named symbol, mcp__clew__search to find a name or enumerate a layer, and "
        "mcp__clew__index for status. Answer from the index alone. Where the index cannot tell "
        "you something, say so plainly rather than guessing — an honest gap is the useful "
        "answer here."
    ),
}

_BRIEF = """Answer the question below about the repository at {root}.

{tools}

Work however you judge best. There is no required format, no word limit and no
structure you are expected to follow — write the answer as prose, at whatever
length the question deserves.

QUESTION:
{question}
"""


## @brief One unit of work: a single question, arm, model and replicate.
## @version 1
@dataclass(frozen=True)
class Cell:
    """@brief One generation cell.
    @version 1
    """

    target: str
    question_id: str
    arm: str
    model: str
    replicate: int
    order: int

    ## @brief Stable filename stem for this cell's artifacts.
    ## @return Stem.
    ## @version 1
    def stem(self) -> str:
        """@brief Artifact name.
        @return Filename stem.
        @version 1
        """
        return f"{self.question_id}_{self.model}_{self.arm}_r{self.replicate}"


## @brief Build one arm's brief.
## @param arm Which arm.
## @param root Repository root shown to the agent.
## @param question The question prompt.
## @return Brief text.
## @version 1
def brief(arm: str, root: str, question: str) -> str:
    """NO RESPONSE FORMAT IS REQUESTED, and that absence is load-bearing.

    A field list shown to the answering agent leaks the answer: `CONCURRENCY: NONE | <list>`
    announces that NONE is on the menu, which is the inference under test. It also helps the
    BASELINE arm more, because the index arm would surface gate state anyway — so the leak does
    not merely make both arms easier, it shrinks the measured gap for a reason unrelated to the
    tools. All structure lives at grading time.

    @brief One arm's brief.
    @return Brief text.
    @version 1
    """
    if arm not in ALL_ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {list(ALL_ARMS)}")
    return _BRIEF.format(root=root, tools=_TOOLS[arm], question=question)


## @brief Refuse unless the two briefs differ only in the tool sentence.
## @return None.
## @version 1
def check_symmetry() -> None:
    """A STRUCTURAL CHECK, not a reading. The two briefs are rendered with identical inputs and
    diffed; the only permitted changed lines are the tool sentences themselves.

    If the baseline arm underperforms because it was under-prompted rather than because its
    tools are limited, every quality delta is an artifact of prompt asymmetry and nothing in the
    result would say so.

    @brief Prompt symmetry holds.
    @return None.
    @version 1
    """
    ## DERIVED FROM `ARMS`, never hardcoded. This check named its two arms literally and kept
    ## comparing the OLD pair after the compared arms changed — it refused a correct
    ## configuration while silently no longer checking the one in use.
    first, second = ARMS
    left = brief(first, "/repo", "Q?").splitlines()
    right = brief(second, "/repo", "Q?").splitlines()
    ## `line[1:]`, NOT `line[2:]`. `unified_diff` prefixes ONE character; slicing two ate the
    ## first character of every line, so nothing ever matched `permitted` and the check refused
    ## its own symmetric briefs. It failed loudly, which is the only reason it was cheap.
    changed = [
        line[1:]
        for line in difflib.unified_diff(left, right, n=0, lineterm="")
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    ## ONLY THE COMPARISON ARMS. The ceiling arm is deliberately asymmetric — it is not part of
    ## the grid and diffing it here would either fail the check or dilute it into permitting
    ## anything.
    permitted = {_TOOLS[a] for a in ARMS}
    stray = [line for line in changed if line not in permitted]
    if stray:
        raise ValueError(
            "the two arms' briefs differ outside the tool sentence, which builds a handicap "
            f"into the instrument: {stray}"
        )


## @brief The ordered cell plan for one run.
## @param rubric The validated rubric.
## @param models Model tiers, outermost loop.
## @param replicates Runs per (question, arm).
## @param seed Recorded, and combined with the target so the shuffle is reproducible per target.
## @return Ordered cells.
## @version 2
def plan(rubric: Rubric, models: tuple[str, ...], replicates: int, seed: int) -> list[Cell]:
    """COUNTERBALANCED ON REPLICATE PARITY. If one arm always ran first, any drift over the run —
    load, throttling, capacity state — would be confounded with arm, and the subtraction that
    produces every headline number would carry it.

    THE SHUFFLE IS SEEDED FROM (seed, target), NOT THE SEED ALONE. Every shipped rubric holds
    five questions, so a bare seed shuffled the same-length list once per target from a fresh
    RNG and every target opened with the SAME question — position perfectly correlated with
    question across the whole grid rather than averaged out by it. Any start-of-run effect then
    lands on one question every time, which is the exact confound the shuffle exists to remove.

    Mixing the target in keeps the seed's whole purpose: an order is still a pure function of
    what is recorded in `run.json`, so a grid replays exactly.

    @brief Ordered cells for a run.
    @return Cells in execution order.
    @version 2
    """
    if replicates < 1:
        raise ValueError("replicates must be at least 1")
    rng = random.Random(f"{seed}:{rubric.target}")
    order = 0
    cells: list[Cell] = []
    for model in models:
        questions = [q.id for q in rubric.questions]
        rng.shuffle(questions)
        for qid in questions:
            for rep in range(1, replicates + 1):
                pair = ARMS if rep % 2 else tuple(reversed(ARMS))
                for arm in pair:
                    cells.append(Cell(rubric.target, qid, arm, model, rep, order))
                    order += 1
    return cells


## @brief Refuse unless the checkout is at the rubric's pinned commit.
## @param rubric The rubric.
## @param root Target working tree.
## @return None.
## @version 1
def check_revision(rubric: Rubric, root: Path) -> None:
    """A rubric verified against one tree and run against another grades code the answer never
    saw, and every mark's line number is then a claim about a different file.

    @brief Checkout is at the pin.
    @return None.
    @version 1
    """
    try:
        got = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"{root}: cannot read HEAD: {exc}") from exc
    head = got.stdout.strip()
    if head != rubric.commit:
        raise ValueError(
            f"{root} is at {head or '<unknown>'} but the rubric pins {rubric.commit}. "
            f"Check out the pin; do not adjust the rubric to match the tree"
        )
    ## HEAD IS NOT THE TREE. A dirty working tree passes a rev-parse check while both arms read
    ## files the rubric was never verified against — every line number in it is then a claim
    ## about content nobody checked. A freshly fetched target cannot be dirty; a LOCAL checkout
    ## reused as a target silently can, which is exactly how two of the reference targets are
    ## provisioned.
    try:
        dirty = subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=no"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        ).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"{root}: cannot read working-tree state: {exc}") from exc
    if dirty:
        raise ValueError(
            f"{root} is at the pinned commit but its working tree is MODIFIED:\n{dirty}\n"
            f"The rubric was verified against the pin, not against these edits. Stash or commit "
            f"them; do not measure a tree nobody checked"
        )


## @brief Refuse unless the built index recorded every declared section.
## @param rubric The rubric.
## @param build_meta The index's recorded build metadata.
## @return None.
## @version 1
def check_declaration_applied(rubric: Rubric, build_meta: dict) -> None:
    """THE CHECK WHOSE ABSENCE LET A WHOLE PHASE OF WORK GO UNMEASURED. A committed declaration
    that never reached the build makes the measured index differ from the intended one, and
    every downstream result describes a build nobody chose.

    THE SIGNAL IS THE TIER, NOT THE KEY'S PRESENCE. `build_meta` stamps `options.<leaf>.tier` for
    EVERY option it knows about, declared or not, and an undeclared one reads `heuristic`. So a
    key-presence check passes on a build that ignored the declaration entirely — which is the
    exact failure this exists to catch, dressed as a pass.

    IT ALSO COMPARES AT THE LEAF, NOT THE SECTION. A rubric declares `preprocessor.predefined`;
    the index records `options.predefined`. The first version compared section names to leaf keys
    and refused a build whose declaration had landed perfectly. It refused loudly rather than
    passing wrongly, which is the only reason that was cheap.

    @brief The declaration reached the build.
    @return None.
    @version 2
    """
    if not rubric.declare:
        return
    rows = build_meta or {}
    wanted: set[str] = set()
    for section, body in rubric.declare.items():
        leaves = body if isinstance(body, dict) else {}
        wanted |= set(leaves) if leaves else {section}
    unapplied = sorted(
        leaf for leaf in wanted if str(rows.get(f"options.{leaf}.tier", "")) in ("", "heuristic")
    )
    if unapplied:
        raise ValueError(
            f"the rubric declares {sorted(wanted)} but the built index records no explicit tier "
            f"for {unapplied} — the declaration did not reach the build, so the index under test "
            f"is not the index the rubric describes"
        )
