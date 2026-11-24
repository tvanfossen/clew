# SPDX-License-Identifier: MIT
"""Coverage through pinned dependencies, opt-in (#73 item 2, 2.1).

#73 (an adopter, 2026-11-23): in a product repository, a system requirement realised only by a
module's requirement (whose `satisfies` points at it) read UNCOVERED, even when that module
implemented it at the pin; the only way through was an exempt status that hid the real trace.
Owner Q/A 2026-11-24: an opt-in `guard.coverage.through_dependencies` — covered when a pinned
dependency's satisfying requirement is implemented (its code tags it at the pin) or exempt,
reported as "covered via <catalog>:<id>". Off by default.

@brief Tests dependency coverage.
@version 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from clew.guard.config import load_config
from clew.guard.coverage import analyze_coverage


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
        cwd=path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _setup(tmp_path: Path, through: bool) -> Path:
    lib = tmp_path / "lib"
    (lib / "src").mkdir(parents=True)
    (lib / "requirements.yaml").write_text(
        "requirements:\n"
        "  REQ-LIB-001:\n    name: Retry\n    satisfies: [product:REQ-PRD-001]\n"
        "  REQ-LIB-002:\n    name: Report\n    satisfies: [product:REQ-PRD-002]\n"
        "  REQ-LIB-003:\n    name: Later\n    status: planned\n    satisfies: [product:REQ-PRD-003]\n"
    )
    (lib / "src" / "retry.c").write_text(
        "/** @brief Retry. @req REQ-LIB-001 */\nint retry(void);\n"
    )
    _git(lib, "init", "-q")
    _git(lib, "add", "-A")
    _git(lib, "commit", "-qm", "c")
    rev = _git(lib, "rev-parse", "HEAD")
    product = tmp_path / "product"
    (product / "src").mkdir(parents=True)
    (product / "src" / "main.c").write_text("int main(void) { return 0; }\n")
    (product / "requirements.yaml").write_text(
        "requirements:\n  REQ-PRD-001:\n    name: A\n  REQ-PRD-002:\n    name: B\n  REQ-PRD-003:\n    name: C\n"
    )
    coverage = "  coverage:\n    through_dependencies: true\n" if through else ""
    (product / ".clew.yaml").write_text(
        "requirements:\n  file: requirements.yaml\n  exempt_status: [planned]\n  external:\n"
        f"    - {{name: lib, repo: ../lib, rev: {rev}, path: requirements.yaml}}\n"
        f"guard:\n{coverage or '  validate: {}'}\n"
    )
    return product


def test_a_requirement_implemented_by_a_dependency_at_its_pin_is_covered_via_it(
    tmp_path, monkeypatch
) -> None:  # noqa: ANN001
    """@brief Tagged at the pin → covered via; exempt by this repo's rules → covered via; else uncovered."""
    product = _setup(tmp_path, through=True)
    monkeypatch.chdir(product)
    report = analyze_coverage(["src"], load_config(product / ".clew.yaml"))
    assert report["covered_via"] == [
        {"req_id": "REQ-PRD-001", "via": "lib:REQ-LIB-001", "how": "implemented"},
        {"req_id": "REQ-PRD-003", "via": "lib:REQ-LIB-003", "how": "exempt"},
    ]
    assert report["uncovered"] == ["REQ-PRD-002"]


def test_off_by_default_nothing_changes(tmp_path, monkeypatch) -> None:  # noqa: ANN001
    """@brief Without the option every one stays uncovered, and `covered_via` is absent."""
    product = _setup(tmp_path, through=False)
    monkeypatch.chdir(product)
    report = analyze_coverage(["src"], load_config(product / ".clew.yaml"))
    assert "covered_via" not in report
    assert report["uncovered"] == ["REQ-PRD-001", "REQ-PRD-002", "REQ-PRD-003"]


def test_the_reports_say_which_dependency_covered_it() -> None:
    """@brief Text and Markdown list each "via"; neither mentions it when the option is off."""
    from clew.guard.coverage import format_coverage_markdown, format_coverage_text

    base = {
        "covered": [],
        "total_requirements": 2,
        "uncovered": ["REQ-B"],
        "exempt": [],
        "orphan_refs": [],
        "unmapped_functions": [],
        "traceability": None,
    }
    via = {**base, "covered_via": [{"req_id": "REQ-A", "via": "lib:REQ-L-1", "how": "implemented"}]}
    assert "REQ-A via lib:REQ-L-1 (implemented)" in format_coverage_text(via)
    assert "- REQ-A via lib:REQ-L-1 (implemented)" in format_coverage_markdown(via)
    assert "via" not in format_coverage_text(base) and "via" not in format_coverage_markdown(base)
