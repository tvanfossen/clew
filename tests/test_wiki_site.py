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

Round 3, P1b — the UI SHELL: one modal component on every page (native `<dialog>`, deep-linked
by URL hash, the back button closes it), the flow-step dialog served by it rather than its own;
one budgeted `clew.js` and nothing remote in any theme asset; a top bar ordered Requirements ·
Flows · Change impact · Map · Docs · Model entries that collapses to a menu on a phone; tables
that become cards on a narrow screen; diagrams that pan and zoom; an inline SVG icon set.

@brief Tests for the wiki theme, charts, summary, burndown, sequence diagram and UI shell.
@version 2
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

_CLI = '''\
from src.data import load


def main():
    """The command line."""
    return load([])
'''

_OTHER_MAIN = '''\
def main():
    """Another program's main."""
    return other()


def other():
    """Not the CLI's callee."""
    return 2
'''

_PYPROJECT = """\
[project]
name = "demo"
version = "0"

[project.scripts]
demo = "src.cli:main"
"""

_ROADMAP = """\
# Roadmap

## v1.0 — first cut
Some text.

## v2.0 — the rest
"""

## Round 3, P3c-2: an architecture decision record naming a requirement.
_ADR = """\
# 1. Use SQLite for the store

Date: 2026-01-02

## Status

Accepted

## Context

REQ-W-001 needs a file-backed store.
"""

## Round 3, P1d: a catalog, so a requirement has acceptance text for its modal.
_CATALOG = """\
requirements:
  REQ-W-001:
    name: Load the data
    acceptance_criteria: Every item is parsed once, then the load finishes.
    ## FIXTURE EXTENDED (2.0.0, S4): two IEEE 29148 attributes, for the traceability checklist.
    rationale: A load that parses twice doubles startup.
    verification: test
"""

