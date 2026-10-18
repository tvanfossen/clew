# SPDX-License-Identifier: MIT
"""How the judge spends its patience, and when it refuses to spend any.

Measured on the first published grid: 12.2% of one target's decisions came back unruled, every
one of them a call that failed INSTANTLY — `duration_api_ms: 0`, zero tokens, no cost. The
retry policy slept 60, then 120, then 180 seconds against each of them, so six minutes went to
waiting on a failure that took no time to happen, and eighteen minutes to each k=3 mark. That
backoff, not the judging, was most of a 3.9-hour grade pass.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance.grader import judge


## @brief Build a fake completed process.
## @version 1
class _Done:
    """@brief Stand-in for subprocess.CompletedProcess.
    @version 1
    """

    def __init__(self, rc: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode = rc
        self.stdout = stdout
        self.stderr = stderr


## @brief A capacity refusal stops the pass instead of burning the budget on it.
## @return None.
## @version 1
def test_a_capacity_refusal_is_raised_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    """NO AMOUNT OF BACKOFF FIXES A USAGE LIMIT, and pretending otherwise converts an operator
    problem with an obvious remedy — wait, then regrade — into silent holes in the measurement.

    An unruled decision is supposed to mean the judge could not decide. A usage limit means
    nobody asked it. Those must not land in the same bucket, because the first is a property of
    the answer and the second is a property of the afternoon.

    `provision.py` already separates these two for its index probe and tells the operator to
    re-run the identical command. The judge now does the same.

    @brief Capacity refusals abort.
    @return None.
    @version 1
    """
    slept: list[float] = []
    monkeypatch.setattr(judge.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *_a, **_k: _Done(1, stdout="Claude usage limit reached. Try again later."),
    )
    with pytest.raises(judge.JudgeCapacityError) as caught:
        judge.ask("does the answer demonstrate X?", "claude-sonnet-4-5-20250929")
    assert "usage limit" in str(caught.value).lower()
    assert not slept, "a usage limit must not be waited out one minute at a time"


## @brief A failure that took no API time is retried quickly, not slept on for a minute.
## @return None.
## @version 1
def test_an_instant_failure_backs_off_briefly(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE BACKOFF EXISTS FOR A SERVER SAYING "SLOW DOWN". A call that failed in zero
    milliseconds never reached the server, so a minute of waiting buys nothing — and at k=3
    across thousands of decisions it buys nothing thousands of times.

    @brief Instant failures retry fast.
    @return None.
    @version 1
    """
    slept: list[float] = []
    monkeypatch.setattr(judge.time, "sleep", lambda s: slept.append(s))
    envelope = json.dumps({"duration_api_ms": 0, "usage": {"input_tokens": 0}})
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Done(1, stdout=envelope))

    reply = judge.ask("does the answer demonstrate X?", "claude-sonnet-4-5-20250929")

    assert reply.error, "an exhausted retry is still an error"
    assert slept, "it must still retry"
    ## THE WHOLE RETRY BUDGET, not one interval — the backoff multiplies by attempt, so the
    ## claim worth making is that exhausting the retries on a call that never reached the
    ## server costs seconds rather than the six minutes it used to.
    assert sum(slept) < judge.ASK_BACKOFF_SECONDS, (
        f"a zero-duration failure cost {sum(slept)}s of waiting across its retries"
    )


## @brief A real server-side failure keeps the long backoff.
## @return None.
## @version 1
def test_a_slow_failure_keeps_the_long_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    """The fast path must not swallow the case the backoff was written for: a call that reached
    the server, took real time, and failed. That one is worth waiting on.

    @brief Slow failures back off slowly.
    @return None.
    @version 1
    """
    slept: list[float] = []
    monkeypatch.setattr(judge.time, "sleep", lambda s: slept.append(s))
    envelope = json.dumps({"duration_api_ms": 4200, "usage": {"input_tokens": 10}})
    monkeypatch.setattr(subprocess, "run", lambda *_a, **_k: _Done(1, stdout=envelope))

    judge.ask("does the answer demonstrate X?", "claude-sonnet-4-5-20250929")

    assert max(slept) >= judge.ASK_BACKOFF_SECONDS, "a real failure must still be backed off"


## @brief A capacity abort ends the pass with a usable message, not a traceback.
## @return None.
## @version 1
def test_grade_reports_a_capacity_abort_and_keeps_what_it_graded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE OPERATOR HAS TO KNOW WHICH KIND OF FAILURE THIS WAS. A traceback out of a worker
    thread reads as a defect in the harness; the actual situation is "wait and run the same
    command again", and the pass already written is still good because grading is additive.

    Exit code is non-zero, because a pass that stopped early must not be mistaken for one that
    graded everything.

    @brief Capacity aborts are reported.
    @return None.
    @version 1
    """
    from acceptance import __main__ as cli
    from acceptance.grader import judge as judge_mod

    rubric = Path(__file__).resolve().parent.parent / "acceptance/targets/mbedtls/questions.yaml"
    import yaml

    qid = yaml.safe_load(rubric.read_text())["questions"][0]["id"]
    (tmp_path / f"{qid}_m_baseline_r1.md").write_text("an answer", "utf-8")

    def boom(*_a, **_k):
        raise judge_mod.JudgeCapacityError("Claude usage limit reached. Try again later.")

    monkeypatch.setattr(cli, "score_question", boom)
    args = cli.argparse.Namespace(rubric=rubric, answers=tmp_path, jobs=1)
    assert cli.cmd_grade(args) != 0, "a pass that stopped early is not a successful pass"
