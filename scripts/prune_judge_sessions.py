# SPDX-License-Identifier: MIT
"""Remove the CLI session transcripts the acceptance grader's judge calls leave behind.

Every `claude -p` judge call is saved as a session under `~/.claude/projects/<cwd slug>/`, and
nothing reads them — each verdict is cached in its run's `judge-cache`. On 2026-11-04 48,412 of
them (14.9 GB) filled the owner's disk. The grader is frozen at its pre-registered fingerprint, so
its argv cannot gain `--no-session-persistence` before the 1.3.0 grid; run this after a pass:

    .venv/bin/python scripts/prune_judge_sessions.py            # this checkout's session dir
    .venv/bin/python scripts/prune_judge_sessions.py <dir>      # an explicit one

A transcript is removed only when its opening bytes hold the grader's own prompt, so a working
session in the same directory is never touched.

@brief Prune judge-call session transcripts.
@version 1
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

## The grader's prompt opening, as `acceptance/grader/judge.py` writes it.
_JUDGE_MARK = b"You are grading ONE checklist item"
## How much of a transcript is read to recognise it: the prompt is in its first record.
_HEAD_BYTES = 4096


##
# @brief The CLI's session directory for a working directory.
# @param cwd The directory the judge calls ran from.
# @return `~/.claude/projects/<slug>`, the slug being the path with every non-alphanumeric as `-`.
# @version 1
def session_dir(cwd: Path) -> Path:
    """@brief Session dir for a cwd. @return The path."""
    return Path.home() / ".claude" / "projects" / re.sub(r"[^A-Za-z0-9]", "-", str(cwd))


##
# @brief Remove every judge transcript directly under a directory.
# @param directory A CLI session directory.
# @return (files removed, bytes freed).
# @version 1
def prune(directory: Path) -> tuple[int, int]:
    """@brief Prune. @return (removed, freed)."""
    removed = freed = 0
    for path in directory.glob("*.jsonl"):
        with path.open("rb") as handle:
            head = handle.read(_HEAD_BYTES)
        if _JUDGE_MARK in head:
            freed += path.stat().st_size
            path.unlink()
            removed += 1
    return removed, freed


##
# @brief Prune the named directory, or this checkout's session directory.
# @return Process exit code.
# @version 1
def main() -> int:
    """@brief Entry point. @return 0."""
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else session_dir(Path.cwd().resolve())
    if not target.is_dir():
        print(f"no session directory at {target}; nothing to prune")
        return 0
    removed, freed = prune(target)
    print(f"removed {removed} judge transcript(s), {freed / 1e9:.2f} GB, from {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
