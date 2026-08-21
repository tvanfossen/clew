# SPDX-License-Identifier: MIT
"""Turn judge output into a score, and say what the score does not cover.

THE UNIT IS A BINARY DECISION, not a mark. A `retrieval` or `conclusion` mark is one decision.
A `set` mark of N members is N+1 — one per member, plus one for precision — because a set is
not one atomic fact. That is what lets a set measure WHERE AN ANSWER STOPPED without
reintroducing partial credit for a single fact: every decision stays hit-or-miss and the
gradient comes from there being several of them.

WEIGHT IS IMPORTANCE, NOT PARTIAL CREDIT. Score is `sum(weight * hit) / sum(weight)` over
decisions, so it cannot exceed 100% and no decision is ever worth a fraction of itself.

AN UNRULED DECISION IS NOT A MISS. It is excluded from neither numerator nor denominator
quietly — it stays in the denominator and `unmarked_pct` is reported beside every score.
Excluding them inflates every score the moment the judge gets flaky; scoring them 0 makes a
transport failure arithmetically identical to a wrong answer, which once turned 102 unruled
marks into failures against both arms.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .judge import Vote, anonymise, ask, extract_prompt, read_items, vote
from .rubric import Mark, Question, Rubric


## @brief One binary decision's outcome.
## @version 1
@dataclass(frozen=True)
class Decision:
    """@brief A single hit-or-miss judgement, its weight, and why it went that way.
    @version 1
    """

    mark: str
    kind: str
    weight: int
    hit: bool | None
    detail: str = ""
    agreement: float = 0.0
    samples: int = 0
    errors: int = 0


## @brief Every decision for one question, plus the score they imply.
## @version 1
@dataclass
class QuestionResult:
    """@brief Scored decisions for one question.
    @version 1
    """

    id: str
    decisions: list[Decision] = field(default_factory=list)

    ## @brief Weighted score over ruled decisions, with unruled left in the denominator.
    ## @return (score, unmarked_pct).
    ## @version 1
    def score(self) -> tuple[float, float]:
        """@brief Weighted score and the share of weight the judge never ruled on.
        @return (score, unmarked_pct).
        @version 1
        """
        total = sum(d.weight for d in self.decisions)
        if not total:
            return 0.0, 0.0
        earned = sum(d.weight for d in self.decisions if d.hit)
        unruled = sum(d.weight for d in self.decisions if d.hit is None)
        return earned / total, unruled / total


## @brief Normalise a path or name for set comparison.
## @param value Raw item text.
## @return Comparable key.
## @version 1
def _key(value: str) -> str:
    """Compare on the LAST path segment plus a lowercase fold.

    An answer writing `programs/ssl/ssl_pthread_server.c`, `./programs/ssl/ssl_pthread_server.c`
    or `ssl_pthread_server.c` has named the same file, and grading it otherwise would measure
    citation style rather than what the agent found. Two DIFFERENT files sharing a basename
    would collide — declare fuller values in that case; the rubric controls the members.

    @brief Comparison key.
    @return Normalised key.
    @version 1
    """
    return value.strip().strip("`'\"").rstrip("/").rsplit("/", 1)[-1].lower()


## @brief Score one set mark: a decision per member, plus one for precision.
## @param mark The set mark.
## @param answer Anonymised answer.
## @param model Dated judge model id.
## @return List of decisions.
## @version 1
def score_set(mark: Mark, answer: str, model: str) -> list[Decision]:
    """PRECISION IS A DECISION, NOT A MODIFIER. Once grading is known to be mechanical the
    optimal strategy for recall alone is to name everything, so an answer that pads its list
    loses a decision it would otherwise have won. Both arms are subject to it identically, so it
    is not a bias — it removes the incentive to dump.

    @brief Score a set mark.
    @return Decisions.
    @version 1
    """
    reply = ask(extract_prompt(mark.extract, answer), model)
    named = None if reply.error else read_items(reply.text)
    if named is None:
        return [
            Decision(mark.text, "set", mark.weight, None, "extraction unavailable")
            for _ in range(len(mark.members) + 1)
        ]

    ## KEYED FOR COMPARISON, REPORTED AS WRITTEN. The detail line has to name what the answer
    ## actually said, or a reader cannot find the spurious item to check it — a normalised key
    ## sends them looking for a string that appears nowhere in the answer.
    got = {_key(item): item for item in named}
    out: list[Decision] = []
    correct = set()
    for member in mark.members:
        key = _key(str(member["value"]))
        correct.add(key)
        found = key in got
        out.append(
            Decision(
                f"{mark.text} — {member['value']}",
                "set_member",
                mark.weight,
                found,
                "named" if found else "not named",
            )
        )
    spurious = sorted(raw for key, raw in got.items() if key not in correct)
    out.append(
        Decision(
            f"{mark.text} — precision",
            "set_precision",
            mark.weight,
            not spurious,
            "clean" if not spurious else f"named {len(spurious)} not in the set: {spurious}",
        )
    )
    return out


## @brief Score every mark of one question against one answer.
## @param question The question.
## @param answer Raw answer text; anonymised here.
## @param rubric The owning rubric, for the judge model and vote threshold.
## @param arm Which arm produced the answer, used only for fencing.
## @return QuestionResult.
## @version 1
def score_question(question: Question, answer: str, rubric: Rubric, arm: str) -> QuestionResult:
    """A FENCED MARK IS EXCLUDED FROM THE ARM THAT CANNOT REACH IT, never scored zero against it.
    `arm_only` names the arm that CAN reach the mark, so it leaves the other arm's denominator
    entirely — scoring it zero would report a handicap the harness imposed as a result the arm
    produced.

    @brief Score one question.
    @return QuestionResult.
    @version 1
    """
    body = anonymise(answer)
    result = QuestionResult(id=question.id)
    for mark in question.marks:
        if mark.arm_only and mark.arm_only != arm:
            continue
        if mark.type == "set":
            result.decisions.extend(score_set(mark, body, rubric.judge_model))
            continue
        n = 3 if mark.weight >= rubric.judge_samples_when_weight_at_least else 1
        voted: Vote = vote(mark.text, body, rubric.judge_model, n)
        result.decisions.append(
            Decision(
                mark=mark.text,
                kind=mark.type,
                weight=mark.weight,
                hit=None if voted.verdict is None else voted.verdict == "HIT",
                detail="" if voted.verdict else f"{voted.errors}/{voted.samples} calls failed",
                agreement=voted.agreement,
                samples=voted.samples,
                errors=voted.errors,
            )
        )
    return result
