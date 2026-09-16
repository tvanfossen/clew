# SPDX-License-Identifier: MIT
"""gh#48 — a split repository refused every query while six of its indexes sat built on disk.

OBSERVED on 1.0.33 against B12_single_rgb: the whole-repo database was absent, six sub-index
databases were present, and every invocation mode refused with

    No database has been built for .../B12_single_rgb yet — call
    index(action='refresh', target='.../B12_single_rgb') first.

wrong in both halves. Six databases existed; and the one action recommended — an unscoped refresh
of a repository that vendors boost, opencv and pcl — indexed 87,911 files until doxygen was
killed at 900 s. An agent reasoning correctly from the message reached a dead end.

THE ROUTING ALREADY EXISTED AND COULD NOT SEE THE DISK. `_preferred_default` sends a bare call on a
split repository to `first-party` — among REGISTERED siblings. Indexes built by another session, by
the CLI, or imported from elsewhere are not registered in this server, so a bare path fell through
to deriving the WHOLE-repo target, whose database did not exist.

@brief Tests for bare-call routing and refusals on a split repository.
@version 1
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("mcp", reason="the MCP SDK is a REQUIRED dependency")

from clew.mcp_server import state as st
from clew.mcp_server.server import build_server
from clew.scope import FIRST_PARTY_INDEX


## @brief A repository with two vendored submodules, so the split has real names.
## @param root Directory to build the repository in.
## @return The resolved repository root.
## @version 1
def _split_repo(root: Path) -> Path:
    """The same shape tests/test_sub_index_refusal.py uses: first-party code plus two nested
    gitlink trees, which is what makes `derive_sub_indexes` split the repository.

    @brief Build a two-submodule repository.
    @version 1
    """
    (root / "app").mkdir(parents=True)
    (root / "app" / "main.cpp").write_text("int main(){return 0;}\n", encoding="utf-8")
    for name in ("tinyfsm", "libIoT"):
        nested = root / "deps" / name
        nested.mkdir(parents=True)
        (nested / ".git").write_text(f"gitdir: ../../.git/modules/{name}\n", encoding="utf-8")
    return root.resolve()


## @brief Put a built database in the slot a sub-index derives, WITHOUT registering it.
## @param home The server's state home.
## @param repo The repository.
## @param name The sub-index name.
## @param db The database to copy in.
## @return None.
## @version 1
def _built_on_disk(home: Path, repo: Path, name: str, db: Path) -> None:
    """NOT REGISTERED, deliberately: that is B12's state. The sub-indexes were built somewhere
    this server never registered them — another session, the CLI, an import — and the database
    files are exactly where `target_for` derives them.

    @brief Write a sub-index database at its derived path.
    @version 1
    """
    target = st.target_for(repo, home, name)
    Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
    Path(target.db_path).write_bytes(db.read_bytes())


def test_a_bare_call_on_a_split_repo_answers_from_first_party(
    tmp_path: Path, rich_db: Path
) -> None:
    """ASK 1. The whole-repo database is absent and first-party is built, so a call that names
    no sub_index answers from first-party — and SAYS so, because a reply that read one index and
    stamped another's identity is this module's most expensive recorded defect.

    @brief An absent whole-repo index routes a bare call to first-party, disclosed.
    @version 1
    """
    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    _built_on_disk(home, repo, FIRST_PARTY_INDEX, rich_db)
    _mcp, state = build_server(st.TargetRegistry(home))

    reply = state.tools.dossier("sensor_poll", target=str(repo))

    assert "found" not in reply, f"first-party knows sensor_poll; got {reply}"
    assert reply.get("sub_index") == FIRST_PARTY_INDEX, (
        f"a defaulted reply must name the index that answered it, got {reply.get('sub_index')!r}"
    )


def test_a_first_party_miss_says_what_it_did_not_search(tmp_path: Path, rich_db: Path) -> None:
    """THE HALF THAT MAKES ASK 1 SAFE. Routing to first-party turns an unhelpful refusal into an
    answer — and, for a symbol that lives in a vendored tree, into a CONFIDENT FALSE NEGATIVE:
    "a definitive negative from the database" about a function that exists one index over. A miss
    answered from part of a repository has to say which parts it did not read.

    `not_searched` NAMES BUILT INDEXES — ones the caller can query next. `deps-libIoT` is never
    built here, and knowing an unbuilt part exists takes the tree walk a query must not pay, so it
    is not invented into the list.

    @brief A negative from a sub-index names the unsearched siblings and is not called definitive.
    @version 1
    """
    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    _built_on_disk(home, repo, FIRST_PARTY_INDEX, rich_db)
    _built_on_disk(home, repo, "deps-tinyfsm", rich_db)
    _mcp, state = build_server(st.TargetRegistry(home))

    reply = state.tools.dossier("rtabmap_only_symbol", target=str(repo))

    assert reply.get("found") is False
    assert reply.get("not_searched") == ["deps-tinyfsm"], (
        f"the miss must name the built sub-index it did not read, got {reply.get('not_searched')}"
    )
    assert "definitive negative" not in reply["note"], (
        f"a negative over one part of a split repository is not definitive: {reply['note']!r}"
    )


def test_a_first_party_miss_is_scoped_even_when_no_other_part_is_built(
    tmp_path: Path, rich_db: Path
) -> None:
    """MEASURED END TO END, then pinned. A background first build of a split repository builds
    first-party ONLY, so the state right after it has no vendored part built at all — and a miss
    for a vendored function came back "a definitive negative" because `not_searched` listed only
    BUILT siblings and there were none. The build had recorded the vendored names; an unbuilt part
    makes the answer more partial, not complete.

    @brief Recorded-but-unbuilt parts are listed as not searched, and the negative is scoped.
    @version 1
    """
    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    registry = st.TargetRegistry(home)
    registry.register(repo, FIRST_PARTY_INDEX)
    registry.note_derived(str(repo), (FIRST_PARTY_INDEX, "deps-libIoT", "deps-tinyfsm"))
    _built_on_disk(home, repo, FIRST_PARTY_INDEX, rich_db)
    _mcp, state = build_server(registry)

    reply = state.tools.dossier("vendored_only_symbol", target=str(repo))

    assert reply.get("not_searched") == ["deps-libIoT", "deps-tinyfsm"], reply.get("not_searched")
    assert "definitive negative" not in reply["note"], reply["note"]


def test_a_hit_whose_callees_are_unresolved_says_which_parts_it_did_not_read(
    tmp_path: Path, rich_db: Path, repo_root: Path
) -> None:
    """ASK 3 IN THE WORDS THE ISSUE USED: "a dossier answered from first-party whose callees live
    in a vendored sub-index should say so, rather than presenting an apparently complete
    neighbour list." A HIT is the dangerous case, because the reply looks complete.
    `external_callees` already names the call sites that resolve to no indexed function; what was
    missing is the connection to the parts of the repository this answer never read.

    THE UNRESOLVED CALL IS MANUFACTURED by dropping one callee's rows from a copy of the fixture
    index — which is exactly the shape a split repository produces: the caller is first-party,
    the callee is indexed somewhere this database is not.

    @brief A hit with unresolved call sites names the unread parts beside them.
    @version 1
    """
    import shutil
    import sqlite3

    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    ## The fixture index records paths relative to the csample tree, and `external_callees`
    ## PARSES THE BODY off disk — so the split repository has to hold those sources for the call
    ## sites to be found at all.
    shutil.copytree(repo_root, repo, dirs_exist_ok=True)
    registry = st.TargetRegistry(home)
    ## `note_derived` records the split onto this repository's existing records, which is what a
    ## build leaves behind — so the first-party record has to exist, as it would after one.
    registry.register(repo, FIRST_PARTY_INDEX)
    registry.note_derived(str(repo), (FIRST_PARTY_INDEX, "deps-tinyfsm"))
    _built_on_disk(home, repo, FIRST_PARTY_INDEX, rich_db)
    first_party = st.target_for(repo, home, FIRST_PARTY_INDEX)
    conn = sqlite3.connect(first_party.db_path)
    conn.execute("DELETE FROM memberdef WHERE name = 'DataModel_Set_DEMOBOT_POWER_BATTERY_MV'")
    conn.commit()
    conn.close()
    _mcp, state = build_server(registry)

    reply = state.tools.dossier("sensor_poll", target=str(repo))

    assert reply.get("found") is not False, reply
    assert reply.get("external_callees"), "premise: this subject has unresolved call sites"
    assert reply.get("not_searched") == ["deps-tinyfsm"], reply.get("not_searched")
    note = str(reply.get("scope_note"))
    assert "not_searched" in note and FIRST_PARTY_INDEX in note, (
        f"a hit with unresolved callees must point at the unread parts: {note!r}"
    )


def test_a_negative_from_first_party_is_scoped_even_with_nothing_else_on_record(
    tmp_path: Path, rich_db: Path
) -> None:
    """FOUND BY DRIVING A MODEL AT IT (gh#48 ask 5). A repository whose first-party index was
    built by the CLI registers no sub-index and records no split, so `not_searched` is empty —
    and a miss for a symbol that lives in a vendored tree came back as "a definitive negative
    from the database". The repository says it is split in its own `.gitmodules`, which costs a
    stat to read, and an answer from ONE part of it is never definitive for the whole.

    @brief A sub-index negative is scoped by declared split evidence, with nothing else recorded.
    @version 1
    """
    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    (repo / ".gitmodules").write_text(
        '[submodule "deps/tinyfsm"]\n\tpath = deps/tinyfsm\n', encoding="utf-8"
    )
    _built_on_disk(home, repo, FIRST_PARTY_INDEX, rich_db)
    _mcp, state = build_server(st.TargetRegistry(home))

    reply = state.tools.dossier("vendored_only_symbol", target=str(repo))

    assert reply.get("found") is False
    assert "definitive negative" not in reply["note"], reply["note"]
    assert "sub_index" in reply["note"], (
        f"a scoped negative must route to the parts that were not read: {reply['note']!r}"
    )


def test_the_refusal_names_what_is_built_and_never_advises_an_unscoped_build(
    tmp_path: Path, rich_db: Path
) -> None:
    """ASK 2, and the half of the old message that did damage. With neither the whole-repo nor
    the first-party index built, a query is refused — but the refusal must list the sub-indexes
    that ARE built and name the scoped build that fixes it. It must not recommend
    `index(action='refresh', target=...)` with no sub_index on a split repository: that call is
    the 87,911-file, 900-second build.

    @brief The refusal enumerates built sub-indexes and recommends a scoped refresh only.
    @version 1
    """
    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    (repo / ".clew.yaml").write_text("# sub_indexes:\n#   deps-tinyfsm: {}\n", encoding="utf-8")
    _built_on_disk(home, repo, "deps-tinyfsm", rich_db)
    _mcp, state = build_server(st.TargetRegistry(home))

    with pytest.raises(RuntimeError) as exc:
        state.tools.dossier("sensor_poll", target=str(repo))
    message = str(exc.value)

    assert "deps-tinyfsm" in message, f"the refusal must name the built sub-index: {message}"
    ## ASK 4: the repository's own declaration file, and whether a build honours it.
    assert ".clew.yaml holds only comments" in message, message
    assert f"sub_index='{FIRST_PARTY_INDEX}'" in message, (
        f"the remedy must be the SCOPED first-party build: {message}"
    )
    assert f"index(action='refresh', target={str(repo)!r})" not in message, (
        f"an unscoped refresh of a split repository must never be advised: {message}"
    )


def test_an_unsplit_repo_keeps_the_original_refusal(tmp_path: Path) -> None:
    """THE CONTROL. A repository with no nested trees is not split, has no sub-indexes to name,
    and an unscoped refresh is exactly the right advice for it.

    @brief A plain unbuilt repository is refused with the unscoped remedy, as before.
    @version 1
    """
    home = tmp_path / "state"
    repo = tmp_path / "plain"
    repo.mkdir()
    _mcp, state = build_server(st.TargetRegistry(home))

    with pytest.raises(RuntimeError) as exc:
        state.tools.dossier("anything", target=str(repo))
    message = str(exc.value)

    assert "index(action='refresh'" in message and "sub_index" not in message, message


def test_a_built_first_party_outranks_a_registered_but_unbuilt_whole_index(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE STATE FOLLOWING THE OLD ADVICE LEAVES BEHIND. `index(action='refresh', target=repo)`
    registers the whole-repository target before it builds, so B12's killed 900 s build left a
    whole-repo RECORD with no database — and the default preferred any whole-repo record, built or
    not, over a first-party index that worked. Every later bare call refused.

    @brief A built index beats a registered-only one when choosing the default.
    @version 1
    """
    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    registry = st.TargetRegistry(home)
    registry.register(repo)
    _built_on_disk(home, repo, FIRST_PARTY_INDEX, rich_db)
    _mcp, state = build_server(registry)

    reply = state.tools.dossier("sensor_poll", target=str(repo))

    assert "found" not in reply, reply
    assert reply.get("sub_index") == FIRST_PARTY_INDEX


def test_a_call_naming_no_target_answers_from_first_party_and_says_so(
    tmp_path: Path, rich_db: Path
) -> None:
    """MODES 2 AND 3 OF THE REPORT: `--repo` or `$CLAUDE_PROJECT_DIR` supplies the default and the
    call names no target. Two defects stacked there. `adopt` saw only registered siblings, and
    `self.active` is resolved ONCE, so a first-party index built after the session connected — by
    another session, the CLI, or a background first build — never became the default.

    And the default path stamped only the repository, so an answer from first-party read as an
    answer from the whole repository.

    @brief The default target follows an on-disk first-party index and the reply names it.
    @version 1
    """
    home = tmp_path / "state"
    repo = _split_repo(tmp_path / "repo")
    _mcp, state = build_server(st.TargetRegistry(home))
    state.adopt(str(repo), st.TARGET_SOURCE_FLAG)
    assert state.active is not None and state.active.name is None, "premise: nothing built yet"

    _built_on_disk(home, repo, FIRST_PARTY_INDEX, rich_db)
    reply = state.tools.dossier("sensor_poll")

    assert "found" not in reply, reply
    assert reply.get("sub_index") == FIRST_PARTY_INDEX, reply.get("sub_index")


def test_a_comment_only_declaration_is_not_reported_as_malformed(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """ASK 4's other half. A `.clew.yaml` holding only comments is what `propose_declaration`
    hands an owner, and it was logged at WARNING as "does not contain a mapping — ignoring it",
    which reads as a broken file. It states nothing; that is said at INFO, in those words. A file
    that holds something other than a mapping is still a WARNING.

    @brief Comment-only declarations log as stating nothing; non-mappings still warn.
    @version 1
    """
    import logging

    from clew.declaration import load_declaration

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".clew.yaml").write_text("# locks:\n#   primitives: []\n", encoding="utf-8")
    with caplog.at_level(logging.INFO):
        assert load_declaration(repo) == {}
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING], caplog.text
    assert "states nothing" in caplog.text

    caplog.clear()
    (repo / ".clew.yaml").write_text("- a\n- b\n", encoding="utf-8")
    with caplog.at_level(logging.INFO):
        assert load_declaration(repo) == {}
    assert any(
        r.levelno == logging.WARNING and "not a mapping" in r.getMessage() for r in caplog.records
    )
