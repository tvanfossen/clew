# SPDX-License-Identifier: MIT
"""One repository root may hold several named indexes.

WHY. A repo that vendors its dependencies as submodules pays for them on every build: a target
measured here enumerated 84,500 files for 526 first-party ones, and doxygen alone at ~20 ms/file
is ~28 minutes before clew runs a stage of its own. Splitting the root into per-git-tree indexes
makes the vendored trees IMMUTABLE — they are pinned, so they are built once — and leaves the
recurring loop rebuilding only first-party code.

Measured on `entropic` (public, vendors `extern/llama.cpp`) with nothing but existing flags:
592 files and 13.9 s split, against 3,521 files and 69.0 s whole; and of 4,968 first-party
internal call edges, 13 were lost.

THE ONE PROPERTY THAT CANNOT BREAK is that an UNNAMED target's slug and db path stay exactly what
they are today. The slug is how every already-built index is found — `resolve_target` matches it,
the CLI writes to it, and nothing re-derives it from anything else. A change there does not
migrate old indexes, it strands them, and the symptom would be "no database has been built for
this repo yet" on a repo with a perfectly good index sitting on disk.

So the first test here pins the unnamed spelling against a literal, deliberately: the usual
objection to literals (they break when the rule changes) is the entire point, because the rule
must not change.

@brief Tests for named sub-index targets under one repo root.
@version 1
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from clew.mcp_server.state import target_for


## @brief The slug rule for an unnamed target, restated independently.
## @param repo Resolved repo path.
## @return The expected slug.
## @version 1
def _legacy_slug(repo: Path) -> str:
    """SPELLED OUT HERE rather than imported, so this is a second statement of the rule and not
    a tautology against the implementation.

    @brief Reproduce the historical slug derivation.
    @return `<name>-<sha1[:6]>`.
    @version 1
    """
    digest = hashlib.sha1(str(repo).encode("utf-8")).hexdigest()[:6]
    return f"{repo.name}-{digest}"


## @brief An unnamed target keeps exactly the slug and path it has always had.
## @version 1
def test_an_unnamed_target_is_unchanged(tmp_path: Path) -> None:
    """THE COMPATIBILITY GATE. Every index already on disk lives at a path derived from this
    rule, and nothing records where it came from — so if this moves, those indexes are not
    migrated, they are lost, and the failure reads as "never built" on a repo that has one.

    @brief The historical slug derivation is preserved.
    @version 1
    """
    repo = tmp_path / "myproj"
    repo.mkdir()
    got = target_for(repo, tmp_path / "state")
    assert got.slug == _legacy_slug(repo.resolve()), (
        "the unnamed slug rule changed; every index already built is now unreachable"
    )
    assert got.db_path.endswith(f"targets/{got.slug}/clew.db")


## @brief A named target gets its own slug and its own database.
## @version 1
def test_a_named_target_is_distinct(tmp_path: Path) -> None:
    """Two sub-indexes of ONE root must not share a database — that is the whole feature. The
    assertion is on both the slug and the db path, because the slug is what a caller addresses
    and the path is what the build writes; a change that made them disagree would route reads
    and writes to different files.

    @brief Named targets differ from the unnamed one and from each other.
    @version 1
    """
    repo = tmp_path / "myproj"
    repo.mkdir()
    state = tmp_path / "state"

    plain = target_for(repo, state)
    first = target_for(repo, state, name="first-party")
    vendor = target_for(repo, state, name="llama-cpp")

    assert len({plain.slug, first.slug, vendor.slug}) == 3, (
        f"slugs collided: {plain.slug}, {first.slug}, {vendor.slug}"
    )
    assert len({plain.db_path, first.db_path, vendor.db_path}) == 3, "db paths collided"
    ## Every sub-index still names the SAME repository — that is what makes them siblings, and
    ## what Phase 2's cross-index lookup will use to find them.
    assert first.repo_path == vendor.repo_path == plain.repo_path


## @brief The same name yields the same target, every time.
## @version 1
def test_named_allocation_is_deterministic(tmp_path: Path) -> None:
    """A build and a later query must land on the same database. Nothing persists the mapping
    from name to path, so determinism IS the mapping — exactly as it already is for the unnamed
    form.

    @brief Allocation is a pure function of (path, name).
    @version 1
    """
    repo = tmp_path / "myproj"
    repo.mkdir()
    state = tmp_path / "state"
    assert target_for(repo, state, name="vendor") == target_for(repo, state, name="vendor")


## @brief A name that would escape the state directory is refused or neutralised.
## @version 1
def test_a_hostile_name_cannot_escape_the_state_directory(tmp_path: Path) -> None:
    """THE NAME REACHES A FILESYSTEM PATH, so it is untrusted input to a path join. A name of
    `../../etc` would otherwise place a database outside the state root — and sub-index names
    come from a repository's own `.clew.yaml`, which is exactly the "target repo influences the
    build" surface this project keeps hardening.

    Asserted as containment rather than as a specific rejection, so either refusing or
    sanitising satisfies it — what must not happen is a path outside the root.

    @brief A sub-index database stays under the state root.
    @version 1
    """
    repo = tmp_path / "myproj"
    repo.mkdir()
    state = (tmp_path / "state").resolve()
    for hostile in ("../../etc", "..", "a/b", "with space", "sub\x00idx"):
        try:
            got = target_for(repo, state, name=hostile)
        except (ValueError, OSError):
            continue
        resolved = Path(got.db_path).resolve()
        assert resolved.is_relative_to(state), (
            f"name {hostile!r} placed a database outside the state root: {resolved}"
        )


## @brief A registry holds several sub-indexes of one root, each with its own database.
## @version 1
def test_the_registry_holds_sub_indexes_of_one_root(tmp_path: Path) -> None:
    """THE FIELD THAT MAKES THE COMPOSITE KEY SAFE is `repo_path` inside the record. `targets()`
    used to reconstruct a Target's repo_path FROM THE KEY, which is correct while the key is a
    bare path and wrong the moment it carries a name — the result would be a path that does not
    exist, handed to `Path()` and stamped into replies as the repository that answered.

    @brief Sub-indexes register and reload with the true repo path.
    @version 1
    """
    from clew.mcp_server.state import TargetRegistry

    repo = tmp_path / "myproj"
    repo.mkdir()
    reg = TargetRegistry(home=tmp_path / "state")

    whole = reg.register(repo)
    first = reg.register(repo, name="first-party")
    vendor = reg.register(repo, name="llama-cpp")

    loaded = {t.slug: t for t in reg.targets()}
    assert len(loaded) == 3, f"expected three records, got {sorted(loaded)}"
    for allocated in (whole, first, vendor):
        back = loaded[allocated.slug]
        assert back.repo_path == str(repo.resolve()), (
            f"{allocated.slug} reloaded with repo_path {back.repo_path!r} — a composite key "
            "leaked into a field that is used as a filesystem path"
        )
        assert back.name == allocated.name
        assert Path(back.db_path).parent.is_dir(), "the db directory was not created"


## @brief A registry written before sub-indexes existed still reloads.
## @version 1
def test_a_legacy_record_without_repo_path_still_reloads(tmp_path: Path) -> None:
    """Every registry on disk today stores `{slug, db_path}` and nothing else, keyed by the repo
    path. The reader must keep falling back to the KEY for those, or an upgrade silently forgets
    every target the user already has.

    @brief Pre-sub-index records keep working.
    @version 1
    """
    import json

    from clew.mcp_server.state import TargetRegistry

    home = tmp_path / "state"
    home.mkdir(parents=True)
    legacy = {"/some/repo": {"slug": "repo-abc123", "db_path": "/some/state/repo-abc123/clew.db"}}
    (home / "targets.json").write_text(json.dumps(legacy), encoding="utf-8")

    got = TargetRegistry(home=home).targets()
    assert len(got) == 1
    assert got[0].repo_path == "/some/repo", "a legacy record lost its repo path"
    assert got[0].name is None, "a legacy record must read as the whole repository"


## @brief A whole-repo target's build scope is left exactly as the caller stated it.
## @version 1
def test_a_whole_repo_target_keeps_the_callers_scope(tmp_path: Path) -> None:
    """THE #511 GUARD. A repository that COULD be split must keep building whole until someone
    builds its named targets. Narrowing it here would shrink an index nobody asked to shrink and
    report success — a smaller index that reads as healthy, which is the silent-narrowing failure
    that task records.

    `exclude=None` must survive as None, not become []: None means "inherit what an earlier
    session stated", and flattening it would silently withdraw the operator's own decision.

    @brief An unnamed target's scope passes through untouched.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = tmp_path / "vendored"
    (repo / "app").mkdir(parents=True)
    nested = repo / "extern" / "dep"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: ../../.git/modules/dep\n", encoding="utf-8")

    whole = target_for(repo, tmp_path / "state")
    assert _sub_index_scope(whole, repo.resolve(), None, None) == (None, None)
    assert _sub_index_scope(whole, repo.resolve(), ["build"], {"kconfig": {}}) == (
        ["build"],
        {"kconfig": {}},
    )