## FIXTURE CHANGED (2.0.0, R5-CFG F20): the test evidence is the top-level `tests:` section.
_WIKI = """\
tests:
  junit: [junit.xml]
  features: ["tests/features/*.feature"]
  layers: {unit: ["tests/test_*"], bdd: ["tests/features/*"]}
  min_layers: 2

wiki:
  title: Site Demo
  docs: [README.md]
  roadmap: ROADMAP.md
  flows:
    - entry: load
      depth: 2
      ## FIXTURE CHANGED (2.0.0, P5.6): block lanes became the default (owner, round 5), and
      ## src/data.py and src/out.py share one block, so this flow would draw ONE lane. The tests
      ## here guard UML properness on a CROSS-LANE call, unchanged, so the flow states `files`.
      lanes: files
  links:
    template: "https://example.invalid/blob/{commit}/{file}#L{line}"
  theme:
    palette: {accent: "#123456"}  # 2.0.0 token name; it still sets --acc
    css: docs/extra.css
  audiences:
    partner: {exclude_bodies: true}
    public: {exclude_requirement_text: true}
  issues: {github: acme/demo}
  doc_kinds: {README.md: tutorial}
  check: {ears: true}  # FIXTURE EXTENDED (2.0.0, S9): the EARS badge on requirement pages
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
        "src/cli.py": _CLI,
        "tools/other.py": _OTHER_MAIN,
        "pyproject.toml": _PYPROJECT,
        "tests/test_data.py": _TEST,
        "tests/features/finish.feature": _FEATURE,
        "junit.xml": _JUNIT,
        "README.md": "# Demo\n\nThe demo repository.\n",
        "ROADMAP.md": _ROADMAP,
        "requirements.yaml": _CATALOG,
        "docs/adr/0001-use-sqlite.md": _ADR,
        "AGENTS.md": "# Agents\n\nHow an agent works in this repository.\n",
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
    pages["_static/clew.js"] = (html / "_static" / "clew.js").read_text()
    pages["__html__"] = str(html)
    pages["__fonts__"] = " ".join(sorted(p.name for p in (html / "_static").rglob("*.ttf")))
    pages["__licenses__"] = " ".join(sorted(p.name for p in (html / "_static").rglob("OFL*")))
    return pages


def _flow_page(site: dict[str, str]) -> str:
    return site["flow-load.html"]


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
    # REQ-X-001 has no tagged test; test_load reaches `parse` in one call, so it is INFERRED.
    assert 'data-label="PASS" data-count="2"' in page and 'data-label="GAP" data-count="1"' in page
    assert (
        'data-label="passed" data-count="1"' in page
        and 'data-label="failed" data-count="1"' in page
    )


def test_the_requirements_page_summarises_each_requirement_group(site: dict[str, str]) -> None:
    """ONE PAGE FOR THE TRACE (owner 2026-11-15: requirements and summary filled the same role):
    the group counts sit above the per-requirement table. A requirement tested in fewer layers than
    `min_layers` is counted, so one-layer coverage is visible rather than reading as tested.

    @brief W14: per group — requirements, implemented, tested, tiers, below the layer minimum.
    """
    page = site["requirements.html"]
    assert "summary.html" not in site

    def cells(group: str) -> list[str]:
        row = page.split(f"<td>{group}</td>", 1)[1].split("</tr>")[0]
        return re.findall(r"<td[^>]*>([^<]*)</td>", row)

    # requirements, implemented, tested, PASS, GAP, TARGET, NOT_RUN, MISSING, EXEMPT, below min
    # layers. EXEMPT column added in round 4 (R8); the counts asserted are unchanged.
    # REQ-W-002 spans two layers once test_load is inferred for `finish` (bdd + unit).
    assert cells("REQ-W")[:10] == ["2", "2", "2", "1", "1", "0", "0", "0", "0", "1"]
    assert cells("REQ-X")[:10] == ["1", "1", "1", "1", "0", "0", "0", "0", "0", "1"]
    assert "only by call-graph inference" in page
    # Round 3, P1d: the group CARDS now lead the page and the counts table sits below the list;
    # the property — group counts come before the per-requirement rows — is held by the cards.
    assert page.index('data-req-filter="REQ-W"') < page.index("REQ-W-001")


def test_the_requirement_table_links_implementers_and_drops_empty_columns(
    site: dict[str, str],
) -> None:
    """EMPTY LINKAGE IS NOT A COLUMN: a column no requirement fills (nodes, mutations here) is not
    drawn. Each implementer links to its source, and a test linked by inference says so.

    @brief The per-requirement table.
    """
    page = site["requirements.html"]
    table = page[page.index('<table class="clew trace"') :]
    table = table[: table.index("</table>")]
    head = re.findall(r"<th>([^<]*)</th>", table)
    assert head[:3] == ["requirement", "tier", "implemented by"]
    assert "nodes" not in head and "mutations" not in head
    row = table.split("REQ-W-001", 1)[1].split("</tr>")[0]
    # Round 3, P1f (owner ruling: source links become DOSSIER REFERENCES): an implementer links
    # to its symbol section, and that section links the source permalink.
    assert 'href="sym-src-data-py.html#s-load"' in row
    assert re.search(
        r'href="https://example\.invalid/blob/[^/]+/src/data\.py#L\d+"',
        site["sym-src-data-py.html"],
    )
    inferred = table.split("REQ-X-001", 1)[1].split("</tr>")[0]
    assert "via-inferred" in inferred and "test_load" in inferred


def test_the_top_bar_holds_sections_and_search(site: dict[str, str]) -> None:
    """THE TOP BAR NAMES SECTIONS, not every page: flows sit under one Flows page and prose under
    Docs. Search is a field in the top bar; the sidebar carries the page's contents only.

    @brief Navigation and search placement.
    """
    index = site["index.html"]
    # Locator loosened (round 3, P1b): the nav now carries an id for its menu button.
    nav = index[index.index('<nav class="nav"') : index.index("</nav>")]
    for section in ("Docs", "Flows", "Requirements"):
        assert f">{section}<" in nav, section
    assert "load" not in nav and "Demo" not in nav
    for name, text in site.items():
        if name.endswith(".html") and name not in ("search.html", "genindex.html"):
            assert '<form class="search"' in text and 'id="searchbox"' not in text, name
    assert "flow-load" in site["flows.html"] and "prose/README" in site["docs.html"]


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
    # Locator narrowed (round 3, P1b): the top bar's menu icon is now the page's first <svg>.
    start = page.index('<svg class="seq"')
    svg = page[start : page.index("</svg>", start)]
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
    trace = (out / "v1.5" / "html" / "requirements.html").read_text()
    assert 'class="burndown"' in trace


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


def test_an_empty_cell_reads_as_a_dash_and_an_empty_column_is_dropped() -> None:
    """@brief The shared table helper."""
    from clew.wiki.htmltable import table

    html = table(["a", "b", "c"], [["x", "", ""], ["", "y", ""]], numeric=("b",))
    assert re.findall(r"<th[^>]*>(\w)</th>", html) == ["a", "b"]
    # Fixture string loosened (round 3, P1b): a cell now also carries its column's `data-label`
    # for the narrow-screen card layout; the property asserted — right-aligned numeric — is unchanged.
    assert html.count('class="none"') == 2 and re.search(r'<td class="n"[^>]*>y</td>', html)


def test_entry_points_become_flows_without_being_declared(site: dict[str, str]) -> None:
    """ENTIRELY GENERATED (owner 2026-11-15: two flows for clew was not comprehensive): every
    entry point the repository has — a console script, a `main` outside test code, a thread's
    entry — gets a flow; declared flows (roots chosen in `.clew.yaml`) are added on top.

    @brief Auto-derived entry-point flows.
    """
    flows = site["flows.html"]
    assert "flow-load" in flows
    cli = next(t for n, t in site.items() if n.startswith("flow-main-src-cli"))
    other = next(t for n, t in site.items() if n.startswith("flow-main-tools-other"))
    assert ">load<" in cli and ">other<" not in cli
    assert ">other<" in other and ">load<" not in other
    assert "demo" in cli  # the console script's name titles its flow


def test_a_flow_entry_is_selected_by_file(repo: tuple[Path, Path]) -> None:
    """TWO `main`s SHARE A NAME AND A DEFINITION: selecting by name alone merged their calls.

    @brief derive_flow(file=...) walks only that file's identity.
    """
    from clew.wiki.flow import derive_flow

    flow = derive_flow(repo[1], repo[0], "main", file="tools/other.py", depth=1)
    assert [s.callee for s in flow.steps] == ["other"]


def test_a_flow_entry_by_file_survives_distinct_identities(
    repo: tuple[Path, Path], tmp_path: Path
) -> None:
    """FOUND IN CI (doxygen 1.9.8; 1.18 locally): the two `main`s can carry DIFFERENT definitions,
    so they are two identities — and `identity_rowids` picked one by its default guess BEFORE the
    file filter, leaving nothing for the other file. 51 wiki tests failed in CI and none locally.
    The file now chooses the identity. Simulated here by giving the rows distinct definitions.

    @brief derive_flow(file=...) finds each file's main whichever identity sorts first.
    """
    import shutil
    import sqlite3

    from clew.wiki.flow import derive_flow

    db = tmp_path / "split.db"
    shutil.copy(repo[1], db)
    conn = sqlite3.connect(db)
    conn.execute(
        "UPDATE memberdef SET definition = 'def ' || ? || '.main' WHERE name = 'main' AND "
        "file_id IN (SELECT rowid FROM path WHERE name LIKE ?)",
        ("tools.other", "%tools/other.py"),
    )
    conn.commit()
    conn.close()
    for file in ("src/cli.py", "tools/other.py"):
        flow = derive_flow(db, repo[0], "main", file=file, depth=1)
        assert flow.steps, file


## The most bytes clew.js may carry: one script for every page, read before anything renders.
_JS_BUDGET = 8192
## P5.6 (owner Q/A 2026-11-20): the second script, loaded only where a quick view exists.
_VIEWS_JS_BUDGET = 8192


def test_one_modal_component_serves_every_page(site: dict[str, str]) -> None:
    """ONE COMPONENT: every content page carries the same labelled `<dialog>` and the script that
    drives it; the flow page's step dialog is that component, not a second one.

    @brief P1b: the shared modal.
    """
    for name, text in site.items():
        if name.endswith(".html") and name not in ("search.html", "genindex.html"):
            assert '<dialog id="clew-modal"' in text, name
            assert 'aria-labelledby="clew-modal-title"' in text, name
            assert "_static/clew.js" in text, name
    page = _flow_page(site)
    assert "dialog.flow-step" not in page and '<dialog class="flow-step"' not in page
    assert page.count("<dialog") == 1


def test_a_modal_trigger_carries_its_content_inert_and_escaped() -> None:
    """REPOSITORY TEXT NEVER BECOMES MARKUP: a trigger names a `<template>` whose content was
    escaped by Python; the script clones it, it does not parse strings.

    @brief P1b: modal triggers and templates.
    """
    from clew.wiki.modal import modal

    html = modal("req-R-1", "R-1", "R-1 <b>", "<p>body</p>")
    assert 'data-modal="req-R-1"' in html and '<template id="modal-req-R-1"' in html
    assert 'data-title="R-1 &lt;b&gt;"' in html and "<p>body</p>" in html
    with pytest.raises(ValueError):
        modal("bad key", "x", "x", "")


def test_the_script_is_budgeted_and_no_theme_asset_is_remote() -> None:
    """SELF-CONTAINED: no theme stylesheet, layout or script names an http(s) URL, and the one
    script stays under its byte budget. Deep links and the back button are the script's job:
    it reads the `#m=` hash and closes on `popstate`.

    @brief P1b: clew.js budget, nothing remote.
    """
    from clew.wiki.theme import THEMES

    js = THEMES / "clew" / "static" / "clew.js"
    assert js.stat().st_size <= _JS_BUDGET
    for path in THEMES.rglob("*"):
        if path.suffix in (".css", ".js", ".html"):
            text = path.read_text(encoding="utf-8")
            assert "http://" not in text and "https://" not in text, path
    source = js.read_text(encoding="utf-8")
    assert "#m=" in source and "popstate" in source


def test_the_top_bar_is_ordered_and_collapses_to_a_menu(site: dict[str, str]) -> None:
    """OWNER 2026-11-15: requirements front and centre. The sections run Requirements · Flows ·
    (Change impact · Map) · Docs · Model entries; on a phone a labelled button opens them.

    @brief P1b: section order and the mobile menu.
    """
    index = site["index.html"]
    nav = index[index.index('<nav class="nav"') : index.index("</nav>")]
    positions = [nav.index(f">{s}<") for s in ("Requirements", "Flows", "Docs")]
    assert positions == sorted(positions)
    assert 'class="menu-toggle"' in index and 'aria-controls="clew-nav"' in index
    assert 'aria-expanded="false"' in index and 'id="clew-nav"' in nav


def test_tables_become_cards_and_diagrams_pan_on_a_narrow_screen(site: dict[str, str]) -> None:
    """@brief P1b: responsive tables (a cell names its column) and pan/zoom diagram wrappers."""
    from clew.wiki.htmltable import table

    html = table(["Name", "Count"], [["a", "1"]], numeric=("Count",))
    assert 'data-label="Name"' in html and 'data-label="Count"' in html
    css = site["_static/clew.css"]
    assert "@media(max-width:760px)" in css and "attr(data-label)" in css
    assert "data-pz" in _flow_page(site)


def test_section_cards_carry_an_icon() -> None:
    """@brief P1b: the inline icon set — currentColor, hidden from assistive tech; unknown names
    refuse."""
    from clew.wiki.icons import icon

    svg = icon("requirements")
    assert svg.startswith("<svg") and 'aria-hidden="true"' in svg and "currentColor" in svg
    with pytest.raises(KeyError):
        icon("nope")


def test_a_step_brief_is_plain_text_and_the_home_card_counts_every_flow(
    site: dict[str, str],
) -> None:
    """FOUND ON THE ROUND-3 SCREENSHOTS: the step modal printed doxygen's `<para>…</para>` around
    the brief, and the Flows card counted only declared flows ("2" on a site with 30).

    @brief Brief markup and the flow count.
    """
    blob = re.search(r'<script type="application/json"[^>]*>(.*?)</script>', _flow_page(site), re.S)
    steps = json.loads(blob.group(1))
    assert any(s["brief"] for s in steps)
    assert all("<" not in s["brief"] and "para>" not in s["brief"] for s in steps)
    count = sum(1 for n in site if n.startswith("flow-") and n.endswith(".html"))
    assert f"{count} sequence diagrams" in site["index.html"]


def test_the_map_is_a_section_between_flows_and_docs(site: dict[str, str]) -> None:
    """@brief P1c: the system map page, in the top bar after Flows, with its lens controls."""
    index = site["index.html"]
    nav = index[index.index('<nav class="nav"') : index.index("</nav>")]
    positions = [nav.index(f">{s}<") for s in ("Requirements", "Flows", "Map", "Docs")]
    assert positions == sorted(positions)
    page = site["map.html"]
    ## ROUND 4, R3: the map page is the repository web (canvas, lens picker, block table) — the
    ## box map's `comp` groups and lens buttons were replaced by owner ruling 2026-11-16.
    assert 'class="web"' in page and "data-web-lens" in page and 'class="clew web-table"' in page


def test_every_page_carries_the_minimap_with_its_components_lit(site: dict[str, str]) -> None:
    """CROSS-TALK (owner 2026-11-15): the sidebar holds the system's block diagram on every page;
    a flow page lights the components its steps pass through, and each box opens that
    component on the map.

    @brief P1c-2: the sidebar minimap.
    """
    ## ROUND 4, R2 (owner 2026-11-16: the unlabelled sidebar boxes were "easier to simply click
    ## into map"): the sidebar is now a LABELLED block list, in the web's order, each block a link
    ## to that block on the web. The property — every page carries it, a flow lights its blocks —
    ## is unchanged.
    for name in ("index.html", "requirements.html", "flow-load.html"):
        assert '<nav class="minimap"' in site[name], name
    flow = site["flow-load.html"]
    lit = re.findall(r'\.minimap \[data-comp="([^"]+)"\]', flow)
    assert lit == ["src"]
    assert re.search(r'href="map\.html#b=\d+"[^>]*data-comp="src"', flow)
    assert re.search(r'data-comp="src"[^>]*>.*?<span class="mm-name">src</span>', flow, re.S)
    assert not re.findall(r'\.minimap \[data-comp="([^"]+)"\]', site["requirements.html"])


def _template(page: str, key: str) -> str:
    """The body of one modal template."""
    found = re.search(rf'<template id="modal-{re.escape(key)}"[^>]*>(.*?)</template>', page, re.S)
    assert found is not None, key
    return found.group(1)


def test_requirement_groups_are_cards_that_filter_the_list(site: dict[str, str]) -> None:
    """OWNER 2026-11-15: requirements front and centre, groups linked. Each group is a card with
    its tier progress; the card filters the requirement list to that group.

    @brief P1d: group cards.
    """
    page = site["requirements.html"]
    cards = re.findall(r'<button[^>]*class="group-card"[^>]*data-req-filter="([^"]+)"', page)
    assert cards == ["REQ-W", "REQ-X"]
    assert page.index('class="group-card"') < page.index('<table class="clew trace"')
    assert re.findall(r'<tr data-group="([^"]+)"', page) == ["REQ-W", "REQ-W", "REQ-X"]
    w = page[page.index('data-req-filter="REQ-W"') :]
    assert 'class="seg c-PASS"' in w[: w.index("</button>")]


def test_each_requirement_group_has_its_own_page(site: dict[str, str]) -> None:
    """OWNER (round 5, P5.4): requirement groups get pages, and the group cards link to them. A
    group page is a URL a reader can share: its tier bar, its counts, and ONLY its own
    requirements, each linking to the requirement's page.

    @brief P5.4: one page per requirement group.
    """
    w, x = site["reqgroup-REQ-W.html"], site["reqgroup-REQ-X.html"]
    assert "REQ-W-001" in w and "REQ-W-002" in w and "REQ-X-001" not in w
    assert "REQ-X-001" in x and "REQ-W-001" not in x
    assert 'href="req-REQ-W-001.html"' in w
    assert 'class="seg c-PASS"' in w and "2 requirements" in w
    assert 'href="requirements.html"' in w, "a group page leads back to the index"


def test_a_group_card_links_to_its_group_page(site: dict[str, str]) -> None:
    """@brief P5.4: each card keeps its filter and gains a link to the group's page."""
    page = site["requirements.html"]
    assert re.findall(r'<a class="g-page" href="reqgroup-([^"]+)\.html"', page) == [
        "REQ-W",
        "REQ-X",
    ]


