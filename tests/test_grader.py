# SPDX-License-Identifier: MIT
"""Tests for the acceptance grader's scoring arithmetic and judge blindness.

NO JUDGE CALLS. Everything here drives the pure functions — prompt construction, reply parsing,
set arithmetic, score arithmetic — because those are where a defect is silent. A wrong prompt
still returns verdicts; wrong arithmetic still returns a number.

@brief Tests for acceptance.grader.
@version 1
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance.grader import judge, score
from acceptance.grader.rubric import Mark


## @brief The judge prompt never contains the mark's evidence or the expected set.
## @return None.
## @version 1
def test_verdict_prompt_carries_only_the_mark_and_the_answer() -> None:
    """RUBRIC-BLINDNESS IS THE LOAD-BEARING PROPERTY. A judge shown the expected answer scores by
    similarity to it rather than by whether the answer states the thing, and nothing downstream
    can tell the two apart.

    @brief Verdict prompt is rubric-blind.
    @return None.
    @version 1
    """
    prompt = judge.verdict_prompt("names the gating macros", "The answer body.")
    assert "names the gating macros" in prompt
    assert "The answer body." in prompt
    for leak in ("mbedtls_config.h", "068ff080", "evidence", "programs/ssl"):
        assert leak not in prompt, f"the verdict prompt leaks {leak!r}"


## @brief The extraction prompt never names the correct set.
## @return None.
## @version 1
def test_extract_prompt_never_shows_the_expected_members() -> None:
    """Showing the set turns extraction into matching and makes precision meaningless — an
    answer could then be scored against a list it was handed.

    @brief Extraction prompt hides the answer.
    @return None.
    @version 1
    """
    prompt = judge.extract_prompt("List every file the answer names.", "It names foo.c.")
    assert "List every file the answer names." in prompt
    assert "programs/ssl/ssl_pthread_server.c" not in prompt
    ## The judge is told NOT to judge correctness, which is the opposite of being told what is
    ## correct — the word appears, the expected set does not.
    assert "NOT judging whether the answer is correct" in prompt


## @brief Arm identity is scrubbed from an answer before judging.
## @return None.
## @version 1
def test_anonymise_strips_arm_identity() -> None:
    """@brief The three leak channels are closed.
    @return None.
    @version 1
    """
    raw = "# Q1 — mcp — sonnet — run 1\nThe index arm used mcp__clew__dossier here.\n## Index gaps\nnone"
    out = judge.anonymise(raw)
    assert "sonnet" not in out
    assert "index arm" not in out.lower()
    assert "mcp__clew__dossier" not in out
    assert "dossier" in out, "the tool's identity is generalised, not deleted"


## @brief The last VERDICT line wins when a judge revises itself.
## @return None.
## @version 1
def test_read_verdict_takes_the_last_line() -> None:
    """A judge that shows a verdict and then revises it HAS revised it. Taking the first would
    score the discarded one.

    @brief Last verdict wins.
    @return None.
    @version 1
    """
    assert judge.read_verdict("VERDICT: MISS\nrethinking\nVERDICT: HIT") == "HIT"
    assert judge.read_verdict("VERDICT: MAYBE") is None
    assert judge.read_verdict("no verdict here") is None


## @brief An explicit NONE and a missing block are different outcomes.
## @return None.
## @version 1
def test_read_items_distinguishes_none_from_absent() -> None:
    """ "The answer named nothing" scores 0 recall. "The judge did not reply" scores nothing at
    all and must reach `unmarked_pct` instead. Collapsing them turns a transport failure into a
    result.

    @brief NONE is not absence.
    @return None.
    @version 1
    """
    assert judge.read_items("ITEMS:\nNONE\nEND") == ()
    assert judge.read_items("nothing at all") is None
    assert judge.read_items("ITEMS:\n- a.c\n`b.c`\nEND") == ("a.c", "b.c")


## @brief Set members compare on basename, so citation style is not graded.
## @return None.
## @version 1
def test_set_keys_ignore_path_prefix_and_case() -> None:
    """@brief Path style does not decide a mark.
    @return None.
    @version 1
    """
    assert score._key("./programs/ssl/X.c") == score._key("programs/ssl/x.c") == "x.c"
    assert score._key("`include/`") == "include"


## @brief A set mark yields one decision per member plus one for precision.
## @return None.
## @version 1
def test_set_scoring_counts_members_and_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    """PRECISION IS A DECISION. An answer that names both correct files AND a spurious one has
    full recall and loses the precision decision — which is what removes the incentive to dump
    every path in the repository once grading is known to be mechanical.

    @brief Set decisions and the precision penalty.
    @return None.
    @version 1
    """
    mark = Mark(
        text="every file with a thread-creation site",
        type="set",
        weight=2,
        extract="List them.",
        members=({"value": "programs/ssl/a.c"}, {"value": "programs/test/b.c"}),
    )
    monkeypatch.setattr(
        judge, "ask", lambda *_a, **_k: judge.Reply(text="ITEMS:\na.c\nb.c\nlibrary/z.c\nEND")
    )
    monkeypatch.setattr(score, "ask", judge.ask)
    out = score.score_set(mark, "answer", "claude-x-1")
    assert len(out) == 3, "two members plus precision"
    assert [d.hit for d in out] == [True, True, False]
    assert "library/z.c" in out[-1].detail
    assert all(d.weight == 2 for d in out)


## @brief Extraction is voted, and a minority extraction does not decide a member.
## @return None.
## @version 1
def test_extraction_is_voted_by_majority(monkeypatch: pytest.MonkeyPatch) -> None:
    """OBSERVED, NOT ANTICIPATED. Grading one answer twice extracted NONE once and `include` the
    other time, flipping two decisions and moving that cell ten points — while every VERDICT
    decision in the same cell agreed unanimously.

    A set mark of N members is N+1 decisions all resting on the extraction call, so a single
    flaky extraction moves far more weight than a single flaky verdict. Majority is the rule:
    union would inherit every hallucination, intersection would punish an answer for one flaky
    call.

    @brief Majority decides a set member.
    @return None.
    @version 1
    """
    mark = Mark(
        text="the directories",
        type="set",
        weight=1,
        extract="List them.",
        members=({"value": "include"}, {"value": "library"}),
    )
    replies = iter(
        [
            judge.Reply(text="ITEMS:\ninclude\nlibrary\nEND"),
            judge.Reply(text="ITEMS:\ninclude\nEND"),
            judge.Reply(text="ITEMS:\ninclude\nEND"),
        ]
    )
    monkeypatch.setattr(score, "ask", lambda *_a, **_k: next(replies))
    out = score.score_set(mark, "answer", "claude-x-1", samples=3)
    ## `include` in 3 of 3 survives; `library` in 1 of 3 does not.
    assert [d.hit for d in out] == [True, False, True]


## @brief An answer that names nothing does not earn the precision decision.
## @return None.
## @version 1
def test_silence_does_not_earn_precision(monkeypatch: pytest.MonkeyPatch) -> None:
    """AN EMPTY PREDICTION SET HAS NOTHING SPURIOUS IN IT, so the first version scored it clean —
    a mark satisfiable by saying nothing, which is the failure the whole design forbids.

    Found by the discrimination check, not by review: a deliberately shallow answer named zero
    directories, missed every member, and still won this decision.

    @brief Naming nothing misses precision.
    @return None.
    @version 1
    """
    mark = Mark(
        text="the directories",
        type="set",
        weight=2,
        extract="List them.",
        members=({"value": "include"}, {"value": "library"}),
    )
    monkeypatch.setattr(score, "ask", lambda *_a, **_k: judge.Reply(text="ITEMS:\nNONE\nEND"))
    out = score.score_set(mark, "an answer naming no directories", "claude-x-1")
    assert [d.hit for d in out] == [False, False, False], "no members, and no free precision"
    assert "silence" in out[-1].detail


## @brief A failed extraction leaves every set decision unruled, never missed.
## @return None.
## @version 1
def test_failed_extraction_is_unruled_not_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scoring a transport failure 0 makes it arithmetically identical to a wrong answer. That
    once converted 102 unruled marks into failures against both arms.

    @brief Extraction failure is unruled.
    @return None.
    @version 1
    """
    mark = Mark(text="m", type="set", weight=1, extract="x", members=({"value": "a.c"},))
    monkeypatch.setattr(score, "ask", lambda *_a, **_k: judge.Reply(error="rc=1"))
    out = score.score_set(mark, "answer", "claude-x-1")
    assert [d.hit for d in out] == [None, None]


