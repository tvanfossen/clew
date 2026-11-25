# SPDX-License-Identifier: MIT
"""The test flowchart: one diamond per pinned assertion, each failing into a declared mode (2.2, F2).

OWNER Q/A 2026-11-25. Ovals start and end the run; a box is the function an assertion observes
(its pin's target, from the syntax tree, never invented); a diamond is each assertion, in body
order. Pass continues down; fail goes right, into:

- the mode the assertion's INLINE MARKER names (`# fails_when: FM-1`, `// fails_when: FM-1`);
- else the test's only mode, when its docstring names exactly one (`@fails_when`);
- else an "unassigned" end, which says so rather than guessing.

@brief Tests flowchart derivation and rendering.
@version 1
"""

from __future__ import annotations

from clew.wiki.checkpins import pin_checks
from clew.wiki.flowchart import UNASSIGNED, chart, flowchart_html, marker

BODY = [
    "def test_add():",
    "    total = add(2, 3)",
    "    assert total == 5  # fails_when: FM-2",
    "    assert add(1, 1) == 2",
]
MEANINGS = {"FM-1": "overflow wraps silently", "FM-2": "wrong sum"}


def _pins():
    return pin_checks(BODY, "tests/test_add.py", {"add"}, first_line=10)


def test_a_marker_is_read_in_both_comment_styles() -> None:
    """@brief `# fails_when: ID` and `// fails_when: ID`; no marker is None."""
    assert marker("    assert total == 5  # fails_when: FM-2") == "FM-2"
    assert marker("    REQUIRE(x == 1); // fails_when: FM-A-1") == "FM-A-1"
    assert marker("    assert ok") is None


def test_each_assertion_is_a_diamond_failing_into_its_mode() -> None:
    """@brief Marker first; else the test's only mode; never a guess."""
    nodes = chart(_pins(), BODY, 10, ["FM-1"])
    kinds = [n.kind for n in nodes]
    assert kinds[0] == "start" and kinds[-1] == "passed"
    checks = [n for n in nodes if n.kind == "check"]
    assert [c.line for c in checks] == [12, 13]
    assert [c.fails_into for c in checks] == ["FM-2", "FM-1"], "marker wins; else the only mode"
    steps = [n.text for n in nodes if n.kind == "step"]
    assert steps and all("add" in s for s in steps), "a box is the function the check observes"
    two = chart(_pins(), BODY, 10, ["FM-1", "FM-3"])
    assert [c.fails_into for c in two if c.kind == "check"] == ["FM-2", UNASSIGNED]


def test_the_chart_renders_as_an_svg_the_player_can_step() -> None:
    """@brief Ovals, boxes, one diamond per check, the mode's meaning, and `data-step` order."""
    html = flowchart_html(chart(_pins(), BODY, 10, ["FM-1"]), MEANINGS)
    assert html.count("<polygon") == 2, "one diamond per assertion"
    assert "<ellipse" in html and "wrong sum" in html and "overflow wraps silently" in html
    assert 'data-step="0"' in html
    unassigned = flowchart_html(chart(_pins(), BODY, 10, ["FM-1", "FM-3"]), MEANINGS)
    assert "unassigned" in unassigned


def test_guard_refuses_a_marker_naming_an_undeclared_mode(tmp_path) -> None:
    """@brief An inline marker's id is checked against the catalogue like `@fails_when`."""
    from clew.guard.checks import check_fails_when_markers
    from clew.guard.config import load_config, parse_source_file

    path = tmp_path / "test_add.py"
    path.write_text(
        '"""@brief T."""\n\n\n## @brief Adds.\ndef test_add():\n    """@brief A."""\n'
        "    assert add(2, 3) == 5  # fails_when: FM-2\n"
        "    assert add(1, 1) == 2  # fails_when: FM-NOPE\n"
    )
    config = load_config(tmp_path / "no-such.yaml")
    (func,) = parse_source_file(str(path), config)
    lines = path.read_text().splitlines()
    (bad,) = check_fails_when_markers(func, str(path), lines, {"FM-1", "FM-2"})
    assert "FM-NOPE" in bad.message and bad.line == 8


def test_a_linked_test_page_draws_its_flowchart_and_a_test_naming_no_mode_does_not(
    tmp_path,
) -> None:
    """@brief Built for real: the page that names a mode has the figure; its sibling has none."""
    from clew.cli import _build_argparser, _run_pipeline
    from clew.wiki.build import build_wiki

    repo = tmp_path / "repo"
    files = {
        "src/__init__.py": "",
        "src/add.py": '"""@brief Add."""\n\n\n## @brief Add.\n## @req REQ-A-001\ndef add(a, b):\n'
        '    """@brief Add."""\n    return a + b\n',
        "tests/test_add.py": '"""@brief Tests."""\nfrom src.add import add\n\n\n'
        "## @brief Sums.\n## @req REQ-A-001\n## @fails_when FM-A-001-1\ndef test_sums():\n"
        '    """@brief Sums."""\n    assert add(2, 3) == 5\n    assert add(1, 1) == 2  # fails_when: FM-A-001-2\n\n\n'
        "## @brief Plain.\n## @req REQ-A-001\ndef test_plain():\n"
        '    """@brief Plain."""\n    assert add(0, 0) == 0\n',
        "README.md": "# Flow\n",
        "reqs.yaml": "requirements:\n  REQ-A-001:\n    name: Add\n    failure_modes:\n"
        "      FM-A-001-1: wrong sum\n      FM-A-001-2: identity broken\n",
        ".clew.yaml": "requirements:\n  file: reqs.yaml\n\nwiki:\n  title: Flow\n  docs: [README.md]\n",
    }
    for rel, text in files.items():
        (repo / rel).parent.mkdir(parents=True, exist_ok=True)
        (repo / rel).write_text(text)
    db = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    html = build_wiki(repo, db, tmp_path / "out")
    pages = {p.name: p.read_text() for p in html.rglob("test-*.html")}
    sums = next(v for k, v in pages.items() if "test_sums" in k)
    plain = next(v for k, v in pages.items() if "test_plain" in k)
    assert 'class="flowchart"' in sums and "How it can fail" in sums
    assert "wrong sum" in sums and "identity broken" in sums
    assert 'class="flowchart"' not in plain
