# SPDX-License-Identifier: MIT
"""Where a repo's doxygen-guard config is, and what happens when it is not found.

gh#16: discovery hardcoded `<repo-root>/.doxygen-guard.yaml` in three independent
places, so a target that keeps its config in a subdirectory — and NAMES that
location in its own pre-commit hook's `args: [--config, <path>]` — was indexed at a
scope its declaration excludes. Silently: no error, no warning, a successful build.

These tests pin the three properties that absence had: the declared location is now
read, the not-found case is LOUD and names where it looked, and ambiguity is REFUSED
rather than resolved by ordering (`discover_doxyfile`'s precedent, which was once
caught selecting a test fixture's Doxyfile to index a whole project).

@brief Guard-config discovery, loud fallback, and refusal to guess.
@version 1
"""

from __future__ import annotations

import logging
from pathlib import Path

from clew.declaration import load_declaration
from clew.precommit import (
    GUARD_SOURCE_CONVENTIONAL,
    GUARD_SOURCE_EXPLICIT,
    GUARD_SOURCE_HOOK_ARGS,
    GUARD_SOURCE_NONE,
    GUARD_SOURCE_ROOT,
    discover_guard_config,
    discover_guard_config_logged,
)
from clew.scope import (
    INDEX_SCOPE_SECTION,
    SOURCE_DECLARED,
    derive_scope,
    derive_scope_logged,
)

## A guard config carrying an `x-clew` passthrough that declares an index
## scope. The passthrough is the consumer that mattered most: it carries THIS tool's
## whole declaration, including `index_scope`, so a config it cannot find is a scope
## decision made from built-in defaults.
_GUARD_CONFIG = """\
validate:
  exclude:
    - '^vendor/'
x-clew:
  index_scope:
    roots: ['src']
"""


## @brief Write a pre-commit config declaring a doxygen-guard hook.
## @param root Repo root to write into.
## @param args The hook's `args:` list, or None to omit it.
## @return The written config path.
## @version 1
## @dg_internal
def _write_precommit(root: Path, args: list[str] | None = None) -> Path:
    """The hook deliberately declares NO `files:`. That is what makes the scope
    assertions meaningful: with no include filter the guard-derived scope sweeps the
    whole tree, so if the passthrough is not found the test sees `vendor/` indexed.

    @brief Write a `.pre-commit-config.yaml` with a doxygen-guard hook.
    @return The config path.
    @version 1
    """
    hook = "      - id: doxygen-guard\n"
    if args is not None:
        hook += f"        args: [{', '.join(args)}]\n"
    path = root / ".pre-commit-config.yaml"
    path.write_text(
        "repos:\n  - repo: https://github.com/tvanfossen/doxygen-guard\n    hooks:\n" + hook,
        encoding="utf-8",
    )
    return path


## @brief Build a repo tree with source and vendored directories.
## @param root Repo root to populate.
## @version 1
## @dg_internal
def _write_tree(root: Path) -> None:
    """@brief Create `src/` and `vendor/` with one file each."""
    for name in ("src", "vendor"):
        (root / name).mkdir(parents=True, exist_ok=True)
        (root / name / "a.c").write_text("void a(void) {}\n", encoding="utf-8")


def test_a_config_named_only_by_the_hook_args_is_found(tmp_path: Path) -> None:
    """THE ISSUE'S CENTRAL CASE, and the shape of a real private target: the config
    lives at `conf/doxygen-guard.yaml` and the ONLY statement of that fact is the
    pre-commit hook's own `--config` arg. `precommit.py` was already parsing that
    file for the hook's `files:`/`exclude:` and discarding the rest, so the
    declaration was present and unread."""
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "doxygen-guard.yaml").write_text(_GUARD_CONFIG, encoding="utf-8")
    _write_precommit(tmp_path, ["--config", "conf/doxygen-guard.yaml"])

    location = discover_guard_config(tmp_path)
    assert location.path == tmp_path / "conf" / "doxygen-guard.yaml"
    assert location.source == GUARD_SOURCE_HOOK_ARGS


