# SPDX-License-Identifier: MIT
"""A function's activity diagram, from its parsed body (round 5, P5.5; owner Q/A 2026-11-20).

@brief Tests activity steps and their SVG.
@version 1
"""

from __future__ import annotations

from clew.wiki.activity import COND, ELSE, EXIT, LOOP, STMT, activity_svg, steps_of

_PY = '''\
def load(items):
    """Load."""
    out = []
    for item in items:
        if item:
            out.append(item)
        else:
            continue
    return out
'''

_CPP = """\
int load(int n) {
    int out = 0;
    for (int i = 0; i < n; ++i) {
        if (i % 2) {
            out += i;
        } else {
            out -= 1;
        }
    }
    return out;
}
"""

_EXPECTED = [
    (STMT, 0),
    (LOOP, 0),
    (COND, 1),
    (STMT, 2),
    (ELSE, 1),
    (STMT, 2),
    (EXIT, 0),
]


def test_python_steps_follow_the_control_flow_with_absolute_lines() -> None:
    """@brief `ast`: the docstring is not a step; lines are the file's (the body starts at 20)."""
    steps = steps_of(_PY.splitlines(), "src/m.py", first_line=20)
    assert [(s.kind, s.depth) for s in steps] == _EXPECTED
    assert [s.first for s in steps] == [22, 23, 24, 25, 26, 27, 28]
    assert steps[1].text == "for item in items" and steps[-1].text == "return out"


def test_cpp_steps_follow_the_same_shape() -> None:
    """@brief tree-sitter: the same seven steps for the C++ twin."""
    steps = steps_of(_CPP.splitlines(), "src/m.cpp", first_line=1)
    assert [(s.kind, s.depth) for s in steps] == _EXPECTED
    assert steps[2].text == "if (i % 2)" and steps[-1].text == "return out;"


def test_the_svg_carries_each_steps_lines_for_lighting() -> None:
    """@brief `data-l` per step, a loop back edge, an accessible label, no script."""
    svg = activity_svg(steps_of(_PY.splitlines(), "src/m.py", 20), "load")
    assert svg.count('class="step ') == 7 and 'data-l="25-25"' in svg
    assert 'class="loop-back"' in svg and 'aria-label="activity of load: 7 steps"' in svg
    assert "<script" not in svg


def test_an_unknown_language_has_no_diagram() -> None:
    """@brief No parser: no steps, no SVG."""
    assert steps_of(["fn x() {}"], "src/m.rs", 1) == [] and activity_svg([], "x") == ""


def test_an_elif_is_a_condition_at_the_same_depth() -> None:
    """@brief `elif` is not `else` + nested `if`; a final `else` keeps its own line."""
    src = (
        "def f(x):\n    if x > 1:\n        a()\n    elif x:\n        b()\n    else:\n        c()\n"
    )
    steps = steps_of(src.splitlines(), "m.py", 1)
    assert [(s.kind, s.text, s.first, s.depth) for s in steps] == [
        (COND, "if x > 1", 2, 0),
        (STMT, "a()", 3, 1),
        (COND, "elif x", 4, 0),
        (STMT, "b()", 5, 1),
        (ELSE, "else", 6, 0),
        (STMT, "c()", 7, 1),
    ]
