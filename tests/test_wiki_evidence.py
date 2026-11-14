# SPDX-License-Identifier: MIT
"""Requirement evidence: JUnit results and Cobertura coverage joined to the requirement trace.

1.4.0 Track 4, W4 (#67: the Python consumer's "skipped, failed and not-run are different", the
fifth consumer's PASS / GAP / MISSING / TARGET tiers). A requirement's evidence tier comes from
the results of the tests linked to it:

  PASS     a linked test passed and none failed
  GAP      a linked test failed or errored
  TARGET   every linked result is a skip of a test declared target-only (needs hardware)
  NOT_RUN  linked tests exist and were skipped, or have no result in the reports given
  MISSING  no test is linked at all

TARGET IS NOT MISSING and NOT_RUN IS NOT GAP: collapsing them reports false gaps for host-only CI,
which is the exact complaint. Parametrized cases (`test_x[a]`, `test_x[b]`) fold into `test_x`.

@brief Tests for clew.wiki.evidence.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.wiki.evidence import parse_cobertura, parse_junit, requirement_evidence

_JUNIT = """<?xml version="1.0"?>
<testsuites>
  <testsuite name="s">
    <testcase classname="tests.test_a" name="test_ok[one]"/>
    <testcase classname="tests.test_a" name="test_ok[two]"/>
    <testcase classname="tests.test_a" name="test_bad"><failure message="boom"/></testcase>
    <testcase classname="tests.test_a" name="test_flash"><skipped message="needs hardware"/></testcase>
    <testcase classname="tests.test_a" name="test_later"><skipped/></testcase>
  </testsuite>
</testsuites>
"""

_COBERTURA = """<?xml version="1.0"?>
<coverage><packages><package><classes>
  <class filename="src/a.c"><lines>
    <line number="10" hits="3"/><line number="11" hits="0"/><line number="30" hits="0"/>
  </lines></class>
</classes></package></packages></coverage>
"""


def test_parametrized_cases_fold_and_statuses_are_distinct(tmp_path: Path) -> None:
    """@brief test_ok[one]/[two] fold to test_ok; failed and skipped are kept apart.
    @return None.
    @version 1
    """
    report = tmp_path / "junit.xml"
    report.write_text(_JUNIT)
    results = parse_junit([report])
    assert results["test_ok"].status == "passed" and results["test_ok"].cases == 2
    assert results["test_bad"].status == "failed"
    assert results["test_flash"].status == "skipped"


def test_cobertura_lines_are_read_per_file(tmp_path: Path) -> None:
    """@brief Hit lines per file.
    @return None.
    @version 1
    """
    report = tmp_path / "coverage.xml"
    report.write_text(_COBERTURA)
    assert parse_cobertura(report) == {"src/a.c": {10: 3, 11: 0, 30: 0}}


@pytest.fixture()
def traced(tmp_path: Path) -> Path:
    """@brief A minimal index with five requirements and their links. @return DB path."""
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER, definition TEXT);
        CREATE TABLE requirements (id TEXT PRIMARY KEY, block TEXT, title TEXT, acceptance TEXT,
            priority TEXT);
        CREATE TABLE req_edges (memberdef_rowid INTEGER, req_id TEXT);
        CREATE TABLE req_test_edges (test_memberdef_rowid INTEGER, req_id TEXT);
        INSERT INTO path VALUES (1, 'src/a.c', 1), (2, 'tests/test_a.py', 1);
        INSERT INTO memberdef VALUES
            (1, 'function', 'impl', 1, 1, 10, 20, 'void impl'),
            (2, 'function', 'test_ok', 2, 2, 1, 2, 'test_ok'),
            (3, 'function', 'test_bad', 2, 2, 3, 4, 'test_bad'),
            (4, 'function', 'test_flash', 2, 2, 5, 6, 'test_flash'),
            (5, 'function', 'test_later', 2, 2, 7, 8, 'test_later'),
            (6, 'function', 'dead', 1, 1, 30, 31, 'void dead');
        INSERT INTO requirements VALUES
            ('R-PASS', '', 'p', '', ''), ('R-GAP', '', 'g', '', ''), ('R-TARGET', '', 't', '', ''),
            ('R-NOTRUN', '', 'n', '', ''), ('R-MISSING', '', 'm', '', '');
        INSERT INTO req_edges VALUES (1, 'R-PASS'), (6, 'R-MISSING');
        INSERT INTO req_test_edges VALUES (2, 'R-PASS'), (3, 'R-GAP'), (2, 'R-GAP'),
            (4, 'R-TARGET'), (5, 'R-NOTRUN');
        """
    )
    conn.commit()
    conn.close()
    return db


def test_each_requirement_gets_its_tier(traced: Path, tmp_path: Path) -> None:
    """@brief PASS, GAP, TARGET, NOT_RUN and MISSING, each from its own evidence.
    @return None.
    @version 1
    """
    junit = tmp_path / "junit.xml"
    junit.write_text(_JUNIT)
    cov = tmp_path / "coverage.xml"
    cov.write_text(_COBERTURA)
    rows = {
        r.req_id: r
        for r in requirement_evidence(
            traced, junit=[junit], coverage=cov, target_only=("test_flash",)
        )
    }
    assert {k: v.tier for k, v in rows.items()} == {
        "R-PASS": "PASS",
        "R-GAP": "GAP",
        "R-TARGET": "TARGET",
        "R-NOTRUN": "NOT_RUN",
        "R-MISSING": "MISSING",
    }
    assert rows["R-PASS"].implementers_covered == ("impl",)
    assert rows["R-MISSING"].implementers_uncovered == ("dead",)


def test_without_coverage_nothing_claims_to_be_uncovered(traced: Path, tmp_path: Path) -> None:
    """UNMEASURED IS NOT UNCOVERED: no Cobertura report, no coverage fields.

    @brief Coverage is None when no report was given.
    @return None.
    @version 1
    """
    junit = tmp_path / "junit.xml"
    junit.write_text(_JUNIT)
    row = next(r for r in requirement_evidence(traced, junit=[junit]) if r.req_id == "R-PASS")
    assert row.implementers_covered is None and row.implementers_uncovered is None


def test_the_cli_prints_the_trace(
    traced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief `clew wiki trace --junit ... --index DB` prints tiers as JSON.
    @return None.
    @version 1
    """
    import json

    from clew.wiki.command import wiki_main

    junit = tmp_path / "junit.xml"
    junit.write_text(_JUNIT)
    code = wiki_main(
        ["trace", "--junit", str(junit), "--index", str(traced), "--target-only", "test_flash"]
    )
    data = json.loads(capsys.readouterr().out)
    assert code == 0 and data["trace_version"] == 1
    assert {r["req_id"]: r["tier"] for r in data["requirements"]}["R-TARGET"] == "TARGET"
