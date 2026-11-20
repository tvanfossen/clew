# SPDX-License-Identifier: MIT
"""The covered command line cannot change unnoticed (PS2, owner Q/A 2026-11-19).

`docs/OVERVIEW.md` listed the `clew` verbs and flags as covered, and nothing checked it; PS2 adds
`clew guard` and `clew wiki`, which pre-commit and CI call. `docs/cli-surface.json` is generated from
the parsers (`clew.cli_surface`) and compared here, the way `docs/wire-keys.json` is.

@brief Tests the committed CLI surface.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path


def test_the_committed_cli_surface_is_current() -> None:
    """A REMOVED OR RENAMED verb or flag fails here and is a major bump; an ADDED one is additive
    — regenerate.

    @brief docs/cli-surface.json equals the generated surface.
    """
    from clew.cli_surface import cli_surface

    committed = json.loads((Path(__file__).parent.parent / "docs" / "cli-surface.json").read_text())
    assert committed == cli_surface(), (
        "the covered CLI changed — regenerate with "
        "`.venv/bin/python -m clew.cli_surface > docs/cli-surface.json`; a removed or renamed "
        "verb or flag is a major bump"
    )


def test_the_gate_and_wiki_verbs_are_covered() -> None:
    """@brief PS2: `clew guard` and `clew wiki` and their subcommands are in the surface."""
    from clew.cli_surface import cli_surface

    surface = cli_surface()
    assert {"validate", "impact", "coverage"} <= set(surface["clew guard"]["subcommands"])
    assert {"build", "check", "flow"} <= set(surface["clew wiki"]["subcommands"])
    assert "--format" in surface["clew guard"]["subcommands"]["validate"]["options"]
