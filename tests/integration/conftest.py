# SPDX-License-Identifier: MIT
"""Opt-in integration tier: the REAL pipeline over REAL source.

The default suite is hermetic — it builds its databases from the pipeline's own
DDL creators and never runs doxygen. That is fast and it is honest about most of
what it tests, but three things cannot be tested that way at all:

  1. **Incrementality.** The index cache's whole job is to classify a real tree
     of real files across two real builds. A synthetic database has no tree.
  2. **Degradation on imperfect input.** "A garbage-tailed C file must not fail
     the build" is a claim about what doxygen and tree-sitter actually do.
  3. **Fixture fidelity.** A synthetic fixture can silently rot away from the
     schema the extractors really emit, and every test built on it keeps
     passing. `test_fixture_fidelity.py` is the tripwire, and it is the reason
     this tier exists at all.

Two independent sources of real source feed the tier:

  * **This checkout** (`self_index_db`) — needs NO NETWORK, so the two tests
    that matter most (self-index counts, fixture fidelity) are unconditionally
    runnable. It is ourselves; there is nothing to be flaky about.
  * **A PINNED commit of `tvanfossen/doxygen-guard`** (`guard_repo`) — a second,
    independent repo. Chosen because it ships a `.doxygen-guard.yaml` and a
    doxygen-guard pre-commit hook but **no Doxyfile**, so every build through it
    exercises the #33 Doxyfile-synthesis path that nothing else covers.

**This tier runs NOWHERE automatically.** It is opt-in via `--integration`, and the
pre-commit pytest hook does not pass it. Running it is a deliberate local act.

**Environment failures are not test failures.** Both preconditions (a `doxygen`
binary, a reachable git remote) raise a named subclass of
`IntegrationEnvironmentError` from a FIXTURE, so pytest reports them as ERRORs
carrying the class name rather than as assertion FAILUREs — a named error tells
you which precondition was missing without re-running anything.

@brief Session fixtures for the opt-in real-pipeline integration tier.
@version 1
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

## This checkout — the network-free integration target.
REPO_ROOT = Path(__file__).resolve().parents[2]

## The second, independent target repo.
GUARD_REPO_URL = "https://github.com/tvanfossen/doxygen-guard.git"

## PINNED COMMIT — never a branch. An integration tier that moves when somebody
## else pushes to another repo is a flaky tier, and a flaky required job gets
## ignored, which defeats the point of having one. This is the commit tagged
## `v1.2.9`, which is the exact doxygen-guard release this project's venv and
## its own pre-commit hook pin (`doxygen-guard>=1.2.9`), so the fixture and the
## dependency cannot drift apart. Recorded as the raw SHA rather than the tag
## because a tag is a movable ref and a SHA is not.
GUARD_REPO_SHA = "c43cdb0b9825af5071e051ab65924e660d7b8712"

## Per-git-command ceiling. A hung fetch must fail as a clone problem, not sit
## in CI until the job's own timeout kills it with no diagnosis.
GIT_TIMEOUT_SECONDS = 180


## @brief The tier could not be SET UP — distinct from a code regression.
## @version 1
class IntegrationEnvironmentError(RuntimeError):
    """Base class for "the preconditions were not met".

    Raised from a fixture, so pytest reports an ERROR (not a FAILURE) whose text
    names the concrete subclass. That is the hook CI keys off to tell "the
    network is down" apart from "the pipeline broke".

    @brief Integration precondition failure.
    @version 1
    """


## @brief No usable `doxygen` binary on PATH.
## @version 1
class DoxygenUnavailableError(IntegrationEnvironmentError):
    """Deliberately an ERROR rather than a `pytest.skip`.

    Passing `--integration` is an explicit request to run the real-pipeline tier;
    silently skipping it would report green while testing nothing. A skip is
    invisible, an error is not.

    @brief Missing doxygen binary.
    @version 2
    """


## @brief The pinned commit could not be fetched.
## @version 1
class CloneUnavailableError(IntegrationEnvironmentError):
    """No network, no git, or the remote refusing the pinned SHA. Nothing about
    this repo's code can cause it, which is why it is a named class rather than
    an assertion failure.

    @brief Pinned-commit fetch failure.
    @version 2
    """


## @brief Run one git command inside a directory, mapping every failure mode.
## @param cwd Directory to run git in.
## @param args git arguments (without the leading "git").
## @return The command's stdout.
## @version 1
def _git(cwd: Path, *args: str) -> str:
    """Any non-zero exit, missing binary or timeout becomes
    `CloneUnavailableError` carrying git's own stderr — the message has to be
    enough to tell a proxy rejection apart from a deleted commit without
    re-running anything.

    @brief Invoke git, raising CloneUnavailableError on any failure.
    @version 1
    """
    try:
        done = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CloneUnavailableError(f"git {' '.join(args)} could not run: {exc}") from exc
    if done.returncode != 0:
        raise CloneUnavailableError(
            f"git {' '.join(args)} failed (rc={done.returncode}) in {cwd}: {done.stderr.strip()}",
        )
    return done.stdout


## @brief Refuse the whole tier up front when doxygen is absent.
## @return None.
## @version 1
@pytest.fixture(scope="session", autouse=True)
def require_doxygen() -> None:
    """Autouse and session-scoped so the diagnosis arrives once, before any
    build burns time, rather than as N identical mid-build tracebacks.

    @brief Assert a doxygen binary exists.
    @version 1
    """
    if shutil.which("doxygen") is None:
        raise DoxygenUnavailableError(
            "no `doxygen` binary on PATH — the integration tier runs the real "
            "pipeline. Install doxygen (>= 1.9.8, built with sqlite3 output) or "
            "drop --integration to run the hermetic suite only.",
        )


## @brief A read-only checkout of the pinned doxygen-guard commit.
## @param tmp_path_factory pytest's session-scoped temp directory factory.
## @return Path to the checkout.
## @version 1
@pytest.fixture(scope="session")
def guard_checkout(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Fetches the SHA directly (`fetch --depth 1 origin <sha>`) instead of
    cloning a branch and checking out. Three reasons: it transfers one commit
    rather than a history, it never materializes a branch tip that could differ
    from the pin, and it fails loudly if the commit is gone instead of silently
    landing on whatever `main` happens to be.

    Submodules are deliberately NOT initialized — the target declares one, and
    a second remote would be a second thing that can be unreachable. The pinned
    commit's own tree is what the tier indexes.

    Session-scoped: one fetch serves every test, and `guard_repo` hands out
    writable copies.

    @brief Fetch the pinned commit once per session.
    @version 1
    """
    root = tmp_path_factory.mktemp("doxygen-guard-pinned")
    _git(root, "init", "--quiet", ".")
    _git(root, "remote", "add", "origin", GUARD_REPO_URL)
    _git(root, "fetch", "--quiet", "--depth", "1", "origin", GUARD_REPO_SHA)
    _git(root, "checkout", "--quiet", "FETCH_HEAD")
    head = _git(root, "rev-parse", "HEAD").strip()
    if head != GUARD_REPO_SHA:
        raise CloneUnavailableError(
            f"fetched {head} but the pin is {GUARD_REPO_SHA} — refusing to test "
            "against an unpinned tree",
        )
    return root


