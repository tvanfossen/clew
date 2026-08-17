# SPDX-License-Identifier: MIT
"""Shared fixtures for the whole suite, and the tier gate.

## Why the symbol names never change

Every fixture here uses the SAME identifiers the `sample/` demobot tree used —
`sensor_poll`, `telemetry_report`, `event_bus_dispatch`, `handle_cloud_command`,
`DEMOBOT_POWER_BATTERY_MV`, `REQ-0621` — even though the data behind them is
synthetic. That is deliberate and it is the whole safety argument for the
conversion.

`sensor_poll` appears in 68 assertion sites. Renaming it would mean touching 68
assertions, and an assertion you touch is an assertion that can silently become a
tautology. Keeping the names byte-identical means the vast majority of the suite
was never edited at all: only the CONSTRUCTION of the data changed, so a test
that still passes is still testing what it tested before.

The names are arbitrary fixture identifiers. What the tests actually assert about
is the GRAPH SHAPE — decl/def duality on one name, an fnptr-dispatched edge with
no textual call site, a shared-key seam with no call path between its endpoints,
one logical call edge found by three extraction layers. That shape is reproduced
exactly; the words attached to it are incidental and therefore not worth the risk
of changing.

## The two database fixtures

`rich_db` is synthetic: doxygen-owned tables (`path`, `memberdef`, `xrefs`,
`compounddef`, `member`, `compoundref`) are hand-made, and every pipeline table
on top of them is created by calling the pipeline's OWN DDL functions. That is
what stops the fixture drifting from the shipped schema — when a CHECK tightens
or a column is added, the fixture gets it for free instead of quietly describing
a schema that no longer ships.

There is no longer a real-doxygen fixture here. `demobot_db` built one from the
committed `sample/` tree, and both are gone: every claim about what a REAL extractor
does to REAL source now lives in `tests/integration/`, which builds against actual
repositories (this checkout, and a pinned external clone) instead of a fixture
maintained for the purpose. That removes a dummy project from the tree without
losing the evidence — the one test that genuinely needed a real doxygen XML pass
moved to `tests/integration/test_xml_parity_integration.py`, where it now runs
against TWO real targets rather than one synthetic one.

@brief Suite-wide fixtures: the synthetic rich_db, its source tree, and the tier gate.
@version 2
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from gitfixture import strip_git_location_env
from richdb import CSAMPLE, build_rich_db

## Marker for tests that need a real doxygen run / a real repo checkout. They are
## DESELECTED unless `--integration` is passed. The gate is a conftest hook rather
## than `[tool.pytest.ini_options]` because pyproject.toml:113 states that gate
## configuration does not live there — `.pre-commit-config.yaml` is the single
## source of truth for the gates, and pytest cannot read it.
INTEGRATION_MARK = "integration"

## The whole opt-in tier lives here, and the directory itself is the marker: its
## modules are ignored at COLLECTION time, not deselected afterwards. That matters
## for two reasons — importing them pulls the real-pipeline machinery in for a run
## that will not use it, and a module in there that fails to import would break the
## hermetic suite it is explicitly not part of.
INTEGRATION_DIR = "integration"


## @brief Register the `--integration` option that opts the slow tier in.
## @param parser The pytest argument parser.
## @version 1
def pytest_addoption(parser: pytest.Parser) -> None:
    """@brief Add `--integration`, which opts the real-pipeline tier in.

    @param parser The pytest argument parser.
    @version 1
    """
    parser.addoption(
        f"--{INTEGRATION_MARK}",
        action="store_true",
        default=False,
        help="also run tests marked `integration` (real doxygen run over a real repo).",
    )


## @brief Declare the `integration` marker so `--strict-markers` stays possible.
## @param config The pytest config object.
## @version 1
def pytest_configure(config: pytest.Config) -> None:
    """@brief Register the `integration` marker with pytest.

    @param config The pytest config object.
    @version 1
    """
    config.addinivalue_line(
        "markers",
        f"{INTEGRATION_MARK}: needs a real doxygen run or a real repo checkout",
    )


## @brief Skip collecting `tests/integration/` unless `--integration` is passed.
## @param collection_path Path pytest is about to collect.
## @param config The pytest config object.
## @return True to ignore the path, else None (leave the decision to pytest).
## @version 1
def pytest_ignore_collect(collection_path: Path, config: pytest.Config) -> bool | None:
    """Ignored at collection, not deselected after it. A deselect still IMPORTS
    the module, so a real-pipeline tier that is not being run would still pay its
    import cost — and, worse, an import error there would fail the hermetic suite
    that has nothing to do with it.

    @brief Keep the opt-in tier out of a default collection entirely.
    @param collection_path Path pytest is about to collect.
    @param config The pytest config object.
    @return True to ignore, else None.
    @version 1
    """
    if config.getoption(f"--{INTEGRATION_MARK}"):
        return None
    tests_root = Path(__file__).resolve().parent
    return collection_path == tests_root / INTEGRATION_DIR or None


## @brief Deselect `integration`-marked tests unless they were requested.
## @param config The pytest config object.
## @param items Collected test items (mutated in place).
## @version 1
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Covers the tests that live in the DEFAULT files but still need a real
    pipeline run — the ones whose claim is about what a real extractor does, which
    a hand-built fixture cannot evidence. `tests/integration/` as a whole is
    handled earlier, by `pytest_ignore_collect`.

    DESELECT rather than skip. A skipped test is reported as a skip, and the
    release checklist asserts the default run has ZERO skipped tests — so using
    skip here would either break that assertion or force it to be weakened to
    "zero skips except these", which is the same thing as not having it.

    @brief Drop `integration`-marked tests from a default run.
    @param config The pytest config object.
    @param items Collected test items (mutated in place).
    @version 1
    """
    if config.getoption(f"--{INTEGRATION_MARK}"):
        return
    deselected = [item for item in items if item.get_closest_marker(INTEGRATION_MARK)]
    if deselected:
        config.hook.pytest_deselected(items=deselected)
        items[:] = [item for item in items if item not in deselected]


