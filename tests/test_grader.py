# SPDX-License-Identifier: MIT
"""Tests for the acceptance grader's scoring arithmetic and judge blindness.

NO JUDGE CALLS. Everything here drives the pure functions — prompt construction, reply parsing,
set arithmetic, score arithmetic — because those are where a defect is silent. A wrong prompt
still returns verdicts; wrong arithmetic still returns a number.

@brief Tests for acceptance.grader.
@version 1
"""

from __future__ import annotations

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