def test_the_equals_spelling_of_the_config_arg_is_read_too(tmp_path: Path) -> None:
    """`--config=path` as one list item is the same declaration as `--config path` as
    two. A repo choosing the other punctuation is not declaring something else."""
    (tmp_path / "tools").mkdir()
    (tmp_path / "tools" / "dg.yaml").write_text(_GUARD_CONFIG, encoding="utf-8")
    _write_precommit(tmp_path, ["--config=tools/dg.yaml"])

    assert discover_guard_config(tmp_path).path == tmp_path / "tools" / "dg.yaml"


def test_a_hook_declared_scope_beats_the_whole_repo_fallback(tmp_path: Path) -> None:
    """THE REGRESSION THAT MATTERS, asserted on the SCOPE rather than on discovery.

    The repo declares `index_scope: roots: ['src']` inside the passthrough of a config
    that only its hook args name. Before gh#16 the passthrough was read from the repo
    root alone, so this declaration was invisible: `_declared_index_scope` returned
    None, the hook's filter-free scope swept the tree, and `vendor/` — which the same
    config excludes — was handed to doxygen. A successful build of the wrong tree."""
    _write_tree(tmp_path)
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "doxygen-guard.yaml").write_text(_GUARD_CONFIG, encoding="utf-8")
    _write_precommit(tmp_path, ["--config", "conf/doxygen-guard.yaml"])

    scope = derive_scope(tmp_path)
    assert scope.source == SOURCE_DECLARED, (
        f"the declared index_scope must win, got {scope.source}: {scope.reason}"
    )
    assert scope.roots == (tmp_path / "src",)
    assert tmp_path / "vendor" not in scope.roots


def test_an_explicit_path_overrides_every_discovery_step(tmp_path: Path) -> None:
    """`--guard-config` used to reach the requirement-tag pattern and NOT the
    passthrough, so a repo passing it got two halves of one config from two different
    files. It must now override all consumers — including this one."""
    elsewhere = tmp_path / "elsewhere.yaml"
    elsewhere.write_text(_GUARD_CONFIG, encoding="utf-8")
    (tmp_path / ".doxygen-guard.yaml").write_text("validate:\n  exclude: []\n", encoding="utf-8")

    location = discover_guard_config(tmp_path, elsewhere)
    assert location.source == GUARD_SOURCE_EXPLICIT
    assert location.path == elsewhere
    assert load_declaration(tmp_path, elsewhere).get("index_scope") == {"roots": ["src"]}


def test_the_repo_root_still_wins_when_it_has_a_config(tmp_path: Path) -> None:
    """A control on the discovery ORDER: an unambiguous root config needs no
    declaration to be believed, and adding later steps must not demote it."""
    (tmp_path / ".doxygen-guard.yaml").write_text(_GUARD_CONFIG, encoding="utf-8")
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "doxygen-guard.yaml").write_text("validate:\n", encoding="utf-8")

    location = discover_guard_config(tmp_path)
    assert location.source == GUARD_SOURCE_ROOT
    assert location.path == tmp_path / ".doxygen-guard.yaml"


def test_a_conventional_directory_is_searched_with_no_declaration_at_all(
    tmp_path: Path,
) -> None:
    """A repo with no pre-commit config that still keeps a guard config in `config/`
    is a plain convention lookup, and the last resort precisely because it is the only
    step that can be ambiguous."""
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "doxygen-guard.yaml").write_text(_GUARD_CONFIG, encoding="utf-8")

    location = discover_guard_config(tmp_path)
    assert location.source == GUARD_SOURCE_CONVENTIONAL


