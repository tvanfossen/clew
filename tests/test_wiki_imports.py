# SPDX-License-Identifier: MIT
"""Evidence imports beyond JUnit and Cobertura (1.4.0 W15, W16; owner 2026-11-15).

  * gcov — the `.gcov` text files gcov writes, and gcov's / gcovr's JSON (`.json`, `.json.gz`),
    read into the same per-file line hits a Cobertura report gives;
  * test result formats — CTest's `Test.xml`, TAP, Catch2's XML reporter, pytest-json-report —
    each DECLARED with its format, never sniffed, and folded like JUnit (worst case wins);
  * a requirement → test MAPPING file, for tests the index cannot see a `@req` tag on;
  * Gherkin `.feature` scenarios whose tags name a requirement;
  * test LAYERS (path globs), so a requirement tested in one layer only can be flagged.

Every import is optional and ABSENT when not given: no layers configured means `layers is None`,
not "no layer".

@brief Tests for clew.wiki.imports.
@version 1
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path

import pytest

from clew.wiki.config import EvidenceInputs
from clew.wiki.evidence import requirement_evidence
from clew.wiki.imports import (
    parse_features,
    parse_gcov,
    parse_mapping,
    parse_results,
)

_GCOV = """        -:    0:Source:src/a.c
        -:    0:Graph:a.gcno
        -:    1:#include <a.h>
        5:   10:int impl(void) {
    #####:   11:  if (x) return 1;
       2*:   12:  return 0;
    =====:   13:  never();
        -:   14:}
"""


def test_gcov_text_reads_hits_and_skips_non_executable_lines(tmp_path: Path) -> None:
    """`#####` and `=====` are executable lines with no hits; `-` is not executable at all, so it
    is not a line with zero hits.

    @brief .gcov text → hits.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.c").write_text("x\n")
    report = tmp_path / "build" / "a.c.gcov"
    report.parent.mkdir()
    report.write_text(_GCOV)
    assert parse_gcov([report], tmp_path) == {"src/a.c": {10: 5, 11: 0, 12: 2, 13: 0}}


def test_gcov_json_gz_relativises_absolute_paths(tmp_path: Path) -> None:
    """@brief gcov --json-format output (gzipped) with an absolute file path."""
    doc = {
        "current_working_directory": str(tmp_path / "build"),
        "files": [
            {
                "file": str(tmp_path / "src" / "a.c"),
                "lines": [{"line_number": 10, "count": 4}, {"line_number": 11, "count": 0}],
            }
        ],
    }
    report = tmp_path / "a.gcov.json.gz"
    report.write_bytes(gzip.compress(json.dumps(doc).encode()))
    assert parse_gcov([report], tmp_path) == {"src/a.c": {10: 4, 11: 0}}


_CTEST = """<?xml version="1.0"?>
<Site><Testing>
  <Test Status="passed"><Name>store_loads</Name></Test>
  <Test Status="failed"><Name>store_saves</Name></Test>
  <Test Status="notrun"><Name>store_flash</Name></Test>
</Testing></Site>
"""

_CATCH2 = """<?xml version="1.0"?>
<Catch2TestRun>
  <Group>
    <TestCase name="Store loads"><OverallResult success="true" skips="0"/></TestCase>
    <TestCase name="Store saves"><OverallResult success="false"/></TestCase>
    <TestCase name="Store flash"><OverallResult success="true" skips="1"/></TestCase>
  </Group>
</Catch2TestRun>
"""

_TAP = """TAP version 13
1..4
ok 1 - parses keys
not ok 2 - writes keys
ok 3 - flashes # SKIP no device
not ok 4 - later # TODO not built
"""

_PYTEST_JSON = {
    "tests": [
        {"nodeid": "tests/test_a.py::test_ok[one]", "outcome": "passed"},
        {"nodeid": "tests/test_a.py::test_ok[two]", "outcome": "failed"},
        {"nodeid": "tests/test_a.py::test_skip", "outcome": "skipped"},
        {"nodeid": "tests/test_a.py::test_err", "outcome": "error"},
    ]
}


