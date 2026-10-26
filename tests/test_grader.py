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
import pathlib
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


## @brief The grader fingerprints its own source, so passes under different code are separable.
## @return None.
## @version 1
def test_grader_fingerprint_tracks_its_own_source(tmp_path: pathlib.Path) -> None:
    """FOUND BY USING THE THING I HAD JUST BUILT. Two grades of the same answers spread -12.1pt
    to +15.0pt and I read that as judge noise — twice, in two different shapes. It was neither.
    The judge RETRY landed between those grades, so marks that had been unruled started being
    ruled, and the scores moved because the GRADER changed underneath them.

    Two consecutive passes under one grader version then reproduced all five cells exactly.

    A pass records `rubric_digest` already, because comparing across rubrics is meaningless. The
    same argument applies to the grader and nothing recorded it, so a variance figure could
    silently be measuring a code change. This is that stamp.

    DERIVED FROM SOURCE, NEVER HAND-MAINTAINED. A constant someone must remember to bump is a
    constant that will be forgotten in exactly the commit that matters — and the commit that
    matters here is the one that changes how a mark is decided.

    @brief Grader identity moves with its code.
    @return None.
    @version 1
    """
    before = score.grader_fingerprint()
    assert before and before == score.grader_fingerprint(), "a fingerprint must be stable"
    assert len(before) == score.FINGERPRINT_CHARS

    ## A CHANGE ANYWHERE IN THE GRADER MOVES IT. score.py decides weighting, judge.py decides
    ## what the judge is asked and how replies are read, rubric.py decides what a mark IS —
    ## a change in any of the three can move a score, so all three are in the digest.
    pkg = tmp_path / "grader"
    pkg.mkdir()
    (pkg / "score.py").write_text("a = 1\n", encoding="utf-8")
    (pkg / "judge.py").write_text("b = 2\n", encoding="utf-8")
    first = score.grader_fingerprint(pkg)
    (pkg / "judge.py").write_text("b = 3\n", encoding="utf-8")
    assert score.grader_fingerprint(pkg) != first, "a judge change must move the fingerprint"

    ## AND BYTECODE MUST NOT. `__pycache__` is regenerated by importing the very code being
    ## identified, so hashing it would make the fingerprint change because it was read.
    stable = score.grader_fingerprint(pkg)
    cache = pkg / "__pycache__"
    cache.mkdir()
    (cache / "judge.cpython-312.pyc").write_bytes(b"\x00\x01\x02")
    assert score.grader_fingerprint(pkg) == stable, "bytecode must not move the fingerprint"


## @brief A failure's reason is kept even when the tool writes it to stdout.
## @return None.
## @version 1
def test_ask_records_stdout_when_stderr_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """MEASURED ON THE WEEKEND GRID. Seven cells recorded `rc=1 after 3 attempt(s):` with nothing
    after the colon — the CLI had put its explanation on STDOUT and only the empty stderr was
    kept. A reason that says only "it failed" is exactly the bare tally this field was added to
    replace, so the omission silently undid that fix.

    @brief The reason is recorded wherever the tool wrote it.
    @return None.
    @version 1
    """
    import subprocess as sp

    monkeypatch.setattr(judge.time, "sleep", lambda _s: None)
    ## NOT AN ACCOUNT-LIMIT STRING. This used "You've hit your session limit", which is now
    ## detected and RAISED rather than recorded — the detection reads stdout too, so the
    ## stdout-is-read property this test exists for is still exercised, just by
    ## `tests/test_judge_retry.py` for that phrase. Here the fixture is an ordinary failure, so
    ## this keeps testing the thing it was written for: a reason on stdout must survive.
    monkeypatch.setattr(
        sp,
        "run",
        lambda argv, **_k: sp.CompletedProcess(argv, 1, "model stream ended unexpectedly", ""),
    )
    error = judge.ask("p", "claude-x-1").error
    assert "stream ended unexpectedly" in error, f"the reason must survive: {error!r}"

    ## STDERR STILL WINS when both are present — it is the channel a failure belongs on, and
    ## preferring stdout would bury a real diagnostic under ordinary output.
    monkeypatch.setattr(
        sp, "run", lambda argv, **_k: sp.CompletedProcess(argv, 1, "chatter", "the real cause")
    )
    assert "the real cause" in judge.ask("p", "claude-x-1").error


