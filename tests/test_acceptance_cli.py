# SPDX-License-Identifier: MIT
"""Tests for the acceptance CLI, chiefly that its phases stay separate.

@brief Tests for acceptance.__main__.
@version 1
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import __main__ as cli
from acceptance import execute
from acceptance import runner
from acceptance.grader import rubric as _rubric_mod
from acceptance.grader import score

REPO = Path(__file__).resolve().parent.parent
MBEDTLS = REPO / "acceptance" / "targets" / "mbedtls" / "questions.yaml"
SELF = REPO / "acceptance" / "targets" / "self" / "questions.yaml"

## DISCOVERED, NOT LISTED. A hand-written list of two covered mbedtls and self while entropic and
## knots shipped unvalidated — a rubric that fails to parse would have reached a matrix run with
## the suite green. `targets/*/questions.yaml` is one level deep, which structurally excludes the
## private tree (it nests a repo directory under `internal/`) without this file naming it.
## THE ARMS UNDER TEST, DERIVED. Naming them literally is how the summary itself went blind:
## it kept comparing a pair the run no longer runs, and every test agreed with it.
##
## AND THE ARITY IS DERIVED TOO, which the first version was not — `_A, _B = runner.ARMS` broke
## the whole module at import the moment a third arm joined. `_A` is the REFERENCE arm; `_REST`
## is every arm measured against it.
_A, *_REST = runner.ARMS
_B = _REST[0]

SHIPPED = sorted(
    p
    for p in (REPO / "acceptance" / "targets").glob("*/questions.yaml")
    if p.parent.name != "internal"
)


## @brief Every shipped rubric loads through the CLI's loader.
## @return None.
## @version 1
@pytest.mark.parametrize("path", SHIPPED, ids=lambda p: p.parent.name)
def test_shipped_rubrics_load(path: Path) -> None:
    """Run against the REAL rubrics, not fixtures. A validator only ever exercised on fixtures
    is tested against the detector rather than against the world.

    @brief Shipped rubrics validate.
    @return None.
    @version 2
    """
    assert cli._rubric(path) is not None


## @brief Discovery finds every shipped target, so adding one cannot skip validation.
## @return None.
## @version 1
def test_rubric_discovery_is_not_empty_and_covers_the_known_targets() -> None:
    """THE GUARD ON THE GUARD. A glob that matches nothing parametrizes to zero cases and reports
    PASSED, which is indistinguishable from validating everything. Naming the two targets that
    were previously hardcoded also proves the replacement did not narrow what is covered.

    @brief Discovery is non-vacuous.
    @return None.
    @version 1
    """
    assert len(SHIPPED) >= 4, f"only found {[p.parent.name for p in SHIPPED]}"
    assert MBEDTLS in SHIPPED and SELF in SHIPPED


## @brief The digest a sidecar records names the rubric its marks came from.
## @return None.
## @version 2
def test_grade_stamps_the_digest_of_the_rubric_it_actually_graded_against(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OBSERVED, by editing a rubric while a grade run was in flight. `grade` re-read the rubric
    file inside its per-cell loop to stamp each sidecar, while the marks came from a parse done
    once at startup. Grading takes minutes per cell, so a mid-run edit produced sidecars whose
    recorded digest named a file that was NOT the file their marks came from — provenance that
    reads as exact and is wrong, which is worse than none.

    DRIVEN THROUGH cmd_grade, NOT through load. The first version of this test asserted that
    `Rubric.digest` does not change after the file changes — which a frozen string satisfies
    however the digest was computed, so it stayed green with the defect restored. A mutation
    control caught that; the assertion had to move to the place that stamps.

    @brief The stamped digest names the graded rubric.
    @return None.
    @version 2
    """
    rubric_path = tmp_path / "questions.yaml"
    rubric_path.write_bytes(MBEDTLS.read_bytes())
    at_load = hashlib.sha256(rubric_path.read_bytes()).hexdigest()[:16]

    answers = tmp_path / "answers"
    answers.mkdir()
    for stem in ("Q1_sonnet_baseline_r1", "Q2_sonnet_baseline_r1"):
        (answers / f"{stem}.md").write_text("an answer", encoding="utf-8")

    ## THE EDIT LANDS BETWEEN CELLS — the real-world shape, since the rubric sits in a working
    ## tree someone is still editing while the run takes minutes per cell.
    def edit_then_score(question, answer, rubric, arm):
        rubric_path.write_text(
            rubric_path.read_text(encoding="utf-8") + "\n# edited mid-run\n", encoding="utf-8"
        )
        return score.QuestionResult(
            id=question.id,
            decisions=[score.Decision(mark="m", kind="conclusion", weight=1, hit=True)],
        )

    monkeypatch.setattr(cli, "score_question", edit_then_score)
    assert cli.cmd_grade(argparse.Namespace(rubric=rubric_path, answers=answers)) == 0

    sidecars = sorted(answers.glob("*.grade.json"))
    assert len(sidecars) == 2, "the run graded nothing, so it proves nothing"
    assert hashlib.sha256(rubric_path.read_bytes()).hexdigest()[:16] != at_load, (
        "the fixture never edited the rubric, so there was no drift to detect"
    )
    stamped = {json.loads(p.read_text(encoding="utf-8"))["rubric_digest"] for p in sidecars}
    assert stamped == {at_load}, (
        f"sidecars recorded {stamped} but the marks came from {at_load}: the digest was "
        f"re-read from disk instead of taken from the parse"
    )


## @brief A file that is not a rubric is refused, not half-parsed.
## @return None.
## @version 1
def test_a_non_rubric_is_refused(capsys: pytest.CaptureFixture) -> None:
    """A rubric that half-parses grades a run and publishes a number.

    @brief Non-rubric refuses.
    @return None.
    @version 1
    """
    assert cli._rubric(REPO / "README.md") is None
    assert "REFUSED" in capsys.readouterr().err


