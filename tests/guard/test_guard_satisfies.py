# SPDX-License-Identifier: MIT
"""The gate refuses a `satisfies` id no catalogue holds (GH #68, P6b-2).

A catalogue entry's `satisfies:` names requirements this one serves — in this catalogue, in an
external one (`impact.requirements.external`), or spelled `<catalog>:<id>`. An id that resolves to
none of them is a broken link in the requirement tree and is refused, naming it.

@brief Tests for the gate's satisfies check.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.main import main
from guard_helpers import guard_yaml

_SOURCE = "/**\n * @brief Send once.\n * @req REQ-LIB-001\n * @version 1.0\n */\nvoid f(void) {}\n"  # void: @return is not what these tests check


def _guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, catalog: str, external: str = ""
) -> int:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "requirements.yaml").write_text(catalog)
    (tmp_path / "f.c").write_text(_SOURCE)
    cfg = tmp_path / "guard.yaml"
    ## FIXTURE CHANGED (2.0.0, R5-CFG F7): the catalog is the top-level `requirements:`.
    lifted = "".join(line[2:] + "\n" for line in external.splitlines())
    cfg.write_text("requirements:\n  file: requirements.yaml\n" + lifted + guard_yaml(""))
    return main(["--config", str(cfg), "validate", "--no-git", "f.c"])


def test_the_gate_refuses_a_satisfies_id_no_catalogue_holds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """@brief REQ-PRD-404 is in no catalogue: a violation naming it; an external id resolves."""
    broken = "requirements:\n  REQ-LIB-001:\n    name: x\n    satisfies: [REQ-PRD-404]\n"
    assert _guard(tmp_path, monkeypatch, broken) == 1
    out = capsys.readouterr()
    assert "REQ-PRD-404" in out.out + out.err
    (tmp_path / "product").mkdir()
    (tmp_path / "product/requirements.yaml").write_text(
        "requirements:\n  REQ-PRD-404:\n    name: now it exists\n"
    )
    external = "    external: [product/requirements.yaml]\n"
    assert _guard(tmp_path, monkeypatch, broken, external) == 0, capsys.readouterr()


def test_a_namespaced_satisfies_id_resolves_by_its_bare_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief `product:REQ-PRD-001` resolves when an external catalogue holds REQ-PRD-001."""
    (tmp_path / "product").mkdir()
    (tmp_path / "product/requirements.yaml").write_text(
        "requirements:\n  REQ-PRD-001:\n    name: p\n"
    )
    cat = "requirements:\n  REQ-LIB-001:\n    name: x\n    satisfies: product:REQ-PRD-001\n"
    external = "    external: [product/requirements.yaml]\n"
    assert _guard(tmp_path, monkeypatch, cat, external) == 0