## @brief Unruled decisions stay in the denominator and are reported separately.
## @return None.
## @version 1
def test_unruled_weight_lowers_the_score_and_is_disclosed() -> None:
    """Excluding unruled decisions inflates every score the moment the judge gets flaky, so they
    stay in the denominator AND `unmarked_pct` is reported beside the score. A reader can then
    see a low score caused by infrastructure rather than by the answer.

    @brief Unruled weight is visible.
    @return None.
    @version 1
    """
    result = score.QuestionResult(id="Q1")
    result.decisions = [
        score.Decision("a", "conclusion", 3, True),
        score.Decision("b", "conclusion", 3, False),
        score.Decision("c", "retrieval", 2, None),
    ]
    got, unmarked = result.score()
    assert got == pytest.approx(3 / 8)
    assert unmarked == pytest.approx(2 / 8)


## @brief Weighted scoring never exceeds 100% and never awards a fraction of a decision.
## @return None.
## @version 1
def test_weight_is_importance_not_partial_credit() -> None:
    """@brief A perfect answer scores exactly 1.0.
    @return None.
    @version 1
    """
    result = score.QuestionResult(id="Q1")
    result.decisions = [score.Decision(str(w), "conclusion", w, True) for w in (1, 2, 3)]
    got, unmarked = result.score()
    assert got == 1.0 and unmarked == 0.0