def test_a_requirement_has_its_own_page_with_its_whole_trace(site: dict[str, str]) -> None:
    """THE ACCEPTANCE TEXT LEAVES THE TABLE (owner: the drop-down was noise) and lives on the
    requirement's OWN PAGE with everything else that requirement links to: implementers, tests
    with their link kind and extent, the flows passing through its implementers, and a prefilled
    issue link that carries the id three ways — in the title, as a `req:` label, and as a marker
    line. ROUND 4, R4 (owner 2026-11-16: "Dont show things by one giant scrolling page, but
    individual links that are self contained"): a page per requirement replaces the modal.

    @brief R4: the requirement page and its issue link.
    """
    from html import unescape
    from urllib.parse import parse_qs, urlsplit

    page = site["requirements.html"]
    assert "<summary>acceptance</summary>" not in page
    assert 'href="req-REQ-W-001.html"' in page
    assert '<template id="modal-req-' not in page
    body = site["req-REQ-W-001.html"]
    assert "Every item is parsed once" in body
    assert "src/data.py" in body and "test_load" in body
    assert 'href="flow-load.html"' in body
    tests = body[body.index('class="clew req-tests') :]
    assert "test_load" in tests and "of 1" in tests
    href = unescape(
        re.search(r'href="(https://github\.com/acme/demo/issues/new\?[^"]+)"', body).group(1)
    )
    query = parse_qs(urlsplit(href).query)
    assert "REQ-W-001" in query["title"][0] and query["labels"] == ["req:REQ-W-001"]
    assert "clew-req: REQ-W-001" in query["body"][0]


