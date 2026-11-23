# SPDX-License-Identifier: MIT
"""Standard test structures (owner 2026-11-15: "allow for catch2, pytest, ceedling, gcovr, standard
test structures").

A test is recognised by its framework's own shape, not only by a `test_` name: a Catch2 / doctest
`TEST_CASE` or `SCENARIO`, a GoogleTest `TEST` / `TEST_F`, a Boost `BOOST_AUTO_TEST_CASE` — each
indexed as a row named after the macro, whose test name is the macro's first argument — a pytest or
Unity / Ceedling `test_*` function. Results come from each framework's own report: Ceedling's XML
report, Unity's text output, GoogleTest's XML (where `notrun` is a skip).

@brief Tests for clew.wiki.frameworks and the framework result formats.
@version 2
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from clew.wiki.config import EvidenceInputs
from clew.wiki.evidence import parse_junit, requirement_evidence
from clew.wiki.frameworks import recognise_test
from clew.wiki.imports import parse_results


@pytest.mark.parametrize(
    ("name", "args", "path", "expected"),
    [
        (
            "SCENARIO",
            '("a store loads", "[store]")',
            "tests/test_store.cpp",
            ## Round 4: also filed as "Scenario: …", the name Catch2's reports give it.
            ("a store loads", ("a store loads", "Scenario: a store loads")),
        ),
        ("TEST_CASE", '("bad construct")', "tests/unit.cpp", ("bad construct", ("bad construct",))),
        (
            "TEST_F",
            "(StoreTest, Loads)",
            "tests/store_test.cc",
            ("StoreTest.Loads", ("Loads", "StoreTest.Loads")),
        ),
        (
            "TEST",
            "(Store, Saves)",
            "tests/store_test.cc",
            ("Store.Saves", ("Saves", "Store.Saves")),
        ),
        (
            "BOOST_AUTO_TEST_CASE",
            "(store_loads)",
            "test/store.cpp",
            ("store_loads", ("store_loads",)),
        ),
        ("test_loads", "(void)", "test/test_store.c", ("test_loads", ("test_loads",))),
        ("test_ok", "(tmp_path)", "tests/test_a.py", ("test_ok", ("test_ok",))),
        ("helper", "()", "tests/test_a.py", None),
        ("SCENARIO", "", "src/scenario.cpp", None),
    ],
)
def test_each_framework_shape_is_recognised(name, args, path, expected) -> None:
    """A MACRO ROW OUTSIDE TEST CODE is not a test (`SCENARIO` may be anyone's function).

    @brief Framework recognition: display name and the names results are filed under.
    """
    assert recognise_test(name, args, path) == expected


def test_ceedling_and_unity_results_are_read(tmp_path: Path) -> None:
    """@brief Ceedling's XML report and Unity's text output."""
    ceedling = tmp_path / "report.xml"
    ceedling.write_text(
        "<TestRun><FailedTests><Test id='1'><Name>test/test_store.c::test_saves</Name></Test>"
        "</FailedTests><SuccessfulTests><Test id='2'><Name>test/test_store.c::test_loads</Name>"
        "</Test></SuccessfulTests><IgnoredTests><Test id='3'><Name>test/test_store.c::test_hw</Name>"
        "</Test></IgnoredTests></TestRun>"
    )
    unity = tmp_path / "unity.txt"
    unity.write_text(
        "test/test_store.c:10:test_loads:PASS\ntest/test_store.c:20:test_saves:FAIL: Expected 1\n"
        "test/test_store.c:30:test_hw:IGNORE\n-----------------------\n3 Tests 1 Failures 1 Ignored\n"
    )
    expected = {"test_loads": "passed", "test_saves": "failed", "test_hw": "skipped"}
    assert {k: v.status for k, v in parse_results("ceedling", ceedling).items()} == expected
    assert {k: v.status for k, v in parse_results("unity", unity).items()} == expected


def test_a_googletest_notrun_case_is_a_skip(tmp_path: Path) -> None:
    """GoogleTest writes a DISABLED test as `status="notrun"` with no child element; read as passed,
    it would turn an unexecuted test into evidence.

    @brief gtest XML through the JUnit reader.
    """
    report = tmp_path / "gtest.xml"
    report.write_text(
        '<testsuites><testsuite name="Store"><testcase name="Loads" status="run" result="completed"/>'
        '<testcase name="DISABLED_Flash" status="notrun" result="suppressed"/>'
        '<testcase name="Saves" status="run" result="skipped"><skipped/></testcase></testsuite></testsuites>'
    )
    results = parse_junit([report])
    assert results["Loads"].status == "passed" and results["DISABLED_Flash"].status == "skipped"


def test_a_catch2_scenario_reaching_an_implementer_is_linked_by_its_name(tmp_path: Path) -> None:
    """@brief Inference walks back to a SCENARIO row and files it under its Catch2 name."""
    db = tmp_path / "c.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT);
        CREATE TABLE requirements (id TEXT PRIMARY KEY, block TEXT, title TEXT, acceptance TEXT,
            priority TEXT);
        CREATE TABLE req_edges (memberdef_rowid INTEGER, req_id TEXT);
        CREATE TABLE req_test_edges (test_memberdef_rowid INTEGER, req_id TEXT);
        CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, source TEXT,
            confidence TEXT, via_macro_rowid INTEGER);
        INSERT INTO path VALUES (1, 'src/store.cpp', 1), (2, 'tests/test_store.cpp', 1);
        INSERT INTO memberdef VALUES
            (1, 'function', 'load', 1, 1, 10, 20, 'void load', '()', '', ''),
            (2, 'function', 'SCENARIO', 2, 2, 5, 9, 'SCENARIO', '("a store loads", "[store]")', '', '');
        INSERT INTO requirements VALUES ('R-1', '', 'load', '', '');
        INSERT INTO req_edges VALUES (1, 'R-1');
        INSERT INTO call_edges VALUES (2, 1, 'ast', 'resolved', NULL);
        """
    )
    conn.commit()
    conn.close()
    report = tmp_path / "catch.xml"
    report.write_text(
        '<Catch2TestRun><TestCase name="a store loads"><OverallResult success="true"/></TestCase>'
        "</Catch2TestRun>"
    )
    inputs = EvidenceInputs(results=(("catch2", "catch.xml"),), evidence_fields=())
    (row,) = requirement_evidence(db, junit=[], inputs=inputs, repo_root=tmp_path)
    assert row.tests == (("a store loads", "passed"),) and row.inferred_tests == ("a store loads",)
    assert row.tier == "PASS"
    json.dumps(row.tests)