@pytest.mark.parametrize(
    ("fmt", "text", "expected"),
    [
        (
            "ctest",
            _CTEST,
            {"store_loads": "passed", "store_saves": "failed", "store_flash": "skipped"},
        ),
        (
            "catch2",
            _CATCH2,
            {"Store loads": "passed", "Store saves": "failed", "Store flash": "skipped"},
        ),
        (
            "tap",
            _TAP,
            {
                "parses keys": "passed",
                "writes keys": "failed",
                "flashes": "skipped",
                "later": "skipped",
            },
        ),
        (
            "pytest-json",
            json.dumps(_PYTEST_JSON),
            {"test_ok": "failed", "test_skip": "skipped", "test_err": "error"},
        ),
    ],
)
def test_each_declared_result_format_folds_to_statuses(
    tmp_path: Path, fmt: str, text: str, expected: dict[str, str]
) -> None:
    """A parametrized pytest node folds to its function and takes its WORST case.

    @brief CTest, Catch2, TAP and pytest-json-report results.
    """
    report = tmp_path / "report"
    report.write_text(text)
    assert {k: v.status for k, v in parse_results(fmt, report).items()} == expected


def test_an_unknown_result_format_is_refused(tmp_path: Path) -> None:
    """@brief A format is declared, never guessed."""
    report = tmp_path / "r.xml"
    report.write_text("<x/>")
    with pytest.raises(ValueError, match="unknown"):
        parse_results("nunit", report)


def test_a_mapping_file_reads_yaml_and_csv(tmp_path: Path) -> None:
    """@brief {REQ: [tests]} YAML, or a `req,test` CSV."""
    yml = tmp_path / "map.yaml"
    yml.write_text("R-A: [Store loads, Store saves]\nR-B: store_loads\n")
    csv = tmp_path / "map.csv"
    csv.write_text("req,test\nR-A,Store loads\nR-C,flashes\n")
    assert parse_mapping(yml) == {"R-A": ("Store loads", "Store saves"), "R-B": ("store_loads",)}
    assert parse_mapping(csv) == {"R-A": ("Store loads",), "R-C": ("flashes",)}


_FEATURE = """@R-FEAT
Feature: Pairing
  # a comment
  @R-B @smoke
  Scenario: A tablet pairs
    Given a tablet
    Then it pairs

  Rule: failures are named
    @req:R-C
    Scenario Outline: A pairing fails
      When <x>
      Examples:
        | x |
        | 1 |
"""


def test_gherkin_scenarios_carry_their_own_and_inherited_tags(tmp_path: Path) -> None:
    """A feature's tags apply to each of its scenarios; `@req:ID` and `@ID` both name one.

    @brief Parse .feature scenarios.
    """
    feat = tmp_path / "tests" / "features" / "pair.feature"
    feat.parent.mkdir(parents=True)
    feat.write_text(_FEATURE)
    scenarios = parse_features(tmp_path, ("tests/features/**/*.feature",))
    assert [(s.file, s.line, s.name, s.tags) for s in scenarios] == [
        ("tests/features/pair.feature", 5, "A tablet pairs", ("R-FEAT", "R-B", "smoke")),
        ("tests/features/pair.feature", 11, "A pairing fails", ("R-FEAT", "R-C")),
    ]


