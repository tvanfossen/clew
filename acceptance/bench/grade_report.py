## @brief Merge completeness grades, blind-pairwise results and runner metrics into one doc.
## @version 1
"""Emit the three-axis results table.

Axis 1 (time/cost) comes from `run_matrix.py`'s `metrics.csv`, axes 2 and 3 from
the `*.grade.json` / `*_pairwise.json` sidecars this grader writes. They are
joined on the answer filename so the three axes sit in one row and cannot drift
apart.

The report always ends with a **Reliability** section — judge errors,
position-bias flips and runner-invalid cells. These grades are advisory; a
reader must be able to see how much of the table to distrust before reading the
numbers.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


## @brief Load the runner's metrics rows keyed by answer filename.
## @param answers Run directory.
## @return Mapping answer filename -> metrics row.
## @version 1
def _metrics(answers: Path) -> dict[str, dict]:
    """@brief Read metrics.csv if the runner produced one.
    @return Metrics by answer filename.
    @version 1
    """
    path = answers / "metrics.csv"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        return {row["answer_path"]: row for row in csv.DictReader(handle)}


## @brief Load every completeness sidecar in a run directory.
## @param answers Run directory.
## @return Sidecar dicts ordered by question then arm.
## @version 1
def _grades(answers: Path) -> list[dict]:
    """@brief Read the `*.grade.json` sidecars.
    @return Grade records.
    @version 1
    """
    found = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(answers.glob("*.grade.json"))
    ]
    return sorted(found, key=lambda g: (g["q"], g["arm"], g["model"], g["run"]))


## @brief Count the non-index tool calls in one metrics row.
## @param row One `metrics.csv` row.
## @return The count as a string, or "-" when it cannot be computed.
## @version 1
def _non_index_tools(row: dict) -> str:
    """`tool_uses - used_db_tools`. Both operands have been persisted per cell all along and
    nothing ever subtracted them, so the one number the owner asked for as a SMELL CHECK was
    reported nowhere. Returns "-" rather than 0 when either operand is absent, because a
    missing metrics row and an arm that touched no other tool are different facts.

    Not a graded axis: its cost is already inside the token count. It is here so a reader can
    see the index arm reaching for grep, which a token total cannot show.

    A NEGATIVE OPERAND IS UNMEASURED, NOT ZERO. `run_matrix` records `tool_uses: -1` and
    `used_db_tools: -1` for a cell whose transcript could not be found, and the subtraction
    turns that pair into `0` — so the cell with NO EVIDENCE AT ALL printed the best possible
    value on the one metric the owner asked for as a smell check. The guard is structural
    rather than a sentinel comparison: a tool-call count cannot be negative, so either operand
    being negative means the audit did not happen, whatever value stands for that.

    @brief Count the non-index tool calls in one metrics row.
    @return The count, or "-" when it cannot be computed.
    @version 2
    """
    try:
        total, indexed = int(row["tool_uses"]), int(row["used_db_tools"])
    except (KeyError, TypeError, ValueError):
        return "-"
    if total < 0 or indexed < 0:
        return "-"
    return str(total - indexed)


## @brief Render one cell's falsity-veto state as four distinguishable words.
## @param summary The cell's summary block.
## @return "VETOED", "DIVIDED", "clean" or "unchecked".
## @version 2
def _veto_cell(summary: dict) -> str:
    """FOUR STATES, NOT TWO, and the added one is the most useful thing this pass can say.
    "the pass did not run" and "the pass ran and found nothing" must not print the same word —
    this repo's standing rule is that unchecked never reads as checked-and-fine, and the
    identifier leak, the disarmed coverage gate and a retracted 36-cell grid all happened
    through exactly that collapse.

    `falsity_checked` is None when the pass was never armed and False when it ran but every
    sample errored. Both are `unchecked` here: from a reader's position they are the same fact,
    that nobody knows.

    DIVIDED IS THE ONE THAT WAS MISSING. A judge that ruled CONTRADICTED without reaching
    `VETO_AGREEMENT` leaves `vetoed` False and `checked` True, so this printed "clean" — the
    same word as the judge finding nothing wrong. "the answer contradicts a stated fact, on a
    divided vote" is precisely the state a human is supposed to arbitrate under D1, and it was
    the one state the report could not show. The veto's whole design records the agreement ratio
    "so a shaky verdict is visible rather than laundered into a clean number", and then the view
    laundered it.

    @brief Name the veto state for the per-cell table.
    @return The state word.
    @version 2
    """
    if summary.get("quality_vetoed"):
        return "**VETOED**"
    if summary.get("falsity_verdict") == "CONTRADICTED":
        return "DIVIDED"
    return "clean" if summary.get("falsity_checked") else "unchecked"


## @brief Build the combined per-cell table.
## @param grades Grade records.
## @param metrics Metrics rows by answer filename.
## @return Markdown lines.
## @version 3
def _cell_table(grades: list[dict], metrics: dict[str, dict]) -> list[str]:
    """THE SIX NUMBERS THE OWNER ASKED FOR, PER CELL, WITH NO VERDICT (D1, 2026-08-13): time,
    token cost, marks met, non-index tool count, tool count, turn count.

    No existing view answered that. `run_matrix report` prints tokens/tools/turns/ms and no
    marks; `tier_report` aggregates quality per model+arm — `_quality` keys on `(model, arm)`
    and sums across cells, so per-cell identity is destroyed inside the function — and it
    prints a pass/fail line. The join was already here and simply did not carry the columns.

    `unmarked_pct` sits beside the score deliberately: a score built from 69% of its marks is a
    different claim from the same score built from all of them, and 102 unruled marks were once
    counted as failures against both arms.

    `cost_usd` is NOT a column. It is `claude -p`'s token-value equivalent, not a charge, and
    presenting it per cell is how a "$0.5/cell" placeholder became an authoritative ~$40-70
    budget that blocked this task for days. It stays in `metrics.csv` for anyone who wants it.

    @brief Render completeness beside the runner's cost, tool and turn axes.
    @return Markdown lines.
    @version 2
    """
    lines = ["## Per-cell — the six reported metrics, and no verdict", "",
             "| Q | arm | model | run | marks | score | ms | tokens | turns | tools | non-idx | unmarked% | veto | valid |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]  # fmt: skip
    for grade in grades:
        s = grade["summary"]
        m = metrics.get(grade["answer"], {})
        lines.append(
            f"| {grade['q']} | {grade['arm']} | {grade['model']} | {grade['run']} | "
            f"{s['marks_hit']}/{s['marks_total']} | {s['score']} | "
            f"{m.get('duration_ms', '-')} | {m.get('total_tokens', '-')} | "
            f"{m.get('num_turns', '-')} | {m.get('tool_uses', '-')} | "
            f"{_non_index_tools(m)} | {s.get('unmarked_pct', '-')} | "
            f"{_veto_cell(s)} | {m.get('valid', '-')} |"
        )
    lines += ["", "`marks` is hit/total. `non-idx` is `tool_uses - used_db_tools` — a SMELL",
              "CHECK, not a graded axis, since its cost is already inside `tokens`. `unmarked%`",
              "is the share of marks the judge never ruled on; read it before the score.",
              "",
              "`veto` is D3: a statement traceable to an index reply that CONTRADICTS established",
              "ground truth zeroes that question's quality, however cheap the answer was. The",
              "cell's measured score is still shown beside it, because the veto is judge-driven",
              "and a human must be able to confirm it by hand. `unchecked` means the falsity pass",
              "did not run or could not rule — which is NOT the same as clean.",
              "",
              "No verdict is printed here: the owner determines the pass."]  # fmt: skip
    return lines


## @brief Build the blind-pairwise quality tally.
## @param answers Run directory.
## @return (markdown lines, unreliable pair records).
## @version 1
def _quality(answers: Path) -> tuple[list[str], list[dict]]:
    """A pair is only counted when both presentation orders agree; flips are
    listed in Reliability instead of being averaged away.

    @brief Render the quality axis.
    @return Markdown lines and the unreliable pairs.
    @version 1
    """
    pairs = [
        json.loads(p.read_text(encoding="utf-8")) for p in sorted(answers.glob("*_pairwise.json"))
    ]
    lines = ["", "## Quality — blind pairwise (both presentation orders)", "",
             "| Q | model | run1 winner | run2 winner | stable | criteria (run1/run2) |",
             "|---|---|---|---|---|---|"]  # fmt: skip
    unreliable = []
    for pair in pairs:
        overall = pair.get("overall_by_arm") or ["judge_error", "judge_error"]
        criteria = pair.get("criteria_by_arm") or {}
        detail = "; ".join(f"{k}: {v[0]}/{v[1]}" for k, v in criteria.items())
        lines.append(
            f"| {pair['q']} | {pair['model']} | {overall[0]} | {overall[1]} | "
            f"{pair.get('stable_winner') or '**UNSTABLE**'} | {detail or '-'} |"
        )
        if pair.get("position_bias") or pair.get("judge_error"):
            unreliable.append(pair)
    tally: dict[str, int] = {}
    for pair in pairs:
        if pair.get("stable_winner"):
            tally[pair["stable_winner"]] = tally.get(pair["stable_winner"], 0) + 1
    lines += ["", f"Stable wins: {tally or 'none'} "
              f"({len(pairs) - len(unreliable)}/{len(pairs)} pairs reliable)"]  # fmt: skip
    return lines, unreliable


## @brief Build the reliability section.
## @param grades Grade records.
## @param metrics Metrics rows.
## @param unreliable Unreliable pairwise records.
## @return Markdown lines.
## @version 1
def _reliability(grades: list[dict], metrics: dict[str, dict], unreliable: list[dict]) -> list[str]:
    """@brief Surface judge errors, position-bias flips and invalid runs.
    @version 1
    @return Markdown lines.
    """
    lines = ["", "## Reliability", ""]
    ## `.get` ON BOTH, because `grade_answer` writes NEITHER. These were bare subscripts, so
    ## `grade_matrix report` raised KeyError on every sidecar the current grader produces —
    ## and the only test covering the report hand-built a wider shape whose docstring claimed
    ## to be "what grade_answer writes". The fixture matched the reader, not the writer.
    errors = [
        (g, m)
        for g in grades
        for m in g["marks"] + g.get("bonus", [])
        if m["verdict"] == "JUDGE_ERROR"
    ]
    lines.append(f"- judge errors on marks: **{len(errors)}**")
    for grade, mark in errors:
        reason = (mark.get("judge") or {}).get("judge_error", "unknown")
        lines.append(f"  - {grade['answer']} {mark.get('kind', 'mark')} #{mark['index']}: {reason}")
    autofail_errors = [g for g in grades if g.get("auto_fail", {}).get("judge_error")]
    lines.append(f"- auto-fail judge errors: **{len(autofail_errors)}** "
                 f"({', '.join(g['answer'] for g in autofail_errors) or 'none'})")  # fmt: skip
    lines.append(f"- position-bias / errored pairs: **{len(unreliable)}** "
                 f"({', '.join(p['q'] for p in unreliable) or 'none'})")  # fmt: skip
    invalid = [name for name, row in metrics.items() if row.get("valid") != "True"]
    lines.append(f"- runner-invalid cells: **{len(invalid)}** ({', '.join(invalid) or 'none'})")
    lines += ["", "A mark is a mark: hit or miss, one point or none. There is no partial credit",
              "and no half point. Any item the rubric fences to one arm — MARK or bonus — is",
              "excluded from the arm that cannot reach it and listed above; the expected count",
              "is zero. Grades are advisory: every verdict has evidence in the matching",
              "`*.grade.json`."]  # fmt: skip
    return lines


## @brief The report's arm-fencing section, over MARKS as well as bonus items.
## @param grades Loaded grade sidecars.
## @return Markdown lines.
## @version 1
## @dg_internal
def _fenced_section(grades: list[dict]) -> list[str]:
    """IT READ `bonus` ONLY, WHICH IS THE SAME DEFECT `fencing_summary` WAS FIXED FOR. A run
    whose every fenced item was a MARK — the normal case; the committed rubrics fence marks and
    no bonus at all — printed "none in the graded questions" under a heading about fencing. That
    is not a missing detail: fencing decides whether a two-arm comparison is fair, and "none" is
    exactly the line someone quotes as evidence that it was.

    ZERO IS NOW THE EXPECTED ANSWER, and the wording says so. A rubric grades understanding of
    the target repository, so a mark only one arm can reach is a solo exam. A non-zero count here
    is a finding about the RUBRIC.

    @brief List every fenced mark and bonus item, or say there are none.
    @return Markdown lines.
    @version 1
    """
    lines = ["", "## Arm-fenced marks and bonus items", "",
             "Expected: NONE. A fenced item is one arm's solo exam; a non-zero count is a rubric",
             "defect, not a footnote. `arm_only` names the arm that CAN reach the item.", ""]  # fmt: skip
    before = len(lines)
    for grade in grades:
        for kind in ("marks", "bonus"):
            for mark in grade.get(kind, []):
                if mark["arm_only"]:
                    lines.append(f"- {grade['answer']} {kind[:-1]} #{mark['index']} is "
                                 f"{mark['arm_only']}-arm-only ({mark['verdict']}) — excluded from the other arm.")  # fmt: skip
    if len(lines) == before:
        lines.append("- none in the graded questions.")
    return lines


## @brief Compose the full markdown results document.
## @param answers Run directory.
## @return Markdown text.
## @version 2
def build_report(answers: Path) -> str:
    """@brief Build the three-axis results doc.
    @return Markdown text.
    @version 1
    """
    grades = _grades(answers)
    metrics = _metrics(answers)
    if not grades:
        return f"# Benchmark grading — {answers.name}\n\nNo `*.grade.json` sidecars found.\n"
    quality, unreliable = _quality(answers)
    header = [f"# Benchmark grading — {answers.name}", "",
              f"Rubric: `{grades[0]['rubric']}` (frozen; read, never rewritten).", ""]  # fmt: skip
    fenced = _fenced_section(grades)
    lines = header + _cell_table(grades, metrics) + quality + fenced
    return "\n".join(lines + _reliability(grades, metrics, unreliable)) + "\n"
