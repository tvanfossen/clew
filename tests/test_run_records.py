# SPDX-License-Identifier: MIT
"""A run's published record names the judge its grades were actually made with.

FOUND BY THE 2.0.0 RUBRIC CROSS-CHECK (2026-11-17): every grade of 1.3.0-final, 1.4.0-pending and
1.4.0-final records `judge_model: claude-sonnet-5-5` (the deliberate switch of 844fee55, disclosed
in the 1.2.0 pre-registration), while those runs' RESULTS.md said `claude-sonnet-4-5-20250929` —
text carried over from an earlier run. The figures are what the grades measured; the label was
wrong, and nothing checked it.

@brief Tests that RESULTS.md agrees with the grades it reports.
@version 1
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