def test_a_public_site_keeps_requirement_text_off_the_requirement_page(
    repo: tuple[Path, Path], tmp_path: Path
) -> None:
    """@brief R4: `exclude_requirement_text` reaches the requirement page and the issue link."""
    from clew.wiki.build import build_wiki

    html = build_wiki(repo[0], repo[1], tmp_path / "out", audience="public")
    page = (html / "requirements.html").read_text() + (html / "req-REQ-W-001.html").read_text()
    assert "Every item is parsed once" not in page and "Load the data" not in page
    assert 'href="req-REQ-W-001.html"' in page


def test_issue_links_follow_the_declared_or_remote_tracker() -> None:
    """GITHUB AND AZURE DEVOPS, prefilled; the tracker is declared (`wiki.issues`) or read from
    the `origin` remote; an unknown host gives no link rather than a guessed one.

    @brief P1d: issue targets and prefilled URLs.
    """
    from urllib.parse import parse_qs, urlsplit

    from clew.wiki.issues import issue_url, target_from_remote

    assert target_from_remote("git@github.com:acme/demo.git") == ("github", "acme/demo")
    assert target_from_remote("https://github.com/acme/demo") == ("github", "acme/demo")
    assert target_from_remote("https://dev.azure.com/org/proj/_git/repo") == ("ado", "org/proj")
    assert target_from_remote("git@ssh.dev.azure.com:v3/org/proj/repo") == ("ado", "org/proj")
    assert target_from_remote("https://gitlab.example/x/y.git") is None
    url = issue_url(("ado", "org/proj"), "REQ-1", "Title", "Body")
    parts = urlsplit(url)
    assert parts.netloc == "dev.azure.com" and parts.path == "/org/proj/_workitems/create/Issue"
    query = parse_qs(parts.query)
    assert query["[System.Tags]"] == ["req:REQ-1"] and "REQ-1" in query["[System.Title]"][0]


