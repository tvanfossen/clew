# SPDX-License-Identifier: MIT
"""An alias that read as a pin.

1.1.0 published a reproducibility caveat it did not have to. The judge was pinned by dated id and
the ANSWERING model was `claude-haiku-5-5` — an alias. The same rubric, commit and seed with a
different model behind them is not the same measurement, and no artifact said so.

**THE RULE THAT WAS SUPPOSED TO CATCH IT WOULD NOT HAVE.** `grader/rubric.py` asked for a hyphen
and any digit, which `claude-haiku-5-5` satisfies. So the judge's own guarantee was weaker than
its comment claimed — it rejected `sonnet` and accepted any family alias. That is the project's
"green while checking nothing" shape applied to the measurement instrument, and the first test
here is specifically the case the old rule let through.

@brief A model id counts as pinned only when it carries a date.
@version 1
"""

from __future__ import annotations

import pytest

from acceptance.modelpin import is_pinned, require_pinned


##
# @brief The family alias the old rule accepted must be rejected.
# @return None.
# @version 1
def test_the_alias_the_old_rule_accepted_is_rejected() -> None:
    """THIS IS THE REGRESSION, NAMED. `claude-haiku-5-5` has a hyphen and digits, so the previous
    rule called it dated. It is the exact string 1.1.0 answered with.

    @brief A family alias is not a pin.
    @return None.
    @version 1
    """
    assert not is_pinned("claude-haiku-5-5")


##
# @brief Aliases of every shape must be rejected.
# @param model The alias.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "model",
    ["sonnet", "opus", "haiku", "claude-opus-5-5", "claude-sonnet-4-5", "claude-haiku-12345678"],
)
def test_an_alias_is_not_pinned(model: str) -> None:
    """`claude-haiku-12345678` is in this list on purpose: eight digits that are not a date. The
    claim being made is "a dated release", so a rule matching any 8-digit run would accept a typo
    and report a pin — the flattering reading again.

    @brief Aliases are not pins.
    @param model The alias.
    @return None.
    @version 1
    """
    assert not is_pinned(model)


##
# @brief A dated id must be accepted.
# @param model The dated id.
# @return None.
# @version 1
@pytest.mark.parametrize(
    "model",
    [
        "claude-sonnet-4-5-20250929",
        "claude-opus-4-1-20250805",
        "claude-3-5-haiku-20241022",
        "claude-x-20250101-preview",
    ],
)
def test_a_dated_id_is_pinned(model: str) -> None:
    """The trailing-suffix case is included because a date is not always last. A rule anchored
    only at end-of-string would refuse a legitimate pin, and the project would then work around
    its own check — which ends with the check being removed.

    @brief Dated ids are pins.
    @param model The dated id.
    @return None.
    @version 1
    """
    assert is_pinned(model)


##
# @brief An unstated model must be refused as unstated, not as an alias.
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
# @brief An alias must be refused with a message naming it an alias.
# @return None.
# @version 1
def test_an_alias_is_refused_as_an_alias() -> None:
    """@brief An alias gets the alias message.
    @return None.
    @version 1
    """
    with pytest.raises(ValueError, match="alias"):
        require_pinned("--models", "claude-haiku-5-5")


##
# @brief A pinned id must raise nothing.
# @return None.
# @version 1
def test_a_pinned_id_is_accepted() -> None:
    """The permissive leg is not redundant: a `require_pinned` wired to always raise would pass
    every other test in this file.

    @brief A pin is accepted.
    @return None.
    @version 1
    """
    require_pinned("judge.model", "claude-sonnet-4-5-20250929")
