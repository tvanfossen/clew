# SPDX-License-Identifier: MIT
"""Change impact as its own section of the site (round 3, P1g).

Owner 2026-11-15: "change impact can be a top bar item". clew-guard's impact report lists the
requirements whose implementing functions changed; the section follows each changed function to
the requirements it implements and the flows it is on.

ABSENCE IS NOT EMPTINESS: without a report the section says the change was NOT MEASURED (and how
to measure it); an empty report says no requirement was affected — a measured zero.

@brief Tests for the change-impact page.
@version 1
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.test_wiki_site import _WIKI, repo  # noqa: F401  (module fixture reused)


## @brief Build the site with a config naming an impact report.
## @param repo The indexed fixture repository.
## @param tmp_path Scratch.
## @param report The report's contents, or None for no report.
## @return {page: html}.
## @version 1
def _site(repo: tuple[Path, Path], tmp_path: Path, report: list | None) -> dict[str, str]:  # noqa: F811
    from clew.wiki.build import build_wiki

    config = tmp_path / "wiki.yaml"
    impact = tmp_path / "impact.json"
    ## FIXTURE CHANGED (2.0.0, R5-CFG F9): `wiki.impact` is gone; the report is read from the gate's
    ## `guard.impact.report_dir`, here in the same out-of-tree config.
    config.write_text(_WIKI + f"guard:\n  impact:\n    report_dir: {tmp_path}\n")
    if report is not None:
        impact.write_text(json.dumps(report))
    html = build_wiki(repo[0], repo[1], tmp_path / "out", config_path=config)
    return {p.name: p.read_text() for p in html.glob("*.html")}


_REPORT = [
    {
        "req_id": "REQ-W-001",
        "req_name": "Load",
        "functions": [{"name": "load", "file": "src/data.py", "version": 2}],
    }
]


def test_change_impact_follows_a_changed_function_to_requirements_and_flows(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    """@brief P1g: changed function → requirement → flow, in the top bar after Flows."""
    pages = _site(repo, tmp_path, _REPORT)
    page = pages["impact.html"]
    nav = page[page.index('<nav class="nav"') : page.index("</nav>")]
    order = [nav.index(f">{s}<") for s in ("Flows", "Change impact", "Map")]
    assert order == sorted(order)
    assert re.search(r'data-stat="requirements"[^>]*>\s*<b>1</b>', page)
    assert re.search(r'data-stat="functions"[^>]*>\s*<b>1</b>', page)
    row = page[page.index("<code>load</code>") :].split("</tr>")[0]
    ## Round 4, R4: a requirement links to its own page.
    assert 'href="req-REQ-W-001.html"' in row and 'href="flow-load.html"' in row
    assert "## Change impact" not in pages["requirements.html"]


def test_without_a_report_the_change_is_not_measured(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    """@brief P1g: no report → "not measured", never a section claiming nothing changed."""
    page = _site(repo, tmp_path, None)["impact.html"]
    assert "Not measured" in page and "clew-guard" in page
    assert "No requirement was affected" not in page


def test_an_empty_report_is_a_measured_zero(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    """@brief P1g: an empty report says nothing was affected."""
    page = _site(repo, tmp_path, [])["impact.html"]
    assert "No requirement was affected" in page and "Not measured" not in page


def test_the_impact_page_links_the_map_change_lens(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    """@brief P1g: the page points at the map's change lens, which opens preselected."""
    page = _site(repo, tmp_path, _REPORT)["impact.html"]
    assert 'href="map.html#lens=change"' in page


def test_a_changed_functions_flows_are_capped_product_first() -> None:
    """FOUND ON CLEW'S OWN WIKI (round 4): `_build_argparser` is on dozens of test flows, and its
    row listed every one. Product flows come first; at most five are listed, the rest counted.
    Requirements link to their own pages (R4).

    @brief Impact rows: product flows first, five listed, the rest counted.
    """
    from types import SimpleNamespace

    from clew.wiki.impactpage import _flow_cell

    pages = [
        SimpleNamespace(name=f"flow-t{i}", title=f"test {i}", role="tests") for i in range(7)
    ] + [SimpleNamespace(name="flow-main", title="main", role="product")]
    cell = _flow_cell(pages)
    assert cell.index("flow-main") < cell.index("flow-t0")
    ## SPEC CHANGED (2.0.0, V5, owner Q/A 2026-11-20): five are still SHOWN, product first; the
    ## rest now open from a closed "3 more" instead of only being counted.
    shown, _sep, hidden = cell.partition("<details")
    assert shown.count("<a ") == 5 and "<summary>3 more</summary>" in hidden
    assert hidden.count("<a ") == 3
