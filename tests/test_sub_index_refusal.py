# SPDX-License-Identifier: MIT
"""gh#35 — a `sub_index` name that matches nothing built the WHOLE repository.

WHAT WAS OBSERVED on 1.0.32, against a repository vendoring nine submodules:

    index(action='refresh', target=B12_single_rgb, sub_index='no-such-tree')

did not refuse. It registered a new slug `B12_single_rgb-8d7b2c.no-such-tree`, TOOK THE
REPOSITORY'S BUILD LOCK, and began building the whole repository into it — boost, opencv and
pcl included, only gitignore excludes applied — until clew's own cap killed doxygen at
900 s. A legitimate `refresh(sub_index='deps-tinyfsm')` issued in parallel queued behind the
lock for the full fifteen minutes; its own build took 3.5 s once the lock freed. Every other
session's auto-refresh on that repository was blocked for the duration, and stopping the MCP
call client-side did not stop the server-side doxygen.

THE MECHANISM WAS A BRANCH MEANT FOR SOMETHING ELSE. `_sub_index_scope` logs "no longer
matches any nested tree — building with the caller's scope instead of a derived one" and
proceeds, which is a reasonable reading of "a submodule was removed since this sub-index was
registered". It also fires for a name that never matched anything, and the caller's scope for
a sub-index build IS the whole repository — so a typo widens instead of narrowing. That is
#511's silent-narrowing failure run in reverse, and it costs more: narrowing produces a small
index that reports healthy, while this produces a fifteen-minute lock on a shared resource.

TWO LAYERS, DELIBERATELY. `_sub_index_rejection` refuses BEFORE the lock is taken, which is
the only place a refusal helps a caller who mistyped; `_sub_index_scope` raises rather than
widening, so no other path into it can reintroduce the whole-repo build. That mirrors gh#26,
where the shape check moved earlier and the pipeline kept its own.

@brief Tests for the refusal of a sub_index name that names no buildable tree.
@version 1
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from clew.scope import FIRST_PARTY_INDEX


##
# @brief A repository with two vendored submodules, so the split has real names.
# @param root Directory to build the repository in.
# @return The resolved repository root.
# @version 1
def _split_repo(root: Path) -> Path:
    """@brief Two nested gitlink trees plus first-party code.
    @return The repo root, resolved.
    @version 1
    """
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    for name in ("tinyfsm", "libIoT"):
        nested = root / "deps" / name
        nested.mkdir(parents=True)
        (nested / ".git").write_text(f"gitdir: ../../.git/modules/{name}\n", encoding="utf-8")
    return root.resolve()


def test_a_sub_index_name_that_matches_nothing_is_refused(tmp_path: Path) -> None:
    """THE REFUSAL NAMES THE ALTERNATIVES, because a caller who mistyped a name cannot
    discover the right one from anywhere else — gh#38 is the same gap seen from `targets`.
    A bare "unknown sub_index" would cost the round trip that the fifteen-minute build cost.

    @brief An unmatched name is rejected, and the message lists what is buildable.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_rejection
    from clew.mcp_server.state import target_for

    repo = _split_repo(tmp_path / "repo")
    bogus = target_for(repo, tmp_path / "state", name="no-such-tree")

    rejection = _sub_index_rejection(bogus, repo)
    assert rejection is not None, "a name matching no nested tree must be refused"
    assert "no-such-tree" in rejection, "the refusal must quote the name that failed"
    for buildable in (FIRST_PARTY_INDEX, "deps-tinyfsm", "deps-libIoT"):
        assert buildable in rejection, f"the refusal must name {buildable!r} as an alternative"


