# SPDX-License-Identifier: MIT
"""Tests for the grid driver.

WHAT IS WORTH ASSERTING HERE is not that four phases run — that is obvious from reading it — but
that the PATHS the phases receive are derived from one root and cannot diverge, and that one
target's failure does not take the grid with it. Every path defect this harness shipped was an
operator typing the same directory twice and typing it differently once.

@brief Tests for acceptance.matrix.
@version 1
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from acceptance import matrix

REPO = Path(__file__).resolve().parent.parent
TARGETS = REPO / "acceptance" / "targets"


## @brief Build driver arguments.
## @return Namespace.
## @version 1
def _args(**over) -> argparse.Namespace:
    """@brief Driver argument stub.
    @return Namespace.
    @version 1
    """
    base = {
        "out": Path("/grid"),
        "targets": TARGETS,
        "models": ["sonnet"],
        "replicates": 3,
        "seed": 7,
        "timeout": 1800,
    }
    base.update(over)
    return argparse.Namespace(**base)


## @brief Discovery finds every shipped target and no private one.
## @return None.
## @version 1
def test_discover_finds_the_shipped_targets() -> None:
    """A GLOB THAT MATCHES NOTHING WOULD DRIVE AN EMPTY GRID and report success on it, which is
    why the count is asserted rather than the mechanism.

    @brief Discovery is non-vacuous and excludes the private tree.
    @return None.
    @version 1
    """
    found = matrix.discover(TARGETS)
    names = [p.parent.name for p in found]
    assert len(found) >= 4, f"only found {names}"
    assert "internal" not in names


## @brief Every phase receives the SAME derived paths for one target.
## @return None.
## @version 1
def test_phase_paths_are_derived_and_absolute(tmp_path: Path) -> None:
    """THE DEFECT THIS DRIVER EXISTS TO PREVENT. Generate writes answers and grade reads them; a
    hand-run sequence retyped that directory and got it wrong. Here both come from one
    expression, so they are equal by construction — and the test compares them rather than
    trusting that.

    ABSOLUTE, because a relative --mcp-config once resolved against the agent's working
    directory rather than the operator's and produced an index arm with no index and no error.

    @brief Paths are shared and absolute.
    @return None.
    @version 1
    """
    rubric = TARGETS / "mbedtls" / "questions.yaml"
    root = tmp_path / "mbedtls"
    gen = matrix.phase_argv("generate", rubric, root, _args())
    grade = matrix.phase_argv("grade", rubric, root, _args())
    report = matrix.phase_argv("report", rubric, root, _args())

    answers_written = gen[gen.index("--out") + 1]
    answers_graded = grade[grade.index("--answers") + 1]
    answers_reported = report[report.index("--answers") + 1]
    assert answers_written == answers_graded == answers_reported, (
        "generate writes and grade reads the same directory or the grid grades nothing"
    )
    for flag in ("--out", "--repo", "--mcp-config", "--rubric"):
        value = gen[gen.index(flag) + 1]
        assert Path(value).is_absolute(), f"{flag} must be absolute, got {value!r}"


## @brief The driver's run parameters reach the generate phase.
## @return None.
## @version 1
def test_generate_carries_the_grid_parameters() -> None:
    """Replicates and seed decide the whole shape of a run; a driver that silently dropped them
    would produce an n=1 grid while the operator believed they had asked for n=3, and every
    downstream number would be right about the wrong run.

    @brief Parameters are threaded through.
    @return None.
    @version 1
    """
    argv = matrix.phase_argv(
        "generate",
        TARGETS / "self" / "questions.yaml",
        Path("/grid/self"),
        _args(replicates=3, seed=11, models=["sonnet", "haiku"]),
    )
    assert argv[argv.index("--replicates") + 1] == "3"
    assert argv[argv.index("--seed") + 1] == "11"
    assert argv[argv.index("--models") + 1 : argv.index("--models") + 3] == ["sonnet", "haiku"]


## @brief Grade and report are never handed generation-only flags.
## @return None.
## @version 1
def test_grading_phases_take_no_generation_flags() -> None:
    """A stray --repo on grade would be an argparse error mid-grid, after generation had already
    been paid for.

    @brief Phase arguments are phase-appropriate.
    @return None.
    @version 1
    """
    for phase in ("grade", "report"):
        argv = matrix.phase_argv(phase, TARGETS / "knots" / "questions.yaml", Path("/g/k"), _args())
        for flag in ("--repo", "--models", "--mcp-config", "--out", "--timeout"):
            assert flag not in argv, f"{phase} must not receive {flag}"


## @brief One target failing does not stop the others.
## @return None.
## @version 1
def test_a_failed_target_does_not_stop_the_grid(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A provisioning problem on one repository is not a reason to spend nothing on the other
    three — a weekend run that aborts on target one has cost a weekend and produced nothing.

    THE FAILURE IS NAMED, NOT COUNTED. "some targets failed" sends a reader to the logs; the
    name and the phase send them to the cause.

    @brief A failure is isolated and named.
    @return None.
    @version 1
    """
    targets = tmp_path / "targets"
    for name in ("alpha", "beta"):
        (targets / name).mkdir(parents=True)
        (targets / name / "questions.yaml").write_text("not a rubric\n", encoding="utf-8")

    prepared: list[str] = []

    def fake_prepare(rubric_path, out):
        name = rubric_path.parent.name
        prepared.append(name)
        if name == "alpha":
            return matrix.TargetOutcome(name, False, "provision", "pinned commit not reachable")
        return object(), out / name, object()

    monkeypatch.setattr(matrix, "_prepare", fake_prepare)
    monkeypatch.setattr(matrix, "run_phase", lambda *_a, **_k: True)
    code = matrix.drive(_args(out=tmp_path / "grid", targets=targets))

    assert prepared == ["alpha", "beta"], "a failed target must not stop provisioning the rest"
    out = capsys.readouterr().out
    assert code == 1, "the exit code is the number of failed targets"
    assert "alpha" in out and "provision" in out, "the failure must be named with its phase"
    assert "1/2 target(s) completed every phase" in out
