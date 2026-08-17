# SPDX-License-Identifier: MIT
## @brief Pin the benchmark harness rules that decide a published number.
## @version 1
"""The harness is not the product, but it decides what the product is allowed to claim.

Three rules here have each been WRONG in a shipped state, and each one silently moved a
headline figure rather than raising an error:

- **Arm fencing** — `arm_only` names the arm that CAN reach a mark. Inverted, it scores the
  source arm zero on marks it was never eligible for, understating it and flattering the
  index. It has been inverted twice.
- **Index-arm validity** — a cell that CALLED a database tool and got an error did not use the
  database. Counting attempts scored a cell VALID whose own answer said it could not reach the
  index at all.
- **Metric de-duplication** — `metrics.csv` is append-only, so a re-run cell counted twice in
  every aggregate, biased toward the slower attempt.

None of these breaks anything visibly. That is exactly why they get tests.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import bench_arms
import bench_judge
import bench_publish
import bench_rubric
import fallback_audit
import grade_matrix
import grade_prompts
import grade_report
import pytest
import run_matrix
import target_check
import tier_report
from grade_matrix import summarise
from run_matrix import latest_per_cell

## Built by concatenation so a foreign home path never appears as a literal in this file.
_FOREIGN_LINUX = "/home/" + "otherperson"


## @brief Arm fencing counts a mark for exactly the arm that can reach it.
## @return None.
## @version 1
def test_arm_fencing_truth_table() -> None:
    """All six combinations, stated explicitly rather than reasoned about.

    The rubric writes `raw`/`db`; the harness writes `src`/`mcp`. That translation is the
    part that gets inverted, and the failure is invisible: every mark still gets a verdict,
    the denominators just move. A published grid once counted four unreachable marks against
    the raw arm and understated it by four points.

    @brief Every fence/arm pair scores the way the rubric says.
    @version 1
    """
    expected = {
        ("db", "src"): False,  # a db-only mark is NOT on the source arm's exam
        ("db", "mcp"): True,
        ("raw", "src"): True,
        ("raw", "mcp"): False,
        ("", "src"): True,  # unfenced marks count for both
        ("", "mcp"): True,
    }
    for (fence, arm), counted in expected.items():
        stats = summarise([{"verdict": "HIT", "arm_only": fence, "judge": None}], arm)
        assert stats["marks_total"] == (1 if counted else 0), f"fence={fence!r} arm={arm!r}"
        assert stats["marks_fenced_out"] == (0 if counted else 1)


## @brief A fenced-out mark is excluded, never scored zero.
## @return None.
## @version 1
def test_fenced_marks_are_excluded_not_failed() -> None:
    """Zero says "tried and failed"; exclusion says "was never on the exam". Scoring a
    fenced mark zero shrinks the numerator while leaving the denominator, which is
    arithmetically identical to the arm getting it wrong.

    @brief Fencing shrinks the denominator, not just the score.
    @version 1
    """
    marks = [
        {"verdict": "HIT", "arm_only": "", "judge": None},
        {"verdict": "MISS", "arm_only": "db", "judge": None},  # unreachable from src
    ]
    stats = summarise(marks, "src")
    assert stats["marks_total"] == 1, "the db-only mark must leave the denominator"
    assert stats["score"] == 1.0
    assert stats["marks_fenced_out"] == 1, "and must be reported, not silently dropped"


## @brief PARTIAL is not a verdict this harness can score.
## @return None.
## @version 1
def test_partial_is_not_a_verdict_the_harness_can_score() -> None:
    """`questions-TEMPLATE.md` has said "A mark is a mark; hit or miss; never past 100%" all
    along, and `PARTIAL` contradicted it in code — weighted 0.5 in `score` and again by a
    SEPARATE hardcoded 0.5 in the summary expression, neither of which any test read.

    The owner's rule makes the contradiction consequential rather than cosmetic. Under atomic
    marks a fact is stated or it is not, so a half point is not a finer measurement, it is a
    refusal to decide that then gets averaged into a headline.

    Asserted as a REFUSAL rather than as "weighs 0.0", because a verdict that scores zero is
    still a verdict the judge can emit and a reader can see in a sidecar. The anti-vacuity
    check is what must catch it, so the whole path is closed rather than re-weighted.

    @brief Feeding a PARTIAL verdict raises rather than scoring a fraction.
    @version 1
    """
    with pytest.raises(AssertionError, match="uncounted verdict"):
        summarise([{"verdict": "PARTIAL", "arm_only": "", "judge": None}], "src")


## @brief No verdict the harness does count may weigh a fraction.
## @return None.
## @version 1
def test_no_countable_verdict_weighs_a_fraction() -> None:
    """The negative half, and the one that survives this change: removing PARTIAL is
    pointless if some other path reintroduces a half point. Every verdict the harness counts
    is checked on BOTH score columns, because `score` and `score_strict` are computed by
    different expressions and only one of them read the weight map.

    @brief Every countable verdict scores 0 or 1 on both columns.
    @version 1
    """
    for token in ("HIT", "MISS", "JUDGE_ERROR"):
        stats = summarise([{"verdict": token, "arm_only": "", "judge": None}], "src")
        assert stats["score"] in (0.0, 1.0), f"{token} scored a fraction: {stats['score']}"
        assert stats["score_strict"] in (0.0, 1.0), f"{token} strict-scored a fraction"
        assert "marks_partial" not in stats, (
            "a summary key that is always zero is dead reporting — it invites a reader to "
            "believe partial credit is still being measured"
        )


## @brief The judge is never offered a verdict the parser will not accept.
## @return None.
## @version 1
def test_the_judge_prompt_offers_exactly_the_verdicts_the_parser_accepts() -> None:
    """TWO DOCUMENTS, ONE FACT. The prompt listed its verdicts in prose and the extractor was
    handed a separate inline tuple, with nothing tying them: a token offered to the judge but
    absent from the tuple parses as unreadable and becomes a JUDGE_ERROR, which weighs the
    same as a genuine MISS — so a prompt/parser disagreement presents as the answer being
    wrong rather than as the grader being broken.

    Both now render from `MARK_VERDICTS`. This asserts the tie in both directions, since a
    one-directional check passes on a prompt that offers a strict subset.

    @brief The prompt's verdict list and the parser's allowed set are the same set.
    @version 1
    """
    prompt = grade_prompts.mark_prompt("some checklist item", "some candidate answer")
    assert "PARTIAL" not in prompt, "the judge must not be offered a verdict nothing scores"
    for token in grade_prompts.MARK_VERDICTS:
        assert token in prompt, f"{token} is accepted by the parser but never offered"
    assert not (set(grade_prompts.MARK_VERDICTS) ^ set(grade_matrix.MARK_VERDICTS)), (
        "the extractor and the prompt must read the same constant, not two copies"
    )
    ## THE SET IDENTITY, not just the absence of PARTIAL. Written as an absence check alone,
    ## this test passed against a mutation that DROPPED "MISS" from the offered set — after
    ## which the judge could only say HIT, and every genuine miss would arrive as an
    ## unparseable reply scored JUDGE_ERROR, which weighs what a MISS weighs. The bug would
    ## have been invisible in the totals and fatal to `unmarked_pct`.
    ##
    ## JUDGE_ERROR is the one deliberate asymmetry: scorable, never offered, because the
    ## harness assigns it when the judge fails to answer at all.
    assert set(grade_prompts.MARK_VERDICTS) | {"JUDGE_ERROR"} == set(grade_matrix.VERDICT_WEIGHT), (
        "every scorable verdict except JUDGE_ERROR must be offered to the judge, and vice versa"
    )
    assert all(w in (0.0, 1.0) for w in grade_matrix.VERDICT_WEIGHT.values()), (
        f"a mark is a mark: {grade_matrix.VERDICT_WEIGHT} contains a fractional weight"
    )


## @brief The report must read the shape the grader actually writes.
## @return None.
## @version 1
def test_the_report_reads_the_sidecar_the_grader_actually_writes(tmp_path: Path) -> None:
    """`grade_answer` writes NINE keys and the report subscripted two it has never written —
    `g["bonus"]` and `g["auto_fail"]`, both bare — so `grade_matrix report` raised KeyError on
    every real run. The only test covering the report hand-built a WIDER sidecar and its
    docstring claimed that shape was "what `grade_answer` writes", which stopped being true
    and kept the gap invisible: the fixture matched the reader rather than the writer.

    Exactly the shape this repo has been caught by before — a fixture built to match the code
    under test instead of the world it runs in.

    The fixture below carries ONLY `grade_answer`'s keys, deliberately. If the grader grows a
    section, this test starts failing and the report gets updated with it, which is the
    coupling that was missing.

    @brief build_report succeeds on a sidecar with only the keys grade_answer writes.
    @version 1
    """
    from grade_report import build_report

    sidecar = {
        "q": "Q1", "arm": "mcp", "model": "sonnet", "run": 1,
        "answer": "Q1_sonnet_mcp_r1.md", "rubric": "r.md", "declared_mark_count": 1,
        "summary": grade_matrix.summarise(
            [{"verdict": "HIT", "arm_only": "", "judge": None}], "mcp"
        ),
        "marks": [{"index": 1, "kind": "mark", "text": "t", "double": False,
                   "arm_only": "", "conceptual": False, "judge": None, "verdict": "HIT"}],
    }  # fmt: skip
    (tmp_path / "Q1_sonnet_mcp_r1.grade.json").write_text(json.dumps(sidecar), encoding="utf-8")

    report = build_report(tmp_path)
    assert "Q1" in report, f"the cell must reach the table:\n{report}"


## @brief The per-cell table reports every metric the owner asked for.
## @return None.
## @version 1
def test_the_per_cell_table_carries_the_six_required_metrics(tmp_path: Path) -> None:
    """D1, owner 2026-08-13: "I expect metrics back on time, token cost, marks met, and # of
    non-index tools used (for the index arm) and a tool/turn count per." SIX numbers, per cell.

    No existing view answered that. `run_matrix report` gives tokens/tools/turns/ms and NO
    marks; `tier_report` gives quality% aggregated per model+arm, destroying per-cell identity
    inside `_quality`, and prints a verdict. The join already existed here — grades against
    `metrics.csv` on `answer_path` — it just did not carry the columns.

    The non-index count is `tool_uses - used_db_tools`, derivable from two persisted columns
    and computed nowhere before this. It is a SMELL CHECK, not a graded axis (its cost is
    already inside the token count), so it is reported and never scored.

    AND THE TABLE MUST NOT RULE. The owner determines the pass; the harness collects marks.

    @brief The per-cell table carries time, tokens, marks, tools, non-index tools and turns.
    @version 1
    """
    from grade_report import build_report

    sidecar = {
        "q": "Q1", "arm": "mcp", "model": "sonnet", "run": 1,
        "answer": "Q1_sonnet_mcp_r1.md", "rubric": "r.md", "declared_mark_count": 2,
        "summary": grade_matrix.summarise(
            [{"verdict": "HIT", "arm_only": "", "judge": None},
             {"verdict": "MISS", "arm_only": "", "judge": None}], "mcp"),
        "marks": [],
    }  # fmt: skip
    (tmp_path / "Q1_sonnet_mcp_r1.grade.json").write_text(json.dumps(sidecar), encoding="utf-8")
    (tmp_path / "metrics.csv").write_text(
        "answer_path,duration_ms,total_tokens,tool_uses,used_db_tools,num_turns,valid\n"
        "Q1_sonnet_mcp_r1.md,45074,458380,10,7,6,True\n",
        encoding="utf-8",
    )

    report = build_report(tmp_path)
    for token in ("45074", "458380", "1/2", "10", "6"):
        assert token in report, f"{token!r} missing from the per-cell table:\n{report}"
    assert "| 3 |" in report, (
        "the non-index tool count (10 tool uses - 7 index calls = 3) is reported nowhere else"
    )
    ## Targeted at the RULING VOCABULARY, not at the word "verdict" — the table's own heading
    ## says "no verdict", which a naive substring check flags. These are the tokens
    ## `tier_report` prints when it rules ("index uses N% FEWER tokens", "REACHES", "PARITY",
    ## "below"), and none of them belongs in a collection-only view.
    for ruling in ("REACHES", "PARITY", "FEWER TOKENS", "PASSES", " PASS ", " FAIL "):
        assert ruling not in report.upper(), (
            f"{ruling!r} rules on the result; the harness collects marks and the owner "
            f"determines the pass (D1)"
        )
    assert "owner determines the pass" in report, (
        "and the table must SAY it does not rule, so a reader does not supply one"
    )


## @brief The falsity veto needs unanimity, and its three states stay distinguishable.
## @return None.
## @version 1
def test_the_falsity_veto_requires_unanimity_and_keeps_three_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D3 lets ONE judge decision zero a whole question, and this is the same judge that
    produced 102 unruled marks on a single grid. So the veto is voted, not asked once, and a
    bare majority is not enough — `VETO_AGREEMENT` is 1.0.

    The asymmetry is deliberate and in one direction only: a MISSED falsehood costs one wrong
    cell, which the owner reading the answer can still catch; a WRONGLY vetoed cell reads as a
    catastrophic tool failure, and this project's history is of exactly such numbers being
    quoted onward.

    THREE STATES, and the third is why this test exists at all. "did not run", "ran and found
    nothing" and "ran and could not tell" must not collapse: unchecked reading as clean is the
    mechanism behind the identifier leak, the disarmed coverage gate and a retracted grid.

    @brief A veto fires only on unanimity; errors read as unchecked, never clean.
    @version 1
    """
    assert grade_matrix.VETO_AGREEMENT == 1.0, "a bare majority must not be able to veto"

    def replies(*tokens: str):
        """@brief Feed one canned judge reply per sample. @return The stub. @version 1"""
        queue = list(tokens)

        def stub(*_a: object, **_k: object) -> bench_judge.JudgeReply:
            token = queue.pop(0) if queue else "CONSISTENT"
            if token == "ERROR":
                return bench_judge.JudgeReply(error="session limit")
            return bench_judge.JudgeReply(text=f"VERDICT: {token}\nQUOTE: x\nWHY: y")

        return stub

    truths = ["there are two thread spawn sites"]

    ## Unanimous contradiction -> vetoed.
    monkeypatch.setattr(
        grade_matrix.judge, "ask", replies("CONTRADICTED", "CONTRADICTED", "CONTRADICTED")
    )
    unanimous = grade_matrix.falsity_check(truths, "an answer", "haiku", 3)
    assert unanimous is not None and unanimous["vetoed"] is True
    assert unanimous["agreement"] == 1.0

    ## A DIVIDED vote must NOT veto, even though the majority said CONTRADICTED — and the
    ## majority verdict is still recorded, so the disagreement is readable rather than lost.
    monkeypatch.setattr(
        grade_matrix.judge, "ask", replies("CONTRADICTED", "CONTRADICTED", "CONSISTENT")
    )
    divided = grade_matrix.falsity_check(truths, "an answer", "haiku", 3)
    assert divided is not None
    assert divided["vetoed"] is False, "2 of 3 must not zero a question"
    assert divided["verdict"] == "CONTRADICTED", "and the divided majority must still be visible"
    assert divided["agreement"] < 1.0

    ## EVERY SAMPLE ERRORED: not checked. Not clean, and emphatically not false.
    monkeypatch.setattr(grade_matrix.judge, "ask", replies("ERROR", "ERROR", "ERROR"))
    unknown = grade_matrix.falsity_check(truths, "an answer", "haiku", 3)
    assert unknown is not None
    assert unknown["checked"] is False, "a run of pure transport failures is UNCHECKED"
    assert unknown["vetoed"] is False, "and must never veto on no evidence"
    assert unknown["errors"] == 3

    ## Disarmed: the pass did not run at all, which is a third distinct state.
    assert grade_matrix.falsity_check(truths, "an answer", "haiku", 0) is None
    assert grade_matrix.falsity_check([], "an answer", "haiku", 3) is None


