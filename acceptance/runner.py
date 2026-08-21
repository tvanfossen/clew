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
import hashlib
import random
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .grader.rubric import Rubric

ARMS = ("baseline", "index")

## THE ONLY PERMITTED DIFFERENCE BETWEEN THE TWO BRIEFS. Everything else is byte-identical and
## `check_symmetry` refuses on any other delta. Asymmetry in what an arm is TOLD is a handicap
## built into the instrument, and "is the baseline arm good enough" is otherwise an opinion.
_TOOLS = {
    "baseline": "You have the usual shell and file tools: Read, Grep, Glob and Bash.",
    "index": (
        "You have the usual shell and file tools — Read, Grep, Glob and Bash — and additionally "
        "a queryable index of this repository, exposed as MCP tools."
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
    if arm not in ARMS:
        raise ValueError(f"unknown arm {arm!r}; expected one of {list(ARMS)}")
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
    left = brief("baseline", "/repo", "Q?").splitlines()
    right = brief("index", "/repo", "Q?").splitlines()
    ## `line[1:]`, NOT `line[2:]`. `unified_diff` prefixes ONE character; slicing two ate the
    ## first character of every line, so nothing ever matched `permitted` and the check refused
    ## its own symmetric briefs. It failed loudly, which is the only reason it was cheap.
    changed = [
        line[1:]
        for line in difflib.unified_diff(left, right, n=0, lineterm="")
        if line.startswith(("+", "-")) and not line.startswith(("+++", "---"))
    ]
    permitted = set(_TOOLS.values())
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
## @param seed Recorded, so the shuffle is reproducible.
## @return Ordered cells.
## @version 1
def plan(rubric: Rubric, models: tuple[str, ...], replicates: int, seed: int) -> list[Cell]:
    """COUNTERBALANCED ON REPLICATE PARITY. If one arm always ran first, any drift over the run —
    load, throttling, capacity state — would be confounded with arm, and the subtraction that
    produces every headline number would carry it.

    @brief Ordered cells for a run.
    @return Cells in execution order.
    @version 1
    """
    if replicates < 1:
        raise ValueError("replicates must be at least 1")
    rng = random.Random(seed)
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


## @brief Refuse unless the built index recorded every declared section.
## @param rubric The rubric.
## @param build_meta The index's recorded build metadata.
## @return None.
## @version 1
def check_declaration_applied(rubric: Rubric, build_meta: dict) -> None:
    """THE CHECK WHOSE ABSENCE LET A WHOLE PHASE OF WORK GO UNMEASURED. A committed declaration
    that never reached the build makes the measured index differ from the intended one, and
    every downstream result describes a build nobody chose.

    Structural, by section NAME — not a count and not a prose note. A count passes when the
    wrong sections are present.

    @brief The declaration reached the build.
    @return None.
    @version 1
    """
    if not rubric.declare:
        return
    stated = (build_meta or {}).get("options") or {}
    missing = sorted(set(rubric.declare) - set(stated))
    if missing:
        raise ValueError(
            f"the rubric declares {sorted(rubric.declare)} but the built index records "
            f"{sorted(stated)} — missing: {missing}. The index under test is not the index "
            f"the rubric describes"
        )


## @brief A short digest binding a run to its rubric text.
## @param path Rubric file.
## @return Hex digest prefix.
## @version 1
def rubric_digest(path: Path) -> str:
    """Recorded with every run so a result names the exact rubric that produced it. A version
    string is a claim; a digest is a fact.

    @brief Rubric content digest.
    @return Digest prefix.
    @version 1
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()[:16]
