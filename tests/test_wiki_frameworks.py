# SPDX-License-Identifier: MIT
"""Standard test structures (owner 2026-11-15: "allow for catch2, pytest, ceedling, gcovr, standard
test structures").

A test is recognised by its framework's own shape, not only by a `test_` name: a Catch2 / doctest
`TEST_CASE` or `SCENARIO`, a GoogleTest `TEST` / `TEST_F`, a Boost `BOOST_AUTO_TEST_CASE` — each
indexed as a row named after the macro, whose test name is the macro's first argument — a pytest or
Unity / Ceedling `test_*` function. Results come from each framework's own report: Ceedling's XML
report, Unity's text output, GoogleTest's XML (where `notrun` is a skip).

@brief Tests for clew.wiki.frameworks and the framework result formats.
@version 1
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
            ("a store loads", ("a store loads",)),
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
