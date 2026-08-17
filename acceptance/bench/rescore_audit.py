#!/usr/bin/env python
# SPDX-License-Identifier: MIT
##
# @brief Replay the objective pass over already-graded cells and report what a scorer change moved.
# @details The objective pass awards a mark with NO judge call when declared evidence matches, so a
#          defect in it is invisible: an auto-HIT produces a score and no second opinion. Changing
#          that pass silently re-writes the meaning of every published figure, and the only honest
#          way to change it is to say how far.
#
#          This replays the CURRENT scorer over the committed answers and diffs it against the
#          objective verdict each sidecar recorded at grading time. A mark that stops auto-hitting
#          does not become a MISS — it becomes `n/a`, which routes to the judge — so its true value
#          is unknown without re-judging. That gives a BRACKET rather than a number:
#
#            optimistic — every lost auto-HIT would have been judged HIT (score unchanged)
#            pessimistic — every lost auto-HIT would have been judged MISS
#
#          The published figure sits somewhere inside. Reporting the pessimistic bound alone would
#          overstate the damage; reporting the optimistic bound alone is how a scorer change gets
#          waved through. Both are printed, always.
#
#          Reads committed sidecars and answers only. No judge calls, no cells run.
# @version 1
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from bench_rubric import load_rubric  # noqa: E402
from bench_score import answer_citations, score_mark  # noqa: E402


##
# @brief Replay one cell and count objective-verdict movement.
# @param sidecar the `*.grade.json` recorded at grading time
# @param answer the graded answer text
# @param marks the rubric marks for this cell's question
# @return dict of counters plus the list of marks that stopped auto-hitting
# @version 1
def replay_cell(sidecar: dict, answer: str, marks: list) -> dict:
    """@brief Replay one cell's objective pass against the recorded one. @version 1"""
    cites = answer_citations(answer)
    by_index = {mark.index: mark for mark in marks}
    out = {"was_hit": 0, "still_hit": 0, "lost": 0, "gained": 0, "lost_marks": []}
    for recorded in sidecar.get("marks", []):
        mark = by_index.get(recorded["index"])
        if mark is None:
            continue
        before = (recorded.get("objective") or {}).get("verdict", "n/a")
        after = score_mark(mark, answer, cites).verdict
        out["was_hit"] += int(before == "HIT")
        out["still_hit"] += int(before == "HIT" and after == "HIT")
        if before == "HIT" and after != "HIT":
            out["lost"] += 1
            out["lost_marks"].append((recorded["index"], mark.text.strip().splitlines()[0][:70]))
        if before != "HIT" and after == "HIT":
            out["gained"] += 1
    return out


##
# @brief Judged outcome of the marks a cell did NOT auto-hit, used for the pessimistic bound.
# @param sidecar the sidecar
# @return number of marks the judge ruled HIT
# @version 1
def judged_hits(sidecar: dict) -> int:
    """@brief Count marks the judge ruled HIT. @version 1"""
    return sum(
        1 for m in sidecar.get("marks", []) if (m.get("judge") or {}).get("verdict") == "HIT"
    )


##
# @brief Audit every cell under an answer directory against one rubric.
# @param rubric_path rubric YAML
# @param answers directory of `*.grade.json` + `*.md`
# @return aggregate counters
# @version 1
def audit(rubric_path: Path, answers: Path) -> dict:
    """@brief Audit every cell under an answer directory against one rubric. @version 1"""
    marks_by_q = {qid: question.marks for qid, question in load_rubric(rubric_path).items()}
    total = {"cells": 0, "was_hit": 0, "still_hit": 0, "lost": 0, "gained": 0, "score": 0}
    losses: dict = {}
    for path in sorted(answers.glob("*.grade.json")):
        sidecar = json.loads(path.read_text())
        answer_file = answers / sidecar.get("answer", "")
        marks = marks_by_q.get(sidecar.get("q"))
        if marks is None or not answer_file.exists():
            continue
        cell = replay_cell(sidecar, answer_file.read_text(), marks)
        total["cells"] += 1
        total["score"] += sidecar.get("summary", {}).get("score", 0)
        for key in ("was_hit", "still_hit", "lost", "gained"):
            total[key] += cell[key]
        for index, text in cell["lost_marks"]:
            losses.setdefault((sidecar["q"], index, text), []).append(path.name)
    total["losses"] = losses
    return total


##
# @brief Print the audit for every (rubric, answers) pair given.
# @param pairs list of (rubric_path, answers_path)
# @return process exit code
# @version 1
def report(pairs: list) -> int:
    """@brief Print the audit for every (rubric, answers) pair given. @version 1"""
    for rubric_path, answers in pairs:
        total = audit(Path(rubric_path), Path(answers))
        print(f"\n=== {Path(answers).parent.name}/{Path(answers).name}  ({total['cells']} cells)")
        print(
            f"auto-HITs before {total['was_hit']}  still {total['still_hit']}  "
            f"LOST {total['lost']}  gained {total['gained']}"
        )
        print(
            f"score as published {total['score']:.0f}   "
            f"pessimistic bound (every lost auto-HIT judged MISS) {total['score'] - total['lost']:.0f}"
        )
        if total["losses"]:
            print("marks that stopped auto-hitting (they now route to the judge, verdict UNKNOWN):")
            for (qid, index, text), cells in sorted(total["losses"].items()):
                print(f"  {qid} #{index:<3} x{len(cells)}  {text}")
    return 0


##
# @brief CLI entry point.
# @return process exit code
# @version 1
def main() -> int:
    """@brief CLI entry point. @version 1"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pair", action="append", nargs=2, metavar=("RUBRIC", "ANSWERS"), required=True
    )
    args = parser.parse_args()
    return report(args.pair)


if __name__ == "__main__":
    sys.exit(main())