def test_ambiguity_is_refused_not_resolved_by_ordering(tmp_path: Path, caplog) -> None:
    """REFUSES TO GUESS, following `discover_doxyfile`. That function once resolved
    strays alphabetically and was caught choosing a TEST FIXTURE's Doxyfile to index a
    whole project; a wrong guard config is the same class of error, silently supplying
    someone else's id pattern, catalog mapping and declaration. The fallback here
    (built-in defaults, reported) is a known quantity, so guessing buys nothing."""
    for directory in ("conf", "config"):
        (tmp_path / directory).mkdir()
        (tmp_path / directory / "doxygen-guard.yaml").write_text(_GUARD_CONFIG, encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        location = discover_guard_config(tmp_path)

    assert location.path is None, "two candidates must not resolve to one by ordering"
    assert location.source == GUARD_SOURCE_NONE
    assert "NOT guessing" in caplog.text
    assert "conf/doxygen-guard.yaml" in caplog.text
    assert "config/doxygen-guard.yaml" in caplog.text


def test_not_found_is_loud_and_names_every_location_searched(tmp_path: Path, caplog) -> None:
    """The silent fallback IS the defect. A build that runs on built-in defaults for
    the id pattern, the catalog mapping and the whole declaration passthrough must say
    so, and must name where it looked — otherwise "this repo declares nothing" and "we
    looked in the wrong place" are the same output."""
    with caplog.at_level(logging.WARNING):
        location = discover_guard_config_logged(tmp_path)

    assert location.path is None
    assert "guard config: none found" in caplog.text
    for expected in (".doxygen-guard.yaml", ".pre-commit-config.yaml", "conf", "config"):
        assert expected in caplog.text, f"the search report must name {expected}"


def test_a_found_config_is_reported_with_its_provenance(tmp_path: Path, caplog) -> None:
    """The success path must be as legible as the failure path: WHICH config, and HOW
    it was found. A build log that names only the path cannot distinguish a declared
    location from a lucky convention hit."""
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "doxygen-guard.yaml").write_text(_GUARD_CONFIG, encoding="utf-8")
    _write_precommit(tmp_path, ["--config", "conf/doxygen-guard.yaml"])

    with caplog.at_level(logging.INFO):
        discover_guard_config_logged(tmp_path)

    assert "guard config: using" in caplog.text
    assert GUARD_SOURCE_HOOK_ARGS in caplog.text


def test_a_declared_path_that_does_not_exist_is_reported(tmp_path: Path, caplog) -> None:
    """The repo SAYS its config is there. Its absence is a fact the owner wants — a
    typo in the hook args, or a config deleted without updating it — not a reason to
    fall through quietly to a convention lookup."""
    _write_precommit(tmp_path, ["--config", "conf/gone.yaml"])

    with caplog.at_level(logging.WARNING):
        location = discover_guard_config(tmp_path)

    assert location.path is None
    assert "conf/gone.yaml" in caplog.text
    assert "does not exist" in caplog.text


def test_the_scope_fallback_reason_names_the_guard_config_search(tmp_path: Path, caplog) -> None:
    """`--scope from-guard` finding no declaration must SAY SO AND NAME WHERE IT
    LOOKED, before falling back. The warning used to name the pre-commit file only, so
    a repo whose config was somewhere unsearched got a message that pointed at the
    wrong file."""
    _write_tree(tmp_path)

    with caplog.at_level(logging.WARNING):
        scope = derive_scope_logged(tmp_path)

    assert not scope.is_derived()
    ## gh#333 changed the SENTENCE (the old one named a Doxyfile tier that no longer
    ## exists) and kept the LEVEL and the CLAUSE. The clause is what gh#16 is about:
    ## without it, "this repo declares no scope" and "we looked in the wrong place
    ## for its config" produce the same message.
    assert "WHOLE repository" in caplog.text
    assert any(rec.levelname == "WARNING" for rec in caplog.records)
    assert "no doxygen-guard config was found" in scope.reason
    assert ".doxygen-guard.yaml" in scope.reason


def test_a_found_config_that_cannot_scope_says_why(tmp_path: Path, caplog) -> None:
    """A config found and a scope still not derived is not a contradiction, and the
    message must not read like one: the `x-clew` passthrough is optional, so a
    guard config can be present, valid, and silent about the index. Naming the found
    config points the owner at the section to add rather than at the file they can
    already see is there."""
    _write_tree(tmp_path)
    (tmp_path / "conf").mkdir()
    (tmp_path / "conf" / "doxygen-guard.yaml").write_text(
        "validate:\n  exclude:\n    - '^vendor/'\n", encoding="utf-8"
    )
    _write_precommit(tmp_path, ["--config", "conf/doxygen-guard.yaml"])
    (tmp_path / ".pre-commit-config.yaml").write_text("repos: []\n", encoding="utf-8")

    with caplog.at_level(logging.WARNING):
        scope = derive_scope_logged(tmp_path)

    assert not scope.is_derived()
    assert "WAS found at" in scope.reason
    assert f"carries no {INDEX_SCOPE_SECTION}" in scope.reason