## @brief A veto zeroes the question's quality without hiding its measured score.
## @return None.
## @version 1
def test_a_veto_zeroes_quality_but_leaves_the_measured_score_readable(tmp_path: Path) -> None:
    """The owner's rule: "a 99% token reduction with a false answer == failure". So the quality
    axis goes to zero while the token axis is untouched — cheapness cannot buy off a falsehood.

    The zero is applied in `tier_report._quality`, where the headline is computed, and NOT in
    `summarise`, which keeps each cell's measured score. That split is the point: the veto is
    judge-driven, so a human must be able to see "scored 3/3 AND vetoed" and confirm the veto by
    hand. An unexplained zero would be unreviewable.

    The marks stay in the DENOMINATOR. Dropping them too would make a vetoed cell arithmetically
    invisible instead of costly.

    @brief A vetoed cell earns zero in the aggregate and keeps its per-cell score.
    @version 1
    """
    from grade_report import build_report

    marks = [{"index": 1, "kind": "mark", "text": "t", "double": False,
              "arm_only": "", "conceptual": False, "judge": None, "verdict": "HIT"}]  # fmt: skip
    falsity = {"checked": True, "verdict": "CONTRADICTED", "agreement": 1.0,
               "tally": [["CONTRADICTED", 3]], "samples": 3, "errors": 0, "vetoed": True}  # fmt: skip
    sidecar = {
        "q": "Q1", "arm": "mcp", "model": "sonnet", "run": 1,
        "answer": "Q1_sonnet_mcp_r1.md", "rubric": "r.md", "declared_mark_count": 1,
        "summary": grade_matrix.summarise(marks, "mcp", falsity),
        "falsity": falsity, "marks": marks,
    }  # fmt: skip
    (tmp_path / "Q1_sonnet_mcp_r1.grade.json").write_text(json.dumps(sidecar), encoding="utf-8")

    ## The per-cell truth: measured 1/1, and flagged.
    assert sidecar["summary"]["score"] == 1.0, "the measured score must survive the veto"
    assert sidecar["summary"]["quality_vetoed"] is True
    assert sidecar["summary"]["index_false"] == 1, "counted separately, never folded into MISS"
    assert sidecar["summary"]["marks_miss"] == 0, "the veto is not a miss"

    ## The aggregate truth: zero earned, denominator intact.
    earned, possible, _unruled = tier_report._quality(tmp_path)[("sonnet", "mcp")]
    assert earned == 0.0, "a vetoed question earns nothing however many marks it hit"
    assert possible == 1, "and its marks stay in the denominator, so the veto costs something"

    report = build_report(tmp_path)
    assert "VETOED" in report, f"the veto must be visible per cell:\n{report}"


## @brief A judge reply naming a retired verdict is rejected at the call site.
## @return None.
## @version 1
def test_a_judge_reply_naming_a_retired_verdict_is_not_accepted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """THE SET-IDENTITY TEST CANNOT SEE THIS, and a mutation proved it. Comparing
    `grade_prompts.MARK_VERDICTS` with `grade_matrix.MARK_VERDICTS` compares the same imported
    OBJECT, so it asserts the import exists — not that the extractor call site uses it. Putting
    the old inline `("HIT", "PARTIAL", "MISS")` tuple back at that call site left the whole
    suite green.

    So this drives `judge_mark` with a canned reply and asserts the BEHAVIOUR: a judge that
    answers PARTIAL is not understood. That is the property the constant exists to produce, and
    it holds however the call site is written.

    The failure it prevents is quiet. A PARTIAL accepted at the extractor would reach
    `summarise`, which now refuses it — so a single stray reply would abort a whole grading run
    rather than mis-score one mark. Rejecting it here turns that into one JUDGE_ERROR, counted
    and visible in `unmarked_pct`.

    @brief judge_mark rejects a verdict token outside the offered set.
    @version 1
    """
    reply = bench_judge.JudgeReply(
        text="Looks close enough.\nVERDICT: PARTIAL\nQUOTE: NONE\nWHY: gestures at it"
    )
    monkeypatch.setattr(grade_matrix.judge, "ask", lambda *_a, **_k: reply)

    mark = bench_rubric.Mark(index=1, text="names the mutex")
    got = grade_matrix.judge_mark(mark, "an answer", "haiku")

    assert got["verdict"] is None, "PARTIAL must not be accepted as a verdict"
    assert "no VERDICT token" in got.get("judge_error", ""), (
        "and the rejection must be recorded as an unreadable reply, not as a MISS"
    )
    assert got["raw"] is reply.text, "the raw reply is kept so a human can see what happened"


## @brief An index tool call that errored does not count as using the index.
## @return None.
## @version 1
def test_db_tool_outcomes_separates_attempted_from_returned(tmp_path: Path) -> None:
    """The measured failure: an index-arm cell whose MCP server never spawned emitted one
    `set_target`, received `No such tool available`, wrote a page explaining it could not
    answer — and was scored VALID because the attempt counter read 1.

    @brief Attempted and succeeded are different counts.
    @version 1
    """
    prefix = bench_arms.MCP_TOOL_PREFIX
    lines = [
        {"message": {"content": [{"type": "tool_use", "id": "a", "name": f"{prefix}set_target"}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "a", "is_error": True}]}},
        {"message": {"content": [{"type": "tool_use", "id": "b", "name": f"{prefix}search"}]}},
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "b"}]}},
    ]
    path = tmp_path / "t.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

    attempted, succeeded = bench_arms.db_tool_outcomes(path)
    assert (attempted, succeeded) == (2, 1)

    only_failed = tmp_path / "f.jsonl"
    only_failed.write_text("\n".join(json.dumps(x) for x in lines[:2]), encoding="utf-8")
    assert bench_arms.db_tool_outcomes(only_failed) == (1, 0), "an all-errors cell is not valid"


## @brief A re-run cell counts once, and the supersession is reported.
## @return None.
## @version 1
def test_latest_per_cell_keeps_the_last_attempt() -> None:
    """Append-only is right for an audit trail and wrong for an average. A retried cell is
    usually the slower one, so double-counting biases rather than merely adding noise.

    @brief De-duplication keeps the final attempt and reports the count dropped.
    @version 1
    """
    rows = [
        {"q": "Q5", "arm": "mcp", "model": "opus", "run": "1", "total_tokens": "100"},
        {"q": "Q5", "arm": "mcp", "model": "opus", "run": "1", "total_tokens": "999"},
        {"q": "Q5", "arm": "src", "model": "opus", "run": "1", "total_tokens": "200"},
    ]
    kept, superseded = latest_per_cell(rows)
    assert superseded == 1
    assert sorted(r["total_tokens"] for r in kept) == ["200", "999"]


## @brief Paired token ratios pair within a question, and cancel question difficulty.
## @return None.
## @version 2
def test_paired_ratios_pair_within_question_and_run() -> None:
    """Pairing is what makes metric 2 computable at all. Question difficulty dominates the
    spread, and comparing two pooled arm means would drown a real effect in it.

    @brief Each pair is one question, one run, both arms.
    @version 2
    """
    rows = [
        {"q": "Q1", "run": "1", "arm": "src", "model": "haiku", "total_tokens": "1000"},
        {"q": "Q1", "run": "1", "arm": "mcp", "model": "haiku", "total_tokens": "500"},
        {"q": "Q2", "run": "1", "arm": "src", "model": "haiku", "total_tokens": "4000"},
        {"q": "Q2", "run": "1", "arm": "mcp", "model": "haiku", "total_tokens": "1000"},
        # Unpaired (no mcp partner) and a different model — neither may produce a pair.
        {"q": "Q3", "run": "1", "arm": "src", "model": "haiku", "total_tokens": "9000"},
        {"q": "Q1", "run": "1", "arm": "src", "model": "opus", "total_tokens": "7000"},
    ]
    pairs = tier_report._paired_ratios(rows, "haiku")
    assert [(q, r) for q, r, _ in pairs] == [("Q1", "1"), ("Q2", "1")]
    assert [round(x, 3) for _, _, x in pairs] == [0.5, 0.25]


## @brief A verdict is refused below the minimum number of paired observations.
## @return None.
## @version 2
def test_no_verdict_below_the_pair_floor() -> None:
    """The bug this pins SHIPPED in the first version of the section written to prevent it: a
    percentile bootstrap over ONE pair resamples the same value every time, so the interval
    had zero width and a single unrepeated cell printed "index uses 25% FEWER tokens".

    An interval that cannot span 1.0 because it has no width is not evidence.

    @brief A one-pair bootstrap must not produce a usable interval.
    @version 2
    """
    assert tier_report.MIN_PAIRS_FOR_VERDICT >= 10, "a percentile bootstrap needs real n"

    geo, lo, hi = tier_report._ratio_interval([0.75])
    assert lo == hi == geo, "n=1 bootstrap is degenerate — that is exactly why the floor exists"

    ## And the floor is above what the calibration produced, so calibration data can never
    ## reach a verdict: 1 question x 3 runs is 3 pairs.
    assert tier_report.MIN_PAIRS_FOR_VERDICT > 3


## @brief Ratios are averaged geometrically, so reciprocal measurements cancel.
## @return None.
## @version 2
def test_ratio_mean_is_geometric() -> None:
    """The arithmetic mean of 0.5x and 2.0x is 1.25x — a 25% increase invented from two
    measurements that exactly cancel. For ratios the geometric mean is the correct centre.

    @brief 0.5x and 2.0x average to 1.0x.
    @version 2
    """
    geo, _, _ = tier_report._ratio_interval([0.5, 2.0])
    assert abs(geo - 1.0) < 1e-9


## @brief Normalising an already-normalised artifact changes nothing.
## @return None.
## @version 1
def test_publishable_is_idempotent() -> None:
    """The sweep sanitises at the end and an operator may run it again before committing.
    A second pass that mangled the first would corrupt evidence silently.

    @brief Sanitisation is safe to repeat.
    @version 1
    """
    once = bench_publish.publishable(f"{Path.home()}/Projects/x {_FOREIGN_LINUX}/y")
    assert bench_publish.publishable(once) == once


## @brief The tools a completed run actually used are seen by the audit.
## @return None.
## @version 1
def test_the_audit_sees_the_tools_the_real_run_used() -> None:
    """`TaskCreate` and `TaskUpdate` are not hypothetical: 15 cells apiece in the completed
    396-cell entropic run used them, in BOTH arms, and the audit's exact-match check for
    `"Task"` saw neither. So did `LSP` (1 cell) and `Glob` in the source arm.

    These names are taken from the recorded histograms under
    `acceptance/targets/entropic/`, NOT invented — the point of the test is that the
    checker's blind spot was occupied by real traffic, and a plausible-sounding fake name
    would prove only that the code does what it says.

    They must be REPORTED as unlisted and must NOT be violations: they read no source,
    query no index, and are equally reachable from either arm, so they cannot bias the
    comparison `audit_clean` exists to protect.

    @brief Real unlisted tool names from the 0.5.0 run surface as unlisted, not violations.
    @version 1
    """
    for arm in ("src", "mcp"):
        result = bench_arms.audit(arm, [("TaskCreate", "{}"), ("TaskUpdate", "{}")])
        assert result["unlisted_tools"] == ["TaskCreate", "TaskUpdate"], arm
        assert result["violations"] == [], f"{arm}: bookkeeping is not contamination"
        assert result["audit_clean"] is True, arm

    ## `LSP` can read source, but the fence it would break is the INDEX arm's, and the one
    ## real call sat in the source arm where reading source is the assignment.
    assert bench_arms.audit("src", [("LSP", "{}")])["unlisted_tools"] == ["LSP"]
    assert bench_arms.audit("mcp", [("LSP", "{}")])["unlisted_tools"] == ["LSP"]


## @brief A sub-agent spawner under an unfamiliar name is caught by the prefix rule.
## @return None.
## @version 1
def test_an_unknown_subagent_spawner_is_an_isolation_break() -> None:
    """THE DEFECT THIS CLOSES. An exact-match check for `"Task"` misses any spawner added
    under a new name, and a source-arm cell that delegated file reading to a sub-agent
    would produce a result nobody could see was invalid — the sub-agent's transcript is
    never written to the cell's own.

    Unfamiliar names on purpose here: the prefix rule has to hold for the tool we have not
    met yet, which is the only case exact matching cannot cover.

    @brief Task*/Agent* names outside the exemption list are violations in both arms.
    @version 1
    """
    for name in ("TaskDelegate", "TaskSpawn", "AgentRun"):
        for arm in ("src", "mcp"):
            result = bench_arms.audit(arm, [(name, "{}")])
            assert result["violations"] == [f"spawn:{name}"], f"{name} in {arm}"
            assert result["audit_clean"] is False, f"{name} in {arm}"
            assert result["unlisted_tools"] == [], "a spawner is a violation, not a footnote"

    ## The exemption is what separates the two verdicts, and it is a list of names rather
    ## than a pattern, so a new family member defaults to VIOLATION.
    assert bench_arms._spawns_subagents("TaskDelegate") is True
    assert bench_arms._spawns_subagents("TaskCreate") is False


## @brief Unlisted and isolation-breaking findings are distinguishable, not collapsed.
## @return None.
## @version 1
def test_unlisted_is_reported_separately_from_a_break() -> None:
    """Both must be VISIBLE and they must not be the same signal. Collapsing them into
    `violations` would fail 15 sound cells of a completed run over todo bookkeeping, and a
    flag that fires on cases that are fine teaches a reviewer to ignore it. Dropping the
    unlisted set restores the silence the fix exists to remove.

    @brief One transcript, one violation and one footnote, in different fields.
    @version 1
    """
    result = bench_arms.audit("src", [("TaskCreate", "{}"), ("TaskDelegate", "{}")])
    assert result["violations"] == ["spawn:TaskDelegate"]
    assert result["unlisted_tools"] == ["TaskCreate"]
    assert result["audit_clean"] is False, "the break decides the verdict"

    clean = bench_arms.audit("src", [("TaskCreate", "{}")])
    assert clean["audit_clean"] is True, "the footnote alone does not disqualify a cell"


