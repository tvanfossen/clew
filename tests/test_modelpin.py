# SPDX-License-Identifier: MIT
"""How specific a model id has to be before a measurement may be published against it.

**THIS FILE RECORDS A SPECIFICATION THAT CHANGED TWICE IN ONE DAY, AND BOTH MOVES WERE RIGHT.**

1. 1.1.0 named its judge with a dated id and never checked the ANSWERING model at all, so the
   published grid was judged by `claude-sonnet-4-5-20250929` and answered by `claude-haiku-5-5`
   with the rubric digest, commit pin and seed all reading as held. The rule that was supposed to
   catch that asked only for a hyphen and a digit — which `claude-haiku-5-5` satisfies.

2. The fix demanded an 8-digit date. **That broke the harness.** The provider publishes no dated
   form for the current family: `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5` and
   `claude-fable-5-1` all fail a date test, and `modelUsage.canonicalModel` in the 1.1.0
   transcripts is *also* `claude-haiku-5-5`, so the dated id does not exist to be recorded. Only
   the previous-generation judge id passed, which would have forced the whole matrix onto a
   receding model.

**THE OWNER'S RULING, which is the specification these tests now encode:** *"models will shift and
move, we cannot and should not be testing against the SAME variant every time; if claude models
shift, so too should our model grid."* Immutability is not the requirement. Naming what answered,
faithfully, and disclosing when that name can float — that is.

Note what did NOT change: a bare `sonnet` is still refused. The client resolves it from
configuration this harness neither reads nor records, so two runs can answer from different models
with nothing saying so. A canonical id can still move under a version bump, but it is the most
specific thing the provider offers, it appears in `modelUsage`, and the runs record it — bounded,
visible drift instead of silent drift.

@brief A model id must be provider-canonical, and floating ids must be disclosed.
@version 2
"""

from __future__ import annotations

from pathlib import Path

import pytest

from acceptance.modelpin import floats, is_pinned, require_pinned


##
# @brief Every current-family model must be accepted.
# @param model The canonical id.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "model",
    ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-1"],
)
def test_a_current_family_model_is_accepted(model: str) -> None:
    """**THE REGRESSION THIS FILE EXISTS TO PREVENT, AND IT IS THE OPPOSITE OF WHAT v1 ASSERTED.**
    v1 required a date and so rejected every one of these, which blocked `plan`, `generate` and
    `grade` outright — a harness that cannot run measures nothing. If a future change reinstates a
    date requirement, this fails first and names the cost.

    @brief Current models are accepted.
    @param model The id.
    @return None.
    @version 1
    """
    assert is_pinned(model), (
        f"{model!r} was refused. The provider publishes no dated form for this family, so a date "
        f"requirement blocks the harness entirely rather than making the model stable."
    )


##
# @brief A client-resolved shortcut must still be refused.
# @param model The shortcut.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "model", ["sonnet", "opus", "haiku", "fable", "default", "latest", "claude", "m"]
)
def test_a_client_resolved_shortcut_is_refused(model: str) -> None:
    """WHAT DID NOT CHANGE. The client maps these through its own configuration, which this
    harness does not read and does not record, so the id in `run.json` would not identify what
    answered. `claude` is in the list because a vendor without a family or version is not a model
    either.

    @brief Shortcuts are refused.
    @param model The shortcut.
    @return None.
    @version 1
    """
    assert not is_pinned(model)


##
# @brief A dated id must be accepted and reported as not floating.
# @param model The dated id.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "model",
    ["claude-sonnet-4-5-20250929", "claude-opus-4-1-20250805", "claude-3-5-haiku-20241022"],
)
def test_a_dated_id_is_accepted_and_does_not_float(model: str) -> None:
    """A date is still the strongest claim available and is still recognised as such — it is just
    no longer the price of admission.

    @brief Dated ids do not float.
    @param model The id.
    @return None.
    @version 1
    """
    assert is_pinned(model)
    assert not floats(model), f"{model!r} carries a date and must not be reported as floating"


