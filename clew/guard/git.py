"""Git diff parsing for change detection.

@brief Parse git diff output to determine which lines changed in staged files.
@version 1.0
"""

from __future__ import annotations

import logging
import re
import subprocess
from collections.abc import Callable

logger = logging.getLogger(__name__)

RunCommand = Callable[[list[str]], str]

DEFAULT_GIT_TIMEOUT_SECONDS = 30

# The canonical set of failures a git invocation can raise. TimeoutExpired is NOT an
# OSError — it derives from SubprocessError — so catching (CalledProcessError, OSError)
# let a hung git command escape as an uncaught traceback and crash the pre-commit gate.
# Every caller in this package catches exactly this tuple; do not hand-assemble a subset.
GIT_ERRORS = (
    subprocess.CalledProcessError,
    subprocess.TimeoutExpired,
    OSError,
)


## @brief Default command runner using subprocess.
#  @version 1.2
#  @dg_internal
def _default_run_command(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd, capture_output=True, text=True, check=True, timeout=DEFAULT_GIT_TIMEOUT_SECONDS
    )
    return result.stdout


## @brief Run a git command through the injectable runner, returning None on failure.
#  @details Centralises the failure contract so callers cannot drift onto a narrower
#  exception tuple, which is how a hung `git diff` came to crash the gate.
#  @version 1.1
#  @req REQ-DDB-GUARD-023
#  @return Command stdout, or None if git failed, timed out, or is unavailable
def run_git(cmd: list[str], run_command: RunCommand | None = None) -> str | None:
    runner = run_command or _default_run_command
    try:
        return runner(cmd)
    except GIT_ERRORS as e:
        logger.warning("git %s failed: %s", " ".join(cmd[1:3]), e)
        return None


## @brief Run git diff --cached for a single file.
#  @version 2.0
#  @req REQ-DDB-GUARD-023
#  @return Diff text, or None if git failed
def get_staged_diff(
    file_path: str,
    run_command: RunCommand | None = None,
) -> str | None:
    return run_git(["git", "diff", "--cached", "-U0", "--", file_path], run_command)


## @brief Run git diff for a file over a given revision range.
#  @version 2.0
#  @req REQ-DDB-GUARD-023
#  @return Diff text, or None if git failed
def get_diff(
    file_path: str,
    diff_range: str,
    run_command: RunCommand | None = None,
) -> str | None:
    if diff_range.startswith("-"):
        # git diff would parse this as an option; --output=<file> is an arbitrary write.
        logger.error("Refusing diff range that looks like an option: %r", diff_range)
        return None
    return run_git(["git", "diff", "-U0", diff_range, "--", file_path], run_command)


## @brief Extract the set of modified line numbers from a unified diff.
#  @version 1.1
#  @req REQ-DDB-GUARD-023
#  @return Set of 0-indexed line numbers that were added or modified
#
#  Parses @@ hunk headers to determine which lines in the new file were
#  added or modified. Returns 0-indexed line numbers to match parser conventions.
def parse_changed_lines(diff_output: str) -> set[int]:
    changed: set[int] = set()
    hunk_re = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)

    for match in hunk_re.finditer(diff_output):
        start = int(match.group(1))
        count = int(match.group(2)) if match.group(2) else 1

        if count == 0:
            # Pure deletion — no new lines added
            continue

        # Convert to 0-indexed
        for line_num in range(start - 1, start - 1 + count):
            changed.add(line_num)

    return changed


## @brief Stage files for the next git commit.
#  @version 2.0
#  @utility
def git_add(
    paths: str | list[str],
    run_command: RunCommand | None = None,
) -> bool:
    file_list = [paths] if isinstance(paths, str) else [str(p) for p in paths]
    # "--" so a path beginning with "-" cannot be parsed as an option.
    return run_git(["git", "add", "--", *file_list], run_command) is not None


## @brief Detect the merge-base between current HEAD and a target branch.
#  @version 1.1
#  @req REQ-DDB-GUARD-023
def get_merge_base(
    target_branch: str = "origin/main",
    run_command: RunCommand | None = None,
) -> str | None:
    result = run_git(["git", "merge-base", target_branch, "HEAD"], run_command)
    if result is None:
        logger.warning("Could not determine merge-base against %s", target_branch)
        return None
    return result.strip()


## @brief Build a diff range string from merge-base to HEAD.
#  @details Returns None when on the target branch itself (merge-base == HEAD),
#  signaling callers to fall back to staged diff.
#  @version 1.2
#  @req REQ-DDB-GUARD-023
def get_branch_diff_range(
    target_branch: str = "origin/main",
    run_command: RunCommand | None = None,
) -> str | None:
    base = get_merge_base(target_branch, run_command)
    if base is None:
        return None
    head = _rev_parse_head(run_command)
    if head and base == head:
        return None
    return f"{base}...HEAD"


## @brief Get the current HEAD commit SHA.
#  @version 1.1
#  @dg_internal
def _rev_parse_head(run_command: RunCommand | None) -> str | None:
    result = run_git(["git", "rev-parse", "HEAD"], run_command)
    return result.strip() if result is not None else None


## @brief Get a file's content as of a given revision.
#  @details The "./" prefix makes git resolve file_path relative to the current
#  working directory rather than the repository root, matching every other path
#  argument in this module.
#  @version 1.0
#  @req REQ-DDB-GUARD-023
#  @return File content at the revision, or None if the file didn't exist there
def get_file_at_revision(
    file_path: str,
    revision: str = "HEAD",
    run_command: RunCommand | None = None,
) -> str | None:
    return run_git(["git", "show", f"{revision}:./{file_path}"], run_command)


## @brief Convenience function combining staged diff retrieval and parsing.
#  @version 1.1
#  @req REQ-DDB-GUARD-023
#  @return Set of 0-indexed changed line numbers, empty if the diff was unavailable
def get_changed_lines_for_file(
    file_path: str,
    run_command: RunCommand | None = None,
) -> set[int]:
    diff_output = get_staged_diff(file_path, run_command)
    return parse_changed_lines(diff_output) if diff_output else set()
