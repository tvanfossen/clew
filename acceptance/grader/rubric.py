# SPDX-License-Identifier: MIT
"""Load and VALIDATE a rubric. Every rule here refuses rather than defaults.

The previous generation's failures were almost all silent acceptance: a fence spelled one way
and parsed another reported zero fenced marks; a mark's machine-checkability was decided by
whether its prose happened to contain a backtick; two rubrics carried no version at all, so
version preflight was inert on them and nothing said so.

So the shape of this module is: one `load` that either returns a fully-validated rubric or
raises naming the offending path. There is no partial parse and no best-effort mode, because a
rubric that half-parses grades a run and publishes a number.

Usage:
    .venv/bin/python -m acceptance.grader.rubric validate acceptance/targets/mbedtls/questions.yaml
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SCHEMA = 1

MARK_TYPES = ("retrieval", "conclusion", "set")
ARMS = ("baseline", "index")

_TOP_REQUIRED = ("schema", "target", "commit", "version", "ground_truth", "judge", "questions")
_TOP_OPTIONAL = ("ref", "index")
_QUESTION_REQUIRED = ("id", "intent", "prompt", "marks")
_MARK_REQUIRED = ("text", "type", "weight")
_MARK_OPTIONAL = ("evidence", "refs", "arm_only", "reason", "extract", "members")

## A COUNT IS NEVER WRITTEN. Every written count in the previous generation was wrong at some
## point, so the keys that used to hold them are refused outright rather than ignored.
_BANNED_KEYS = frozenset({"marks_count", "graded_marks", "index", "mark_count", "count"})


class RubricError(ValueError):
    """@brief A rubric that cannot be trusted to grade a run.
    @version 1
    """


## @brief One gradeable item.
## @version 1
@dataclass(frozen=True)
class Mark:
    """@brief A single answer component, binary: stated or not.
    @version 1
    """

    text: str
    type: str
    weight: int
    evidence: str = ""
    refs: tuple = ()
    arm_only: str = ""
    reason: str = ""
    extract: str = ""
    members: tuple = ()

    ## @brief Number of binary decisions this mark contributes.
    ## @return Count of sub-decisions.
    ## @version 1
    @property
    def decisions(self) -> int:
        """A SET IS NOT ONE FACT. Each declared member is its own binary decision at this
        mark's weight, plus one for precision — which is what lets a set measure WHERE AN
        ANSWER STOPPED without reintroducing partial credit for a single fact.

        @brief Binary decisions contributed.
        @return Count.
        @version 1
        """
        return len(self.members) + 1 if self.type == "set" else 1


## @brief One question and its marks.
## @version 1
@dataclass(frozen=True)
class Question:
    """@brief A question, its authoring intent, and its answer components.
    @version 1
    """

    id: str
    intent: str
    prompt: str
    marks: tuple[Mark, ...] = ()


## @brief A validated rubric.
## @version 1
@dataclass(frozen=True)
class Rubric:
    """@brief Everything needed to grade one target, validated.
    @version 1
    """

    target: str
    commit: str
    version: str
    ground_truth: str
    judge_model: str
    judge_samples_when_weight_at_least: int
    questions: tuple[Question, ...] = ()
    ref: str = ""
    declare: dict = field(default_factory=dict)
    variant_note: str = ""


## @brief Refuse any key that is not in the allowed set, naming it.
## @param doc Mapping to check.
## @param allowed Every permitted key.
## @param where Human-readable location for the error.
## @return None.
## @version 1
def _reject_unknown(doc: dict, allowed: tuple[str, ...], where: str) -> None:
    """Fail closed at the ENTRY level, not just the document level.

    An entry-level slip — `key_arg_idx` for `key_arg_index` — parses to a valid mapping that no
    consumer reads, and that shape is this project's most repeated defect. Naming the offending
    key and the allowed set is what turns it from silent into loud.

    @brief Refuse unknown keys by name.
    @return None.
    @version 1
    """
    unknown = set(doc) - set(allowed)
    banned = unknown & _BANNED_KEYS
    if banned:
        raise RubricError(
            f"{where}: {sorted(banned)} is a written COUNT. Counts are derived from list "
            f"length, never written — every written count here has been wrong at some point"
        )
    if unknown:
        raise RubricError(f"{where}: unknown key(s) {sorted(unknown)}; allowed: {sorted(allowed)}")


## @brief Validate one mark and build it.
## @param raw The mark mapping.
## @param where Location for errors.
## @return Mark.
## @version 1
def _mark(raw: dict, where: str) -> Mark:
    """Every rule refuses. `type` is DECLARED — the previous generation inferred it from the
    absence of symbols and refs, so punctuation decided how a mark was graded.

    @brief Build a validated mark.
    @return Mark.
    @version 1
    """
    _reject_unknown(raw, _MARK_REQUIRED + _MARK_OPTIONAL, where)
    for key in _MARK_REQUIRED:
        if not raw.get(key) and raw.get(key) != 0:
            raise RubricError(f"{where}: missing required key '{key}'")
    kind = raw["type"]
    if kind not in MARK_TYPES:
        raise RubricError(f"{where}: type '{kind}' is not one of {list(MARK_TYPES)}")
    weight = raw["weight"]
    if not isinstance(weight, int) or weight < 1:
        raise RubricError(f"{where}: weight must be a positive integer, got {weight!r}")

    arm = raw.get("arm_only", "") or ""
    if arm:
        if arm not in ARMS:
            raise RubricError(f"{where}: arm_only '{arm}' is not one of {list(ARMS)}")
        if not raw.get("reason"):
            raise RubricError(
                f"{where}: arm_only='{arm}' requires a `reason`. A mark only one arm can "
                f"reach measures ACCESS, not understanding, so fencing one is a claim that "
                f"has to be written down"
            )

    members = tuple(raw.get("members") or ())
    if kind == "set":
        if not members:
            raise RubricError(f"{where}: a set mark must declare its `members`")
        if not raw.get("extract"):
            raise RubricError(
                f"{where}: a set mark must declare an `extract` prompt. The judge is asked "
                f"what the answer NAMES and is never shown the correct set — that is what "
                f"keeps recall honest and precision computable"
            )
        for i, member in enumerate(members):
            if not isinstance(member, dict) or not member.get("value"):
                raise RubricError(f"{where}: members[{i}] needs a `value`")
    elif members or raw.get("extract"):
        raise RubricError(f"{where}: `members`/`extract` are only meaningful on type: set")

    return Mark(
        text=str(raw["text"]).strip(),
        type=kind,
        weight=weight,
        evidence=str(raw.get("evidence") or "").strip(),
        refs=tuple(tuple(r) for r in (raw.get("refs") or ())),
        arm_only=arm,
        reason=str(raw.get("reason") or "").strip(),
        extract=str(raw.get("extract") or "").strip(),
        members=members,
    )


## @brief Validate one question and build it.
## @param raw The question mapping.
## @return Question.
## @version 1
def _question(raw: dict) -> Question:
    """THE ONE CONTENT RULE A SCRIPT CAN ENFORCE lives here: every question must carry at least
    one `conclusion` mark. A question with none is testing retrieval, and retrieval is the axis
    the hypothesis explicitly does not claim.

    @brief Build a validated question.
    @return Question.
    @version 1
    """
    qid = raw.get("id") or "<unnamed question>"
    where = f"question {qid}"
    _reject_unknown(raw, _QUESTION_REQUIRED, where)
    for key in _QUESTION_REQUIRED:
        if not raw.get(key):
            raise RubricError(f"{where}: missing required key '{key}'")
    marks = tuple(_mark(m, f"{where} mark[{i}]") for i, m in enumerate(raw["marks"]))
    if not any(m.type == "conclusion" for m in marks):
        raise RubricError(
            f"{where}: carries no `conclusion` mark. Every question must have at least one "
            f"component reachable only by argument over what was read — a question with none "
            f"measures retrieval path, not whether the question was answered"
        )
    return Question(
        id=str(qid),
        intent=str(raw["intent"]).strip(),
        prompt=str(raw["prompt"]).strip(),
        marks=marks,
    )


## @brief Load and fully validate a rubric file.
## @param path Path to the rubric YAML.
## @return Rubric.
## @version 1
def load(path: Path) -> Rubric:
    """Either a fully-validated rubric or a raise naming the offending path. No partial parse.

    @brief Load a rubric.
    @param path Rubric file.
    @return Rubric.
    @version 1
    """
    try:
        doc: Any = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise RubricError(f"{path}: unreadable: {exc}") from exc
    if not isinstance(doc, dict):
        raise RubricError(f"{path}: top level is not a mapping")

    _reject_unknown(doc, _TOP_REQUIRED + _TOP_OPTIONAL, str(path))
    for key in _TOP_REQUIRED:
        if not doc.get(key):
            raise RubricError(f"{path}: missing required key '{key}'")
    if doc["schema"] != SCHEMA:
        raise RubricError(f"{path}: schema {doc['schema']!r}, this grader speaks {SCHEMA}")

    judge = doc["judge"]
    model = str(judge.get("model") or "")
    ## AN ALIAS IS REFUSED. `sonnet` moves under the rubric without the commit pin changing,
    ## which makes "repeatable so long as the pin holds" false in a way nothing reports.
    if "-" not in model or not any(ch.isdigit() for ch in model):
        raise RubricError(
            f"{path}: judge.model {model!r} looks like an alias. Pin a DATED model id — an "
            f"alias moves under the rubric while the commit pin still reads as held"
        )

    index = doc.get("index") or {}
    declare = index.get("declare") or {}
    variant = str(index.get("variant_note") or "").strip()
    if declare and not variant:
        raise RubricError(
            f"{path}: index.declare is set but index.variant_note is empty. A declared build "
            f"can differ from what the target ships, and marks may ask about the shipped "
            f"default — say so where the marks are"
        )

    questions = tuple(_question(q) for q in doc["questions"])
    if not questions:
        raise RubricError(f"{path}: no questions")
    seen: set[str] = set()
    for q in questions:
        if q.id in seen:
            raise RubricError(f"{path}: duplicate question id {q.id!r}")
        seen.add(q.id)

    return Rubric(
        target=str(doc["target"]),
        commit=str(doc["commit"]),
        version=str(doc["version"]),
        ground_truth=str(doc["ground_truth"]).strip(),
        judge_model=model,
        judge_samples_when_weight_at_least=int(judge.get("samples_when_weight_at_least", 2)),
        questions=questions,
        ref=str(doc.get("ref") or ""),
        declare=declare,
        variant_note=variant,
    )


## @brief CLI entry point.
## @return Exit code.
## @version 1
def main() -> int:
    """Validate a rubric and print what it holds, so a reader can see the shape it accepted.

    @brief Entry point.
    @return Exit code.
    @version 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("path", type=Path)
    args = parser.parse_args()
    try:
        rubric = load(args.path)
    except RubricError as exc:
        print(f"REFUSED — {exc}", file=sys.stderr)
        return 1
    decisions = sum(m.decisions for q in rubric.questions for m in q.marks)
    points = sum(m.weight * m.decisions for q in rubric.questions for m in q.marks)
    print(f"{rubric.target} @ {rubric.commit[:10]}  rubric {rubric.version}")
    print(f"judge: {rubric.judge_model}")
    print(f"{len(rubric.questions)} questions, {decisions} binary decisions, {points} points")
    for q in rubric.questions:
        kinds = {t: sum(1 for m in q.marks if m.type == t) for t in MARK_TYPES}
        print(f"  {q.id:<5} {len(q.marks):>3} marks  {kinds}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