@pytest.fixture()
def traced(tmp_path: Path) -> Path:
    """@brief An index: R-A linked to an indexed test, R-B/R-C/R-D only via imports. @return DB."""
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, file_id INTEGER,
            bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER, definition TEXT,
            briefdescription TEXT, detaileddescription TEXT);
        CREATE TABLE requirements (id TEXT PRIMARY KEY, block TEXT, title TEXT, acceptance TEXT,
            priority TEXT);
        CREATE TABLE req_edges (memberdef_rowid INTEGER, req_id TEXT);
        CREATE TABLE req_test_edges (test_memberdef_rowid INTEGER, req_id TEXT);
        -- FIXTURE FIDELITY (2026-11-15): the shipped memberdef carries `argsstring`, which the
        -- trace now reads to name framework test cases.
        INSERT INTO path VALUES (1, 'src/a.c', 1), (2, 'tests/unit/test_a.py', 1);
        INSERT INTO memberdef VALUES
            (1, 'function', 'impl', 1, 1, 10, 13, 'int impl', '', ''),
            (2, 'function', 'test_ok', 2, 2, 1, 2, 'test_ok', '', '');
        INSERT INTO requirements VALUES
            ('R-A', '', 'a', '', ''), ('R-B', '', 'b', '', ''), ('R-C', '', 'c', '', ''),
            ('R-D', '', 'd', '', '');
        ALTER TABLE memberdef ADD COLUMN argsstring TEXT DEFAULT '';
        INSERT INTO req_edges VALUES (1, 'R-A');
        INSERT INTO req_test_edges VALUES (2, 'R-A');
        """
    )
    conn.commit()
    conn.close()
    return db


def test_imports_join_the_trace(traced: Path, tmp_path: Path) -> None:
    """ONE TRACE FROM EVERY SOURCE: an indexed test with a pytest-json result, a scenario with a
    JUnit result under its own name, a Catch2 case linked by the mapping file, and gcov coverage.
    Layers count each requirement's tests by layer; R-D, tested nowhere, has no layers.

    @brief Imported results, mapping, scenarios, gcov and layers in requirement_evidence.
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.c").write_text("x\n")
    (tmp_path / "a.c.gcov").write_text(_GCOV)
    (tmp_path / "r.json").write_text(
        json.dumps({"tests": [{"nodeid": "t.py::test_ok", "outcome": "passed"}]})
    )
    (tmp_path / "c.xml").write_text(_CATCH2)
    (tmp_path / "j.xml").write_text(
        '<testsuite><testcase name="A tablet pairs"/><testcase name="A pairing fails">'
        '<failure message="x"/></testcase></testsuite>'
    )
    (tmp_path / "map.yaml").write_text("R-C: [Store loads]\n")
    feat = tmp_path / "tests" / "features" / "pair.feature"
    feat.parent.mkdir(parents=True)
    feat.write_text(_FEATURE)
    inputs = EvidenceInputs(
        results=(("pytest-json", "r.json"), ("catch2", "c.xml")),
        gcov=("*.gcov",),
        mapping="map.yaml",
        features=("tests/features/*.feature",),
        layers=(("unit", ("tests/unit/*",)), ("bdd", ("tests/features/*",)), ("cpp", ("Store *",))),
        min_layers=2,
    )
    rows = {
        r.req_id: r
        for r in requirement_evidence(
            traced, junit=[tmp_path / "j.xml"], inputs=inputs, repo_root=tmp_path
        )
    }
    assert rows["R-A"].tier == "PASS" and rows["R-A"].implementers_covered == ("impl",)
    assert rows["R-A"].layers == (("unit", 1),)
    assert rows["R-B"].tests == (("tests/features/pair.feature::A tablet pairs", "passed"),)
    assert rows["R-B"].tier == "PASS" and rows["R-B"].layers == (("bdd", 1),)
    assert {t for t, _s in rows["R-C"].tests} == {
        "Store loads",
        "tests/features/pair.feature::A pairing fails",
    }
    assert rows["R-C"].tier == "GAP"
    assert rows["R-C"].layers == (("bdd", 1), ("cpp", 1))
    assert rows["R-D"].tier == "MISSING" and rows["R-D"].layers == ()


def test_before_tests_a_report_a_run_produces_is_not_yet_required(
    traced: Path, tmp_path: Path
) -> None:
    """A PRE-COMMIT HOOK RUNS BEFORE THE TESTS (round 3, P6c, found dogfooding): the JUnit,
    coverage, result and gcov reports are what the test run WRITES, so in pre-commit they do not
    exist yet and the shipped `clew-wiki-check` hook failed every commit of a repository that
    declared them. `before_tests` drops only those; files the repository HOLDS — the mapping,
    feature files, mutation records — are still required, and the full check (after the tests,
    in CI) still names a missing report.

    @brief check_wiki(before_tests=True).
    """
    from clew.wiki.check import check_wiki

    (tmp_path / ".clew.yaml").write_text(
        "wiki:\n  docs: []\n  tests:\n    junit: [build/junit.xml]\n"
        "    coverage: build/coverage.xml\n    results: [{format: tap, path: build/t.tap}]\n"
        "    gcov: ['build/*.gcov']\n    mapping: missing-map.yaml\n"
    )
    early = "\n".join(check_wiki(tmp_path, traced, before_tests=True))
    assert "junit.xml" not in early and "coverage.xml" not in early and "t.tap" not in early
    assert "build/*.gcov" not in early
    assert "missing-map.yaml" in early
    full = "\n".join(check_wiki(tmp_path, traced))
    assert "'build/junit.xml' does not exist" in full


def test_without_layers_the_field_is_absent(traced: Path) -> None:
    """@brief No layers configured → `layers is None`, not ()."""
    row = next(r for r in requirement_evidence(traced, junit=[]) if r.req_id == "R-A")
    assert row.layers is None


