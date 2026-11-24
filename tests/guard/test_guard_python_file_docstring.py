# SPDX-License-Identifier: MIT
"""A Python module docstring is read whole as the file block (2.1).

FOUND BY AN ADOPTER (glyph-animator, 2026-11-23, adopting clew-guard v2.0.1): with
`presence.require_file_doxygen`, a module docstring whose tags follow a blank line —

    \"\"\"Summary.

    @file x.py
    @brief ...
    @version 1.0
    \"\"\"

— was read only to its first blank line, so @file / @brief / @version were reported missing. GUARD.md's
Python section says PEP 257 leads: the docstring IS the block.

@brief Tests the Python file-docstring block.
@version 1
"""

from __future__ import annotations

from clew.guard.checks import check_file_presence

_CONFIG = {"validate": {"presence": {"require_file_doxygen": True}}}


def test_tags_after_a_blank_line_in_a_module_docstring_count() -> None:
    """@brief The block runs to the closing quotes."""
    source = '"""Summary.\n\n@file x.py\n@brief Does x.\n@version 1.0\n"""\n\nimport os\n'
    assert check_file_presence("x.py", source, _CONFIG) == []


def test_a_docstring_missing_a_tag_is_still_reported() -> None:
    """@brief Reading the whole docstring must not make the check vacuous."""
    source = '"""Summary.\n\n@file x.py\n@brief Does x.\n"""\n'
    messages = [v.message for v in check_file_presence("x.py", source, _CONFIG)]
    assert messages == ["File-level doxygen missing @version tag in 'x.py'"]


def test_a_one_line_docstring_is_one_block() -> None:
    """@brief Opened and closed on one line."""
    source = '"""@file x.py @brief Does x. @version 1"""\nimport os\n'
    assert check_file_presence("x.py", source, _CONFIG) == []
