# SPDX-License-Identifier: MIT
"""Build a real submodule fixture — a parent that RECORDS a child at mode 160000.

EXTRACTED WHEN THE SECOND CONSUMER APPEARED (gh#352 half 2). Two test files need to
build the same shape, and a copied builder is how two fixtures come to describe two
different worlds while both look like "a submodule": the external-provenance tests
would have kept asserting against gitlinks while the scope-inheritance tests asserted
against bare `.git` directories, and only one of those is what `git submodule`
produces.

WHY A GITLINK AND NOT A `.git` DIRECTORY. A `.git` in a directory says somebody has a
repository THERE; only the PARENT knows whether it treats that directory as a
dependency it declared or as code it committed and owns. The two diverge for a
developer clone left inside a tracked directory — and then the external tag becomes a
property of the working copy rather than of the repository, so the same commit indexes
differently depending on who built it. Measured on
[tvanfossen/entropic](https://github.com/tvanfossen/entropic): three roots tagged
external against the one `.gitmodules` declares.

@brief Shared helpers for building submodule fixtures.
@version 1
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

## The sha need not EXIST — the detector reads the MODE field, never the object, so resolving a
## real commit would make every fixture slower and prove nothing more. It may not be the NULL
## sha: git rejects `0`*40 with `error: cache entry has null sha1` followed by `fatal: Unable to
## write new index file`, because all-zeros is git's own sentinel for "no object". The first
## version of this fixture used it, and `check=True` in `git_run` is what turned that into a
## visible failure instead of a silently gitlink-free world in which every assertion here would
## have passed for the wrong reason.
PLACEHOLDER_SHA = "1" * 40

## `160000` is a GITLINK: the parent's index saying "this path is another repository". Ordinary
## committed files are `100644`/`100755`, which is precisely the discrimination the external tag
## rests on.
GITLINK_MODE = "160000"


## The environment variables git EXPORTS TO ITS OWN HOOKS, which every git command run
## from inside a hook then inherits. `GIT_DIR` is the fatal one: with it set, `git init`
## initialises the repository it names instead of `<cwd>/.git`, so a fixture that believes
## it built a nested tree has built nothing at all.
##
## MEASURED, and this is why the list exists rather than a comment saying "be careful":
## thirteen tests across `test_external_provenance`, `test_datamodel` and
## `test_index_scope_inheritance` PASSED under `pre-commit run --all-files` and FAILED
## under the real `git commit`, with a `FileNotFoundError` on a `.git` the fixture thought
## it had just created. Reproduced exactly by exporting `GIT_DIR` and running the same
## tests from a shell. That is the shape this repo's own notes warn about — a green
## `--all-files` is necessary and not sufficient, because the two invocations ask
## different questions — and here the difference was the ENVIRONMENT rather than the diff.
## LIVES HERE, NOT IN `conftest.py`, AND THE REASON IS AN IMPORT COLLISION THAT ONLY
## APPEARS IN THE OPT-IN TIER. Two agents fixed this defect independently and the merge
## kept both halves; the session-wide autouse fixture below imported its list with a bare
## `from conftest import …`, which resolves against `sys.path` — and under `--integration`
## pytest has inserted `tests/integration/` ahead of `tests/`, so the name binds to the
## WRONG conftest and collection dies with an ImportError. A module with a unique name
## cannot collide, so the single source sits in one.
GIT_LOCATION_ENV = (
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
)


## @brief Remove every git location variable from an environment mapping.
## @param environ The mapping to strip, mutated in place.
## @return The names that were present and have been removed, with their values.
## @version 2
def strip_git_location_env(environ: dict[str, str]) -> dict[str, str]:
    """Split out from the fixture so the mechanism is testable without depending on the
    ambient environment. A test that merely asserts `GIT_DIR` is absent passes for free in a
    normal run — where it was never set — and would therefore go on passing if the fixture
    were deleted, which is the whole failure mode this suite's own notes warn about.

    @brief Strip the git location variables, reporting what was removed.
    @param environ The mapping to strip, mutated in place.
    @return The removed name to value pairs.
    @version 2
    """
    return {name: environ.pop(name) for name in GIT_LOCATION_ENV if name in environ}


## @brief Run one git command in a directory, failing loudly.
## @param cwd Directory to run in.
## @param args Git arguments.
## @return Captured stdout.
## @version 3
def git_run(cwd: Path, *args: str) -> str:
    """`check=True`, because a fixture whose git command failed silently would build exactly the
    world the OLD detector believed in — a directory with a `.git` and no gitlink — and every
    assertion resting on it would then pass for the wrong reason.

    THE ENVIRONMENT IS SCRUBBED, and that is what makes this runnable from a git hook at
    all. See `GIT_LOCATION_ENV`: a fixture that inherits `GIT_DIR` from the commit that is
    running it writes into the REPOSITORY BEING COMMITTED rather than into `tmp_path`, and
    the failure surfaces later and somewhere else.

    @brief Run git in a clean environment, raising on failure.
    @return stdout.
    @version 3
    """
    env = {k: v for k, v in os.environ.items() if k not in GIT_LOCATION_ENV}
    return subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True, env=env
    ).stdout


## @brief Make `parent` record `rel` as a submodule gitlink, as `git submodule add` would.
## @param parent Enclosing repository root (already `git init`ed).
## @param rel Repo-relative directory to turn into a gitlink.
## @param git_as_file Give the child a `.git` POINTER FILE instead of a real `.git` directory.
## @return None.
## @version 1
def make_gitlink(parent: Path, rel: str, git_as_file: bool = False) -> None:
    """`update-index --cacheinfo 160000` rather than `git submodule add`, which wants a URL and a
    network-shaped workflow. The MODE is the whole point, and it is exactly what the detector
    reads.

    The child gets a real `.git` too, so the cheap filesystem pre-check still passes and a test
    exercises BOTH halves of the discriminator rather than only the git query.

    `git_as_file` builds the OTHER half of that pre-check — the 44-byte `gitdir:` pointer a real
    `git submodule` checkout writes, where `git init` leaves a directory. Not cosmetic: a detector
    reading `".git" in dirnames` passes every directory fixture and is blind to every actual
    submodule, which is the defect gh#335 shipped and no fixture in the suite could catch, because
    every fixture built a directory.

    @brief Record a directory as a submodule gitlink.
    @version 1
    """
    child = parent / rel
    child.mkdir(parents=True, exist_ok=True)
    if git_as_file:
        depth = "../" * (len(Path(rel).parts) + 1)
        (child / ".git").write_text(f"gitdir: {depth}.git/modules/{rel}\n", encoding="utf-8")
    else:
        git_run(child, "init", "-q", ".")
    git_run(
        parent, "update-index", "--add", "--cacheinfo", f"{GITLINK_MODE},{PLACEHOLDER_SHA},{rel}"
    )


## @brief Initialise a repository and record nested dependency trees in it.
## @param root Directory to make into a repository.
## @param nested Repo-relative directories to record as submodule gitlinks.
## @return The root, for chaining.
## @version 1
def repo_with_submodules(root: Path, *nested: str) -> Path:
    """The whole shape in one call, since every caller needs the parent to be a repository before
    a gitlink can be recorded in it — and a `_gitlink` against an uninitialised parent fails with
    git's own message rather than with anything about what the fixture meant.

    @brief Build a parent repository declaring the given submodules.
    @return The repository root.
    @version 1
    """
    root.mkdir(parents=True, exist_ok=True)
    git_run(root, "init", "-q", ".")
    for rel in nested:
        make_gitlink(root, rel)
    return root