## @brief The deny check is derived from ARM_POLICY, not a restated literal.
## @return None.
## @version 1
def test_the_deny_list_is_honoured_in_full() -> None:
    """The replaced code compared against `{"Grep", "Glob", "Bash", "Task"}` in the `mcp`
    arm only. That literal had drifted from the policy it mirrored, so a denied attempt was
    invisible to the audit. Deriving the check from `ARM_POLICY` makes that drift impossible
    rather than merely fixed — and it is why this test still holds after gh#354 shrank the
    policy to two web tools: it asserts the DERIVATION, not a remembered list.

    @brief Every name on an arm's deny list is a violation for that arm.
    @version 2
    """
    for arm in ("src", "mcp"):
        _, denied = bench_arms.ARM_POLICY[arm]
        assert denied, f"{arm}: an empty deny list would make this test vacuous"
        for name in denied:
            label = bench_arms.classify_tool(arm, name)
            assert label is not None, f"{arm}: denied {name} classified clean"
            assert label.startswith(("tool:", "spawn:")), f"{arm}/{name}: {label}"

    ## The case that survives, spelled out: the open internet is a THIRD source measuring
    ## neither arm, so it is denied for both where every other affordance was released.
    assert bench_arms.audit("src", [("WebFetch", "{}")])["violations"] == ["tool:WebFetch"]

    ## AND THE CASE THAT WAS DELIBERATELY RELEASED (gh#354). `Edit` used to be denied for
    ## both arms and asserted here as `tool:Edit`. The owner's reframe allows it — an arm
    ## that cannot write cannot answer the edit-to-queryable question at all — so it must
    ## now be CLEAN on the source arm and a REVIEW finding on the index arm. Asserting both
    ## halves keeps the release deliberate: a future re-denial breaks this test rather than
    ## quietly re-crippling the arm.
    released = bench_arms.audit("src", [("Edit", "{}")])
    assert released["violations"] == [], "the src arm has no denials but the web"
    assert released["review"] == [], "and its own source reads are the method, not a finding"

    flagged = bench_arms.audit("mcp", [("Edit", "{}")])
    assert flagged["violations"] == [], "the index arm may write; it is not fenced out"
    assert flagged["review"] == ["mutation:Edit"], "but a write is flagged for a human"
    assert flagged["audit_clean"] is True, "a review finding must not invalidate the cell"

    ## A bare MCP SERVER entry on the deny list must cover the server's tools WHATEVER the
    ## enumeration says. The probes are deliberately three KINDS: one currently registered
    ## (`lock_roster`), one this repo DELETED in a tool cull (`lock_nestings`, folded into
    ## `lock_roster` in round 3; `sections_in` went the same way earlier), and one that never
    ## existed (`set_target` — it was on the hand-written list for years anyway).
    ## Coverage must not depend on membership, because membership is what kept being wrong.
    for tool in ("lock_roster", "lock_nestings", "sections_in", "set_target"):
        name = bench_arms.MCP_TOOL_PREFIX + tool
        assert bench_arms.classify_tool("src", name) == f"tool:{name}", tool
        assert bench_arms.classify_tool("mcp", name) is None, f"{tool} is the mcp arm's job"

    ## And the enumeration must now agree with the served surface rather than drift from it.
    assert "sections_in" not in bench_arms.MCP_TOOLS, "a deleted tool must leave the list"

    ## ASSERTED AGAINST THE DESCRIPTIONS ON DISK, not against a list typed here — and the
    ## previous version of this line is why. It named `{dossier, graph_stats, kconfig,
    ## status}`, which the four-tool collapse folded into `index(action=)`,
    ## `search(corpus=)` and `dossier`, so the assertion went stale the moment the surface
    ## changed. `MCP_TOOLS` is already DERIVED from `load_descriptions`, so re-typing the
    ## membership here reintroduced exactly the drift this test exists to catch, one level up.
    ##
    ## It went unnoticed because `acceptance/bench/` is NOT covered by the pre-commit pytest
    ## hook (`pytest tests/`), so nothing ran it — see the module docstring.
    served = {
        path.stem
        for path in (Path(bench_arms.__file__).parent.parent.parent).glob(
            "clew/mcp_server/descriptions/*.json"
        )
    }
    assert served, "the description directory moved; this probe is measuring nothing"
    assert served <= set(bench_arms.MCP_TOOLS), (
        f"served but not enumerated: {sorted(served - set(bench_arms.MCP_TOOLS))}"
    )


## @brief A foreign MCP server is an unaudited oracle, in either arm.
## @return None.
## @version 1
def test_a_foreign_mcp_server_is_an_isolation_break() -> None:
    """A real attempt exists in the 0.5.0 source-arm evidence: a cell called
    `mcp__entropic__ask` — a different server that answers questions about the very repo
    under test. It came back an error, so nothing was contaminated, and the audit would
    not have told anyone either way: its only MCP check was our own server's prefix.

    An off-transcript oracle is the same defect as a sub-agent, so it gets the same
    severity. Matched by "any `mcp__` that is not ours" rather than a list of known
    foreign servers, because the one that matters is the one not anticipated.

    @brief Any non-clew MCP tool violates, whatever server it belongs to.
    @version 1
    """
    for arm in ("src", "mcp"):
        result = bench_arms.audit(arm, [("mcp__entropic__ask", '{"question":"x"}')])
        assert result["violations"] == ["foreign_mcp:mcp__entropic__ask"], arm
        assert result["audit_clean"] is False, arm

    ## A TYPO'd form of our OWN server is foreign too — one cell called
    ## `mcp__doxyguare-db__dossier`. It cannot have returned index data, and treating a
    ## near-miss as ours would let a real foreign server hide behind a similar name.
    typo = "mcp__doxyguare-db__dossier"
    assert bench_arms.classify_tool("mcp", typo) == f"foreign_mcp:{typo}"

    ## And our own server is still clean in the arm entitled to it.
    assert bench_arms.classify_tool("mcp", bench_arms.MCP_TOOL_PREFIX + "dossier") is None


## @brief Re-auditing preserved evidence re-derives verdicts and never writes.
## @return None.
## @version 1
def test_reaudit_rederives_a_verdict_from_a_preserved_transcript(tmp_path: Path) -> None:
    """Transcripts are preserved so a verdict can be re-derived when the checker changes.
    Trusting a recorded `audit_clean` produced by the weaker classifier is how a wrong
    verdict survives the fix to the thing that made it wrong.

    @brief reaudit reads the arm from the cell name and reports per cell.
    @version 1
    """
    history = tmp_path / "history"
    history.mkdir()
    for cell, tool in (("Q1_opus_src_r1", "TaskDelegate"), ("Q2_opus_mcp_r1", "TaskCreate")):
        line = {"message": {"content": [{"type": "tool_use", "id": "x", "name": tool}]}}
        (history / f"{cell}.transcript.jsonl").write_text(json.dumps(line), encoding="utf-8")
    ## No arm in the name — must be skipped, not guessed at.
    (history / "notes.transcript.jsonl").write_text("{}", encoding="utf-8")

    before = sorted(p.name for p in history.iterdir())
    rows = {cell: (arm, result) for cell, arm, result in bench_arms.reaudit(tmp_path)}
    assert set(rows) == {"Q1_opus_src_r1", "Q2_opus_mcp_r1"}, "arm-less names are skipped"
    assert rows["Q1_opus_src_r1"] == ("src", rows["Q1_opus_src_r1"][1])
    assert rows["Q1_opus_src_r1"][1]["violations"] == ["spawn:TaskDelegate"]
    assert rows["Q2_opus_mcp_r1"][1]["audit_clean"] is True
    assert rows["Q2_opus_mcp_r1"][1]["unlisted_tools"] == ["TaskCreate"]
    assert sorted(p.name for p in history.iterdir()) == before, "re-audit must not write"


## @brief The fencing summary counts fenced MARKS.
## @param tmp_path pytest temp dir.
## @version 2
def test_fencing_summary_counts_fenced_marks(tmp_path: Path) -> None:
    """THE COUNTER READ THE WRONG COLLECTION. `cmd_rubric` computed its "arm-fenced"
    figure over `rubric.bonus` alone, so a rubric whose every MARK was fenced printed
    `0 arm-fenced` provided no bonus item was — the label said the opposite of what was
    measured.

    THE BONUS AND AUTO-FAIL TIERS ARE GONE (owner: both were retired as concepts), so this
    test was left RED by that removal — `rubric.bonus` no longer exists. It went unnoticed
    because `acceptance/bench/` is deliberately outside the pre-commit pytest hook: these are
    pre-acceptance harness tests, not source tests, and nothing runs them on a commit. The
    original defect is still worth covering, so the bonus half is deleted rather than the
    test: what remains asserts the counter reads MARKS, which is the collection it got wrong.

    Fencing decides whether a two-arm comparison is fair: a fenced mark is dropped from
    the denominator of the arm that cannot reach it. So "0 arm-fenced" is exactly the
    line someone quotes as evidence that a rubric is comparable across arms, and it was
    quoted that way in this repository while a rubric was being rewritten specifically
    to remove fencing. The conclusion happened to be right because a separate grep did
    the real work; the parse output contributed nothing and looked like confirmation.

    The fixture is the case the old code got wrong and no test covered: a fenced MARK
    and an unfenced bonus. Counting them separately is deliberate — a blended number
    would invite the same misreading in the other direction, since a fenced mark and a
    fenced bonus item mean different things to a score.

    @brief A fenced mark is reported even when no bonus item is fenced.
    @version 1
    """
    rubric_text = "\n".join(
        [
            "# Q1 — a question",
            "",
            "### Marks (2)",
            "",
            "- ☐ an ordinary mark anyone can reach",
            "- ☐ a mark only one arm can reach [db-arm-only]",
        ]
    )
    path = tmp_path / "questions.md"
    path.write_text(rubric_text, encoding="utf-8")

    rubric = bench_rubric.parse_rubric(path)["Q1"]

    ## Both halves, because a counter that reported EVERY mark as fenced would also satisfy
    ## "1 fenced mark" — the original bug was reading the wrong collection, and only the
    ## unfenced mark's absence from the count distinguishes reading the right one.
    assert sum(1 for m in rubric.marks if m.arm_only) == 1, "the parser must see the fence"
    assert len(rubric.marks) == 2, "and must not lose the unfenced mark"

    summary = grade_matrix.fencing_summary(rubric)
    assert "1 fenced mark" in summary, f"a fenced mark must be reported: {summary!r}"


## @brief Compose a transcript exercising one target-stamp scenario.
## @param path Where to write it.
## @param stamps Target values the index replies carry; None writes a reply with no stamp.
## @return None.
## @version 1
def _stamped_transcript(path: Path, stamps: list[str | None]) -> None:
    """@brief Write a synthetic transcript with index replies carrying target stamps.
    @version 1
    """
    lines = []
    for i, stamp in enumerate(stamps):
        tid = f"toolu_{i}"
        use = {"type": "tool_use", "id": tid, "name": "mcp__clew__dossier", "input": {}}
        lines.append(json.dumps({"message": {"content": [use]}}))
        payload: dict = {"found": True}
        if stamp is not None:
            payload["target"] = stamp
        result = {"type": "tool_result", "tool_use_id": tid,
                  "content": [{"type": "text", "text": json.dumps(payload)}]}  # fmt: skip
        lines.append(json.dumps({"message": {"content": [result]}}))
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


## @brief A cell whose index answered about another repository is VOID, not low-scoring.
## @param tmp_path Pytest scratch directory.
## @return None.
## @version 1
def test_wrong_repository_is_void(tmp_path: Path) -> None:
    """THE OWNER'S HARD GATE, and the case that already cost this project a 36-cell grid: an
    arm answered from a self-index while every question asked about a C++ engine, 15 of 18
    cells said so in prose, and all 36 recorded valid=True because every validity term
    verified the agent CALLED database tools and none verified WHICH repository answered.

    Structural, not prose: the comparison is against the `target` field the server stamps on
    every reply, so an agent cannot phrase around it. A prose version of this check was
    measured at 4 of 15 real cases with a false positive on a source-arm cell, and dropped.

    @brief Pin the void verdict for a foreign-repository reply.
    @version 1
    """
    right, wrong = tmp_path / "right", tmp_path / "wrong"
    right.mkdir()
    wrong.mkdir()
    transcript = tmp_path / "t.jsonl"

    _stamped_transcript(transcript, [str(right)])
    assert target_check.verify("mcp", transcript, right)["status"] == target_check.OK

    _stamped_transcript(transcript, [str(wrong)])
    assert target_check.verify("mcp", transcript, right)["status"] == target_check.VOID

    ## ONE foreign reply is enough. An answer assembled partly from another repository is not
    ## partly correct — no grade can separate the halves.
    _stamped_transcript(transcript, [str(right), str(wrong)])
    assert target_check.verify("mcp", transcript, right)["status"] == target_check.VOID


## @brief "Could not check" never shares a spelling with "checked and fine".
## @param tmp_path Pytest scratch directory.
## @return None.
## @version 1
def test_unverifiable_target_is_unchecked_not_ok(tmp_path: Path) -> None:
    """The negative half, written because the positive half alone would pass with a gate that
    returns OK by default. Three ways the provenance can be unreadable, and all three must
    report UNCHECKED — this repo's recurring failure is a check that cannot read its input
    reporting nothing, which is indistinguishable from passing.

    The source arm is `n/a` rather than `ok`: it was never subject to the check.

    @brief Pin unchecked for every unreadable case.
    @version 1
    """
    target = tmp_path / "right"
    target.mkdir()
    transcript = tmp_path / "t.jsonl"

    _stamped_transcript(transcript, [None])
    assert target_check.verify("mcp", transcript, target)["status"] == target_check.UNCHECKED

    _stamped_transcript(transcript, [])
    assert target_check.verify("mcp", transcript, target)["status"] == target_check.UNCHECKED

    assert target_check.verify("mcp", None, target)["status"] == target_check.UNCHECKED
    assert target_check.verify("src", None, target)["status"] == target_check.NOT_APPLICABLE


## @brief A void cell is excluded from grading AND named, never silently dropped.
## @param tmp_path Pytest scratch directory.
## @return None.
## @version 1
def test_void_cells_are_excluded_and_named(tmp_path: Path) -> None:
    """Excluding without naming is the failure this project shipped when 102 unruled marks
    were scored as substantive: a cell removed from an average has to be counted somewhere a
    reader can see it. And a run directory written before the column existed reads UNCHECKED,
    because absence of a measurement is not a clean measurement.

    @brief Pin grader exclusion and the legacy-run report.
    @version 1
    """
    header = "q,arm,target_ok,valid,answer_path\n"
    run = tmp_path / "run"
    run.mkdir()
    (run / "metrics.csv").write_text(
        header + "Q1,mcp,ok,True,Q1_haiku_mcp_r1.md\n" + "Q2,mcp,void,True,Q2_haiku_mcp_r1.md\n",
        encoding="utf-8",
    )
    for name in ("Q1_haiku_mcp_r1.md", "Q2_haiku_mcp_r1.md"):
        (run / name).write_text("# a\n", encoding="utf-8")

    assert target_check.records_target_column(run)
    assert sorted(target_check.void_cells(run)) == ["Q2_haiku_mcp_r1"]
    assert {c["q"] for c in grade_matrix.list_cells(run)} == {"Q1"}

    legacy = tmp_path / "legacy"
    legacy.mkdir()
    (legacy / "metrics.csv").write_text("q,arm,valid\nQ1,mcp,True\n", encoding="utf-8")
    (legacy / "Q1_haiku_mcp_r1.md").write_text("# a\n", encoding="utf-8")
    assert not target_check.records_target_column(legacy)
    ## Unchecked runs are still graded — the note says so; it does not delete the data.
    assert {c["q"] for c in grade_matrix.list_cells(legacy)} == {"Q1"}


