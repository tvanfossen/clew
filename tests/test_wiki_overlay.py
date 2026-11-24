# SPDX-License-Identifier: MIT
"""`--wiki-config`: an organisation's wiki settings layered over a repository's own (#73 item 5).

#73 (an adopter, 2026-11-23): `--config <file>` REPLACES the whole `.clew.yaml` — requirements,
tests and wiki all read from that file — so applying one organisation-wide theme in CI meant
generating a merged copy of every repository's `.clew.yaml`. Owner Q/A 2026-11-23: in 2.1.

@brief Tests the wiki-config overlay.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.wiki.config import load_wiki_config, wiki_overlay


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".clew.yaml").write_text(
        "wiki:\n  title: Mine\n  theme:\n    palette: {accent: '#111111', ink: '#222222'}\n"
        "tests:\n  junit: [build/junit.xml]\n"
    )
    return repo


def test_the_overlay_merges_over_the_repositorys_wiki_section(tmp_path: Path) -> None:
    """@brief Mappings merge key by key; the repository's other sections are untouched."""
    repo = _repo(tmp_path)
    overlay = tmp_path / "org.yaml"
    overlay.write_text("wiki:\n  theme:\n    palette: {accent: '#0969da'}\n")
    with wiki_overlay(overlay):
        config, problems = load_wiki_config(repo)
    assert not problems, problems
    palette = dict(config.theme.palette)
    assert palette["acc"] == "#0969da" and palette["ink"] == "#222222"
    assert config.title == "Mine" and config.junit == ("build/junit.xml",)


def test_without_an_overlay_nothing_changes(tmp_path: Path) -> None:
    """@brief The overlay applies only inside its context."""
    repo = _repo(tmp_path)
    overlay = tmp_path / "org.yaml"
    overlay.write_text("wiki:\n  title: Org\n")
    with wiki_overlay(overlay):
        assert load_wiki_config(repo)[0].title == "Org"
    assert load_wiki_config(repo)[0].title == "Mine"


def test_an_overlay_carrying_other_sections_is_refused_by_name(tmp_path: Path) -> None:
    """@brief An overlay layers `wiki:` only: requirements and tests stay the repository's."""
    repo = _repo(tmp_path)
    overlay = tmp_path / "org.yaml"
    overlay.write_text("wiki:\n  title: Org\ntests:\n  junit: [x.xml]\n")
    with wiki_overlay(overlay):
        _config, problems = load_wiki_config(repo)
    assert any("tests" in p and "wiki:" in p for p in problems), problems


def test_the_cli_takes_wiki_config_on_check_and_build() -> None:
    """@brief `clew wiki check|build --wiki-config <file>`."""
    from clew.wiki.command import _parser

    for verb, extra in (("check", []), ("build", ["--out", "o"])):
        args = _parser().parse_args([verb, *extra, "--wiki-config", "org.yaml"])
        assert args.wiki_config == "org.yaml"
