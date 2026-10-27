# SPDX-License-Identifier: MIT
"""THE REVIEW'S RANKING STEP, PINNED — because it is the step that decides where work goes.

`acceptance/DESIGN.md` makes the post-release review a required step and names its first rule:
rank by the index-vs-baseline GAP, not by raw score, because a cluster every arm fails measures
the RUBRIC and not the tool. `scripts/cluster_review.py` is that step as a command.

WHAT THESE TESTS GUARD, in order of how much a defect would cost:

- **the gap, not the score.** A ranking by raw score puts `self` Q6 (7.9%) at the top, which is a
  question the shell arm also fails; by gap it sits tenth. A regression here sends every
  subsequent fix after the wrong clusters, and nothing downstream would notice.
- **de-duplication by mark text.** Replicates repeat every decision, so summing them counts one
  mark three times. The direction is also chosen: a mark ANY replicate hit counts as hit, since
  the pessimistic reading makes a flaky judge look like a capability gap.
- **absence is not emptiness.** A cluster with no baseline arm cannot be ranked — there is no gap
  — and must be NAMED rather than ranked at its raw score or silently dropped. A missing
  `meta.json` must yield -1, never 0: `tool_calls = -1` means unknown and must never be counted
  as none.

@brief The cluster ranking ranks by gap, de-duplicates marks, and names what it cannot rank.
@version 1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from cluster_review import cell_shape, rank  # noqa: E402


##
# @brief Write one cell's sidecars into a target's answers directory.
# @version 1
def _cell(
    adir: Path,
    stem: str,
    score: float,
    decisions: list[dict],
    *,
    calls: int | None = 5,
    chars: int = 100,
) -> None:
    adir.mkdir(parents=True, exist_ok=True)
    (adir / f"{stem}.grade.json").write_text(
        json.dumps({"cell": stem, "score": score, "decisions": decisions}), "utf-8"
    )
    (adir / f"{stem}.md").write_text("x" * chars, "utf-8")
    if calls is not None:
        (adir / f"{stem}.meta.json").write_text(json.dumps({"tool_calls": calls}), "utf-8")


##
# @brief A run with one cluster the index loses and one every arm fails.
# @version 1
def _run(tmp_path: Path) -> Path:
    """Q1 is the shape the ranking must surface: the index arm 30 points below baseline. Q2 is the
    `self` Q4 shape — both arms near zero, so a raw-score ranking puts it first and a gap ranking
    puts it last. Those two orderings are the whole test.
    """
    run = tmp_path / "run"
    adir = run / "t" / "answers"
    hit = [{"mark": "a", "weight": 2, "hit": True}]
    miss = [{"mark": "a", "weight": 2, "hit": False}]
    _cell(adir, "Q1_m_baseline_r1", 0.90, hit)
    _cell(adir, "Q1_m_index_only_r1", 0.60, miss)
    _cell(adir, "Q2_m_baseline_r1", 0.10, miss)
    _cell(adir, "Q2_m_index_only_r1", 0.05, miss)
    return run


## @brief The ranking is by gap, so a both-arms-fail cluster does not lead.
## @version 1
def test_the_ranking_is_by_gap_and_not_by_raw_score(tmp_path: Path, capsys) -> None:
    """THE RULE THE PROCEDURE OPENS WITH. Q2 scores 5% and Q1 scores 60%, so by raw score Q2
    leads; by gap Q1 leads at −30.00 against Q2's −5.00. Asserted on the printed ORDER, because
    the order is what a reviewer acts on.

    @brief Gap ordering, not score ordering.
    @return None.
    @version 1
    """
    assert rank(_run(tmp_path)) == 0
    out = capsys.readouterr().out
    first, second = (line for line in out.splitlines() if " t Q" in line)
    assert "t Q1" in first, f"the worst GAP must lead, got:\n{out}"
    assert "t Q2" in second
    assert "-30.00" in first and "-5.00" in second


## @brief A cluster with no baseline arm is named, never ranked.
## @version 1
def test_an_unpaired_cluster_is_named_rather_than_ranked(tmp_path: Path, capsys) -> None:
    """A gap needs both halves. Ranking a one-armed cluster at its raw score is exactly the
    confusion step 1 exists to prevent, and dropping it silently would make the printed cluster
    count a lie about coverage.
    """
    run = _run(tmp_path)
    _cell(run / "t" / "answers", "Q9_m_index_only_r1", 0.20, [{"mark": "z", "weight": 1}])

    assert rank(run) == 0
    out = capsys.readouterr().out
    assert "clusters: 2" in out, "an unpaired cluster must not inflate the ranked count"
    assert "unpaired" in out and "t Q9" in out, f"the unpaired cluster was not named:\n{out}"


## @brief Replicated decisions are counted once, and optimistically.
## @version 1
def test_failed_weight_de_duplicates_by_mark_text(tmp_path: Path) -> None:
    """Three replicates of one mark is one mark. The DIRECTION is asserted too: `hit` in any
    replicate means hit, because treating a single flaky miss as a failure would dress judge
    variance up as a capability gap — the thing the 8.95 pt noise floor exists to stop.
    """
    adir = tmp_path / "answers"
    decisions = [
        {"mark": "shared", "weight": 3, "hit": False},
        {"mark": "shared", "weight": 3, "hit": True},
        {"mark": "shared", "weight": 3, "hit": False},
        {"mark": "other", "weight": 2, "hit": False},
    ]
    _cell(adir, "Q1_m_index_only_r1", 0.5, decisions)

    _score, _chars, _calls, failed, total = cell_shape(adir, "Q1_m_index_only_r1")

    assert total == 5, f"one mark counted three times: total weight {total}"
    assert failed == 2, (
        f"expected only `other` to count as failed, got {failed} — a mark any replicate hit must "
        f"not read as a capability gap"
    )


## @brief An absent measurement is -1, never 0.
## @version 1
def test_a_missing_meta_yields_unknown_and_not_zero(tmp_path: Path) -> None:
    """`tool_calls = -1` means UNKNOWN and must never be counted as zero — the vocabulary rule
    stated in AGENTS.md. A cell whose meta sidecar is missing would otherwise be averaged in as a
    zero-call cell and drag a cluster's mean toward the finding this instrument is used to make.
    """
    adir = tmp_path / "answers"
    _cell(adir, "Q1_m_index_only_r1", 0.5, [{"mark": "a", "weight": 1}], calls=None)

    _score, chars, calls, _failed, _total = cell_shape(adir, "Q1_m_index_only_r1")

    assert calls == -1, f"a missing measurement must read as unknown, got {calls}"
    assert chars == 100, "the answer length is present and must still be measured"


## @brief An empty run says so rather than printing an empty table.
## @version 1
def test_a_run_with_nothing_to_pair_refuses(tmp_path: Path, capsys) -> None:
    """A table with no rows reads as "no gaps found", which is the most flattering possible
    reading of a run that could not be measured at all. The non-zero status is what makes it a
    detectable failure in a script.
    """
    run = tmp_path / "empty"
    (run / "t" / "answers").mkdir(parents=True)

    assert rank(run) == 2
    assert "no cluster" in capsys.readouterr().out
