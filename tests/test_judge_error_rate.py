# SPDX-License-Identifier: MIT
"""Tests for the judge error-rate gate.

WHAT IS WORTH ASSERTING is not that it sums two integers, but the two ways a rate like this
lies: a missing sidecar counted as zero errors, which makes an ungraded grid the healthiest
one, and a rate printed without its denominator, which is the figure this project removes
rather than re-derives.

@brief Tests for scripts/judge_error_rate.py.
@version 1
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

_spec = importlib.util.spec_from_file_location(
    "judge_error_rate", REPO / "scripts" / "judge_error_rate.py"
)
assert _spec and _spec.loader
judge_error_rate = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(judge_error_rate)


## @brief Write one grade sidecar under a run layout.
## @param root Run directory.
## @param target Target name.
## @param cell Cell stem.
## @param decisions Decision dicts to record.
## @return The sidecar path.
## @version 1
def _sidecar(root: Path, target: str, cell: str, decisions: list[dict]) -> Path:
    """@brief Build a grade sidecar.
    @return Path written.
    @version 1
    """
    answers = root / target / "answers"
    answers.mkdir(parents=True, exist_ok=True)
    path = answers / f"{cell}.grade.json"
    path.write_text(json.dumps({"cell": cell, "decisions": decisions}), "utf-8")
    return path


## @brief The rate is errors over samples, with both numbers reported.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_rate_is_errors_over_samples_and_names_both(tmp_path: Path) -> None:
    """@brief Samples and errors are summed across every decision of every cell.
    @return None.
    @version 1
    """
    _sidecar(tmp_path, "a", "Q1_m_baseline_r1", [{"samples": 3, "errors": 1}])
    _sidecar(tmp_path, "b", "Q1_m_index_r1", [{"samples": 3, "errors": 0}, {"samples": 4}])
    samples, errors, cells, unreadable = judge_error_rate.tally(tmp_path)
    assert (samples, errors, cells) == (10, 1, 2)
    assert unreadable == []


## @brief An unreadable sidecar is reported, never counted as clean.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_an_unreadable_sidecar_is_not_zero_errors(tmp_path: Path) -> None:
    """ABSENCE IS NOT EMPTINESS, in the form this measure invites. A cell whose sidecar cannot
    be parsed was not graded; folding it in at zero errors would make a grid nobody graded score
    best on judge health, so it is excluded from the rate AND named.

    @brief A corrupt sidecar lands in `unreadable` and out of the denominator.
    @return None.
    @version 1
    """
    _sidecar(tmp_path, "a", "Q1_m_baseline_r1", [{"samples": 3, "errors": 3}])
    bad = tmp_path / "a" / "answers" / "Q2_m_baseline_r1.grade.json"
    bad.write_text("{not json", "utf-8")
    samples, errors, cells, unreadable = judge_error_rate.tally(tmp_path)
    assert (samples, errors, cells) == (3, 3, 1)
    assert unreadable == [bad]


## @brief A run with no sidecars refuses rather than reporting 0%.
## @param tmp_path Pytest temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @param capsys Pytest capture fixture.
## @return None.
## @version 1
def test_a_run_with_nothing_graded_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """0.00% OVER NOTHING IS THE FLATTERING READING and it would pass the gate. The refusal is
    the whole reason this is a command rather than an arithmetic note.

    @brief An ungraded run exits 2 and says why.
    @return None.
    @version 1
    """
    monkeypatch.setattr(sys, "argv", ["judge_error_rate", str(tmp_path)])
    assert judge_error_rate.main() == 2
    assert "no grade sidecars" in capsys.readouterr().err


## @brief Above the threshold the gate fails and says the figure is withheld.
## @param tmp_path Pytest temporary directory.
## @param monkeypatch Pytest monkeypatch fixture.
## @param capsys Pytest capture fixture.
## @return None.
## @version 1
def test_above_threshold_withholds_and_exits_nonzero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """@brief The publication gate has teeth.
    @return None.
    @version 1
    """
    _sidecar(tmp_path, "a", "Q1_m_baseline_r1", [{"samples": 100, "errors": 6}])
    monkeypatch.setattr(sys, "argv", ["judge_error_rate", str(tmp_path), "--threshold", "2"])
    assert judge_error_rate.main() == 1
    out = capsys.readouterr().out
    assert "6.00%" in out
    assert "withheld" in out
    ## THE DENOMINATOR IS PART OF THE CLAIM. A rate whose sample count is not printed cannot be
    ## reproduced by the reader, which is how a figure stops being evidence.
    assert "100" in out


## @brief The 1.1.0 run reproduces the published 5.1% from its own sidecars.
## @return None.
## @version 1
def test_the_published_1_1_0_rate_is_reproducible() -> None:
    """A TEST THAT CANNOT FAIL IS A LIABILITY, so this one is pinned to real committed evidence
    rather than a fixture: 152 of 2,970 samples errored across the 144 published cells. If the
    sidecars or the reader change, this fails, which is the point — the 5.1% in
    `acceptance/runs/1.2.0-pending/PRE-REGISTRATION.md` is a claim about those files.

    @brief The counter reproduces a published figure.
    @return None.
    @version 1
    """
    run = REPO / "acceptance" / "runs" / "2026-10-19-n3"
    samples, errors, cells, unreadable = judge_error_rate.tally(run)
    assert (cells, samples, errors) == (144, 2970, 152)
    assert unreadable == []
    assert round(100.0 * errors / samples, 2) == 5.12


## @brief The split rate is reported, because a cheaper judge may simply be noisier.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_split_rate_counts_only_voted_decisions(tmp_path: Path) -> None:
    """WHY THIS NUMBER, AND WHY NOW. The 1.2.0 run grades with `claude-haiku-5-5` rather than
    `claude-sonnet-4-5-20250929`, and it runs ONE pass, so there is no floor to measure whether
    the cheaper judge disagrees with itself more often. The split rate is the one indicator of
    that available from a single pass: on the Sonnet-graded 1.1.0 grid, 146 of 936 voted
    decisions — 15.6% — had the three samples disagree. A materially higher figure here means
    the instrument got noisier, and saying so costs nothing.

    THE DENOMINATOR IS VOTED DECISIONS, NOT ALL OF THEM. A single-sample decision cannot split,
    so counting it in would dilute the rate by however many marks happened to be unvoted —
    making the rate a fact about the rubric's weights rather than about the judge.

    @brief Split rate is over k>1 decisions only.
    @return None.
    @version 1
    """
    _sidecar(
        tmp_path,
        "a",
        "Q1_m_baseline_r1",
        [
            {"samples": 3, "errors": 0, "agreement": 1.0},
            {"samples": 3, "errors": 0, "agreement": 0.67},
            {"samples": 1, "errors": 0, "agreement": 1.0},
        ],
    )
    voted, split = judge_error_rate.splits(tmp_path)
    assert (voted, split) == (2, 1)


## @brief The published 1.1.0 split rate is reproducible from its sidecars.
## @return None.
## @version 1
def test_the_1_1_0_split_rate_is_reproducible() -> None:
    """PINNED TO REAL EVIDENCE so the Sonnet baseline this run is compared against is a
    measurement rather than a remembered number.

    @brief 146 of 936 voted decisions split under the Sonnet judge.
    @return None.
    @version 1
    """
    run = REPO / "acceptance" / "runs" / "2026-10-19-n3"
    voted, split = judge_error_rate.splits(run)
    assert (voted, split) == (936, 146)
