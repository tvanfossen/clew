# SPDX-License-Identifier: MIT
"""What the registry accumulates, found by reading a real one.

Asked to review open issues with none on the tracker, I read the state this machine's own server
had built up. Three shapes, all checkable:

  * ONE REPOSITORY, TWO ROWS. The registry was keyed by repo path and is now keyed by slug.
    `register` writes the slug row and never removes the legacy one, so `entropic` appeared twice
    in `index(action='targets')` and twice in every sibling lookup. It is not cosmetic: the two
    rows are the same database, so a reader counting targets counts one repository twice.
  * A ROW FOR `$HOME`, NEVER BUILT, with no state directory — a survivor of the era when merely
    RESOLVING a target registered it (gh#1). `cull` can drop it, and the control below pins that,
    but only when called in a way that does not also delete perfectly good version-stale indexes.
  * INDEXES ON DISK THAT THE REGISTRY DOES NOT KNOW. A CLI build writes where the server reads —
    that is the whole point of the derived `--output` — and then registers nothing, so
    `index(action='targets')` does not list it. Two of this machine's six built indexes were
    invisible that way.

@brief Tests for registry de-duplication, ghost rows and CLI registration.
@version 1
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from clew.mcp_server.state import REGISTRY_NAME, TargetRegistry, cull, target_for
from clew.signature import write_build_signature


## @brief Write a registry holding the same target under BOTH key shapes.
## @param home State root to write under.
## @param repo The repository both rows describe.
## @return The path of the registry file.
## @version 1
def _legacy_and_slug_rows(home: Path, repo: Path) -> Path:
    """The legacy shape is what `register` wrote before slugs became the key: the repo path as
    the key and no `repo_path` field. Both rows carry the SAME slug, because the slug is derived
    from the path and that derivation is frozen.

    @brief Build a registry with a duplicated target.
    @return The registry path.
    @version 1
    """
    target = target_for(repo, home)
    home.mkdir(parents=True, exist_ok=True)
    path = home / REGISTRY_NAME
    path.write_text(
        json.dumps(
            {
                str(repo): {"slug": target.slug, "db_path": target.db_path},
                target.slug: {
                    "slug": target.slug,
                    "db_path": target.db_path,
                    "repo_path": str(repo),
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_one_repository_registered_twice_is_listed_once(tmp_path: Path) -> None:
    """READ-SIDE, so an existing registry is fixed without waiting for a rebuild. Whoever is
    holding a duplicated registry today gets one row per repository on the next call.

    @brief A legacy row and its slug row resolve to a single target.
    @version 1
    """
    home, repo = tmp_path / "state", tmp_path / "repo"
    repo.mkdir()
    _legacy_and_slug_rows(home, repo)

    targets = TargetRegistry(home).targets()

    assert [t.slug for t in targets] == [target_for(repo, home).slug], targets
    assert targets[0].repo_path == str(repo), "the surviving row must carry the repository path"


def test_registering_removes_the_legacy_row_it_supersedes(tmp_path: Path) -> None:
    """WRITE-SIDE, so the duplicate does not come back. Only the row for the SAME slug is
    dropped — a registry holding several repositories keeps them all.

    @brief A whole-repo registration drops its own legacy key and nothing else.
    @version 1
    """
    home, repo, other = tmp_path / "state", tmp_path / "repo", tmp_path / "other"
    repo.mkdir()
    other.mkdir()
    _legacy_and_slug_rows(home, repo)
    registry = TargetRegistry(home)
    registry.register(other)

    registry.register(repo)

    stored = json.loads((home / REGISTRY_NAME).read_text())
    assert str(repo) not in stored, f"the legacy row survived: {sorted(stored)}"
    assert target_for(repo, home).slug in stored
    assert target_for(other, home).slug in stored, "another repository's row must be untouched"


def test_cull_drops_a_never_built_row_without_touching_a_current_index(tmp_path: Path) -> None:
    """THE CONTROL, and the answer to "how do I get rid of the `$HOME` row". `cull` already
    drops a target whose database does not exist — but its DEFAULTS also delete every index
    built by an older pipeline, which on this machine was three healthy ones. So the remedy is
    the narrow call, and this pins both halves of it.

    @brief cull(max_age_days=None, include_stale=False) removes only rows with no database.
    @version 1
    """
    home = tmp_path / "state"
    ghost, built = tmp_path / "home_dir", tmp_path / "built"
    ghost.mkdir()
    built.mkdir()
    registry = TargetRegistry(home)
    registry.register(ghost)
    target = registry.register(built)
    write_build_signature(Path(target.db_path))

    culled = cull(registry, max_age_days=None, include_stale=False)

    assert [row["repo_path"] for row in culled] == [str(ghost)], culled
    assert [t.repo_path for t in registry.targets()] == [str(built)]
    assert Path(target.db_path).is_file(), "the built index must survive"


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="asserted against a real build")
def test_a_cli_build_registers_the_target_it_wrote(tmp_path: Path) -> None:
    """THE INVISIBLE INDEX. `clew --repo-root X` with no `--output` writes exactly where the
    server reads — `test_omitted_output_resolves_to_the_servers_own_path` pins that — and then
    registered nothing, so `index(action='targets')` did not list it and `cull` could not reach
    it. Two of this machine's six built indexes were in that state.

    REGISTERED AFTER THE BUILD, not at argument resolution: registration is the claim that a
    database is there, and a failed build must not make it.

    @brief A CLI build into the served location registers its repository.
    @version 1
    """
    from clew.cli import build_index

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "unit.c").write_text("/** @brief unit. */\nint unit(void) { return 0; }\n")
    subprocess.run(["git", "init", "-q", "."], cwd=repo, check=True)
    home = TargetRegistry().home
    derived = target_for(repo, home)

    build_index(output=derived.db_path, repo_root=repo)

    assert Path(derived.db_path).is_file(), "premise: the build landed at the served path"
    assert [t.repo_path for t in TargetRegistry(home).targets()] == [str(repo.resolve())]


def test_a_build_written_somewhere_else_registers_nothing(tmp_path: Path) -> None:
    """THE COUNTER-CASE. `--output /somewhere/mine.db` is a database the server does not read,
    so recording it as a target would list a repository whose index no query can reach — and the
    acceptance harness builds exactly that way.

    @brief A build outside the served location leaves the registry alone.
    @version 1
    """
    from clew.cli import _register_built_target

    repo = tmp_path / "repo"
    repo.mkdir()
    elsewhere = tmp_path / "mine.db"
    elsewhere.write_bytes(b"")

    _register_built_target(str(repo), elsewhere)

    assert TargetRegistry().targets() == []
