# SPDX-License-Identifier: MIT
"""ONE DEFINITION OF "THIS MODEL IS PINNED", FOR THE JUDGE AND FOR WHAT IT GRADES.

WHY IT EXISTS. 1.1.0 published a reproducibility caveat it did not have to: the judge was pinned
by dated id while the ANSWERING model was the alias `claude-haiku-5-5`. An alias moves under the
run — the same rubric, the same commit pin, the same seed, a different model — so "repeatable so
long as the pin holds" was false on the one axis the measurement is about, and nothing reported
it. `grader/rubric.py` already refused an alias for the judge; the rule simply was not applied to
the other half of the experiment.

THE OLD RULE WAS WEAKER THAN IT READ, which is how the gap survived review. It asked for a hyphen
and any digit:

    if "-" not in model or not any(ch.isdigit() for ch in model):

`sonnet` is caught by that. `claude-haiku-5-5` is not — it has both — so the judge check would
have accepted a family alias as a dated id. A rule that passes the case you are worried about,
while reading as though it rejects it, is worse than no rule: it is a green that means nothing.
What distinguishes a pinned id is a DATE, so a date is what is asked for.

ABSENCE IS NOT EMPTINESS. An empty or missing model string is not "pinned" and is not "an alias"
either — it is unstated, and `require_pinned` says so in those words rather than guessing which.
"""

from __future__ import annotations

import re

## A pinned id carries an 8-digit `YYYYMMDD` segment: `claude-sonnet-4-5-20250929`. Anchored to
## a segment boundary so a version like `claude-x-20250929-preview` still counts and a bare run
## of digits inside a word does not. `20\d{6}` rather than `\d{8}` because a date is the claim —
## `claude-haiku-12345678` is not a pin, it is a typo that would otherwise pass.
_DATED = re.compile(r"-20\d{6}(?:$|-)")


##
# @brief Report whether a model id is pinned to a dated release rather than an alias.
# @param model The model id as written.
# @return True when the id carries a YYYYMMDD segment.
# @version 1
def is_pinned(model: str) -> bool:
    """@brief Is this a dated model id.
    @param model The model id.
    @return True when dated.
    @version 1
    """
    return bool(_DATED.search(model.strip()))


##
# @brief Raise unless a model id is pinned to a dated release.
# @param label What this model is, for the message: "judge.model", "--models".
# @param model The model id as written.
# @return None.
# @version 1
def require_pinned(label: str, model: str) -> None:
    """THE MESSAGE NAMES WHICH FAILURE IT IS. "unstated" and "an alias" need different fixes —
    one is a missing argument, the other a wrong one — and a single "invalid model" would send
    the reader looking for the wrong thing.

    @brief Refuse an unpinned model.
    @param label The field name.
    @param model The model id.
    @return None.
    @version 1
    """
    text = model.strip()
    if not text:
        raise ValueError(
            f"{label} is unstated. A measurement has to name the model that produced it; "
            f"pin a DATED id such as claude-sonnet-4-5-20250929"
        )
    if not is_pinned(text):
        raise ValueError(
            f"{label} {text!r} is an alias, not a pinned id. An alias moves under the run while "
            f"the rubric digest, the commit pin and the seed all still read as held, so the "
            f"artifacts claim a repeatability they do not have. Pin a DATED id such as "
            f"claude-sonnet-4-5-20250929"
        )
