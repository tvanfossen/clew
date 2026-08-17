# SPDX-License-Identifier: MIT
"""The environment a `git` subprocess must NOT inherit.

A LEAF ON PURPOSE, like `vocabulary.py`: it imports `os` and nothing else, so the two
call sites that need it (`scope.py`'s ignore listing and gitlink probe,
`propose/notindexed.py`'s tracked-file listing) can share one rule without either of them
importing the other.

THE DEFECT, measured 2026-08-12. git EXPORTS `GIT_DIR` to its own hooks, and an absolute
`GIT_DIR` OUTRANKS both `git -C <root>` and `cwd=<parent>` — so every git query this
package makes from inside a hook answers about the repository running the hook rather than
the repository it was pointed at. `whole_repo_scope` then excluded the wrong tree's ignored
paths and `_is_submodule_of_parent` returned False for every real submodule.

WHY IT WAS INVISIBLE UNTIL A WORKTREE. In an ordinary checkout git exports the RELATIVE
`GIT_DIR=.git`, which resolves against each subprocess's own cwd and therefore lands on the
right repository by accident. A `git worktree` has no `.git` directory, so git exports an
ABSOLUTE path and the accident stops working: thirteen tests passed under
`pre-commit run --all-files` and failed under the real `git commit`, in a worktree only.
That is the same shape as this repo's recorded worktree/venv trap — a gate that cannot run
where the work is being done — and the same shape as its standing warning that a green
`--all-files` is necessary and not sufficient.

@brief The git-hook environment variables a subprocess must be run without.
@version 1
"""

from __future__ import annotations

import os

## Every variable git exports to a hook that REPOINTS a later git command. `GIT_DIR` is the
## fatal one; the rest are listed because they are the same class of override and a fix that
## removed only the one observed failing is a fix that waits for the next one.
##
## Deliberately NOT the whole `GIT_*` namespace: `GIT_AUTHOR_NAME`, `GIT_EDITOR` and
## friends are also exported and are harmless, and stripping an unknown variable by prefix
## is how a scrub starts breaking things it was never asked to touch.
GIT_HOOK_VARS: tuple[str, ...] = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)


## @brief The current environment with git's hook-repository overrides removed.
## @return A copy of os.environ safe to pass to a `git` subprocess.
## @version 1
## @req REQ-DDB-CONFIG-001
def git_env() -> dict[str, str]:
    """A COPY, never a mutation of `os.environ`. This package runs inside a host process —
    a pre-commit hook, an MCP server, a test session — and clearing the variables globally
    would change how the HOST's own git commands behave, which is a far larger blast radius
    than the bug being fixed.

    Returns the full environment minus the overrides, rather than a minimal one: `PATH`,
    `HOME` and the git config variables all matter to the commands being run, and a
    hand-built environment would have to guess at them.

    @brief Build a git-safe subprocess environment.
    @return The environment without the hook overrides.
    @version 1
    """
    return {k: v for k, v in os.environ.items() if k not in GIT_HOOK_VARS}
