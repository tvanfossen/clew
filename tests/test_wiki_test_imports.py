# SPDX-License-Identifier: MIT
"""Round 3, P3c-1 imports: CTRF results, hardened JUnit, Sphinx-needs requirements.

  * CTRF (Common Test Report Format) is a result format like the others: declared, never
    sniffed; `pending` is a skip and `other` an error.
  * JUNIT VARIANTS the plan names: a JUnit 5 / parametrised `name(args)[n]` is the function
    `name`; `status="disabled"` (or `"skipped"`) with no child element is a skip, not a pass; a
    test that failed and then passed on a rerun (`flakyFailure` / `rerunFailure` only) passed.
  * SPHINX-NEEDS `needs.json` (`requirements.needs`) contributes requirements: titles and content for ids
    the catalog does not describe, and a need the index has never seen becomes a requirement with
    no implementer — MISSING, not absent. The repository's own catalog wins where both speak.

@brief Tests for CTRF, JUnit variants and the needs.json import.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

from tests.test_wiki_site import _WIKI, repo  # noqa: F401  (module fixture reused)


def test_ctrf_results_fold_like_every_other_format(tmp_path: Path) -> None:
    """@brief CTRF: statuses mapped, parameters dropped, worst case wins."""
    from clew.wiki.imports import RESULT_FORMATS, parse_results

    report = tmp_path / "ctrf.json"
    report.write_text(
        json.dumps(
            {
                "results": {
                    "tool": {"name": "pytest"},
                    "tests": [
                        {"name": "test_a", "status": "passed"},
                        {"name": "test_b[1]", "status": "passed"},
                        {"name": "test_b[2]", "status": "failed", "message": "boom"},
                        {"name": "test_c", "status": "pending"},
                        {"name": "test_d", "status": "other"},
                    ],
                }
            }
        )
    )
    assert "ctrf" in RESULT_FORMATS
    found = parse_results("ctrf", report)
    assert {n: r.status for n, r in found.items()} == {
        "test_a": "passed",
        "test_b": "failed",
        "test_c": "skipped",
        "test_d": "error",
    }
    assert found["test_b"].cases == 2


def test_junit_variants_name_the_function_and_classify_honestly(tmp_path: Path) -> None:
    """@brief JUnit 5 names, disabled cases, reruns that passed."""
    from clew.wiki.evidence import parse_junit

    report = tmp_path / "junit.xml"
    report.write_text(
        "<testsuites><testsuite>"
        '<testcase name="adds(int, int)[1]"/>'
        '<testcase name="adds(int, int)[2]"/>'
        '<testcase name="off" status="disabled"/>'
        '<testcase name="flaky"><flakyFailure message="once"/></testcase>'
        '<testcase name="gone" status="skipped"/>'
        "</testsuite></testsuites>"
    )
    found = parse_junit([report])
    assert {n: r.status for n, r in found.items()} == {
        "adds": "passed",
        "off": "skipped",
        "flaky": "passed",
        "gone": "skipped",
    }
    assert found["adds"].cases == 2


def test_needs_json_contributes_requirements(repo: tuple[Path, Path], tmp_path: Path) -> None:  # noqa: F811
    """THE CATALOG WINS where both speak; a need nothing implements is MISSING, with its title.

    @brief needs.json import.
    """
    from clew.wiki.build import build_wiki

    needs = tmp_path / "needs.json"
    needs.write_text(
        json.dumps(
            {
                "current_version": "1",
                "versions": {
                    "1": {
                        "needs": {
                            "REQ-W-001": {"id": "REQ-W-001", "type": "req", "title": "Not this"},
                            "REQ-W-002": {
                                "id": "REQ-W-002",
                                "type": "req",
                                "title": "Finish the run",
                                "content": "It finishes.",
                            },
                            "REQ-N-001": {"id": "REQ-N-001", "type": "req", "title": "Export it"},
                            "SPEC-1": {"id": "SPEC-1", "type": "spec", "title": "A spec"},
                        }
                    }
                },
            }
        )
    )
    config = tmp_path / "wiki.yaml"
    ## FIXTURE CHANGED (2.0.0, R5-CFG F7): `wiki.needs` moved to `requirements.needs`.
    config.write_text(f"requirements:\n  needs: {needs}\n" + _WIKI)
    html = build_wiki(repo[0], repo[1], tmp_path / "out", config_path=config)
    page = (html / "requirements.html").read_text()
    assert "Load the data" in page and "Not this" not in page
    ## Round 4, R4: the acceptance text is on the requirement's own page, not in the index.
    assert "Finish the run" in page
    assert "It finishes." in (html / "req-REQ-W-002.html").read_text()
    row = page[page.index('<tr data-group="REQ-N"') :].split("</tr>")[0]
    assert "REQ-N-001" in row and "t-MISSING" in row and "Export it" in row
    assert "SPEC-1" not in page
