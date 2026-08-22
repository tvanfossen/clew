# SPDX-License-Identifier: MIT
"""Tests for the acceptance CLI, chiefly that its phases stay separate.

@brief Tests for acceptance.__main__.
@version 1
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import __main__ as cli
from acceptance import execute
from acceptance.grader import score

REPO = Path(__file__).resolve().parent.parent
MBEDTLS = REPO / "acceptance" / "targets" / "mbedtls" / "questions.yaml"
SELF = REPO / "acceptance" / "targets" / "self" / "questions.yaml"

## DISCOVERED, NOT LISTED. A hand-written list of two covered mbedtls and self while entropic and
## knots shipped unvalidated — a rubric that fails to parse would have reached a matrix run with
## the suite green. `targets/*/questions.yaml` is one level deep, which structurally excludes the
## private tree (it nests a repo directory under `internal/`) without this file naming it.
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
            "sonnet",
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
            cell("Q1_sonnet_baseline_r1", "baseline", 11, 0.20),
            cell("Q1_sonnet_index_r1", "index", 5, 0.75),
            cell("Q2_sonnet_baseline_r1", "baseline", 10, 0.667),
            cell("Q2_sonnet_index_r1", "index", 13, 0.667),
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
                    "stem": "Q1_sonnet_baseline_r1",
                    "arm": "baseline",
                    "tool_calls": -1,
                    "non_index_tool_calls": -1,
                },
                {"score": 0.5},
            ),
            (
                {
                    "stem": "Q1_sonnet_index_r1",
                    "arm": "index",
                    "tool_calls": 6,
                    "non_index_tool_calls": 4,
                },
                {"score": 0.5},
            ),
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
            cell("Q1_sonnet_baseline_r1", "baseline", 9, 9, 0.833),
            cell("Q1_sonnet_index_r1", "index", 6, 6, 0.667),
            cell("Q2_sonnet_baseline_r1", "baseline", 9, 9, 0.50),
            cell("Q2_sonnet_index_r1", "index", 8, 5, 0.90),
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
