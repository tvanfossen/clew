# SPDX-License-Identifier: MIT
"""A test is a slice of a master flow (round 5, R5-4).

OWNER 2026-11-17: "a test itself doesn't need a sequence diagram, a test case is testing a portion
OF a sequence diagram". Per-test coverage (`imports.parse_contexts`: coverage.py contexts, or an
LCOV tracefile's `TN:` sections) says which lines each test ran. Against a master flow:

  * a step is EXERCISED by a test when its call-site line ran in that test — the call happened,
    not merely the callee's file being touched;
  * the test ENTERS the flow at a function whose calls it ran while no exercised step called that
    function: the test called it itself (the flow's entry, or a function in its middle).

This is measurement. Without per-test coverage nothing here applies; a slice is then static reach,
and the page says so.

@brief Test slices of master flows from per-test coverage.
@version 1
"""

from __future__ import annotations

from dataclasses import dataclass

from .flow import Flow

## {file: {line: tests}}, as `imports.parse_contexts` returns it.
Contexts = dict[str, dict[int, set[str]]]
## {file: lines one test ran}.
Lines = dict[str, set[int]]


## @brief One test's portion of one master flow.
## @version 1
@dataclass(frozen=True)
class Slice:
    """@brief Exercised step indices and where the test entered. @version 1"""

    exercised: tuple[int, ...] = ()
    entered: tuple[str, ...] = ()


## @brief Per-test coverage turned around: each test's lines per file.
## @param contexts {file: {line: tests}}.
## @return {test: {file: lines}}.
## @version 1
## @req REQ-DDB-WIKI-041
def lines_per_test(contexts: Contexts) -> dict[str, Lines]:
    """@brief Group lines by test. @return Lines per test."""
    out: dict[str, Lines] = {}
    for rel, lines in contexts.items():
        for line, tests in lines.items():
            for test in tests:
                out.setdefault(test, {}).setdefault(rel, set()).add(line)
    return out


## @brief The steps of a flow one test exercised, and where it entered.
## @param flow The master flow.
## @param lines The lines that test ran, per file.
## @return The slice.
## @version 1
## @req REQ-DDB-WIKI-041
def slice_of(flow: Flow, lines: Lines) -> Slice:
    """A STEP'S CALL SITE is `site_file:line` — the line in the caller where the call is made — so
    a step is exercised only if that call happened in this test. Entry points are listed in the
    order their first exercised step appears.

    @brief Slice a flow.
    @return The slice.
    """
    exercised = tuple(
        i
        for i, step in enumerate(flow.steps)
        if step.line in lines.get(step.site_file or step.file, ())
    )
    called = {flow.steps[i].callee_qualified or flow.steps[i].callee for i in exercised}
    entered: list[str] = []
    for i in exercised:
        caller = flow.steps[i].caller_qualified or flow.steps[i].caller
        if caller not in called and caller not in entered:
            entered.append(caller)
    return Slice(exercised, tuple(entered))
