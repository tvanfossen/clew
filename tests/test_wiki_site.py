# SPDX-License-Identifier: MIT
"""The wiki site, round 2 (owner 2026-11-15, after the demo sites): W13, W14, W17, W18.

  * W13 — a DEFAULT THEME in the sassafras-class look (its botanical palette, Manrope / Newsreader /
    JetBrains Mono bundled under the OFL, no CDN), overridable per repository: palette tokens, an
    extra stylesheet, a logo, or another installed Sphinx theme by name;
  * W14 — requirement and test CHARTS (inline SVG donuts) and a SUMMARY page per requirement group;
  * W17 — a BURNDOWN of open requirements across recorded versions, with ROADMAP.md headings that
    name a version as milestones;
  * W18 — a UML-proper sequence diagram: activation bars, return arrows, numbered steps, drawn
    loop / alt frames, themed, and interactive — clicking a step opens a dialog with the data it
    carries (the call expression, the callee's signature), play / pause / step controls. An
    audience that excludes bodies gets no call text.

One indexed repository and one site build are shared by the module: Sphinx is the slow part.

@brief Tests for the wiki theme, charts, summary, burndown and sequence diagram.
@version 1
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

_DATA = '''\
from src.out import finish


def load(items):
    """Load the data.

    @req REQ-W-001
    """
    for item in items:
        parse(item, "SECRET_CALL_ARG")
    return finish()


def parse(raw, tag):
    """Parse one item.

    @req REQ-X-001
    """
    return raw  # SECRET_BODY_MARKER
'''

_OUT = '''\
def finish():
    """Finish up.

    @req REQ-W-002
    """
    return 1
'''

_TEST = '''\
from src.data import load


def test_load():
    """Covers the load. @req REQ-W-001"""
    assert load([]) == 1
'''

_FEATURE = """\
Feature: Finishing
  @REQ-W-002
  Scenario: Finish runs
    Then it finishes
"""

_JUNIT = """\
<testsuite><testcase classname="tests.test_data" name="test_load"/>
<testcase name="Finish runs"><failure message="no"/></testcase></testsuite>
"""

_ROADMAP = """\
# Roadmap

## v1.0 — first cut
Some text.

## v2.0 — the rest
"""

_WIKI = """\
wiki:
  title: Site Demo
  docs: [README.md]
  roadmap: ROADMAP.md
  flows:
    - entry: load
      depth: 2
  tests:
    junit: [junit.xml]
    features: ["tests/features/*.feature"]
    layers: {unit: ["tests/test_*"], bdd: ["tests/features/*"]}
    min_layers: 2
  links:
    template: "https://example.invalid/blob/{commit}/{file}#L{line}"
  theme:
    palette: {acc: "#123456"}
    css: docs/extra.css
  audiences:
    partner: {exclude_bodies: true}