## @brief Hide the ambient git repository from every test in the session.
## @return Generator yielding once, with the caller's own git variables restored after.
## @version 1
@pytest.fixture(autouse=True, scope="session")
def _isolate_git_environment() -> Iterator[None]:
    """A HARD SAFETY REQUIREMENT, for the same reason `_isolate_claude_config` is,
    and a worse one: this leak does not merely read the wrong state, it WRITES.

    MEASURED, not anticipated. Under `git commit` — the only invocation that
    exports these — 13 tests across `test_datamodel`, `test_external_provenance`
    and `test_index_scope_inheritance` failed while the identical tree passed
    standalone, because a fixture's `git init` inside `tmp_path` resolved to the
    real repository and the nested trees it builds were therefore never nested
    trees at all. The same run staged nine phantom gitlink entries
    (`vendor/lib`, `deps/generator`, `evidence/other_project`, …) into the
    repository's index, pointing at directories that exist only under
    `/tmp/pytest-of-*`. Committing that would have written submodule gitlinks to
    nowhere into HEAD.

    It is also why the gate's two invocations disagreed: `pre-commit run
    --all-files` runs in a plain shell and passed, `git commit` ran the same tests
    and failed. That reads exactly like "my change broke the suite", and the
    control that settles it is this one — restore HEAD, set the variables by hand,
    watch the identical 8 failures (`.claude/tmp/gitenv_control.sh`).

    Session-scoped rather than per-test because removal is idempotent and carries
    no cross-test state, unlike the per-test config isolation above.

    @brief Remove inherited git location variables for the whole session.
    @return Generator yielding once.
    @version 1
    """
    removed = strip_git_location_env(os.environ)
    yield
    os.environ.update(removed)


## @brief Point `CLAUDE_CONFIG_DIR` at a throwaway directory for every test.
## @param tmp_path_factory Session-scoped temporary-directory factory.
## @return Generator yielding once, with the real config directory restored after.
## @version 2
@pytest.fixture(autouse=True)
def _isolate_claude_config(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    """A HARD SAFETY REQUIREMENT, not a convenience.

    `mcp_config.apply_plan` REWRITES the file `global_config_path()` returns, and
    without an override that file is `~/.claude.json` — roughly 144 KB of the
    user's live Claude Code state (project history, MCP registrations, session
    metadata), none of which is regenerable. `claude_state_dir()` resolves the
    same way. Setting `CLAUDE_CONFIG_DIR` relocates BOTH, so no test — present or
    future, deliberate or accidental — can reach the real one.

    Autouse, so a new `init` test is protected by existing rather than by
    remembering to request a fixture. PER-TEST rather than per-session: a single
    shared directory would make the global-scope `init` tests couple to each other
    through the `.claude.json` a previous one left behind — the same cross-test
    state leak the isolation exists to prevent, just relocated from the user's home
    directory into the suite.

    Restores the caller's own value rather than deleting the variable, because a
    developer running the suite under a deliberately set `CLAUDE_CONFIG_DIR` should
    get it back.

    @brief Redirect the Claude config directory away from the user's real state.
    @param tmp_path_factory Session-scoped temporary-directory factory.
    @return Generator yielding once.
    @version 2
    """
    isolated = tmp_path_factory.mktemp("claude-config")
    previous = os.environ.get("CLAUDE_CONFIG_DIR")
    os.environ["CLAUDE_CONFIG_DIR"] = str(isolated)
    yield
    if previous is None:
        os.environ.pop("CLAUDE_CONFIG_DIR", None)
    else:
        os.environ["CLAUDE_CONFIG_DIR"] = previous


## @brief The real source tree the `rich_db` index's paths point at.
## @return Path to `tests/data/csample/`.
## @version 1
@pytest.fixture(scope="session")
def repo_root() -> Path:
    """Used in place, not copied. Nothing in the default suite writes into it, and
    the tests that need a mutable tree (`source()` refusing an unreadable root, the
    source-drift detector) build their own under `tmp_path` — so a copy would buy
    isolation nothing needs and hide the fact that `rich_db`'s `path` rows and this
    directory are the same fixture.

    @brief The C source tree behind the synthetic index.
    @return Path to `tests/data/csample/`.
    @version 1
    """
    return CSAMPLE


## @brief The synthetic index over `repo_root`, built once per session.
## @param tmp_path_factory Session-scoped temporary-directory factory.
## @return Path to the built database.
## @version 1
@pytest.fixture(scope="session")
def rich_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Doxygen's four tables are hand-made; the other fifteen stages are RUN
    against the real source tree (see `tests/richdb.py` for what that buys). No
    doxygen binary, no network, ~0.5s.

    Session-scoped and therefore SHARED: every test reading it must treat it as
    read-only. Nothing in the converted suite writes to it — the tests that mutate
    a database build their own with `tmp_path`.

    @brief Session-scoped synthetic clew.db over tests/data/csample/.
    @param tmp_path_factory Session-scoped temporary-directory factory.
    @return Path to the built database.
    @version 2
    """
    return build_rich_db(tmp_path_factory.mktemp("richdb") / "clew.db", CSAMPLE)