## @brief Retry backoff spans minutes, because the failure it must survive lasts minutes.
## @return None.
## @version 1
def test_retry_backoff_covers_a_rate_limit_not_a_blip() -> None:
    """CALIBRATED FROM ARITHMETIC, NOT FROM A GUESS ABOUT ONE FAILURE. Three attempts at four
    seconds of linear backoff cover twelve seconds in total. A capacity refusal is measured in
    MINUTES — this account hit one that named a reset time hours away — so the retry was sized
    for a network blip and could not ride out the thing that actually happens.

    Measured consequence on the weekend grid: seven of twenty graded cells came back
    majority-unruled, each having exhausted all three attempts.

    WHAT IS NOT CLAIMED: that this was the cause of those specific failures. Their reason was
    discarded by a separate defect (only stderr was recorded, and the CLI writes to stdout), so
    it is unrecoverable. This is sized for the failure mode that is documented to exist, and the
    next occurrence will record its own reason.

    @brief Backoff is minutes-scale.
    @return None.
    @version 1
    """
    total = sum(judge.ASK_BACKOFF_SECONDS * i for i in range(judge.ASK_ATTEMPTS))
    assert total >= 120, (
        f"total backoff is {total}s; a capacity refusal outlasts that, so every attempt burns "
        f"into the same refusal and the cell is lost"
    )
    ## AND IT MUST STILL TERMINATE. An unbounded retry hangs a 90-cell grade on one bad cell.
    assert total <= 900, f"total backoff {total}s would stall a grid on a single cell"


## @brief The judge does not wait on inherited stdin.
## @return None.
## @version 1
def test_ask_closes_stdin(monkeypatch: pytest.MonkeyPatch) -> None:
    """MEASURED, AND NOT A CORRECTNESS FIX. The CLI warns "no stdin data received in 3s,
    proceeding without it" when stdin is inherited and idle, and the same call measured 8.9s with
    stdin closed against 3.4s from /dev/null. Both SUCCEED — stdin was tested as a suspect for
    the rc=1 failures and cleared.

    It is a cost fix. The grid makes roughly 2,244 judge calls, so a few seconds of waiting each
    is on the order of two hours of a grade spent waiting for input that never comes.

    @brief stdin is explicitly closed.
    @return None.
    @version 1
    """
    import subprocess as sp

    seen = {}

    def capture(argv, **kw):
        seen.update(kw)
        return sp.CompletedProcess(argv, 0, json.dumps({"result": "VERDICT: HIT"}), "")

    monkeypatch.setattr(sp, "run", capture)
    judge.ask("p", "claude-x-1")
    assert seen.get("stdin") is sp.DEVNULL, "the judge must not wait on inherited stdin"