## @brief Write a transcript of one index tool call with a hand-shaped reply payload.
## @param path Transcript path.
## @param tool Tool name without the `mcp__clew__` prefix.
## @param payload The reply payload, verbatim.
## @return None.
## @version 1
def _tool_transcript(path: Path, tool: str, payload: dict) -> None:
    """Distinct from `_stamped_transcript`, which always writes a `dossier` reply keyed on
    `target`. This one takes the payload whole, so a test can assert against the shape a
    SPECIFIC tool really emits rather than against the shape the check happens to read.

    @brief Emit a two-event transcript for one named index tool.
    @version 1
    """
    use = {"type": "tool_use", "id": "toolu_0", "name": f"mcp__clew__{tool}", "input": {}}
    result = {"type": "tool_result", "tool_use_id": "toolu_0",
              "content": [{"type": "text", "text": json.dumps(payload)}]}  # fmt: skip
    path.write_text(
        json.dumps({"message": {"content": [use]}})
        + "\n"
        + json.dumps({"message": {"content": [result]}})
        + "\n",
        encoding="utf-8",
    )


## @brief `status` names its repository under `repo_path`, and the gate must read it.
## @param tmp_path Pytest scratch directory.
## @return None.
## @version 1
def test_status_reply_stamp_is_read_and_list_targets_is_not(tmp_path: Path) -> None:
    """THE GAP A CONTROL FOUND, and the reason the control was built before the gate was
    believed. Reading only `target` made the check blind to `status` — the ONE tool a bringup
    or Q0 cell calls first — because `status` returns a `db_status()` record whose repository
    key is `repo_path`. A synthetic cell whose only index call was a `status` reply naming the
    WRONG repository came back `unchecked`, which is the spelling for "could not look". The
    owner's hard-gate case was being silently downgraded to the one verdict that means nothing.

    Both payload shapes below are copied from live replies at build 30, not invented:
      `status` -> {"repo_path": "…", "active": true, …}      (carries no `target` key)
      `list_targets` -> {"result": [{"repo_path": "…"}, …]}  (carries neither, at top level)

    THE `list_targets` HALF IS THE LOAD-BEARING ONE. The registry legitimately holds foreign
    repositories, so the obvious generalisation — scan the payload for any absolute path — voids
    every cell that merely looked at the registry. That is the "guard that fires on some of the
    real cases" failure in its other direction: a false positive on a correct cell. Reading the
    two keys at TOP LEVEL ONLY is what makes the check safe, and this assertion is what pins it.

    @brief Pin the status stamp as read and the registry listing as not a false positive.
    @version 1
    """
    right, wrong = tmp_path / "right", tmp_path / "wrong"
    right.mkdir()
    wrong.mkdir()
    transcript = tmp_path / "t.jsonl"

    _tool_transcript(transcript, "status", {"repo_path": str(right), "active": True})
    assert target_check.verify("mcp", transcript, right)["status"] == target_check.OK

    _tool_transcript(transcript, "status", {"repo_path": str(wrong), "active": True})
    assert target_check.verify("mcp", transcript, right)["status"] == target_check.VOID

    ## The registry listing names other repositories BY DESIGN. Not void, not ok — it carries
    ## no top-level stamp, so it is simply not an observation.
    _tool_transcript(
        transcript, "list_targets", {"result": [{"repo_path": str(wrong)}, {"repo_path": str(right)}]}
    )  # fmt: skip
    assert target_check.verify("mcp", transcript, right)["status"] == target_check.UNCHECKED


## @brief The report's fencing section must see a fenced MARK, not only a fenced bonus item.
## @param tmp_path Pytest scratch directory.
## @return None.
## @version 1
def test_report_fencing_section_sees_a_fenced_mark(tmp_path: Path) -> None:
    """THE SAME WRONG-COLLECTION BUG `fencing_summary` WAS FIXED FOR, still live in the report
    one layer down. `build_report` iterated `grade["bonus"]` alone, so a run whose fenced items
    were all MARKS — the normal case; the committed rubrics fence marks and no bonus at all —
    printed "none in the graded questions" under a heading about arm fencing.

    That line is not decoration. Fencing decides whether a two-arm comparison is fair, and
    "none" is precisely the sentence someone quotes as evidence that it was. It has been quoted
    that way in this project before, while a rubric was being rewritten to remove fencing.

    The sidecar below is a WIDER shape than `grade_answer` writes — it carries `bonus`,
    `bonus_summary` and `auto_fail`, which the grader does not — with the fence on a MARK and
    the bonus list deliberately clean, the control the original code would have passed.

    This docstring used to claim the fixture WAS what `grade_answer` writes. That stopped being
    true, and the false claim is what kept a live defect invisible: the report subscripted
    `g["bonus"]` bare and raised KeyError on every real sidecar, while this test passed because
    its fixture had been built to match the reader. See
    `test_the_report_reads_the_sidecar_the_grader_actually_writes` for the narrow control.

    @brief Pin that a fenced mark reaches the report.
    @version 1
    """
    from grade_report import build_report

    sidecar = {
        "q": "Q1", "arm": "src", "model": "haiku", "run": 1,
        "answer": "Q1_haiku_src_r1.md", "rubric": "r.md", "declared_mark_count": 1,
        "summary": {"score": 0.0, "marks_total": 0, "marks_hit": 0,
                    "marks_miss": 0, "judge_errors": 0, "marks_fenced_out": 1,
                    "unmarked_pct": 0.0, "score_strict": 0.0},
        "bonus_summary": {"score": 0.0, "marks_total": 0, "marks_hit": 0,
                          "marks_miss": 0, "judge_errors": 0, "marks_fenced_out": 0,
                          "unmarked_pct": 0.0, "score_strict": 0.0},
        "auto_fail": {"defined": False},
        "marks": [{"index": 1, "kind": "mark", "text": "t", "double": False,
                   "arm_only": "db", "conceptual": True, "judge": None, "verdict": "MISS"}],
        "bonus": [],
    }  # fmt: skip
    (tmp_path / "Q1_haiku_src_r1.grade.json").write_text(json.dumps(sidecar), encoding="utf-8")

    report = build_report(tmp_path)
    assert "mark #1 is db-arm-only" in report, f"a fenced MARK must be named:\n{report}"
    assert "none in the graded questions" not in report, f"and must not read as clean:\n{report}"


## @brief The runner's own report must exclude a void cell from its means and name it.
## @param tmp_path Pytest scratch directory.
## @param capsys Pytest stdout capture.
## @return None.
## @version 1
def test_runner_report_excludes_void_cells_from_the_means(tmp_path: Path, capsys) -> None:
    """A VOID CELL IS RECORDED `valid=True` ON PURPOSE — `target_ok` is a separate column so a
    void cell is not buried inside the invalid count — and this report filtered on `valid`
    alone. Every void cell's tokens and wall time were therefore landing in the means an
    operator reads first, straight after a sweep.

    That is the retracted headline's mechanism exactly: a cell that discovers the wrong
    repository and bails costs a fraction of a working one, so averaging bail-outs makes the arm
    that bailed look efficient. The grader and the tier report both exclude void cells; this one
    did not.

    THE CONTROL IS THE NUMBER, NOT THE PRESENCE OF A WARNING. The void row below carries 10
    tokens against the good row's 1,000, so a mean of 1,000 proves the exclusion and a mean of
    505 proves it silently failed — a prose-only assertion would pass either way.

    @brief Pin void exclusion and naming in the runner's report.
    @version 1
    """
    import run_matrix

    out = tmp_path / "run"
    out.mkdir()
    header = ",".join(run_matrix.CSV_FIELDS)

    def row(q: str, ok: str, tokens: int) -> str:
        values = {f: "" for f in run_matrix.CSV_FIELDS}
        values.update(
            target="t", q=q, arm="mcp", model="haiku", run="1",
            tokens_in=str(tokens), tokens_out="0", cache_read="0", cache_creation="0",
            total_tokens=str(tokens), tool_uses="1", num_turns="1", duration_ms="100",
            build_ms="", cost_usd="0.0", used_db_tools="1", audit_clean="True",
            target_ok=ok, valid="True", answer_path=f"{q}_haiku_mcp_r1.md",
        )  # fmt: skip
        return ",".join(values[f] for f in run_matrix.CSV_FIELDS)

    (out / "metrics.csv").write_text(
        "\n".join([header, row("Q1", "ok", 1000), row("Q2", "void", 10)]) + "\n",
        encoding="utf-8",
    )
    assert run_matrix.cmd_report(SimpleNamespace(out=str(out))) == 0
    report = (out / "report.md").read_text(encoding="utf-8")

    assert "1 VOID cell(s) EXCLUDED" in report, f"a void cell must be named:\n{report}"
    assert "Q2/mcp/haiku/r1" in report, f"and named by its coordinates:\n{report}"
    ## THE AGGREGATE ROW, MATCHED WHOLE — and the first version of this assertion did not, which
    ## a mutation control caught. `"| 1 | 1000 |"` also appears in the PER-CELL table (run 1,
    ## 1000 tokens), so the test passed with the exclusion deleted: green for the wrong reason,
    ## in a test written specifically to catch a silent inclusion. Anchor on `arm | model` so
    ## only the aggregate can satisfy it, and assert the wrong answer's absence as well.
    assert "| mcp | haiku | 1 | 1000 |" in report, (
        f"the void cell must not reach the mean:\n{report}"
    )
    assert "| mcp | haiku | 2 | 505 |" not in report, f"the void cell WAS averaged in:\n{report}"

    ## THE THIRD STATE. A run written before the column existed must say UNCHECKED — silence
    ## there would let "not measured" read as "measured and clean", which is the substitution
    ## behind the disarmed coverage gate and the identifier leak both.
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    fields = [f for f in run_matrix.CSV_FIELDS if f != "target_ok"]
    kept = [v for f, v in zip(run_matrix.CSV_FIELDS, row("Q1", "ok", 1000).split(","), strict=True)
            if f != "target_ok"]  # fmt: skip
    (legacy / "metrics.csv").write_text(
        ",".join(fields) + "\n" + ",".join(kept) + "\n", encoding="utf-8"
    )
    assert run_matrix.cmd_report(SimpleNamespace(out=str(legacy))) == 0
    legacy_report = (legacy / "report.md").read_text(encoding="utf-8")
    assert "UNCHECKED for target correctness" in legacy_report, legacy_report
    capsys.readouterr()


## @brief The report carries review_count as a WORST case, and skips unmeasured rows.
## @return None.
## @version 1
def test_the_report_carries_the_worst_review_count_not_the_mean(tmp_path: Path, capsys) -> None:
    """COLLECTED SINCE THE FIRST SWEEP AND NEVER REPORTED, so nobody read it: the index arm's
    per-question figures were Q1 0, Q2 2, and one Q2 cell at SEVEN. Seven is the number that
    matters — one useless response resets the preference for the rest of a context window — and
    it is exactly the number a mean erases.

    THE CONTROL IS THAT 7 SURVIVES AND 3.5 DOES NOT. Two cells at 0 and 7 average to 3.5, so a
    report showing 3.5 proves the aggregate is a mean and a report showing 7 proves it is a
    worst case; asserting only that "7 appears somewhere" would pass on the per-cell table
    alone, which is the mistake a mutation control caught in the void-exclusion test above.

    THE THIRD ROW IS UNMEASURED (-1, written when no transcript was found). It must be skipped
    rather than counted as clean: folding "we could not look" into "we looked and it was fine"
    is the substitution behind the disarmed coverage gate.

    @brief Pin the worst-case reporting of review_count.
    @version 1
    """
    import run_matrix

    out = tmp_path / "run"
    out.mkdir()

    def row(q: str, reviews: int) -> str:
        values = {f: "" for f in run_matrix.CSV_FIELDS}
        values.update(
            target="t", q=q, arm="mcp", model="haiku", run="1",
            tokens_in="1000", tokens_out="0", cache_read="0", cache_creation="0",
            total_tokens="1000", tool_uses="1", num_turns="1", duration_ms="100",
            build_ms="", cost_usd="0.0", used_db_tools="1", audit_clean="True",
            review_count=str(reviews), target_ok="ok", valid="True",
            answer_path=f"{q}_haiku_mcp_r1.md",
        )  # fmt: skip
        return ",".join(values[f] for f in run_matrix.CSV_FIELDS)

    (out / "metrics.csv").write_text(
        "\n".join([",".join(run_matrix.CSV_FIELDS), row("Q1", 0), row("Q2", 7), row("Q3", -1)])
        + "\n",
        encoding="utf-8",
    )
    assert run_matrix.cmd_report(SimpleNamespace(out=str(out))) == 0
    report = (out / "report.md").read_text(encoding="utf-8")

    assert "worst review" in report, f"the column must be labelled as a worst case:\n{report}"
    ## ANCHORED ON THE AGGREGATE ROW ITSELF, found by its `arm | model | n` prefix, so the
    ## per-cell table cannot satisfy it — the mistake a mutation control caught in the
    ## void-exclusion test above. Deliberately NOT `report.endswith(...)`: that version broke
    ## the moment a later section was appended, which would have read as a regression in the
    ## column rather than in the assertion.
    aggregate = [ln for ln in report.splitlines() if ln.startswith("| mcp | haiku | 3 |")]
    assert len(aggregate) == 1, f"one aggregate row over three valid non-void cells:\n{report}"
    assert aggregate[0].rstrip().endswith("| 7 |"), (
        f"the aggregate's last column must be the WORST review count, not a mean: {aggregate[0]}"
    )
    assert "| 3.5 |" not in report and "| 2.3 |" not in report, (
        f"review_count was averaged — worst case is the whole point of reporting it:\n{report}"
    )
    ## The bringup section says UNMEASURED rather than going missing: no cell here built
    ## anything, and silence would read as "bringup was free".
    assert "## Bringup cost" in report and "NOT MEASURED" in report, report
    ## And the unmeasured row did not become a zero: `_worst` reads it directly.
    assert run_matrix._worst([{"review_count": "-1"}], "review_count") == -1
    assert run_matrix._worst([{"review_count": "-1"}, {"review_count": "2"}], "review_count") == 2
    capsys.readouterr()


