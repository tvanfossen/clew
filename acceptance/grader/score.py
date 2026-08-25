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

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

from collections import Counter

from .judge import Vote, anonymise, ask, extract_prompt, read_items, vote
from .rubric import Mark, Question, Rubric


## Length of the published grader fingerprint. It exists to be COMPARED, never inverted.
FINGERPRINT_CHARS = 12


## @brief Identify the grader's own source, so passes under different code are separable.
## @param root Grader package directory; defaults to this module's own.
## @return Short hex digest, or "" when the tree cannot be read.
## @version 1
def grader_fingerprint(root: Path | None = None) -> str:
    """FOUND BY USING THE VARIANCE MACHINERY THIS PACKAGE FEEDS. Two grades of the same frozen
    answers spread -12.1pt to +15.0pt and it was read as judge noise — twice, in two different
    shapes, and both readings were wrong. The judge RETRY had landed between those grades, so
    marks that were previously left unruled started being ruled and the scores moved because the
    GRADER changed underneath them. Two consecutive passes under one grader version then
    reproduced all five cells exactly.

    A pass already records `rubric_digest`, because comparing across rubrics is meaningless. The
    identical argument applies to the grader, and nothing recorded it — so a variance figure
    could silently be measuring a code change and read as a property of the judge.

    ALL THREE MODULES, because a score can move from any of them: `score.py` decides weighting,
    `judge.py` decides what the judge is asked and how a reply is read, `rubric.py` decides what
    a mark IS.

    DERIVED, NEVER HAND-MAINTAINED. A constant somebody must remember to bump is a constant that
    will be forgotten in exactly the commit that matters — the one that changes how a mark is
    decided.

    ONLY `.py` IS HASHED. A `.pyc` is regenerated as a side effect of importing the very code
    being identified, so hashing bytecode would make the fingerprint change because it was read.

    @brief Fingerprint the grader's source.
    @return Short digest, or "" when unreadable.
    @version 1
    """
    here = root if root is not None else Path(__file__).resolve().parent
    try:
        sources = sorted(p for p in here.glob("*.py"))
        digest = hashlib.sha256()
        for path in sources:
            digest.update(path.name.encode("utf-8"))
            digest.update(path.read_bytes())
    except OSError:
        return ""
    return digest.hexdigest()[:FINGERPRINT_CHARS] if sources else ""


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

    ## @brief Decisions where the judge's samples did not agree.
    ## @return Count of split verdicts.
    ## @version 2
    def split_decisions(self) -> int:
        """A SPLIT VERDICT IS A DECISION THE JUDGE WAS NOT SURE OF, and that is all this counts.

        IT DOES NOT PREDICT DRIFT, and an earlier version of this docstring claimed it did.
        Measured on five cells regraded against an unchanged rubric: three cells carrying a
        split verdict reproduced to the decimal, while the two that moved were a split cell
        (+10.0pt) and a cell with NO split verdicts at all (-12.1pt). The largest movement came
        from a cell where every sampled verdict was unanimous — so a mark can be decided 3-0 one
        way and 3-0 the other on the next pass, which is a worse failure than a visible split
        and one this number cannot see.

        Kept because an uncertain decision is worth flagging on its own terms, and because a
        real noise floor needs replicates rather than one regrade of n=5.

        SET DECISIONS ARE EXCLUDED. They carry agreement 0.0 with samples 0 because it was the
        EXTRACTION that was voted, not the verdict; counting them would mark every set member
        uncertain.

        @brief Count split verdicts.
        @return Number of decisions whose samples disagreed.
        @version 2
        """
        return sum(1 for d in self.decisions if d.samples > 0 and 0.0 < d.agreement < 1.0)


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
## @param samples Independent extraction calls to vote over.
## @return List of decisions.
## @version 1
def score_set(mark: Mark, answer: str, model: str, samples: int = 3) -> list[Decision]:
    """PRECISION IS A DECISION, NOT A MODIFIER. Once grading is known to be mechanical the
    optimal strategy for recall alone is to name everything, so an answer that pads its list
    loses a decision it would otherwise have won. Both arms are subject to it identically, so it
    is not a bias — it removes the incentive to dump.

    @brief Score a set mark.
    @return Decisions.
    @version 1
    """
    ## EXTRACTION IS VOTED, for the same reason verdicts are and with more urgency: a set mark
    ## of N members is N+1 decisions ALL resting on this call, so one flaky extraction moves far
    ## more weight than one flaky verdict.
    ##
    ## OBSERVED, NOT ANTICIPATED. Grading the same answer twice extracted NONE once and `include`
    ## the other time, flipping two decisions and moving that cell ten points — while every
    ## verdict decision in the same cell agreed unanimously. The judge-variance measurement that
    ## found 0 flips covered VERDICT calls only, and said so; this is the other half.
    ##
    ## An item counts when a MAJORITY of successful extractions named it. Union would inherit
    ## every hallucination; intersection would punish an answer for one flaky call.
    prompt = extract_prompt(mark.extract, answer)
    tally: Counter = Counter()
    ## KEYED FOR COMPARISON, REPORTED AS WRITTEN. A detail line naming the normalised key sends
    ## a reader looking for a string that appears nowhere in the answer.
    written: dict[str, str] = {}
    ok = 0
    for _ in range(max(1, samples)):
        reply = ask(prompt, model)
        items = None if reply.error else read_items(reply.text)
        if items is None:
            continue
        ok += 1
        for item in {_key(i): i for i in items}.items():
            tally[item[0]] += 1
            written.setdefault(item[0], item[1])
    if not ok:
        return [
            Decision(mark.text, "set", mark.weight, None, "extraction unavailable")
            for _ in range(len(mark.members) + 1)
        ]

    got = {key: written[key] for key, n in tally.items() if n * 2 > ok}
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
    ## SILENCE DOES NOT EARN PRECISION. An answer that named NOTHING has an empty prediction
    ## set, so it has nothing spurious in it and scored clean under the first version — a mark
    ## satisfiable by saying nothing, which is the exact failure the design forbids. Caught by
    ## the discrimination check: a deliberately shallow answer named zero directories and won
    ## this decision. Precision is undefined on an empty set; here it is a MISS, because the
    ## answer contributed no set information at all.
    spurious = sorted(raw for key, raw in got.items() if key not in correct)
    if not got:
        detail = "named nothing — precision is not earned by silence"
    elif spurious:
        detail = f"named {len(spurious)} not in the set: {spurious}"
    else:
        detail = "clean"
    out.append(
        Decision(
            f"{mark.text} — precision",
            "set_precision",
            mark.weight,
            bool(got) and not spurious,
            detail,
        )
    )
    return out