##
# @brief The grader fingerprint must stay at the value the published runs recorded.
# @return None.
# @version 1
def test_grader_fingerprint_is_the_value_published_runs_recorded() -> None:
    """**A PUBLISHED RUN CAN ONLY BE RE-GRADED AT ITS OWN KEYS, AND 1.1.1 BROKE THAT BY ACCIDENT.**
    `grader_fingerprint()` hashes every `*.py` in this directory, so an edit anywhere here moves
    it — and a release that refactored input validation in `rubric.py` moved it from
    `9cc2b15baf93` to `18f7cfdb541c`. Nothing noticed: no preflight compares a run's recorded
    fingerprint to the current one, `--skip-graded` treats a mismatch as a reason to grade rather
    than to refuse, and `.grade.json` is then overwritten unconditionally. The 144 frozen cells of
    `acceptance/runs/2026-10-19-n3/` stamped `9cc2b15baf93` and silently stopped being
    re-gradable.

    **THIS PIN IS DELIBERATELY BRITTLE, AND THAT IS THE WHOLE POINT.** Any change under
    `acceptance/grader/` fails this test. That is not friction to route around — it is the one
    moment someone has to decide, consciously, that the new scoring behaviour is worth making an
    already-published run un-re-gradable. When that decision is genuinely taken, update the
    constant here and record in the affected run's `RESULTS.md` that it can no longer be
    re-graded at its own keys.

    **WHAT IT DOES NOT PIN.** Not behaviour — `test_grader_fingerprint_tracks_its_own_source`
    covers the mechanism. This pins one number against one published artifact.

    @brief The fingerprint matches the published runs.
    @return None.
    @version 1
    """
    ## MOVED DELIBERATELY ON 2026-10-26, from `9cc2b15baf93`, to add the verdict cache to
    ## `judge.ask`. The cache is the fix for an instrument that gave a different reading each time
    ## it was used: the `claude` CLI exposes no temperature, seed or top_p, so re-grading the same
    ## answers moved the score by a mean absolute 8.95 pt. Caching verdicts by prompt and model
    ## makes a re-grade exact and free; the alternative, calling the API directly to pin
    ## temperature, would have moved ~3.1M judge input tokens per pass onto metered billing and
    ## still left residual nondeterminism.
    ##
    ## CONSEQUENCE, RECORDED HERE AND IN THE RUN'S OWN RESULTS.md: the 144 cells of
    ## acceptance/runs/2026-10-19-n3 were graded at `9cc2b15baf93` and can no longer be re-graded
    ## at their own keys from this tree. They remain re-gradable from the tagged tree that
    ## produced them, which is why the constant below is a record and not just a guard.
    ## MOVED AGAIN, 2026-10-26, from `274b0d72688b`. Three defects were fixed in one pass after
    ## an Opus audit of four graded cells, and all three change recorded scores:
    ##   - `_key` did not strip a trailing `:LINE`, so an answer citing `file.cpp:796` could
    ##     never match the member `file.cpp`. Deterministic, and DIFFERENTIAL — it punished
    ##     whichever arm cited line numbers, which is the style a code index encourages. One cell
    ##     named 4 of 7 members correctly and scored 0 of 8 set decisions: 18.5 points.
    ##   - `score_set` now REFUSES when extraction matched no member at all, rather than scoring
    ##     a confident zero. That is the signature of a key mismatch, and the harness had already
    ##     published one while printing four member paths as "not in the set".
    ##   - the judge's own `QUOTE:`/`WHY:` are recorded. They were requested by the prompt and
    ##     discarded, leaving 11 of 26 audited failures with no stated reason to dispute.
    published = "0e7ad2bdb67d"

    assert score.grader_fingerprint() == published, (
        f"grader_fingerprint() is {score.grader_fingerprint()!r}, but every graded cell under "
        f"acceptance/runs/2026-10-19-n3/ recorded {published!r}. Those answers can no longer be "
        f"re-graded at the keys their run was published with. If the change under "
        f"acceptance/grader/ was intended, update this constant AND say in that run's RESULTS.md "
        f"that it is no longer re-gradable; if it was incidental, move the change out of "
        f"acceptance/grader/ instead — input validation, for one, does not belong in the scorer."
    )


