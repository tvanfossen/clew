# SPDX-License-Identifier: MIT
"""Evidence imports beyond JUnit and Cobertura (1.4.0 W15, W16; owner 2026-11-15).

COVERAGE (W15). gcov's own outputs, read into the `{file: {line: hits}}` shape Cobertura gives:
  * `.gcov` text — `count:line:source`, where `-` is a NON-EXECUTABLE line (absent, not zero) and
    `#####` / `=====` an executable line never run (zero);
  * gcov's `--json-format` and gcovr's `--json` (`.json`, `.json.gz`) — `files[].lines[]`.
A path is made repo-relative: an absolute one under the repository, or one relative to the
report's directory or gcov's recorded working directory that resolves into it.

RESULTS (W16). CTest `Test.xml`, TAP, Catch2's XML reporter, pytest-json-report, Ceedling's XML
report and Unity's text output, each DECLARED
with its format (`RESULT_FORMATS`) — nothing is sniffed. Each folds like JUnit: one result per
test name, the WORST case's status, pytest parameters dropped so the name is the function's.

LINKS (W16). A MAPPING file links requirements to tests the index cannot see a `@req` tag on
(`{REQ: [test]}` YAML or a `req,test` CSV). Gherkin `.feature` SCENARIOS link through their tags
— their own and the feature's / rule's they inherit — with `@ID` or `@req:ID`.

Every report is capped at `evidence.MAX_REPORT_BYTES`; these are CI artifacts the operator chose.

@brief Parse gcov, other result formats, mapping files and Gherkin features.
@version 1
"""

from __future__ import annotations

import csv
import gzip
import io
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

## Result formats `wiki.tests.results` may declare.
RESULT_FORMATS = ("ctest", "tap", "catch2", "pytest-json", "ceedling", "unity")
## Worst-first statuses (JUnit's rank).
_RANK = {"error": 0, "failed": 1, "skipped": 2, "passed": 3}
_PARAMS = re.compile(r"\[.*\]$")
## `ok 3 - name # SKIP why` → (not, name, directive).
_TAP_LINE = re.compile(r"^(not )?ok\b\s*\d*\s*(?:-\s*)?(.*?)(?:\s+#\s*(SKIP|TODO)\b.*)?$", re.I)
_SCENARIO = re.compile(r"^(Scenario(?: Outline| Template)?|Example):\s*(.*)$")
_CTEST = {"passed": "passed", "failed": "failed", "notrun": "skipped", "disabled": "skipped"}
_PYTEST = {"xfailed": "skipped", "xpassed": "passed"}
_UNITY_LINE = re.compile(r"^[^:]+:\d+:(\w+):(PASS|FAIL|IGNORE)(?::\s*(.*))?$")
_UNITY = {"PASS": "passed", "FAIL": "failed", "IGNORE": "skipped"}


## @brief One Gherkin scenario with its effective tags.
## @version 1
@dataclass(frozen=True)
class Scenario:
    """@brief Feature file, line, scenario name, tags (`@` and `req:` removed). @version 1"""

    file: str
    line: int
    name: str
    tags: tuple[str, ...]

    ## @brief The test id the trace shows: `<feature file>::<scenario>`.
    ## @return The id.
    ## @version 1
    ## @req REQ-DDB-WIKI-010
    @property
    def test_id(self) -> str:
        """@brief Id. @return `file::name`."""
        return f"{self.file}::{self.name}"


## @brief Fold (name, status, message) cases into one result per name, worst status first.
## @param cases The cases.
## @return {name: CaseResult}.
## @version 1
## @req REQ-DDB-WIKI-010
def fold_cases(cases: Iterable[tuple[str, str, str]]) -> dict[str, Any]:
    """@brief Fold. @return Results."""
    from .evidence import CaseResult

    folded: dict[str, list[tuple[str, str]]] = {}
    for name, status, message in cases:
        if name:
            folded.setdefault(name, []).append((status, message))
    return {
        name: CaseResult(
            name=name,
            status=min(rows, key=lambda r: _RANK[r[0]])[0],
            cases=len(rows),
            message=next((m for s, m in rows if s == "skipped" and m), ""),
        )
        for name, rows in folded.items()
    }


