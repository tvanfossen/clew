# SPDX-License-Identifier: MIT
"""One top-level `tests:` section: where the tests are, and the evidence they leave (R5-CFG F20).

FOUND BY THE 2.0.0 CONFIG REVIEW (agent A, vetted; owner ruled the top-level section). Where tests
live was stated twice — `test_paths:` for the index and `wiki.tests.layers` for the site — and the
evidence a test run leaves (JUnit, coverage, per-test contexts) describes the REPOSITORY'S tests,
yet only the wiki could read it. `tests:` holds both; `test_paths` and `wiki.tests` are refused
naming where they went.

@brief Tests the top-level tests section.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.declaration import DeclarationError, load_declaration


def _write(tmp_path: Path, text: str) -> Path:
    """@brief A repo with this `.clew.yaml`. @return Root."""
    (tmp_path / ".clew.yaml").write_text(text, encoding="utf-8")
    return tmp_path


def test_the_index_reads_tests_paths(tmp_path: Path) -> None:
    """@brief `tests.paths` is the index's test scope."""
    from clew.cli import _build_argparser, _test_paths

    root = _write(tmp_path, "tests:\n  paths: ['unittests/*']\n  junit: [build/junit.xml]\n")
    args = _build_argparser().parse_args(["--output", str(tmp_path / "x.db")])
    assert "unittests/*" in _test_paths(args, load_declaration(root)).values


def test_the_wiki_reads_the_same_section(tmp_path: Path) -> None:
    """@brief The wiki's evidence inputs come from top-level `tests:`."""
    from clew.wiki.config import load_wiki_config

    root = _write(
        tmp_path,
        "tests:\n  junit: [build/junit.xml]\n  contexts: .coverage\n  layers: {unit: ['tests/*']}\n",
    )
    config, problems = load_wiki_config(root)
    assert not problems, problems
    assert config.junit == ("build/junit.xml",)
    assert config.inputs.contexts == ".coverage"
    assert config.inputs.layers == (("unit", ("tests/*",)),)


def test_test_paths_is_refused_with_a_pointer(tmp_path: Path) -> None:
    """@brief `test_paths:` moved to `tests.paths`."""
    with pytest.raises(DeclarationError, match=r"tests\.paths"):
        load_declaration(_write(tmp_path, "test_paths: ['t/*']\n"))


def test_wiki_tests_is_refused_with_a_pointer(tmp_path: Path) -> None:
    """@brief `wiki.tests` moved to the top-level `tests:`."""
    from clew.wiki.config import load_wiki_config

    _config, problems = load_wiki_config(_write(tmp_path, "wiki:\n  tests: {junit: [j.xml]}\n"))
    assert any("top-level `tests:`" in p for p in problems), problems


def test_an_unknown_tests_key_is_refused(tmp_path: Path) -> None:
    """@brief A misspelled tests key is refused by name."""
    with pytest.raises(DeclarationError, match="junti"):
        load_declaration(_write(tmp_path, "tests:\n  junti: [j.xml]\n"))


def test_a_stated_tests_option_reaches_the_index(tmp_path: Path) -> None:
    """Tier 1 names the section, as every other option does (the owner's 1:1 ruling).

    @brief `options={"tests": {"paths": [...]}}` is applied.
    """
    from clew.buildoptions import apply_options
    from clew.cli import _build_argparser

    args = _build_argparser().parse_args(["--output", str(tmp_path / "x.db")])
    applied = apply_options(args, {"tests": {"paths": ["spec/*"]}}, tmp_path)
    assert applied == ["tests"]
