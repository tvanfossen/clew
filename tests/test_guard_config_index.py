# SPDX-License-Identifier: MIT
"""The gate's config is the `guard:` section of `.clew.yaml`, read by gate and index alike.

One file, two severities: the gate refuses an invalid section, the index warns and runs on
its defaults. `.doxygen-guard.yaml` is not read at all — the move was a hard break, and the
last test pins that so a fallback cannot creep back in unannounced.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from clew.declaration import describe_declaration, load_declaration
from clew.guard.config import CONFIG_FILE_NAME, CONFIG_SECTION, load_config
from clew.guard.contract import build_schema_contract
from clew.guard.errors import ConfigError
from clew.requirements import load_guard_config, resolve_req_id_pattern
from clew.scope import derive_scope

_GUARD = """\
guard:
  validate:
    tags:
      req:
        pattern: "^REQ-[0-9]{4}$"
  impact:
    requirements:
      file: catalog.yaml
"""


def _write(root: Path, text: str, name: str = CONFIG_FILE_NAME) -> Path:
    path = root / name
    path.write_text(text, encoding="utf-8")
    return path


def test_the_index_reads_the_guard_section_of_clew_yaml(tmp_path: Path) -> None:
    _write(tmp_path, _GUARD)

    cfg = load_guard_config(tmp_path)

    assert cfg is not None
    assert cfg["impact"]["requirements"]["file"] == "catalog.yaml"
    assert resolve_req_id_pattern(cfg).pattern == "^REQ-[0-9]{4}$"


def test_the_gate_reads_the_same_section(tmp_path: Path) -> None:
    path = _write(tmp_path, _GUARD)

    cfg = load_config(path)

    assert cfg["validate"]["tags"]["req"]["pattern"] == "^REQ-[0-9]{4}$"
    assert cfg["impact"]["requirements"]["file"] == "catalog.yaml"


def test_no_file_and_no_section_both_mean_nothing_declared(tmp_path: Path) -> None:
    assert load_guard_config(tmp_path) is None

    _write(tmp_path, "index_scope:\n  roots: [src]\n")
    assert load_guard_config(tmp_path) is None, (
        "a .clew.yaml with no guard: section declares nothing to the gate"
    )


def test_an_invalid_section_degrades_the_index_and_is_refused_by_the_gate(
    tmp_path: Path, caplog
) -> None:
    path = _write(tmp_path, "guard:\n  validate:\n    no_such_key: 1\n")

    with caplog.at_level(logging.WARNING):
        assert load_guard_config(tmp_path) is None
    assert str(path) in caplog.text and "no_such_key" in caplog.text, (
        "the index must say which file it could not use and why, not fall back silently"
    )
    with pytest.raises(ConfigError):
        load_config(path)


def test_a_guard_section_that_is_not_a_mapping_is_refused_by_the_gate(tmp_path: Path) -> None:
    path = _write(tmp_path, "guard: [validate]\n")

    with pytest.raises(ConfigError):
        load_config(path)
    assert load_guard_config(tmp_path) is None


def test_the_guard_section_is_known_but_is_not_an_index_declaration(tmp_path: Path) -> None:
    _write(tmp_path, _GUARD + "index_scope:\n  roots: [src]\n")
    (tmp_path / "src").mkdir()

    assert load_declaration(tmp_path) == {"index_scope": {"roots": ["src"]}}

    _write(tmp_path, _GUARD)
    assert load_declaration(tmp_path) == {}, (
        "a file that configures only the gate must declare nothing to the index"
    )
    assert "configures only the gate" in describe_declaration(tmp_path)


def test_the_scope_fallback_names_where_it_looked(tmp_path: Path) -> None:
    reason = derive_scope(tmp_path).reason
    assert f"no {CONFIG_FILE_NAME} was found" in reason

    _write(tmp_path, _GUARD)
    reason = derive_scope(tmp_path).reason
    assert "exists but carries no index_scope" in reason


def test_the_schema_contract_names_the_file_and_section() -> None:
    contract = build_schema_contract()

    assert contract["config_file"] == CONFIG_FILE_NAME
    assert contract["config_section"] == CONFIG_SECTION
    assert "passthrough_prefix" not in contract


def test_a_leftover_doxygen_guard_yaml_is_not_read(tmp_path: Path) -> None:
    """HARD BREAK, pinned. A repo that has not moved its config runs on the defaults; a
    silent fallback to the old file would leave two configs that can disagree."""
    old = _GUARD.replace("guard:\n", "").replace("\n  ", "\n")
    _write(tmp_path, old + "x-clew:\n  index_scope:\n    roots: [src]\n", ".doxygen-guard.yaml")

    assert load_guard_config(tmp_path) is None
    assert load_declaration(tmp_path) == {}
