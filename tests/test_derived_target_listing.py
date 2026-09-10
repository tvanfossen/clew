# SPDX-License-Identifier: MIT
"""gh#38 — the derived sub-index names a caller may build are listed nowhere.

`index(action='targets')` listed only the sub-indexes already BUILT. On a repository split
five ways that meant a caller could see `first-party` and `deps-libBissellIoT` and had to
GUESS the rest from the directory layout — and a wrong guess was not refused (gh#35), it
built the whole repository into a new slug and held the build lock to the 900 s kill.

46a526c claimed "every derived sub-index name is discoverable, not just the built ones", and
that was true of `build_sub_indexes` on the CLI; nothing on the MCP surface surfaced them.

WHY THE NAMES ARE CACHED RATHER THAN DERIVED PER CALL. `derive_sub_indexes` walks the whole
tree — 24.6 s on the reporting repository (gh#36) — and `targets` is the ORIENTATION call,
often the first one a session makes. Deriving on demand would put a nested-tree walk per
repository in front of a listing whose whole job is to be cheap. So a build of any sub-index
records the split it derived, and the listing reads it back.

THE HONEST CONSEQUENCE: a repository no sub-index has ever been built for lists exactly what
it lists today. That is a gap, not a wrong answer — the listing never claims the set is
complete, and one `first-party` build fills it. Inventing names from a walk nobody asked for
would trade a known gap for an unbounded cost on the cheapest call in the surface.

@brief Tests for derived-but-unbuilt sub-index names in the targets listing.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.mcp_server import state as st
from clew.scope import FIRST_PARTY_INDEX


##
# @brief A repository split three ways, with only first-party built.
# @param tmp_path Pytest temp dir.
# @param rich_db A real built database to stand in for the built index.
# @return (registry, repo root, the built target).
# @version 1
def _partly_built(tmp_path: Path, rich_db: Path) -> tuple[st.TargetRegistry, Path, st.Target]:
    """@brief Register and populate only the first-party sub-index of a split repo.
    @return (registry, repo, built target).
    @version 1
    """
    repo = tmp_path / "repo"
    (repo / "app").mkdir(parents=True)
    for name in ("tinyfsm", "libIoT"):
        nested = repo / "deps" / name
        nested.mkdir(parents=True)
        (nested / ".git").write_text(f"gitdir: ../../.git/modules/{name}\n", encoding="utf-8")
    reg = st.TargetRegistry(tmp_path / "state")
    built = reg.register(repo.resolve(), name=FIRST_PARTY_INDEX)
    Path(built.db_path).write_bytes(rich_db.read_bytes())
    reg.note_derived(built.repo_path, (FIRST_PARTY_INDEX, "deps-tinyfsm", "deps-libIoT"))
    return reg, repo.resolve(), built


def test_the_listing_names_the_sub_indexes_that_are_not_built_yet(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE ON-DEMAND BUILD MODEL NEEDS A NAME TO BUILD. "Build a vendored sub-index only when a
    query needs it" is only usable if the name is obtainable without guessing, and guessing was
    what cost fifteen minutes of a shared build lock.

    @brief Unbuilt derived names appear with exists false.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import build_server

    reg, _repo, _built = _partly_built(tmp_path, rich_db)
    _mcp, server = build_server(reg)

    rows = server.list_targets()
    by_name = {row.get("sub_index"): row for row in rows}
    assert by_name[FIRST_PARTY_INDEX]["exists"] is True, "the built index must still be built"
    for unbuilt in ("deps-tinyfsm", "deps-libIoT"):
        assert unbuilt in by_name, f"{unbuilt!r} is buildable and was not listed"
        assert by_name[unbuilt]["exists"] is False, f"{unbuilt!r} is not built and must say so"


def test_a_derived_name_is_listed_once_even_when_built(tmp_path: Path, rich_db: Path) -> None:
    """A DUPLICATE ROW IS WORSE THAN A MISSING ONE, because a caller counting indexes would
    double-count every built sub-index the moment the derived set started being reported. The
    registered row wins: it is the one carrying the real staleness measurement.

    @brief The built sub-index appears exactly once.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import build_server

    reg, _repo, _built = _partly_built(tmp_path, rich_db)
    _mcp, server = build_server(reg)

    names = [row.get("sub_index") for row in server.list_targets()]
    assert names.count(FIRST_PARTY_INDEX) == 1, (
        f"first-party listed {names.count(FIRST_PARTY_INDEX)}x"
    )


def test_a_repository_with_no_recorded_split_invents_nothing(tmp_path: Path, rich_db: Path) -> None:
    """NO WALK ON A LISTING, which is the cost this design refuses to pay. A repository whose
    split has never been derived lists exactly its registered entries — the same answer as
    before this change — rather than paying a whole-tree walk on the cheapest call in the
    surface to discover names nobody asked for.

    @brief An unrecorded repository lists only what is registered.
    @return None.
    @version 1
    """
    from clew.mcp_server.server import build_server

    repo = tmp_path / "plain"
    repo.mkdir()
    reg = st.TargetRegistry(tmp_path / "state")
    target = reg.register(repo.resolve())
    Path(target.db_path).write_bytes(rich_db.read_bytes())
    _mcp, server = build_server(reg)

    rows = server.list_targets()
    assert len(rows) == 1, f"nothing may be invented for an unrecorded repo, got {rows}"
    assert rows[0].get("sub_index") is None


def test_the_recorded_split_survives_a_reload(tmp_path: Path, rich_db: Path) -> None:
    """IT IS PERSISTED, not held in the process. The listing is most useful to a session that
    did not do the build — another session, or this one after a restart — and a note kept in
    memory would be exactly backwards: available only where it is least needed.

    @brief A second registry over the same state root reads the split back.
    @return None.
    @version 1
    """
    reg, _repo, built = _partly_built(tmp_path, rich_db)
    reloaded = st.TargetRegistry(tmp_path / "state")
    assert reloaded.derived_names(built.repo_path) == (
        FIRST_PARTY_INDEX,
        "deps-tinyfsm",
        "deps-libIoT",
    )
