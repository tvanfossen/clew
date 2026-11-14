# SPDX-License-Identifier: MIT
"""Requirement evidence: test results and coverage, joined to the requirement trace.

1.4.0 Track 4, W4 (#67). The requirement trace already says which functions implement a
requirement and which tests cover it (`req_edges`, `req_test_edges`). This adds what CI measured:
JUnit results per test and Cobertura line hits per file, and grades each requirement:

  PASS     a linked test passed and none failed
  GAP      a linked test failed or errored
  TARGET   every linked result is a skip of a test declared target-only (needs hardware)
  NOT_RUN  tests are linked but were skipped, or the reports carry no result for them
  MISSING  no test is linked at all

THE TIERS NEVER COLLAPSE: a host-only CI run skips hardware tests on purpose, and reporting those
as GAP or MISSING is the false gap #67's consumers asked to stop seeing. Coverage is reported per
implementer — covered, uncovered — and is ABSENT (None) when no Cobertura report was given:
unmeasured is not uncovered.

Reports are read with the standard library's XML parser and capped at `MAX_REPORT_BYTES`; they are
CI artifacts the operator chose, not repository content.

@brief JUnit/Cobertura evidence per requirement.
@version 1
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from ..query._common import connect, table_exists

## A report larger than this is refused rather than parsed.
MAX_REPORT_BYTES = 64 * 1024 * 1024
## Worst-first: a folded test takes the worst status of its cases.
_RANK = {"error": 0, "failed": 1, "skipped": 2, "passed": 3}
## A parametrized case's suffix: `test_x[a-1]` folds to `test_x`.
_PARAMS = re.compile(r"\[.*\]$")


## @brief One test's folded result.
## @version 1
@dataclass(frozen=True)
class CaseResult:
    """@brief Status (worst case), case count, and the skip message if any. @version 1"""

    name: str
    status: str
    cases: int
    message: str = ""


## @brief One requirement's graded evidence.
## @version 1
@dataclass(frozen=True)
class RequirementEvidence:
    """@brief Tier, linked tests with their statuses, implementer coverage. @version 1"""

    req_id: str
    title: str
    tier: str
    tests: tuple[tuple[str, str], ...]
    implementers: tuple[str, ...]
    implementers_covered: tuple[str, ...] | None = None
    implementers_uncovered: tuple[str, ...] | None = None


## @brief Read JUnit XML reports into one folded result per test.
## @param paths JUnit report files.
## @return {test name: CaseResult}.
## @version 1
## @req REQ-DDB-WIKI-002
def parse_junit(paths: list[Path]) -> dict[str, CaseResult]:
    """THE TEST NAME IS THE CASE NAME WITH ITS PARAMETERS DROPPED, the name the index knows as a
    function; a folded test takes its WORST case's status and records how many cases it had.

    @brief Parse JUnit.
    @return Results.
    @version 1
    """
    folded: dict[str, list[tuple[str, str]]] = {}
    for path in paths:
        for case in _root(path).iter("testcase"):
            name = _PARAMS.sub("", case.get("name") or "")
            folded.setdefault(name, []).append(_case_status(case))
    return {
        name: CaseResult(
            name=name,
            status=min(statuses, key=lambda s: _RANK[s[0]])[0],
            cases=len(statuses),
            message=next((m for s, m in statuses if s == "skipped" and m), ""),
        )
        for name, statuses in folded.items()
        if name
    }


## @brief Read a Cobertura XML report into line hits per file.
## @param path The report.
## @return {repo-relative file: {line: hits}}.
## @version 1
## @req REQ-DDB-WIKI-002
def parse_cobertura(path: Path) -> dict[str, dict[int, int]]:
    """@brief Parse Cobertura. @return Hits per file."""
    hits: dict[str, dict[int, int]] = {}
    for cls in _root(path).iter("class"):
        lines = hits.setdefault(cls.get("filename") or "", {})
        for line in cls.iter("line"):
            lines[int(line.get("number") or 0)] = int(line.get("hits") or 0)
    return hits


## @brief Grade every requirement the index knows against the given reports.
## @param db The index.
## @param junit JUnit report files.
## @param coverage A Cobertura report, or None.
## @param target_only Test-name globs that need hardware (skipped on host by design).
## @return One RequirementEvidence per requirement, ordered by id.
## @version 1
## @req REQ-DDB-WIKI-002
def requirement_evidence(
    db: Path | str,
    *,
    junit: list[Path],
    coverage: Path | None = None,
    target_only: tuple[str, ...] = (),
) -> list[RequirementEvidence]:
    """@brief Join reports to the trace. @return Evidence rows."""
    results = parse_junit(junit)
    hits = parse_cobertura(coverage) if coverage is not None else None
    with connect(db) as conn:
        ids = _requirement_ids(conn)
        out = []
        for req_id, title in ids:
            tests = _linked(conn, "req_test_edges", "test_memberdef_rowid", req_id)
            impls = _implementer_spans(conn, req_id)
            statuses = tuple((t, _status_of(t, results)) for t in tests)
            covered = uncovered = None
            if hits is not None:
                covered = tuple(n for n, f, s, e in impls if _covered(hits, f, s, e))
                uncovered = tuple(n for n, f, s, e in impls if not _covered(hits, f, s, e))
            out.append(
                RequirementEvidence(
                    req_id=req_id,
                    title=title,
                    tier=_tier(statuses, target_only),
                    tests=statuses,
                    implementers=tuple(n for n, _f, _s, _e in impls),
                    implementers_covered=covered,
                    implementers_uncovered=uncovered,
                )
            )
    return out


## @brief Grade one requirement from its linked tests' statuses.
## @param statuses (test name, status) pairs; status "absent" when no report had it.
## @param target_only Target-only test-name globs.
## @return The tier.
## @version 1
## @dg_internal
def _tier(statuses: tuple[tuple[str, str], ...], target_only: tuple[str, ...]) -> str:
    """@brief Apply the tier rules in order. @return Tier."""
    if not statuses:
        return "MISSING"
    kinds = {s for _t, s in statuses}
    if kinds & {"failed", "error"}:
        return "GAP"
    if "passed" in kinds:
        return "PASS"
    if all(s == "skipped" and any(fnmatch(t, g) for g in target_only) for t, s in statuses):
        return "TARGET"
    return "NOT_RUN"


## @brief One test's status in the reports, or "absent".
## @param test The test's function name.
## @param results The folded JUnit results.
## @return The status.
## @version 1
## @dg_internal
def _status_of(test: str, results: dict[str, CaseResult]) -> str:
    """@brief Look a test up. @return Status or "absent"."""
    found = results.get(test)
    return found.status if found is not None else "absent"


## @brief The status and skip message of one JUnit testcase element.
## @param case The element.
## @return (status, message).
## @version 1
## @dg_internal
def _case_status(case: ET.Element) -> tuple[str, str]:
    """@brief Classify a testcase. @return Status and message."""
    for tag, status in (("error", "error"), ("failure", "failed"), ("skipped", "skipped")):
        child = case.find(tag)
        if child is not None:
            return status, child.get("message") or ""
    return "passed", ""


## @brief Parse one report, refusing an oversized one.
## @param path The report.
## @return The XML root.
## @version 1
## @dg_internal
def _root(path: Path) -> ET.Element:
    """@brief Read XML with a size cap. @return Root element."""
    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError(f"{path} is larger than {MAX_REPORT_BYTES} bytes; refusing to parse it")
    return ET.parse(path).getroot()


## @brief Every requirement id the index knows, with its title.
## @param conn Open connection.
## @return (id, title) pairs, ordered.
## @version 1
## @dg_internal
def _requirement_ids(conn: object) -> list[tuple[str, str]]:
    """THE CATALOG AND EVERY TAGGED ID, so a `@req` literal with no catalog row is still graded.

    @brief Collect requirement ids.
    @return Pairs.
    """
    ids: dict[str, str] = {}
    if table_exists(conn, "requirements"):
        ids.update(
            (str(i), str(t or "")) for i, t in conn.execute("SELECT id, title FROM requirements")
        )
    for table in ("req_edges", "req_test_edges"):
        if table_exists(conn, table):
            for (i,) in conn.execute(f"SELECT DISTINCT req_id FROM {table}"):
                ids.setdefault(str(i), "")
    return sorted(ids.items())


## @brief The function names linked to a requirement through one edge table.
## @param conn Open connection.
## @param table Edge table.
## @param column Its memberdef rowid column.
## @param req_id The requirement.
## @return Names, ordered.
## @version 1
## @dg_internal
def _linked(conn: object, table: str, column: str, req_id: str) -> tuple[str, ...]:
    """@brief Linked function names. @return Names."""
    if not table_exists(conn, table):
        return ()
    rows = conn.execute(
        f"SELECT DISTINCT m.name FROM {table} t JOIN memberdef m ON m.rowid = t.{column} "
        "WHERE t.req_id = ? ORDER BY m.name",
        (req_id,),
    )
    return tuple(str(r[0]) for r in rows)


## @brief Each implementer of a requirement with its file and body span.
## @param conn Open connection.
## @param req_id The requirement.
## @return (name, file, start, end) per implementer.
## @version 1
## @dg_internal
def _implementer_spans(conn: object, req_id: str) -> list[tuple[str, str, int, int]]:
    """@brief Implementer locations. @return Rows."""
    if not table_exists(conn, "req_edges"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT m.name, p.name, m.bodystart, m.bodyend FROM req_edges r "
        "JOIN memberdef m ON m.rowid = r.memberdef_rowid "
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        "WHERE r.req_id = ? ORDER BY m.name",
        (req_id,),
    )
    return [(str(n), str(f), int(s or 0), int(e or 0)) for n, f, s, e in rows]


## @brief Whether any line of a body span was hit.
## @param hits Coverage per file.
## @param rel The file.
## @param start Body start.
## @param end Body end.
## @return True when a line in the span has hits > 0.
## @version 1
## @dg_internal
def _covered(hits: dict[str, dict[int, int]], rel: str, start: int, end: int) -> bool:
    """@brief Span coverage. @return Covered?"""
    lines = hits.get(rel) or {}
    return any(n for line, n in lines.items() if start <= line <= end)
