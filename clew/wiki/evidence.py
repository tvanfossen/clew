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

MUTATION RECORDS (W9) are the strongest requirement → test link: a record names a MECHANISM (a
function), the TEST that should catch its removal, and whether it did (`killed`). A record attaches
to every requirement its mechanism implements, as (mechanism, test, killed | survived). The field
is ABSENT (None) when no record file was given — unmeasured is not "every mutant was killed".

Reports are read with the standard library's XML parser and capped at `MAX_REPORT_BYTES`; they are
CI artifacts the operator chose, not repository content.

Imports beyond these (W15/W16: gcov, CTest / TAP / Catch2 / pytest-json results, a mapping file,
Gherkin scenarios, test layers) are parsed in `clew.wiki.imports` and joined here.

@brief JUnit/Cobertura/mutation evidence per requirement.
@version 3
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from ..query._common import connect, table_exists
from .config import EvidenceInputs

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
## v2: mutation outcomes (W9).
## v3: test counts per layer (W16), None when no layers are configured.
## @version 3
@dataclass(frozen=True)
class RequirementEvidence:
    """@brief Tier, linked tests, implementer coverage, mutations, layers. @version 3"""

    req_id: str
    title: str
    tier: str
    tests: tuple[tuple[str, str], ...]
    implementers: tuple[str, ...]
    implementers_covered: tuple[str, ...] | None = None
    implementers_uncovered: tuple[str, ...] | None = None
    mutations: tuple[tuple[str, str, str], ...] | None = None
    layers: tuple[tuple[str, int], ...] | None = None


## @brief Read JUnit XML reports into one folded result per test.
## @param paths JUnit report files.
## @return {test name: CaseResult}.
## v2: folding shared with the W16 formats (`imports.fold_cases`).
## @version 2
## @req REQ-DDB-WIKI-002
def parse_junit(paths: list[Path]) -> dict[str, CaseResult]:
    """THE TEST NAME IS THE CASE NAME WITH ITS PARAMETERS DROPPED, the name the index knows as a
    function; a folded test takes its WORST case's status and records how many cases it had.

    @brief Parse JUnit.
    @return Results.
    @version 2
    """
    from .imports import fold_cases

    return fold_cases(
        (_PARAMS.sub("", case.get("name") or ""), *_case_status(case))
        for path in paths
        for case in _root(path).iter("testcase")
    )


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


## @brief Read a mutation record: (mechanism, test, killed) per entry.
## @param path A YAML or JSON list of `{mechanism, test, killed}`.
## @return Records, in file order.
## @version 1
## @req REQ-DDB-WIKI-006
def parse_mutations(path: Path) -> list[tuple[str, str, bool]]:
    """AN ENTRY MISSING A FIELD IS REFUSED, never defaulted: a record that does not say whether
    the mutant was killed is not evidence either way.

    @brief Parse mutation records.
    @return Records.
    @version 1
    """
    import yaml

    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError(f"{path} is larger than {MAX_REPORT_BYTES} bytes; refusing to parse it")
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    if not isinstance(doc, list):
        raise ValueError(f"{path}: a mutation record is a list of {{mechanism, test, killed}}")
    out = []
    for i, entry in enumerate(doc):
        if not isinstance(entry, dict) or not {"mechanism", "test", "killed"} <= set(entry):
            raise ValueError(f"{path}: entry {i} needs `mechanism`, `test` and `killed`")
        out.append((str(entry["mechanism"]), str(entry["test"]), bool(entry["killed"])))
    return out


