# SPDX-License-Identifier: MIT
"""The suite must not inherit the repository it is being committed to.

`git commit` exports `GIT_DIR`, `GIT_INDEX_FILE` and `GIT_WORK_TREE` into every
hook it runs. Under those, a fixture that shells out to `git init` / `git ls-files`
/ `git submodule` inside `tmp_path` is not talking about `tmp_path` at all — it is
talking about, and writing into, the repository being committed to.

MEASURED, on this repository, from a real commit attempt:

  * 13 tests failed across `test_datamodel`, `test_external_provenance` and
    `test_index_scope_inheritance` — every one of them a nested-git-tree test,
    because the nested trees the fixtures build were not nested trees under an
    inherited `GIT_DIR`;
  * the same run STAGED NINE PHANTOM GITLINKS into the repository index
    (`vendor/lib`, `vendor/theirs`, `deps/generator`, `evidence/other_project`, …)
    pointing at directories that exist only under `/tmp/pytest-of-*`. Committing
    that writes submodule references to nowhere into HEAD.

The failure is worth the length because of how it PRESENTS. `pre-commit run
--all-files` runs in a plain shell and passes; `git commit` runs the same tests and
fails. To whoever is mid-change that reads exactly like "my edit broke the suite",
and the wrong response — weaken the assertion, or bypass the gate — is the easy one.

Reproduced a second time, unintentionally, by the mutation control below: the run
that disarms the conftest fixture staged `extern/theirs` into the index on its way
past. ONE test, run once, with the isolation removed.

@brief The git-location environment is stripped before any test runs.
@version 1
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from gitfixture import GIT_LOCATION_ENV, strip_git_location_env

## The three `git commit` itself exports. The rest of `GIT_LOCATION_ENV` are the
## other ways to point git at a repository; they are stripped for completeness, but
## these three are the ones measured to cause the failure above.
_EXPORTED_BY_COMMIT = ("GIT_DIR", "GIT_INDEX_FILE", "GIT_WORK_TREE")


def test_strip_removes_every_git_location_variable() -> None:
    """The mechanism, on a synthetic mapping rather than on `os.environ`, so it is
    testable without depending on how the suite happened to be launched."""
    environ = dict.fromkeys(GIT_LOCATION_ENV, "/somewhere/.git")
    environ["PATH"] = "/usr/bin"
    removed = strip_git_location_env(environ)
    assert set(removed) == set(GIT_LOCATION_ENV)
    assert environ == {"PATH": "/usr/bin"}


def test_strip_reports_only_what_was_present() -> None:
    """The restore half. The fixture puts back exactly what it took, so a developer
    who deliberately set `GIT_DIR` before running the suite gets it back, and one who
    did not does not acquire an empty string."""
    environ = {"GIT_DIR": "/a/.git", "HOME": "/home/x"}
    removed = strip_git_location_env(environ)
    assert removed == {"GIT_DIR": "/a/.git"}
    assert "GIT_INDEX_FILE" not in removed


def test_the_three_variables_a_commit_exports_are_covered() -> None:
    """Names the measured three explicitly. `GIT_LOCATION_ENV` could be trimmed to
    something plausible-looking that omits `GIT_INDEX_FILE`, and nothing else here
    would notice — the staging damage came through that one."""
    for name in _EXPORTED_BY_COMMIT:
        assert name in GIT_LOCATION_ENV


def test_a_nested_tree_test_still_passes_under_an_inherited_git_dir() -> None:
    """THE ONLY NON-VACUOUS PIN, and the reason this file spawns a subprocess.

    Every assertion above tests the helper; none of them would fail if the autouse
    fixture that CALLS it were deleted, and neither would asserting `GIT_DIR` is
    absent from `os.environ` — in a normal run it was never set, so that assertion
    is green whatever the fixture does. Only re-running a genuinely affected test
    WITH the variables set distinguishes "isolated" from "never exposed".

    `test_a_submodule_whose_git_is_a_file_is_detected` is the target because a
    submodule's `.git` is a FILE, so it is the one that fails hardest when the
    fixture tree is not really a fixture tree."""
    tests_dir = Path(__file__).resolve().parent
    git_dir = subprocess.run(
        ["git", "rev-parse", "--absolute-git-dir"],
        cwd=tests_dir,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    env = {
        **os.environ,
        "GIT_DIR": git_dir,
        "GIT_INDEX_FILE": f"{git_dir}/index",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(tests_dir / "test_external_provenance.py"),
            "-q",
            "-p",
            "no:cacheprovider",
            "-k",
            "a_submodule_whose_git_is_a_file_is_detected",
        ],
        cwd=tests_dir.parent,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "a nested-tree test failed under an inherited GIT_DIR — the conftest "
        f"isolation is not reaching it:\n{result.stdout[-3000:]}"
    )
