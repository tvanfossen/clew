# SPDX-License-Identifier: MIT
"""A test is a slice of a master flow (round 5, R5-4a).

OWNER 2026-11-17: "a test itself doesn't need a sequence diagram, a test case is testing a portion
OF a sequence diagram". Per-test coverage says which lines a test ran; a master-flow step is
EXERCISED by a test when its call-site line ran in that test. The test ENTERS the flow at a
function whose calls it ran while no exercised step called that function — the test called it
itself. That is the portion of the diagram the test validates, measured, not guessed.

@brief Tests for test slices of master flows.
@version 1
"""

from __future__ import annotations

from clew.wiki.flow import Flow, Lane, Step
from clew.wiki.slices import slice_of, lines_per_test


## @brief One step of a hand-built flow.
## @param caller The caller.
## @param callee The callee.
## @param line The call site's line in `src/app.py`.
## @param depth The step's call level.
## @return The step.
## @version 1
def _step(caller: str, callee: str, line: int, depth: int) -> Step:
    """@brief Build a step. @return Step."""
    return Step(
        caller=caller,
        caller_qualified=caller,
        callee=callee,
        callee_qualified=callee,
        from_lane="src/app.py",
        to_lane="src/app.py",
        file="src/app.py",
        line=line,
        depth=depth,
        site_file="src/app.py",
    )


## main → load (10) → parse (20) → check (21); main → save (11) → write (30).
_FLOW = Flow(
    entry="main",
    entry_qualified="main",
    depth=3,
    lane_strategy="files",
    lanes=(Lane(id="src/app.py", label="src/app.py"),),
    steps=(
        _step("main", "load", 10, 1),
        _step("load", "parse", 20, 2),
        _step("load", "check", 21, 2),
        _step("main", "save", 11, 1),
        _step("save", "write", 30, 2),
    ),
)

## coverage.py's shape: {file: {line: tests}}.
_CONTEXTS = {
    "src/app.py": {
        10: {"test_main"},
        11: {"test_main"},
        20: {"test_main", "test_load"},
        21: {"test_load"},
        30: {"test_main"},
    }
}


def test_lines_are_grouped_per_test() -> None:
    """@brief {file: {line: tests}} turns into {test: {file: lines}}."""
    lines = lines_per_test(_CONTEXTS)
    assert lines["test_load"] == {"src/app.py": {20, 21}}
    assert lines["test_main"]["src/app.py"] == {10, 11, 20, 30}


def test_a_step_is_exercised_when_its_call_site_ran_in_the_test() -> None:
    """test_main ran lines 10, 11, 20, 30 but not 21: check() was never called from load in that
    test, so step 2 (load → check) is not part of what test_main validates.

    @brief Exercised = call-site line ran in this test.
    """
    cut = slice_of(_FLOW, lines_per_test(_CONTEXTS)["test_main"])
    assert cut.exercised == (0, 1, 3, 4)
    assert cut.entered == ("main",)


def test_a_test_that_calls_into_the_middle_enters_there() -> None:
    """test_load called load() itself: its calls ran (20, 21) but the step main → load did not,
    so the test enters the flow at load, and main's own steps are outside its slice.

    @brief Mid-flow entry is where the test called in.
    """
    cut = slice_of(_FLOW, lines_per_test(_CONTEXTS)["test_load"])
    assert cut.exercised == (1, 2)
    assert cut.entered == ("load",)


def test_a_test_that_ran_none_of_the_flow_has_an_empty_slice() -> None:
    """@brief Nothing ran → nothing exercised, nowhere entered (and never an error)."""
    cut = slice_of(_FLOW, {"src/other.py": {1}})
    assert cut.exercised == () and cut.entered == ()


def test_a_slice_is_drawn_as_a_window_of_the_master_flow() -> None:
    """THE PORTION OF THE DIAGRAM: the window runs from `pad` steps before the first exercised step
    to `pad` after the last, numbered as in the master flow; exercised steps are lit (`ex`), the
    rest dimmed (`dim`); the test's entry is marked; the steps outside the window are counted.

    @brief Window of the master flow with the slice lit.
    """
    import re

    from clew.wiki.slices import slice_svg

    cut = slice_of(_FLOW, lines_per_test(_CONTEXTS)["test_load"])
    html = slice_svg(_FLOW, cut, pad=0)
    groups = dict(re.findall(r'<g class="st ([a-z ]+)" data-step="(\d+)"', html))
    assert {v: k for k, v in groups.items()} == {"1": "ex entry", "2": "ex"}
    assert ">2<" in html and ">3<" in html  # master numbering kept
    assert "test enters" in html
    assert "1 earlier step" in html and "2 later steps" in html
    wide = slice_svg(_FLOW, cut, pad=1)
    assert 'data-step="0"' in wide and 'class="st dim" data-step="3"' in wide


def test_every_test_s_slice_of_a_flow_comes_from_one_pass_over_its_steps() -> None:
    """A FLOW PAGE NEEDS ALL ITS TESTS' SLICES at once (clew: ~2,900 tests); `slices_of` reads them
    from the steps' call sites in one pass, and agrees with `slice_of` test by test. A test that
    touched none of the flow is absent, not an empty slice.

    @brief All slices of a flow, equal to the per-test ones.
    """
    from clew.wiki.slices import slices_of

    every = slices_of(_FLOW, _CONTEXTS)
    per_test = lines_per_test(_CONTEXTS)
    assert set(every) == {"test_main", "test_load"}
    assert all(every[t] == slice_of(_FLOW, per_test[t]) for t in every)