## @brief Grade every requirement the index knows against the given reports.
## @param db The index.
## @param junit JUnit report files.
## @param coverage A Cobertura report, or None.
## @param target_only Test-name globs that need hardware (skipped on host by design).
## @param mutations A mutation record, or None.
## @param inputs The W15/W16 imports (result formats, gcov, mapping, features, layers).
## @param repo_root The repository the imports' paths are relative to (needed with `inputs`).
## @return One RequirementEvidence per requirement, ordered by id.
## v2: `mutations` (W9).
## v3: `inputs` / `repo_root` (W15/W16): more result formats, gcov, mapping, Gherkin, layers.
## @version 3
## @req REQ-DDB-WIKI-002
def requirement_evidence(
    db: Path | str,
    *,
    junit: list[Path],
    coverage: Path | None = None,
    target_only: tuple[str, ...] = (),
    mutations: Path | None = None,
    inputs: EvidenceInputs | None = None,
    repo_root: Path | None = None,
) -> list[RequirementEvidence]:
    """@brief Join reports to the trace. @return Evidence rows."""
    reports = _Reports.read(junit, coverage, mutations, inputs, repo_root)
    with connect(db) as conn:
        out = []
        for req_id, title in _requirement_ids(conn):
            impls = _implementer_spans(conn, req_id)
            linked = reports.linked_tests(conn, req_id)
            statuses = tuple((t, reports.status(t, names)) for t, _where, names in linked)
            covered = uncovered = None
            if reports.hits is not None:
                covered = tuple(n for n, f, s, e in impls if _covered(reports.hits, f, s, e))
                uncovered = tuple(n for n, f, s, e in impls if not _covered(reports.hits, f, s, e))
            out.append(
                RequirementEvidence(
                    req_id=req_id,
                    title=title,
                    tier=_tier(statuses, target_only),
                    tests=statuses,
                    implementers=tuple(n for n, _f, _s, _e in impls),
                    implementers_covered=covered,
                    implementers_uncovered=uncovered,
                    mutations=_mutations_for(reports.records, impls),
                    layers=reports.layers_of(linked),
                )
            )
    return out


## @brief Every report a trace reads, parsed once.
## @version 1
class _Reports:
    """@brief Results, coverage hits, mutation records, mapping, scenarios, layers. @version 1"""

    ## @brief Hold the parsed reports.
    ## @param results Folded results by test name.
    ## @param hits Coverage hits, or None when unmeasured.
    ## @param records Mutation records, or None.
    ## @param mapping Requirement → tests from a mapping file.
    ## @param scenarios Gherkin scenarios.
    ## @param layers Layer name → globs, or None.
    ## @version 1
    ## @dg_internal
    def __init__(self, results, hits, records, mapping, scenarios, layers) -> None:
        """@brief Store. @return None."""
        self.results = results
        self.hits = hits
        self.records = records
        self.mapping = mapping
        self.scenarios = scenarios
        self.layers = layers

    ## @brief Read every given report.
    ## @param junit JUnit files.
    ## @param coverage A Cobertura file, or None.
    ## @param mutations A mutation record, or None.
    ## @param inputs The W15/W16 imports, or None.
    ## @param repo_root The repository.
    ## @return The reports.
    ## @version 1
    ## @dg_internal
    @classmethod
    def read(cls, junit, coverage, mutations, inputs, repo_root) -> _Reports:
        """COVERAGE IS None ONLY WHEN NO REPORT OF EITHER KIND WAS GIVEN; Cobertura and gcov hits
        for the same line are summed.

        @brief Parse.
        @return Reports.
        """
        from .imports import parse_features, parse_gcov, parse_mapping, parse_results

        inputs = inputs or EvidenceInputs()
        root = Path(repo_root or ".")
        results = parse_junit(junit)
        for fmt, rel in inputs.results:
            results = _merge(results, parse_results(fmt, root / rel))
        hits = parse_cobertura(coverage) if coverage is not None else None
        if inputs.gcov:
            gcov = parse_gcov(sorted({p for g in inputs.gcov for p in root.glob(g)}), root)
            hits = _sum_hits(hits or {}, gcov)
        return cls(
            results,
            hits,
            parse_mutations(mutations) if mutations is not None else None,
            parse_mapping(root / inputs.mapping) if inputs.mapping else {},
            parse_features(root, inputs.features),
            inputs.layers,
        )

    ## @brief A requirement's tests: indexed, mapped and scenario, each once.
    ## @param conn Open connection.
    ## @param req_id The requirement.
    ## @return (test id, where for layer globs, names to look results up by).
    ## @version 1
    ## @dg_internal
    def linked_tests(self, conn, req_id: str) -> list[tuple[str, str, tuple[str, ...]]]:
        """A SCENARIO'S RESULT is found under its own name (behave, cucumber) or its pytest-bdd
        function name, `test_<name, snake-cased>`.

        @brief Collect links.
        @return Tests.
        """
        out = {name: (name, file, (name,)) for name, file in _linked_tests(conn, req_id)}
        for name in self.mapping.get(req_id, ()):
            out.setdefault(name, (name, name, (name,)))
        for sc in self.scenarios:
            if req_id in sc.tags:
                slug = "test_" + re.sub(r"\W+", "_", sc.name.lower()).strip("_")
                out.setdefault(sc.test_id, (sc.test_id, sc.test_id, (sc.name, slug)))
        return sorted(out.values())

    ## @brief One test's status: the first of its names a report holds, else "absent".
    ## @param test The test id.
    ## @param names The names to look up.
    ## @return The status.
    ## @version 1
    ## @dg_internal
    def status(self, test: str, names: tuple[str, ...]) -> str:
        """@brief Look up. @return Status."""
        found = next((self.results[n] for n in names if n in self.results), None)
        return found.status if found is not None else "absent"

    ## @brief Test counts per layer for one requirement's tests.
    ## @param linked The requirement's linked tests.
    ## @return (layer, count) pairs in layer order, or None when no layers are configured.
    ## @version 1
    ## @dg_internal
    def layers_of(self, linked) -> tuple[tuple[str, int], ...] | None:
        """A TEST MATCHING NO LAYER is counted in none — it is not a layer of its own.

        @brief Count.
        @return Pairs or None.
        """
        if self.layers is None:
            return None
        counts = {
            layer: sum(1 for _t, where, _n in linked if any(fnmatch(where, g) for g in globs))
            for layer, globs in self.layers
        }
        return tuple(sorted((k, v) for k, v in counts.items() if v))