## @brief Grading never executes a cell.
## @return None.
## @version 1
def test_grade_does_not_generate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """THE PHASE SEPARATION IS THE POINT. The judge must be arm-blind, and grading inline puts
    the grader in the same process as the thing that knows the arm. Coupling them also means a
    scorer fix costs a regeneration, which is how a previous set of grids ended up spanning two
    scorer versions.

    Asserted by making cell execution EXPLODE: if `grade` ever reaches it, this fails loudly
    rather than quietly costing a run.

    @brief Grade runs no cells.
    @return None.
    @version 1
    """

    def explode(*_a, **_k):
        raise AssertionError("grade must never execute a cell")

    monkeypatch.setattr(execute, "run_cell", explode)
    monkeypatch.setattr(cli, "run_cell", explode)
    monkeypatch.setattr(cli, "score_question", lambda *_a, **_k: _StubResult())
    (tmp_path / "Q1_sonnet_baseline_r1.md").write_text("an answer", "utf-8")
    args = cli.argparse.Namespace(rubric=MBEDTLS, answers=tmp_path)
    assert cli.cmd_grade(args) == 0
    sidecar = json.loads((tmp_path / "Q1_sonnet_baseline_r1.grade.json").read_text())
    assert sidecar["arm"] == "baseline"
    assert "unmarked_pct" in sidecar, "coverage rides beside every score"
    assert sidecar["judge_model"].count("-") >= 2, "the sidecar records a dated judge id"


## @brief A stand-in scored result.
## @version 1
class _StubResult:
    """@brief Minimal QuestionResult stand-in.
    @version 1
    """

    decisions: list = []

    ## @brief No split verdicts in a stub.
    ## @return Zero.
    ## @version 1
    def split_decisions(self) -> int:
        """@brief Stub split count.
        @return 0.
        @version 1
        """
        return 0

    ## @brief Fixed score.
    ## @return (score, unmarked).
    ## @version 1
    def score(self) -> tuple[float, float]:
        """@brief Fixed score.
        @return (score, unmarked).
        @version 1
        """
        return 0.5, 0.0


## @brief Grading an empty directory fails rather than reporting a clean run.
## @return None.
## @version 1
def test_grading_nothing_is_an_error(tmp_path: Path) -> None:
    """A grade pass over zero answers that exits 0 is indistinguishable from one that graded
    everything successfully — which is how a vacuous pass gets read as a result.

    @brief Empty grade run fails.
    @return None.
    @version 1
    """
    assert cli.cmd_grade(cli.argparse.Namespace(rubric=MBEDTLS, answers=tmp_path)) == 1


## @brief The CLI is reachable as a module and its subcommands are wired.
## @return None.
## @version 1
def test_cli_module_runs() -> None:
    """@brief `python -m acceptance plan` works end to end.
    @return None.
    @version 1
    """
    done = subprocess.run(
        [
            sys.executable,
            "-m",
            "acceptance",
            "plan",
            "--rubric",
            str(MBEDTLS),
            "--models",
            ## FIXTURE, NOT BEHAVIOUR: `plan` now refuses an alias, so the example
            ## is a real pinned id. What the test asserts is unchanged.
            "claude-sonnet-4-5-20250929",
        ],
        capture_output=True,
        text=True,
        cwd=str(REPO),
        check=False,
    )
    assert done.returncode == 0, done.stderr
    assert "Mbed-TLS/mbedtls" in done.stdout
    assert "digest" in done.stdout, "a run names the exact rubric text that produced it"


## @brief The paired summary reports separation, ties and shell displacement.
## @return None.
## @version 1
def test_paired_summary_reports_ties_and_displacement(capsys: pytest.CaptureFixture) -> None:
    """TWO THINGS THE PER-CELL TABLE CANNOT SHOW.

    A tie contributes nothing to the comparison however good its marks are, and a tie at the
    CEILING means the question is saturated — measured at n=1, three of four questions tied and
    one of those was 100%/100%. The discrimination fixtures cannot see that, because a shallow
    answer and a complete one both score high there.

    Displacement answers "what is the index actually doing" when the index arm still spends most
    of its calls on the shell. A NEGATIVE displacement is a real result, not a glitch.

    @brief Paired summary output.
    @return None.
    @version 1
    """

    def cell(stem, arm, shell, score):
        return (
            {"stem": stem, "arm": arm, "tool_calls": shell, "non_index_tool_calls": shell},
            {"score": score},
        )

    cli._paired_summary(
        [
            cell(f"Q1_sonnet_{_A}_r1", _A, 11, 0.20),
            *[cell(f"Q1_sonnet_{a}_r1", a, 5, 0.75) for a in _REST],
            cell(f"Q2_sonnet_{_A}_r1", _A, 10, 0.667),
            *[cell(f"Q2_sonnet_{a}_r1", a, 13, 0.667) for a in _REST],
        ]
    )
    out = capsys.readouterr().out
    assert "+55.0pt" in out
    assert "TIED" in out
    assert "+6" in out, "displacement where the index saved shell calls"
    assert "-3" in out, "a NEGATIVE displacement must be shown, not hidden"
    assert "saturated" in out


## @brief An unknown tool count never becomes a displacement number.
## @return None.
## @version 1
def test_unknown_tool_counts_produce_no_displacement(capsys: pytest.CaptureFixture) -> None:
    """-1 means the transcript could not be read. Arithmetic on it would invent a number, and an
    invented number on the axis under test is worse than an absent one.

    @brief Unknown counts yield no displacement.
    @return None.
    @version 1
    """
    cli._paired_summary(
        [
            (
                {
                    "stem": f"Q1_sonnet_{_A}_r1",
                    "arm": _A,
                    "tool_calls": -1,
                    "non_index_tool_calls": -1,
                },
                {"score": 0.5},
            ),
            *[
                (
                    {
                        "stem": f"Q1_sonnet_{a}_r1",
                        "arm": a,
                        "tool_calls": 6,
                        "non_index_tool_calls": 4,
                    },
                    {"score": 0.5},
                )
                for a in _REST
            ],
        ]
    )
    ## ASSERT ON THE DISPLACEMENT COLUMN, not on the presence of an em-dash anywhere. The first
    ## version checked `"—" in out` and passed with the guard REMOVED, because the tie message
    ## below the table contains one. A mutation control caught it; reading the test did not.
    line = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("Q1_"))
    assert line.split()[-1] == "—", line
    assert "-5" not in line, "an unknown count must not be turned into arithmetic"


