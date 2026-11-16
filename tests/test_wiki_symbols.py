# SPDX-License-Identifier: MIT
"""Symbol pages and the ego-graph (round 3, P1f).

Owner 2026-11-15: source links should be DOSSIER REFERENCES — a symbol's own page, which links its
source — and a dossier viewer drawn as a "spiderweb" of its links ("walking source"). Every symbol
the site references (a requirement's implementers, a flow's functions) gets a section on its
file's page: signature, brief, a radial EGO-GRAPH of its callers and callees two hops out (big
fan-outs folded, never dropped silently), the requirements it implements, the flows it is on, and
its body bundled from the file (withheld under `exclude_bodies`).

"GH LINK BROKEN (local unpushed commits)": a source permalink names a commit; when the repository
HAS a remote and no remote branch contains that commit, the permalink would 404, so the site
drops it and the bundled body stands in. With no git or no remote nothing is known, and links
stay.

@brief Tests for symbol pages, the ego-graph and published-commit permalinks.
@version 1
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.test_wiki_site import repo, site  # noqa: F401  (module fixtures reused)


def test_a_referenced_symbol_has_a_section_on_its_files_page(site: dict[str, str]) -> None:  # noqa: F811
    """@brief P1f: signature, ego-graph, requirements, flows and bundled body."""
    page = site["sym-src-data-py.html"]
    load = page[page.index('id="s-load"') :]
    load = load[: load.index('id="s-parse"')] if 'id="s-parse"' in load else load
    ego = load[load.index('<svg class="ego"') : load.index("</svg>")]
    assert ">load<" in ego and ">parse<" in ego and ">finish<" in ego
    assert 'href="requirements.html#REQ-W-001"' in load
    assert 'href="flow-load.html"' in load
    assert "SECRET_BODY_MARKER" in page[page.index('id="s-parse"') :]


def test_implementers_and_flow_steps_link_to_symbol_sections(site: dict[str, str]) -> None:  # noqa: F811
    """@brief P1f: dossier references instead of bare source links."""
    req = site["requirements.html"]
    assert 'href="sym-src-data-py.html#s-load"' in req
    flow = site["flow-load.html"]
    steps = flow[flow.index('<table class="clew steps"') :]
    assert 'href="sym-src-data-py.html#s-parse"' in steps[: steps.index("</table>")]


def test_a_partner_site_bundles_no_body_on_symbol_pages(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    """@brief P1f: `exclude_bodies` reaches symbol pages."""
    from clew.wiki.build import build_wiki

    html = build_wiki(repo[0], repo[1], tmp_path / "out", audience="partner")
    page = (html / "sym-src-data-py.html").read_text()
    assert "SECRET_BODY_MARKER" not in page and 'id="s-parse"' in page


def test_the_ego_graph_folds_a_large_fan_out() -> None:
    """A FOLD IS SAID: more neighbours than fit become one "+N more" node.

    @brief P1f: ego-graph folding.
    """
    from clew.wiki.symbols import ego_svg

    callees = [(f"f{i}", "") for i in range(25)]
    svg = ego_svg("hub", [("caller", "")], callees, {})
    assert ">hub<" in svg and ">caller<" in svg
    assert len(re.findall(r'class="node callee"', svg)) == 10
    assert "+15 more" in svg


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_a_permalink_needs_the_commit_on_a_remote(tmp_path: Path) -> None:
    """@brief P1f: unpushed with a remote → unpublished; pushed → published; no remote → unknown."""
    from clew.wiki.build import commit_published

    work, bare = tmp_path / "work", tmp_path / "remote.git"
    work.mkdir()
    _git(tmp_path, "init", "-q", "--bare", str(bare))
    _git(work, "init", "-q", "-b", "main")
    _git(
        work,
        "-c",
        "user.email=t@e",
        "-c",
        "user.name=t",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    sha = _git(work, "rev-parse", "HEAD")
    assert commit_published(work, sha) is None
    _git(work, "remote", "add", "origin", str(bare))
    assert commit_published(work, sha) is False
    _git(work, "push", "-q", "origin", "main")
    _git(work, "fetch", "-q", "origin")
    assert commit_published(work, sha) is True


@pytest.mark.parametrize("rel", ["src/data.py", "a/b/c.py"])
def test_symbol_page_names_are_stable(rel: str) -> None:
    """@brief P1f: one page per file, its name derived from the path."""
    from clew.wiki.symbols import page_for

    assert page_for(rel) == "sym-" + re.sub(r"[^A-Za-z0-9]+", "-", rel).strip("-")


def test_a_stale_extent_bundles_no_wrong_body(tmp_path: Path) -> None:
    """FOUND ON THE DEMO: an index older than the file bundled another function's lines under
    this one's name. A recorded extent that no longer names the function says so instead.

    @brief P1f: stale body extents.
    """
    from clew.wiki.symbols import Definition, _body

    (tmp_path / "m.py").write_text("def other():\n    return 1\n\n\ndef mine():\n    return 2\n")
    stale = Definition(1, "mine", "m.py", "mine()", "", 1, 2)
    fresh = Definition(1, "mine", "m.py", "mine()", "", 5, 6)
    assert "return 1" not in _body(tmp_path, stale) and "older than this file" in _body(
        tmp_path, stale
    )
    assert "return 2" in _body(tmp_path, fresh)


# --- Round 3, P2a: what a test tests --------------------------------------------------------------


def test_a_test_section_says_what_it_verifies_and_how(site: dict[str, str]) -> None:  # noqa: F811
    """OWNER 2026-11-15: "click into a test associated with a requirement and see WHAT it's
    testing". A test's section lists its assertions, the requirements it verifies with the link
    kind, and for an inferred link the call path from the test to the implementer it reaches.

    @brief P2a: a test's section.
    """
    page = site["sym-tests-test-data-py.html"]
    sec = page[page.index('id="s-test_load"') :]
    asserts = sec[sec.index('class="asserts"') :]
    assert "assert load([]) == 1" in asserts[: asserts.index("</ul>")]
    verifies = sec[sec.index('class="verifies"') :]
    verifies = verifies[: verifies.index("</table>")]
    assert 'href="requirements.html#REQ-X-001"' in verifies and "via-inferred" in verifies
    assert re.search(r"test_load\s*→\s*load\s*→\s*parse", re.sub(r"<[^>]+>", "", verifies))
    assert "t-passed" in sec[: sec.index('class="verifies"')]


def test_a_requirements_tests_link_to_their_sections(site: dict[str, str]) -> None:  # noqa: F811
    """@brief P2a: a requirement's tests open what they test."""
    body = site["requirements.html"]
    assert 'href="sym-tests-test-data-py.html#s-test_load"' in body
    assert 'href="sym-tests-features-finish-feature.html#s-Finish_runs"' in body


