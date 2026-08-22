# SPDX-License-Identifier: MIT
"""Tests for the run plan and its preflight refusals.

The plan's ORDER is the design — nesting, counterbalancing, seeded shuffle — and an order defect
is silent: every cell still runs and produces a number. So the order is asserted directly rather
than inferred from a run.

@brief Tests for acceptance.runner.
@version 1
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import runner
from acceptance.grader.rubric import Question, Rubric

REPO = Path(__file__).resolve().parent.parent
MBEDTLS_RUBRIC = REPO / "acceptance" / "targets" / "mbedtls" / "questions.yaml"


## @brief Build a rubric stub with the given question ids.
## @param ids Question identifiers.
## @return Rubric.
## @version 1
def _rubric(*ids: str, declare: dict | None = None) -> Rubric:
    """@brief A minimal rubric for plan tests.
    @return Rubric.
    @version 1
    """
    return Rubric(
        target="owner/repo",
        commit="a" * 40,
        version="1.0.0",
        ground_truth="source",
        judge_model="claude-x-1",
        judge_samples_when_weight_at_least=2,
        questions=tuple(Question(id=i, intent="i", prompt="p") for i in ids),
        declare=declare or {},
    )


## @brief The two arms' briefs differ only in the tool sentence.
## @return None.
## @version 1
def test_prompt_symmetry_holds_on_the_shipped_briefs() -> None:
    """@brief Shipped briefs are symmetric.
    @return None.
    @version 1
    """
    runner.check_symmetry()


## @brief Any difference outside the tool sentence is refused.
## @return None.
## @version 1
def test_asymmetric_briefs_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """THE CONTROL FOR THE CHECK ABOVE. A passing symmetry check is worth nothing until it has
    been watched to fail on a brief that really is asymmetric.

    @brief Asymmetry refuses.
    @return None.
    @version 1
    """
    monkeypatch.setitem(runner._TOOLS, runner.ARMS[1], _TOOLS_LEAK)
    with pytest.raises(ValueError, match="differ outside the tool sentence"):
        runner.check_symmetry()


_TOOLS_LEAK = "You have an index.\nAlso: remember to check whether the feature is enabled."


## @brief No response format is requested of either arm.
## @return None.
## @version 1
def test_neither_brief_requests_a_response_format() -> None:
    """A field list shown to the answering agent leaks the answer — and helps the BASELINE arm
    more, since the index arm would surface the same facts anyway. That shrinks the measured gap
    for a reason unrelated to the tools.

    @brief Briefs impose no schema.
    @return None.
    @version 1
    """
    for arm in runner.ARMS:
        text = runner.brief(arm, "/repo", "What runs concurrently?")
        assert "no required format" in text
        for leak in ("CONCURRENCY:", "THREADS:", "ITEMS:", "one line per"):
            assert leak not in text, f"{arm} brief leaks a response schema: {leak!r}"


## @brief Arms run as adjacent pairs, and their order alternates.
## @return None.
## @version 1
def test_arms_are_paired_and_counterbalanced() -> None:
    """An unpaired cell is uninterpretable, and a fixed arm order confounds any drift over the
    run with the arm — which is the axis every headline number subtracts along.

    @brief Pairing and counterbalancing.
    @return None.
    @version 1
    """
    cells = runner.plan(_rubric("Q1", "Q2"), ("sonnet",), replicates=2, seed=1)
    pairs = [cells[i : i + 2] for i in range(0, len(cells), 2)]
    for pair in pairs:
        assert {c.arm for c in pair} == set(runner.ARMS), "each pair holds both arms"
        assert len({(c.question_id, c.replicate) for c in pair}) == 1, "same question and rep"
    firsts = [pair[0].arm for pair in pairs]
    assert len(set(firsts)) == 2, "arm order must alternate, not be fixed"


## @brief All replicates of a question complete before the next question starts.
## @return None.
## @version 1
def test_replicates_finish_before_the_next_question() -> None:
    """A stop then leaves FEWER QUESTIONS AT USABLE n rather than every question at n=1, and n=1
    is exactly the state that tells you nothing.

    @brief Replicate is inside question.
    @return None.
    @version 1
    """
    cells = runner.plan(_rubric("Q1", "Q2", "Q3"), ("sonnet",), replicates=3, seed=4)
    seen: list[str] = []
    for cell in cells:
        if not seen or seen[-1] != cell.question_id:
            seen.append(cell.question_id)
    assert len(seen) == len(set(seen)), f"a question was revisited after moving on: {seen}"


## @brief A model tier completes before the next one begins.
## @return None.
## @version 1
def test_model_is_the_outermost_loop() -> None:
    """One tier fully measured is a real result; three tiers at 40% is not.

    @brief Model is outermost.
    @return None.
    @version 1
    """
    cells = runner.plan(_rubric("Q1", "Q2"), ("haiku", "sonnet"), replicates=1, seed=2)
    order = [c.model for c in cells]
    assert order == sorted(order, key=lambda m: 0 if m == "haiku" else 1)
    assert order[0] == "haiku" and order[-1] == "sonnet"


## @brief The same seed gives the same order; a different seed does not.
## @return None.
## @version 1
def test_question_order_is_seeded_and_reproducible() -> None:
    """A fixed order correlates position with question across a long run; an unrecorded random
    order cannot be resumed or re-analysed.

    @brief Seeded shuffle.
    @return None.
    @version 1
    """
    rubric = _rubric(*[f"Q{i}" for i in range(12)])
    a = [c.stem() for c in runner.plan(rubric, ("sonnet",), 1, seed=7)]
    b = [c.stem() for c in runner.plan(rubric, ("sonnet",), 1, seed=7)]
    c = [c.stem() for c in runner.plan(rubric, ("sonnet",), 1, seed=8)]
    assert a == b
    assert a != c


## @brief A checkout at the wrong commit is refused by name.
## @return None.
## @version 1
def test_wrong_revision_is_refused(tmp_path: Path) -> None:
    """@brief Revision mismatch refuses.
    @return None.
    @version 1
    """
    import subprocess

    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "--allow-empty", "-m", "x"],
                   check=True, env={"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                                    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t",
                                    "PATH": "/usr/bin:/bin"})  # fmt: skip
    with pytest.raises(ValueError, match="but the rubric pins"):
        runner.check_revision(_rubric("Q1"), tmp_path)


## @brief A declared section missing from the built index is refused by name.
## @return None.
## @version 1
def test_unapplied_declaration_is_refused() -> None:
    """THE CHECK WHOSE ABSENCE LET A WHOLE PHASE OF WORK GO UNMEASURED — a committed declaration
    that never reached the build, with every downstream result describing a build nobody chose.

    THE SIGNAL IS THE TIER, NOT THE KEY'S PRESENCE. `build_meta` stamps `options.<leaf>.tier` for
    every option it knows about, declared or not, and an undeclared one reads `heuristic`. A
    key-presence check therefore PASSES on a build that ignored the declaration entirely, which
    is the failure this exists to catch wearing a pass.

    Comparison is at the LEAF: a rubric declares `preprocessor.predefined`, the index records
    `options.predefined`. The first version compared section names to leaf keys and refused a
    real build whose declaration had landed perfectly.

    @brief Unapplied declaration refuses.
    @return None.
    @version 2
    """
    rubric = _rubric("Q1", declare={"preprocessor": {"predefined": ["X"]}})
    ## Applied: the leaf carries an explicit tier.
    runner.check_declaration_applied(rubric, {"options.predefined.tier": "explicit"})
    ## Present but HEURISTIC — the build knows the option and nobody declared it.
    with pytest.raises(ValueError, match="no explicit tier"):
        runner.check_declaration_applied(rubric, {"options.predefined.tier": "heuristic"})
    ## Absent entirely.
    with pytest.raises(ValueError, match="no explicit tier"):
        runner.check_declaration_applied(rubric, {"options.locks.tier": "explicit"})


## @brief A rubric with no declaration needs no build metadata.
## @return None.
## @version 1
def test_no_declaration_needs_no_build_meta() -> None:
    """@brief An undeclared rubric passes trivially.
    @return None.
    @version 1
    """
    runner.check_declaration_applied(_rubric("Q1"), {})


## @brief The shipped mbedtls rubric plans a coherent run.
## @return None.
## @version 1
def test_the_shipped_rubric_plans() -> None:
    """Runs the plan against the REAL rubric, not a stub. A plan that only ever sees fixtures is
    a plan tested against the detector rather than against the world.

    @brief The shipped rubric plans.
    @return None.
    @version 1
    """
    from acceptance.grader.rubric import load

    rubric = load(MBEDTLS_RUBRIC)
    cells = runner.plan(rubric, ("sonnet",), replicates=1, seed=3)
    assert len(cells) == len(rubric.questions) * 2
    assert len({c.stem() for c in cells}) == len(cells), "cell names must be unique"


## @brief A dirty working tree is refused even at the right commit.
## @return None.
## @version 1
def test_dirty_tree_is_refused_at_the_pin(tmp_path: Path) -> None:
    """HEAD IS NOT THE TREE. A modified checkout passes a rev-parse check while both arms read
    files the rubric was never verified against, so every line number in it is a claim about
    content nobody checked.

    A freshly fetched target cannot be dirty. A LOCAL checkout reused as a target silently can,
    which is how two of the reference targets are provisioned — so the check exists for the case
    that actually occurs rather than the one that cannot.

    @brief Dirty tree refuses.
    @return None.
    @version 1
    """
    import subprocess

    env = {
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "a.txt").write_text("one")
    subprocess.run(["git", "-C", str(tmp_path), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "commit", "-q", "-m", "x"], check=True, env=env)
    head = subprocess.run(
        ["git", "-C", str(tmp_path), "rev-parse", "HEAD"], capture_output=True, text=True
    ).stdout.strip()

    rubric = Rubric(
        target="owner/repo",
        commit=head,
        version="1.0.0",
        ground_truth="source",
        judge_model="claude-x-1",
        judge_samples_when_weight_at_least=2,
        questions=(Question(id="Q1", intent="i", prompt="p"),),
    )
    ## Clean at the pin: passes.
    runner.check_revision(rubric, tmp_path)
    ## Same commit, modified content: refused.
    (tmp_path / "a.txt").write_text("two")
    with pytest.raises(ValueError, match="working tree is MODIFIED"):
        runner.check_revision(rubric, tmp_path)


## @brief 1.1.0 compares baseline vs index_only; the blended arm stays out.
## @return None.
## @version 1
def test_blended_arm_is_out_of_the_comparison_and_index_only_has_no_shell() -> None:
    """AN INDEX ARM SCORING BELOW FULL MARKS IS AMBIGUOUS between "the index could not answer"
    and "the agent did not ask" — measured, index arms made 0 to 5 index calls out of 6 to 14, so
    every score is confounded with adoption. The ceiling arm removes the second explanation.

    IT IS NOT A COMPARISON ARM. Nobody ships "you may only use the index", and this project
    retired a crippled arm once already because index-versus-grep is not the real-world question.
    So it must stay out of ARMS, and `check_symmetry` must compare only the arms that ARE paired
    — diffing a deliberately asymmetric arm would either fail the check or dilute it into
    permitting anything.

    @brief Ceiling arm is separate and shell-free.
    @return None.
    @version 1
    """
    ## 1.1.0 COMPARES baseline vs index_only. The BLENDED arm — a full harness that also has the
    ## index — is confounded with adoption and is deferred to 1.2.0, so it must stay OUT of the
    ## compared pair while remaining runnable.
    assert runner.BLENDED_ARM not in runner.ARMS, "the blended arm must not join the comparison"
    assert runner.BLENDED_ARM in runner.ALL_ARMS
    assert "index_only" in runner.ARMS
    text = runner.brief("index_only", "/repo", "Q?")
    for shell in ("Bash", "Grep", "Glob"):
        assert shell not in text, f"the index-only arm was granted {shell}"
    assert "index alone" in text
    ## The blended arm still has its shell, or it would not be the shipped shape.
    assert "Bash" in runner.brief(runner.BLENDED_ARM, "/repo", "Q?")
    ## Symmetry still holds over the comparison arms with the third one present.
    runner.check_symmetry()
