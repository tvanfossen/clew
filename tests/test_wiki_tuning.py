# SPDX-License-Identifier: MIT
"""Every build-time number the wiki assumed is a declared key (R5-CFG C1-C5, C7-C9, W6, W8, W13, D14).

FOUND BY THE 2.0.0 HARD-CODING REVIEW (agent B, vetted, owner-approved: "those hard values belong
in the config file"). Each was a module constant a repository could not change: how deep a call
measured as run expands (12) and how many steps a measured flow may hold (400); the test →
implementer path depth (5 on a symbol page, 12 on a test page — one question, two answers); a
traced test's flow depth (2) and timeout (600 s) and its interpreter (silently clew's own); the
map's package depth (2) and web ring cap (8); the report size cap (64 MiB, now also per-test LCOV);
the gate's diff base (`origin/main`). Two silent faults ride along: the fast refresh ignored a
declared catalog, and the issue fetch stopped at 50 pages without saying so.

@brief Tests the wiki's tuning keys, the gate's diff base and the two silent faults.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.wiki.config import load_wiki_config
from tests.test_wiki_flow import _RAN_LOAD_ONLY, indexed  # noqa: F401  (fixture reused)


def _config(tmp_path: Path, text: str):
    """@brief Load a `.clew.yaml`. @return (config, problems)."""
    (tmp_path / ".clew.yaml").write_text(text, encoding="utf-8")
    return load_wiki_config(tmp_path)


def test_the_defaults_are_the_former_constants(tmp_path: Path) -> None:
    """@brief Undeclared, every key is the value the code used to assume."""
    config, problems = _config(tmp_path, "wiki: {title: x}\n")
    assert not problems
    assert (config.measured_depth, config.measured_steps) == (12, 400)
    assert (config.path_depth, config.trace_depth, config.trace_timeout) == (12, 2, 600)
    assert (config.component_depth, config.web_max_ring, config.trace_python) == (2, 8, None)
    assert config.max_report_mb == 64


def test_every_key_is_read_and_a_bad_one_is_a_problem(tmp_path: Path) -> None:
    """@brief Declared values are read; a non-positive or non-integer value is reported."""
    config, problems = _config(
        tmp_path,
        "wiki:\n  measured_depth: 4\n  measured_steps: 50\n  path_depth: 3\n  trace_depth: 1\n"
        "  trace_timeout: 30\n  trace_python: .tox/py/bin/python\n  component_depth: 3\n"
        "  web: {max_ring: 5}\n  flows:\n    - {entry: main, measured_depth: 2, max_steps: 9}\n"
        "tests:\n  max_report_mb: 8\n",
    )
    assert not problems, problems
    assert (config.measured_depth, config.measured_steps, config.path_depth) == (4, 50, 3)
    assert (config.trace_depth, config.trace_timeout, config.trace_python) == (
        1,
        30,
        ".tox/py/bin/python",
    )
    assert (config.component_depth, config.web_max_ring, config.max_report_mb) == (3, 5, 8)
    assert (config.flows[0].measured_depth, config.flows[0].max_steps) == (2, 9)
    _config_, problems = _config(tmp_path, "wiki:\n  measured_depth: 0\n  web: {max_ring: x}\n")
    assert any("measured_depth" in p for p in problems) and any("max_ring" in p for p in problems)


def test_a_measured_depth_bounds_measured_expansion(indexed: tuple[Path, Path]) -> None:  # noqa: F811
    """C1: a call measured as run expands past the flow's depth only up to `measured_depth`.

    @brief derive_flow honours measured_depth.
    """
    from clew.wiki.flow import derive_flow

    db, repo = indexed
    deep = derive_flow(db, repo, "main", depth=1, executed=_RAN_LOAD_ONLY)
    held = derive_flow(db, repo, "main", depth=1, executed=_RAN_LOAD_ONLY, measured_depth=1)
    assert ("load", "parse") in {(s.caller, s.callee) for s in deep.steps}
    assert ("load", "parse") not in {(s.caller, s.callee) for s in held.steps}


def test_the_package_depth_is_declared(tmp_path: Path) -> None:
    """C7: `src/main/java/com/acme/x.java` is one package `src/main` at depth 2, deeper at 4.

    @brief graph package depth.
    """
    from clew.wiki.graph import package_of

    assert package_of("src/main/java/com/acme/x.java") == "src/main"
    assert package_of("src/main/java/com/acme/x.java", depth=4) == "src/main/java/com"


def test_a_traced_run_names_the_interpreter_it_fell_back_to(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """W6: no venv found and none declared → clew's own interpreter, said at WARNING; a declared
    interpreter is used as given.

    @brief The traced-run interpreter is declared or the fallback is said.
    """
    import logging
    import sys

    from clew.wiki.tracerun import interpreter_for

    with caplog.at_level(logging.WARNING):
        assert interpreter_for(tmp_path) == Path(sys.executable)
    assert any("interpreter" in r.message for r in caplog.records)
    assert interpreter_for(tmp_path, declared="bin/py") == tmp_path / "bin/py"


def test_the_gate_diffs_against_a_declared_base(tmp_path: Path) -> None:
    """W8: `guard.impact.base` is the branch the impact report diffs against.

    @brief guard.impact.base.
    """
    from clew.guard.config import impact_base, load_config

    (tmp_path / ".clew.yaml").write_text("guard:\n  impact:\n    base: upstream/develop\n")
    assert impact_base(load_config(tmp_path / ".clew.yaml")) == "upstream/develop"
    assert impact_base(load_config(tmp_path / "none.yaml")) == "origin/main"


def test_the_fast_tier_refuses_when_a_declared_catalog_changes(tmp_path: Path) -> None:
    """W13: the fast refresh matched only the basename `requirements.yaml`; a catalog declared at
    another path changed under it without the full build its derived edges need.

    @brief A declared catalog is a whole-index input.
    """
    from clew.fasttier import config_inputs

    (tmp_path / ".clew.yaml").write_text("requirements:\n  file: docs/reqs.yaml\n")
    assert "docs/reqs.yaml" in config_inputs(tmp_path)


def test_a_truncated_issue_fetch_says_so() -> None:
    """D14: the fetch stopped at its page cap and returned what it had with no disclosure.

    @brief The cap is reported, not silent.
    """
    from clew.wiki.issues import fetch_pages

    pages = iter([[{"n": i}] * 100 for i in range(60)])
    rows, truncated = fetch_pages(lambda page: next(pages), max_pages=3)
    assert len(rows) == 300 and truncated is True
