# SPDX-License-Identifier: MIT
"""A repo still carrying `.doxygen-guard.yaml` is told so, rather than silently defaulted.

Group B, 1.1.0 MERGE REVIEW. doxygen-guard's config was its own `.doxygen-guard.yaml`; clew
reads the `guard:` section of `.clew.yaml` and does not read the old file at all. Both sides
of that are right — a one-file config is the point of the absorption — but the transition has
no signpost: a repository that upgrades keeps a `.doxygen-guard.yaml` that is now inert, the
gate runs on built-in defaults, and everything LOOKS fine. The `@req` gate in particular goes
from enforced to absent with no output, which is the same class of silent-success failure as
B1 and the unconfigured-language skip.

SIGNPOSTED, NOT SUPPORTED, was the 1.1.0 rule: a warning, and only while no `guard:` section
existed. 2.0.0 REPLACES IT (owner, 2026-11-19: "a hard cut of doxygen-guard priors — clew only"):
the GATE REFUSES to run while the leftover exists, migrated or not, naming it and the fix — a
stale config a contributor reads states rules the gate does not enforce. The INDEX still only
warns: it indexes repositories it must not change. tests/guard/test_guard_hard_cut.py covers the
hook-id half.

@brief The legacy doxygen-guard config is refused by the gate and named by the index.
@version 2
"""

from __future__ import annotations

import logging

import pytest

from clew.guard.config import LEGACY_CONFIG_NAME, load_config
from clew.guard.errors import ConfigError


def test_a_legacy_config_with_no_guard_section_is_refused(tmp_path, monkeypatch):
    """@brief No `guard:` section and the old file present: refused, naming the file and `guard:`."""
    (tmp_path / LEGACY_CONFIG_NAME).write_text("validate:\n  presence:\n    require_brief: true\n")
    ## FIXTURE CHANGED (2.0.0, R5-CFG F1): `thread_patterns: [worker]` was never read (a list
    ## under a mapping section) and is now refused; these tests only need a non-gate section.
    (tmp_path / ".clew.yaml").write_text("thread_patterns:\n  spawns:\n    - {name: worker}\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError) as refused:
        load_config()
    assert LEGACY_CONFIG_NAME in refused.value.details() and "guard:" in refused.value.details()


def test_a_migrated_repo_with_the_leftover_is_refused_too(tmp_path, monkeypatch):
    """1.1.0 deliberately did NOT warn here ("not nagged on every commit"). 2.0.0 reverses it: a
    leftover beside a migrated `guard:` section is still a file a contributor reads and believes,
    and a refusal cannot be learned-to-ignore the way a repeated warning can — it is deleted once.

    @brief A `guard:` section does not excuse the leftover. @version 2
    """
    (tmp_path / LEGACY_CONFIG_NAME).write_text("validate: {}\n")
    (tmp_path / ".clew.yaml").write_text("guard:\n  validate:\n    exclude: []\n")
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ConfigError):
        load_config()


def test_no_legacy_file_means_no_warning(tmp_path, monkeypatch, caplog):
    """@brief A repo that never used doxygen-guard sees nothing. @version 1"""
    (tmp_path / ".clew.yaml").write_text("thread_patterns:\n  spawns:\n    - {name: worker}\n")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING, logger="clew.guard.config"):
        load_config()

    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


def test_the_index_warns_too(tmp_path, caplog):
    """BOTH SIDES, because the index reads the gate's config as well: the `@req` id pattern
    and the requirements catalog come from `guard:`, so a repository with an inert legacy file
    has its requirement LINKS defaulted in the graph for the same reason its gate stopped
    enforcing them. An owner who only ever runs `clew index` would otherwise never see the
    warning at all.

    The gate's own helper is reused rather than copied — `clew/declaration.py` already imports
    the gate's config module for the section name — so the two sides cannot describe the
    migration differently.

    @brief `load_declaration` names the legacy file too. @version 1
    """
    from clew.declaration import load_declaration

    (tmp_path / LEGACY_CONFIG_NAME).write_text("validate: {}\n")
    (tmp_path / ".clew.yaml").write_text("thread_patterns:\n  spawns:\n    - {name: worker}\n")

    with caplog.at_level(logging.WARNING):
        load_declaration(tmp_path)

    assert LEGACY_CONFIG_NAME in " ".join(r.getMessage() for r in caplog.records)