def test_check_names_every_missing_import(traced: Path, tmp_path: Path) -> None:
    """A GLOB THAT MATCHES NOTHING is a problem: a misspelled gcov or feature glob would otherwise
    yield a trace that reads as "no coverage measured" or "no scenarios".

    @brief `clew wiki check` covers the W15/W16 inputs.
    """
    from clew.wiki.check import check_wiki

    (tmp_path / "map.yaml").write_text("R-A: [x]\nR-NOPE: [y]\n")
    (tmp_path / ".clew.yaml").write_text(
        "wiki:\n  docs: []\n  tests:\n"
        "    results: [{format: tap, path: missing.tap}, {format: nunit, path: n.xml}]\n"
        "    gcov: ['build/*.gcov']\n    features: ['features/*.feature']\n"
        "    mapping: map.yaml\n"
    )
    problems = "\n".join(check_wiki(tmp_path, traced))
    assert "'missing.tap' does not exist" in problems
    assert "'nunit' is not known" in problems
    assert "'build/*.gcov' matches no file" in problems
    assert "'features/*.feature' matches no file" in problems
    assert "R-NOPE" in problems and "R-A" not in problems.replace("R-A:", "")


def test_the_trace_cli_reads_imports_from_the_config(
    traced: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief `clew wiki trace --config FILE` applies the section's imports."""
    from clew.wiki.command import wiki_main

    (tmp_path / "r.tap").write_text("ok 1 - Store loads\n")
    (tmp_path / "map.yaml").write_text("R-B: [Store loads]\n")
    cfg = tmp_path / "wiki.yaml"
    cfg.write_text(
        "wiki:\n  tests:\n    results: [{format: tap, path: r.tap}]\n    mapping: map.yaml\n"
        "    layers: {cpp: ['Store *']}\n"
    )
    argv = ["trace", "--index", str(traced), "--repo-root", str(tmp_path), "--config", str(cfg)]
    assert wiki_main(argv) == 0
    rows = {r["req_id"]: r for r in json.loads(capsys.readouterr().out)["requirements"]}
    assert rows["R-B"]["tier"] == "PASS" and rows["R-B"]["layers"] == [["cpp", 1]]


def test_tests_named_by_the_catalog_evidence_field_are_linked(traced: Path, tmp_path: Path) -> None:
    """THE CATALOG IS A SOURCE TOO (owner 2026-11-15: clew's own trace read 92 MISSING because its
    tests carry no `@req` tags, while `requirements.yaml` names each requirement's test files in
    `x-evidence`). A test file named there links every test function the index holds in it — a
    FILE-LEVEL claim, so the row records which links came from the catalog.

    @brief `x-evidence` test files link their tests, marked as declared.
    """
    (tmp_path / "requirements.yaml").write_text(
        "- {id: R-D, title: d, x-evidence: 'src/a.c impl; tests/unit/test_a.py.'}\n"
    )
    (tmp_path / "r.json").write_text(
        json.dumps({"tests": [{"nodeid": "t.py::test_ok", "outcome": "passed"}]})
    )
    inputs = EvidenceInputs(results=(("pytest-json", "r.json"),))
    rows = {
        r.req_id: r
        for r in requirement_evidence(traced, junit=[], inputs=inputs, repo_root=tmp_path)
    }
    assert rows["R-D"].tests == (("test_ok", "passed"),) and rows["R-D"].tier == "PASS"
    assert rows["R-D"].declared_tests == ("test_ok",)
    assert rows["R-A"].declared_tests == ()
    off = EvidenceInputs(results=inputs.results, evidence_fields=())
    plain = requirement_evidence(traced, junit=[], inputs=off, repo_root=tmp_path)
    assert next(r for r in plain if r.req_id == "R-D").tier == "MISSING"


def _with_calls(traced: Path, tmp_path: Path) -> Path:
    """@brief A copy of the index where test_infer → helper → impl (R-A) and test_far → a 3-hop chain."""
    import shutil

    db = tmp_path / "calls.db"
    shutil.copyfile(traced, db)
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, source TEXT,
            confidence TEXT, via_macro_rowid INTEGER);
        INSERT INTO path VALUES (3, 'tests/unit/test_b.py', 1);
        INSERT INTO memberdef VALUES
            (3, 'function', 'test_infer', 3, 3, 1, 3, 'test_infer', '', '', ''),
            (4, 'function', 'helper', 1, 1, 20, 22, 'helper', '', '', ''),
            (5, 'function', 'test_far', 3, 3, 5, 7, 'test_far', '', '', ''),
            (6, 'function', 'mid1', 1, 1, 30, 31, 'mid1', '', '', ''),
            (7, 'function', 'mid2', 1, 1, 32, 33, 'mid2', '', '', ''),
            (8, 'function', 'test_bound', 3, 3, 9, 10, 'test_bound', '', '', '');
        INSERT INTO call_edges VALUES (3, 4, 'ast', 'resolved', NULL), (4, 1, 'ast', 'resolved', NULL),
            (5, 6, 'ast', 'resolved', NULL), (6, 7, 'ast', 'resolved', NULL),
            (7, 1, 'ast', 'resolved', NULL), (8, 1, 'binding', 'resolved', NULL);
        """
    )
    conn.commit()
    conn.close()
    return db


def test_tests_that_reach_an_implementer_are_inferred_within_the_depth(
    traced: Path, tmp_path: Path
) -> None:
    """NO TAG NEEDED (owner 2026-11-15: "can't that be inferred?"): a test whose calls reach a
    function tagged with a requirement, within `infer_depth` hops, is linked to it — and the row
    says the link was INFERRED, because reaching code is weaker than verifying it. A deeper chain
    is not linked, and a `binding` edge (a function value passed along) is not a call.

    @brief Call-graph inference of test → requirement links.
    """
    db = _with_calls(traced, tmp_path)
    rows = {
        r.req_id: r
        for r in requirement_evidence(
            db, junit=[], inputs=EvidenceInputs(infer_depth=2), repo_root=tmp_path
        )
    }
    assert rows["R-A"].inferred_tests == ("test_infer",)
    assert {t for t, _s in rows["R-A"].tests} == {"test_ok", "test_infer"}
    deeper = requirement_evidence(
        db, junit=[], inputs=EvidenceInputs(infer_depth=3), repo_root=tmp_path
    )
    assert next(r for r in deeper if r.req_id == "R-A").inferred_tests == ("test_far", "test_infer")
    off = requirement_evidence(
        db, junit=[], inputs=EvidenceInputs(infer_depth=0), repo_root=tmp_path
    )
    assert next(r for r in off if r.req_id == "R-A").inferred_tests == ()


def test_per_test_coverage_contexts_link_tests_by_measurement(traced: Path, tmp_path: Path) -> None:
    """MEASURED, NOT INFERRED: coverage.py run with `--cov-context=test` records which test ran each
    line; a test that ran a line inside an implementer's body is linked to its requirement.

    @brief coverage.py JSON contexts → measured links.
    """
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "files": {
                    "src/a.c": {
                        "contexts": {
                            "11": ["tests/unit/test_c.py::test_cov[1]|run", ""],
                            "40": ["tests/unit/test_c.py::test_elsewhere|run"],
                        }
                    }
                }
            }
        )
    )
    inputs = EvidenceInputs(contexts="coverage.json", infer_depth=0)
    rows = {
        r.req_id: r
        for r in requirement_evidence(traced, junit=[], inputs=inputs, repo_root=tmp_path)
    }
    assert rows["R-A"].measured_tests == ("test_cov",)
    assert "test_elsewhere" not in {t for t, _s in rows["R-A"].tests}


def test_a_declared_report_that_is_not_there_is_unmeasured_not_a_crash(
    traced: Path, tmp_path: Path
) -> None:
    """FOUND DOGFOODING (round 3, P6c): building clew's own wiki without CI's coverage file died
    with a raw FileNotFoundError. A report that is declared and absent was NOT MEASURED: coverage
    fields absent (None), results not run — never a traceback, never a zero.

    @brief Missing JUnit and Cobertura: evidence still computed, unmeasured.
    """
    rows = {
        r.req_id: r
        for r in requirement_evidence(
            traced, junit=[tmp_path / "gone.xml"], coverage=tmp_path / "gone-cov.xml"
        )
    }
    assert rows["R-A"].implementers_covered is None
    assert rows["R-A"].tier in ("NOT_RUN", "MISSING")


def test_a_measured_link_carries_its_extent(traced: Path, tmp_path: Path) -> None:
    """OWNER 2026-11-17: "a test could cover sections of multiple requirements, or one requirement
    in full". A measured link says WHICH of the requirement's implementers the test executed, so
    "ran 1 of 9" never reads like "ran all 9". Unmeasured (no contexts) is ABSENT, not empty.

    @brief Per-test extent: the implementers each measured test executed.
    """
    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps({"files": {"src/a.c": {"contexts": {"11": ["tests/t.py::test_cov|run"]}}}})
    )
    measured = {
        r.req_id: r
        for r in requirement_evidence(
            traced,
            junit=[],
            inputs=EvidenceInputs(contexts="coverage.json", infer_depth=0),
            repo_root=tmp_path,
        )
    }
    assert measured["R-A"].extent == (("test_cov", ("impl",)),)
    assert measured["R-B"].extent == ()
    plain = requirement_evidence(
        traced, junit=[], inputs=EvidenceInputs(infer_depth=0), repo_root=tmp_path
    )
    assert all(r.extent is None for r in plain)


def test_by_default_inference_is_the_full_transitive_closure(traced: Path, tmp_path: Path) -> None:
    """OWNER 2026-11-17: tests are linked to source by what they reach, transitively — "we should
    EXPLICITLY know which tests are related to which requirements by transitive linkage". A fixed
    hop cap was a guess: clew's REQ-DDB-GUARD-021 implementer sits 4 calls under its tests, so the
    demo read it MISSING. With no `infer_depth` declared, every test whose calls reach an
    implementer at ANY depth is linked; the cap stays available, and 0 still turns it off. The
    link's extent names the implementers each inferred test reaches.

    @brief Unbounded transitive inference by default, with extent.
    """
    db = _with_calls(traced, tmp_path)
    rows = {
        r.req_id: r
        for r in requirement_evidence(db, junit=[], inputs=EvidenceInputs(), repo_root=tmp_path)
    }
    assert rows["R-A"].inferred_tests == ("test_far", "test_infer")
    assert dict(rows["R-A"].extent) == {"test_far": ("impl",), "test_infer": ("impl",)}
    ## The nearest test is the one aimed at the code: test_infer is 2 calls away, test_far 3.
    assert dict(rows["R-A"].distance) == {"test_far": 3, "test_infer": 2}


def test_contexts_are_read_from_coverage_s_own_data_file(traced: Path, tmp_path: Path) -> None:
    """FOUND ON CLEW'S OWN SUITE (round 4): the JSON report with per-test contexts was 3.9 GB for
    3,176 tests — every line repeating every test that ran it. coverage.py's data file holds the
    same contexts compactly (SQLite), so `contexts:` also takes it, read through coverage's API.

    @brief Per-test contexts from a `.coverage` data file.
    """
    from coverage import CoverageData

    data = CoverageData(basename=str(tmp_path / ".coverage"))
    data.set_context("tests/unit/test_c.py::test_cov|run")
    data.add_lines({str(tmp_path / "src" / "a.c"): [11]})
    data.set_context("tests/unit/test_c.py::test_elsewhere|run")
    data.add_lines({str(tmp_path / "src" / "a.c"): [40]})
    data.write()
    inputs = EvidenceInputs(contexts=".coverage", infer_depth=0)
    rows = {
        r.req_id: r
        for r in requirement_evidence(traced, junit=[], inputs=inputs, repo_root=tmp_path)
    }
    assert rows["R-A"].measured_tests == ("test_cov",)


def test_a_context_with_brackets_in_its_parameters_names_its_test(tmp_path: Path) -> None:
    """FOUND ON CLEW'S OWN WIKI (round 4): `tests/t.py::test_x[a::b[c]-enhanced]|run` read as a
    test called `enhanced]`. The parameters are cut at the first "[" before the name is taken.

    @brief Context nodeids with nested brackets.
    """
    from clew.wiki.imports import parse_contexts

    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {"files": {"a.py": {"contexts": {"1": ["tests/t.py::test_x[a::b[c]-enhanced]|run"]}}}}
        )
    )
    (tmp_path / "a.py").write_text("x = 1\n")
    assert parse_contexts(report, tmp_path) == {"a.py": {1: {"test_x"}}}


def test_only_a_tests_own_run_links_it_not_its_fixtures_setup(tmp_path: Path) -> None:
    """FOUND ON CLEW'S OWN WIKI (round 4): `test_cap_at_depth_taper` read as MEASURED against
    REQ-DDB-MCP-004 through `source_fingerprint`, which only an autouse fixture's SETUP ran. A
    context is `<nodeid>|<phase>`; the test exercised what ran in its `run` phase.

    @brief Setup and teardown contexts do not link a test.
    """
    from clew.wiki.imports import parse_contexts

    report = tmp_path / "coverage.json"
    report.write_text(
        json.dumps(
            {
                "files": {
                    "a.py": {
                        "contexts": {
                            "1": ["tests/t.py::test_x|setup"],
                            "2": ["tests/t.py::test_x|run"],
                        }
                    }
                }
            }
        )
    )
    (tmp_path / "a.py").write_text("x = 1\ny = 2\n")
    assert parse_contexts(report, tmp_path) == {"a.py": {1: set(), 2: {"test_x"}}}
