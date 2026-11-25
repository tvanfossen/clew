# SPDX-License-Identifier: MIT
"""clew adopts its own wiki and guard, completely (round 3, P6c).

OWNER 2026-11-16, asked whether adoption was "full and complete for clew": it was not. The gate
ran; the wiki was configured but read no test results, ran no check hook, had no impact report and
was built nowhere; `@req` coverage was ungated with a stale figure in the header. Each test here
pins one piece of the adoption, so it cannot quietly lapse the way the coverage gate did when
`scripts/req_coverage_audit.py` was deleted.

PAGES (owner): CI builds the site and uploads it now; the Pages DEPLOY switches on at the 2.0.0
cut — so this file asserts the build and the artifact, and asserts NO deploy step yet.

@brief clew dogfoods its wiki and guard.
@version 2
"""

from __future__ import annotations

from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent


def _clew_yaml() -> dict:
    return yaml.safe_load((REPO / ".clew.yaml").read_text(encoding="utf-8"))


def _hooks() -> dict[str, dict]:
    doc = yaml.safe_load((REPO / ".pre-commit-config.yaml").read_text(encoding="utf-8"))
    return {h["id"]: h for r in doc["repos"] for h in r["hooks"]}


def test_every_gate_run_writes_junit_where_the_wiki_reads_it() -> None:
    """@brief run_tests.py writes build/junit.xml; clew's wiki reads it and the CI coverage file."""
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_tests", REPO / "scripts" / "run_tests.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert "--junitxml=build/junit.xml" in module.PYTEST_ARGS
    tests = _clew_yaml()["tests"]  # 2.0.0 (R5-CFG F20): the top-level tests: section
    assert tests["junit"] == ["build/junit.xml"]
    assert tests["coverage"] == "build/coverage.xml"
    ## Round 4 (owner 2026-11-17: tests are linked to source by coverage, never by a tag): the
    ## coverage run records which test ran each line, and the wiki links tests by it.
    assert "--cov-context=test" in module.COVERAGE_ARGS
    ## Contexts are read from coverage's own data file: the JSON form measured 3.9 GB here.
    assert not any("json" in a for a in module.COVERAGE_ARGS)
    assert tests["contexts"] == ".coverage"


def test_the_wiki_check_and_impact_hooks_run_on_clew_itself() -> None:
    """@brief clew-wiki-check validates the wiki: section; clew-guard-impact writes impact.json."""
    hooks = _hooks()
    assert "clew-wiki-check" in hooks
    impact = hooks["clew-guard-impact"]
    assert "impact" in impact.get("args", []) or "impact" in impact["entry"]
    ## 2.0.0 (R5-CFG F9): one report directory; the hook writes it with `--write`.
    assert "--write" in impact.get("args", [])
    assert _clew_yaml()["guard"]["impact"] == {"report_dir": "docs/generated/impact/"}


def test_ci_builds_clews_own_wiki_and_does_not_deploy_it_yet() -> None:
    """@brief A CI job runs the composite action from this checkout and uploads the site."""
    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    job = ci["jobs"]["wiki"]
    uses = [s.get("uses", "") for s in job["steps"]]
    assert "./.github/actions/wiki" in uses
    assert any(u.startswith("actions/upload-artifact@") for u in uses)
    assert not any("deploy-pages" in u for u in uses), "Pages deploys at the 2.0.0 cut, not before"
    text = (REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    assert "run_tests.py --coverage" in text


def test_the_declaration_header_states_what_is_configured() -> None:
    """@brief The header no longer claims only the gate is configured, nor quotes a stale figure."""
    head = (REPO / ".clew.yaml").read_text(encoding="utf-8").split("\nguard:", 1)[0]
    assert "Only the gate is configured" not in head
    assert "30 of 34" not in head
    assert "wiki:" in head and "guard:" in head


def test_every_catalogued_requirement_has_an_implementer_or_an_exempt_status() -> None:
    """THE GATE `scripts/req_coverage_audit.py` ONCE WAS, back and declared: the hook runs `clew
    guard coverage`, and on this tree it passes — every requirement tagged, or exempt by status
    (`planned`, `configuration`), each exemption still listed in the report.

    @brief clew-guard-coverage hook, and a clean run on clew.
    """
    import os
    import subprocess

    hook = _hooks()["clew-guard-coverage"]
    assert "coverage" in hook["entry"]
    req = _clew_yaml()["requirements"]  # 2.0.0: the top-level catalog section
    assert req["exempt_status"] == ["planned", "configuration"]
    out = subprocess.run(
        [str(REPO / ".venv" / "bin" / "python"), "-m", "clew", "guard", "coverage", "clew"],
        cwd=REPO,
        capture_output=True,
        text=True,
        env={**os.environ},
        timeout=300,
    )
    assert out.returncode == 0, out.stdout + out.stderr
    assert "Exempt by status" in out.stdout


def test_ci_records_the_traced_run_the_wiki_s_real_values_come_from() -> None:
    """2.1 (roadmap: trace-run in CI). X-2 gave the dossier flow real values from one traced test,
    recorded by hand: CI's site, and so the published wiki, had none. The wiki job now runs that
    trace before building, to a path `tests.traces` in `.clew.yaml` reads.

    @brief CI traces the dossier test before the wiki builds.
    """
    import fnmatch

    ci = yaml.safe_load((REPO / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8"))
    steps = ci["jobs"]["wiki"]["steps"]
    runs = [s.get("run", "") for s in steps]
    traced = next((i for i, r in enumerate(runs) if "clew wiki trace-run" in r), None)
    assert traced is not None, "the wiki job runs no trace-run"
    site = next(i for i, s in enumerate(steps) if s.get("uses") == "./.github/actions/wiki")
    assert traced < site, "the trace must exist before the site is built"
    out = runs[traced].split("--out", 1)[1].split()[0]
    globs = _clew_yaml()["tests"]["traces"]
    assert any(fnmatch.fnmatch(out, g) for g in globs), (out, globs)