##
# @brief A canonical id with no date must be accepted AND disclosed as floating.
# @param model The canonical id.
# @return None.
# @version 1
@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-opus-5-5"])
def test_a_canonical_id_without_a_date_is_disclosed_as_floating(model: str) -> None:
    """**BOTH HALVES, BECAUSE ACCEPTANCE WITHOUT DISCLOSURE IS THE ORIGINAL DEFECT.** 1.1.0
    answered with a floating id and said nothing; accepting one silently would reproduce exactly
    that. `floats()` is what lets a run record and its `RESULTS.md` state that two runs months
    apart may not have answered from the same weights.

    @brief Floating ids are accepted and flagged.
    @param model The id.
    @return None.
    @version 1
    """
    assert is_pinned(model)
    assert floats(model), (
        f"{model!r} carries no date, so it can move under a version bump — a run using it must be "
        f"able to say so"
    )


##
# @brief An unstated model must be refused as unstated, not as a shortcut.
# @return None.
# @version 1
def test_an_unstated_model_is_refused_as_unstated() -> None:
    """ABSENCE IS NOT EMPTINESS, and the two need different fixes: a missing argument versus a
    wrong one. A single "invalid model" would send the reader looking for the wrong thing.

    @brief Unstated is its own message.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="unstated"):
        require_pinned("--models", "   ")


##
# @brief A shortcut must be refused with a message naming what is wrong with it.
# @return None.
# @version 1
def test_a_shortcut_is_refused_with_a_message_that_names_the_cause() -> None:
    """The message has to say WHY, because the obvious reading of a refusal here is "use a dated
    id" — which is no longer true and no longer possible for the current family.

    @brief Shortcuts get an explanatory message.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="shortcut"):
        require_pinned("--models", "sonnet")


##
# @brief A canonical id must raise nothing.
# @param model The canonical id.
# @return None.
# @version 1
@pytest.mark.parametrize("model", ["claude-haiku-5-5", "claude-sonnet-4-5-20250929"])
def test_a_canonical_id_is_accepted_by_require_pinned(model: str) -> None:
    """The permissive leg is not redundant: a `require_pinned` wired to always raise would pass
    every other test in this file and block the harness.

    @brief Canonical ids pass.
    @param model The id.
    @return None.
    @version 1
    """
    require_pinned("judge.model", model)


##
# @brief The CLI rubric loader must refuse a shortcut judge model.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 2
def test_the_cli_loader_refuses_a_shortcut_judge_model(tmp_path) -> None:
    """**THE RULE HAD TO MOVE OUT OF THE GRADER, AND THIS PINS THAT IT SURVIVED THE MOVE.** It used
    to live in `acceptance/grader/rubric.py`, where `grader_fingerprint()` hashes it — so editing
    it there moved the fingerprint and made 144 published cells un-re-gradable at their own keys.
    It now lives in `_rubric`, the single load point for every CLI path that produces a
    measurement.

    v2: the fixture is `sonnet` rather than `claude-haiku-5-5`, because the latter is now
    legitimately accepted.

    @brief The CLI loader refuses a shortcut judge.
    @return None.
    @version 2
    """
    import yaml

    from acceptance import __main__ as cli

    src = Path(__file__).resolve().parent.parent / "acceptance/targets/mbedtls/questions.yaml"
    doc = yaml.safe_load(src.read_text("utf-8"))
    doc["judge"]["model"] = "sonnet"
    rubric_path = tmp_path / "q.yaml"
    rubric_path.write_text(yaml.safe_dump(doc), encoding="utf-8")

    assert cli._rubric(rubric_path) is None, "the CLI loader accepted a client-resolved shortcut"


##
# @brief A rubric with a canonical judge model must still load.
# @return None.
# @version 1
def test_the_cli_loader_accepts_a_pinned_judge_model() -> None:
    """The permissive leg, against a REAL shipped rubric rather than a fixture: a loader wired to
    refuse everything would pass the test above and break every run.

    @brief A canonical judge loads.
    @return None.
    @version 1
    """
    from acceptance import __main__ as cli

    src = Path(__file__).resolve().parent.parent / "acceptance/targets/mbedtls/questions.yaml"

    assert cli._rubric(src) is not None, "a shipped rubric with a dated judge id failed to load"