##
# @brief A cited line number must not stop a set member from matching.
# @param written How the answer wrote the path.
# @param member How the rubric declares it.
# @return None.
# @version 1
@pytest.mark.parametrize(
    ("written", "member"),
    [
        ("src/facade/external_bridge.cpp:796", "src/facade/external_bridge.cpp"),
        ("src/mcp/health_monitor.cpp:92", "src/mcp/health_monitor.cpp"),
        ("src/mcp/transport_sse.cpp:107-120", "src/mcp/transport_sse.cpp"),
        ("./src/core/response_generator.cpp:402", "src/core/response_generator.cpp"),
        ("`src/x.cpp:1`", "src/x.cpp"),
    ],
)
def test_a_cited_line_number_still_matches_its_member(written: str, member: str) -> None:
    """**THIS SILENTLY ZEROED WHOLE SET MARKS, AND IT IS DETERMINISTIC — NOT JUDGE NOISE.**
    `_key` folded directories and backticks but not a trailing `:LINE`, so an answer citing
    `src/facade/external_bridge.cpp:796` keyed to `external_bridge.cpp:796` and could never equal
    the member's `external_bridge.cpp`. Measured on one 2026-10-26 cell: 4 of 7 members were
    correctly named and ALL EIGHT set decisions were scored against the answer — 18.5 points on
    that cell alone.

    **THE GRADER PRINTED ITS OWN REFUTATION AND NOTHING CHECKED IT.** That cell's precision detail
    read `named 4 not in the set: ['src/facade/external_bridge.cpp:796',
    'src/mcp/health_monitor.cpp:92', 'src/mcp/transport_sse.cpp:107',
    'src/mcp/transport_stdio.cpp:164']` — four MEMBER paths, reported as spurious.

    **THE BIAS IS DIFFERENTIAL, WHICH IS WHY AVERAGING CANNOT ABSORB IT.** It penalises whichever
    arm happens to cite line numbers, and on Q4 the two arms differed in exactly that habit on the
    same question. `path:line` is the citation style a code index encourages, so the arm under test
    is the one more likely to be punished.

    A RANGE IS INCLUDED because `:107-120` is as natural a citation as `:107`, and a fix that
    handled only the single-line form would leave half the defect in place.

    @brief A line suffix does not break matching.
    @param written The answer's spelling.
    @param member The rubric's spelling.
    @return None.
    @version 1
    """
    assert score._key(written) == score._key(member), (
        f"{written!r} keyed to {score._key(written)!r} but the member keys to "
        f"{score._key(member)!r} — a cited line number is still losing the decision"
    )


##
# @brief A real colon in a name must survive normalisation.
# @return None.
# @version 1
def test_a_colon_that_is_not_a_line_number_survives() -> None:
    """THE OVER-EAGER FIX IS THE OTHER FAILURE. `Owner::method` and a Windows-style `C:` prefix
    both contain colons that are not line citations, and stripping at the first colon would
    silently merge distinct members. Only a trailing `:digits` (optionally a range) is a citation.

    @brief Non-numeric colons are kept.
    @return None.
    @version 1
    """
    assert score._key("ServerManager::execute") == "servermanager::execute"
    assert score._key("src/a.cpp:abc") == "a.cpp:abc"


##
# @brief Extracting items but matching no member must be refused, not scored zero.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_extracting_items_that_match_no_member_is_refused(monkeypatch) -> None:
    """**THE HARNESS ALREADY PUBLISHED THIS FAILURE AND NOTHING NOTICED.** A trailing `:796` kept
    an answer's `src/facade/external_bridge.cpp:796` from equalling the member's
    `src/facade/external_bridge.cpp`, so a cell that named 4 of 7 members correctly scored 0 of 8
    set decisions, and the precision detail printed four MEMBER paths as "not in the set".

    `_key` now strips the citation, so that instance cannot recur. **This guard is for the next
    normalisation gap**, which will be just as unanticipated. The signature is specific: the
    extractor found things and NONE of them matched any member. That is far more likely a
    mis-keying than an answer that named only irrelevant files.

    The fixture deliberately uses a separator the current `_key` does NOT fold — a backslash
    path — so it stands in for a future gap rather than re-testing the one just fixed.

    @brief A total mismatch is unruled.
    @return None.
    @version 1
    """
    mark = Mark(
        text="every file that creates a thread",
        type="set",
        weight=2,
        members=[{"value": "src/facade/external_bridge.cpp"}, {"value": "src/mcp/health.cpp"}],
        extract="List the files.",
    )
    monkeypatch.setattr(
        score,
        "ask",
        lambda *_a, **_k: judge.Reply(text="ITEMS:\nsrc\\facade\\other_thing.cpp\nEND"),
    )

    out = score.score_set(mark, "an answer", "claude-sonnet-4-5-20250929", samples=1)

    assert all(d.hit is None for d in out), (
        f"a total member mismatch was scored instead of refused: {[(d.mark, d.hit) for d in out]}"
    )
    assert "key mismatch" in out[0].detail, f"the refusal does not say why: {out[0].detail!r}"