def test_a_macro_test_gets_its_own_page_under_its_framework_name(tmp_path: Path) -> None:
    """FOUND ON ENTROPIC (round 4): 2,009 Catch2 tests and 11 test pages — a SCENARIO is a macro
    row named `SCENARIO` in the index, so test pages looked for a function named after the scenario
    and found none. A test page resolves tests the way the evidence does (`recognise_test`).

    @brief R6: Catch2 / GoogleTest cases get test pages.
    """
    import sqlite3

    from clew.wiki.testpages import _test_definitions

    db = tmp_path / "clew.db"
    with sqlite3.connect(db) as conn:
        conn.executescript(
            """
            CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
            CREATE TABLE test_scope (path_rowid INTEGER);
            CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,
                file_id INTEGER, bodyfile_id INTEGER, definition TEXT, argsstring TEXT,
                briefdescription TEXT, bodystart INTEGER, bodyend INTEGER, line INTEGER);
            INSERT INTO path VALUES (1, 'tests/test_x.cpp', 1);
            INSERT INTO test_scope VALUES (1);
            INSERT INTO memberdef VALUES (1, 'function', 'SCENARIO', 1, 1, 'SCENARIO',
                '("Loads a file", "[load]")', '', 3, 9, 3);
            """
        )
        defs = _test_definitions(conn, {"Loads a file"})
    assert [(d.name, d.file, d.start) for d in defs] == [("Loads a file", "tests/test_x.cpp", 3)]


def test_catch2_section_cases_fold_into_their_test_case(tmp_path: Path) -> None:
    """FOUND ON SASSAFRAS-CLASS (round 4): Catch2's own JUnit reporter writes one testcase per
    SECTION PATH ("Scenario: X/Given: a/When: b"), under classname `<binary>.global`; the index
    knows the test case ("Scenario: X"), so 230 of 267 tested requirements read NOT_RUN. Section
    cases fold into their test case, worst status first — and a FAILURE keeps its message, which
    a test page shows in red (only skip messages were kept).

    @brief Catch2 section folding; failure messages kept.
    """
    from clew.wiki.evidence import parse_junit

    report = tmp_path / "catch2.xml"
    report.write_text(
        '<testsuites><testsuite name="t">'
        '<testcase classname="t.global" name="Scenario: X/Given: a" status="run"/>'
        '<testcase classname="t.global" name="Scenario: X/Given: a/When: b" status="run">'
        '<failure message="REQUIRE( n == 2 )">expanded: 1 == 2</failure></testcase>'
        '<testcase classname="t.global" name="Scenario: Y" status="run"/>'
        "</testsuite></testsuites>"
    )
    results = parse_junit([report])
    assert set(results) == {"Scenario: X", "Scenario: Y"}
    assert results["Scenario: X"].status == "failed" and results["Scenario: X"].cases == 2
    assert "REQUIRE( n == 2 )" in results["Scenario: X"].message


def test_a_catch2_scenario_is_found_under_the_name_catch2_reports() -> None:
    """FOUND ON SASSAFRAS-CLASS (round 4): Catch2 reports a SCENARIO as "Scenario: <name>" (its
    JUnit and ctest's discovered names alike), while the index holds the macro's string. The
    scenario is filed under both, so its result is found; its display name stays the string.

    @brief SCENARIO lookup names include Catch2's "Scenario: " form.
    """
    from clew.wiki.frameworks import recognise_test

    test = recognise_test("SCENARIO", '("loads a file", "[load]")', "tests/test_x.cpp")
    assert test == ("loads a file", ("loads a file", "Scenario: loads a file"))


def test_a_test_named_function_outside_test_code_is_not_a_test() -> None:
    """FOUND ON CLEW'S OWN WIKI (round 4): `test_pages`, `test_link`, `test_id` — production
    functions in clew/wiki/ — were found as "tests" by the call-graph walk, the same defect R9
    fixed for tagged tests. A plain `test*` name is a test only in test code, as the macro forms
    already required.

    @brief recognise_test: plain names need a test path.
    """
    from clew.wiki.frameworks import recognise_test

    assert recognise_test("test_pages", "", "clew/wiki/testpages.py") is None
    assert recognise_test("test_load", "", "tests/test_data.py") == ("test_load", ("test_load",))
