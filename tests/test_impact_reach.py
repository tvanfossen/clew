# SPDX-License-Identifier: MIT
"""The impact report names the tests covering each requirement and the changes that reach none
(2.1, clew#74 items 2-4).

FOUND by entropic (v2.14.6): the whole fix was two `@utility` helpers, `gemma4_dropped_tool_spans`
and `keep_dropped_tool_text`, so `impact.json` named no requirement and a consumer selecting tests
from it would have run nothing. Now:

- each entry lists its covering tests as `{name, file}`: Catch2 cases by title (`clew.catch2`)
  and test functions carrying `@req`, read from the test tree with no index;
- a changed function with no `@req` is walked up its callers (the index's `call_edges`, at most
  `VIA_DEPTH` calls) to the nearest `@req` functions; the requirements reached list it with
  `via`, the chain of callers, so an inferred link reads differently from a direct one;
- a change that reaches no requirement is listed under `unmapped` with the reason, and a changed
  file holding no function under `unmapped_files`, never dropped.

ABSENT WHEN NOT COMPUTED: a report built without the reach step keeps its 2.0.0 shape exactly.

@brief Tests covering tests, `via` and unmapped changes in the impact report.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

from clew.guard.impact import (
    ChangedFunction,
    build_impact_report,
    build_report,
    format_json,
    format_markdown,
)
from clew.guard.config import load_config
from clew.guard.reach import Reach, TestRef, covering_tests

CPP_TESTS = """#include <catch2/catch_test_macros.hpp>
TEST_CASE("adds two numbers", "[core][REQ-A-001]") { }
"""

PY_TESTS = '''"""@brief Tests."""


## @brief Checks the adder.
## @req REQ-A-001
def test_adds():
    """@brief Adds."""
'''

SRC = """/// @brief Helper.
/// @utility
static int helper(int x) { return x + 1; }

/// @brief Entry.
/// @req REQ-A-001
int entry(int x) { return helper(x); }

/// @brief Orphan.
/// @utility
int orphan(void) { return 0; }
"""


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "tests" / "add_test.cpp").write_text(CPP_TESTS)
    (repo / "tests" / "test_add.py").write_text(PY_TESTS)
    (repo / "src" / "a.cpp").write_text(SRC)
    return repo


def test_covering_tests_are_read_from_the_test_tree(tmp_path: Path) -> None:
    """@brief A Catch2 case by title and a Python test function by name, each with its file."""
    repo = _repo(tmp_path)
    found = covering_tests(
        repo,
        {"REQ-A-001"},
        catalog={"REQ-A-001"},
        files=["tests/add_test.cpp", "tests/test_add.py", "src/a.cpp"],
        ## The gate's defaults (its languages): an empty mapping enables no parser.
        config=load_config(tmp_path / "no-such.yaml"),
    )
    assert found["REQ-A-001"] == [
        TestRef(name="adds two numbers", file="tests/add_test.cpp"),
        TestRef(name="test_adds", file="tests/test_add.py"),
    ]


def _db(tmp_path: Path, repo: Path) -> Path:
    from clew.cli import _build_argparser, _run_pipeline

    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return db


def test_an_untagged_change_reaches_a_requirement_through_its_callers(tmp_path: Path) -> None:
    """@brief `helper` → `entry` (REQ-A-001); `orphan` reaches nothing."""
    repo = _repo(tmp_path)
    reach = Reach(_db(tmp_path, repo))
    assert reach.via(ChangedFunction(name="helper", file_path="src/a.cpp")) == [
        ("REQ-A-001", ["entry"])
    ]
    assert reach.via(ChangedFunction(name="orphan", file_path="src/a.cpp")) == []


def test_the_report_lists_via_tests_and_unmapped(tmp_path: Path) -> None:
    """@brief One entry for REQ-A-001 with `helper` via `entry` and its tests; `orphan` unmapped."""
    repo = _repo(tmp_path)
    reach = Reach(_db(tmp_path, repo))
    reach.tests = {"REQ-A-001": [TestRef(name="adds two numbers", file="tests/add_test.cpp")]}
    changed = [
        ChangedFunction(name="helper", file_path="src/a.cpp"),
        ChangedFunction(name="orphan", file_path="src/a.cpp"),
    ]
    entries, extras = build_report(changed, {}, reach=reach, unmapped_files=["CMakeLists.txt"])
    (entry,) = entries
    assert entry.req_id == "REQ-A-001"
    assert [(f.name, f.via) for f in entry.functions] == [("helper", ["entry"])]
    doc = json.loads(format_json(entries, extras))
    assert doc["entries"][0]["tests"] == [
        {"name": "adds two numbers", "file": "tests/add_test.cpp"}
    ]
    assert doc["entries"][0]["functions"][0]["via"] == ["entry"]
    assert doc["unmapped"] == [
        {"name": "orphan", "file": "src/a.cpp", "reason": "no @req caller within 3 calls"}
    ]
    assert doc["unmapped_files"] == ["CMakeLists.txt"]
    md = format_markdown(entries, extras)
    assert "| Tests |" in md and "adds two numbers" in md and "orphan" in md


def test_without_an_index_an_untagged_change_is_unmapped_and_says_why(tmp_path: Path) -> None:
    """@brief No index: no walk, and the reason names it."""
    reach = Reach(None)
    entries, extras = build_report(
        [ChangedFunction(name="helper", file_path="src/a.cpp")], {}, reach=reach
    )
    assert entries == []
    assert extras.unmapped == [
        {"name": "helper", "file": "src/a.cpp", "reason": "no index to walk callers"}
    ]


def test_a_report_without_the_reach_step_keeps_its_shape() -> None:
    """@brief No reach: the 2.0.0 object, no `tests`, `via` or unmapped keys."""
    entries = build_impact_report(
        [ChangedFunction(name="f", file_path="a.c", reqs=["REQ-A-001"])], {}
    )
    doc = json.loads(format_json(entries))
    assert set(doc) == {"schema_version", "entries"}
    assert "tests" not in doc["entries"][0] and "via" not in doc["entries"][0]["functions"][0]


def test_a_change_in_test_code_is_reported_as_test_code(tmp_path: Path) -> None:
    """FOUND RUNNING entropic's v2.14.6 fix: changed helpers in test files (`count_log_lines` in
    tests/model/model_test_context.h) read "no @req caller", as if product code had lost its
    trace. Test code implements no requirement; it is not walked, and the reason says so.

    @brief Test code is named as test code.
    """
    repo = _repo(tmp_path)
    reach = Reach(_db(tmp_path, repo))
    _entries, extras = build_report(
        [ChangedFunction(name="count_log_lines", file_path="tests/model/helpers.h")],
        {},
        reach=reach,
    )
    assert extras.unmapped == [
        {"name": "count_log_lines", "file": "tests/model/helpers.h", "reason": "test code"}
    ]
