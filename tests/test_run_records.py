# SPDX-License-Identifier: MIT
"""A run's published record names the judge its grades were actually made with.

FOUND BY THE 2.0.0 RUBRIC CROSS-CHECK (2026-11-17): every grade of 1.3.0-final, 1.4.0-pending and
1.4.0-final records `judge_model: claude-sonnet-5-5` (the deliberate switch of 844fee55, disclosed
in the 1.2.0 pre-registration), while those runs' RESULTS.md said `claude-sonnet-4-5-20250929` —
text carried over from an earlier run. The figures are what the grades measured; the label was
wrong, and nothing checked it.

@brief Tests that a run's records agree with the grades and the tree they describe.
@version 2
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

_RUNS = Path(__file__).resolve().parent.parent / "acceptance" / "runs"


def _graded_runs() -> list[Path]:
    """@brief Run directories with a RESULTS.md and at least one grade. @return Paths."""
    return sorted(
        run
        for run in _RUNS.iterdir()
        if (run / "RESULTS.md").is_file() and any(run.glob("*/answers/*.grade.json"))
    )


@pytest.mark.parametrize("run", _graded_runs(), ids=lambda p: p.name)
def test_results_name_every_judge_the_grades_recorded(run: Path) -> None:
    """@brief Each judge model a run's grades record appears in its RESULTS.md."""
    judges = {
        json.loads(g.read_text(encoding="utf-8")).get("judge_model", "")
        for g in run.glob("*/answers/*.grade.json")
    }
    text = (run / "RESULTS.md").read_text(encoding="utf-8")
    missing = sorted(j for j in judges if j and j not in text)
    assert not missing, f"{run.name}/RESULTS.md never names judge(s) {missing} its grades record"


## THE 2.0.0 RECORD IS WRITTEN BEFORE ITS GRID, so what it pins must agree with the tree the grid
## will run: a pre-registration naming a grader, judge, replicate count or rubric version the
## harness will not actually use is a promise the run cannot keep, and nothing else would notice.
_PREREG_2_0_0 = _RUNS / "2.0.0" / "PRE-REGISTRATION.md"
_RUN_COMMAND_2_0_0 = _RUNS / "2.0.0" / "RUN-COMMAND.md"
_TARGETS_2_0_0 = ("mattermost", "mbedtls", "self", "entropic")


## @brief The 2.0.0 pre-registration pins what the grid will actually run.
## @return None.
## @version 1
def test_the_2_0_0_preregistration_pins_what_the_grid_runs() -> None:
    """Owner ruling 2026-11-17: a full fresh run, 5 replicates, standalone (no 1.4.0 comparator),
    grader `c10cf554ae6d` (then `1ac344ae8cf3`, a comment-only re-tag, 2026-11-19), judge
    `claude-sonnet-5-5`. Each is read from the tree, not restated:
    the fingerprint from the grader, the judge and version from each rubric, the replicate
    count from every command in RUN-COMMAND.md.

    @brief The pre-registration agrees with the grader, the rubrics and the run command.
    """
    import re

    import yaml

    from acceptance.grader import score

    text = _PREREG_2_0_0.read_text(encoding="utf-8")
    commands = _RUN_COMMAND_2_0_0.read_text(encoding="utf-8")
    assert f"`{score.grader_fingerprint()}`" in text
    for target in _TARGETS_2_0_0:
        rubric = yaml.safe_load(
            (_RUNS.parent / "targets" / target / "questions.yaml").read_text(encoding="utf-8")
        )
        assert f"`{rubric['judge']['model']}`" in text, target
        ## SPEC CHANGED (2.1, self rubric 7.0.0, owner Q/A 2026-11-25): the version the grid RAN
        ## is the one its own grade records carry, not whatever the tree holds today. Reading the
        ## tree held only until a rubric moved on after the grid; the property is unchanged.
        graded = {
            json.loads(g.read_text(encoding="utf-8"))["rubric_version"]
            for g in (_RUNS / "2.0.0" / target / "answers").glob("*.grade.json")
        }
        assert len(graded) == 1, (target, graded)
        assert f"{target} {graded.pop()}" in text, f"{target} rubric version not pinned"
    replicates = re.findall(r"--replicates (\d+)", commands)
    assert replicates and set(replicates) == {"5"}, replicates
    assert "Replicates **5**" in text
    assert "1.4.0-final" not in commands, "the 2.0.0 run stands alone; no 1.4.0 comparator"
