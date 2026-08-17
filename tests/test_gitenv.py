# SPDX-License-Identifier: MIT
"""Every git subprocess this package runs must ignore the hook environment it inherits.

THE DEFECT, and how it was found rather than reasoned about. Thirteen tests across
`test_external_provenance`, `test_datamodel` and `test_index_scope_inheritance` passed
under `pre-commit run --all-files` and FAILED under the real `git commit`, in a git
WORKTREE. Reproduced from a shell by exporting `GIT_DIR` and running the same three files:
the identical thirteen failed, and the fix took them to zero under the same environment.

WHY IT HID FOR SO LONG. In an ordinary checkout git exports the RELATIVE `GIT_DIR=.git`,
which each subprocess resolves against its own cwd and therefore lands on the right
repository by accident. A worktree has no `.git` directory, so git exports an ABSOLUTE
path and the accident stops working. So the bug is invisible exactly where the suite
normally runs and fatal exactly where an agent's worktree runs — which is why the
environment, and not the diff, is what these tests vary.

WHAT IT COST WHEN IT FIRED, in production terms: `git -C <root>` and `cwd=<parent>` are
both OUTRANKED by an absolute `GIT_DIR`, so `whole_repo_scope` excluded the wrong tree's
ignored paths, `_is_dependency_of_parent` returned False for every real submodule, and
`propose_declaration` saw every file in the target repository as untracked. clew's
sibling tool is a PRE-COMMIT HOOK, so "invoked from inside a git hook" is not an exotic
environment for this package — it is the intended one.

@brief Tests that the git-hook environment cannot repoint this package's git queries.
@version 1
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from clew import gitenv, scope
from clew.propose.notindexed import tracked_files


## @brief A one-file git repository under tmp_path.
## @param root Directory to initialise.
## @return The initialised root.
## @version 1
def _repo(root: Path) -> Path:
    """Built through `gitfixture.git_run`, which scrubs the same variables — so the
    FIXTURE cannot be the thing that makes these tests pass. That distinction matters:
    a fixture that inherited `GIT_DIR` would fail to build at all, and the failure would
    look like the production bug while proving nothing about it.

    @brief Initialise a small git repo.
    @return The repo root.
    @version 1
    """
    from gitfixture import git_run

    root.mkdir(parents=True, exist_ok=True)
    (root / "kept.c").write_text("int kept(void){return 0;}\n", encoding="utf-8")
    (root / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    (root / "ignored").mkdir()
    (root / "ignored" / "junk.c").write_text("int junk(void){return 1;}\n", encoding="utf-8")
    git_run(root, "init", "-q")
    git_run(root, "add", "kept.c", ".gitignore")
    git_run(root, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "x")
    return root


## @brief Export a foreign GIT_DIR for the duration of one test.
## @param monkeypatch pytest monkeypatch fixture.
## @param elsewhere A directory that is NOT the repo under test.
## @return None.
## @version 1
def _as_if_inside_a_hook(monkeypatch: pytest.MonkeyPatch, elsewhere: Path) -> None:
    """ABSOLUTE, because that is what a worktree's git exports and it is the half that
    breaks. A relative `.git` would resolve per-subprocess and the test would pass against
    the unfixed code — a control that cannot fail.

    @brief Simulate the environment git hands a hook.
    @return None.
    @version 1
    """
    elsewhere.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("GIT_DIR", str(elsewhere.resolve()))
    monkeypatch.setenv("GIT_INDEX_FILE", str((elsewhere / "index").resolve()))


def test_git_env_drops_the_repointing_variables_and_keeps_the_rest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The scrub is NAMED, not a `GIT_*` prefix sweep. `GIT_AUTHOR_NAME` and `GIT_EDITOR`
    are exported to hooks too and are harmless; removing an unknown variable by prefix is
    how a scrub starts breaking things nobody asked it to touch.

    @brief `git_env` removes exactly the overrides and nothing else.
    @return None.
    @version 1
    """
    monkeypatch.setenv("GIT_DIR", "/somewhere/else/.git")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "someone")
    env = gitenv.git_env()

    assert "GIT_DIR" not in env
    assert env.get("GIT_AUTHOR_NAME") == "someone", "a harmless git variable must survive"
    assert env.get("PATH") == os.environ.get("PATH"), "the rest of the environment is kept"
    assert os.environ.get("GIT_DIR") == "/somewhere/else/.git", (
        "the scrub must return a COPY — mutating os.environ would change how the HOST "
        "process's own git commands behave"
    )


def test_the_ignore_scope_answers_about_its_own_repo_inside_a_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`git -C <root>` reads as "definitely this repository" and is not: an absolute
    `GIT_DIR` outranks it. Under the unfixed code this returned the OTHER repository's
    ignore list, so the scope excluded paths that do not exist here and admitted the ones
    that should have been excluded.

    @brief `.gitignore` exclusions are read from the target repo, not the hook's.
    @return None.
    @version 1
    """
    repo = _repo(tmp_path / "target")
    _as_if_inside_a_hook(monkeypatch, tmp_path / "foreign")

    excluded = {p.resolve() for p in scope.whole_repo_scope(repo).excludes}
    assert (repo / "ignored").resolve() in excluded, (
        "the ignored directory belongs to THIS repo's .gitignore; a hook's GIT_DIR must "
        "not decide what this index excludes"
    )


def test_the_tracked_file_listing_answers_about_its_own_repo_inside_a_hook(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`cwd=<repo_root>` is overridden by an absolute `GIT_DIR` just as `-C` is, and the
    consequence is worse here because the result is used as a MEMBERSHIP test: every file
    in the target repository reads as untracked, so `propose_declaration` reports a
    correctly-indexed repo as indexing nothing it tracks.

    @brief `tracked_files` lists the target repo's files, not the hook's.
    @return None.
    @version 1
    """
    repo = _repo(tmp_path / "target")
    _as_if_inside_a_hook(monkeypatch, tmp_path / "foreign")

    tracked = tracked_files(repo)
    assert tracked is not None, "a real repository must not read as 'git unavailable'"
    assert "kept.c" in tracked