## @brief A cell whose every mark is fenced off its arm is never scheduled.
## @return None.
## @version 1
def test_a_fully_fenced_question_is_not_scheduled_for_that_arm(tmp_path: Path, capsys) -> None:
    """AGAINST THE COMMITTED mbedtls RUBRIC, not a fixture, because the defect is a property of a
    real key: Q0's nine marks all carry `[db-arm-only]`, so `--arm both` scheduled a source-arm Q0
    cell that spends a full cell of session capacity to be graded against zero marks.

    IT WAS INVISIBLE BECAUSE THE SCORE WAS RIGHT. Fencing already worked at the mark level —
    excluded, never scored zero — so nothing in the completeness axis complained. What leaked was
    COST: the cell's tokens and wall time joined the source arm's aggregate means, skewing a
    comparison with a question that is never compared. The plan listed this as a check to verify;
    it was a live defect.

    THE FAIL-OPEN HALF IS ASSERTED TOO. A question the rubric parsed no marks for must still be
    scheduled: `parse_rubric` returns nothing for a heading it cannot match, and treating that as
    "fenced" would silently shrink the grid, which is strictly worse than paying for a cell.
    Without this half the feature could be implemented as "skip anything the rubric is quiet
    about" and every test above would still pass.

    @brief Fully-fenced cells are dropped, unparsed ones are kept.
    @version 1
    """
    import run_matrix

    rubric = bench_rubric.REPO_ROOT / "acceptance" / "targets" / "mbedtls" / "questions.yaml"
    opts = SimpleNamespace(
        questions=str(rubric), questions_filter="Q0,Q1", arm="both", model=["haiku"], runs=1
    )
    cells = {(q["id"], arm) for q, arm, _model, _run in run_matrix.plan_cells(opts)}
    assert ("Q0", "src") not in cells, (
        "a source-arm Q0 cell is graded against zero marks and its cost joins the src means"
    )
    assert ("Q0", "mcp") in cells, "Q0 is the index arm's question — dropping it drops the exam"
    assert {("Q1", "src"), ("Q1", "mcp")} <= cells, (
        "Q1 has unfenced marks, so both arms must still run it — a skip that also caught Q1 "
        "would be a guard firing on the ordinary case"
    )
    assert "skipping Q0/src" in capsys.readouterr().out, (
        "a dropped cell must be named: silent truncation reads as 'covered everything'"
    )

    ## FAIL OPEN on a question the rubric parses no marks for.
    quiet = tmp_path / "quiet.md"
    quiet.write_text(
        "<!-- x -->\n---\nrubric: t\nground_truth_source: source\n---\n\n"
        "# Q1 — a question with no marks section\n\n"
        ## The trailing prose line is load-bearing: `parse_questions` closes a blockquote on the
        ## first NON-`>` line, so a file ending at the quote yields a question with empty text
        ## that the parser then drops — and the assertion below would read as a wrongly-skipped
        ## cell rather than a malformed fixture.
        "> **Question (frozen).** What is here?\n\nno marks follow.\n",
        encoding="utf-8",
    )
    opts_quiet = SimpleNamespace(
        questions=str(quiet), questions_filter="", arm="both", model=["haiku"], runs=1
    )
    quiet_cells = {(q["id"], arm) for q, arm, _model, _run in run_matrix.plan_cells(opts_quiet)}
    assert quiet_cells == {("Q1", "src"), ("Q1", "mcp")}, (
        f"an unparsed rubric must not shrink the grid — that is a parse problem, not a fence: "
        f"{quiet_cells}"
    )
    capsys.readouterr()


## @brief A measured bringup cost is reported, and never inside the comparison means.
## @return None.
## @version 1
def test_bringup_cost_is_reported_separately_from_the_means(tmp_path: Path, capsys) -> None:
    """THE SUCCESS PATH OF `_bringup_note`, written because the sibling test above only covers
    the UNMEASURED branch — a suite that exercises one branch of a two-branch report passes
    against a section that can never print a number, which is the shape this repo recorded as "a
    check with a test for its failure path and none for its success path".

    TWO PROPERTIES, and the second is the owner's ruling (gh#360): the figures APPEAR, and they
    stay OUT of the aggregate means. Q1 here builds for 20,000 ms and Q2 builds nothing; if
    bringup were folded into the comparison the two cells' means would diverge on a cost that is
    paid once per (tool version, index version, repo@sha) and reused by every later cell.

    @brief Pin the measured bringup section and its exclusion from the means.
    @version 1
    """
    import run_matrix

    out = tmp_path / "run"
    out.mkdir()

    def row(q: str, build: str, bringup: str) -> str:
        values = {f: "" for f in run_matrix.CSV_FIELDS}
        values.update(
            target="t", q=q, arm="mcp", model="haiku", run="1",
            tokens_in="1000", tokens_out="0", cache_read="0", cache_creation="0",
            total_tokens="1000", tool_uses="1", num_turns="1", duration_ms="100",
            build_ms=build, bringup_ms=bringup, cost_usd="0.0", used_db_tools="1",
            audit_clean="True", review_count="0", target_ok="ok", valid="True",
            answer_path=f"{q}_haiku_mcp_r1.md",
        )  # fmt: skip
        return ",".join(values[f] for f in run_matrix.CSV_FIELDS)

    (out / "metrics.csv").write_text(
        "\n".join([",".join(run_matrix.CSV_FIELDS), row("Q1", "20000", "31000"), row("Q2", "", "")])
        + "\n",
        encoding="utf-8",
    )
    assert run_matrix.cmd_report(SimpleNamespace(out=str(out))) == 0
    report = (out / "report.md").read_text(encoding="utf-8")

    assert "## Bringup cost (EXCLUDED from every mean above)" in report, report
    assert "| Q1 | mcp | haiku | 1 | 20000 | 31000 |" in report, (
        f"both figures must be reported, and separately — a refresh cost and a stand-up cost "
        f"answer different questions:\n{report}"
    )
    assert "| Q2 |" not in report.split("## Bringup cost")[1], (
        "a cell that built nothing has no bringup row — an empty figure is not a zero"
    )
    ## THE EXCLUSION. `duration_ms` is 100 for both cells, so a mean of 100 proves bringup was
    ## not folded into wall time, and any larger figure proves it was.
    aggregate = [ln for ln in report.splitlines() if ln.startswith("| mcp | haiku | 2 |")]
    assert len(aggregate) == 1, report
    assert "| 100 |" in aggregate[0], (
        f"bringup leaked into the wall-time mean — the axis exists to keep them apart: "
        f"{aggregate[0]}"
    )
    assert "20000" not in aggregate[0] and "31000" not in aggregate[0], aggregate[0]
    capsys.readouterr()


## @brief Both arms are given the SAME output contract, byte for byte.
## @return None.
## @version 1
def test_the_two_briefs_state_the_same_output_contract() -> None:
    """ANYTHING THE INDEX ARM IS TOLD THAT THE SOURCE ARM IS NOT IS A HANDICAP BUILT INTO THE
    HARNESS. The two briefs must differ on exactly one thing — which tools the arm has, which is
    the arm's definition — and agree on everything else. The index brief was 2,136 B against the
    source arm's 768 before this campaign, carrying a build-the-index mandate, a currency check,
    a repository-verification paragraph and meta-commentary about its own tool list, none of
    which the source arm was asked to do and none of which was true at cell time.

    THE LAST ASYMMETRY WAS THE GAPS HEADING. The index brief asked for `## Index gaps` where the
    source brief asked for `## Gaps` — the same request under a name that primes attribution to
    the index, in a section the judge reads. It is now the same heading in both, and the gaps an
    arm actually hit are captured mechanically from the transcript by `fallback_audit`, which an
    agent cannot flatter by manufacturing something to report.

    COMPARED AS TEXT, not as a checklist of remembered differences: the point is to catch the
    NEXT asymmetry, which by definition nobody has thought of.

    @brief The `## Output` sections of both briefs are identical.
    @version 1
    """
    briefs = {
        arm: (Path(__file__).resolve().parent / f"_brief_{arm}.md").read_text(encoding="utf-8")
        for arm in ("src", "mcp")
    }
    outputs = {arm: text.split("## Output", 1)[1] for arm, text in briefs.items()}
    assert outputs["src"] == outputs["mcp"], (
        "the two arms are held to different output contracts, so any quality difference is "
        "partly a difference in what they were asked to produce:\n"
        f"--- src ---{outputs['src']}\n--- mcp ---{outputs['mcp']}"
    )
    assert "Index gaps" not in briefs["mcp"], (
        "the index arm is asked for a differently-named gaps section, which primes attribution "
        "to the index in a section the judge reads"
    )


## @brief The index arm's brief must not forbid tools the harness grants it.
## @return None.
## @version 1
def test_the_index_brief_does_not_contradict_the_arm_policy() -> None:
    """A FOURTH SILENT MOVER OF A HEADLINE FIGURE, measured on run4. gh#354 deliberately gave
    the `mcp` arm the full default toolset — the reframe is "index+grep vs grep", the honest
    real-world question and the harder one to win — while `_brief_mcp.md` still told the agent
    "no `grep`/`rg`/`find`, no `Grep`/`Glob`, no `Bash`".

    A brief that forbids what the policy permits cannot be enforced and is only partly obeyed:
    across six four-tool cells, all three Q1 runs used no forbidden tool and all three Q2 runs
    used exactly one each (`Grep`, `Glob`, `Bash`), every one of them against the same file.
    So the arm's EFFECTIVE toolset varied per cell according to how strictly the model read a
    rule it could not be held to — an uncontrolled variable in both cost and quality, and one
    that flatters the index arm's completeness while inflating its token count.

    The fence that IS real stays asserted: direct database access measures a schema rather
    than the shipped tool, and it is the one prohibition gh#354 did not remove.

    @brief The brief's prohibitions match the arm policy's denials.
    @return None.
    @version 1
    """
    brief = (Path(bench_arms.__file__).parent / "_brief_mcp.md").read_text(encoding="utf-8")
    granted = {"Grep", "Glob", "Bash"}
    assert granted <= set(bench_arms.ARM_POLICY["mcp"][0]), (
        "this test's premise is that the policy GRANTS these; if it no longer does, "
        "the brief may forbid them again and this test is what needs changing"
    )
    for tool in granted:
        assert f"no `{tool}`" not in brief, (
            f"the brief forbids `{tool}` while ARM_POLICY grants it — an unenforceable rule "
            "that some cells obey and others do not"
        )
    ## AND THE REAL LIMIT SURVIVES, or the alignment has become a blanket permission.
    assert "sqlite3" in brief
    assert "clew.db" in brief


## @brief A source read after a CITED file is not the same finding as one beyond it.
## @return None.
## @version 1
def test_fallback_audit_separates_cited_confirmation_from_discovery(tmp_path: Path) -> None:
    """THE DISTINCTION THAT CHANGED THE HEADLINE. The first version of `fallback_audit`
    counted every index-arm source read as a wasted call and reported 48.2% on the measured
    run. But the brief permits `Read` to confirm a line the index has already cited, and 16
    of those 27 reads opened a file the preceding index reply had NAMED. Excluding them gives
    34.2%. A bare source-read count can be argued in either direction from one transcript.

    So the split is asserted rather than trusted: a read of a file the index just cited must
    classify `cited`, and a read of one it never mentioned must classify `beyond`. Both halves
    are here because a rule that only ever said `beyond` would also have "passed" a one-sided
    test — and would have restored the overstatement it exists to remove.

    @brief cited vs beyond discriminates on whether the index named the file.
    @version 1
    """
    prefix = fallback_audit._INDEX_PREFIX
    lines = [
        ## The index names threading.c ...
        {
            "message": {
                "content": [
                    {"type": "tool_use", "id": "a", "name": f"{prefix}dossier", "input": {}},
                ]
            }
        },
        {
            "message": {
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": "a",
                        "content": '{"count":1,"file":"library/threading.c"}',
                    },
                ]
            }
        },
        ## ... so reading THAT file is confirmation the brief allows.
        {
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "b",
                        "name": "Read",
                        "input": {"file_path": "~/t/library/threading.c"},
                    },
                ]
            }
        },
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "b", "content": "..."}]}},
        ## ... while reading a file it never mentioned is discovery beyond the index.
        {
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "id": "c",
                        "name": "Read",
                        "input": {"file_path": "~/t/include/mbedtls/rsa.h"},
                    },
                ]
            }
        },
        {"message": {"content": [{"type": "tool_result", "tool_use_id": "c", "content": "..."}]}},
    ]
    path = tmp_path / "Q1_sonnet_mcp_r1.transcript.jsonl"
    path.write_text("\n".join(json.dumps(x) for x in lines), encoding="utf-8")

    rows = fallback_audit.attribute(fallback_audit.calls(path))
    assert [(tool, seen) for tool, _after, _outcome, seen in rows] == [
        ("Read", "cited"),
        ("Read", "beyond"),
    ]

    ## AND THE REPORT PUBLISHES BOTH NUMBERS, never the larger one alone.
    text = fallback_audit.report(tmp_path)
    assert "1 beyond, 1 cited" in text
    assert "OVERSTATES" in text, "the naive count must be shown as an overstatement"


## @brief A target's declaration is derived from its rubric's own directory.
## @return None.
## @version 1
def test_declaration_is_found_beside_the_rubric_and_absent_is_not_an_error(tmp_path: Path) -> None:
    """BOTH HALVES. A target that declares nothing must still run — most do — so the absent
    case returning None is as load-bearing as the present case returning the path. A version
    that treated absence as an error would refuse every target but this one.
    """
    questions = tmp_path / "questions.md"
    questions.write_text("marks: 0\n", encoding="utf-8")
    assert run_matrix.declaration_for(questions) is None, "absent must be None, not a refusal"

    (tmp_path / "declaration.yaml").write_text("locks:\n  locks: []\n", encoding="utf-8")
    found = run_matrix.declaration_for(questions)
    assert found is not None and found.name == "declaration.yaml"
    assert found.parent == questions.resolve().parent, "it must be the RUBRIC's sibling"


## @brief The per-cell restore rebuilds the index WITH the target's declaration.
## @return None.
## @version 1
def test_restore_target_forwards_the_declaration_to_the_rebuild(
    tmp_path: Path, monkeypatch
) -> None:
    """THE TEST THAT WOULD HAVE CAUGHT THE 2026-08-14 INVALID SPOT CHECK.

    `restore_target` rebuilt the index before every cell and passed no `declare=`, so each
    restore replaced a declared index with an undeclared one. Reproduced deliberately on the
    real target: built with the document, `options.predefined.tier` reads `declared` and
    `scope.vendored_roots` is `3rdparty`; refreshed without it, they read `heuristic` and
    ABSENT while `options.locks.tier` stays `explicit` through replay. That asymmetry is
    exactly the state the graded index was in, and no existing check could see it.

    ASSERTS THE ARGUMENT, not the resulting database. A test that rebuilt and then read
    build_meta would pass on a replayed statement from some earlier declared build — the very
    thing that disguised the defect. The argument is the mechanism; the rows are downstream.
    """
    target = tmp_path / "clone"
    (target / ".git").mkdir(parents=True)
    (target / run_matrix.RESTORE_MARKER).write_text("", encoding="utf-8")
    declaration = tmp_path / "declaration.yaml"
    declaration.write_text("vendored:\n  - 3rdparty\n", encoding="utf-8")

    seen: dict[str, object] = {}

    def fake_build_index(**kwargs):
        seen.update(kwargs)

    monkeypatch.setattr("clew.cli.build_index", fake_build_index)
    monkeypatch.setattr(
        "clew.mcp_server.state.target_for",
        lambda _t: SimpleNamespace(db_path=str(tmp_path / "clew.db")),
    )
    ## `stdout` IS PART OF THE REAL API AND THE FAKE OMITTED IT. `restore_target` now asks git for
    ## `--show-toplevel` and refuses unless it IS the target, so the destructive `git clean -fd`
    ## cannot resolve to another repository — which matters most for an internal target living
    ## inside this one. A stub that returns no stdout was fine while nothing read it and became a
    ## false failure the moment something did; answering with the target's own path keeps this
    ## test about the DECLARATION, which is what it exists to check.
    monkeypatch.setattr(
        run_matrix.subprocess,
        "run",
        lambda *a, **k: SimpleNamespace(returncode=0, stderr="", stdout=str(target)),
    )

    message = run_matrix.restore_target(target, declaration)
    assert seen.get("declare") == declaration, f"the rebuild dropped the declaration: {seen}"
    assert "declaration.yaml" in message, "the run log must say the index was built declared"

    ## AND THE UNDECLARED CASE STILL WORKS — a target with no document must not be forced to
    ## invent one. Written because the fix for the defect above is a new required argument if
    ## nobody checks the other half.
    seen.clear()
    message = run_matrix.restore_target(target, None)
    assert seen.get("declare") is None
    assert "declaration" not in message


