# SPDX-License-Identifier: MIT
"""Tests drawn as slices of master flows, on a built site (round 5, R5-4c).

OWNER 2026-11-17: "a test itself doesn't need a sequence diagram, a test case is testing a portion
OF a sequence diagram". With per-test coverage the site draws, on each test's page, the window of
every master flow the test exercised — its steps lit, the rest dimmed, where it entered marked —
and links the whole master flow with that test highlighted. No test gets a flow page of its own.

@brief Site tests for test slices.
@version 1
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
_CONTEXTS = {
    "files": {
        "src/app.py": {"contexts": {"6": ["t::test_run|run"], "7": ["t::test_run|run"]}},
        "src/store.py": {
            "contexts": {
                "3": ["t::test_run|run", "t::test_check|run"],
                "11": ["t::test_run|run", "t::test_check|run"],
                "17": ["t::test_run|run"],
            }
        },
    }
}

_WIKI = """\
wiki:
  title: Slices
  docs: [README.md]
  flows:
    - entry: run
      depth: 1
  tests:
    contexts: coverage.json
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
    assert 'href="flow-run.html#test=test_check"' in page


def test_no_test_gets_a_flow_page_of_its_own(site: dict[str, str]) -> None:
    """@brief Tests are slices; only master flows have flow pages."""
    assert not [k for k in site if k.startswith("flow-test_")]


def test_the_master_flow_page_carries_each_test_s_slice(site: dict[str, str]) -> None:
    """@brief `#test=<name>` on a flow page lights that test's steps; the slices ride inline."""
    flow = _page(site, "flow-run")
    assert 'id="flow-slices"' in flow and '"test_check"' in flow
