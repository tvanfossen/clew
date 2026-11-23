# SPDX-License-Identifier: MIT
"""The checked-in `.clew.yaml` is validated as strictly as a stated option (R5-CFG F1/F4/F5/F26).

FOUND BY THE 2.0.0 CONFIG REVIEW (agent A, vetted 2026-11-17, owner-approved): the repository's own
file — the human's main way to configure clew — was the LEAST validated route. `--declare` and MCP
`options` refused an unknown entry key through `buildoptions.MANIFEST_SCHEMAS`; the same document
in `.clew.yaml` went straight to loaders that read `entry.get(key, default)`, so a misspelled field
silently took its default and the build reported the declaration honoured. Section internals
(`preprocessor`, `kconfig`) were not key-checked at all, a mapping section written as a path string
was silently dropped, and a list section written as one string was iterated character by character.

Each test pairs the refused shape with the accepted one of the same section.

@brief Tests that the in-tree declaration shares one validator with tier-1 options.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.declaration import DeclarationError, load_declaration


def _declare(tmp_path: Path, text: str) -> Path:
    """@brief Write a `.clew.yaml` into a fresh repo root. @return The root."""
    (tmp_path / ".clew.yaml").write_text(text, encoding="utf-8")
    return tmp_path


def test_an_unknown_manifest_entry_key_is_refused_in_tree(tmp_path: Path) -> None:
    """F1: `entry_arg_idx` for `entry_arg_index` keyed a spawn off argument 0 with no word said.

    @brief The in-tree file is checked against MANIFEST_SCHEMAS.
    """
    bad = _declare(tmp_path, "thread_patterns:\n  spawns:\n    - {name: Spawn, entry_arg_idx: 2}\n")
    with pytest.raises(DeclarationError, match="entry_arg_idx"):
        load_declaration(bad)
    (tmp_path / ".clew.yaml").write_text(
        "thread_patterns:\n  spawns:\n    - {name: Spawn, entry_arg_index: 2}\n", encoding="utf-8"
    )
    assert load_declaration(tmp_path)["thread_patterns"]["spawns"][0]["entry_arg_index"] == 2


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ("preprocessor:\n  predefine: [FOO]\n", "predefine"),
        ("kconfig:\n  path: sub/Kconfig\n", "path"),
    ],
)
def test_a_section_document_key_nothing_reads_is_refused(
    tmp_path: Path, text: str, named: str
) -> None:
    """F4 / F2a: `preprocessor: {predefine: [FOO]}` recorded a DECLARED configuration with no
    macros; `kconfig: {path: ...}` (the documented spelling, wrong) was ignored and the root
    Kconfig picked by convention.

    @brief preprocessor and kconfig keys are allow-listed.
    """
    with pytest.raises(DeclarationError, match=repr(named)):
        load_declaration(_declare(tmp_path, text))


def test_the_section_keys_match_what_the_readers_read() -> None:
    """The allow-sets are restated in declaration.py to keep it free of reader imports; this pins
    them to the readers' own constants so the two spellings cannot drift.

    @brief Section allow-sets equal the readers' keys.
    """
    from clew import kconfig, preprocessor
    from clew.declaration import SECTION_KEYS

    assert SECTION_KEYS["preprocessor"] == {
        preprocessor.KEY_PREDEFINED,
        preprocessor.KEY_CONFIG_HEADER,
    }
    assert SECTION_KEYS["kconfig"] == {kconfig.KEY_ROOT}


def test_a_mapping_section_written_as_a_scalar_is_refused(tmp_path: Path) -> None:
    """A path string under `thread_patterns:` was dropped by `section()` (mapping-or-None), so the
    build ran on built-in spawn patterns. In-tree, a manifest section is the document inline.

    @brief A non-mapping manifest section is refused.
    """
    with pytest.raises(DeclarationError, match="thread_patterns"):
        load_declaration(_declare(tmp_path, "thread_patterns: patterns.yaml\n"))


def test_a_list_section_written_as_one_string_is_one_entry(tmp_path: Path) -> None:
    """F5 for the index: `vendored: extern` was iterated as `e, x, t, e, r, n`. A bare string is a
    one-item list (the precedent `gcov` and `theme.css` already set); any other non-list is refused
    rather than warned and ignored (F26).

    @brief A string list section is normalised; a wrong type is refused.
    """
    assert load_declaration(_declare(tmp_path, "vendored: extern\n"))["vendored"] == ["extern"]
    with pytest.raises(DeclarationError, match="entry_patterns"):
        load_declaration(_declare(tmp_path, "entry_patterns: {main: 1}\n"))


def test_a_path_section_must_be_a_string(tmp_path: Path) -> None:
    """F26: `doxyfile: [a, b]` warned and was ignored. A path section is one path.

    @brief A non-string path section is refused.
    """
    with pytest.raises(DeclarationError, match="doxyfile"):
        load_declaration(_declare(tmp_path, "doxyfile: [a, b]\n"))
