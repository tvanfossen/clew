# SPDX-License-Identifier: MIT
"""The `wiki:` section reads a value as written (R5-CFG F5/F15/F16/F25, W9, D2).

FOUND BY THE 2.0.0 CONFIG REVIEW (agents A and B, vetted, owner-approved):
- F5: a string where a list belongs was split into characters — `docs: README.md` read
  `R, E, A, D, …` — with no problem reported, while `gcov` and `theme.css` accepted one string.
- F16 / W9: a falsy value became the default — `flows[].depth: 0` read 3, `docs: []` read the
  default docs — while `infer_depth: 0` meant 0.
- F15: `entry_points: 2` held a DEPTH, one letter-group from `entry_patterns` (a list of names).
- F25: palette tokens (`acc`, `accbg`, `rule2`) were internal CSS abbreviations about to become
  semver-covered.
- D2: the default tooling globs named `acceptance/*`, a convention of this repository only.

@brief Tests that wiki config values mean what they say.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.wiki.config import load_wiki_config


def _load(tmp_path: Path, body: str):
    """@brief Load a `wiki:` section. @return (config, problems)."""
    (tmp_path / ".clew.yaml").write_text("wiki:\n" + body, encoding="utf-8")
    return load_wiki_config(tmp_path)


@pytest.mark.parametrize("key", ["docs", "tooling", "adrs"])
def test_one_string_is_a_one_item_list(tmp_path: Path, key: str) -> None:
    """@brief A bare string is one entry, never its characters."""
    config, problems = _load(tmp_path, f"  {key}: README.md\n")
    assert getattr(config, key) == ("README.md",), problems
    assert not problems


def test_a_non_list_value_is_a_problem_not_a_default(tmp_path: Path) -> None:
    """@brief `docs: {a: 1}` is reported."""
    _config, problems = _load(tmp_path, "  docs: {a: 1}\n")
    assert any("wiki.docs" in p for p in problems), problems


def test_an_explicit_empty_list_is_empty(tmp_path: Path) -> None:
    """W9: `docs: []` states "no prose", not "the default prose".

    @brief [] means none.
    """
    config, problems = _load(tmp_path, "  docs: []\n  tooling: []\n")
    assert config.docs == () and config.tooling == (), problems


def test_a_flow_depth_of_zero_is_refused_not_defaulted(tmp_path: Path) -> None:
    """F16: depth 0 draws nothing, so it is a problem — never silently 3.

    @brief depth < 1 is a problem; an omitted depth is 3.
    """
    config, problems = _load(
        tmp_path, "  flows:\n    - {entry: main, depth: 0}\n    - {entry: run}\n"
    )
    assert any("depth" in p for p in problems), problems
    ## The flow is kept at the default depth WITH the problem reported — never silently 3.
    assert [f.depth for f in config.flows] == [3, 3]


def test_entry_points_is_renamed_and_the_old_key_points_at_the_new_one(tmp_path: Path) -> None:
    """F15: `entry_point_depth` says what it holds; `entry_points` is refused with a pointer.

    @brief The depth key is named for what it is.
    """
    config, problems = _load(tmp_path, "  entry_point_depth: 0\n")
    assert config.entry_point_depth == 0 and not problems
    _config, problems = _load(tmp_path, "  entry_points: 2\n")
    assert any("entry_point_depth" in p for p in problems), problems


def test_palette_tokens_are_words_and_the_abbreviations_point_at_them(tmp_path: Path) -> None:
    """F25: a readable token maps onto the theme's CSS variable; an old abbreviation is refused
    naming its replacement.

    @brief Readable palette tokens.
    """
    config, problems = _load(tmp_path, "  theme:\n    palette: {accent: '#123456'}\n")
    assert config.theme.palette == (("acc", "#123456"),) and not problems
    _config, problems = _load(tmp_path, "  theme:\n    palette: {accbg: '#123456'}\n")
    assert any("accent_bg" in p for p in problems), problems


def test_the_default_tooling_names_no_single_repository(tmp_path: Path) -> None:
    """D2: `acceptance/*` is this repository's layout, which it declares for itself.

    @brief Defaults are conventions, not this repo.
    """
    config, _problems = _load(tmp_path, "  title: x\n")
    assert "acceptance/*" not in config.tooling