def test_every_derived_name_is_accepted(tmp_path: Path) -> None:
    """THE CONTROL, and the half a refusal gets wrong most easily. A check that rejected a
    legitimate vendored name would make the split unbuildable, which is worse than the defect
    it replaced.

    @brief First-party and each derived vendored name pass.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_rejection
    from clew.mcp_server.state import target_for

    repo = _split_repo(tmp_path / "repo")
    for name in (FIRST_PARTY_INDEX, "deps-tinyfsm", "deps-libIoT"):
        target = target_for(repo, tmp_path / "state", name=name)
        assert _sub_index_rejection(target, repo) is None, f"{name!r} is buildable and was refused"


def test_a_whole_repo_target_is_never_refused(tmp_path: Path) -> None:
    """`name is None` is the unnamed target, which every repository has and which this check
    must not touch — it is also the only shape that existed before sub-indexes, so refusing it
    would strand every index on disk.

    @brief An unnamed target passes without consulting the split at all.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_rejection
    from clew.mcp_server.state import target_for

    repo = _split_repo(tmp_path / "repo")
    assert _sub_index_rejection(target_for(repo, tmp_path / "state"), repo) is None


def test_an_unsplit_repository_refuses_any_sub_index_by_saying_so(tmp_path: Path) -> None:
    """A REPOSITORY WITH NOTHING VENDORED HAS NO SUB-INDEXES AT ALL — `derive_sub_indexes`
    returns [] to mean "do not split" — so every name is wrong and the honest message is that
    this repository is not split, not a list of zero alternatives.

    @brief The refusal for an unsplit repo says the repo is unsplit.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_rejection
    from clew.mcp_server.state import target_for

    repo = tmp_path / "plain"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.c").write_text("int a(void){return 0;}\n", encoding="utf-8")
    target = target_for(repo.resolve(), tmp_path / "state", name="anything")

    rejection = _sub_index_rejection(target, repo.resolve())
    assert rejection is not None
    assert "not split" in rejection.lower(), f"say the repo is unsplit, got: {rejection}"


def test_the_refusal_happens_before_the_build_lock_is_taken(tmp_path: Path) -> None:
    """THE WHOLE POINT OF THE ISSUE. The damage was not the wasted build, it was holding a
    shared repository's build lock for fifteen minutes: a legitimate sub-index refresh queued
    behind it, and so did every other session's auto-refresh. A refusal after the lock would
    fix the wasted work and leave the contention exactly as it was.

    `build_lock` is replaced with something that fails if it is ever entered, so the assertion
    is about ORDER rather than about the message.

    @brief A refused sub_index never reaches the build lock.
    @return None.
    @version 1
    """
    from clew.mcp_server import server as srv
    from clew.mcp_server.state import target_for

    repo = _split_repo(tmp_path / "repo")
    bogus = target_for(repo, tmp_path / "state", name="no-such-tree")

    def _explode(_db: Path):  # noqa: ANN202 - a stand-in that must never be called
        raise AssertionError("the build lock was taken for a sub_index that names nothing")

    original = srv.build_lock
    srv.build_lock = _explode
    try:
        instance = srv.DocsDbServer.__new__(srv.DocsDbServer)
        result = instance._run_build(bogus, doxyfile=None)
    finally:
        srv.build_lock = original

    assert result["ok"] is False, "a refused build must not report ok"
    assert result["built"] is False
    assert "no-such-tree" in result["error"]


def test_the_scope_helper_raises_rather_than_widening(tmp_path: Path) -> None:
    """DEFENCE IN DEPTH, and the reason it is not redundant: `_sub_index_scope` is reachable
    from any future caller, and its unmatched branch returned the caller's scope — which for a
    sub-index build is the whole repository. A helper that silently answers "build everything"
    when asked "what is the scope of this part" is wrong regardless of who calls it.

    @brief The unmatched branch refuses instead of returning a whole-repo scope.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = _split_repo(tmp_path / "repo")
    bogus = target_for(repo, tmp_path / "state", name="no-such-tree")

    with pytest.raises(ValueError, match="no-such-tree"):
        _sub_index_scope(bogus, repo, None, None)


