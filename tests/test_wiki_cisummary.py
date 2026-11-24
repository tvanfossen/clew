# SPDX-License-Identifier: MIT
"""A short evidence summary beside the site, for a CI run's summary tab (#72 item 12, 2.1).

#72 (an adopter, 2026-11-23): a per-build Markdown summary for the CI summary tab (Azure DevOps
`##vso[task.uploadsummary]`, GitHub's job summary) — requirements, tests this run, coverage.

@brief Tests the CI summary.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.wiki.cisummary import ci_summary
from clew.wiki.evidence import CaseResult, RequirementEvidence


def _ev(rid: str, tier: str, implementers=("f",)) -> RequirementEvidence:  # noqa: ANN001
    return RequirementEvidence(rid, "", tier, (), tuple(implementers))


def test_the_summary_counts_requirements_tests_and_coverage(tmp_path: Path) -> None:
    """@brief Each tier counted, tests by result, Cobertura's line and branch rates."""
    cobertura = tmp_path / "coverage.xml"
    cobertura.write_text('<coverage line-rate="0.8421" branch-rate="0.61"><packages/></coverage>')
    text = ci_summary(
        "Lib",
        [_ev("R1", "PASS"), _ev("R2", "PASS"), _ev("R3", "GAP"), _ev("R4", "MISSING", ())],
        {
            "t1": CaseResult("t1", "passed", 1),
            "t2": CaseResult("t2", "failed", 1),
            "t3": CaseResult("t3", "skipped", 1),
        },
        cobertura,
    )
    assert text.startswith("## Lib — clew evidence")
    assert "**4** requirements · 3 implemented" in text
    assert "| PASS | 2 |" in text and "| GAP | 1 |" in text and "| MISSING | 1 |" in text
    assert "**3** tests: 1 passed, 1 failed, 1 skipped" in text
    assert "line 84.2% · branch 61.0%" in text


def test_what_was_not_measured_says_so(tmp_path: Path) -> None:
    """@brief No report is "not measured", never a zero."""
    text = ci_summary("Lib", [_ev("R1", "MISSING", ())], {}, None)
    assert "No test report was read" in text and "Coverage: not measured" in text
    assert "0 passed" not in text and "0.0%" not in text


def test_a_build_writes_the_summary_beside_the_site(tmp_path: Path) -> None:
    """@brief `clew wiki build --out X` → `X/summary.md`, next to `X/html`."""
    from tests.test_wiki_page_weight import _SRC, _WIKI
    from clew.cli import _build_argparser, _run_pipeline
    from clew.wiki.build import build_wiki

    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "__init__.py").write_text("")
    (repo / "pkg" / "mod.py").write_text(_SRC)
    (repo / "README.md").write_text("# Weight\n")
    (repo / ".clew.yaml").write_text(_WIKI)
    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    html = build_wiki(repo, db, tmp_path / "out")
    summary = html.parent / "summary.md"
    assert summary.is_file() and "clew evidence" in summary.read_text()


def test_build_takes_summary_for_either_format() -> None:
    """@brief `clew wiki build --summary FILE` (a Markdown wiki's own directory is its pages)."""
    from clew.wiki.command import _parser

    args = _parser().parse_args(
        ["build", "--out", "o", "--format", "markdown", "--summary", "s.md"]
    )
    assert args.summary == "s.md"


def test_a_markdown_build_writes_the_summary_where_asked(tmp_path: Path) -> None:
    """@brief Not among the pages: at the path given."""
    from tests.test_wiki_page_weight import _SRC, _WIKI
    from clew.cli import _build_argparser, _run_pipeline
    from clew.wiki.markdown import build_markdown

    repo = tmp_path / "repo"
    (repo / "pkg").mkdir(parents=True)
    (repo / "pkg" / "mod.py").write_text(_SRC)
    (repo / ".clew.yaml").write_text(_WIKI)
    db = tmp_path / "x.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    out = build_markdown(repo, db, tmp_path / "md", "ado", summary=tmp_path / "s.md")
    assert (tmp_path / "s.md").is_file() and not (out / "summary.md").exists()


def test_the_ci_templates_hand_the_summary_to_the_run() -> None:
    """@brief GitHub's job summary and Azure DevOps' uploadsummary both receive it."""
    root = Path(__file__).resolve().parents[1]
    action = (root / ".github" / "actions" / "wiki" / "action.yml").read_text()
    assert "--summary" in action and "GITHUB_STEP_SUMMARY" in action
    azure = (root / "templates" / "azure-pipelines-wiki.yml").read_text()
    assert "--summary" in azure and "##vso[task.uploadsummary]" in azure
