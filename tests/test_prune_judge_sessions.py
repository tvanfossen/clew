# SPDX-License-Identifier: MIT
"""Judge calls leave session transcripts; the prune removes those and nothing else.

FOUND WHEN THE OWNER'S DISK FILLED (2026-11-04): every `claude -p` judge call the grader makes is
saved as a CLI session under `~/.claude/projects/<cwd slug>/`. 48,412 had accumulated — 14.9 GB —
and nothing reads them: verdicts live in each run's `judge-cache`. The grader is frozen at its
pre-registered fingerprint for the 1.3.0 grid, so the call keeps its argv and the transcripts are
pruned after a pass. A transcript is a judge's ONLY when its opening prompt is the grader's own.

@brief Tests for scripts/prune_judge_sessions.py.
@version 1
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


## @brief Load the prune script by path.
## @return The module.
## @version 1
def _load():
    """@brief Load. @return Module."""
    path = REPO_ROOT / "scripts" / "prune_judge_sessions.py"
    spec = importlib.util.spec_from_file_location("prune_judge_sessions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


## @brief Only judge transcripts are removed; a working session and other files survive.
## @param tmp_path Pytest temporary directory.
## @return None.
## @version 1
def test_only_judge_transcripts_are_removed(tmp_path: Path) -> None:
    """@brief Judge files go; the rest stay.
    @return None.
    @version 1
    """
    judge = tmp_path / "a.jsonl"
    judge.write_text(
        '{"content":"You are grading ONE checklist item from a frozen grading key"}\n', "utf-8"
    )
    work = tmp_path / "b.jsonl"
    work.write_text('{"content":"fix the build"}\n', "utf-8")
    other = tmp_path / "notes.txt"
    other.write_text("You are grading ONE checklist item", "utf-8")

    removed, freed = _load().prune(tmp_path)

    assert (removed, judge.exists(), work.exists(), other.exists()) == (1, False, True, True)
    assert freed > 0
