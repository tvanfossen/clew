# SPDX-License-Identifier: MIT
"""A documented declaration's doc block is checked like a definition's (PG2; 2.0.0).

FOUND BY A CONSUMER (the entropic session), reproduced: a header prototype whose doc block
carried `@req REQ-NOPE-999` passed `clew guard validate` (rc 0) while the same tag on a function
with a body was refused. The gate collected only nodes with a body, so a header doc block, where a C
library documents its API, was never read. entropic once carried a dead requirement in a header
for a long time this way.

OWNER (2026-11-19): a declaration and its definition are ONE function, and presence rules apply
wherever the block is. THE GATE RUNS PER FILE, so it cannot see a header and its `.c` together
when only one is staged. Hence:
  * a declaration WITH a doc block has that block checked: @brief / @version presence, @return,
    `@req` existence, unknown and removed tags, and @version staleness of its own text;
  * a declaration WITHOUT one is skipped: its definition carries the documentation, as before;
  * the per-function "needs @req or an exemption" rule stays with definitions, so a header does
    not need its `@req` written twice. `clew guard coverage`, which reads the whole tree, counts a
    tag on either side.

@brief Tests declaration doc blocks in the gate.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.config import CONFIG_DEFAULTS, deep_merge
from clew.guard.main import validate_file

_CATALOG = "requirements:\n  REQ-REAL-001:\n    name: real\n"
_FILE_BLOCK = "/**\n * @file {name}\n * @brief B.\n * @version 1.0\n */\n\n"


@pytest.fixture()
def config(tmp_path: Path) -> dict:
    """@brief A gate config with a catalog. @return Config."""
    catalog = tmp_path / "requirements.yaml"
    catalog.write_text(_CATALOG)
    return deep_merge(CONFIG_DEFAULTS, {"requirements": {"file": str(catalog), "format": "yaml"}})


def _check(tmp_path: Path, config: dict, name: str, body: str) -> list[str]:
    """@brief Validate one file. @return Messages."""
    path = tmp_path / name
    path.write_text(_FILE_BLOCK.format(name=name) + body)
    return [
        v.message for v in validate_file(str(path), config, no_git=True, req_ids={"REQ-REAL-001"})
    ]


def test_a_dead_req_on_a_documented_declaration_is_refused(tmp_path: Path, config: dict) -> None:
    """@brief The entropic case: a header prototype's dead @req."""
    found = _check(
        tmp_path,
        config,
        "api.h",
        "/**\n * @brief Open.\n * @version 1.0\n * @req REQ-NOPE-999\n * @return x.\n */\nint api_open(int x);\n",
    )
    assert any("REQ-NOPE-999" in m and "api_open" in m for m in found), found


def test_a_documented_declaration_needs_its_version(tmp_path: Path, config: dict) -> None:
    """@brief Presence rules apply wherever the block is."""
    found = _check(
        tmp_path,
        config,
        "api.h",
        "/**\n * @brief Open.\n * @return x.\n */\nint api_open(int x);\n",
    )
    assert any("api_open" in m and "@version" in m for m in found), found


def test_an_undocumented_declaration_is_not_a_finding(tmp_path: Path, config: dict) -> None:
    """@brief Its definition carries the documentation."""
    assert _check(tmp_path, config, "api.h", "int api_open(int x);\n") == []


def test_a_declaration_does_not_need_its_own_req(tmp_path: Path, config: dict) -> None:
    """@brief The @req-or-exemption obligation stays with the definition."""
    found = _check(
        tmp_path,
        config,
        "api.h",
        "/**\n * @brief Open.\n * @version 1.0\n * @return x.\n */\nint api_open(int x);\n",
    )
    assert found == [], found


def test_a_cpp_member_declaration_is_checked_too(tmp_path: Path, config: dict) -> None:
    """@brief An in-class prototype is a declaration like a free one."""
    found = _check(
        tmp_path,
        config,
        "bridge.hpp",
        "class Bridge {\npublic:\n    /**\n     * @brief Send.\n     * @version 1.0\n     * @req REQ-NOPE-999\n"
        "     * @return n.\n     */\n    int send(int n);\n};\n",
    )
    assert any("REQ-NOPE-999" in m and "send" in m for m in found), found


def test_coverage_treats_a_declaration_and_its_definition_as_one(
    tmp_path: Path, config: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief A documented header prototype without @req, whose definition has one, is not unmapped."""
    from clew.guard.coverage import analyze_coverage

    ## The coverage path keeps the catalog inside the repository: run from it, catalog relative.
    monkeypatch.chdir(tmp_path)
    config = deep_merge(config, {"requirements": {"file": "requirements.yaml"}})

    (tmp_path / "api.h").write_text(
        _FILE_BLOCK.format(name="api.h")
        + "/**\n * @brief Open.\n * @version 1.0\n * @return x.\n */\nint api_open(int x);\n"
    )
    (tmp_path / "api.c").write_text(
        _FILE_BLOCK.format(name="api.c")
        + "/**\n * @brief Open.\n * @version 1.0\n * @req REQ-REAL-001\n * @return x.\n */\nint api_open(int x) { return x; }\n"
    )
    report = analyze_coverage(["."], config)
    assert "api_open" not in report["unmapped_functions"]
    assert "REQ-REAL-001" in report["covered"]