## @brief A cell that never touched the index is flagged in the separation row.
## @return None.
## @version 1
def test_zero_index_cell_is_flagged_in_the_separation_table(capsys: pytest.CaptureFixture) -> None:
    """A CELL THAT NEVER TOUCHED THE INDEX IS NOT A RESULT ABOUT THE INDEX.

    Measured: one cell scored 16.7 points BELOW its baseline while making zero index calls. Read
    from the separation table alone that is a quality loss for the tool. It is the adoption
    holdout — the arm answered from source and the index was never consulted.

    The generate-time warning names it, but a reader of the report has no reason to go looking
    for that, so the row carries the flag itself.

    @brief Zero-index cells are marked in the row.
    @return None.
    @version 1
    """

    def cell(stem, arm, total, shell, score):
        return (
            {"stem": stem, "arm": arm, "tool_calls": total, "non_index_tool_calls": shell},
            {"score": score},
        )

    cli._paired_summary(
        [
            cell(f"Q1_sonnet_{_A}_r1", _A, 9, 9, 0.833),
            *[cell(f"Q1_sonnet_{a}_r1", a, 6, 6, 0.667) for a in _REST],
            cell(f"Q2_sonnet_{_A}_r1", _A, 9, 9, 0.50),
            *[cell(f"Q2_sonnet_{a}_r1", a, 8, 5, 0.90) for a in _REST],
        ]
    )
    lines = {x.split()[0]: x for x in capsys.readouterr().out.splitlines() if x.startswith("Q")}
    assert "NO INDEX CALLS" in lines["Q1_sonnet_r1"], "a loss with no index calls must be marked"
    assert "NO INDEX CALLS" not in lines["Q2_sonnet_r1"], (
        "a cell that used the index is not flagged"
    )


## @brief The cross-rubric audit passes on the shipped set.
## @return None.
## @version 1
def test_shipped_rubrics_pass_the_cross_rubric_audit() -> None:
    """THE LOADER VALIDATES ONE RUBRIC; THESE ARE PROPERTIES OF THE SET. It caught a five-member
    set mark carrying 56% of its question's weight — one mark deciding the majority of a
    question, which the per-rubric validator has no way to see because nothing about that mark
    is malformed.

    Run through the module rather than the shell so a failure names the offending mark here
    instead of in a subprocess's stdout.

    @brief The audit is clean.
    @return None.
    @version 1
    """
    import scripts.rubric_audit as audit

    assert audit.TARGETS, "the audit found no rubrics, so a pass proves nothing"
    assert audit.main() == 0


## @brief Build one cell's (meta, grade) pair for the summary.
## @return The pair.
## @version 1
def _cell(stem: str, arm: str, score: float, *, shell: int = 4, tools: int = 6) -> tuple:
    """@brief A minimal reported cell.
    @return (meta, grade).
    @version 1
    """
    meta = {
        "stem": stem,
        "arm": arm,
        "non_index_tool_calls": shell,
        "tool_calls": tools,
    }
    return meta, {"score": score, "unmarked_pct": 0.0}


## @brief The paired summary pairs the arms the run actually used.
## @return None.
## @version 1
def test_paired_summary_uses_the_configured_arms(capsys: pytest.CaptureFixture) -> None:
    """THE SAME DEFECT `check_symmetry` ALREADY HAD, one file over. The summary named its two
    arms literally, so once 1.1.0 moved to baseline vs index_only every pair failed the
    membership test and the whole block printed "No arm PAIRS in this run" — on a grid where
    every cell was in fact paired.

    Silent and total: the per-cell table still prints, so a reader sees a full run with the
    separation and displacement analysis simply missing, which reads like a run that was not
    paired rather than a reporter that could not see the pairing.

    @brief Summary derives its arms from ARMS.
    @return None.
    @version 1
    """
    ## EVERY ARM, DERIVED — including the arity. This built exactly two rows, so it would have
    ## reported "no complete arm set" the moment a third arm joined, which is the same blindness
    ## it was written to catch.
    rows = [_cell(f"Q1_sonnet_{runner.ARMS[0]}_r1", runner.ARMS[0], 0.40, shell=9)]
    rows += [_cell(f"Q1_sonnet_{a}_r1", a, 0.70, shell=1) for a in runner.ARMS[1:]]
    cli._paired_summary(rows)
    out = capsys.readouterr().out
    assert "No complete arm SETS" not in out, "the configured arms were not recognised"
    assert "+30.0pt" in out, "separation must be computed against the reference arm"
    assert "+8" in out, "shell displacement must be computed"
    ## ONE ROW PER COMPARISON ARM, so a third arm is reported rather than silently folded in.
    body = [x for x in out.splitlines() if x.startswith("Q1_")]
    assert len(body) == len(runner.ARMS) - 1, body


## @brief Separation is reported beside the question's citation spread.
## @return None.
## @version 1
def test_separation_table_carries_files_cited(capsys: pytest.CaptureFixture) -> None:
    """THE AXIS THE GRID EXISTS TO TEST, per the owner: multi-file questions are where the index
    should excel over a source harness. That is a PREDICTION, and a prediction is only testable
    if the two numbers appear together — separation on one axis, files-cited on the other.

    Reported and never ruled on. The harness prints the pair; whether the correlation holds is
    the owner's call on the finished grid, and no threshold here decides it.

    @brief Files-cited rides beside separation.
    @return None.
    @version 1
    """
    rows = [
        _cell(f"Q1_sonnet_{_A}_r1", _A, 0.40),
        *[_cell(f"Q1_sonnet_{a}_r1", a, 0.70) for a in _REST],
        _cell(f"Q2_sonnet_{_A}_r1", _A, 0.80),
        *[_cell(f"Q2_sonnet_{a}_r1", a, 0.80) for a in _REST],
    ]
    cli._paired_summary(rows, files_cited={"Q1": 6, "Q2": 1})
    out = capsys.readouterr().out
    q1 = next(x for x in out.splitlines() if x.startswith("Q1_"))
    q2 = next(x for x in out.splitlines() if x.startswith("Q2_"))
    assert " 6 " in f" {q1} ", f"Q1 must report 6 files cited: {q1}"
    assert " 1 " in f" {q2} ", f"Q2 must report 1 file cited: {q2}"
    assert "files" in out, "the column must be labelled"