## @brief A writable per-test copy of the pinned checkout.
## @param guard_checkout The session-scoped pinned checkout.
## @param tmp_path Per-test temp directory.
## @return Path to the writable copy.
## @version 1
@pytest.fixture
def guard_repo(guard_checkout: Path, tmp_path: Path) -> Path:
    """The incremental-cache tests edit, touch and delete files, so each one
    needs its own tree. `.git` is excluded: the pipeline reads declarations off
    the filesystem and a copied `.git` would only add weight and a second
    identity for the same content.

    @brief Stage a writable copy of the pinned target repo.
    @version 1
    """
    root = tmp_path / "doxygen-guard"
    shutil.copytree(guard_checkout, root, ignore=shutil.ignore_patterns(".git"))
    return root


## @brief A real, cold, full index of THIS checkout.
## @param tmp_path_factory pytest's session-scoped temp directory factory.
## @return Path to the built database.
## @version 1
@pytest.fixture(scope="session")
def self_index_db(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Needs no network, so every test built on it is unconditionally required.

    Built at the DEFAULT `from-guard` scope and naming no Doxyfile: this repo ships
    none, so the scope comes from its own doxygen-guard hook declaration and a
    Doxyfile is synthesized (#33) — the same path a stranger's guard-enforced repo
    takes. An uncached build makes it a true cold build that no sidecar from a
    previous run can influence.

    THE TWO FLAGS THIS USED TO PASS ARE GONE (22->6 collapse) and neither value is:
    `from-guard` is now the parser's default and is asserted as such by
    `tests/test_scope.py`, and `no_index_cache` stays a surviving dest. Restating the
    default here would have hidden a change to it, which is how the gh#333 inversion
    reached two different doors in the first place.

    @brief Index this repository with the real pipeline.
    @version 2
    """
    out = tmp_path_factory.mktemp("self-index") / "clew.db"
    args = _build_argparser().parse_args(["--repo-root", str(REPO_ROOT), "--output", str(out)])
    args.no_index_cache = True
    _run_pipeline(args)
    return out
