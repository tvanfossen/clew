# SPDX-License-Identifier: MIT
"""A repo still carrying `.doxygen-guard.yaml` is told so, rather than silently defaulted.

Group B, 1.1.0 MERGE REVIEW. doxygen-guard's config was its own `.doxygen-guard.yaml`; clew
reads the `guard:` section of `.clew.yaml` and does not read the old file at all. Both sides
of that are right — a one-file config is the point of the absorption — but the transition has
no signpost: a repository that upgrades keeps a `.doxygen-guard.yaml` that is now inert, the
gate runs on built-in defaults, and everything LOOKS fine. The `@req` gate in particular goes
from enforced to absent with no output, which is the same class of silent-success failure as
B1 and the unconfigured-language skip.

SIGNPOSTED, NOT SUPPORTED. clew does not read the legacy file, and nothing here makes it. The
warning fires only when the old file exists AND no `guard:` section does, so a repository that
has migrated and simply not deleted the old file is not nagged on every commit.

@brief The legacy doxygen-guard config is named when it is the likely cause.
@version 1
"""

from __future__ import annotations

import logging

from clew.guard.config import LEGACY_CONFIG_NAME, load_config


def test_a_legacy_config_with_no_guard_section_is_named(tmp_path, monkeypatch, caplog):
    """@brief The old file is named, with the migration. @version 1"""
    (tmp_path / LEGACY_CONFIG_NAME).write_text("validate:\n  presence:\n    require_brief: true\n")
    (tmp_path / ".clew.yaml").write_text("thread_patterns:\n  - worker\n")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING, logger="clew.guard.config"):
        load_config()

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert LEGACY_CONFIG_NAME in messages, (
        f"the gate ran on defaults with an inert legacy config present and said nothing: "
        f"{messages!r}"
    )
    assert "guard:" in messages, "the warning must name what to do, not only what is wrong"


def test_a_migrated_repo_is_not_nagged(tmp_path, monkeypatch, caplog):
    """THE LIMIT. Once a `guard:` section exists the legacy file is explained — the owner has
    migrated and merely not deleted it. Warning then is noise on every commit, which is how an
    owner learns to ignore the channel the warning above needs.

    @brief No warning when a `guard:` section exists. @version 1
    """
    (tmp_path / LEGACY_CONFIG_NAME).write_text("validate: {}\n")
    (tmp_path / ".clew.yaml").write_text("guard:\n  validate:\n    exclude: []\n")
    monkeypatch.chdir(tmp_path)

    with caplog.at_level(logging.WARNING, logger="clew.guard.config"):
        load_config()

    assert LEGACY_CONFIG_NAME not in " ".join(r.getMessage() for r in caplog.records)


def test_no_legacy_file_means_no_warning(tmp_path, monkeypatch, caplog):
    """@brief A repo that never used doxygen-guard sees nothing. @version 1"""
    (tmp_path / ".clew.yaml").write_text("thread_patterns:\n  - worker\n")
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
    (tmp_path / ".clew.yaml").write_text("thread_patterns:\n  - worker\n")

    with caplog.at_level(logging.WARNING):
        load_declaration(tmp_path)

    assert LEGACY_CONFIG_NAME in " ".join(r.getMessage() for r in caplog.records)