## @brief Without a rubric the spread column degrades rather than inventing a number.
## @return None.
## @version 1
def test_separation_table_without_a_rubric_shows_no_spread(
    capsys: pytest.CaptureFixture,
) -> None:
    """`report` can be run against an answers directory alone, and a zero there would read as
    "this question cites nothing" — a claim about the rubric made by a caller that never opened
    one. The same rule as the -1 tool counts: an unknown is printed as unknown.

    @brief Absent spread prints as unknown.
    @return None.
    @version 1
    """
    rows = [
        _cell(f"Q1_sonnet_{_A}_r1", _A, 0.40),
        *[_cell(f"Q1_sonnet_{a}_r1", a, 0.70) for a in _REST],
    ]
    cli._paired_summary(rows)
    line = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("Q1_"))
    assert " 0 " not in f" {line} ", f"an unknown spread must not print as zero: {line}"


## @brief A question with cells but no complete arm pair is named, not silently dropped.
## @return None.
## @version 1
def test_unpaired_questions_are_named(capsys: pytest.CaptureFixture) -> None:
    """MEASURED ON THE LIVE RUN. mbedtls Q2 had a baseline cell and a blended-arm cell but no
    index_only cell, so it simply did not appear in the separation table — and the table gives
    no sign that a question is missing from it. A reader comparing five questions sees four rows
    and no reason to look for the fifth.

    Silent truncation reading as complete coverage is this project's recurring shape. The count
    of unpaired questions is printed with their names.

    @brief Unpaired questions are reported.
    @return None.
    @version 1
    """
    rows = [
        _cell(f"Q1_sonnet_{_A}_r1", _A, 0.40),
        *[_cell(f"Q1_sonnet_{a}_r1", a, 0.70) for a in _REST],
        _cell(f"Q2_sonnet_{_A}_r1", _A, 0.80),
    ]
    cli._paired_summary(rows)
    out = capsys.readouterr().out
    tail = out.split("shell displaced")[-1]
    assert "Q2" in tail, (
        f"the question with no complete pair must be NAMED, not just counted: {tail}"
    )
    assert "absent from the table" in tail, "and the reader must be told it is missing from it"
    assert "Q1" not in tail.split("absent from the table above:")[-1], (
        "a question that DID pair must not be listed as missing"
    )