def test_flows_are_grouped_by_role(site: dict[str, str]) -> None:
    """OWNER 2026-11-15: "a bunch of scripts, not much by way of core function". The Flows page
    groups flows by role — PRODUCT (console scripts, declared roots, mains outside tooling),
    THREADS (thread entries; absent here, so no section), TOOLING (scripts/, acceptance/, tools/
    by default) folded away.

    @brief P1e: flows by role.
    """
    page = site["flows.html"]

    def role(name: str) -> str:
        found = re.search(
            rf'<section class="flow-role" data-role="{name}">(.*?)</section>', page, re.S
        )
        assert found is not None, name
        return found.group(1)

    product, tooling = role("product"), role("tooling")
    assert "flow-load.html" in product and "flow-main-src-cli-py.html" in product
    assert "flow-main-tools-other-py.html" in tooling and "<details" in tooling
    assert "flow-main-tools-other-py.html" not in product
    assert 'data-role="threads"' not in page
    assert page.index('data-role="product"') < page.index('data-role="tooling"')


def test_a_flow_step_carries_the_requirements_its_callee_implements(site: dict[str, str]) -> None:
    """@brief P1e: requirement badges on steps, linked to the requirement's row."""
    page = _flow_page(site)
    table = page[page.index('<table class="clew steps"') :]
    table = table[: table.index("</table>")]
    assert 'href="requirements.html#REQ-X-001"' in table
    assert 'href="requirements.html#REQ-W-002"' in table


def test_docs_are_grouped_by_kind_and_agent_docs_are_included(site: dict[str, str]) -> None:
    """DIÁTAXIS, AND HUMAN VS AGENT DOCS (owner 2026-11-15): the Docs page groups the repository's
    prose by declared kind; AGENTS.md is included without being listed and kept apart, as
    agent-facing.

    @brief P3c-2: doc kinds.
    """
    page = site["docs.html"]

    def kind(name: str) -> str:
        found = re.search(
            rf'<section class="doc-kind" data-kind="{name}">(.*?)</section>', page, re.S
        )
        assert found is not None, name
        return found.group(1)

    assert "prose/README" in kind("tutorial") and "prose/AGENTS" in kind("agents")
    assert page.index('data-kind="tutorial"') < page.index('data-kind="agents"')
    assert "prose/AGENTS.html" in site


