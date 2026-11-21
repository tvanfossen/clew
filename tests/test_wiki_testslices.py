# SPDX-License-Identifier: MIT
"""Tests drawn as slices of master flows, on a built site (round 5, R5-4c).

OWNER 2026-11-17: "a test itself doesn't need a sequence diagram, a test case is testing a portion
OF a sequence diagram". With per-test coverage the site draws, on each test's page, the window of
every master flow the test exercised — its steps lit, the rest dimmed, where it entered marked —
and links the whole master flow with that test highlighted. No test gets a flow page of its own.

@brief Site tests for test slices.
@version 2
"""

from __future__ import annotations

import json

import pytest

from clew.cli import _build_argparser, _run_pipeline

_APP = '''\
from src.store import check, save


def run(x):
    """Run."""
    y = check(x)
    return save(y)
'''

_STORE = '''\
def check(x):
    """Check."""
    return clean(x)


def clean(x):
    """Clean.

    @req REQ-A-001
    """
    return x


def save(x):
    """Save."""
    return x
'''

_TESTS = '''\
from src.app import run
from src.store import check


def test_run():
    """Runs it all."""
    assert run(1) == 1


def test_check():
    """Checks only."""
    assert check(2) == 2
'''

## test_run ran run's two calls and everything under them; test_check called check itself.
## FIXTURE CHANGED (2.0.0, W11): the node ids are the shape pytest writes, `<file>::<test>`. They
## were `t::<test>`, a placeholder whose file part named nothing, which a key that keeps the file
## (W11) cannot attribute to the test's definition.
_CONTEXTS = {
    "files": {
        "src/app.py": {
            "contexts": {
                "6": ["tests/test_app.py::test_run|run"],
                "7": ["tests/test_app.py::test_run|run"],
            }
        },
        "src/store.py": {
            "contexts": {
                "3": ["tests/test_app.py::test_run|run", "tests/test_app.py::test_check|run"],
                "11": ["tests/test_app.py::test_run|run", "tests/test_app.py::test_check|run"],
                "17": ["tests/test_app.py::test_run|run"],
            }
        },
    }
}

## FIXTURE CHANGED (2.0.0, R5-CFG F20): the test evidence is the top-level `tests:` section.
_WIKI = """\
tests:
  contexts: coverage.json

wiki:
  title: Slices
  docs: [README.md]
  flows:
    - entry: run
      depth: 1
"""


## @brief A built site whose tests carry per-test coverage.
## @param tmp_path_factory Pytest's factory.
## @return {relative page path: html}.
## @version 1
@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    """@brief Build. @return Pages."""
    from clew.wiki.build import build_wiki

    root = tmp_path_factory.mktemp("slices")
    repo = root / "repo"
    for rel, text in {
        "src/__init__.py": "",
        "src/app.py": _APP,
        "src/store.py": _STORE,
        "tests/test_app.py": _TESTS,
        "README.md": "# Slices\n",
        "requirements.yaml": "requirements:\n  REQ-A-001:\n    name: Clean\n",
        "coverage.json": json.dumps(_CONTEXTS),
        ".clew.yaml": _WIKI,
    }.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    db = root / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    html = build_wiki(repo, db, root / "out")
    return {p.relative_to(html).as_posix(): p.read_text() for p in html.rglob("*.html")}


def _page(site: dict[str, str], prefix: str) -> str:
    """@brief The one page whose name starts with prefix. @return Its HTML."""
    found = [v for k, v in site.items() if k.startswith(prefix)]
    assert len(found) == 1, sorted(k for k in site if k.startswith(prefix[:5]))
    return found[0]


def test_the_master_flow_grows_where_tests_ran(site: dict[str, str]) -> None:
    """@brief Declared depth 1, but check → clean ran, so the master flow draws it."""
    flow = _page(site, "flow-run")
    assert ">clean<" in flow


def test_a_test_page_draws_its_slice_of_the_master_flow(site: dict[str, str]) -> None:
    """test_check called check itself: its page draws the window of `run`'s flow around
    check → clean, lit, entered at check, and links the whole flow with the test highlighted.

    @brief The test page carries the slice, the entry and the link.
    """
    page = _page(site, "test-tests-test_app-py-test_check")
    assert "What it exercises" in page
    assert 'class="st ex entry"' in page and "test enters" in page
    ## W11 (2.0.0): the link carries the test's key, `file::name`.
    assert 'href="flow-run.html#test=tests/test_app.py%3A%3Atest_check"' in page


def test_no_test_gets_a_flow_page_of_its_own(site: dict[str, str]) -> None:
    """@brief Tests are slices; only master flows have flow pages."""
    assert not [k for k in site if k.startswith("flow-test_")]


def test_the_master_flow_page_carries_each_test_s_slice(site: dict[str, str]) -> None:
    """@brief `#test=<name>` on a flow page lights that test's steps; the slices ride inline."""
    flow = _page(site, "flow-run")
    assert 'id="flow-slices"' in flow and '"tests/test_app.py::test_check"' in flow


def test_a_test_page_draws_its_top_slices_and_lists_the_rest(monkeypatch) -> None:
    """OWNER Q/A 2026-11-20 (after P6): slice diagrams were 84 MB of clew's 179 MB site — 8,148
    inline SVGs, three flows on most pages, by flow rank 49.2 / 21.6 / 13.3 MB. The top
    `wiki.test_slices` flows (default 1, by steps exercised) are drawn; the rest are a `<details>`
    "N more" list, each linking its whole flow lit for this test.

    @brief Slices past the cap are links in a details list.
    """
    from types import SimpleNamespace

    from clew.wiki import slices, testpages

    monkeypatch.setattr(slices, "slice_svg", lambda flow, cut: "<svg class='seq'/>")
    page = lambda n, s: SimpleNamespace(name=f"flow-{n}", title=n, steps=s, flow=None)  # noqa: E731
    cut = lambda k: SimpleNamespace(exercised=tuple(range(k)))  # noqa: E731
    cuts = [(page("a", 40), cut(9)), (page("b", 30), cut(5)), (page("c", 20), cut(2))]

    html = testpages._exercises("t", {"slices": {"t": cuts}})
    assert html.count("<svg") == 1, html
    assert "<details" in html and "2 more" in html
    assert 'href="flow-b.html#test=t"' in html and 'href="flow-c.html#test=t"' in html

    wider = testpages._exercises("t", {"slices": {"t": cuts}, "test_slices": 2})
    assert wider.count("<svg") == 2 and "1 more" in wider


def test_wiki_test_slices_is_a_whole_number_of_one_or_more(tmp_path) -> None:
    """@brief `wiki.test_slices` defaults to 1, reads a value, and refuses 0 by name."""
    from clew.wiki.config import WikiConfig, load_wiki_config

    assert WikiConfig().test_slices == 1
    (tmp_path / ".clew.yaml").write_text("wiki:\n  test_slices: 2\n")
    config, problems = load_wiki_config(tmp_path, None)
    assert config.test_slices == 2 and problems == []
    (tmp_path / ".clew.yaml").write_text("wiki:\n  test_slices: 0\n")
    _config, problems = load_wiki_config(tmp_path, None)
    assert any("wiki.test_slices" in p for p in problems), problems