## @brief The sidecar records how many verdicts were split, and the report shows it.
## @return None.
## @version 1
def test_split_count_reaches_the_sidecar_and_the_table(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A SCORE ALONE CANNOT SAY HOW STABLE IT IS. Measured: two grading passes over an unchanged
    rubric reproduced four cells exactly and moved a fifth by 10 points, entirely from one mark
    the judge splits 2:1 on. Without this column the two kinds of cell look identical, and a
    reader averaging them cannot tell which numbers to trust.

    Reported, never ruled on — no threshold here rejects a cell for being split.

    @brief Split verdicts are recorded and displayed.
    @return None.
    @version 1
    """
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / f"Q1_sonnet_{_A}_r1.md").write_text("an answer", encoding="utf-8")

    def scored(question, answer, rubric, arm):
        return score.QuestionResult(
            id=question.id,
            decisions=[
                score.Decision("firm", "conclusion", 3, True, agreement=1.0, samples=3),
                score.Decision("split", "conclusion", 2, True, agreement=0.67, samples=3),
            ],
        )

    monkeypatch.setattr(cli, "score_question", scored)
    assert cli.cmd_grade(argparse.Namespace(rubric=MBEDTLS, answers=answers)) == 0
    sidecar = json.loads((answers / f"Q1_sonnet_{_A}_r1.grade.json").read_text())
    assert sidecar["split_decisions"] == 1, "the sidecar must carry the count"
    capsys.readouterr()

    rows = [
        (
            {
                "stem": f"Q1_sonnet_{_A}_r1",
                "arm": _A,
                "seconds": 1.0,
                "output_tokens": 1,
                "cache_read_tokens": 1,
                "result_bytes": 1,
                "turns": 1,
                "tool_calls": 1,
                "non_index_tool_calls": 1,
                "denied_tool_calls": 0,
            },
            sidecar,
        )
    ]
    cli._print_cells(rows)
    line = next(x for x in capsys.readouterr().out.splitlines() if x.startswith("Q1_"))
    assert line.split()[-1] == "1", f"the split count must be the last column: {line}"


## @brief The ref-existence check fails on a rubric citing a file that is not at the pin.
## @return None.
## @version 1
def test_audit_ref_check_fails_on_a_missing_file(tmp_path: Path) -> None:
    """THE GUARD ON THE GUARD, and a mutation control is what demanded it. The audit had one
    test — that the shipped rubrics pass — and disabling the ref check entirely ALSO makes them
    pass, so nothing distinguished "every ref is real" from "nobody looked".

    That is the shape this project keeps shipping: a check with a test for the clean case and
    none for the case it exists to catch.

    @brief The ref check refuses a phantom file.
    @return None.
    @version 1
    """
    import scripts.rubric_audit as audit

    checkout = tmp_path / "repo"
    (checkout / "src").mkdir(parents=True)
    (checkout / "src" / "real.c").write_text("int main(void){return 0;}\n", encoding="utf-8")

    rubric = cli._rubric(MBEDTLS)
    assert rubric is not None
    marks = (
        _rubric_mod.Mark(
            text="cites a real file", type="conclusion", weight=1, refs=(("src/real.c", 1),)
        ),
        _rubric_mod.Mark(
            text="cites a phantom", type="conclusion", weight=1, refs=(("src/gone.c", 1),)
        ),
    )
    question = _rubric_mod.Question(id="Q9", intent="i", prompt="p", marks=marks)
    stub = dataclasses.replace(rubric, questions=(question,))

    found = audit._missing_refs(stub, checkout, "fixture")
    assert len(found) == 1, f"exactly the phantom must be reported, got {found}"
    assert "src/gone.c" in found[0] and "src/real.c" not in found[0]

    ## AND IT MUST STAY QUIET when every ref resolves — a check that fires on a clean rubric is
    ## worse than none, because the noise trains a reader to skip it.
    clean = dataclasses.replace(stub, questions=(dataclasses.replace(question, marks=marks[:1]),))
    assert audit._missing_refs(clean, checkout, "fixture") == []


## @brief Every grading pass is retained, not just the latest.
## @return None.
## @version 1
def test_grading_appends_a_pass_history(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """MEASURED, AND THE MEASUREMENT ATE ITS OWN EVIDENCE. Regrading five cells against an
    unchanged rubric moved one by -12.1 points, and which marks flipped is now unrecoverable —
    the second pass overwrote the first. A variance figure needs BOTH passes; grading kept one.

    `<stem>.grade.json` still holds the latest pass, so every existing consumer is unchanged.
    The history rides beside it as one JSON object per line, appended, so a regrade adds
    evidence instead of replacing it and the cost is a few kilobytes per cell.

    DECISIONS ARE KEPT IN THE HISTORY, not just the score. "The cell moved 12 points" is the
    question; "these two marks flipped" is the answer, and only the decisions carry it.

    @brief Grading appends rather than replacing.
    @return None.
    @version 1
    """
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / f"Q1_sonnet_{_A}_r1.md").write_text("an answer", encoding="utf-8")

    scores = iter([True, False])

    def scored(question, answer, rubric, arm):
        return score.QuestionResult(
            id=question.id,
            decisions=[
                score.Decision("m", "conclusion", 2, next(scores), agreement=1.0, samples=3)
            ],
        )

    monkeypatch.setattr(cli, "score_question", scored)
    args = argparse.Namespace(rubric=MBEDTLS, answers=answers)
    assert cli.cmd_grade(args) == 0
    assert cli.cmd_grade(args) == 0

    latest = json.loads((answers / f"Q1_sonnet_{_A}_r1.grade.json").read_text())
    assert latest["score"] == 0.0, "the sidecar holds the LATEST pass"

    history = (answers / f"Q1_sonnet_{_A}_r1.grades.jsonl").read_text().splitlines()
    assert len(history) == 2, f"both passes must be retained, got {len(history)}"
    passes = [json.loads(line) for line in history]
    assert [p["score"] for p in passes] == [1.0, 0.0], "in the order they were graded"
    assert passes[0]["decisions"][0]["hit"] is True, "a pass keeps its DECISIONS, not just a score"
    assert passes[1]["decisions"][0]["hit"] is False
    assert all(p["rubric_digest"] == latest["rubric_digest"] for p in passes), (
        "each pass records the rubric it graded against, or a drift cannot be told from noise"
    )


## @brief With more than one grading pass, the report shows the spread and what flipped.
## @return None.
## @version 1
def test_report_shows_grading_variance_and_the_marks_that_flipped(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """ "THE CELL MOVED 12 POINTS" IS THE QUESTION; "THESE MARKS FLIPPED" IS THE ANSWER. Retaining
    passes is worth nothing if nothing reads them, and a spread alone still leaves a reader
    unable to tell judge noise from a rubric that changed underneath.

    ONLY PASSES GRADED AGAINST THE SAME RUBRIC ARE COMPARED. A digest change between passes is a
    different question being answered, and indexing that as variance would report an intentional
    rubric edit as instability.

    @brief Variance and flips are reported.
    @return None.
    @version 1
    """
    answers = tmp_path / "answers"
    answers.mkdir()

    def a_pass(score_value, steady_hit, moved_hit, digest="abc123"):
        return {
            "cell": "Q1_sonnet_baseline_r1",
            "arm": "baseline",
            "rubric_digest": digest,
            "score": score_value,
            "unmarked_pct": 0.0,
            "split_decisions": 0,
            "decisions": [
                {
                    "mark": "steady mark",
                    "hit": steady_hit,
                    "weight": 3,
                    "agreement": 1.0,
                    "samples": 3,
                    "kind": "conclusion",
                    "detail": "",
                    "errors": 0,
                },
                {
                    "mark": "the one that moved",
                    "hit": moved_hit,
                    "weight": 2,
                    "agreement": 1.0,
                    "samples": 3,
                    "kind": "conclusion",
                    "detail": "",
                    "errors": 0,
                },
            ],
        }

    ## THE SUPERSEDED PASS COMES FIRST, which is the real shape: a rubric is corrected and
    ## regraded, so the stale digest is the OLD one. The newest digest decides what is
    ## comparable, so this pass is excluded and the two after it are the measurement.
    lines = [
        a_pass(0.2, False, False, digest="SUPERSEDED"),
        a_pass(1.0, True, True),
        a_pass(0.6, True, False),
    ]
    (answers / "Q1_sonnet_baseline_r1.grades.jsonl").write_text(
        "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8"
    )

    cli._print_variance(answers)
    out = capsys.readouterr().out
    assert "Q1_sonnet_baseline_r1" in out
    assert "40.0" in out, "the spread between the two comparable passes must be shown"
    assert "the one that moved" in out, "the mark that flipped must be NAMED"
    assert "steady mark" not in out, "a mark that never moved is noise in this table"
    ## ASSERT ON THE COLUMN, not on a phrase. The count says how much evidence the spread rests
    ## on — a 40pt spread over two passes and over twenty are different claims — and reading the
    ## row proves the number is there rather than that some wording happens to appear.
    row = next(x for x in out.splitlines() if x.startswith("Q1_sonnet_baseline_r1"))
    assert row.split()[1] == "2", f"the passes column must show 2, got: {row}"


## @brief A single grading pass produces no variance block at all.
## @return None.
## @version 1
def test_report_shows_no_variance_block_for_one_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """A spread computed from one pass is zero, and printing zero would assert the grader is
    perfectly stable on the strength of never having checked.

    @brief One pass yields no variance claim.
    @return None.
    @version 1
    """
    answers = tmp_path / "answers"
    answers.mkdir()
    (answers / "Q1_sonnet_baseline_r1.grades.jsonl").write_text(
        json.dumps(
            {"cell": "Q1_sonnet_baseline_r1", "rubric_digest": "d", "score": 0.5, "decisions": []}
        )
        + "\n",
        encoding="utf-8",
    )
    cli._print_variance(answers)
    assert capsys.readouterr().out.strip() == "", "one pass is not a variance measurement"


## @brief Spread is summarised per arm, so arm-dependent noise is visible rather than averaged.
## @return None.
## @version 1
def test_variance_summarises_spread_per_arm(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    """OBSERVED AND NOT YET ESTABLISHED, which is exactly why the number is printed rather than
    ruled on. Three grading passes over five frozen mbedtls cells left both BASELINE cells at a
    spread of 0.0pt while all three index-arm cells moved 10-15pt. n=3 on five cells cannot tell
    that from chance.

    It matters because of what it would mean if it holds: arm-dependent grader noise is a BIAS,
    not a floor. A single shared error bar would understate one arm's uncertainty and overstate
    the other's, and "the index wins by X" would need its own interval rather than a common one.

    So the summary reports mean spread per arm and says nothing about which is larger. If the
    arms are equally stable it prints that just as plainly.

    @brief Per-arm spread is reported.
    @return None.
    @version 1
    """
    answers = tmp_path / "answers"
    answers.mkdir()

    def write(cell, arm, scores):
        lines = [
            {
                "cell": cell,
                "arm": arm,
                "rubric_digest": "d",
                "score": s,
                "unmarked_pct": 0.0,
                "split_decisions": 0,
                "decisions": [],
            }
            for s in scores
        ]
        (answers / f"{cell}.grades.jsonl").write_text(
            "".join(json.dumps(x) + "\n" for x in lines), encoding="utf-8"
        )

    write("Q1_sonnet_baseline_r1", "baseline", [0.20, 0.20, 0.20])
    write("Q2_sonnet_baseline_r1", "baseline", [0.90, 0.90, 0.90])
    write("Q1_sonnet_index_only_r1", "index_only", [0.60, 0.60, 0.75])

    cli._print_variance(answers)
    out = capsys.readouterr().out
    summary = out.split("mean spread by arm:")[-1].splitlines()[0]
    assert "baseline 0.0pt" in summary, f"a perfectly stable arm must read 0.0: {summary}"
    assert "index_only 15.0pt" in summary, f"the moving arm's mean must be shown: {summary}"
    assert "2 cell" in summary and "1 cell" in summary, (
        "the cell count must ride with each mean, or a one-cell arm reads as a measurement"
    )


## @brief Passes graded by a different grader version are excluded from variance.
## @return None.
## @version 1
def test_variance_excludes_passes_from_another_grader_version(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """THE DEFECT THIS SESSION'S OWN MEASUREMENT WALKED INTO. Two grades of the same frozen
    answers spread -12.1pt to +15.0pt and it was reported as judge noise. It was not: the judge
    RETRY landed between them, so marks previously left unruled started being ruled and the
    scores moved because the GRADER had changed. Two passes under one grader version then
    reproduced every cell exactly.

    A pass already excluded a differing rubric digest for exactly this reason. The grader
    deserved the same treatment and had none, so a code change could be measured and published
    as a property of the judge.

    @brief Grader drift is not variance.
    @return None.
    @version 1
    """
    answers = tmp_path / "answers"
    answers.mkdir()

    def line(sc, grader):
        return json.dumps(
            {
                "cell": "Q1_sonnet_baseline_r1",
                "arm": "baseline",
                "rubric_digest": "same",
                "grader_fingerprint": grader,
                "score": sc,
                "unmarked_pct": 0.0,
                "split_decisions": 0,
                "decisions": [],
            }
        )

    ## An old grader scored this cell far lower. Under one grader it never moves.
    (answers / "Q1_sonnet_baseline_r1.grades.jsonl").write_text(
        "\n".join([line(0.20, "OLD"), line(0.80, "NEW"), line(0.80, "NEW")]) + "\n",
        encoding="utf-8",
    )
    cli._print_variance(answers)
    out = capsys.readouterr().out
    row = next(x for x in out.splitlines() if x.startswith("Q1_sonnet_baseline_r1"))
    assert row.split()[1] == "2", f"only the two same-grader passes are comparable: {row}"
    assert "0.0pt" in row, f"and under one grader this cell did not move: {row}"
    assert "60.0" not in row, "the 60pt gap across grader versions must NOT be reported as noise"


## @brief Passes excluded by drift are reported, not silently dropped.
## @return None.
## @version 1
def test_variance_says_when_passes_were_excluded_by_drift(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    """THE GUARD IS CONSERVATIVE ON PURPOSE AND THAT MAKES IT LOUD BY NECESSITY. The grader
    fingerprint digests every source file in the grader package, so ANY edit invalidates
    comparability — including one that cannot move a score. A false "incomparable" is safe and a
    false "comparable" publishes a code change as judge noise, so the strictness is the right
    trade.

    But it means a run of passes spanning an ordinary edit yields NO variance row, and a reader
    seeing no row concludes there was no variance rather than that their passes were never
    comparable. That is the silent-truncation failure this project keeps re-learning: an absent
    answer reading as a clean one.

    So the exclusion is stated with its cause and its count.

    @brief Excluded passes are named.
    @return None.
    @version 1
    """
    answers = tmp_path / "answers"
    answers.mkdir()

    def line(sc, grader="G1", digest="R1"):
        return json.dumps(
            {
                "cell": "Q1_sonnet_baseline_r1",
                "arm": "baseline",
                "rubric_digest": digest,
                "grader_fingerprint": grader,
                "score": sc,
                "unmarked_pct": 0.0,
                "split_decisions": 0,
                "decisions": [],
            }
        )

    ## Three passes, each under a different grader — nothing is comparable with anything.
    (answers / "Q1_sonnet_baseline_r1.grades.jsonl").write_text(
        "\n".join([line(0.2, "G1"), line(0.5, "G2"), line(0.8, "G3")]) + "\n", encoding="utf-8"
    )
    cli._print_variance(answers)
    out = capsys.readouterr().out
    assert "Q1_sonnet_baseline_r1" in out, "the cell must be named, not omitted in silence"
    assert "grader" in out.lower(), "and the reason must be the grader, not left to inference"
    assert "3 pass" in out, "with how many passes were set aside"
    assert "spread" not in out.split("Q1_sonnet_baseline_r1")[0].lower(), (
        "no variance table should be printed when nothing is comparable"
    )


## @brief A cell the judge never ruled on is not reported as a score.
## @return None.
## @version 1
def test_separation_hides_scores_the_judge_never_ruled(capsys: pytest.CaptureFixture) -> None:
    """MEASURED ON THE WEEKEND GRID. Six entropic Q3 cells came back with unmarked_pct 1.0 — the
    judge ruled on NOTHING, every call failing with rc=1 — and the separation table printed
    "0.0% 0.0% +0.0pt TIED" for all three replicates. A transport failure rendered as a
    substantive finding about both arms, in the one table a reader draws conclusions from.

    The answers were excellent. One traced the whole authorisation pipeline with file:line
    references. Nothing about them earned a zero.

    This is the design's own rule — an unruled decision is NOT a miss — enforced where it
    actually matters. A cell whose weight is mostly unruled has no score to compare, so it shows
    the unmarked share instead and is never called a tie.

    @brief Unruled cells report as unruled.
    @return None.
    @version 1
    """

    def cell(stem, arm, score_value, unmarked):
        return (
            {"stem": stem, "arm": arm, "tool_calls": 6, "non_index_tool_calls": 3},
            {"score": score_value, "unmarked_pct": unmarked, "split_decisions": 0},
        )

    rows = [
        cell(f"Q3_sonnet_{_A}_r1", _A, 0.0, 1.0),
        *[cell(f"Q3_sonnet_{a}_r1", a, 0.0, 1.0) for a in _REST],
        cell(f"Q4_sonnet_{_A}_r1", _A, 0.80, 0.0),
        *[cell(f"Q4_sonnet_{a}_r1", a, 0.60, 0.0) for a in _REST],
    ]
    cli._paired_summary(rows)
    out = capsys.readouterr().out
    q3 = next(x for x in out.splitlines() if x.startswith("Q3_"))
    q4 = next(x for x in out.splitlines() if x.startswith("Q4_"))
    assert "TIED" not in q3, f"an unruled cell must never be called a tie: {q3}"
    assert "0.0%" not in q3, f"and must not publish a score it does not have: {q3}"
    assert "unruled" in q3.lower(), f"it must say what happened instead: {q3}"
    ## THE CONTROL: a genuinely graded pair still reports its separation, or this fix would have
    ## blanked the table it exists to protect.
    assert "-20.0pt" in q4, f"a fully ruled pair still separates: {q4}"


## @brief Resuming skips the cells that already produced an answer.
## @return None.
## @version 1
def test_resume_does_not_respend_a_cell_that_already_has_an_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """GENERATION IS THE PHASE THAT CANNOT BE RE-RUN CHEAPLY, and it had no way to resume: the
    loop walks the whole plan unconditionally and a failed cell writes no `.md` and is passed
    over. A capacity window inside a serial grid therefore loses those cells permanently, and
    re-running spends every completed cell again to reach them.

    OPT-IN, SO THE DEFAULT CONTRACT IS UNCHANGED. Without `--resume` a second `generate` still
    re-spends everything, which is what every past measurement assumed. With it, the frozen
    `.md` is treated as the record it already is.

    THE PRESENCE OF `.md` IS THE RIGHT TEST because `run_cell` writes it LAST and only on
    success — a transport failure leaves `.meta.json` and `.raw.json` but no answer, so a cell
    that errored is correctly retried rather than skipped.

    @brief --resume skips answered cells.
    @return None.
    @version 1
    """
    from acceptance.runner import plan as plan_cells

    rubric = _rubric_mod.load(MBEDTLS)
    ## FIXTURE, NOT BEHAVIOUR: the stems the frozen answers are written under must use the
    ## same model id `cmd_generate` is given, and `--models` now refuses an alias.
    cells = plan_cells(rubric, ("claude-sonnet-4-5-20250929",), 1, 7)
    done = {cells[0].stem(), cells[3].stem()}
    answers = tmp_path / "answers"
    answers.mkdir()
    for stem in done:
        (answers / f"{stem}.md").write_text("an answer from an earlier window", "utf-8")

    ran: list[str] = []

    def record(cell, *_a, **_k):
        ran.append(cell.stem())
        return execute.CellResult(cell.stem(), cell.arm, cell.model, True, tool_calls=1)

    monkeypatch.setattr(cli, "run_cell", record)
    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    args = cli.argparse.Namespace(
        rubric=MBEDTLS,
        ## FIXTURE, NOT BEHAVIOUR. This said `m` (resp. `sonnet`) until `--models` began
        ## refusing an alias. What this test guards is unchanged; only the example string
        ## had to become a real pinned id to reach the code under test.
        models=["claude-sonnet-4-5-20250929"],
        replicates=1,
        seed=7,
        repo=tmp_path / "repo",
        out=answers,
        mcp_config=None,
        timeout=60,
        resume=True,
    )
    assert cli.cmd_generate(args) == 0
    assert done.isdisjoint(ran), "a cell with a frozen answer was spent again"
    assert len(ran) == len(cells) - len(done)
    ## THE RUN RECORD SAYS SO. A grid assembled over several windows must not read as one pass.
    assert json.loads((answers / "run.json").read_text())["resumed"] == sorted(done)


## @brief Grading several answers at once produces exactly what grading them in turn produces.
## @return None.
## @version 1
def test_jobs_grades_concurrently_and_changes_no_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WHY GRADING MAY PARALLELISE WHEN GENERATION MAY NOT: a cell's wall-clock is a reported
    axis and a judge call's is reported nowhere. A full grid is ~3,400 judge calls per pass and
    the noise floor needs two passes, so serial grading is most of the run's wall-clock while
    contributing nothing a reader will ever quote.

    THE BARRIER IS THE ASSERTION. Counting elapsed time would make this a timing test on shared
    CI; a barrier that all four answers must reach before any proceeds either happens or times
    out, and it times out on a serial implementation.

    AND THE OUTPUT MUST NOT MOVE. `grader_fingerprint` hashes only `acceptance/grader/`, which
    this change does not touch, so a parallel pass stays comparable to a serial one — but the
    sidecars are compared byte for byte rather than assumed.

    @brief --jobs is concurrent and output-identical.
    @return None.
    @version 1
    """
    import threading

    rubric = _rubric_mod.load(MBEDTLS)
    qid = rubric.questions[0].id
    stems = [f"{qid}_m_baseline_r{i}" for i in range(1, 5)]

    def _run(folder: Path, jobs: int, gate: threading.Barrier | None) -> None:
        folder.mkdir()
        for stem in stems:
            (folder / f"{stem}.md").write_text(f"an answer for {stem}", "utf-8")

        def scored(*_a, **_k):
            if gate is not None:
                gate.wait()
            return _StubResult()

        monkeypatch.setattr(cli, "score_question", scored)
        args = cli.argparse.Namespace(rubric=MBEDTLS, answers=folder, jobs=jobs)
        assert cli.cmd_grade(args) == 0

    ## FOUR ANSWERS, FOUR SLOTS, ONE BARRIER. On a serial grader the first call blocks forever
    ## and `Barrier` raises rather than hanging the suite.
    _run(tmp_path / "parallel", 4, threading.Barrier(4, timeout=10))
    _run(tmp_path / "serial", 1, None)

    for stem in stems:
        wide = json.loads((tmp_path / "parallel" / f"{stem}.grade.json").read_text())
        thin = json.loads((tmp_path / "serial" / f"{stem}.grade.json").read_text())
        assert wide == thin, f"{stem} graded differently under --jobs"
        assert wide["grader_fingerprint"] == thin["grader_fingerprint"]


## @brief Generating a subset of arms spends only those arms, and the record says so.
## @param tmp_path Per-test temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @return None.
## @version 1
def test_arms_can_be_narrowed_and_the_record_says_which(tmp_path: Path, monkeypatch) -> None:
    """A PROBE THAT ONLY NEEDS THE INDEX ARMS MUST NOT PAY FOR THE BASELINE. The baseline arm
    makes no index calls at all, so for a measurement about index-call waste its cells are pure
    spend. Without this flag the choices were to buy them anyway or to plant fake answer files so
    `--resume` would skip them — and a fake answer makes the run record lie, which is worse than
    the cost.

    THE RECORD MUST NAME THE SUBSET. A directory holding only two arms is indistinguishable from
    a three-arm run that lost a third of its cells, unless the window says which arms were asked
    for. Absent when every arm ran, so "all arms" and "nobody recorded" do not read alike.

    @brief --arms narrows generation and is recorded.
    @return None.
    @version 1
    """
    ran: list[str] = []
    monkeypatch.setattr(cli, "check_revision", lambda *_a, **_k: None)
    monkeypatch.setattr(
        cli,
        "run_cell",
        lambda cell, *_a, **_k: (
            ran.append(cell.arm),
            execute.CellResult(cell.stem(), cell.arm, cell.model, True),
        )[1],
    )
    answers = tmp_path / "answers"
    args = cli.argparse.Namespace(
        rubric=MBEDTLS,
        models=["claude-haiku-5-5"],
        replicates=1,
        seed=7,
        repo=tmp_path / "repo",
        out=answers,
        mcp_config=None,
        timeout=60,
        resume=False,
        arms=["index_only", "index"],
    )

    assert cli.cmd_generate(args) == 0
    assert set(ran) == {"index_only", "index"}, f"arms outside the request were spent: {set(ran)}"
    assert "baseline" not in ran, "the baseline arm was generated despite being excluded"

    window = json.loads((answers / "run.json").read_text())["windows"][-1]
    assert window["arms"] == ["index", "index_only"], (
        f"the window record does not name the arms that were asked for: {window}"
    )


## @brief An unknown arm name must be refused by name rather than silently dropped.
## @param tmp_path Per-test temporary directory.
## @return None.
## @version 1
def test_an_unknown_arm_is_refused_by_name(tmp_path: Path) -> None:
    """REFUSED BY NAME, like every other declaration in this project. A typo'd arm that silently
    matched nothing would generate zero cells and report success — a run directory with no answers
    and a green exit code, which reads as "the grid is cheap" rather than "the filter was wrong".

    @brief An unknown arm is refused.
    @return None.
    @version 1
    """
    args = cli.argparse.Namespace(
        rubric=MBEDTLS,
        models=["claude-haiku-5-5"],
        replicates=1,
        seed=7,
        repo=tmp_path / "repo",
        out=tmp_path / "answers",
        mcp_config=None,
        timeout=60,
        resume=False,
        arms=["index_onlyy"],
    )

    assert cli.cmd_generate(args) == 1, "a misspelled arm was accepted"


## @brief A question nothing was ruled on prints as unruled, not as a crash.
## @return None.
## @version 1
def test_grade_line_handles_an_unruled_question() -> None:
    """FOUND BY THE 1.2.0 RUN, 90 cells in. `QuestionResult.score()` returns `float | None` by
    design — None means NOTHING WAS RULED, which is the fix that stopped an unruled question
    scoring a confident 0.0. The progress line was never taught about it and formatted the value
    with `:6.1%`, so the first fully-unruled cell killed the whole grading phase with
    `TypeError: unsupported format string passed to NoneType.__format__`.

    THE SIDECAR IS WRITTEN BEFORE THE LINE IS FORMATTED, so no score was lost or changed — this
    is a reporting crash, not a scoring one, and it lives outside `acceptance/grader/` so
    `grader_fingerprint()` does not move.

    IT MUST NOT PRINT 0.0%. That is the exact confusion the None was introduced to end: a reader
    scanning the log for weak cells would see a zero and treat an unmeasured question as a
    failed one.

    @brief An unruled score formats as UNRULED.
    @return None.
    @version 1
    """
    line = cli._grade_line("Q6_claude-haiku-5-5_index_r1", None, 1.0)
    assert "score UNRULED" in line
    ## ANCHORED TO THE SCORE FIELD, not a bare substring: `unmarked 100.0%` CONTAINS "0.0%", so
    ## the obvious assertion passes on correct output and fails on nothing. A test that cannot
    ## fail for the reason it names is the liability this repository keeps finding.
    assert "score   0.0%" not in line
    assert "Q6_claude-haiku-5-5_index_r1" in line
    assert "unmarked 100.0%" in line


## @brief A ruled question still prints its score as a percentage.
## @return None.
## @version 1
def test_grade_line_still_prints_a_real_score() -> None:
    """@brief The ordinary path is unchanged.
    @return None.
    @version 1
    """
    line = cli._grade_line("Q1_claude-haiku-5-5_baseline_r1", 0.6875, 0.0)
    assert "68.8%" in line
    assert "UNRULED" not in line