## @brief The declaration preflight refuses an index the document never reached.
## @return None.
## @version 1
def test_preflight_declaration_refuses_an_undeclared_index(tmp_path: Path, monkeypatch) -> None:
    """THREE STATES, and the middle one is the defect. An index that RECORDS the document's sha
    passes; one that records nothing is refused naming every section it never saw; one that
    records a DIFFERENT sha is refused too, because that is the document edited after the build
    that stated it — how `vendored` and `preprocessor` went missing while `locks` still read
    `explicit`.
    """
    import sqlite3

    from clew.declaration import stated_document_meta

    declaration = tmp_path / "declaration.yaml"
    declaration.write_text("vendored:\n  - 3rdparty\nlocks:\n  locks: []\n", encoding="utf-8")
    db = tmp_path / "clew.db"
    monkeypatch.setattr(
        "clew.mcp_server.state.target_for",
        lambda _t: SimpleNamespace(db_path=str(db)),
    )

    def stamp(rows: dict[str, str]) -> None:
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE IF NOT EXISTS build_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute("DELETE FROM build_meta")
        conn.executemany("INSERT INTO build_meta(key, value) VALUES(?, ?)", list(rows.items()))
        conn.commit()
        conn.close()

    ## 1. RECORDS NOTHING — the state that invalidated the spot check.
    stamp({"build_version": "47"})
    with pytest.raises(SystemExit) as refusal:
        run_matrix.preflight_declaration_applied(tmp_path, declaration)
    assert "locks" in str(refusal.value) and "vendored" in str(refusal.value), (
        "the refusal must NAME the sections the index never saw — 'it did not apply' sends an "
        "operator to re-read a file that is probably correct"
    )

    ## 2. RECORDS THE RIGHT DOCUMENT — must pass, or the gate refuses every valid run.
    want = stated_document_meta(declaration.read_bytes(), {"vendored": ["3rdparty"], "locks": {}})
    stamp({f"declaration.{k}": v for k, v in want.items()})
    run_matrix.preflight_declaration_applied(tmp_path, declaration)

    ## 3. RECORDS A DIFFERENT DOCUMENT — the document edited since the build.
    stamp({"declaration.stated_sha256": "0" * 64, "declaration.stated_sections": "locks, vendored"})
    with pytest.raises(SystemExit) as refusal:
        run_matrix.preflight_declaration_applied(tmp_path, declaration)
    assert "edited since the build" in str(refusal.value), (
        "a sha mismatch with matching section names is a DIFFERENT failure and must read as one"
    )

    ## 4. A TARGET THAT DECLARES NOTHING is not refused.
    run_matrix.preflight_declaration_applied(tmp_path, None)


## @brief Vote agreement is over samples REQUESTED, so a flaky judge cannot manufacture unanimity.
## @return None.
## @version 1
def test_vote_agreement_does_not_treat_an_ERROR_as_a_concurring_vote(monkeypatch) -> None:
    """THE VETO GOT EASIER TO TRIP THE FLAKIER THE JUDGE BECAME — a live CRITICAL defect, and
    nothing tested `vote` at all.

    `agreement` was `top_n / sum(counts.values())`, i.e. over samples that SURVIVED. One
    CONTRADICTED beside two errored samples therefore returned 1.0, which is exactly
    `grade_matrix.VETO_AGREEMENT`, so D3's veto fired on a single sample and zeroed a whole
    question. Judge flakiness here is caused by exhausting session capacity — the constraint
    that actually binds a sweep — so the failure mode arrived precisely when grading was least
    reliable. `falsity_check`'s docstring already promised "ERRORS DO NOT VETO"; that held only
    when EVERY sample errored, which is the case nobody worries about.

    FOUR STATES, and the last two are what make this two-sided: a genuine unanimous vote must
    still reach 1.0, or the fix would disarm the veto entirely rather than correct it.
    """
    from grade_matrix import VETO_AGREEMENT

    def replies(*seq):
        it = iter(seq)

        def fake_ask(_prompt, model=""):
            return next(it)

        monkeypatch.setattr(bench_judge, "ask", fake_ask)

    ok = bench_judge.JudgeReply(text="VERDICT: CONTRADICTED")
    other = bench_judge.JudgeReply(text="VERDICT: CONSISTENT")
    boom = bench_judge.JudgeReply(error="session limit reached")
    allowed = ("CONTRADICTED", "CONSISTENT")

    ## 1. ONE VOTE, TWO ERRORS — the defect. Must NOT reach the veto threshold.
    replies(ok, boom, boom)
    divided = bench_judge.vote("p", "VERDICT", allowed, n=3)
    assert divided.verdict == "CONTRADICTED", "the one real sample is still reported"
    assert divided.errors == 2
    assert divided.agreement == pytest.approx(1 / 3), f"agreement was {divided.agreement}"
    assert divided.agreement < VETO_AGREEMENT, "a single sample must not be able to veto"

    ## 2. ALL ERRORED — "not checked", never "clean" and never "false".
    replies(boom, boom, boom)
    dead = bench_judge.vote("p", "VERDICT", allowed, n=3)
    assert dead.verdict is None and dead.agreement == 0.0

    ## 3. A GENUINE SPLIT stays below unanimity, as before.
    replies(ok, ok, other)
    split = bench_judge.vote("p", "VERDICT", allowed, n=3)
    assert split.verdict == "CONTRADICTED"
    assert split.agreement == pytest.approx(2 / 3) and split.agreement < VETO_AGREEMENT

    ## 4. UNANIMOUS AND ERROR-FREE still vetoes — without this the fix would be a disarm.
    replies(ok, ok, ok)
    unanimous = bench_judge.vote("p", "VERDICT", allowed, n=3)
    assert unanimous.agreement == pytest.approx(1.0)
    assert unanimous.agreement >= VETO_AGREEMENT, "a real unanimous contradiction must veto"


## @brief A veto that did not run reports UNCHECKED rather than clean, whatever disabled it.
## @return None.
## @version 2
def test_a_veto_that_did_not_run_says_unchecked_rather_than_passing() -> None:
    """THE THIRD STATE, asserted independently of whether the veto is armed. This test used to pin
    `VETO_SAMPLES == 0`, which was the right shape while the constant WAS the decision: nothing
    pinned the armed state in either direction, and flipping it from 3 to 0 left all 56 bench tests
    green — which is how a catastrophic per-question veto came to be armed by default with no test
    naming that choice.

    The arming decision now lives in `test_the_veto_is_armed_and_fed_only_veto_safe_marks`, together
    with the SELECTION that made arming defensible. What survives here is the part that does not
    depend on the constant: a pass that did not run must read as "unchecked", never as "clean" —
    whether it was skipped for samples or refused on an empty fact list. Converting unchecked into
    checked-and-fine is how the identifier leak, the disarmed coverage gate and a whole invalid grid
    all shipped.

    @brief An unrun veto is a third state, not a pass.
    @version 2
    """
    assert grade_matrix.falsity_check(["some fact"], "body", "sonnet", 0) is None, (
        "zero samples must not run the pass"
    )
    assert grade_matrix.falsity_check([], "body", "sonnet", 3) is None, (
        "an empty fact list must refuse rather than vote on nothing and report agreement"
    )

    summary = summarise([{"index": 1, "verdict": "HIT", "arm_only": ""}], "mcp", None)
    assert summary["falsity_checked"] is None, (
        "a disarmed pass must be a THIRD state; False would read as 'ran and found nothing'"
    )
    assert summary["quality_vetoed"] is False


## @brief An unmeasured cell must not print the BEST value on the owner's headline metric.
## @return None.
## @version 1
def test_non_index_tool_count_reports_unmeasured_rather_than_zero() -> None:
    """`run_matrix` records `tool_uses: -1` and `used_db_tools: -1` for a cell whose transcript
    could not be found, and the subtraction turned that pair into `0` — so the cell with NO
    EVIDENCE AT ALL printed zero fallbacks, which is the best possible value on the one metric
    the owner asked for as a smell check, and the lever the whole re-run is aimed at.

    The guard is STRUCTURAL rather than a comparison against -1: a tool-call count cannot be
    negative, so either operand being negative means the audit did not happen, whatever value
    happens to stand for that.
    """
    assert grade_report._non_index_tools({"tool_uses": "13", "used_db_tools": "3"}) == "10"
    assert grade_report._non_index_tools({"tool_uses": "-1", "used_db_tools": "-1"}) == "-", (
        "a missing transcript must read as unmeasured, never as a perfect score"
    )
    assert grade_report._non_index_tools({"tool_uses": "5"}) == "-"
    ## A real zero is still a zero — the fix must not hide the genuinely clean cell, which is
    ## the result the hypothesis predicts and Q1 actually produced.
    assert grade_report._non_index_tools({"tool_uses": "3", "used_db_tools": "3"}) == "0"


## @brief A divided CONTRADICTED is its own state, not "clean".
## @return None.
## @version 1
def test_veto_cell_distinguishes_a_divided_contradiction_from_a_clean_one() -> None:
    """The veto records its agreement ratio expressly "so a shaky verdict is visible rather than
    laundered into a clean number" — and then this view laundered it. A judge ruling
    CONTRADICTED without reaching `VETO_AGREEMENT` leaves `vetoed` False and `checked` True, so
    the cell printed the same word as one where the judge found nothing wrong. Under D1 the owner
    arbitrates; that is exactly the cell they need to see.
    """
    assert grade_report._veto_cell({"quality_vetoed": True}) == "**VETOED**"
    assert (
        grade_report._veto_cell(
            {"quality_vetoed": False, "falsity_checked": True, "falsity_verdict": "CONTRADICTED"}
        )
        == "DIVIDED"
    ), "a contradiction that did not reach unanimity must not print as clean"
    assert (
        grade_report._veto_cell(
            {"quality_vetoed": False, "falsity_checked": True, "falsity_verdict": "CONSISTENT"}
        )
        == "clean"
    )
    ## The two unchecked states stay collapsed ON PURPOSE: never armed and all-samples-errored
    ## are the same fact from a reader's position, that nobody knows.
    assert grade_report._veto_cell({"falsity_checked": None}) == "unchecked"
    assert grade_report._veto_cell({"falsity_checked": False}) == "unchecked"


## @brief The YAML rubric is a faithful translation, and the gate that says so actually works.
## @return None.
## @version 1
def test_the_yaml_rubric_matches_the_markdown_and_the_gate_catches_a_drop(tmp_path: Path) -> None:
    """MIGRATION AND CORRECTION IN ONE PASS IS THE OWNER'S CALL; this is what keeps them
    separable. Without it a DROPPED mark is indistinguishable from a corrected one — and that
    exact confusion has already invalidated a grading run here: a `###` sub-header "fix" removed
    Q1-Q4 from the parse, the declared-vs-parsed count still printed [OK], and the pass was scored
    against 65 marks instead of 173.

    SO THE GATE IS TESTED AGAINST THE CASES IT EXISTS FOR, not just exercised. Every gate written
    in this repo's recent sessions was wrong in its first version and only a control found it, so
    a passing baseline plus three mutations is the minimum: a deleted mark, a reworded one and an
    inverted fence. All three verified caught, and the live pair verified equivalent at 173 marks
    across 12 questions.
    """
    target = bench_rubric.REPO_ROOT / "acceptance/targets/mbedtls"
    yml = target / "questions.yaml"

    ## THERE IS EXACTLY ONE KEY. `questions.md` was DELETED once the translation was verified and
    ## the corrections landed (owner, 2026-08-14), because two documents describing one grading key
    ## is the drift failure this repo keeps paying for — and the audit found ~15 wrong
    ## cross-references in that prose already: stale "Q3:6"/"Q3:8" claims the atomisation
    ## reassigned, a 98/89 mark count against a file holding 173, and a contamination table
    ## pointing at a clean mark while hiding eleven dirty ones. Those defects WERE the prose.
    assert not (target / "questions.md").exists(), (
        "questions.md is retired: a second parseable mark list would drift from the YAML, and "
        "nothing would notice because the harness reads only one of them"
    )
    assert yml.exists()

    from_yaml = bench_rubric.parse_rubric_yaml(yml)
    ## A DECLARED COUNT, so a silent loss shows up as a failing test rather than a smaller exam.
    ## 173 translated, minus 6 deleted: Q3 #9 (a resurrected epistemic-habit mark) and five marks that
    ## could not be SCORED as written — Q5 #8, Q7 #8, Q8 #8, Q10 #1 and Q10 #8, each either a
    ## prohibition satisfiable by silence, a grading rule a codebase-blind judge defaults to HIT on,
    ## or a duplicate that made one failure cost three points.
    assert sum(len(r.marks) for r in from_yaml.values()) == 167
    assert len(from_yaml) == 12

    ## THE GATE ITSELF STILL WORKS, proved on fixtures rather than on the live pair it no longer
    ## has. It stays because the next target's migration needs it, and because a gate nobody
    ## exercises is a gate nobody can trust.
    base = tmp_path / "base.yaml"
    base.write_text(
        "questions:\n  - id: Q1\n    marks:\n    - text: first\n    - text: second\n",
        encoding="utf-8",
    )
    same = tmp_path / "same.yaml"
    same.write_text(base.read_text(encoding="utf-8"), encoding="utf-8")
    dropped = tmp_path / "dropped.yaml"
    dropped.write_text("questions:\n  - id: Q1\n    marks:\n    - text: first\n", encoding="utf-8")
    reworded = tmp_path / "reworded.yaml"
    reworded.write_text(
        base.read_text(encoding="utf-8").replace("second", "SECOND"), encoding="utf-8"
    )
    ## The gate takes a markdown path first, so drive it through the YAML-vs-YAML comparison it
    ## performs internally by pointing both sides at YAML files.
    left = bench_rubric.parse_rubric_yaml(base)
    baseline = [m.text for m in left["Q1"].marks]
    for label, other in (("dropped", dropped), ("reworded", reworded)):
        right = [m.text for m in bench_rubric.parse_rubric_yaml(other)["Q1"].marks]
        assert right != baseline, f"a {label} mark must not compare equal to the baseline"
    assert [m.text for m in bench_rubric.parse_rubric_yaml(same)["Q1"].marks] == [
        m.text for m in left["Q1"].marks
    ], "an identical file must compare equal, or the check is vacuous"

    ## THE READER REFUSES AN UNKNOWN KEY at both levels, because a misspelled `require` parses to
    ## a valid mapping nothing reads and the mark would score on the default silently.
    typo = tmp_path / "typo.yaml"
    typo.write_text(
        "questions:\n  - id: Q1\n    marks:\n    - text: a mark\n      requires: all\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown key"):
        bench_rubric.parse_rubric_yaml(typo)

    ## AND IT READS ONLY WHAT IS DECLARED — no fallback to the prose regexes, or the migration
    ## would keep the punctuation-decides-checkability defect alive under a new format.
    single = tmp_path / "single.yaml"
    single.write_text(
        "questions:\n"
        "  - id: Q1\n"
        "    marks:\n"
        "    - text: mentions `mbedtls_mutex_lock` at threading.c:101\n",
        encoding="utf-8",
    )
    only = bench_rubric.parse_rubric_yaml(single)["Q1"].marks[0]
    assert only.symbols == [] and only.refs == [], (
        "the YAML reader must NOT derive evidence from prose — declaring it is the whole point"
    )
    ## A whole-file citation is first class, which the markdown reader could not express.
    whole = tmp_path / "whole.yaml"
    whole.write_text(
        "questions:\n  - id: Q1\n    marks:\n    - text: names the header\n"
        "      refs: [[include/mbedtls/threading.h]]\n",
        encoding="utf-8",
    )
    assert bench_rubric.parse_rubric_yaml(whole)["Q1"].marks[0].refs == [
        ("include/mbedtls/threading.h", 0, 0)
    ]