## @brief A first-party target adds the nested trees to the caller's exclusions.
## @version 1
def test_a_first_party_target_adds_nested_excludes(tmp_path: Path) -> None:
    """ADDS, never replaces. The operator's own exclusions and the derived ones answer different
    questions — "what I do not want indexed" and "what belongs to another index" — and dropping
    either produces a build that is quietly wrong in a different direction.

    @brief First-party excludes the nested trees on top of the caller's list.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for
    from clew.scope import FIRST_PARTY_INDEX

    repo = tmp_path / "vendored"
    (repo / "app").mkdir(parents=True)
    nested = repo / "extern" / "dep"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: ../../.git/modules/dep\n", encoding="utf-8")

    first = target_for(repo, tmp_path / "state", name=FIRST_PARTY_INDEX)
    got_exclude, got_options = _sub_index_scope(first, repo.resolve(), ["build"], None)
    assert "build" in got_exclude, "the operator's own exclusion was dropped"
    assert "extern/dep" in got_exclude, "the nested tree was not excluded from first-party"
    assert got_options is None


## @brief A vendored target is scoped to its own tree.
## @version 1
def test_a_vendored_target_is_scoped_to_its_tree(tmp_path: Path) -> None:
    """@brief A named vendored sub-index declares roots covering only itself.
    @version 1
    """
    from clew.mcp_server.server import _sub_index_scope
    from clew.mcp_server.state import target_for

    repo = tmp_path / "vendored"
    (repo / "app").mkdir(parents=True)
    nested = repo / "extern" / "dep"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: ../../.git/modules/dep\n", encoding="utf-8")

    vendored = target_for(repo, tmp_path / "state", name="extern-dep")
    _got_exclude, got_options = _sub_index_scope(vendored, repo.resolve(), None, None)
    assert got_options["index_scope"] == {"roots": ["extern/dep"]}


## @brief The server class still owns every method the server calls on it.
## @version 1
def test_the_server_class_keeps_its_methods() -> None:
    """A STRUCTURAL GUARD AGAINST A MISTAKE ALREADY MADE HERE. Inserting a module-level function
    into the middle of a class body TERMINATES the class: every method after the insertion point
    silently becomes a module-level function. The module still imports, every symbol still
    exists, and `from clew.mcp_server.server import ...` still works — so a smoke test sees
    nothing wrong while `self._run_propose(...)` has become an AttributeError waiting for a
    caller.

    Asserted over the class body rather than by calling anything, because the failure is
    structural and a behavioural test would only catch whichever method it happened to exercise.

    @brief Methods the server dispatches to are attributes of the class.
    @version 1
    """
    from clew.mcp_server.server import DocsDbServer

    for method in ("_run_build", "_run_propose", "resolve_target", "answering"):
        assert callable(getattr(DocsDbServer, method, None)), (
            f"DocsDbServer.{method} is missing — a module-level definition inserted into the "
            "class body silently detaches every method below it"
        )