## @brief Read one result report of a declared format.
## @param fmt One of RESULT_FORMATS.
## @param path The report.
## @return {test name: CaseResult}.
## v2: Ceedling's XML report and Unity's text output.
## @version 2
## @req REQ-DDB-WIKI-010
def parse_results(fmt: str, path: Path) -> dict[str, Any]:
    """@brief Parse a report. @return Results."""
    readers = {
        "ctest": _ctest,
        "tap": _tap,
        "catch2": _catch2,
        "pytest-json": _pytest_json,
        "ceedling": _ceedling,
        "unity": _unity,
    }
    if fmt not in readers:
        raise ValueError(f"unknown result format {fmt!r} (known: {', '.join(RESULT_FORMATS)})")
    return fold_cases(readers[fmt](_text(path)))


## @brief Read gcov reports into line hits per repo-relative file.
## @param paths `.gcov` text, or gcov / gcovr JSON (`.json`, `.json.gz`) files.
## @param repo_root The repository the paths are made relative to.
## @return {file: {line: hits}}; hits from several reports are summed.
## @version 1
## @req REQ-DDB-WIKI-009
def parse_gcov(paths: Iterable[Path], repo_root: Path) -> dict[str, dict[int, int]]:
    """@brief Parse gcov. @return Hits."""
    hits: dict[str, dict[int, int]] = {}
    root = Path(repo_root).resolve()
    for path in paths:
        is_json = path.name.endswith((".json", ".json.gz"))
        rows = _gcov_json(path, root) if is_json else _gcov_text(path, root)
        for rel, line, count in rows:
            lines = hits.setdefault(rel, {})
            lines[line] = lines.get(line, 0) + count
    return hits


## @brief Read a requirement → test mapping file.
## @param path `{REQ: [test]}` YAML (a scalar is one test) or a CSV with `req` and `test` columns.
## @return {requirement: tests}, in file order.
## @version 1
## @req REQ-DDB-WIKI-010
def parse_mapping(path: Path) -> dict[str, tuple[str, ...]]:
    """@brief Parse a mapping. @return Links."""
    text = _text(path)
    out: dict[str, list[str]] = {}
    if path.suffix.lower() == ".csv":
        for row in csv.DictReader(io.StringIO(text)):
            if row.get("req") and row.get("test"):
                out.setdefault(row["req"].strip(), []).append(row["test"].strip())
        return {k: tuple(v) for k, v in out.items()}
    import yaml

    doc = yaml.safe_load(text) or {}
    if not isinstance(doc, dict):
        raise ValueError(f"{path}: a mapping file maps a requirement id to its tests")
    return {
        str(k): tuple(str(t) for t in (v if isinstance(v, list) else [v]) if t is not None)
        for k, v in doc.items()
    }


## @brief Read coverage.py's per-test contexts: which tests ran each line.
## @param path A coverage.py JSON report written with contexts (`--cov-context=test`,
## `coverage json --show-contexts`).
## @param repo_root The repository the files are made relative to.
## @return {file: {line: test names}}; the empty (no-test) context is dropped.
## @version 1
## @req REQ-DDB-WIKI-016
def parse_contexts(path: Path, repo_root: Path) -> dict[str, dict[int, set[str]]]:
    """A CONTEXT IS `<nodeid>|<phase>`; the test is the nodeid's function, parameters dropped,
    the same name JUnit folding gives.

    @brief Parse contexts.
    @return Tests per line.
    """
    root = Path(repo_root).resolve()
    out: dict[str, dict[int, set[str]]] = {}
    for name, data in (json.loads(_text(path)).get("files") or {}).items():
        lines = out.setdefault(_relative(name, path.parent, root), {})
        for line, contexts in ((data or {}).get("contexts") or {}).items():
            tests = {_PARAMS.sub("", c.split("|", 1)[0].rsplit("::", 1)[-1]) for c in contexts}
            lines.setdefault(int(line), set()).update(t for t in tests if t)
    return out