## @brief Score every mark of one question against one answer.
## @param question The question.
## @param answer Raw answer text; anonymised here.
## @param rubric The owning rubric, for the judge model and vote threshold.
## @param arm Which arm produced the answer, used only for fencing.
## @return QuestionResult.
## @version 2
def score_question(question: Question, answer: str, rubric: Rubric, arm: str) -> QuestionResult:
    """A FENCED MARK IS EXCLUDED FROM THE ARM THAT CANNOT REACH IT, never scored zero against it.
    `arm_only` names the arm that CAN reach the mark, so it leaves the other arm's denominator
    entirely — scoring it zero would report a handicap the harness imposed as a result the arm
    produced.

    @brief Score one question.
    @return QuestionResult.
    @version 2
    """
    body = anonymise(answer)
    result = QuestionResult(id=question.id)
    for mark in question.marks:
        if mark.arm_only and mark.arm_only != arm:
            continue
        if mark.type == "set":
            result.decisions.extend(score_set(mark, body, rubric.judge_model, 3))
            continue
        n = 3 if mark.weight >= rubric.judge_samples_when_weight_at_least else 1
        voted: Vote = vote(mark.text, body, rubric.judge_model, n)
        result.decisions.append(
            Decision(
                mark=mark.text,
                kind=mark.type,
                weight=mark.weight,
                hit=None if voted.verdict is None else voted.verdict == "HIT",
                detail=(
                    ""
                    if voted.verdict
                    else f"{voted.errors}/{voted.samples} calls failed: "
                    + "; ".join(dict.fromkeys(voted.reasons))
                ),
                agreement=voted.agreement,
                samples=voted.samples,
                errors=voted.errors,
            )
        )
    return result
