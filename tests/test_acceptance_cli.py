# SPDX-License-Identifier: MIT
"""Tests for the acceptance CLI, chiefly that its phases stay separate.

@brief Tests for acceptance.__main__.
@version 1
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import __main__ as cli
from acceptance import execute

REPO = Path(__file__).resolve().parent.parent
MBEDTLS = REPO / "acceptance" / "targets" / "mbedtls" / "questions.yaml"
SELF = REPO / "acceptance" / "targets" / "self" / "questions.yaml"


## @brief Every shipped rubric loads through the CLI's loader.
## @return None.
## @version 1
@pytest.mark.parametrize("path", [MBEDTLS, SELF], ids=["mbedtls", "self"])
def test_shipped_rubrics_load(path: Path) -> None:
    """Run against the REAL rubrics, not fixtures. A validator only ever exercised on fixtures
    is tested against the detector rather than against the world.

    @brief Shipped rubrics validate.
    @return None.
    @version 1
    """
    assert cli._rubric(path) is not None


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
        return ({"stem": stem, "arm": arm, "non_index_tool_calls": shell}, {"score": score})

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
                {"stem": "Q1_sonnet_baseline_r1", "arm": "baseline", "non_index_tool_calls": -1},
                {"score": 0.5},
            ),
            (
                {"stem": "Q1_sonnet_index_r1", "arm": "index", "non_index_tool_calls": 4},
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
