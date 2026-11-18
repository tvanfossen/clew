# SPDX-License-Identifier: MIT
"""Every fixture `.clew.yaml` under tests/data is a CURRENT config: the gate and the declaration
loader both accept it (2.0.0).

FOUND WHILE WRITING T1, after P1 reshaped the config. `tests/data/csample/.clew.yaml` still held
`guard.output_dir`, `guard.impact.requirements` and a regex `validate.exclude` entry. All three
are refused since P1, so every build of the fixture logged "INVALID ... continues with built-in
defaults", and the `@req` pattern the fixture exists to DECLARE was no longer read. Nothing failed,
because the built-in default happens to accept the fixture's ids. A fixture whose config is
discarded tests the defaults while claiming to test a declaration.

@brief Fixture configs are valid under the current schema.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.declaration import load_declaration
from clew.guard.config import load_config

_FIXTURES = sorted((Path(__file__).parent / "data").rglob(".clew.yaml"))


def test_there_is_a_fixture_config_to_check() -> None:
    """@brief The glob finds something, so the parametrized test cannot pass on nothing."""
    assert _FIXTURES


@pytest.mark.parametrize("path", _FIXTURES, ids=lambda p: str(p.parent.name))
def test_the_fixture_config_loads_under_the_current_schema(path: Path) -> None:
    """@brief Neither loader refuses it, and the declared @req pattern is the one in force."""
    config = load_config(path)
    load_declaration(path.parent)
    if "csample" in str(path):
        assert config["validate"]["tags"]["req"]["pattern"] == "^REQ-[0-9]{4}$"