def test_a_gherkin_scenario_is_displayed_as_gherkin(site: dict[str, str]) -> None:  # noqa: F811
    """OWNER 2026-11-15: "when we display gherkin, please display it properly" — Feature and
    Scenario headings, keyword-highlighted steps, tags as chips, its result.

    @brief P2a: Gherkin rendering.
    """
    page = site["sym-tests-features-finish-feature.html"]
    sec = page[page.index('id="s-Finish_runs"') :]
    assert '<span class="gk">Feature:</span>' in sec and '<span class="gk">Scenario:</span>' in sec
    assert '<span class="gk step">Then</span> it finishes' in sec
    assert '<span class="gtag">@REQ-W-002</span>' in sec and "t-failed" in sec


def test_a_partner_site_lists_no_assertions(
    repo: tuple[Path, Path],  # noqa: F811
    tmp_path: Path,
) -> None:
    """@brief P2a: assertions are source text — withheld under `exclude_bodies`."""
    from clew.wiki.build import build_wiki

    html = build_wiki(repo[0], repo[1], tmp_path / "out", audience="partner")
    page = (html / "sym-tests-test-data-py.html").read_text()
    assert "assert load" not in page and 'class="verifies"' in page


def test_assertions_are_read_per_framework() -> None:
    """@brief P2a: Python assert, Catch2 REQUIRE/CHECK, gtest EXPECT_/ASSERT_, Unity TEST_ASSERT_;
    a statement spanning lines is read whole."""
    from clew.wiki.testfacts import assertions

    lines = [
        "def test_x():",
        "    assert f(1) == 2",
        "  REQUIRE(x == 1);",
        "  CHECK_THAT(a,",
        "             Equals(b));",
        "  EXPECT_EQ(1, f());",
        "  foo();",
        "  TEST_ASSERT_EQUAL(1, x);",
        "  ASSERT_TRUE(ok) << why;",
    ]
    assert assertions(lines) == [
        "assert f(1) == 2",
        "REQUIRE(x == 1);",
        "CHECK_THAT(a, Equals(b));",
        "EXPECT_EQ(1, f());",
        "TEST_ASSERT_EQUAL(1, x);",
        "ASSERT_TRUE(ok) << why;",
    ]


def test_gherkin_renders_rules_examples_and_doc_strings() -> None:
    """@brief P2a: a Rule heading, an Examples table and a doc string, as Gherkin."""
    from clew.wiki.testfacts import render_scenario

    text = (
        "@area\nFeature: Cart\n  Rule: Totals\n    @REQ-C-1\n    Scenario Outline: Add <n>\n"
        '      Given a cart\n      When I add <n> items\n      Then the body is\n        """\n'
        '        total <n>\n        """\n      Examples:\n        | n |\n        | 2 |\n'
        "    Scenario: Other\n      Given nothing\n"
    )
    html = render_scenario(text, 5)
    assert '<span class="gk">Rule:</span> Totals' in html
    assert '<span class="gk">Scenario Outline:</span> Add &lt;n&gt;' in html
    assert "<table" in html and "<td>2</td>" in html
    assert '<pre class="docstring">total &lt;n&gt;</pre>' in html
    assert "Other" not in html and '<span class="gtag">@area</span>' in html