def test_decisions_are_listed_and_reach_the_requirements_they_name(site: dict[str, str]) -> None:
    """@brief P3c-2: ADRs — a Decisions page (number, title, status, date, requirements named) and
    a Decisions section on each named requirement's page."""
    page = site["decisions.html"]
    table = page[page.index('<table class="clew"') :]
    row = table[table.index("Use SQLite for the store") :].split("</tr>")[0]
    assert "Accepted" in row and "2026-01-02" in row and 'href="requirements.html#REQ-W-001"' in row
    assert "adr/0001-use-sqlite" in page
    ## Round 4, R4: the requirement's own page holds what its modal did.
    body = site["req-REQ-W-001.html"]
    assert "<h4>Decisions</h4>" in body and "Use SQLite for the store" in body


def test_adr_status_is_read_in_every_common_shape() -> None:
    """@brief P3c-2: `Status:` inline, a `## Status` section, MADR front matter."""
    from clew.wiki.adr import parse_adr

    inline = parse_adr("0002-x.md", "# 2. X\n\nStatus: Proposed\nDate: 2026-02-01\n")
    section = parse_adr("0003-y.md", "# Y\n\n## Status\n\nSuperseded by 4\n")
    madr = parse_adr("0004-z.md", "---\nstatus: accepted\ndate: 2026-03-03\n---\n# Z\n")
    assert (inline.number, inline.title, inline.status, inline.date) == (
        "2",
        "X",
        "Proposed",
        "2026-02-01",
    )
    assert (section.number, section.status) == ("3", "Superseded by 4")
    assert (madr.title, madr.status, madr.date) == ("Z", "accepted", "2026-03-03")


def test_an_unknown_doc_kind_is_a_problem(tmp_path: Path) -> None:
    """@brief P3c-2: doc kinds are a closed set."""
    from clew.wiki.config import load_wiki_config

    (tmp_path / ".clew.yaml").write_text("wiki:\n  doc_kinds: {README.md: novel}\n")
    assert load_wiki_config(tmp_path)[1]


def test_a_test_has_its_own_page_saying_what_it_checks_and_reaches(site: dict[str, str]) -> None:
    """OWNER 2026-11-16: tests did not link through from requirements, and "at minimum, I want to
    see visually what a test is PROVING". A requirement's test links to the test's OWN page: the
    packaged run's result, its checks, and a drawn chain from the test through its calls to each
    implementer it reaches — labelled as reaching, not proving, without mutation records.

    @brief R6/R7: the test page.
    """
    req = site["req-REQ-W-001.html"]
    assert 'href="test-tests-test_data-py-test_load.html"' in req
    page = site["test-tests-test_data-py-test_load.html"]
    assert "Passed in the packaged run." in page
    assert "assert load([]) == 1" in page
    proof = page[page.index('<svg class="proof') :]
    proof = proof[: proof.index("</svg>")]
    assert ">test_load" in proof and ">load<" in proof and "REQ-W-001" in proof
    assert "Reaching is not proving" in page
    ## OWNER 2026-11-17 (round 5): "a test itself doesn't need a sequence diagram" — without a
    ## packaged run a test has no flow of its own (its slices of the master flows need per-test
    ## coverage, which this fixture does not give; tests/test_wiki_testslices.py covers them).
    assert "flow-test_load" not in page and "replay" not in page