## @brief A declared threshold is READ by the scorer, not merely stored.
## @return None.
## @version 1
def test_require_and_min_matches_are_enforced_not_just_declared() -> None:
    """A THRESHOLD DECLARED AND IGNORED IS THE WHOLE MIGRATION BEING COSMETIC. This is the
    accepted-but-unread defect this project keeps finding one level down — `key_arg_idx` for
    `key_arg_index` parses to a valid mapping no consumer reads and keys a whole dataflow off
    argument 0 — and I shipped it once in this very session by adding `require` and `veto_safe` to
    the accepted keys while `Mark` had no such fields.

    WHY ANY-OF WAS WRONG WHERE THE MARK SAYS OTHERWISE. Q1 #29 lists SEVEN public headers and says
    "names at least TWO of them", and the objective pass HIT on one — while `entropy.h` and `rsa.h`
    yielded no symbol at all under the old regex, so two of its seven acceptable answers were
    silently unscoreable. Q10 #5 is about two DISTINCT objects that share a name and HIT on either
    one, which inverts the mark's whole point.

    BOTH DEFAULTS ARE THE OLD BEHAVIOUR, so a mark stating no threshold scores exactly as before —
    the migration must not move a score it was not asked to move.
    """
    from bench_rubric import Mark
    from bench_score import answer_citations, score_mark

    seven = [[f"h{i}.h", 0, 0] for i in range(7)]

    ## min_matches: two of the seven cited files must appear.
    threshold = Mark(
        index=1,
        text="names at least two of them",
        refs=[(name, lo, hi) for name, lo, hi in seven],
        min_matches=2,
    )
    one = "I looked at `h0.h` and stopped."
    two = "I looked at `h0.h` and `h3.h`."
    assert score_mark(threshold, one, answer_citations(one)).verdict == "MISS", (
        "one of seven must NOT satisfy a mark whose text asks for two"
    )
    assert score_mark(threshold, two, answer_citations(two)).verdict == "HIT"

    ## require: all — both citations, which is Q10 #5's two same-named statics.
    both = Mark(
        index=2,
        text="two separate objects share a name",
        refs=[("psa_crypto.c", 124, 124), ("psa_crypto_slot_management.c", 193, 193)],
        require="all",
    )
    half = "see `psa_crypto.c:124`"
    whole = "see `psa_crypto.c:124` and `psa_crypto_slot_management.c:193`"
    assert score_mark(both, half, answer_citations(half)).verdict == "MISS", (
        "naming ONE of two distinct objects must not satisfy a mark about their distinctness"
    )
    assert score_mark(both, whole, answer_citations(whole)).verdict == "HIT"

    ## THE DEFAULT IS UNCHANGED: any-of still hits on one when no threshold is stated.
    plain = Mark(index=3, text="names either", refs=[("a.c", 0, 0), ("b.c", 0, 0)])
    only_a = "see `a.c`"
    assert score_mark(plain, only_a, answer_citations(only_a)).verdict == "HIT", (
        "a mark stating no threshold must score exactly as it did before the migration"
    )


## @brief A declared symbol must not be a bare short lowercase word.
## @version 1
def test_no_declared_symbol_is_a_prose_token() -> None:
    """THE GUARD THAT WOULD HAVE CAUGHT MY OWN MISTAKE. `_match_symbols` compares with
    `symbol in answer` — a SUBSTRING, case-sensitive — so a short all-lowercase declared symbol
    matches ordinary prose and awards its mark unseen. Batch 4's first draft declared `heap` for
    Q10 #2, which hits on "heap allocation", "the heap", "heaps": the same auto-HIT defect batch 3
    was written to remove, reintroduced by the batch that cites batch 3's rule.

    THE RULE IS SHAPE, NOT A WORD LIST. A blocklist of English words would have to anticipate the
    next one; "a bare short all-lowercase alphabetic token is prose, not an identifier" is checkable
    and needs no maintenance. It deliberately admits `INPUT` and `TimerProc`, both real declared
    symbols in this rubric: case carries the distinctiveness, and a rule that flagged them would be
    a guard firing on the ordinary case.

    Asserted over the COMMITTED rubric rather than a fixture, because a fixture would test the rule
    against itself — the standing lesson that a detector matching its own fixture is blind to the
    world.

    THE LENGTH BOUND WAS TOO TIGHT AT SIX, and the self rubric proved it. That draft declared
    `check`, `absent` and `rejected`; the guard caught the first two and let `rejected` through on
    length alone, though it is the same defect and appears in prose at least as often. Raised to
    twelve after MEASURING what a wider rule flags across all three committed rubrics: nothing.
    So the widening costs no false positives on the real corpus, which is the only evidence worth
    having — a bound loosened or tightened on intuition is how a guard ends up firing on the
    ordinary case and being switched off.

    @brief No declared symbol is a prose-shaped token.
    @version 1
    """
    from bench_rubric import load_rubric

    ## EVERY PUBLIC RUBRIC. Governing one target while the others go unchecked is how the next
    ## rubric inherits a defect this project already knows how to prevent — and it happened: the
    ## self rubric's first draft declared `check`, `absent` and `rejected`, three words that
    ## appear in ordinary prose constantly, and this guard is what caught them.
    offenders = [
        (target, qid, mark.index, symbol)
        for target in ("mbedtls", "entropic", "self")
        for qid, question in load_rubric(
            bench_rubric.REPO_ROOT / "acceptance" / "targets" / target / "questions.yaml"
        ).items()
        for mark in question.marks
        for symbol in mark.symbols
        if symbol.isalpha() and symbol.islower() and len(symbol) <= 12
    ]
    assert not offenders, (
        f"declared symbols that are prose-shaped and will auto-HIT on a substring match: "
        f"{offenders}. Leave the mark judge-settled and name the object in its text instead."
    )


## @brief The re-armed veto is fed ONLY the marks declared veto-safe.
## @return None.
## @version 1
def test_the_veto_is_armed_and_fed_only_veto_safe_marks() -> None:
    """THE RE-ARM, and the selection is the whole of it. The veto was disarmed because it was fed
    EVERY mark text as an established fact while some marks were false and about fourteen were
    grading instructions — fed a false fact it zeroes the MORE accurate answer. Batch 2 deleted the
    grading instructions, batches 1-4 corrected the false marks, and 19 marks now carry
    `veto_safe: true`, so the premise the veto needed finally holds for a DECLARED SUBSET rather
    than for the whole key.

    ARMING WITHOUT THE FILTER WOULD BE STRICTLY WORSE THAN LEAVING IT OFF: every open mark whose
    acceptable set is enumerated in prose ("a file not in this tree does not earn the mark") would
    become an "established fact" the answer is checked against, and an answer that names a
    DIFFERENT correct file would read as contradicting it. So this asserts the selection, not just
    the constant.

    FAILS CLOSED ON AN EMPTY SUBSET. A rubric with nothing veto-safe must report UNCHECKED, never
    clean — `falsity_check` already returns None on an empty fact list, and this pins that the
    empty list is what reaches it rather than the full one.

    @brief The veto is armed and its fact list is the veto-safe subset.
    @version 1
    """
    from bench_rubric import Mark, load_rubric

    assert grade_matrix.VETO_SAMPLES == 3, (
        "odd, so a non-unanimous vote still has a majority to report; 0 would disarm the pass"
    )

    safe = Mark(index=1, text="a source-verified fact", veto_safe=True)
    instruction = Mark(index=2, text="an answer that omits the default is partial")
    assert grade_matrix.veto_facts([safe, instruction]) == ["a source-verified fact"], (
        "a mark that is a grading instruction must not be handed to the veto as a fact"
    )
    assert grade_matrix.veto_facts([instruction]) == [], (
        "no veto-safe mark must yield an EMPTY fact list, which falsity_check reports as unchecked"
    )
    assert (
        grade_matrix.falsity_check(grade_matrix.veto_facts([instruction]), "b", "haiku", 3) is None
    )

    ## THE COMMITTED RUBRIC HAS A NON-EMPTY SUBSET, so arming is not vacuous on the real key.
    rubric = bench_rubric.REPO_ROOT / "acceptance" / "targets" / "mbedtls" / "questions.yaml"
    declared = sum(
        len(grade_matrix.veto_facts(question.marks)) for question in load_rubric(rubric).values()
    )
    assert declared >= 10, (
        f"only {declared} marks are veto-safe; arming a veto over that few facts checks almost "
        f"nothing while costing 3 judge calls per cell"
    )


## @brief The judge is asked for evidence BEFORE its verdict, and told not to grade arrangement.
## @return None.
## @version 1
def test_the_judge_searches_before_it_decides_and_does_not_grade_format() -> None:
    """TWO DEFECTS, ONE PROMPT, both measured over a real graded run by four independent forensic
    passes: 12 of 39 misses were facts the answer states, several verbatim.

    ORDER. The block used to ask for `VERDICT:` and then `QUOTE:`, with the instruction to check
    the quote "in your head, not on the page". So the judge committed to a verdict and produced
    the evidence afterwards, with no retrieval step between — which is exactly how a reply reads
    `VERDICT: MISS / QUOTE: NONE` against text in the paragraph it was grading. Evidence first is
    the fix, and the ORDER IS THE MECHANISM, so the order is what this asserts.

    ARRANGEMENT. The rules said MISS was "anything else", which was read as licence to fail a
    correct fact for how it was written. Measured: a fact failed FOR BEING IN A TABLE ROW; two
    marks graded off ONE sentence with opposite verdicts; twice a WHY that concedes the fact and
    then rules MISS on "framing". Under D2 a mark is one atomic FACT — format, prominence and
    phrasing are not gradeable.

    ASSERTED ON THE RENDERED PROMPT, not on the constants, because the constants can be right
    while the block that carries them is not — and it is the block the judge actually reads.

    @brief The prompt orders evidence before verdict and forbids grading on format.
    @version 1
    """
    prompt = grade_prompts.mark_prompt("some checklist item", "some candidate answer")

    quote_at, verdict_at = prompt.rindex("QUOTE:"), prompt.rindex("VERDICT:")
    assert quote_at < verdict_at, (
        "the judge must be asked for its quote BEFORE its verdict — reversing this restores the "
        "commit-then-justify order that produced QUOTE: NONE against present text"
    )
    assert "in your head" not in prompt, (
        "telling the judge to verify without writing anything down removes the retrieval step"
    )

    ## FORMAT IS NOT GRADED — asserted by the words the rules must carry, since this is a
    ## behavioural instruction and there is nothing structural to check.
    lowered = prompt.lower()
    assert "table" in lowered and "bullet" in lowered, (
        "the HIT rule must name the containers a fact can legitimately sit in; a fact was failed "
        "for being in a table row and nothing in the prompt said that was not gradeable"
    )
    for phrase in ("format and placement are not graded", "if you can quote the substance"):
        assert phrase in lowered, f"the prompt no longer tells the judge: {phrase!r}"


## @brief The src arm is fenced STRUCTURALLY, not by prompt or by tool-denial.
## @return None.
## @version 1
def test_the_src_arm_is_fenced_by_strict_mcp_config_not_by_its_brief() -> None:
    """THE DEFECT THIS PINS DESTROYED AN ARM WITHOUT TOUCHING A NUMBER. `build_argv` attached
    `--mcp-config` to the mcp arm only, and its docstring claimed the src arm "never sees the
    server at all". `--strict-mcp-config` was attached on the SAME line, so it too was mcp-only —
    and without it `claude -p` loads the operator's GLOBAL MCP configuration.

    Measured on the p5-both run by reading transcripts: the SOURCE arm's context carried the
    clew instructions block, including a sentence describing a prior measured result for
    the very question it was answering. `used_db_tools: 0` recorded a CHOICE, not an inability.

    A prompt saying "you have no index" is not a fence; neither is a deny-list, because the
    instructions text arrives before any tool call. Only "load no servers" is a fence, and the
    flag that means that must be on BOTH arms — on one it scopes, on the other it excludes.

    ASSERTED ON THE ARGV, because that is the only place the guarantee exists. A test of
    `used_db_tools` would pass on a contaminated run whenever the agent happened not to call the
    server, which is precisely how this survived.

    @brief Both arms strict; only the mcp arm gets a config.
    @version 1
    """
    import run_matrix

    src = run_matrix.build_argv("src", "sonnet", "p", Path("/t"), Path("/c.json"))
    mcp = run_matrix.build_argv("mcp", "sonnet", "p", Path("/t"), Path("/c.json"))

    assert "--strict-mcp-config" in src, (
        "without this flag the src arm inherits the operator's global MCP servers, so the arm "
        "separation is a matter of what the agent chose rather than what it could reach"
    )
    assert "--mcp-config" not in src, "the src arm must be given no server config at all"
    assert "--strict-mcp-config" in mcp and "--mcp-config" in mcp, (
        "the mcp arm needs both: the config names its server, strict excludes every other"
    )


