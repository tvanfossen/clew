# SPDX-License-Identifier: MIT
"""A gate that reports green while checking nothing.

**THIS SHIPPED A RED RELEASE.** `843764f` added 1,637 acceptance artifacts. The gate had been
run — `pre-commit run --all-files`, green — and then the files were staged and committed. The
release workflow went red on all three interpreters because `end-of-file-fixer` rewrote files the
local run had never looked at.

TWO SEPARATE HOLES PRODUCED ONE FAILURE, and either alone is enough to do it again:

  - **`--all-files` means all TRACKED files.** pre-commit asks git for the index, so a file that
    is untracked at the moment the gate runs is invisible to it. "Green on the tree" was in fact
    "green on the subset of the tree git already knew about."
  - **No commit-time hook was installed at all.** `.git/hooks/pre-commit` did not exist, so the
    staged files were never gated either. Every green in this repository's history was a human
    remembering to run `--all-files` by hand. That is not a gate, it is a habit.

The second one is the root cause and it cannot be fixed by a file in the repository — `.git/hooks`
is not version controlled. What a repository CAN do is refuse to call itself green while the
commit-time gate is missing, which is why that check is here rather than in a README someone
reads once.

**WHY THE EXCLUDE LIST IS READ RATHER THAN RESTATED.** The set of paths the hooks cover is
defined by the global `exclude:` in `.pre-commit-config.yaml`. A second copy of that regex here
would be a second place to edit, and the first time they disagreed this guard would either block
a legitimate untracked artifact or wave through the exact class of file that caused the incident.

@brief The gate must refuse to report green while it cannot see the whole tree.
@version 1
"""

from __future__ import annotations

import importlib.util
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


##
# @brief Load the gate-hygiene script as a module without making `scripts/` a package.
# @return The loaded module.
# @version 1
# @dg_internal
def _load() -> ModuleType:
    """`scripts/` has no `__init__.py` and should not grow one just to be imported by a test, so
    the file is loaded by path. Failing here is a legitimate RED — the script not existing and
    the script being wrong are the same defect from the gate's point of view.

    @brief Load `scripts/gate_hygiene.py`.
    @return The module.
    @version 1
    """
    path = REPO_ROOT / "scripts" / "gate_hygiene.py"
    spec = importlib.util.spec_from_file_location("gate_hygiene", path)
    assert spec is not None and spec.loader is not None, f"cannot load {path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gate_hygiene = _load()


##
# @brief Build a throwaway git repository with a pre-commit config.
# @param root Directory to initialise.
# @param exclude Body of the global exclude alternation, or None for no exclude.
# @return None.
# @version 1
# @dg_internal
def _repo(root: Path, exclude: str | None = None) -> None:
    """A REAL `git init`, not a stub. The question asked is what `git ls-files --others
    --exclude-standard` reports, and that is git's answer about `.gitignore`, nested repositories
    and its own internals — none of which a fake would get right.

    @brief Initialise a git repository with a config.
    @param root Directory to initialise.
    @param exclude Exclude alternation body.
    @return None.
    @version 1
    """
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    block = f"exclude: |\n  (?x)^(\n    {exclude}\n  )$\n" if exclude else ""
    (root / ".pre-commit-config.yaml").write_text(f"---\n{block}repos: []\n", encoding="utf-8")


##
# @brief An untracked file the hooks would cover must fail the guard.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_untracked_file_under_a_hook_covered_path_is_reported(tmp_path: Path) -> None:
    """This is the incident, reduced: a file on disk that the hooks apply to and that `--all-files`
    cannot see. The config is written but never committed, so it is itself untracked — the guard
    must therefore report it too, and the assertion names the artifact rather than the count so a
    future change that reports the wrong path cannot pass.

    @brief An untracked covered file is reported.
    @return None.
    @version 1
    """
    _repo(tmp_path)
    (tmp_path / "evidence.json").write_text("{}", encoding="utf-8")

    reported = gate_hygiene.untracked_but_covered(tmp_path)

    assert "evidence.json" in reported, (
        f"the guard did not report an untracked file the hooks cover; reported {reported}"
    )