def test_a_registered_sub_index_whose_tree_vanished_refuses_and_names_the_route(
    tmp_path: Path,
) -> None:
    """THE CASE THE WIDENING BRANCH WAS WRITTEN FOR, and it still must not widen. A submodule
    removed since its sub-index was built leaves a database describing code that is no longer
    in the tree. Building it whole would turn that sub-index into a second copy of the
    repository; building it narrow is impossible, because there is no tree to narrow to.

    So it refuses — and says which route clears the leftover, because a caller told only "no"
    about an index they legitimately built once has nowhere to go.

    @brief A vanished tree is refused with the cull route named.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_rejection
    from clew.mcp_server.state import target_for

    repo = _split_repo(tmp_path / "repo")
    gone = target_for(repo, tmp_path / "state", name="deps-removed")
    db = Path(gone.db_path)
    db.parent.mkdir(parents=True, exist_ok=True)
    db.write_bytes(b"")

    rejection = _sub_index_rejection(gone, repo)
    assert rejection is not None, "a vanished tree must not build the whole repository"
    assert "cull" in rejection, f"name the route that clears the leftover, got: {rejection}"
    assert "deps-removed" in rejection


def test_culling_one_dead_sub_index_leaves_its_healthy_siblings_alone(
    tmp_path: Path, rich_db: Path
) -> None:
    """FOUND WHILE FIXING gh#35's LEFTOVER, and worse than the leftover. `cull` evaluates each
    target individually and then calls `registry.drop(target.repo_path)`, which drops EVERY
    entry sharing that repo path AND `rmtree`s each one's database directory. So culling the
    dead slug the bogus build left behind also deletes the repository's first-party index and
    every vendored sub-index beside it — a sweep meant to reclaim one abandoned directory takes
    out the working indexes it was called to preserve.

    `drop`'s breadth is right for `drop`: a caller passing a repo root means "forget this repo".
    It is wrong as the implementation of a per-target decision, and it is the loop above it that
    makes it wrong.

    @brief A cull removes only the target it judged, not its siblings.
    @return None.
    @version 1
    """
    from clew.mcp_server import state as st

    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "repo"
    repo.mkdir()
    healthy = reg.register(repo, name=FIRST_PARTY_INDEX)
    dead = reg.register(repo, name="deps-abandoned")
    Path(healthy.db_path).write_bytes(rich_db.read_bytes())
    ## `dead` gets the leftovers of a killed build and no database at all.
    leftovers = Path(dead.db_path).parent
    leftovers.mkdir(parents=True, exist_ok=True)
    (leftovers / "clew.db.buildlock").write_text("", encoding="utf-8")
    (leftovers / "clew.db.buildlog").write_text("killed at 900 s\n", encoding="utf-8")

    culled = st.cull(reg, max_age_days=None)

    assert [c["repo_path"] for c in culled], "the never-built sub-index must be culled"
    names = {t.name for t in reg.targets()}
    assert FIRST_PARTY_INDEX in names, "culling a dead sibling dropped the healthy index"
    assert "deps-abandoned" not in names, "the dead sub-index is still registered"
    assert Path(healthy.db_path).exists(), "the healthy database was deleted from disk"
    assert not leftovers.exists(), "the killed build's leftover directory was not reclaimed"


##
# @brief A repository whose vendored tree vendors more of its own.
# @param root Directory to build the repository in.
# @return The resolved repository root.
# @version 1
def _nested_split_repo(root: Path) -> Path:
    """DEPTH MATTERS HERE, unlike `_split_repo`. gh#41 is about a refusal that listed every
    name the recursive split reaches — ~300 on the reporting repository, including every boost
    sub-library — so the fixture needs names at two levels to tell top-level from deep.

    @brief Two top-level trees, one of which holds three of its own.
    @return The repo root, resolved.
    @version 1
    """
    (root / "app").mkdir(parents=True)
    for name in ("tinyfsm", "vendor"):
        nested = root / "deps" / name
        nested.mkdir(parents=True)
        (nested / ".git").write_text(f"gitdir: ../../.git/modules/{name}\n", encoding="utf-8")
    for child in ("alpha", "beta", "gamma"):
        deep = root / "deps" / "vendor" / "sub" / child
        deep.mkdir(parents=True)
        (deep / ".git").write_text(f"gitdir: x/{child}\n", encoding="utf-8")
    return root.resolve()


def test_a_refused_sub_index_registers_nothing(tmp_path: Path) -> None:
    """gh#40. THE REFUSAL LANDED AFTER REGISTRATION, so a mistyped name still created
    `~/.local/state/clew/targets/<repo>.<bogus>/` and a four-line `targets.json` entry — and
    `index(action='targets')` then listed a slug that had never been built and never would be.
    A refusal that leaves a trace is a refusal the operator has to clean up by hand, which is
    what the reporter did.

    `_build_subject` registers because a build needs somewhere to write. Nothing needs
    somewhere to write when there is nothing to build, so the name is checked first.

    @brief A refused name allocates no slug, no directory, no registry entry.
    @return None.
    @version 1
    """
    from clew.mcp_server import server as srv
    from clew.mcp_server import state as st

    repo = _split_repo(tmp_path / "repo")
    state = tmp_path / "state"
    registry = st.TargetRegistry(state)
    instance = srv.DocsDbServer.__new__(srv.DocsDbServer)
    instance.registry = registry

    with pytest.raises(RuntimeError, match="no-such-tree"):
        asyncio.run(instance._build_subject(None, str(repo), "no-such-tree"))

    assert registry.targets() == [], "a refused sub_index must leave the registry untouched"
    stray = [p.name for p in state.glob("targets/*") if "no-such-tree" in p.name]
    assert stray == [], f"a refused sub_index must allocate no directory, found {stray}"


def test_a_legitimate_sub_index_still_registers(tmp_path: Path) -> None:
    """THE CONTROL. The check runs before registration, so getting it wrong would make every
    sub-index unbuildable rather than merely leaving litter behind.

    @brief A derived name registers and allocates as before.
    @return None.
    @version 1
    """
    from clew.mcp_server import server as srv
    from clew.mcp_server import state as st

    repo = _split_repo(tmp_path / "repo")
    registry = st.TargetRegistry(tmp_path / "state")
    instance = srv.DocsDbServer.__new__(srv.DocsDbServer)
    instance.registry = registry

    resolved = asyncio.run(instance._build_subject(None, str(repo), "deps-tinyfsm"))
    assert resolved is not None and resolved.name == "deps-tinyfsm"
    assert [t.name for t in registry.targets()] == ["deps-tinyfsm"]
    assert Path(resolved.db_path).parent.is_dir(), "the build still needs somewhere to write"


def test_the_refusal_names_top_level_trees_and_counts_the_rest(tmp_path: Path) -> None:
    """gh#41. THE LIST WAS CORRECT AND UNREADABLE: ~300 names in one error string on the
    reporting repository, including every boost sub-library from `-accumulators` to `-yap` and
    a libBissellIoT transitive dependency 96 characters long. A caller who mistyped
    `deps-tinyfsm` cannot find it in that.

    THE DEEP NAMES ARE STILL REACHABLE, and the message says how they are spelled rather than
    enumerating them — the same choice `_bounded_output` makes about repeated warning lines:
    one example plus a count beats the full set.

    @brief The refusal lists top-level names and counts what is under them.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_rejection
    from clew.mcp_server.state import target_for

    repo = _nested_split_repo(tmp_path / "repo")
    bogus = target_for(repo, tmp_path / "state", name="typo")

    rejection = _sub_index_rejection(bogus, repo)
    assert rejection is not None
    for top in (FIRST_PARTY_INDEX, "deps-tinyfsm", "deps-vendor"):
        assert top in rejection, f"the top-level name {top!r} must be offered"
    for deep in ("deps-vendor-sub-alpha", "deps-vendor-sub-beta", "deps-vendor-sub-gamma"):
        assert deep not in rejection, f"{deep!r} is a nested name and must not be enumerated"
    assert "3" in rejection, "the count of nested names under deps-vendor must be reported"
