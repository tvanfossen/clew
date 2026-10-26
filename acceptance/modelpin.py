# SPDX-License-Identifier: MIT
"""ONE DEFINITION OF "THIS MODEL IS NAMED WELL ENOUGH TO MEASURE WITH".

WHY IT EXISTS. 1.1.0 published a reproducibility caveat it did not have to: the judge was named by
a dated id while the ANSWERING model was given as `claude-haiku-5-5`, and nothing checked the
second one at all. `grader/rubric.py` had refused a bare `sonnet` for the judge since the first
release; the rule was simply never applied to the other half of the experiment.

**THE FIRST FIX OVER-CORRECTED AND BROKE THE HARNESS.** It demanded an 8-digit date, on the
reasoning that an alias can move under a run while the commit pin still reads as held. The
reasoning is sound; encoding it as "the id must contain a date" is not, because the provider
publishes no dated form for the current family. Measured: `claude-haiku-5-5`,
`claude-sonnet-5-5`, `claude-opus-5-5` and `claude-fable-5-1` all fail a date test, and
`modelUsage.canonicalModel` in the 1.1.0 transcripts is *also* `claude-haiku-5-5` — so the dated
id is not merely unknown, it does not exist to be recorded. A rule nothing can satisfy does not
make the model stable; it prevents measurement, which is worse.

**MODELS MOVE, AND THE GRID SHOULD MOVE WITH THEM.** Freezing the answering model forever would
measure clew against a receding target: the question "is the index cheaper than a shell for an
agent" is about the agent people actually have. So the requirement is not immutability. It is
that the run NAME what it used, faithfully, and disclose when that name can float.

WHAT IS STILL REFUSED, and why it is not a formality. A bare family word — `sonnet`, `haiku`,
`opus` — is resolved by the CLIENT, from configuration this harness does not read and does not
record. Two runs a week apart with `--models sonnet` can answer from different models with
nothing anywhere saying so. A provider-canonical id (`claude-haiku-5-5`) can still move under a
version bump, but it is the most specific thing the provider offers, it is what appears in
`modelUsage`, and the runs record it — so the drift is bounded and visible rather than silent.

So: refuse a client-resolved shortcut, accept a provider-canonical id, and make floating visible
through `floats()` so a run record and its `RESULTS.md` can say which kind answered.

ABSENCE IS NOT EMPTINESS. An empty or missing model string is not "acceptable" and is not "a
shortcut" either — it is unstated, and `require_pinned` says so in those words rather than
guessing which.
"""

from __future__ import annotations

import re

## A DATED id carries an 8-digit `YYYYMMDD` segment: `claude-sonnet-4-5-20250929`. Anchored to a
## segment boundary so `claude-x-20250929-preview` still counts and a bare run of digits inside a
## word does not. `20\d{6}` rather than `\d{8}` because a DATE is the claim —
## `claude-haiku-12345678` is eight digits and not a date.
##
## This no longer gates anything. It is the input to `floats()`, which is disclosure.
_DATED = re.compile(r"-20\d{6}(?:$|-)")

## A PROVIDER-CANONICAL id names a vendor, a family and a version: `claude-haiku-5-5`,
## `claude-sonnet-4-5-20250929`. At least two hyphen-separated segments after the vendor, with a
## digit somewhere in the version part. What this excludes is the shape that matters: a single
## bare word the client resolves from its own configuration.
_CANONICAL = re.compile(r"^[a-z][a-z0-9]*(?:[-.][a-z0-9]+)*$", re.IGNORECASE)

## The client-resolved shortcuts this harness refuses by name. Listed rather than inferred, so the
## refusal message can be specific and so a reader can see exactly what is rejected. These are the
## words a CLI accepts as a convenience and maps through local configuration.
_SHORTCUTS = frozenset(
    {"sonnet", "opus", "haiku", "fable", "default", "latest", "fast", "sonnet[1m]"}
)


##
# @brief Report whether a model id can change meaning without the id changing.
# @param model The model id as written.
# @return True when the id carries no date segment, so a version bump moves it.
# @version 1
def floats(model: str) -> bool:
    """DISCLOSURE, NOT A GATE. A canonical id without a date is accepted and reported as floating,
    so the run record and `RESULTS.md` can say that two runs months apart may not have answered
    from the same weights. That sentence is what the date requirement was really for, and it can
    be written without refusing to run.

    @brief Can this id move under the run.
    @param model The model id.
    @return True when it floats.
    @version 1
    """
    return not bool(_DATED.search(model.strip()))


##
# @brief Report whether a model id is specific enough to measure with.
# @param model The model id as written.
# @return True when the id is provider-canonical rather than a client shortcut.
# @version 2
def is_pinned(model: str) -> bool:
    """v2: ACCEPTS A CANONICAL ID WITHOUT A DATE. v1 demanded a date and thereby rejected every
    current-family model, blocking the harness entirely — see the module docstring.

    The name is kept because the callers' intent is unchanged: "is this named well enough to
    publish a measurement against". What changed is the answer for an id the provider does not
    date.

    @brief Is this specific enough to measure with.
    @param model The model id.
    @return True when acceptable.
    @version 2
    """
    text = model.strip()
    if not text or text.lower() in _SHORTCUTS:
        return False
    ## A version segment is required: `claude` alone names a vendor, not a model.
    return bool(_CANONICAL.match(text)) and any(ch.isdigit() for ch in text) and "-" in text


##
# @brief Raise unless a model id is specific enough to measure with.
# @param label What this model is, for the message: "judge.model", "--models".
# @param model The model id as written.
# @return None.
# @version 2
def require_pinned(label: str, model: str) -> None:
    """THE MESSAGE NAMES WHICH FAILURE IT IS. "unstated" and "a client shortcut" need different
    fixes — one is a missing argument, the other a wrong one — and a single "invalid model" would
    send the reader looking for the wrong thing.

    A FLOATING CANONICAL ID RAISES NOTHING. It is accepted and `floats()` reports it, because the
    alternative is a harness that cannot run against any current model.

    @brief Refuse a model id too vague to measure with.
    @param label The field name.
    @param model The model id.
    @return None.
    @version 2
    """
    text = model.strip()
    if not text:
        raise ValueError(
            f"{label} is unstated. A measurement has to name the model that produced it; "
            f"give a provider-canonical id such as claude-haiku-5-5"
        )
    if not is_pinned(text):
        raise ValueError(
            f"{label} {text!r} is a client-resolved shortcut, not a model id. The client maps it "
            f"through configuration this harness does not read and does not record, so two runs "
            f"can answer from different models with nothing saying so. Give a provider-canonical "
            f"id such as claude-haiku-5-5 or claude-sonnet-4-5-20250929"
        )
