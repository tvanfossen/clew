# SPDX-License-Identifier: MIT
"""A Doxyfile alias that rewrites `@req` is named, never silent (#72 bug 2, 2.1).

FOUND BY AN ADOPTER (#72, 2026-11-23): `ALIASES = "req=@par Requirement:^^"` makes doxygen rewrite
every `@req` before clew reads it; the index reported `req_edges: 0` while 196 distinct ids were
tagged, and every requirement read MISSING, with nothing saying why.

@brief Tests the redefined-tag warning.
@version 1
"""

from __future__ import annotations

import logging
from pathlib import Path

from clew.requirements import redefined_clew_tags, warn_redefined_tags


def test_an_alias_redefining_a_clew_tag_is_found(tmp_path: Path) -> None:
    """@brief `=`, `+=`, quoted entries and continuation lines are all read."""
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text(
        "PROJECT_NAME = x\n"
        'ALIASES = "req=@par Requirement:^^" \\\n'
        '          "foo=@b bar"\n'
        'ALIASES += "utility=@internal"\n'
    )
    assert redefined_clew_tags(doxyfile) == {"req": "@par Requirement:^^", "utility": "@internal"}


def test_no_alias_or_no_doxyfile_finds_nothing(tmp_path: Path) -> None:
    """@brief A synthesised Doxyfile, or none at all, is a correct negative."""
    plain = tmp_path / "Doxyfile"
    plain.write_text('ALIASES = "emits=@xrefitem evt_emits \\"Emits\\" \\"Events\\""\n')
    assert redefined_clew_tags(plain) == {}
    assert redefined_clew_tags(tmp_path / "missing") == {}


def test_the_index_build_warns_naming_the_alias(tmp_path: Path, caplog) -> None:  # noqa: ANN001
    """@brief The warning names the tag, the alias and what it costs."""
    doxyfile = tmp_path / "Doxyfile"
    doxyfile.write_text('ALIASES = "req=@par Requirement:^^"\n')
    with caplog.at_level(logging.WARNING):
        warn_redefined_tags(doxyfile)
    assert "req=@par Requirement:^^" in caplog.text and "requirement edge" in caplog.text


def test_building_an_index_over_such_a_doxyfile_warns(tmp_path: Path, caplog) -> None:  # noqa: ANN001
    """@brief The real pipeline says it, at the requirement-edge stage."""
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.c").write_text("/** @brief Go. @req REQ-X-001 */\nint go(void) { return 1; }\n")
    (repo / "Doxyfile").write_text(
        'INPUT = .\nFILE_PATTERNS = *.c\nALIASES = "req=@par Requirement:^^"\n'
    )
    with caplog.at_level(logging.WARNING):
        _run_pipeline(
            _build_argparser().parse_args(
                ["--output", str(tmp_path / "x.db"), "--repo-root", str(repo)]
            )
        )
    assert "req=@par Requirement:^^" in caplog.text
