# SPDX-License-Identifier: MIT
"""Grading the same answer twice produced two different scores.

**THE JUDGE REACHES THE MODEL THROUGH A TRANSPORT WITH NO DETERMINISM CONTROLS.** `judge.ask`
shells out to `claude -p … --model …`, and that CLI exposes no `--temperature`, no `--seed` and no
`--top-p`. Every call is therefore a sample at default sampling, and re-grading the same answers
moved the score by a **mean absolute 8.95 pt** across 21 re-graded cells — larger than most
effects this harness exists to detect. An instrument that gives a different reading each time it
is used is not measuring only the thing it points at.

**WHY NOT temperature=0.** It would mean calling the API directly instead of the CLI, which moves
~3.1M judge input tokens per grading pass from a subscription onto metered billing, recurring on
every pass forever — and it would still leave residual nondeterminism rather than none.

**WHY A CACHE IS STRICTLY BETTER AT WHAT WAS WANTED.** Keyed on the whole prompt — which already
contains the mark text and the anonymised answer — plus the model, the same answer and the same
mark return the SAME verdict by construction, not approximately. A re-grade then costs nothing
instead of 3,348 calls, and a third party holding the artifacts can replay the published grading
exactly.

**IT MAKES A GRADE REPRODUCIBLE, NOT CORRECT**, and that distinction is the point rather than a
caveat. A wrong verdict becomes reliably wrong: stable, inspectable and arguable, instead of
different every time anyone checks it. These tests pin the reproducibility, and `--no-judge-cache`
exists so the floor can still be measured deliberately.

@brief The same answer and mark must yield the same verdict.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

from acceptance.grader import judge

## The cache is reset around every test by the autouse fixture in `tests/conftest.py`, which is
## session-wide because the leak crosses modules: `cmd_grade` configures the global and the tests
## that suffer for it live in other files.


##
# @brief A repeated call must return the first verdict without invoking the judge again.
# @param tmp_path Per-test temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_repeated_call_replays_the_first_verdict(tmp_path: Path, monkeypatch) -> None:
    """THE SUBPROCESS IS COUNTED, not just the return value. A cache that returned the right text
    while still paying for the call would satisfy a value-only assertion and none of the reasons
    it exists — determinism, and a free re-grade.

    The stub returns a DIFFERENT verdict each time it is called, so a cache miss is visible in the
    value as well as the count. Without the cache this test would see HIT then MISS.

    @brief A second identical call is served from cache.
    @return None.
    @version 1
    """
    calls = {"n": 0}

    def fake_run(argv, **kwargs):
        calls["n"] += 1
        verdict = "HIT" if calls["n"] == 1 else "MISS"

        class Done:
            returncode = 0
            stdout = json.dumps({"result": verdict})
            stderr = ""

        return Done()

    monkeypatch.setattr(judge.subprocess, "run", fake_run)
    judge.configure_cache(tmp_path / "judge-cache")

    first = judge.ask("mark: does it name the mutex?", "claude-sonnet-4-5-20250929")
    second = judge.ask("mark: does it name the mutex?", "claude-sonnet-4-5-20250929")

    assert first.text == "HIT"
    assert second.text == "HIT", (
        f"the second call returned {second.text!r} — the cache did not replay the first verdict, "
        f"so re-grading the same answer still produces a different score"
    )
    assert calls["n"] == 1, f"the judge was invoked {calls['n']} times; a re-grade is not free"


##
# @brief A different prompt or model must not hit another entry.
# @param tmp_path Per-test temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_different_prompt_or_model_is_judged_separately(tmp_path: Path, monkeypatch) -> None:
    """THE DANGEROUS FAILURE IS A KEY THAT IS TOO COARSE, because it would silently serve one
    mark's verdict for another and no assertion about determinism would notice. Two models are
    two instruments and must not share entries either.

    @brief Distinct calls get distinct entries.
    @return None.
    @version 1
    """
    seen: list[str] = []

    def fake_run(argv, **kwargs):
        seen.append(argv[argv.index("--model") + 1])

        class Done:
            returncode = 0
            stdout = json.dumps({"result": f"HIT{len(seen)}"})
            stderr = ""

        return Done()

    monkeypatch.setattr(judge.subprocess, "run", fake_run)
    judge.configure_cache(tmp_path / "judge-cache")

    a = judge.ask("mark one", "claude-sonnet-4-5-20250929")
    b = judge.ask("mark two", "claude-sonnet-4-5-20250929")
    c = judge.ask("mark one", "claude-haiku-5-5")

    assert {a.text, b.text, c.text} == {"HIT1", "HIT2", "HIT3"}, (
        "distinct prompts or models collided on one cache entry"
    )
    assert len(seen) == 3


##
# @brief A transport failure must not be cached.
# @param tmp_path Per-test temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_failure_is_not_cached(tmp_path: Path, monkeypatch) -> None:
    """**CACHING AN ERROR WOULD MAKE A TRANSIENT FAILURE PERMANENT.** The judge's observed failure
    mode is transient capacity — measured: three cells came back 85-100% unruled, every call
    failing, and the identical call succeeded minutes later with no code change. If that were
    cached, those holes would never fill, and `grade` is additive precisely so they can.

    @brief Errors are judged afresh.
    @return None.
    @version 1
    """
    state = {"fail": True}

    def fake_run(argv, **kwargs):
        class Done:
            returncode = 1 if state["fail"] else 0
            stdout = "" if state["fail"] else json.dumps({"result": "HIT"})
            stderr = "overloaded" if state["fail"] else ""

        return Done()

    monkeypatch.setattr(judge.subprocess, "run", fake_run)
    monkeypatch.setattr(judge, "ASK_ATTEMPTS", 1)
    judge.configure_cache(tmp_path / "judge-cache")

    failed = judge.ask("mark: anything", "claude-sonnet-4-5-20250929")
    assert failed.error, "the stub was supposed to fail"
    assert not list((tmp_path / "judge-cache").glob("*.json")), (
        "a transport failure was written to the cache, so it can never succeed on a later pass"
    )

    state["fail"] = False
    recovered = judge.ask("mark: anything", "claude-sonnet-4-5-20250929")
    assert recovered.text == "HIT", "a cached failure blocked the retry"


##
# @brief With the cache disabled, every call must reach the judge.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_disabling_the_cache_judges_afresh(monkeypatch) -> None:
    """**THIS IS HOW THE FLOOR IS MEASURED, AND WHY THE FLAG IS NOT A CONVENIENCE.** Judge
    variance is quantified by grading the same answers twice; with the cache on, the second pass
    replays the first and reports a floor of zero — a measurement of the cache rather than of the
    judge. A harness that could not turn its own cache off would have lost the ability to know how
    noisy it is.

    @brief No cache means no replay.
    @return None.
    @version 1
    """
    calls = {"n": 0}

    def fake_run(argv, **kwargs):
        calls["n"] += 1

        class Done:
            returncode = 0
            stdout = json.dumps({"result": "HIT" if calls["n"] == 1 else "MISS"})
            stderr = ""

        return Done()

    monkeypatch.setattr(judge.subprocess, "run", fake_run)
    judge.configure_cache(None)

    first = judge.ask("mark: same prompt", "claude-sonnet-4-5-20250929")
    second = judge.ask("mark: same prompt", "claude-sonnet-4-5-20250929")

    assert (first.text, second.text) == ("HIT", "MISS"), (
        "the cache was not actually disabled, so a floor pass would measure the cache"
    )
    assert calls["n"] == 2


## @brief A stub judge that answers each call with the next verdict from a list.
## @param monkeypatch Pytest monkeypatch fixture.
## @param replies Reply texts, one per subprocess call, in order.
## @return The call counter.
## @version 1
def _scripted(monkeypatch, replies: list[str]) -> dict:
    """@brief Install a judge stub that answers in order.
    @return Call counter.
    @version 1
    """
    calls = {"n": 0}

    def fake_run(argv, **kwargs):
        text = replies[calls["n"] % len(replies)]
        calls["n"] += 1

        class Done:
            returncode = 0
            stdout = json.dumps({"result": text})
            stderr = ""

        return Done()

    monkeypatch.setattr(judge.subprocess, "run", fake_run)
    return calls


##
# @brief A k=3 vote must reach the judge three times, not once and replay it twice.
# @param tmp_path Per-test temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_vote_of_three_asks_the_judge_three_times(tmp_path: Path, monkeypatch) -> None:
    """**THE CACHE COLLAPSED EVERY VOTE TO ONE CALL.** `vote` builds its prompt once and asks it
    `n` times; the cache keyed only on prompt and model, so call 1 was stored and calls 2 and 3
    replayed it. Every k=3 verdict was one sample counted three times: agreement read 1.0 by
    construction and the split rate read zero — a variance measurement of the cache.

    The stub disagrees with itself (HIT, MISS, HIT), so a collapsed vote is visible in the tally
    as well as in the call count.

    @brief Three samples are three judge calls.
    @return None.
    @version 1
    """
    calls = _scripted(monkeypatch, ["VERDICT: HIT", "VERDICT: MISS", "VERDICT: HIT"])
    judge.configure_cache(tmp_path / "judge-cache")

    voted = judge.vote("a mark", "an answer", "claude-sonnet-4-5-20250929", 3)

    assert calls["n"] == 3, f"the judge was asked {calls['n']} time(s) for a vote of three"
    assert voted.verdict == "HIT" and voted.agreement < 1.0, voted


##
# @brief Re-grading a k=3 vote must replay all three samples, not re-ask the judge.
# @param tmp_path Per-test temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_repeated_vote_replays_every_sample(tmp_path: Path, monkeypatch) -> None:
    """THE FIX MUST NOT COST THE CACHE ITS PURPOSE. Each sample is cached under its own key, so a
    re-grade replays the same split, exactly and for free.

    @brief A re-vote is exact and free.
    @return None.
    @version 1
    """
    calls = _scripted(monkeypatch, ["VERDICT: HIT", "VERDICT: MISS", "VERDICT: HIT"])
    judge.configure_cache(tmp_path / "judge-cache")

    first = judge.vote("a mark", "an answer", "claude-sonnet-4-5-20250929", 3)
    second = judge.vote("a mark", "an answer", "claude-sonnet-4-5-20250929", 3)

    assert calls["n"] == 3, f"a re-vote asked the judge {calls['n'] - 3} more time(s)"
    assert (second.verdict, second.agreement) == (first.verdict, first.agreement)


##
# @brief A k=3 set extraction must reach the judge three times.
# @param tmp_path Per-test temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_a_set_extraction_of_three_asks_the_judge_three_times(tmp_path: Path, monkeypatch) -> None:
    """`score_set` HAD THE IDENTICAL COLLAPSE: one prompt, asked `samples` times through the same
    cached `ask`. Its majority rule exists because one flaky extraction moved a cell ten points;
    with the collapse, the "majority" was one extraction counted three times.

    @brief Three extraction samples are three judge calls.
    @return None.
    @version 1
    """
    from acceptance.grader import score
    from acceptance.grader.rubric import Mark

    calls = _scripted(monkeypatch, ["ITEMS:\ninclude\nEND"])
    judge.configure_cache(tmp_path / "judge-cache")
    mark = Mark(
        text="the directories",
        type="set",
        weight=1,
        extract="List them.",
        members=({"value": "include"},),
    )

    score.score_set(mark, "an answer", "claude-sonnet-4-5-20250929", samples=3)

    assert calls["n"] == 3, f"the judge was asked {calls['n']} time(s) for three extractions"


##
# @brief The first sample must keep the key every existing cache entry was written under.
# @param tmp_path Per-test temporary directory.
# @param monkeypatch Pytest monkeypatch fixture.
# @return None.
# @version 1
def test_the_first_sample_replays_an_entry_written_before_samples_were_keyed(
    tmp_path: Path, monkeypatch
) -> None:
    """THE EXISTING CACHES STAY VALID FOR WHAT THEY ACTUALLY HOLD. Every entry already written is
    sample 0 — the only sample the collapsed vote ever made. So sample 0 keeps the old key, and
    only samples 1 and up are new. The entry is written here by hand, in the old format, rather
    than through `ask`, so this test cannot pass by agreeing with itself.

    @brief Sample 0 uses the pre-existing key.
    @return None.
    @version 1
    """
    import hashlib

    calls = _scripted(monkeypatch, ["VERDICT: MISS"])
    cache = tmp_path / "judge-cache"
    judge.configure_cache(cache)
    model, prompt = "claude-sonnet-4-5-20250929", "mark: written before"
    digest = hashlib.sha256(f"{model}\x00{prompt}".encode()).hexdigest()
    (cache / f"{digest}.json").write_text(json.dumps({"text": "VERDICT: HIT"}), "utf-8")

    reply = judge.ask(prompt, model, sample=0)

    assert reply.text == "VERDICT: HIT" and calls["n"] == 0, (
        "sample 0 missed an entry written under the original key, so every existing cache "
        "would be re-judged from scratch"
    )
