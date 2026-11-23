# SPDX-License-Identifier: MIT
"""The requirement ratio floor, and coverage running from the pre-commit hook (PG3; 2.0.0).

OWNER (2026-11-19, after review): a floor on @req / (@req + exemptions) is the codebase-level
statement that "most code SHOULD be aligned to a requirement". No standard sets a number
(DO-178C, ISO 26262 and IEC 62304 require trace-or-justify), and the measured values differ by
repository (clew about 0.40 by raw tag count, entropic 52.4%), so:

  * `guard.coverage.min_req_ratio` is OFF unless declared; there is no built-in number;
  * ratio = functions with @req / (functions with @req + functions exempt by @utility or
    @callback), over NON-TEST code (the index's test paths), a declaration and its definition
    counted ONCE (by `Class::name(params)`);
  * the counts per tag are printed whether the gate passes or fails, so the trend is visible in
    review above the floor too;
  * it runs from the `clew-guard` pre-commit hook, so coverage (uncovered entries, orphan @req,
    the floor) is never a separate manual step.

@brief Tests the ratio floor and coverage in the hook.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

from clew.guard.main import main

_CATALOG = "requirements:\n  REQ-A-001:\n    name: a\n"
_FILE = "/**\n * @file {name}\n * @brief B.\n * @version 1.0\n */\n\n"
_REQ = "/**\n * @brief {n}.\n * @version 1.0\n * @req REQ-A-001\n */\nvoid {n}(void) {{ }}\n"
_UTIL = "/**\n * @brief {n}.\n * @version 1.0\n * @utility\n */\nvoid {n}(void) {{ }}\n"
_CB = "/**\n * @brief {n}.\n * @version 1.0\n * @callback\n */\nvoid {n}(void) {{ }}\n"


def _repo(tmp_path: Path, guard: str = "") -> Path:
    """@brief One @req function, two @utility, one @callback, a test helper. @return Root."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "requirements.yaml").write_text(_CATALOG)
    body = (
        _REQ.format(n="traced") + _UTIL.format(n="u1") + _UTIL.format(n="u2") + _CB.format(n="cb")
    )
    (tmp_path / "src/a.c").write_text(_FILE.format(name="a.c") + body)
    (tmp_path / "tests/t.c").write_text(_FILE.format(name="t.c") + _UTIL.format(n="helper"))
    (tmp_path / ".clew.yaml").write_text(
        f"requirements:\n  file: requirements.yaml\nguard:\n{guard}"
    )
    return tmp_path


def test_the_counts_are_printed_and_tests_are_left_out(tmp_path, monkeypatch, capsys) -> None:
    """@brief 1 @req, 2 @utility, 1 @callback (the tests/ helper not counted): ratio 0.25."""
    monkeypatch.chdir(_repo(tmp_path))
    assert main(["coverage", "."]) == 0
    out = capsys.readouterr().out
    assert "1 with @req" in out and "@utility 2" in out and "@callback 1" in out
    assert "ratio 0.25" in out and "no floor declared" in out


def test_a_ratio_below_the_declared_floor_fails(tmp_path, monkeypatch, capsys) -> None:
    """@brief Floor 0.50, ratio 0.25: rc 1, saying both numbers."""
    monkeypatch.chdir(_repo(tmp_path, "  coverage:\n    min_req_ratio: 0.5\n"))
    assert main(["coverage", "."]) == 1
    out = capsys.readouterr().out
    assert "ratio 0.25" in out and "below the floor 0.5" in out


def test_a_ratio_at_or_above_the_floor_passes(tmp_path, monkeypatch) -> None:
    """@brief Floor 0.25: passes."""
    monkeypatch.chdir(_repo(tmp_path, "  coverage:\n    min_req_ratio: 0.25\n"))
    assert main(["coverage", "."]) == 0


@pytest.mark.parametrize("bad", ["0", "1.5", "half"])
def test_a_floor_outside_zero_to_one_is_refused(tmp_path, monkeypatch, capsys, bad) -> None:
    """@brief A floor is a number in (0, 1]; anything else is refused by name."""
    monkeypatch.chdir(_repo(tmp_path, f"  coverage:\n    min_req_ratio: {bad}\n"))
    assert main(["coverage", "."]) != 0
    assert "min_req_ratio" in capsys.readouterr().err


def test_the_pre_commit_hook_runs_the_coverage_gate(tmp_path, monkeypatch, capsys) -> None:
    """A VALID config, no floor, and a staged file with nothing wrong in it: the hook still fails,
    because the catalog holds a requirement nothing implements. Before PG3 the hook never ran
    coverage, so this passed (rc 0) and the gap waited for someone to run `coverage` by hand.

    @brief `clew guard <files>` (what pre-commit runs) runs the coverage gate.
    """
    root = _repo(tmp_path)
    (root / "requirements.yaml").write_text(
        _CATALOG + "  REQ-B-002:\n    name: nobody implements this\n"
    )
    monkeypatch.chdir(root)
    assert main(["validate", "--no-git", "src/a.c"]) == 0, "the staged file itself is clean"
    assert main(["src/a.c"]) == 1
    captured = capsys.readouterr()
    assert "REQ-B-002" in captured.out + captured.err