##
# @brief An untracked file inside the global exclude must not be reported.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_untracked_file_under_the_global_exclude_is_not_reported(tmp_path: Path) -> None:
    """`acceptance/runs/` is excluded on purpose — you do not reformat frozen evidence — so an
    untracked file there is not a hole, it is the design. A guard that could not tell these apart
    would fire on every acceptance run and be switched off within a day, which is the failure mode
    this check exists to prevent.

    @brief An excluded untracked file is ignored.
    @return None.
    @version 1
    """
    _repo(tmp_path, exclude=r"acceptance/runs/.*")
    (tmp_path / "acceptance" / "runs" / "r1").mkdir(parents=True)
    (tmp_path / "acceptance" / "runs" / "r1" / "provision.json").write_text("{}", encoding="utf-8")

    reported = gate_hygiene.untracked_but_covered(tmp_path)

    assert not [p for p in reported if p.startswith("acceptance/runs/")], (
        f"the guard reported an excluded path as a hole; reported {reported}"
    )


##
# @brief A gitignored file is not a gate hole.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_gitignored_file_is_not_reported(tmp_path: Path) -> None:
    """The hooks never see a gitignored file either, so it is not a gap between what the gate
    checked and what the commit carries. `--exclude-standard` is what makes git answer this, and
    asserting it here is what stops someone "simplifying" to a plain `--others`.

    @brief A gitignored untracked file is ignored.
    @return None.
    @version 1
    """
    _repo(tmp_path)
    (tmp_path / ".gitignore").write_text("build/\n", encoding="utf-8")
    (tmp_path / "build").mkdir()
    (tmp_path / "build" / "out.json").write_text("{}", encoding="utf-8")

    reported = gate_hygiene.untracked_but_covered(tmp_path)

    assert "build/out.json" not in reported, (
        f"a gitignored path was reported as a gate hole; reported {reported}"
    )


##
# @brief A repository with no commit-time hook installed must be reported as ungated.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_a_repository_without_the_commit_time_hook_is_reported(tmp_path: Path) -> None:
    """A FRESH CLONE IS THE DEFAULT STATE, which is the whole point: nobody has to do anything
    wrong for this to be true. `pre-commit install` is a per-checkout action and this repository
    went its entire history to 1.1.0 without it.

    @brief A missing commit-time hook is reported.
    @return None.
    @version 1
    """
    _repo(tmp_path)

    assert not gate_hygiene.commit_hook_installed(tmp_path), (
        "a repository with no .git/hooks/pre-commit was reported as gated at commit time"
    )


##
# @brief An installed pre-commit hook must be recognised.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_an_installed_pre_commit_hook_is_recognised(tmp_path: Path) -> None:
    """IT IS NOT ENOUGH FOR THE FILE TO EXIST. Other tools install their own `pre-commit` hook,
    and a check that only tested for the path would call those a pre-commit gate. The file has to
    say it is pre-commit's, so the content is what is asked about.

    @brief An installed hook is recognised.
    @return None.
    @version 1
    """
    _repo(tmp_path)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/usr/bin/env bash\n# start templated\nINSTALL_PYTHON=pre-commit\n", "utf-8")

    assert gate_hygiene.commit_hook_installed(tmp_path), (
        "an installed pre-commit hook was not recognised"
    )


##
# @brief A hook belonging to another tool must not count as the commit-time gate.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_a_foreign_hook_does_not_count_as_the_gate(tmp_path: Path) -> None:
    """The flattering reading of "a file is at `.git/hooks/pre-commit`" is "we are gated". This
    asserts the unflattering one, because reporting a gate that is not there is worse than
    reporting none at all — it is the same defect as a green gate that checked nothing.

    @brief A foreign hook is not the gate.
    @return None.
    @version 1
    """
    _repo(tmp_path)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("#!/bin/sh\nexec make lint\n", encoding="utf-8")

    assert not gate_hygiene.commit_hook_installed(tmp_path), (
        "a hook belonging to another tool was accepted as the pre-commit gate"
    )