def test_a_discovered_flow_that_cannot_be_drawn_is_listed_not_fatal(
    repo: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FOUND BUILDING ENTROPIC AND SASSAFRAS-CLASS (round 4): one entry point the build discovered
    on its own — a thread entry recorded at its header declaration, a `main` in vendored code —
    could not be derived, and the whole site failed. A DISCOVERED flow that cannot be drawn is
    listed on the Flows page with the reason; a DECLARED one still fails the build, since it is
    the repository's own statement and a typo must not pass silently.

    @brief Undrawable discovered flows are reported, not fatal.
    """
    from clew.wiki import entrypoints
    from clew.wiki.build import build_wiki
    from clew.wiki.config import FlowSpec

    real = entrypoints.entry_point_flows

    def with_a_ghost(db, root, depth):  # noqa: ANN001, ANN202
        return [*real(db, root, depth), FlowSpec(entry="ghost", file="vendor/x.c", depth=depth)]

    monkeypatch.setattr(entrypoints, "entry_point_flows", with_a_ghost)
    html = build_wiki(repo[0], repo[1], tmp_path / "out")
    flows = (html / "flows.html").read_text()
    assert "ghost" in flows and "vendor/x.c" in flows and "not drawn" in flows


def test_a_long_test_list_says_how_many_are_direct() -> None:
    """ROUND 4: with transitive inference a broad requirement lists hundreds of tests; the index
    says how many are aimed at it directly and how many only reach it through calls.

    @brief The requirement index's test summary splits direct from reached.
    """
    from types import SimpleNamespace

    from clew.wiki.tracepages import _tests_cell

    row = SimpleNamespace(
        tests=tuple((f"t{i}", "passed") for i in range(6)), inferred_tests=("t3", "t4", "t5")
    )
    cell = _tests_cell(row, {})
    assert "3 direct · 3 reached through calls" in cell and "6 tests: 6 passed" in cell


def test_the_traceability_checklist_states_each_requirements_evidence(site: dict[str, str]) -> None:
    """S4 (owner-approved, 2026-11-17): an IEEE 29148 traceability checklist — per requirement,
    which attributes it carries (rationale, verification method, parent) and whether it is
    implemented, tested and passing. Worded as SUPPORTING EVIDENCE, never as compliance: the page
    measures what a catalogue and an index show, and a standard's conformance is an assessor's call.

    @brief P5.4 / S4: the traceability checklist page.
    """
    page = site["traceability.html"]
    assert "supports evidence" in page and "compliant" not in page.lower()

    def row(req: str) -> str:
        return page.split(f'<tr data-req="{req}"', 1)[1].split("</tr>", 1)[0]

    w1, x1 = row("REQ-W-001"), row("REQ-X-001")
    assert (
        'data-check="rationale" class="ok"' in w1 and 'data-check="verification" class="ok"' in w1
    )
    assert 'data-check="rationale" class="gap"' in x1
    assert 'data-check="implemented" class="ok"' in w1
    assert "1 of 3 carry a rationale" in page
    assert 'href="traceability.html"' in site["requirements.html"], "the checklist is reachable"


def test_with_ears_on_a_requirement_page_shows_its_pattern(site: dict[str, str]) -> None:
    """S9 (owner-approved 2026-11-17): opt-in, never a gate. REQ-W-001's acceptance text ("Every
    item is parsed once, then the load finishes.") follows no EARS pattern, so its page says so.

    @brief P5.4 / S9: the EARS badge.
    """
    assert '<span class="ears ears-none">not EARS</span>' in site["req-REQ-W-001.html"]


def test_wiki_check_prints_ears_notes_without_failing_on_them(repo, capsys) -> None:
    """S9: never a gate. `clew wiki check` prints a note for each requirement in no EARS pattern,
    on stderr, and its exit code is exactly what the problems alone decide.

    @brief P5.4 / S9: EARS notes from `clew wiki check`.
    """
    from clew.wiki.check import check_wiki
    from clew.wiki.command import wiki_main

    root, db = repo
    rc = wiki_main(["check", "--repo-root", str(root), "--index", str(db)])
    out, err = capsys.readouterr()
    assert "note: REQ-W-001 is in no EARS pattern:" in err
    assert "note:" not in out, "notes are not problems"
    assert rc == (1 if check_wiki(root, db) else 0)


def test_a_requirement_page_draws_its_evidence_chain(site: dict[str, str]) -> None:
    """OWNER (round 5, P5.4): the requirement's evidence as a diagram — implementers → tests →
    result. Edges come from the row's `extent` (which implementers each test exercises), so a
    drawn line is a measured or tagged link, never a guess. REQ-W-001: `test_load` passed and
    exercises `load`.

    @brief P5.4: the implementers → tests → result diagram.
    """
    page = site["req-REQ-W-001.html"]
    svg = page[page.index('<svg class="req-evidence"') :]
    svg = svg[: svg.index("</svg>")]
    assert 'role="img"' in svg and "aria-label=" in svg
    assert ">load</text>" in svg and ">test_load</text>" in svg and ">passed</text>" in svg
    assert 'data-edge="test_load→load"' in svg


def test_a_requirement_page_links_to_its_map_overlay(site: dict[str, str]) -> None:
    """@brief P5.4: "Show on the map" opens the overlay for this requirement."""
    assert 'href="map.html#req=REQ-W-001"' in site["req-REQ-W-001.html"]


def test_a_test_page_pins_each_check_to_what_it_observes(site: dict[str, str]) -> None:
    """OWNER (round 5, P5.5): checks pinned by syntax tree. `test_load`'s one check,
    `assert load([]) == 1`, observes `load` directly.

    @brief P5.5: the pinned check on the test's page.
    """
    (name,) = [k for k in site if k.startswith("test-") and k.endswith("test_load.html")]
    page = site[name]
    item = page.split('<ol class="asserts">', 1)[1].split("</ol>", 1)[0]
    assert "<code>assert load([]) == 1</code>" in item
    assert '<span class="pin pin-direct">observes <code>load</code></span>' in item


def test_a_test_page_says_how_the_product_reaches_what_it_tests(site: dict[str, str]) -> None:
    """OWNER (round 5, P5.5): context paths. `test_load` calls `load`; the product flow from
    `main` reaches it, so the page shows that path and links the flow.

    @brief P5.5: the product's path to the tested code.
    """
    (name,) = [k for k in site if k.startswith("test-") and k.endswith("test_load.html")]
    context = site[name].split('<div class="context">', 1)[1].split("</div>", 1)[0]
    assert "<code>main</code> → <code>load</code>" in context
    assert 'href="flow-' in context


def test_a_test_page_draws_its_call_flow_boxes(site: dict[str, str]) -> None:
    """@brief P5.5: `test_load` → a box for `load`, linking its activity diagram."""
    (name,) = [k for k in site if k.startswith("test-") and k.endswith("test_load.html")]
    flow = site[name].split('<div class="callflow">', 1)[1].split("</div>", 1)[0]
    assert "#act-s-load" in flow and ">load</a>" in flow


def test_the_site_has_an_architecture_tab(site: dict[str, str]) -> None:
    """@brief P5.6: the C4 page is built and the home page links it."""
    page = site["architecture.html"]
    assert all(f'id="c4-l{n}"' in page for n in (1, 2, 3, 4))
    assert 'href="architecture.html"' in site["index.html"]


def test_source_bodies_and_diagrams_are_not_in_the_search_index(site: dict[str, str]) -> None:
    """P5.1b (2.0.0, page weight). MEASURED on clew's own site: searchindex.js was 8.2 MB, 6.35 MB
    of it 80,285 terms, because Sphinx's indexer strips the tags off RAW HTML and indexes the text —
    every folded source body, activity statement and SVG label. A function is found by its heading,
    signature and brief; code text is what the index's own code search is for. `SECRET_BODY_MARKER`
    lives only in `parse`'s body; `parse` itself must stay findable.

    @brief P5.1b: the search index holds names and prose, not bodies.
    """
    import pathlib

    index = (pathlib.Path(site["__html__"]) / "searchindex.js").read_text()
    assert "secret_body_mark" not in index.lower() and "secret_body_marker" not in index.lower()
    assert '"pars' in index, "the function's own name must stay searchable"


def test_a_flow_page_carries_a_quick_view_per_function(site: dict[str, str]) -> None:
    """OWNER (round 5, P5.6): every entity gets a quick-view modal with the view strip. A flow
    page lists a trigger per function on it, each opening its template, and loads the views
    script; `load` is on the fixture's `load` flow.

    @brief P5.6: quick views on flow pages.
    """
    page = _flow_page(site)
    quick = page.split('class="modal-list quick-views"', 1)[1].split("</ul>", 1)[0]
    assert 'data-modal="q-' in quick and ">load</a>" in quick
    template = re.search(
        r'<template id="modal-q-\d+" data-title="load \(src/data\.py\)">(.*?)</template>',
        page,
        re.S,
    )
    assert template and 'data-view-panel="tests"' in template.group(1)
    assert "_static/clew-views.js" in page


def test_the_views_script_is_budgeted() -> None:
    """@brief Owner Q/A 2026-11-20: clew-views.js has its own budget, and names nothing remote."""
    from clew.wiki.theme import THEMES

    js = THEMES / "clew" / "static" / "clew-views.js"
    assert js.stat().st_size <= _VIEWS_JS_BUDGET
    text = js.read_text()
    assert "http://" not in text and "https://" not in text


def test_the_step_table_and_the_diagram_stay_in_sync(site: dict[str, str]) -> None:
    """OWNER (round 5; Q/A 2026-11-20 "live sync" = diagram ↔ step table): each table row names its
    step, and the page script lights the row as the diagram plays or steps, scrolls it into view,
    and opens the step from a row.

    @brief P5.6: live sync.
    """
    page = _flow_page(site)
    table = page.split('<table class="clew steps"', 1)[1].split("</table>", 1)[0]
    assert re.findall(r'<tr data-step="(\d+)"', table)[:2] == ["0", "1"]
    for needle in ("animationstart", "scrollIntoView", "tr[data-step]"):
        assert needle in page, needle


def test_the_site_has_an_sbom_page(site: dict[str, str]) -> None:
    """@brief #70 (P5.8): the page is built and linked; the fixture has no SBOM, which it says."""
    page = site["sbom.html"]
    assert "No SBOM was found" in page and "This repository" in page
    assert 'href="sbom.html"' in site["index.html"]


def test_the_tests_tab_lists_every_test_with_a_filter(site: dict[str, str]) -> None:
    """OWNER (Q/A 2026-11-20): tests are their own category. The Tests tab lists every test the
    index recognises — linked or not — each linked to its page when it has one, with a filter box.

    @brief Tests tab.
    """
    page = site["tests.html"]
    table = page.split('<table class="clew tests-all"', 1)[1].split("</table>", 1)[0]
    assert re.search(r'<a href="test-[^"]*test_load\.html"><code>test_load</code></a>', table)
    assert 'data-filter-table="tests-all"' in page and "_static/clew-views.js" in page
    assert 'href="tests.html"' in site["index.html"]


def test_test_pages_are_kept_out_of_the_main_search(site: dict[str, str]) -> None:
    """OWNER (Q/A 2026-11-20): test pages leave the main search (68% of its postings on clew);
    they are found from the Tests tab's filter. Their pages still exist and link as before.

    @brief Test pages not in the search index.
    """
    import json
    import pathlib

    text = (pathlib.Path(site["__html__"]) / "searchindex.js").read_text()
    doc = json.loads(text[text.index("(") + 1 : text.rindex(")")])
    assert not [d for d in doc["docnames"] if d.startswith("test-")]
    assert any(k.startswith("test-") for k in site), "the test pages themselves are still built"


def test_every_recognised_test_is_found_not_only_the_linked(repo) -> None:
    """@brief `None` resolves every test the index recognises, a superset of the linked names."""
    from clew.query._common import connect
    from clew.wiki.testpages import _test_definitions

    _root, db = repo
    with connect(db) as conn:
        every = {d.name for d in _test_definitions(conn, None)}
        linked = {d.name for d in _test_definitions(conn, {"test_load"})}
    assert linked == {"test_load"} and linked <= every