## @brief Every scenario of the feature files the globs select.
## @param repo_root The repository.
## @param globs Repo-relative globs.
## @return Scenarios, by file then line.
## @version 1
## @req REQ-DDB-WIKI-010
def parse_features(repo_root: Path, globs: Iterable[str]) -> list[Scenario]:
    """@brief Parse Gherkin. @return Scenarios."""
    root = Path(repo_root)
    files = sorted({p for g in globs for p in root.glob(g) if p.is_file()})
    out: list[Scenario] = []
    for path in files:
        out += _scenarios(path.relative_to(root).as_posix(), _text(path))
    return out


## @brief The scenarios of one feature file.
## @param rel Its repo-relative path.
## @param text Its content.
## @return Scenarios.
## @version 1
## @dg_internal
def _scenarios(rel: str, text: str) -> list[Scenario]:
    """FEATURE TAGS APPLY TO EVERY SCENARIO, a Rule's to the scenarios under it; an Examples
    block's tags select example rows, not requirements, and are dropped.

    @brief Walk one file.
    @return Scenarios.
    """
    pending: list[str] = []
    scopes = {"Feature": (), "Rule": ()}
    out = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if line.startswith("@"):
            pending += [_tag(t) for t in line.split() if t.startswith("@")]
            continue
        keyword = line.split(":", 1)[0]
        match = _SCENARIO.match(line)
        if match:
            tags = (*scopes["Feature"], *scopes["Rule"], *pending)
            out.append(Scenario(rel, number, match.group(2).strip(), tuple(dict.fromkeys(tags))))
        elif keyword in scopes:
            scopes[keyword] = tuple(pending)
        if line and not line.startswith("#"):
            pending = []
    return out


## @brief A tag without its `@` and an optional `req:` / `req=` prefix.
## @param token The token.
## @return The tag.
## @version 1
## @dg_internal
def _tag(token: str) -> str:
    """@brief Normalise a tag. @return Tag."""
    tag = token[1:]
    return tag[4:] if tag.lower().startswith(("req:", "req=")) else tag


## @brief A report's text, refused when oversized; `.gz` is decompressed.
## @param path The report.
## @return The text.
## @version 1
## @dg_internal
def _text(path: Path) -> str:
    """@brief Read capped. @return Text."""
    from .evidence import MAX_REPORT_BYTES

    if path.stat().st_size > MAX_REPORT_BYTES:
        raise ValueError(f"{path} is larger than {MAX_REPORT_BYTES} bytes; refusing to parse it")
    data = path.read_bytes()
    if path.suffix == ".gz":
        data = gzip.decompress(data)
    return data.decode("utf-8", errors="replace")


## @brief CTest `Test.xml` cases.
## @param text The report.
## @return (name, status, message) cases.
## @version 1
## @dg_internal
def _ctest(text: str) -> list[tuple[str, str, str]]:
    """@brief Read CTest. @return Cases."""
    return [
        (t.findtext("Name") or "", _CTEST.get(t.get("Status") or "", "error"), "")
        for t in ET.fromstring(text).iter("Test")
    ]


## @brief Catch2 XML reporter cases.
## @param text The report.
## @return Cases.
## @version 1
## @dg_internal
def _catch2(text: str) -> list[tuple[str, str, str]]:
    """A CASE THAT SKIPPED (`skips > 0`) is skipped even though Catch2 counts it a success.

    @brief Read Catch2.
    @return Cases.
    """
    out = []
    for case in ET.fromstring(text).iter("TestCase"):
        result = case.find("OverallResult")
        attrs = result.attrib if result is not None else {}
        if int(attrs.get("skips") or 0) > 0:
            status = "skipped"
        else:
            status = "passed" if attrs.get("success") == "true" else "failed"
        out.append((case.get("name") or "", status, ""))
    return out


## @brief Ceedling's XML test report (`xml_tests_report`).
## @param text The report.
## @return Cases named by their test function.
## @version 1
## @dg_internal
def _ceedling(text: str) -> list[tuple[str, str, str]]:
    """@brief Read Ceedling. @return Cases."""
    root = ET.fromstring(text)
    out = []
    for group, status in (
        ("SuccessfulTests", "passed"),
        ("FailedTests", "failed"),
        ("IgnoredTests", "skipped"),
    ):
        for test in root.iter(group):
            for case in test.iter("Test"):
                out.append(((case.findtext("Name") or "").rsplit("::", 1)[-1], status, ""))
    return out


