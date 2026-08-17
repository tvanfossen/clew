# SPDX-License-Identifier: MIT
"""Per-stage wall-clock cost of one build, recorded beside the refresh total.

`refresh.duration_ms` is one number for a pipeline of thirty stages, which is enough
to decide whether to refresh and not enough to decide what to make faster. The
timings already exist at runtime — the build prints per-stage progress — and are
discarded when the process ends, the same shape as the scope decision that was
computed, logged and thrown away before it was stamped.

MARK-BASED RATHER THAN A CONTEXT MANAGER, and that is the whole design. The stages
are a flat sequence of calls in `cli._build_stages` separated by the ordering
comments that make the pipeline readable; wrapping each in a `with` would indent
every call and every comment one level, for a diff that hides the change it makes.
`mark(name)` CLOSES the segment that just ran, so a stage costs one line placed
directly beneath it and nothing else moves.

The consequence to know: time before the first `mark` and between an unmarked call
and the next `mark` is attributed to the segment that closes next. Every stage
therefore has to be marked for the breakdown to mean what it says, and a stage added
without one is charged to its neighbour rather than reported missing. The
`refresh.stages` name set is pinned by a test against a real build for exactly that
reason.

@brief Per-stage build timing, serialized into the refresh build_meta section.
@version 1
"""

from __future__ import annotations

import time

## build_meta key, under the `refresh.` section `write_build_signature` prefixes.
STAGES_KEY = "stages"

## Serialization: `name=milliseconds`, segments joined by a single space, in the
## order they ran. A space-joined flat string rather than JSON because this value
## is read inside an already-JSON `status` payload, where quoting a nested document
## costs a backslash on every key and buys nothing a `split()` does not give.
## Stage names are identifiers, so neither separator can occur inside one.
STAGE_ASSIGN = "="
STAGE_SEPARATOR = " "


## @brief Wall-clock cost of each build stage, in the order they ran.
## @version 1
## @req REQ-DDB-MCP-004
class StageTimer:
    """Accumulates `(stage name, elapsed milliseconds)` for one build.

    Not thread-safe and not meant to be: the pipeline is one sequence on one thread,
    and a timer that tolerated concurrent marks would be recording something other
    than the sequence a caller waited for.

    @brief Ordered per-stage timings for one build.
    @version 1
    """

    ## @brief Start the first segment.
    ## @version 1
    ## @req REQ-DDB-MCP-004
    def __init__(self) -> None:
        """@brief Begin timing at construction.

        @version 1
        """
        self._last = time.perf_counter()
        self._stages: list[tuple[str, int]] = []

    ## @brief Close the segment that just ran and name it.
    ## @param name Identifier for the stage that has finished.
    ## @version 1
    ## @req REQ-DDB-MCP-004
    def mark(self, name: str) -> None:
        """Elapsed time is measured from the previous `mark` (or from construction),
        so the segments partition the timed span with no gaps and no overlaps.

        A repeated name is recorded again rather than merged. Two segments that
        genuinely ran twice are two facts, and silently summing them would report a
        single stage that no single call ever took.

        @brief Record the elapsed time since the last mark under `name`.
        @version 1
        """
        now = time.perf_counter()
        self._stages.append((name, int((now - self._last) * 1000)))
        self._last = now

    ## @brief The recorded segments, in execution order.
    ## @return Tuple of (stage name, elapsed milliseconds) pairs.
    ## @version 1
    ## @req REQ-DDB-MCP-004
    def stages(self) -> tuple[tuple[str, int], ...]:
        """@brief Read the recorded segments.

        @return The (name, milliseconds) pairs in order.
        @version 1
        """
        return tuple(self._stages)

    ## @brief The breakdown as a build_meta section fragment.
    ## @return `{STAGES_KEY: "name=ms name=ms ..."}`, or {} when nothing was marked.
    ## @version 1
    ## @req REQ-DDB-MCP-004
    def as_meta(self) -> dict[str, str]:
        """EMPTY WHEN NOTHING WAS MARKED, so an unmeasured build stamps no key at all.
        `write_build_signature` drops falsy values, so an empty string would vanish
        anyway; returning {} says the same thing at the point a reader looks.

        @brief Serialize the breakdown for `write_build_signature(refresh=...)`.
        @return A one-key mapping, or {}.
        @version 1
        """
        if not self._stages:
            return {}
        rendered = STAGE_SEPARATOR.join(
            f"{name}{STAGE_ASSIGN}{elapsed}" for name, elapsed in self._stages
        )
        return {STAGES_KEY: rendered}


## @brief Parse a stamped `refresh.stages` value back into ordered pairs.
## @param rendered The stored `name=ms name=ms ...` string.
## @return Tuple of (stage name, milliseconds) pairs, in the stored order.
## @version 1
## @req REQ-DDB-MCP-004
def parse_stages(rendered: str) -> tuple[tuple[str, int], ...]:
    """The inverse of `StageTimer.as_meta`, kept beside it so the two cannot drift
    into different notions of the separator. A malformed segment is DROPPED rather
    than raised on: this reads a stored measurement in a reporting path, and a
    breakdown that cannot be shown must not take the status call down with it.

    @brief Decode a stored stage breakdown.
    @return The decoded pairs.
    @version 1
    """
    decoded: list[tuple[str, int]] = []
    for segment in rendered.split(STAGE_SEPARATOR):
        name, _, value = segment.partition(STAGE_ASSIGN)
        if name and value.isdigit():
            decoded.append((name, int(value)))
    return tuple(decoded)