## @brief Two folded result sets merged; a test in both takes the worse status.
## @param a Results.
## @param b Results.
## @return The merge.
## @version 1
## @dg_internal
def _merge(a: dict[str, CaseResult], b: dict[str, CaseResult]) -> dict[str, CaseResult]:
    """@brief Merge. @return Results."""
    out = dict(a)
    for name, result in b.items():
        mine = out.get(name)
        if mine is None or _RANK[result.status] < _RANK[mine.status]:
            out[name] = result
    return out


## @brief Two coverage maps summed line by line.
## @param a Hits.
## @param b Hits.
## @return The sum.
## @version 1
## @dg_internal
def _sum_hits(
    a: dict[str, dict[int, int]], b: dict[str, dict[int, int]]
) -> dict[str, dict[int, int]]:
    """@brief Sum. @return Hits."""
    out = {f: dict(lines) for f, lines in a.items()}
    for f, lines in b.items():
        mine = out.setdefault(f, {})
        for line, n in lines.items():
            mine[line] = mine.get(line, 0) + n
    return out


## @brief The mutation outcomes whose mechanism implements a requirement.
## @param records All records, or None when none were given.
## @param impls The requirement's implementers.
## @return (mechanism, test, killed|survived) tuples, or None.
## @version 1
## @dg_internal
def _mutations_for(
    records: list[tuple[str, str, bool]] | None, impls: list[tuple[str, str, int, int]]
) -> tuple[tuple[str, str, str], ...] | None:
    """@brief Attach records. @return Outcomes or None."""
    if records is None:
        return None
    names = {n for n, _f, _s, _e in impls}
    return tuple(
        (m, t, "killed" if killed else "survived") for m, t, killed in records if m in names
    )


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


## @brief The indexed tests linked to a requirement, with their files.
## @param conn Open connection.
## @param req_id The requirement.
## @return (name, file) pairs, ordered.
## @version 1
## @dg_internal
def _linked_tests(conn: object, req_id: str) -> list[tuple[str, str]]:
    """@brief Linked tests. @return Pairs."""
    if not table_exists(conn, "req_test_edges"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT m.name, COALESCE(p.name, '') FROM req_test_edges t "
        "JOIN memberdef m ON m.rowid = t.test_memberdef_rowid "
        "LEFT JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        "WHERE t.req_id = ? ORDER BY m.name",
        (req_id,),
    )
    return [(str(n), str(f)) for n, f in rows]


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
