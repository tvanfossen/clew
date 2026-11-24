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
  EXEMPT   no test is linked, and the catalog's declared status is one `impact.requirements.
           exempt_status` exempts (round 4, R8) — the gate's own rule, so the wiki and `clew guard
           coverage` never disagree about one catalogue

THE TIERS NEVER COLLAPSE: a host-only CI run skips hardware tests on purpose, and reporting those
as GAP or MISSING is the false gap #67's consumers asked to stop seeing. Coverage is reported per
implementer — covered, uncovered — and is ABSENT (None) when no Cobertura report was given:
unmeasured is not uncovered.

MUTATION RECORDS (W9) are the strongest requirement → test link: a record names a MECHANISM (a
function), the TEST that should catch its removal, and whether it did (`killed`). A record attaches
to every requirement its mechanism implements, as (mechanism, test, killed | survived). The field
is ABSENT (None) when no record file was given — unmeasured is not "every mutant was killed".

Reports are read with the standard library's XML parser and capped (`tests.max_report_mb`); they are
CI artifacts the operator chose, not repository content.

Imports beyond these (W15/W16: gcov, CTest / TAP / Catch2 / pytest-json results, a mapping file,
Gherkin scenarios, test layers) are parsed in `clew.wiki.imports` and joined here.

@brief JUnit/Cobertura/mutation evidence per requirement.
@version 4
"""

from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from fnmatch import fnmatch
from pathlib import Path

from ..query._common import connect, table_exists
from .config import DEFAULT_MAX_REPORT_MB, EvidenceInputs

logger = logging.getLogger(__name__)

## A report larger than this is refused rather than parsed: `tests.max_report_mb` (R5-CFG C9,
## 2.0.0), default 64 MiB — per-test LCOV grows with the number of tests, so a mid-size C repo can
## exceed a cap that suited one JUnit file. Set per build with `report_limit`, read by the readers
## below; a ContextVar so the limit belongs to the build that set it, not the process.
_REPORT_MB: ContextVar[int] = ContextVar("clew_wiki_report_mb", default=DEFAULT_MAX_REPORT_MB)


## @brief Hold this build's report size limit for the readers below.
## @param megabytes The limit, in MiB.
## @return A context manager.
## @version 1
## @req REQ-DDB-WIKI-005
@contextmanager
def report_limit(megabytes: int) -> Iterator[None]:
    """@brief Scope the report limit. @return Context."""
    token = _REPORT_MB.set(megabytes)
    try:
        yield
    finally:
        _REPORT_MB.reset(token)


## @brief Refuse a report over this build's size limit.
## @param path The report.
## @return None; raises ValueError naming the limit and the key that raises it.
## @version 1
## @utility
def check_report_size(path: Path) -> None:
    """@brief Apply the cap. @return None."""
    limit = _REPORT_MB.get() * 1024 * 1024
    if path.stat().st_size > limit:
        raise ValueError(
            f"{path} is larger than {_REPORT_MB.get()} MiB; refusing to parse it "
            f"(raise `tests.max_report_mb` if the report is expected to be this large)"
        )


## Worst-first: a folded test takes the worst status of its cases.
_RANK = {"error": 0, "failed": 1, "skipped": 2, "passed": 3}
## A parametrized case's suffix: `test_x[a-1]` folds to `test_x`.
_PARAMS = re.compile(r"\[.*\]$")
## A JUnit case's parameters: JUnit 5 `name(args)[n]`, pytest `name[id]`.
## A `status` attribute naming a case that did not run (GoogleTest, Surefire, others).
_SKIP_STATUS = ("notrun", "disabled", "skipped")
_JUNIT_PARAMS = re.compile(r"(\(.*\))?(\[.*\])?$")
## A path-shaped token in a catalog evidence field.
_PATH_TOKEN = re.compile(r"[\w.-]+(?:/[\w.-]+)+\.\w+")


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
## v4: implementer sites (name, file, line), so a page can link each implementer to its source;
## `declared_tests` (catalog evidence files), `measured_tests` (per-test coverage) and
## `inferred_tests` (the call graph) — the tests linked by each weaker kind than a tag.
## v5: `extent` — per measured test, the implementers it executed (None when unmeasured).
## v6: `distance` — per inferred test, the fewest calls to an implementer.
## @version 6
@dataclass(frozen=True)
class RequirementEvidence:
    """@brief Tier, tests, implementers and their sites, coverage, mutations, layers. @version 6"""

    req_id: str
    title: str
    tier: str
    tests: tuple[tuple[str, str], ...]
    implementers: tuple[str, ...]
    implementers_covered: tuple[str, ...] | None = None
    implementers_uncovered: tuple[str, ...] | None = None
    mutations: tuple[tuple[str, str, str], ...] | None = None
    layers: tuple[tuple[str, int], ...] | None = None
    implementer_sites: tuple[tuple[str, str, int], ...] = ()
    declared_tests: tuple[str, ...] = ()
    measured_tests: tuple[str, ...] = ()
    inferred_tests: tuple[str, ...] = ()
    extent: tuple[tuple[str, tuple[str, ...]], ...] | None = None
    ## Per inferred test, the fewest calls between it and an implementer (round 4).
    distance: tuple[tuple[str, int], ...] = ()


## @brief Read JUnit XML reports into one folded result per test.
## @param paths JUnit report files.
## @return {test name: CaseResult}.
## v2: folding shared with the W16 formats (`imports.fold_cases`).
## v3: JUnit 5 `name(args)[n]` folds to `name` (round 3, P3c).
## v4 (round 4): a Catch2 section path folds into its test case (`_case_name`).
## @version 4
## @req REQ-DDB-WIKI-002
def parse_junit(paths: list[Path]) -> dict[str, CaseResult]:
    """THE TEST NAME IS THE CASE NAME WITH ITS PARAMETERS DROPPED, the name the index knows as a
    function; a folded test takes its WORST case's status and records how many cases it had.

    @brief Parse JUnit.
    @return Results.
    @version 3
    """
    from .imports import fold_cases

    return fold_cases(
        (_case_name(case), *_case_status(case))
        for path in paths
        for case in _root(path).iter("testcase")
    )


## @brief A JUnit testcase's test name: parameters dropped, a Catch2 section path folded.
## @param case The element.
## @return The name the index knows the test by.
## @version 1
## @utility
def _case_name(case: ET.Element) -> str:
    """CATCH2'S OWN JUNIT REPORTER names one case per SECTION PATH ("Scenario: X/Given: a") under
    classname `<binary>.global`; the test is the part before the first "/". Found on
    sassafras-class, where 230 of 267 tested requirements read NOT_RUN without it.

    @brief Test name.
    @return Name.
    """
    name = _JUNIT_PARAMS.sub("", case.get("name") or "", count=1)
    if (case.get("classname") or "").endswith(".global"):
        name = name.split("/", 1)[0]
    return name


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
## v2: the cap is this build's tests.max_report_mb (2.0.0, R5-CFG C9)
## @version 2
## @req REQ-DDB-WIKI-006
def parse_mutations(path: Path) -> list[tuple[str, str, bool]]:
    """AN ENTRY MISSING A FIELD IS REFUSED, never defaulted: a record that does not say whether
    the mutant was killed is not evidence either way.

    @brief Parse mutation records.
    @return Records.
    @version 1
    """
    import yaml

    check_report_size(path)
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
## v4: implementer sites.
## v5: per-test extent from coverage contexts (round 4).
## v6: per-test call distance for inferred links.
## @version 6
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
            linked, kinds, inferred = reports.linked_tests(conn, req_id, impls)
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
                    implementer_sites=tuple((n, f, s) for n, f, s, _e in impls),
                    declared_tests=_of_kind(kinds, "catalog"),
                    measured_tests=_of_kind(kinds, "measured"),
                    inferred_tests=_of_kind(kinds, "inferred"),
                    extent=reports.extent(impls, inferred),
                    distance=tuple(sorted((t, v[2]) for t, v in inferred.items())),
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
    ## @param catalog Requirement → test files its catalog evidence field names.
    ## @param infer (per-test coverage contexts, call-graph inference depth).
    ## @version 1
    ## @utility
    def __init__(self, results, hits, records, mapping, scenarios, layers, catalog, infer) -> None:
        """@brief Store. @return None."""
        self.catalog = catalog
        self.contexts, self.infer_depth = infer
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
    ## v2: catalog evidence files, per-test coverage contexts and inference depth.
    ## v3: a declared report that does not exist is unmeasured, not an error (round 3, P6c).
    ## v4: no contexts report is None (unmeasured), not {} (round 4).
    ## @version 4
    ## @utility
    @classmethod
    def read(cls, junit, coverage, mutations, inputs, repo_root) -> _Reports:
        """COVERAGE IS None ONLY WHEN NO REPORT OF EITHER KIND WAS GIVEN; Cobertura and gcov hits
        for the same line are summed.

        @brief Parse.
        @return Reports.
        """
        from .imports import (
            parse_contexts,
            parse_features,
            parse_gcov,
            parse_mapping,
            parse_results,
        )

        inputs = inputs or EvidenceInputs()
        root = Path(repo_root or ".")
        # A DECLARED REPORT THAT IS NOT THERE WAS NOT MEASURED (round 3, P6c): dropped here, so
        # its fields stay absent — never a traceback, never a zero. The site names it.
        junit = [j for j in junit if Path(j).is_file()]
        coverage = coverage if coverage is not None and Path(coverage).is_file() else None
        results = parse_junit(junit)
        for fmt, rel in inputs.results:
            if (root / rel).is_file():
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
            _catalog_files(root, inputs.evidence_fields) if repo_root else {},
            (
                (
                    parse_contexts(root / inputs.contexts, root)
                    if inputs.contexts and (root / inputs.contexts).is_file()
                    else None
                ),
                inputs.infer_depth,
            ),
        )

    ## @brief A requirement's tests: indexed, mapped and scenario, each once.
    ## @param conn Open connection.
    ## @param req_id The requirement.
    ## @param impls Its implementers (name, file, start, end).
    ## @return (tests, the kind of each link weaker than a tag, the inferred tests with extent).
    ## v2: catalog evidence files, per-test coverage, call-graph inference.
    ## v3 (round 4): the inferred tests' reached implementers are returned for the extent.
    ## @version 3
    ## @utility
    def linked_tests(self, conn, req_id: str, impls: list) -> tuple[list, dict[str, str]]:
        """LINKS BY STRENGTH: a test tagged, mapped or a tagged scenario; else MEASURED (per-test
        coverage ran a line of an implementer); else named by the CATALOG's evidence file; else
        INFERRED (its calls reach an implementer within `infer_depth`). A test keeps its strongest
        kind; the weaker kinds are returned so the page can say how each link was made.
        A scenario's result is found under its own name or its pytest-bdd `test_<snake>` name.

        @brief Collect links.
        @return (tests as (id, where, lookup names), {test: catalog | measured | inferred},
            {test: (row, implementers reached)}).
        """
        inferred = _reaching_tests(conn, req_id, self.infer_depth)
        out = {name: (name, file, names) for name, file, names in _linked_tests(conn, req_id)}
        for name in self.mapping.get(req_id, ()):
            out.setdefault(name, (name, name, (name,)))
        for sc in self.scenarios:
            if req_id in sc.tags:
                slug = "test_" + re.sub(r"\W+", "_", sc.name.lower()).strip("_")
                out.setdefault(sc.test_id, (sc.test_id, sc.test_id, (sc.name, slug)))
        kinds: dict[str, str] = {}
        weaker = (
            ("measured", self._measured(impls)),
            ("catalog", _tests_in_files(conn, self.catalog.get(req_id, ()))),
            ("inferred", [t for t, _impls, _hop in inferred.values()]),
        )
        for kind, found in weaker:
            for name, file, names in found:
                if name not in out:
                    out[name] = (name, file, names)
                    kinds[name] = kind
        return sorted(out.values()), kinds, inferred

    ## @brief Tests the per-test coverage saw run a line of an implementer.
    ## @param impls (name, file, start, end) per implementer.
    ## @return (test, file, lookup names).
    ## v2: through `_hits`, shared with the per-test extent.
    ## @version 2
    ## @utility
    def _measured(self, impls: list) -> list[tuple[str, str, tuple[str, ...]]]:
        """@brief Measured tests. @return Pairs."""
        return [(t, t, (t,)) for t in sorted(self._hits(impls))]

    ## @brief Which tests ran a line of which implementer.
    ## @param impls (name, file, start, end) per implementer.
    ## @return {test: implementer names it executed}; empty when no contexts.
    ## v2: per-test keys normalised to names (2.0.0, W11)
    ## @version 2
    ## @utility
    def _hits(self, impls: list) -> dict[str, set[str]]:
        """@brief Per-test implementer hits. @return Map."""
        from .slices import test_name

        found: dict[str, set[str]] = {}
        for name, rel, start, end in impls:
            for line, tests in ((self.contexts or {}).get(rel) or {}).items():
                if start <= line <= end:
                    ## W11 (2.0.0): the per-test key is `file::name`; a requirement's evidence
                    ## lists tests by name, as before.
                    for t in tests:
                        found.setdefault(test_name(t), set()).add(name)
        return found

    ## @brief Per linked test, the implementers of one requirement it executed or reaches.
    ## @param impls (name, file, start, end) per implementer.
    ## @param inferred {test: (row, implementers reached)} from the call graph.
    ## @return ((test, implementers), ...) ordered, or None when neither source ran.
    ## @version 1
    ## @utility
    def extent(self, impls: list, inferred: dict) -> tuple[tuple[str, tuple[str, ...]], ...] | None:
        """MEASURED WINS: a test with per-test coverage reports the implementers it EXECUTED; one
        without reports those its calls reach. UNKNOWN IS ABSENT: with no contexts and inference
        off this is None, never ().

        @brief Extent.
        @return Pairs or None.
        """
        if self.contexts is None and self.infer_depth == 0:
            return None
        out = {t: set(n) for t, (_row, n, _hop) in inferred.items()}
        out.update(self._hits(impls))
        return tuple((t, tuple(sorted(n))) for t, n in sorted(out.items()))

    ## @brief One test's status: the first of its names a report holds, else "absent".
    ## @param test The test id.
    ## @param names The names to look up.
    ## @return The status.
    ## @version 1
    ## @utility
    def status(self, test: str, names: tuple[str, ...]) -> str:
        """@brief Look up. @return Status."""
        found = next((self.results[n] for n in names if n in self.results), None)
        return found.status if found is not None else "absent"

    ## @brief Test counts per layer for one requirement's tests.
    ## @param linked The requirement's linked tests.
    ## @return (layer, count) pairs in layer order, or None when no layers are configured.
    ## @version 1
    ## @utility
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
## @utility
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
## @utility
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
## @utility
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
## @utility
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


## @brief Re-grade MISSING requirements whose declared status the gate exempts.
## @param evidence The graded rows.
## @param declared The catalog entries by id.
## @param guard The parsed guard section, or None.
## @return The rows, EXEMPT where the status is exempt and no test is linked.
## Round 4, R8: the demo read 5 MISSING where `clew guard coverage` read 3 of them exempt.
## v2: reads the top-level requirements: section (2.0.0, R5-CFG F7)
## v3: exempt_when (2.1, #72 item 14)
## @version 3
## @req REQ-DDB-WIKI-002
def exempt_by_status(
    evidence: list[RequirementEvidence], declared: dict[str, dict], guard: dict | None
) -> list[RequirementEvidence]:
    """ONLY MISSING MOVES: a linked test's measured result outranks a catalogue label, so a
    planned requirement whose test failed is still GAP.

    @brief Apply exempt statuses.
    @return Rows.
    """
    from dataclasses import replace

    from ..guard.config import get_requirements

    from ..guard.config import exemption

    req = get_requirements(guard)

    ## 2.1 (#72 item 14): the gate's own predicate, so `exempt_when` fields exempt here too.
    def exempt(row: RequirementEvidence) -> bool:
        return row.tier == "MISSING" and exemption(declared.get(row.req_id) or {}, req) is not None

    return [replace(r, tier="EXEMPT") if exempt(r) else r for r in evidence]


## @brief The status and skip message of one JUnit testcase element.
## @param case The element.
## @return (status, message).
## v2: GoogleTest's notrun / suppressed / skipped attributes.
## v3: `status="disabled"` / `"skipped"` is a skip; a rerun-only failure
## (`flakyFailure`, `rerunFailure`) passed — it has no `failure` child (P3c).
## @version 3
## @utility
def _case_status(case: ET.Element) -> tuple[str, str]:
    """GOOGLETEST'S `status="notrun"` (a disabled test) has no child element: it is a skip, not a
    pass.

    @brief Classify a testcase.
    @return Status and message.
    """
    if case.get("status") in _SKIP_STATUS or case.get("result") in ("suppressed", "skipped"):
        return "skipped", case.get("result") or str(case.get("status"))
    for tag, status in (("error", "error"), ("failure", "failed"), ("skipped", "skipped")):
        child = case.find(tag)
        if child is not None:
            return status, child.get("message") or ""
    return "passed", ""


## Terminal colour/cursor sequences, then every character XML 1.0 forbids (C0 controls but tab,
## newline and carriage return): what a test runner copies from coloured stdout into its report.
_ANSI = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_XML_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


## @brief Parse one report, refusing an oversized one; recover a runner's control characters.
## @param path The report.
## @return The XML root.
## v2: the cap is this build's tests.max_report_mb (2.0.0, R5-CFG C9)
## v3: #72 bug 3 (2.1) — control characters stripped and counted; unreadable XML refused by name
## @version 3
## @utility
def _root(path: Path) -> ET.Element:
    """#72 (an adopter, 2026-11-23): Ceedling copies coloured stdout (`ESC[0m`) into its JUnit, which
    is not XML 1.0, and the raw ParseError either killed `clew wiki trace` or left every linked
    test NOT_RUN. Colour sequences and XML-illegal controls are REMOVED AND COUNTED (a warning names
    the file); what still does not parse is a ValueError naming the file, line and column.

    @brief Read XML with a size cap.
    @return Root element.
    """
    check_report_size(path)
    raw = Path(path).read_bytes().decode("utf-8", errors="replace")
    clean = _XML_ILLEGAL.sub("", _ANSI.sub("", raw))
    if len(clean) != len(raw):
        logger.warning(
            "%s: removed %d terminal-colour or XML-illegal control characters before parsing",
            path,
            len(raw) - len(clean),
        )
    try:
        return ET.fromstring(clean)
    except ET.ParseError as exc:
        line, column = exc.position
        raise ValueError(f"{path}: not valid XML at line {line}, column {column}: {exc}") from exc


## @brief Every requirement id the index knows, with its title.
## @param conn Open connection.
## @return (id, title) pairs, ordered.
## @version 1
## @utility
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


## @brief The test files each requirement's catalog evidence names.
## @param root The repository.
## @param fields The catalog fields to read (`x-evidence`, `evidence`).
## @return {requirement: path-shaped tokens}.
## @version 1
## @utility
def _catalog_files(root: Path, fields: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    """EVIDENCE TEXT IS PROSE ("src/a.c impl; tests/x.py."): every path-shaped token is kept,
    and only a path the INDEX holds test functions in links anything (`_tests_in_files`).

    @brief Read evidence fields.
    @return Files per requirement.
    """
    if not fields:
        return {}
    from .catalogs import declared_catalog

    out = {}
    for req_id, entry in declared_catalog(root)[1].items():
        text = " ".join(str(entry.get(f) or "") for f in fields)
        files = _PATH_TOKEN.findall(text)
        if files:
            out[req_id] = tuple(dict.fromkeys(files))
    return out


## @brief The tests whose calls reach a requirement's implementers, and which ones each reaches.
## @param conn Open connection.
## @param req_id The requirement.
## @param depth Call hops; None = the full transitive closure (the default), 0 = off.
## @return {test: ((test, file, lookup names), implementer names it reaches)}.
## v2: framework recognition (Catch2 / GoogleTest / Boost cases), one hop per `_callers_step`.
## v3 (round 4): unbounded by default, and each test's reached implementers (its extent).
## @version 3
## @req REQ-DDB-WIKI-016
def _reaching_tests(conn: object, req_id: str, depth: int | None) -> dict[str, tuple]:
    """WALKED BACKWARDS from the implementers over call edges, never through a `binding` edge (a
    function value passed along is not a call) nor a fuzzy one, and never through a test: a test
    found is recorded, not expanded. A test is whatever `frameworks.recognise_test` recognises —
    a `test_*` function or a Catch2 / GoogleTest / Boost case.

    EACH NODE CARRIES THE IMPLEMENTERS IT REACHES (owner 2026-11-17: a test may cover part of one
    requirement or all of it), and is walked again only when that set grows — so the closure
    terminates on a cyclic graph and the extent is exact.

    @brief Infer reaching tests with their extent.
    @return Tests found.
    """
    if depth == 0 or not table_exists(conn, "call_edges") or not table_exists(conn, "req_edges"):
        return {}
    origins: dict[int, set[str]] = {}
    for rowid, name in conn.execute(
        "SELECT r.memberdef_rowid, m.name FROM req_edges r "
        "JOIN memberdef m ON m.rowid = r.memberdef_rowid WHERE r.req_id = ?",
        (req_id,),
    ):
        origins.setdefault(rowid, set()).add(str(name))
    frontier, found, hop = set(origins), {}, 0
    while frontier and (depth is None or hop < depth):
        hop += 1
        frontier = _callers_step(conn, frontier, origins, found, hop)
    return found


## @brief One backward hop: callers of the frontier inherit its implementers; tests are recorded.
## @param conn Open connection.
## @param frontier Rowids whose implementer sets just grew.
## @param origins Implementers reached, per rowid; updated.
## @param found Tests found, by test name; updated with (row, implementers, nearest hop).
## @param hop How many calls from an implementer this step is.
## @return The next frontier: non-test callers whose set grew.
## v2 (round 4): implementer sets propagate (extent); a node is re-walked when its set grows.
## v3: the nearest hop a test was found at, so the closest tests can be listed first.
## v4: test code from test_scope and declared shapes (2.0.0, P4 W1)
## @version 4
## @utility
def _callers_step(conn: object, frontier: set, origins: dict, found: dict, hop: int = 1) -> set:
    """@brief Step back. @return Next frontier."""
    from .frameworks import TestRecognizer

    marks = ",".join("?" * len(frontier))
    rows = conn.execute(
        "SELECT DISTINCT c.callee_rowid, c.caller_rowid, m.name, COALESCE(m.argsstring, ''), "
        "COALESCE(p.name, '') FROM call_edges c JOIN memberdef m ON m.rowid = c.caller_rowid "
        "LEFT JOIN path p ON p.rowid = m.file_id "
        f"WHERE c.callee_rowid IN ({marks}) AND c.source != 'binding' AND c.confidence != 'fuzzy'",
        tuple(frontier),
    ).fetchall()
    nxt = set()
    for callee, rowid, name, args, rel in rows:
        test = TestRecognizer.for_conn(conn)(str(name), str(args), str(rel))
        if test:
            entry = found.setdefault(test[0], [(test[0], str(rel), test[1]), set(), hop])
            entry[1].update(origins[callee])
            entry[2] = min(entry[2], hop)
            continue
        mine = origins.setdefault(rowid, set())
        if not origins[callee] <= mine:
            mine |= origins[callee]
            nxt.add(rowid)
    return nxt


## @brief The links of one kind.
## @param kinds {test: kind}.
## @param kind The kind.
## @return Tests, ordered.
## @version 1
## @utility
def _of_kind(kinds: dict[str, str], kind: str) -> tuple[str, ...]:
    """@brief Filter. @return Tests."""
    return tuple(sorted(t for t, k in kinds.items() if k == kind))


## @brief The test functions the index holds in some files.
## @param conn Open connection.
## @param files Repo-relative paths.
## @return (test, file, lookup names).
## v2: framework recognition, not a `test_` name filter.
## v3: test code from test_scope and declared shapes (2.0.0, P4 W1)
## @version 3
## @utility
def _tests_in_files(conn: object, files: tuple[str, ...]) -> list[tuple[str, str, tuple[str, ...]]]:
    """@brief Tests per file, recognised by framework. @return (test, file, lookup names)."""
    from .frameworks import TestRecognizer

    out = []
    for rel in files:
        rows = conn.execute(
            "SELECT DISTINCT m.name, COALESCE(m.argsstring, '') FROM memberdef m "
            "JOIN path p ON p.rowid = m.file_id WHERE p.name = ? AND m.kind = 'function'",
            (rel,),
        )
        for name, args in rows:
            test = TestRecognizer.for_conn(conn)(str(name), str(args), rel)
            if test:
                out.append((test[0], rel, test[1]))
    return out


## @brief The indexed tests linked to a requirement, with their files.
## @param conn Open connection.
## @param req_id The requirement.
## @return (test, file, lookup names), ordered.
## v2: framework names (a tagged `SCENARIO` row is its scenario).
## v3: test code from test_scope and declared shapes (2.0.0, P4 W1)
## @version 3
## @utility
def _linked_tests(conn: object, req_id: str) -> list[tuple[str, str, tuple[str, ...]]]:
    """A FRAMEWORK CASE IS NAMED BY ITS FRAMEWORK: a tagged Catch2 `SCENARIO` row is the scenario's
    own name, not "SCENARIO"; a row no framework recognises keeps its indexed name.

    @brief Linked tests.
    @return (test, file, lookup names).
    """
    from .frameworks import TestRecognizer

    if not table_exists(conn, "req_test_edges"):
        return []
    rows = conn.execute(
        "SELECT DISTINCT m.name, COALESCE(m.argsstring, ''), COALESCE(p.name, '') "
        "FROM req_test_edges t JOIN memberdef m ON m.rowid = t.test_memberdef_rowid "
        "LEFT JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        "WHERE t.req_id = ? ORDER BY m.name",
        (req_id,),
    )
    out = []
    for name, args, rel in rows:
        test = TestRecognizer.for_conn(conn)(str(name), str(args), str(rel)) or (
            str(name),
            (str(name),),
        )
        out.append((test[0], str(rel), test[1]))
    return out


## @brief Each implementer of a requirement with its file and body span.
## @param conn Open connection.
## @param req_id The requirement.
## @return (name, file, start, end) per implementer.
## v2 (round 4): a tagged function in TEST CODE is a test of the requirement, not an implementer.
## @version 2
## @utility
def _implementer_spans(conn: object, req_id: str) -> list[tuple[str, str, int, int]]:
    """A TEST IS NEVER ITS REQUIREMENT'S IMPLEMENTER: counting it made a test's extent read
    "1 of 2" where the requirement has one implementer and the test exercises it.

    @brief Implementer locations.
    @return Rows.
    """
    if not table_exists(conn, "req_edges"):
        return []
    tests = (
        " AND p.rowid NOT IN (SELECT path_rowid FROM test_scope)"
        if table_exists(conn, "test_scope")
        else ""
    )
    rows = conn.execute(
        "SELECT DISTINCT m.name, p.name, m.bodystart, m.bodyend FROM req_edges r "
        "JOIN memberdef m ON m.rowid = r.memberdef_rowid "
        "JOIN path p ON p.rowid = COALESCE(NULLIF(m.bodyfile_id, 0), m.file_id) "
        f"WHERE r.req_id = ?{tests} ORDER BY m.name",
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
## @utility
def _covered(hits: dict[str, dict[int, int]], rel: str, start: int, end: int) -> bool:
    """@brief Span coverage. @return Covered?"""
    lines = hits.get(rel) or {}
    return any(n for line, n in lines.items() if start <= line <= end)