##
# @brief A genuine partial match must still be scored normally.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_partial_member_match_is_still_scored(monkeypatch) -> None:
    """THE GUARD MUST NOT SWALLOW REAL GRADING. If any member matched, the extraction demonstrably
    speaks the same language as the rubric, and the misses are then real misses. A guard that
    fired on partial matches would turn every imperfect answer into an unmeasured one.

    @brief Partial matches score.
    @return None.
    @version 1
    """
    mark = Mark(
        text="every file that creates a thread",
        type="set",
        weight=2,
        members=[{"value": "src/facade/external_bridge.cpp"}, {"value": "src/mcp/health.cpp"}],
        extract="List the files.",
    )
    monkeypatch.setattr(
        score,
        "ask",
        lambda *_a, **_k: judge.Reply(text="ITEMS:\nsrc/facade/external_bridge.cpp:796\nEND"),
    )

    out = score.score_set(mark, "an answer", "claude-sonnet-4-5-20250929", samples=1)
    hits = {d.mark.rsplit("— ", 1)[-1]: d.hit for d in out}

    assert hits["src/facade/external_bridge.cpp"] is True, (
        f"the cited member was not credited — the line-suffix fix regressed: {hits}"
    )
    assert hits["src/mcp/health.cpp"] is False, f"an unnamed member was credited: {hits}"


##
# @brief The judge's stated reason must reach the recorded decision.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_the_judges_reason_reaches_the_record(monkeypatch) -> None:
    """**THE HARNESS ASKED FOR REASONING AND THREW IT AWAY.** `verdict_prompt` requires a `QUOTE:`
    carrying the item's substance and a one-line `WHY:`, written before the verdict is settled —
    and only `read_verdict` was ever called, so every binary decision was recorded with
    `detail: ""`.

    Measured cost: an audit of 26 failed decisions found 11 with no stated reason at all, could
    not quote the judge where it disagreed with it, and listed that as its first limitation. A
    published grid exists for other people to argue with; a decision carrying no reason cannot be
    argued with at all.

    @brief The reason is recorded.
    @return None.
    @version 1
    """
    reply = judge.Reply(
        text="QUOTE: it names ServerManager::execute\nVERDICT: HIT\nWHY: stated directly in prose"
    )
    monkeypatch.setattr(judge, "ask", lambda *_a, **_k: reply)
    mark = Mark(text="names the entry point", type="retrieval", weight=1)

    voted = judge.vote(mark.text, "an answer", "claude-sonnet-4-5-20250929", 1)

    assert voted.verdict == "HIT"
    assert voted.rationale, "the winning verdict carried no rationale"
    assert "ServerManager::execute" in voted.rationale[0], voted.rationale


##
# @brief A failed vote must report transport reasons, not an empty rationale.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_failed_vote_still_reports_why_it_failed(monkeypatch) -> None:
    """ "THE JUDGE NEVER RULED" AND "THE JUDGE RULED AND SAID WHY" ARE DIFFERENT FACTS. Recording
    the rationale must not displace the transport reasons on an unruled decision, or a hole
    becomes indistinguishable from a verdict whose reason happened to be empty.

    @brief Unruled decisions keep their transport reasons.
    @return None.
    @version 1
    """
    monkeypatch.setattr(
        judge, "ask", lambda *_a, **_k: judge.Reply(error="rc=1 after 1: overloaded")
    )

    voted = judge.vote("a mark", "an answer", "claude-sonnet-4-5-20250929", 1)

    assert voted.verdict is None
    assert not voted.rationale, "a failed vote invented a rationale"
    assert any("overloaded" in r for r in voted.reasons), voted.reasons
