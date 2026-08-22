# SPDX-License-Identifier: MIT
"""Nothing under an `internal/` segment may ever be committable.

Private targets are measured but never published: no path, symbol, count or requirement id from
one may reach a committed file. That rule has NO SCRUB GATE behind it — CLAUDE.md records that
two keyword sweeps came back clean while eight files still leaked — so the protection has to be
structural rather than vigilant.

THIS TEST NAMES NO PRIVATE TARGET, deliberately. A test listing them would itself be the leak it
exists to prevent, and would need editing every time one is added — which is the same
remember-to-do-it failure the wholesale ignore replaces.

@brief Private target paths are unconditionally ignored.
@version 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


## @brief Whether git would ignore a path.
## @param rel Repo-relative path, which need not exist.
## @return True when ignored.
## @version 1
def _ignored(rel: str) -> bool:
    """`--no-index` so the answer is about the RULES, not about whether the file happens to be
    on disk right now. A check that only works once a private target exists locally would pass
    vacuously on any other machine.

    @brief Is this path ignored.
    @return True when ignored.
    @version 1
    """
    done = subprocess.run(
        ["git", "check-ignore", "--no-index", "-q", rel],
        cwd=str(REPO),
        capture_output=True,
        check=False,
    )
    return done.returncode == 0


## @brief Every place a private target can appear is ignored.
## @return None.
## @version 1
def test_internal_paths_are_ignored_everywhere() -> None:
    """Rubric, checkout, index and run artifacts all have to be covered. A run writes somewhere
    the rubric does not, and an earlier version of this protection covered only the rubric — one
    `git add -A` away from committing a private repository into a public one.

    @brief Internal paths are ignored.
    @return None.
    @version 1
    """
    for rel in (
        "acceptance/targets/internal/anything/questions.yaml",
        "acceptance/runs/2099-01-01-n9/internal/anything/answers/Q1_m_index_r1.md",
        "acceptance/runs/2099-01-01-n9/internal/anything/repo/src/main.rs",
        "acceptance/runs/2099-01-01-n9/internal/anything/state/targets/x/clew.db",
        "acceptance/operational/internal/whatever.md",
    ):
        assert _ignored(rel), f"a private-target path is COMMITTABLE: {rel}"


## @brief The rule does not swallow public targets.
## @return None.
## @version 1
def test_public_run_artifacts_stay_committable() -> None:
    """The other half. An ignore broad enough to catch everything would also hide the evidence
    every published number depends on, and a figure whose artifacts are not in the repository is
    unverifiable prose.

    @brief Public artifacts remain committable.
    @return None.
    @version 1
    """
    for rel in (
        "acceptance/runs/2099-01-01-n9/mbedtls/answers/Q1_m_index_r1.md",
        "acceptance/targets/mbedtls/questions.yaml",
    ):
        assert not _ignored(rel), f"a PUBLIC artifact is being ignored: {rel}"