## @brief A transient failure is retried; a missing binary is not.
## @return None.
## @version 1
def test_ask_retries_transient_failures_but_not_a_missing_binary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """MEASURED: three cells came back 85-100% unruled with EVERY call failing, and the identical
    call succeeded minutes later with no code change. That is transient capacity, and it gets
    worse exactly as a grid gets bigger — when unruled marks do the most damage.

    A missing binary is the opposite case: it will not fix itself, and retrying burns the budget
    to reach the same answer three times.

    @brief Retry policy.
    @return None.
    @version 1
    """
    import subprocess as sp

    monkeypatch.setattr(judge.time, "sleep", lambda _s: None)

    calls = {"n": 0}

    def flaky(argv, **_kw):
        calls["n"] += 1
        if calls["n"] < judge.ASK_ATTEMPTS:
            return sp.CompletedProcess(argv, 1, "", "overloaded")
        return sp.CompletedProcess(argv, 0, json.dumps({"result": "QUOTE: x\nVERDICT: HIT"}), "")

    monkeypatch.setattr(sp, "run", flaky)
    reply = judge.ask("p", "claude-x-1")
    assert reply.error == "" and judge.read_verdict(reply.text) == "HIT"
    assert calls["n"] == judge.ASK_ATTEMPTS, "a transient failure must be retried"

    def missing(argv, **_kw):
        calls["n"] += 1
        raise OSError("no such file: claude")

    calls["n"] = 0
    monkeypatch.setattr(sp, "run", missing)
    assert "transport" in judge.ask("p", "claude-x-1").error
    assert calls["n"] == 1, "a missing binary must NOT be retried"


## @brief An unruled vote records WHY, not just how many failed.
## @return None.
## @version 1
def test_vote_records_the_reason_each_attempt_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "3/3 calls failed" cannot tell a reader whether the judge was rate-limited, timed out, or
    replied without a verdict block — three failures needing three different responses. Recording
    only the tally made an unruled decision uninvestigable after the fact.

    @brief Failure reasons are kept.
    @return None.
    @version 1
    """
    monkeypatch.setattr(judge, "ask", lambda *_a, **_k: judge.Reply(error="rc=1: overloaded"))
    voted = judge.vote("m", "a", "claude-x-1", 3)
    assert voted.verdict is None and voted.errors == 3
    assert voted.reasons and all("overloaded" in r for r in voted.reasons)

    ## A reply that arrives but carries no verdict block is a DIFFERENT failure and says so.
    monkeypatch.setattr(judge, "ask", lambda *_a, **_k: judge.Reply(text="I think it is fine."))
    voted = judge.vote("m", "a", "claude-x-1", 1)
    assert "no VERDICT line" in voted.reasons[0]


## @brief A split verdict is counted, so a score built on them is distinguishable.
## @return None.
## @version 1
def test_split_decisions_are_counted(monkeypatch: pytest.MonkeyPatch) -> None:
    """MEASURED. Grading five cells twice against an unchanged rubric reproduced four of them to
    the decimal and moved one by 10 points — and the entire movement was ONE weight-2 mark the
    judge splits 2:1 on. Every other verdict in that cell was unanimous.

    So run-to-run noise on this grader is not spread thinly across a cell; it is concentrated in
    the decisions where the judge disagrees with itself, and `agreement` already exposes which.
    Counting them makes a score that rests on split verdicts distinguishable from one where
    every verdict was unanimous — the same job `unmarked_pct` does for decisions never ruled on.

    SET DECISIONS ARE NOT SPLIT VERDICTS. They record agreement 0.0 with samples 0 because the
    extraction, not the verdict, was voted; counting them would report every set mark as
    unstable and drown the signal.

    @brief Split verdicts are counted, set decisions are not.
    @return None.
    @version 1
    """
    decisions = [
        score.Decision("unanimous", "conclusion", 3, True, agreement=1.0, samples=3),
        score.Decision("split", "conclusion", 2, True, agreement=0.67, samples=3),
        score.Decision("also split", "conclusion", 2, False, agreement=0.67, samples=3),
        score.Decision("single sample", "retrieval", 1, True, agreement=1.0, samples=1),
        score.Decision("a set member", "set", 2, True, agreement=0.0, samples=0),
        score.Decision("unruled", "conclusion", 3, None, agreement=0.0, samples=3, errors=3),
    ]
    result = score.QuestionResult(id="Q1", decisions=decisions)
    assert result.split_decisions() == 2, "only the two genuinely split VERDICTS count"