## @brief Unity's text output: `file:line:test:PASS|FAIL|IGNORE[:message]`.
## @param text The output.
## @return Cases.
## @version 1
## @dg_internal
def _unity(text: str) -> list[tuple[str, str, str]]:
    """@brief Read Unity. @return Cases."""
    out = []
    for line in text.splitlines():
        match = _UNITY_LINE.match(line.strip())
        if match:
            out.append((match.group(1), _UNITY[match.group(2)], match.group(3) or ""))
    return out


## @brief TAP lines.
## @param text The stream.
## @return Cases; `# SKIP` and `# TODO` are skipped (a TODO is an expected failure).
## @version 1
## @dg_internal
def _tap(text: str) -> list[tuple[str, str, str]]:
    """@brief Read TAP. @return Cases."""
    out = []
    for line in text.splitlines():
        match = _TAP_LINE.match(line.strip())
        if not match:
            continue
        failed, name, directive = match.groups()
        status = "skipped" if directive else ("failed" if failed else "passed")
        out.append((name.strip(), status, ""))
    return out


## @brief pytest-json-report cases.
## @param text The report.
## @return Cases named by function, parameters dropped.
## @version 1
## @dg_internal
def _pytest_json(text: str) -> list[tuple[str, str, str]]:
    """@brief Read pytest-json-report. @return Cases."""
    out = []
    for test in json.loads(text).get("tests") or []:
        name = _PARAMS.sub("", str(test.get("nodeid") or "").rsplit("::", 1)[-1])
        outcome = str(test.get("outcome") or "error")
        out.append((name, _PYTEST.get(outcome, outcome if outcome in _RANK else "error"), ""))
    return out


## @brief The rows of one `.gcov` text file.
## @param path The file.
## @param root The resolved repository root.
## @return (file, line, hits) rows; non-executable lines are not rows.
## @version 1
## @dg_internal
def _gcov_text(path: Path, root: Path) -> list[tuple[str, int, int]]:
    """@brief Read .gcov. @return Rows."""
    rel, rows = "", []
    for raw in _text(path).splitlines():
        parts = raw.split(":", 2)
        if len(parts) < 3:
            continue
        count, number = parts[0].strip(), parts[1].strip()
        if number == "0" and parts[2].startswith("Source:"):
            rel = _relative(parts[2][len("Source:") :], path.parent, root)
        elif count != "-" and number.isdigit() and rel:
            hits = 0 if count.startswith(("#", "=")) else int(count.rstrip("*") or 0)
            rows.append((rel, int(number), hits))
    return rows


## @brief The rows of one gcov / gcovr JSON report.
## @param path The report.
## @param root The resolved repository root.
## @return Rows.
## @version 1
## @dg_internal
def _gcov_json(path: Path, root: Path) -> list[tuple[str, int, int]]:
    """@brief Read gcov JSON. @return Rows."""
    doc = json.loads(_text(path))
    base = Path(doc.get("current_working_directory") or path.parent)
    return [
        (_relative(str(f.get("file") or ""), base, root), int(ln["line_number"]), int(ln["count"]))
        for f in doc.get("files") or []
        for ln in f.get("lines") or []
    ]


## @brief A report's source path made repo-relative where it resolves into the repository.
## @param name The path as the report wrote it.
## @param base The directory a relative path is relative to.
## @param root The resolved repository root.
## @return The repo-relative path, or the name as written.
## @version 1
## @dg_internal
def _relative(name: str, base: Path, root: Path) -> str:
    """AN ABSOLUTE PATH needs only to lie under the repository; a RELATIVE one must resolve to a
    file there, from the root first, then from the report's base.

    @brief Relativise.
    @return Path.
    """
    name = name.strip()
    if Path(name).is_absolute():
        resolved = Path(name).resolve()
        return resolved.relative_to(root).as_posix() if resolved.is_relative_to(root) else name
    for candidate in (root / name, base / name):
        resolved = candidate.resolve()
        if resolved.is_relative_to(root) and resolved.exists():
            return resolved.relative_to(root).as_posix()
    return name.removeprefix("./")
