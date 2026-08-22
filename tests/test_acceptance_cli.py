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