##
# @brief The guard must read the exclude regex from the config rather than restating it.
# @return None.
# @version 1
def test_the_guard_reads_this_repository_own_exclude_list() -> None:
    """ANCHORED TO THE REAL CONFIG ON PURPOSE. The parse is the part most likely to rot — the
    exclude is a `(?x)` verbose alternation across lines — and a fixture-only test would keep
    passing after a config change that silently made the pattern match nothing, which is the
    "green while checking nothing" shape again.

    @brief The real config's exclude parses and matches a known excluded path.
    @return None.
    @version 1
    """
    pattern = gate_hygiene.global_exclude(REPO_ROOT / ".pre-commit-config.yaml")

    assert pattern is not None, "this repository has a global exclude and the guard found none"
    assert pattern.match("acceptance/runs/2026-10-19-n3/run.json"), (
        "the parsed exclude does not match a path the config excludes, so the guard would "
        "report frozen evidence as a gate hole"
    )
    assert not pattern.match("clew/cli.py"), (
        "the parsed exclude matches source, so the guard would ignore the files that matter"
    )


##
# @brief The script must exit non-zero when it finds a hole and zero when clean.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
@pytest.mark.parametrize(
    ("make_hole", "expected"),
    [(True, 1), (False, 0)],
    ids=["untracked-file-fails", "clean-tree-passes"],
)
def test_main_exit_code_follows_what_it_found(
    tmp_path: Path, make_hole: bool, expected: int
) -> None:
    """A CHECK THAT CANNOT FAIL THE BUILD IS A COMMENT. The exit code is the only part pre-commit
    reads, so it is asserted directly rather than inferred from the printed text. The clean leg is
    not redundant: a guard wired to always exit 1 would pass the failing leg alone.

    @brief The exit code reflects the finding.
    @return None.
    @version 1
    """
    _repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "add", ".pre-commit-config.yaml"], check=True)
    hook = tmp_path / ".git" / "hooks" / "pre-commit"
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text("# start templated\nINSTALL_PYTHON=pre-commit\n", encoding="utf-8")
    if make_hole:
        (tmp_path / "evidence.json").write_text("{}", encoding="utf-8")

    assert gate_hygiene.main([str(tmp_path)]) == expected


##
# @brief A missing commit-time hook must not fail the run under CI.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_a_missing_hook_does_not_fail_under_ci(tmp_path: Path) -> None:
    """CI CLONES FRESH, so `.git/hooks/pre-commit` is absent there by construction and enforcing
    it would fail every CI run — after which the check gets deleted, which is how a check really
    dies. The claim the check makes is about an interactive checkout.

    `ci` is passed explicitly rather than through the environment: a test that set `CI` would be
    asserting on a global, and the leg that matters most runs *inside* CI where that variable is
    already set to the opposite of what the test wants.

    @brief Under CI the missing hook is reported but not enforced.
    @return None.
    @version 1
    """
    _repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "add", ".pre-commit-config.yaml"], check=True)

    assert gate_hygiene.main([str(tmp_path)], ci=True) == 0, (
        "a fresh CI clone with no installed hook failed the gate; this would be red on every run"
    )
    assert gate_hygiene.main([str(tmp_path)], ci=False) == 1, (
        "an interactive checkout with no commit-time gate was reported as green"
    )


##
# @brief Under CI an untracked covered file must still fail.
# @param tmp_path Pytest temporary directory.
# @return None.
# @version 1
def test_an_untracked_covered_file_still_fails_under_ci(tmp_path: Path) -> None:
    """The CI relaxation is scoped to the hook check alone. The untracked claim holds everywhere —
    a file git does not know about is invisible to the hooks whoever runs them — and a relaxation
    that quietly widened to cover both would restore the original hole under the one condition
    nobody watches.

    @brief The untracked check is enforced under CI too.
    @return None.
    @version 1
    """
    _repo(tmp_path)
    subprocess.run(["git", "-C", str(tmp_path), "add", ".pre-commit-config.yaml"], check=True)
    (tmp_path / "evidence.json").write_text("{}", encoding="utf-8")

    assert gate_hygiene.main([str(tmp_path)], ci=True) == 1, (
        "an untracked file inside the hooks' scope passed the gate under CI"
    )
