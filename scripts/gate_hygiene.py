# SPDX-License-Identifier: MIT
"""REFUSE TO CALL THE GATE GREEN WHEN IT COULD NOT SEE THE TREE.

WHY IT EXISTS. `843764f` committed 1,637 acceptance artifacts after a green
`pre-commit run --all-files`, and the release workflow then went red on all three interpreters
because `end-of-file-fixer` rewrote files the local run had never looked at. Two independent
holes produced that:

  - **`--all-files` means all TRACKED files.** pre-commit asks git for the index, so a file that
    is untracked when the gate runs is invisible to it. The green was real; its scope was not.
  - **No commit-time hook was installed.** `.git/hooks/pre-commit` did not exist, so the staged
    files were not gated either. Every green in this repository's history up to 1.1.0 was a human
    remembering to run the gate by hand.

The second is the root cause, and a file in the repository cannot fix it — `.git/hooks` is not
version controlled, and `pre-commit install` is a per-checkout action. What the repository CAN do
is decline to report success while the commit-time gate is absent. A warning in a README is read
once; an exit code is read every time.

WHAT IT DELIBERATELY DOES NOT DO. It does not install anything. A gate that silently modifies the
checkout it is auditing cannot be trusted to report on it, and an agent or CI job writing to
`.git/hooks` is a surprise either way. It prints the command and fails.

WHY IT READS THE EXCLUDE LIST INSTEAD OF RESTATING IT. Which paths the hooks cover is defined by
the global `exclude:` in `.pre-commit-config.yaml`. A second copy of that regex here would be a
second place to edit, and the first time the two disagreed this guard would either fire on every
acceptance run — and be switched off within a day — or wave through the exact class of file that
caused the incident. `acceptance/runs/` is excluded on purpose: you do not reformat frozen
evidence.

ABSENCE IS NOT EMPTINESS. A config with no global `exclude:` yields `None`, not an empty pattern.
"nothing is excluded" and "the exclude could not be read" are different facts and the second one
must not quietly take the permissive reading.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

## pre-commit's installed hook is a generated shell script carrying this marker and an
## `INSTALL_PYTHON` assignment. Matching on content rather than on the path's existence is
## deliberate: other tools install their own `pre-commit` hook, and treating one of those as this
## gate would report a gate that is not there — the same defect as a green gate checking nothing.
_PRE_COMMIT_MARKERS = ("start templated", "INSTALL_PYTHON")

_EXCLUDE_HEADER = re.compile(r"^exclude:\s*\|", re.MULTILINE)


##
# @brief Parse the global `exclude:` regex out of a pre-commit config.
# @param config Path to `.pre-commit-config.yaml`.
# @return The compiled pattern, or None when the config declares no global exclude.
# @version 1
def global_exclude(config: Path) -> re.Pattern[str] | None:
    """HAND-PARSED RATHER THAN VIA PYYAML, because the value wanted is the verbose `(?x)`
    alternation exactly as written, and a YAML load would hand back a block scalar that still has
    to be reassembled. The block is the indented run of lines after `exclude: |`, which is all
    this needs to find.

    Returns None when there is no `exclude:` key at all — absent, not empty. A caller that got an
    empty pattern instead would silently treat an unreadable config as "nothing is excluded".

    @brief Read the global exclude pattern.
    @param config The config path.
    @return Compiled pattern or None.
    @version 1
    """
    if not config.is_file():
        return None
    text = config.read_text("utf-8")
    match = _EXCLUDE_HEADER.search(text)
    if match is None:
        return None
    body: list[str] = []
    for line in text[match.end() :].splitlines()[1:]:
        ## The block ends at the first line that is neither blank nor indented, which is the next
        ## top-level key.
        if line.strip() and not line.startswith((" ", "\t")):
            break
        body.append(line.strip())
    return re.compile("".join(body))


##
# @brief List the paths git reports as untracked, honouring ignore rules.
# @param repo Repository root.
# @return Repo-relative paths, in git's order.
# @version 1
def untracked_paths(repo: Path) -> list[str]:
    """`--exclude-standard` IS LOAD-BEARING. Without it this returns every ignored build artifact
    and venv file, the guard becomes noise, and someone turns it off. A gitignored file is also
    not a hole: the hooks never see it either, so there is no gap between what was checked and
    what the commit carries.

    @brief Untracked, non-ignored paths.
    @param repo Repository root.
    @return Repo-relative paths.
    @version 1
    """
    result = subprocess.run(
        ["git", "-C", str(repo), "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in result.stdout.splitlines() if line]


##
# @brief List untracked paths that the configured hooks would have covered.
# @param repo Repository root.
# @return Repo-relative paths the gate could not see but would have checked.
# @version 1
def untracked_but_covered(repo: Path) -> list[str]:
    """The intersection that matters: on disk, not in the index, and not excluded. Those are the
    files a `--all-files` run reports nothing about and a commit then carries.

    @brief Untracked paths inside the hooks' scope.
    @param repo Repository root.
    @return The offending paths.
    @version 1
    """
    excluded = global_exclude(repo / ".pre-commit-config.yaml")
    paths = untracked_paths(repo)
    if excluded is None:
        return paths
    return [path for path in paths if not excluded.match(path)]


##
# @brief Report whether pre-commit's own commit-time hook is installed.
# @param repo Repository root.
# @return True when `.git/hooks/pre-commit` is pre-commit's generated hook.
# @version 1
def commit_hook_installed(repo: Path) -> bool:
    """Asks about CONTENT, not existence — see `_PRE_COMMIT_MARKERS`. A worktree's `.git` is a
    file pointing elsewhere rather than a directory, in which case the hook path cannot be
    resolved this way and the honest answer is False: not "no hook", but "this check cannot
    confirm one", and the two agree on the action.

    @brief Is pre-commit's hook installed.
    @param repo Repository root.
    @return True when it is.
    @version 1
    """
    hook = repo / ".git" / "hooks" / "pre-commit"
    if not hook.is_file():
        return False
    text = hook.read_text("utf-8", errors="replace")
    return any(marker in text for marker in _PRE_COMMIT_MARKERS)


##
# @brief Report untracked files the hooks would have covered.
# @param unseen Paths the gate could not see.
# @return None.
# @version 1
# @dg_internal
def _report_unseen(unseen: list[str]) -> None:
    """Every path is named, never a count alone. "3 files" sends the reader to `git status` to
    work out which three; the whole value of the check is which.

    @brief Print the unseen paths.
    @param unseen The paths.
    @return None.
    @version 1
    """
    print(
        f"{len(unseen)} untracked file(s) lie inside the hooks' scope, so "
        f"`pre-commit run --all-files` reports nothing about them while a commit would carry "
        f"them. Stage them and re-run the gate, or exclude them deliberately:",
        file=sys.stderr,
    )
    for path in unseen:
        print(f"  {path}", file=sys.stderr)


##
# @brief Report that the commit-time hook is absent, and whether that is being enforced.
# @param enforced True when the missing hook will fail this run.
# @return None.
# @version 1
# @dg_internal
def _report_missing_hook(enforced: bool) -> None:
    """SAYS WHICH IT DID. A check that sometimes fails and sometimes only mentions, without
    stating which, teaches the reader to skim it — and then the one time it mattered reads
    exactly like the times it did not.

    @brief Print the missing-hook finding.
    @param enforced Whether it fails the run.
    @return None.
    @version 1
    """
    severity = "not installed" if enforced else "not installed (not enforced under CI)"
    print(
        f"pre-commit's commit-time hook is {severity}, so nothing gates a commit in this "
        "checkout and every green is a human remembering to run one. Install it with:\n"
        "  .venv/bin/pre-commit install",
        file=sys.stderr,
    )


##
# @brief Print both findings and return the exit code the gate should take.
# @param argv Optional argument list; the first entry is the repository root.
# @param ci True when running in CI, where a commit-time hook is not expected.
# @return 0 when the gate can see the tree and is gated, 1 otherwise.
# @version 1
def main(argv: list[str] | None = None, ci: bool | None = None) -> int:
    """BOTH CHECKS ALWAYS RUN AND BOTH ARE ALWAYS REPORTED. Returning on the first failure would
    hide the second, and these two are each other's context: an uninstalled hook is why an
    untracked file reaches a commit at all.

    **THE COMMIT-TIME CHECK IS NOT ENFORCED UNDER CI, AND THAT IS NOT A LOOPHOLE.** CI clones
    fresh and invokes the gate explicitly, so `.git/hooks/pre-commit` is absent there by
    construction and always will be. Enforcing it would fail every CI run and the check would be
    deleted within a day — which is the real way a check dies. The claim it makes is about an
    *interactive checkout*, where the gate runs only if something invokes it. It is still printed
    under CI, so the finding never silently disappears.

    The untracked check is enforced everywhere, because its claim holds everywhere: a file on disk
    that git does not know about is invisible to the hooks whoever is running them.

    Single exit point, by the returns-per-function limit this repository enforces.

    @brief Run the hygiene checks.
    @param argv Argument list.
    @param ci CI override; read from the environment when None.
    @return Process exit code.
    @version 1
    """
    args = list(sys.argv[1:] if argv is None else argv)
    repo = Path(args[0]) if args else Path(__file__).resolve().parent.parent
    in_ci = bool(os.environ.get("CI")) if ci is None else ci

    unseen = untracked_but_covered(repo)
    installed = commit_hook_installed(repo)

    if unseen:
        _report_unseen(unseen)
    if not installed:
        _report_missing_hook(enforced=not in_ci)

    hook_fails = not installed and not in_ci
    return 1 if (unseen or hook_fails) else 0


if __name__ == "__main__":
    raise SystemExit(main())
