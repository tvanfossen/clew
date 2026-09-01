# SPDX-License-Identifier: MIT
"""The bisect fast path must agree with the scan on every input, not merely be faster.

`_ast_caller_at_line` answers "which function's body contains this line", once per call site —
466,595 times on a 1,549-file target, and O(functions x call sites) per file. `_FuncRanges`
accelerates it with a bisect, but ONLY when a file's body ranges are disjoint.

WHY THAT CONDITION IS THE WHOLE SAFETY ARGUMENT. When ranges do not overlap, exactly one can
contain a line, so bisect and a scan cannot disagree — the answer is identical by construction.
When ranges NEST (a lambda inside a function, a method inside a class body) "the enclosing
function" has more than one answer, and the two methods would pick different ones.

AND THE EXISTING ANSWER IS AN ACCIDENT WORTH PRESERVING ANYWAY. `_build_function_indexes` issues
its SELECT with no ORDER BY, so "first in list order" is whatever order SQLite returned. Choosing
a better rule (innermost, say) is defensible and is a BEHAVIOUR change to call-edge attribution
that needs a build-version bump — not something a performance patch may do quietly. So the
nested case keeps the scan.

@brief Tests that _FuncRanges' fast path is equivalent to the linear scan.
@version 1
"""

from __future__ import annotations

from clew.call_edges import _FuncRanges, _ast_caller_at_line


## @brief The scan the fast path must agree with, spelled out independently.
## @param rows The file's (rowid, name, bodystart, bodyend) ranges.
## @param line Source line to locate.
## @return The enclosing function's rowid, or None.
## @version 1
def _scan(rows: list[tuple[int, str, int, int]], line: int) -> int | None:
    """WRITTEN OUT HERE RATHER THAN IMPORTED. Comparing the implementation against itself would
    pass whatever it does; this is the reference the fast path is checked against, so it has to
    be a separate statement of the rule.

    @brief Reference implementation: first range in list order containing the line.
    @return The rowid, or None.
    @version 1
    """
    for rid, _name, bs, be in rows:
        if bs <= line <= be:
            return rid
    return None


## @brief On disjoint ranges the bisect path matches the scan for every line.
## @version 1
def test_disjoint_ranges_agree_with_the_scan_on_every_line() -> None:
    """EXHAUSTIVE OVER THE LINE SPACE, not sampled. The interesting inputs are the boundaries —
    the first and last line of a body, the gaps between bodies, and lines before the first and
    after the last — and an exhaustive sweep over a small range covers all of them without
    anyone having to enumerate which ones matter.

    @brief Bisect equals scan on disjoint ranges.
    @version 1
    """
    rows = [(10, "a", 1, 5), (20, "b", 7, 12), (30, "c", 20, 25)]
    ranges = _FuncRanges(rows)
    for line in range(0, 30):
        assert ranges.caller_at(line) == _scan(rows, line), f"disagreement at line {line}"


## @brief Ranges given out of order are still located correctly.
## @version 1
def test_unordered_input_is_handled() -> None:
    """`_build_function_indexes` has NO `ORDER BY`, so the rows arrive in whatever order SQLite
    produced. A bisect over an unsorted list would return nonsense, so the sort is not an
    optimisation detail — it is a correctness precondition, and this pins it.

    @brief Input order does not affect the answer.
    @version 1
    """
    rows = [(30, "c", 20, 25), (10, "a", 1, 5), (20, "b", 7, 12)]
    ranges = _FuncRanges(rows)
    for line in range(0, 30):
        assert ranges.caller_at(line) == _scan(rows, line), f"disagreement at line {line}"


## @brief Nested ranges fall back to the scan and keep its exact answer.
## @version 1
def test_nested_ranges_keep_the_scan_answer() -> None:
    """THE CASE THE FAST PATH MUST REFUSE. A lambda at lines 4-6 inside a function at 1-20 means
    two ranges contain line 5; bisect would return the inner one and the scan returns whichever
    is first in list order. Preserving the scan's answer is what keeps this a cost change rather
    than a silent re-attribution of call edges.

    Asserted against the scan rather than against a hardcoded rowid, so the test states the
    property ("same answer as before") rather than blessing one of the two candidates.

    @brief Nesting falls back to the scan.
    @version 1
    """
    rows = [(10, "outer", 1, 20), (20, "lambda", 4, 6)]
    ranges = _FuncRanges(rows)
    for line in range(0, 25):
        assert ranges.caller_at(line) == _scan(rows, line), f"disagreement at line {line}"
    ## Anti-vacuity: the nesting must be real, or this test is the disjoint case again.
    assert ranges.caller_at(5) == 10, "expected the scan's first-in-list-order answer"


## @brief Touching ranges count as nesting, not as disjoint.
## @version 1
def test_touching_ranges_are_treated_as_overlapping() -> None:
    """A boundary the disjointness test has to get right: bodies at 1-5 and 5-9 SHARE line 5, so
    they are not disjoint and the bisect path must not be taken. An off-by-one in that check
    (`>=` for `>`) would silently enable the fast path on overlapping input, where it can
    disagree — and every other test here would still pass.

    @brief Shared boundary lines disable the fast path.
    @version 1
    """
    rows = [(10, "a", 1, 5), (20, "b", 5, 9)]
    ranges = _FuncRanges(rows)
    for line in range(0, 12):
        assert ranges.caller_at(line) == _scan(rows, line), f"disagreement at line {line}"


## @brief An empty file and a plain list both still work.
## @version 1
def test_empty_and_plain_list_inputs() -> None:
    """`file_funcs.get(rowid, [])` hands a PLAIN list when a file has no functions, so
    `_ast_caller_at_line` must keep working on one — the isinstance check exists for exactly
    that path.

    @brief Empty and non-accelerated inputs are handled.
    @version 1
    """
    assert _FuncRanges([]).caller_at(3) is None
    assert _ast_caller_at_line([], 3) is None
    assert _ast_caller_at_line([(10, "a", 1, 5)], 3) == 10
    assert _ast_caller_at_line([(10, "a", 1, 5)], 9) is None