## @brief A mark whose substance is a COUNT must not declare evidence that cannot settle a count.
## @return None.
## @version 1
def test_a_numeric_mark_declares_no_symbol_that_would_auto_hit_it() -> None:
    """THE AUTO-HIT CLASS, THIRD OCCURRENCE, so it gets a rule rather than another correction.
    Batch 3 removed six declared symbols that awarded their marks unseen; batch 4 reintroduced one
    (`heap`) and removed it; batch 6 removed Q2 #18's `MBEDTLS_PRIVATE`.

    THE MECHANISM IS WHY IT KEEPS HAPPENING. `_decide` returns an objective HIT the moment one
    declared symbol appears, and `grade_matrix` then SKIPS THE JUDGE. So a symbol that every
    plausible answer contains does not merely weaken the mark — it removes the only reader that
    would have checked the substance.

    A MARK ASKING FOR A NUMBER IS THE UNSETTLEABLE CASE. No symbol and no file reference can
    demonstrate that an answer stated a COUNT; only reading it can. Measured on p5-both: Q2 #18
    demands "about 884 lines in 71 files", both arms scored HIT, and neither answer contains any
    number — the src arm's recorded evidence was a definition line.

    THE RULE IS SHAPE, NOT A LIST. A mark whose text contains a bare integer of three digits or
    more is asking for a figure; such a mark may declare `refs` (a citation is checkable) but not
    `symbols`.

    CITATIONS ARE STRIPPED FIRST, AND THE FIRST DRAFT DID NOT DO IT PROPERLY — it excluded a digit
    run preceded by `:` and so still fired on Q10 #6's `threading.h:134-143`, where `143` is the
    END of a line range and preceded by a dash. That is a false positive on an ordinary,
    correctly-formed mark, and shipping it would have converted this guard into noise the next
    reader learns to ignore. Removing whole `file.ext:NNN[-NNN]` citations before the search is the
    version that survives, and the Q10 case is the control it was checked against.

    @brief Count-bearing marks declare no auto-hitting symbol.
    @version 2
    """
    import re

    ## A LINE CITATION, with or without its filename and with or without a range. Matching from
    ## the COLON rather than from a filename is what makes this correct, and it took two wrong
    ## drafts to get there. The rubric's house style names a file once and then continues with bare
    ## line references — "`x509_crt.h:3159`), `:3176`, `:3210`" — so a filename-anchored pattern
    ## leaves the continuations behind, and a lookbehind for `:` cannot reach the second number of
    ## a range. Both mistakes fired on real, correctly-written marks (Q6 #2, Q6 #8, Q10 #6).
    citation = re.compile(r":\d+(?:\s*[-–]\s*\d+)?")
    ## A standalone quantity: three or more digits, once citations are gone.
    quantity = re.compile(r"(?<![\w.])\d{3,}(?!\w)")

    from bench_rubric import load_rubric

    ## EVERY PUBLIC RUBRIC, not just the one the rule was written against. The guard sat on
    ## mbedtls alone while entropic went ungoverned through a whole grid — and a rule enforced on
    ## one target and not another is how the next target inherits a defect the project already
    ## knows how to prevent. `targets/internal` is deliberately absent: it is gitignored, so a test
    ## that required it would fail on any checkout but this one.
    targets = ("mbedtls", "entropic", "self")
    offenders = [
        (target, qid, mark.index, mark.symbols)
        for target in targets
        for qid, question in load_rubric(
            bench_rubric.REPO_ROOT / "acceptance" / "targets" / target / "questions.yaml"
        ).items()
        for mark in question.marks
        if mark.symbols and quantity.search(citation.sub(" ", mark.text))
    ]
    assert not offenders, (
        f"marks asking for a COUNT while declaring symbols that would auto-HIT them, skipping the "
        f"judge that would have read for the figure: {offenders}"
    )


## @brief The destructive restore refuses unless git resolves to the target itself.
## @param tmp_path Pytest temp dir.
## @return None.
## @version 1
def test_restore_refuses_when_git_resolves_to_a_different_repository(tmp_path: Path) -> None:
    """`git clean -fd` DELETES UNTRACKED FILES, and `cwd=` alone does not decide which repository
    it deletes them from. `GIT_DIR` in the environment overrides cwd discovery outright, and
    gh#386 records git subprocesses in this harness inheriting exactly that from a pre-commit
    hook.

    THE CASE THAT MAKES IT URGENT: an internal acceptance target lives INSIDE this repository, so
    the "wrong repository" a stray GIT_DIR resolves to is docs-db itself — and the restore would
    clean the operator's own untracked work rather than the target's.

    STRIPPING THE ENV IS NOT ENOUGH ON ITS OWN, which is why the toplevel check exists. Stripping
    makes the right resolution likely; only asserting that git's own `--show-toplevel` IS the
    target makes the wrong one impossible, whatever future code or wrapper reintroduces a pointer.
    This asserts the check, not the stripping, because the check is the guarantee.

    A DIRECTORY THAT IS NOT A REPOSITORY AT ALL must also refuse — `--show-toplevel` there either
    fails or resolves to an ENCLOSING repository, and the second is the dangerous one: a target
    that is merely a subdirectory of a checkout would have that whole checkout cleaned.

    @brief Restore refuses a target that is not its own git toplevel.
    @version 1
    """
    import subprocess

    import run_matrix

    ## A plain directory inside a real repository, with the opt-in marker present so the refusal
    ## can only come from the toplevel check and not from the marker guard.
    inner = tmp_path / "outer" / "target"
    inner.mkdir(parents=True)
    subprocess.run(["git", "init", "--quiet", str(tmp_path / "outer")], check=True)
    (inner / run_matrix.RESTORE_MARKER).write_text("disposable", encoding="utf-8")

    with pytest.raises(SystemExit) as caught:
        run_matrix.restore_target(inner)
    message = str(caught.value)
    assert "REFUSING" in message, (
        "a target that is a SUBDIRECTORY of a repository must refuse — cleaning it would clean "
        "the enclosing checkout, which for an internal target is this repository itself"
    )
    assert "clean -fd" in message, "the refusal must say what it was about to do"


## @brief A declared symbol must match a whole identifier, not a substring of a longer one.
## @version 1
def test_a_declared_symbol_does_not_hit_inside_a_longer_identifier() -> None:
    """MEASURED, NOT HYPOTHESISED. entropic Q1 #7 requires that six unrelated classes declare a
    member LITERALLY NAMED `mutex_`. It auto-HIT in 4 of 4 cells, and the sidecars record the
    awarding evidence as `adapter_mutex_ in AdapterManager` and `io_mutex_ (transport_stdio.h:158)`
    — two DIFFERENT members whose names merely end in the declared one. `_match_symbols` compared
    with `symbol in answer`, so a member name is indistinguishable from its own suffix.

    THIS IS NOT THE PROSE-TOKEN RULE ONE TEST UP. `mutex_` is not a bare lowercase English word;
    it is a real identifier, correctly declared, and the shape guard passes it. The defect is in
    the MATCHER, and a rubric-side rule cannot reach it.

    WHY WORD BOUNDARIES AND NOT A BLOCKLIST: the boundary is a property of C identifiers, so it
    needs no maintenance and cannot be phrased around. A trailing `_` still works because the
    character AFTER it in `mutex_;` is not a word character, while the character BEFORE the match
    in `adapter_mutex_` is — which is exactly the distinction the mark is about.

    BOTH HALVES ARE ASSERTED. A test that only checked the rejection would pass against a matcher
    that had stopped matching anything at all, which is this repo's standing lesson about writing
    the negative half.

    @brief Word-boundary symbol matching, both directions.
    @version 1
    """
    from bench_rubric import Mark
    from bench_score import answer_citations, score_mark

    mark = Mark(
        index=7, text="six classes declare a member literally named `mutex_`", symbols=["mutex_"]
    )

    for wrong in (
        "adapter_mutex_ in AdapterManager — 11 acquisitions",
        "io_mutex_ (transport_stdio.h:158)",
        "guarded by eval_mutex_ throughout",
    ):
        assert score_mark(mark, wrong, answer_citations(wrong)).verdict != "HIT", (
            f"a longer identifier ending in the declared symbol must not award it: {wrong!r}"
        )

    for right in (
        "six classes each declare `mutex_` as a member",
        "the member is named mutex_;",
        "mutex_ appears in six unrelated classes",
    ):
        assert score_mark(mark, right, answer_citations(right)).verdict == "HIT", (
            f"the declared symbol named as itself must still award the mark: {right!r}"
        )


## @brief The recorded evidence must quote the occurrence that actually matched.
## @version 1
def test_evidence_quotes_the_matching_occurrence_not_the_first_substring() -> None:
    """THIS DEFECT MANUFACTURED A FALSE FINDING, which is why it earns a test of its own.

    An independent reviewer audited the committed sidecars, read
    `symbol \\`mutex_\\` — adapter_mutex_ in AdapterManager` on entropic Q1 #7, and concluded the
    mark had been awarded on a different member. Replaying the scorer over the same four answers
    showed every one of them DOES name a bare `mutex_` elsewhere in the text — 3, 6, 8 and 8
    occurrences — so the mark was earned and only the QUOTE was wrong. The reviewer's method was
    sound; the evidence field lied to it.

    `_quote` searched with `token in line` while the matcher searched for a whole identifier, so
    the two disagreed about which occurrence mattered and the record kept the wrong one. An
    evidence field exists so a human can overturn a grade, and one that points at a different
    identifier makes every audit built on it unsound in the direction of false alarms.

    @brief Evidence quotes the whole-identifier occurrence.
    @version 1
    """
    from bench_rubric import Mark
    from bench_score import answer_citations, score_mark

    answer = (
        "AdapterManager holds adapter_mutex_ with 11 acquisitions.\n"
        "StdioTransport declares io_mutex_ at transport_stdio.h:158.\n"
        "Six unrelated classes each declare a member named `mutex_`, which collides.\n"
    )
    mark = Mark(index=7, text="six classes declare a member named `mutex_`", symbols=["mutex_"])
    result = score_mark(mark, answer, answer_citations(answer))

    assert result.verdict == "HIT", "the answer does name a bare `mutex_`, so the mark is earned"
    quoted = " ".join(result.evidence)
    assert "Six unrelated classes" in quoted, (
        "the evidence must quote the line where the symbol appears AS ITSELF; quoting the "
        "adapter_mutex_ line reads as an award on a different member and invites a false finding"
    )
    assert "adapter_mutex_ with 11" not in quoted, "the first-substring line must not be the quote"


## @brief An UNCHECKED falsity pass must not report a summable zero for index_false.
## @version 1
def test_unchecked_falsity_reports_no_summable_index_false() -> None:
    """THE PER-CELL VIEW WAS ALREADY HONEST AND THE AGGREGATE WAS NOT, which is the whole defect.
    `_veto_cell` prints four distinguishable words and has done since the DIVIDED fix; but the
    summary block recorded `index_false: 0` whether the pass had run and found nothing or had
    never run at all, so anything that SUMS the field prints a reassuring zero over cells nobody
    checked.

    MEASURED ON THIS GRID: 50 of 74 public cells were never falsity-checked — entropic declares no
    veto-safe mark, so all 28 of its cells are unchecked by construction, and mbedtls's Q0/Q4/Q5/
    Q7/Q8/Q9 add 22 more. Those include the submodule, generated-code and doc-scope questions,
    where a wrong index answer is most likely. An aggregate over that reported `index_false: 0`,
    and I published exactly that number in this session before checking what stood behind it.

    THE FIX IS A TYPE, NOT A CAVEAT. `None` for unchecked makes a naive `sum()` raise instead of
    reading zero — a comment asking future aggregators to be careful is the thing that does not
    survive. This is the standing rule (unchecked never reads as checked-and-fine) applied to the
    one surface where a prose warning cannot reach: someone else's arithmetic.

    @brief Unchecked index_false is None, not 0.
    @version 1
    """
    from grade_matrix import summarise

    unchecked = summarise([], "mcp", None)
    assert unchecked["index_false"] is None, (
        "a cell whose falsity pass never ran must not report a zero that sums as 'no false answers'"
    )
    assert unchecked["falsity_checked"] is None

    with pytest.raises(TypeError):
        sum(cell["index_false"] for cell in [unchecked, unchecked])

    clean = summarise([], "mcp", {"checked": True, "vetoed": False, "verdict": "CONSISTENT"})
    assert clean["index_false"] == 0, "a pass that RAN and found nothing is a real zero"
    vetoed = summarise([], "mcp", {"checked": True, "vetoed": True, "verdict": "CONTRADICTED"})
    assert vetoed["index_false"] == 1


## @brief The falsity record must state how many facts it weighed.
## @version 1
def test_falsity_record_states_its_fact_count() -> None:
    """THE FIX FOR THE EMPTY STATE CAN MANUFACTURE A REASSURING ONE. `falsity_check` refuses on an
    empty fact list, so a rubric declaring nothing veto-safe reports `unchecked` — correct, and the
    reason entropic's 28 cells were unchecked by construction. But arming that rubric with a SINGLE
    veto-safe mark flips every one of those cells to `clean`, while 78 of its 79 facts still go
    unchecked. Same overstatement, opposite direction, and no field distinguished them.

    `facts` is the denominator. "CONSISTENT over 1 fact" and "CONSISTENT over 19" are different
    claims about an answer and must not print as the same word.

    @brief Falsity records carry their fact count.
    @version 1
    """
    import bench_judge
    import grade_matrix

    class _Tally:
        verdict, agreement, tally, samples, errors = "CONSISTENT", 1.0, [("CONSISTENT", 3)], 3, 0

    original = bench_judge.vote
    bench_judge.vote = lambda *a, **k: _Tally()
    try:
        one = grade_matrix.falsity_check(["a single established fact"], "body", "sonnet", 3)
        many = grade_matrix.falsity_check(["fact one", "fact two", "fact three"], "b", "sonnet", 3)
    finally:
        bench_judge.vote = original

    assert one is not None and many is not None
    assert one["facts"] == 1, "a pass weighing one fact must say so"
    assert many["facts"] == 3
    assert one["verdict"] == many["verdict"], (
        "the verdict alone cannot separate them, which is exactly why the count is recorded"
    )
    assert grade_matrix.falsity_check([], "body", "sonnet", 3) is None, (
        "an empty fact list still refuses — unchecked, never clean"
    )


## @brief The rubric template must stay parseable by the harness that will read a copy of it.
## @version 1
def test_the_rubric_template_parses() -> None:
    """A TEMPLATE THAT NO LONGER PARSES IS WORSE THAN NO TEMPLATE: the first thing it does is
    waste a colleague's afternoon, and it rots silently because nothing else reads it.

    Asserts structure rather than content — the placeholder marks are deliberately not real facts
    and must NOT be held to the auto-HIT guards, which govern the three committed rubrics. What
    matters is that `load_rubric` accepts it and that the fields a copier will edit are present.

    @brief The template rubric loads and carries the fields a copier edits.
    @version 1
    """
    from bench_rubric import load_rubric

    path = bench_rubric.REPO_ROOT / "acceptance" / "targets" / "TEMPLATE" / "questions.yaml"
    assert path.is_file(), "the template is referenced by its README and by the release docs"
    rubric = load_rubric(path)
    assert rubric, "the template must contain at least one question or it demonstrates nothing"
    marks = [mark for question in rubric.values() for mark in question.marks]
    assert marks, "a rubric with no marks would parse and grade every answer 0/0"
    assert any(m.symbols or m.refs for m in marks), (
        "the template must demonstrate a declared symbol and a declared ref, since getting those "
        "wrong is the defect class the guards exist for"
    )
    assert all(m.veto_safe is False for m in marks), (
        "no template mark may ship veto_safe: a copier who leaves it set feeds a PLACEHOLDER to "
        "the falsity veto as an established fact, and a false fact inverts the veto"
    )