"""


## @brief The indexed fixture repository, shared by the module.
## @param tmp_path_factory Pytest's factory.
## @return (repo, index).
## @version 1
@pytest.fixture(scope="module")
def repo(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Path]:
    """@brief Build the fixture. @return Paths."""
    root = tmp_path_factory.mktemp("site")
    repo = root / "repo"
    for rel, text in {
        "src/__init__.py": "",
        "src/data.py": _DATA,
        "src/out.py": _OUT,
        "tests/test_data.py": _TEST,
        "tests/features/finish.feature": _FEATURE,
        "junit.xml": _JUNIT,
        "README.md": "# Demo\n\nThe demo repository.\n",
        "ROADMAP.md": _ROADMAP,
        "docs/extra.css": ".repo-extra{color:red}\n",
        ".clew.yaml": _WIKI,
    }.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    db = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    return repo, db


## @brief The full site, built once.
## @param repo The fixture.
## @param tmp_path_factory Pytest's factory.
## @return {relative page path: html}.
## @version 1
@pytest.fixture(scope="module")
def site(repo: tuple[Path, Path], tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """@brief Build. @return Pages."""
    from clew.wiki.build import build_wiki

    html = build_wiki(repo[0], repo[1], tmp_path_factory.mktemp("out"))
    pages = {p.relative_to(html).as_posix(): p.read_text() for p in html.rglob("*.html")}
    pages.update({p.relative_to(html).as_posix(): p.read_text() for p in html.rglob("*.css")})
    pages["__fonts__"] = " ".join(sorted(p.name for p in (html / "_static").rglob("*.ttf")))
    pages["__licenses__"] = " ".join(sorted(p.name for p in (html / "_static").rglob("OFL*")))
    return pages


def _flow_page(site: dict[str, str]) -> str:
    return next(text for name, text in site.items() if name.startswith("flow-"))


def test_the_default_theme_is_bundled_and_self_contained(site: dict[str, str]) -> None:
    """THE FONTS SHIP WITH THEIR LICENCES and load same-origin; nothing on any page is remote.

    @brief W13: the clew theme's stylesheet, tokens and fonts.
    """
    css = site["_static/clew.css"]
    assert "--paper:" in css and "--acc:" in css
    assert "@font-face" in site["_static/fonts/clew-fonts.css"]
    assert {"manrope.ttf", "newsreader.ttf", "jetbrains-mono.ttf"} <= set(site["__fonts__"].split())
    assert "OFL" in site["__licenses__"]
    for name, text in site.items():
        if name.endswith(".html"):
            assert "fonts.googleapis" not in text and "https://cdn" not in text, name
            assert "_static/clew.css" in text, name


def test_the_repository_overrides_palette_and_adds_css(site: dict[str, str]) -> None:
    """@brief W13: `wiki.theme.palette` and `wiki.theme.css` reach every page."""
    assert "--acc:#123456" in site["_static/clew-theme.css"]
    assert ".repo-extra" in site["_static/extra.css"]
    assert (
        "_static/clew-theme.css" in site["index.html"] and "_static/extra.css" in site["index.html"]
    )


def test_another_installed_theme_can_be_named(tmp_path: Path) -> None:
    """@brief W13: `theme.name` selects a Sphinx theme; the clew stylesheet is then not imposed."""
    from clew.wiki.config import ThemeSpec
    from clew.wiki.theme import sphinx_settings

    settings = sphinx_settings(ThemeSpec(name="alabaster"), tmp_path, tmp_path)
    assert settings["html_theme"] == "alabaster" and "html_theme_path" not in settings


def test_check_refuses_an_unknown_palette_token(repo: tuple[Path, Path], tmp_path: Path) -> None:
    """@brief A misspelled token would otherwise be a silent no-op."""
    from clew.wiki.check import check_wiki

    cfg = tmp_path / "w.yaml"
    cfg.write_text(
        "wiki:\n  docs: [README.md]\n  theme:\n    palette: {acent: '#000'}\n    css: nope.css\n"
    )
    problems = "\n".join(check_wiki(repo[0], repo[1], cfg))
    assert "'acent'" in problems and "'nope.css' does not exist" in problems


def test_requirement_and_test_charts_are_drawn(site: dict[str, str]) -> None:
    """@brief W14: donuts of requirement tiers and test statuses, with their counts."""
    page = site["requirements.html"]
    assert page.count('class="donut"') == 2
    assert 'data-label="PASS" data-count="1"' in page and 'data-label="GAP" data-count="1"' in page
    assert 'data-label="MISSING" data-count="1"' in page
    assert (
        'data-label="passed" data-count="1"' in page
        and 'data-label="failed" data-count="1"' in page
    )


def test_the_summary_page_counts_each_requirement_group(site: dict[str, str]) -> None:
    """A REQUIREMENT TESTED IN FEWER LAYERS THAN `min_layers` is counted, so one-layer coverage is
    visible rather than reading as tested.

    @brief W14: per group — requirements, implemented, tested, tiers, below the layer minimum.
    """
    page = site["summary.html"]
    assert 'class="donut"' in page

    def cells(group: str) -> list[str]:
        return re.findall(r"<td[^>]*>([^<]*)</td>", page.split(group, 1)[1].split("</tr>")[0])

    # requirements, implemented, tested, PASS, GAP, TARGET, NOT_RUN, MISSING, below min layers
    assert cells("REQ-W")[:9] == ["2", "2", "2", "1", "1", "0", "0", "0", "2"]
    assert cells("REQ-X")[:9] == ["1", "1", "0", "0", "0", "0", "0", "1", "0"]


def test_a_step_links_to_its_call_site_not_the_callee_file(repo: tuple[Path, Path]) -> None:
    """THE LINE IS THE CALL SITE'S, so the file must be the caller's: `finish` is defined in
    src/out.py but called at a line of src/data.py.

    @brief Flow steps carry the call site's file.
    """
    from clew.wiki.flow import derive_flow

    flow = derive_flow(repo[1], repo[0], "load", depth=2)
    step = next(s for s in flow.steps if s.callee == "finish")
    assert step.file == "src/out.py" and step.site_file == "src/data.py"
    assert (repo[0] / "src/data.py").read_text().splitlines()[
        step.line - 1
    ].strip() == "return finish()"


def test_the_sequence_diagram_is_uml_proper(site: dict[str, str]) -> None:
    """@brief W18: activation bars, a return arrow for the cross-lane call, a drawn loop frame,
    numbered steps, and lane heads at top and bottom."""
    page = _flow_page(site)
    svg = page[page.index("<svg") : page.index("</svg>")]
    assert 'class="act"' in svg and 'class="ret"' in svg
    assert 'class="frame"' in svg and ">loop<" in svg
    assert re.findall(r'class="num"[^>]*>(\d+)<', svg) == ["1", "2"]
    assert ">parse<" in svg and ">finish<" in svg
    assert svg.count('class="head"') == 2 * svg.count('class="lane"')


def test_a_step_opens_a_dialog_with_the_data_it_carries(site: dict[str, str]) -> None:
    """@brief W18: per-step data (call text, callee signature, call-site link) and controls."""
    page = _flow_page(site)
    assert "<dialog" in page and 'data-flow-control="play"' in page
    assert 'data-flow-control="pause"' in page and 'data-flow-control="step"' in page
    blob = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', page, re.S)
    steps = json.loads(
        blob.group(1).replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&")
    )
    parse = next(s for s in steps if s["callee"] == "parse")
    assert 'parse(item, "SECRET_CALL_ARG")' in parse["call"]
    assert "raw, tag" in parse["signature"]
    assert parse["site"].startswith("src/data.py:") and "example.invalid" in parse["link"]


def test_a_partner_site_carries_no_call_text(repo: tuple[Path, Path], tmp_path: Path) -> None:
    """REDACTION ON THE OUTPUT: the dialog data is source text too.

    @brief W18 under `exclude_bodies`.
    """
    from clew.wiki.build import build_wiki

    html = build_wiki(repo[0], repo[1], tmp_path / "partner", audience="partner")
    for page in html.rglob("*.html"):
        text = page.read_text()
        assert "SECRET_CALL_ARG" not in text and "SECRET_BODY_MARKER" not in text, page


def test_versions_burn_down_toward_roadmap_milestones(
    repo: tuple[Path, Path], tmp_path: Path
) -> None:
    """A ROADMAP HEADING NAMING A VERSION is a milestone; one not yet recorded is drawn ahead.

    @brief W17: open requirements per recorded version, milestones from ROADMAP.md.
    """
    from clew.wiki.build import build_wiki

    out = tmp_path / "versions"
    build_wiki(repo[0], repo[1], out, version="v1.0")
    build_wiki(repo[0], repo[1], out, version="v1.5")
    index = (out / "index.html").read_text()
    chart = index[index.index('<svg class="burndown"') :]
    chart = chart[: chart.index("</svg>")]
    assert chart.count('class="pt"') == 2
    assert ">v1.0<" in chart and ">v1.5<" in chart and ">v2.0<" in chart
    assert 'class="milestone"' in chart
    summary = (out / "v1.5" / "html" / "summary.html").read_text()
    assert 'class="burndown"' in summary


def test_only_a_heading_that_leads_with_a_version_is_a_milestone(tmp_path: Path) -> None:
    """A VERSION MENTIONED IN PASSING is not a milestone: "Adopting design_master v1.0.28" names
    another project's release.

    @brief Roadmap milestone detection.
    """
    from clew.wiki.charts import roadmap_milestones

    road = tmp_path / "ROADMAP.md"
    road.write_text(
        "# Roadmap to v0.8.0\n## A. Tooling\n### Adopting design_master v1.0.28, in order\n"
        "## Proposed v0.8.0 cut\n## v0.9 — later\n## Milestone 1.0.0\n"
    )
    assert [v for v, _h in roadmap_milestones(road)] == ["v0.8.0", "v0.9", "1.0.0"]
