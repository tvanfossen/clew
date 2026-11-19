# SPDX-License-Identifier: MIT
"""A test's slice is drawn as windows split at gaps, and is keyed by file and name (P4; 2.0.0: W10,
W11 of the hard-coded-assumptions review).

W10 (CONFIRMED, my code): `slice_svg` drew ONE window from the first exercised step to the last,
so a test that ran steps 2 and 40 of a flow drew 38 dimmed steps between them. A gap wider than
the padding on both sides now splits the slice into windows, and what lies between is counted.

W11 (CONFIRMED): `imports._context_test` kept only the bare function name, so `test_x` in
`tests/test_a.py` and `test_x` in `tests/test_b.py` were one test whose slices merged. A per-test
coverage key is now `file::name`; the page for a name draws each definition's own slices under
its file. The bare name is still what a requirement's evidence shows.

@brief Tests slice windows and per-test identity.
@version 1
"""

from __future__ import annotations

from types import SimpleNamespace

from clew.wiki.flow import Flow, Lane, Step
from clew.wiki.imports import _context_test
from clew.wiki.slices import Slice, slice_svg, test_name


def _flow(n: int) -> Flow:
    """@brief A straight flow of n steps. @return Flow."""
    steps = tuple(
        Step(
            caller=f"f{i}",
            caller_qualified=f"f{i}",
            callee=f"f{i + 1}",
            callee_qualified=f"f{i + 1}",
            from_lane="a",
            to_lane="a",
            file="a.c",
            line=i + 1,
            depth=1,
        )
        for i in range(n)
    )
    return Flow(
        entry="f0",
        entry_qualified="f0",
        depth=1,
        lane_strategy="file",
        lanes=(Lane("a", "a"),),
        steps=steps,
    )


def test_a_slice_with_a_gap_is_two_windows_with_the_gap_counted() -> None:
    """@brief Steps 2 and 40 of 50: two windows, the 33 steps between counted, not drawn."""
    html = slice_svg(_flow(50), Slice(exercised=(2, 40)), pad=2)
    assert html.count("<svg") == 2
    assert "… 33 steps between" in html
    assert "… 45 later steps" not in html


def test_adjacent_exercised_steps_stay_one_window() -> None:
    """@brief Steps 2 and 5 with pad 2: the windows overlap, so one is drawn."""
    assert slice_svg(_flow(50), Slice(exercised=(2, 5)), pad=2).count("<svg") == 1


def test_a_per_test_key_carries_the_file() -> None:
    """@brief pytest node id → `file::name`; parameters and classes dropped; setup phase ignored."""
    assert _context_test("tests/test_a.py::TestK::test_x[p::q]|run") == "tests/test_a.py::test_x"
    assert _context_test("tests/test_b.py::test_x|run") == "tests/test_b.py::test_x"
    assert _context_test("tests/test_b.py::test_x|setup") == ""
    assert test_name("tests/test_b.py::test_x") == "test_x"
    assert test_name("an LCOV TN name") == "an LCOV TN name"


def test_two_namesakes_keep_their_own_slices_on_the_page() -> None:
    """@brief One page, two definitions, each with its own flows listed under its file."""
    from clew.wiki.testpages import _exercises

    page = lambda name: SimpleNamespace(name=name, title=f"Flow {name}", steps=3, flow=None)  # noqa: E731
    ctx = {
        "slices": {
            "tests/test_a.py::test_x": [(page("alpha"), Slice())],
            "tests/test_b.py::test_x": [(page("beta"), Slice())],
        }
    }
    defs = [SimpleNamespace(file="tests/test_a.py"), SimpleNamespace(file="tests/test_b.py")]
    html = _exercises("test_x", ctx, defs)
    assert html.index("tests/test_a.py") < html.index("Flow alpha") < html.index("tests/test_b.py")
    assert html.index("tests/test_b.py") < html.index("Flow beta")
