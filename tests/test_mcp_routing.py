# SPDX-License-Identifier: MIT
"""One server process, many target repositories — the target travels on the CALL.

Everything here is about the routing property and nothing else. The wrapper/R2 parity,
the budget cap and the tier-0 lifecycle are pinned in `test_mcp_server.py`; what this
file asserts is that a SINGLE `DocsDbServer` answers about whichever repository each
call names, that omitting the argument still reaches the derived target, that four
concurrent refreshes of one target build it once, and that a target the server cannot
find is refused by name rather than answered from the wrong index.

The last of those is the one worth stating twice. A reply from the wrong repository is
this project's most expensive recorded defect — a 36-cell grid published a verdict from
an arm pointed at the wrong index — so a routing failure has to be loud.

@brief Tests for per-call target routing and per-target refresh deduplication.
@version 1
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path

import anyio
import pytest

pytest.importorskip(
    "mcp",
    reason="the MCP SDK is a REQUIRED dependency, so this skipping means a BROKEN install, not an unselected extra",
)

from test_mcp_server import _FakeCtx

from clew.mcp_server import server as server_module
from clew.mcp_server import state as st
from clew.mcp_server.server import build_server
from clew.mcp_server.tools_query import TIER1_TOOLS, QueryTools
from clew.signature import write_build_signature


## @brief Register a repo under a server's registry and give it a built database.
## @param state The server whose registry allocates the database path.
## @param repo Directory to register (created if absent).
## @param db Database file to copy in as this target's index.
## @return The registered Target.
## @version 1
def _built_target(state, repo: Path, db: Path) -> st.Target:
    """Copies a real built index into the slot the registry allocates, which is what
    makes the routing assertion meaningful: both targets answer with the SAME fixture
    data, so a reply naming the right repository cannot be luck of differing content.

    @brief Register a repo and populate its allocated database.
    @return The registered Target.
    @version 1
    """
    repo.mkdir(parents=True, exist_ok=True)
    target = state.registry.register(str(repo))
    Path(target.db_path).write_bytes(db.read_bytes())
    return target


@pytest.mark.anyio
async def test_one_process_answers_two_targets_in_sequence(tmp_path: Path, rich_db: Path) -> None:
    """THE WHOLE POINT: one server, two repositories, no restart and no retarget.

    Asserted through the `target` field because that field exists precisely so a caller
    can tell which repository answered — and because a routing bug that returned the
    right SHAPE from the wrong index is exactly the failure that voided a 36-cell grid.

    Also asserts the server stayed stateless: neither call adopts a target, so the third
    call's answer does not depend on the order of the first two.

    @brief Two targets, one process, each reply naming its own repository.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo_a = tmp_path / "alpha"
    repo_b = tmp_path / "beta"
    _built_target(state, repo_a, rich_db)
    _built_target(state, repo_b, rich_db)

    first = state.tools.dossier("sensor_poll", target=str(repo_a))
    second = state.tools.dossier("sensor_poll", target=str(repo_b))
    third = state.tools.dossier("sensor_poll", target=str(repo_a))

    assert first["target"] == str(repo_a)
    assert second["target"] == str(repo_b)
    assert third["target"] == str(repo_a), "a routed call must not inherit the previous one"
    assert state.active is None, "routing must not adopt a target — the server is stateless"


@pytest.mark.anyio
async def test_a_routed_reply_reads_the_routed_INDEX_not_only_its_name(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE ASSERTION THE `target` FIELD CANNOT MAKE ON ITS OWN.

    Stamping the routed repository onto the reply and reading the DERIVED repository's
    database would satisfy every attribution check in this file while returning another
    project's answers under this project's name — the same shape as the grid that recorded
    36 cells `valid=True` because every term checked that tools were CALLED and none
    checked which index answered. So the two indexes here are made to DISAGREE, and the
    disagreement is what is asserted.

    @brief A routed call reads the routed database, proven by content and not by label.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    complete = tmp_path / "complete"
    pruned = tmp_path / "pruned"
    _built_target(state, complete, rich_db)
    thinned = _built_target(state, pruned, rich_db)
    with sqlite3.connect(thinned.db_path) as conn:
        conn.execute("DELETE FROM memberdef WHERE name = 'sensor_poll'")
    state.adopt(str(complete), st.TARGET_SOURCE_FLAG)

    hit = state.tools.dossier("sensor_poll", target=str(complete))
    miss = state.tools.dossier("sensor_poll", target=str(pruned))

    assert "found" not in hit, "the complete index must still know sensor_poll"
    assert miss["found"] is False, (
        "the pruned index does not know sensor_poll — a hit here means the call read the "
        "DERIVED database while naming the routed one"
    )
    assert miss["target"] == str(pruned)


@pytest.mark.anyio
async def test_a_routed_source_read_uses_the_routed_WORKING_TREE(
    tmp_path: Path, rich_db: Path, repo_root: Path
) -> None:
    """`dossier.body` reads bytes off disk using line numbers recorded in an index, so the
    call resolves TWO things from `target` — the database and the working tree — and a
    mismatch between them would quote one file's text under another's name.

    The derived target here has a database and an empty tree; the routed one has the real
    tree. Only a call that resolves the tree from `target` can read anything.

    THIS TEST GUARDED `source` AND NOW GUARDS `dossier`, which is a STRONGER shape rather
    than a port: `source` answered `found: false` on a treeless target, so index
    resolution and tree resolution failed together and one assertion covered both. A
    dossier answers from the index either way, so the tree resolution is isolated — the
    index half is asserted present on both calls and only `body` is allowed to differ.

    @brief A routed dossier reads its body from the routed repository's files.
    @version 2
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    treeless = tmp_path / "no_sources_here"
    _built_target(state, treeless, rich_db)
    _built_target(state, repo_root, rich_db)
    state.adopt(str(treeless), st.TARGET_SOURCE_FLAG)

    derived = state.tools.dossier("sensor_poll")
    assert derived.get("found") is not False, "premise: the index knows the symbol either way"
    assert "body" not in derived, (
        "premise: the derived target's working tree holds none of the indexed files, so the "
        "body panel must be absent rather than read from somewhere else"
    )

    routed = state.tools.dossier("sensor_poll", target=str(repo_root))
    assert routed.get("found") is not False
    assert "sensor_poll" in "\n".join(routed["body"]["lines"]), (
        "the routed tree holds the file and must be read from THERE"
    )
    assert routed["target"] == str(repo_root)


## Minimal arguments for every tier-1 tool, keyed by name. Written out rather than
## introspected so that a tool gaining a required argument fails the sweep below loudly
## instead of being skipped by a clever loop.
_ARGS: dict[str, dict[str, object]] = {
    "dossier": {"subject": "sensor_poll"},
    "search": {"text": "telemetry"},
}


def test_the_argument_table_covers_the_frozen_surface() -> None:
    """The table above is only a valid premise for the routing sweep if it is complete.

    @brief Every tier-1 tool has arguments declared for the routing sweep.
    @version 1
    """
    assert set(_ARGS) == set(TIER1_TOOLS)


@pytest.mark.anyio
async def test_every_tier1_tool_routes_and_omitting_the_target_keeps_the_derived_one(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE ADDITIVE GUARANTEE, checked over the whole frozen surface rather than a sample.

    Every tier-1 tool must accept `target=` and must behave exactly as before when it is
    omitted. Driving the full `TIER1_TOOLS` set means a tool added without routing fails
    here, the same reasoning that makes the target-stamp test structural: a sampled check
    is how 36 cells were recorded valid against the wrong index.

    @brief Each tier-1 tool routes when told to and falls back to the derived target.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    derived = tmp_path / "derived"
    routed = tmp_path / "routed"
    _built_target(state, derived, rich_db)
    _built_target(state, routed, rich_db)
    state.adopt(str(derived), st.TARGET_SOURCE_FLAG)

    for name in TIER1_TOOLS:
        tool = getattr(state.tools, name)
        assert tool(**_ARGS[name])["target"] == str(derived), (
            f"{name} with no target must answer from the derived repository"
        )
        assert tool(**_ARGS[name], target=str(routed))["target"] == str(routed), (
            f"{name} must answer from the repository the CALL named"
        )


@pytest.mark.anyio
async def test_target_is_an_optional_parameter_on_every_tier1_schema(tmp_path: Path) -> None:
    """STRUCTURAL, not prose: the routing capability only exists over MCP if the argument
    reaches the wire schema, and it is only additive if it is not required.

    A Python signature that a client never sees is a capability nobody can call.

    @brief `target` is present and optional in every tier-1 tool's input schema.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "anything"
    repo.mkdir()
    reg.register(str(repo))
    mcp, _state = build_server(reg)

    schemas = {t.name: t.input_schema for t in await mcp.list_tools()}
    for name in TIER1_TOOLS:
        assert name in schemas, f"{name} is not registered, so its schema cannot be checked"
        schema = schemas[name]
        assert "target" in schema.get("properties", {}), f"{name} does not expose `target`"
        assert "target" not in schema.get("required", []), (
            f"{name} makes `target` required, which breaks every existing call"
        )


@pytest.mark.anyio
async def test_a_server_with_no_derived_target_still_serves_its_registered_indexes(
    tmp_path: Path, rich_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE TIER-GATE DECISION, asserted rather than described.

    The gate used to be "a target is derived". A query tool now takes the repository on
    the call, so that condition stopped correlating with "a query can be answered" — and
    the process it locks out is exactly the one routing is for: launched at no repository
    in particular, holding several indexes, serving several sessions. Under the old gate
    that server offered zero query tools.

    The honest half of the old gate survives and is asserted next door
    (`test_tier0_present_tier1_absent_at_construction`): a first-ever run with nothing
    indexed anywhere still offers only the lifecycle tools, because there genuinely is
    nothing to read.

    @brief Query tools are gated on having an index, not on having a derived target.
    @version 1
    """
    monkeypatch.delenv(st.PROJECT_DIR_ENV, raising=False)
    reg = st.TargetRegistry(tmp_path / "state")
    repo = tmp_path / "indexed_earlier"
    ## Registered and built by some earlier session, exactly the residue a restart leaves.
    repo.mkdir()
    built = reg.register(str(repo))
    Path(built.db_path).write_bytes(rich_db.read_bytes())

    mcp, state = build_server(reg)
    assert state.resolve_startup_target(None) is None, "premise: no eager source"
    assert state.active is None

    assert set(TIER1_TOOLS) <= await _tool_names(mcp), (
        "a server with indexes but no derived target must still offer the query tools"
    )
    assert state.tools.dossier("sensor_poll", target=str(repo))["target"] == str(repo)


## @brief Registered tool names on an MCP server.
## @param mcp The server to inspect.
## @return Set of tool names.
## @version 1
async def _tool_names(mcp) -> set[str]:
    """@brief Collect the currently registered tool names.
    @return Set of tool names.
    @version 1
    """
    return {t.name for t in await mcp.list_tools()}


@pytest.mark.anyio
async def test_concurrent_refreshes_of_one_target_build_it_once(tmp_path: Path) -> None:
    """FOUR SESSIONS, ONE REPOSITORY, ONE BUILD.

    The build runs on an anyio worker thread while the transport keeps serving frames, so
    the guard has to be held by the awaiting TASK across that hand-off — a threading lock
    taken on the event loop would stall the transport for every other session, which is
    the exact deployment this routing exists to serve.

    The stand-in build sleeps and then writes a currently-stamped database, because that
    is what makes the second caller's re-check meaningful: the deduplication is the lock
    PLUS the freshness re-check inside it, and a stand-in that left the index stale would
    let this pass on the lock alone.

    @brief Concurrent refreshes of one target produce exactly one build.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo = tmp_path / "contended"
    repo.mkdir()
    builds: list[str] = []

    def _fake_build(
        target, doxyfile, scope="from-guard", exclude=None, options=None, skip_if_fresh=False
    ):
        """@brief Stand-in build that records its call and leaves a current index.
        @version 1
        """
        builds.append(target.repo_path)
        time.sleep(0.05)
        Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(target.db_path).close()
        write_build_signature(Path(target.db_path))
        return {"ok": True, "built": True, "doxyfile": "(stand-in)", "output": ""}

    state._run_build = _fake_build

    async def _refresh() -> None:
        """@brief One session's refresh of the contended target.
        @version 1
        """
        result = await state.build_or_refresh(_FakeCtx(), target=str(repo))
        assert result["ok"] is True, result
        assert result["target"] == str(repo)

    async with anyio.create_task_group() as tg:
        for _ in range(4):
            tg.start_soon(_refresh)

    assert builds == [str(repo)], (
        f"four concurrent refreshes of one target must build it ONCE, got {len(builds)}"
    )


@pytest.mark.anyio
async def test_concurrent_refreshes_of_different_targets_are_not_serialised(
    tmp_path: Path,
) -> None:
    """The counter-case, and the reason the lock is keyed by TARGET rather than global.

    Two repositories are independent work; a single build lock would make five sessions
    on five repositories queue behind each other for no reason. Asserted by overlap in
    time rather than by inspecting the lock, so it survives a change of primitive.

    @brief Builds of different targets run concurrently.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repos = [tmp_path / "one", tmp_path / "two"]
    for repo in repos:
        repo.mkdir()
    spans: list[tuple[float, float]] = []

    def _fake_build(
        target, doxyfile, scope="from-guard", exclude=None, options=None, skip_if_fresh=False
    ):
        """@brief Stand-in build recording when it started and finished.
        @version 1
        """
        started = time.monotonic()
        time.sleep(0.1)
        Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(target.db_path).close()
        write_build_signature(Path(target.db_path))
        spans.append((started, time.monotonic()))
        return {"ok": True, "built": True, "doxyfile": "(stand-in)", "output": ""}

    state._run_build = _fake_build

    async def _refresh(repo: Path) -> None:
        """@brief Refresh one of the two independent targets.
        @version 1
        """
        assert (await state.build_or_refresh(_FakeCtx(), target=str(repo)))["ok"] is True

    async with anyio.create_task_group() as tg:
        for repo in repos:
            tg.start_soon(_refresh, repo)

    assert len(spans) == 2, "both targets must build"
    (a_start, a_end), (b_start, b_end) = spans
    assert min(a_end, b_end) > max(a_start, b_start), (
        "builds of different targets overlapped nowhere, so the lock is global not per-target"
    )


@pytest.mark.anyio
async def test_an_unknown_target_is_refused_and_says_what_it_looked_for(
    tmp_path: Path, rich_db: Path
) -> None:
    """A target string that matches nothing must REFUSE. Building it would be worse: the
    caller most likely mistyped a path, and a mistyped path that is also a real directory
    would silently start a multi-minute doxygen run over the wrong tree.

    The message has to name the string, say what was searched, and list what is known,
    because the caller's next move — fix the spelling, or call list_targets — depends on
    which of those it was.

    @brief An unresolvable target is refused by name, on every surface.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    known = tmp_path / "known"
    _built_target(state, known, rich_db)
    missing = str(tmp_path / "never_existed")

    with pytest.raises(RuntimeError) as exc:
        state.tools.dossier("sensor_poll", target=missing)
    message = str(exc.value)
    assert missing in message, "the refusal must name the string it could not resolve"
    assert "index(action='targets')" in message, "and the move that would show what IS known"
    assert str(known) in message, "and what is registered right now"

    ## The same refusal on the build surface, which REPORTS rather than raises.
    result = await state.build_or_refresh(_FakeCtx(), target=missing)
    assert result["ok"] is False
    assert missing in result["error"]


@pytest.mark.anyio
async def test_a_known_but_unbuilt_target_names_the_action_that_fixes_it(
    tmp_path: Path,
) -> None:
    """ "Registered but never built" is the ordinary first state of a new target, and it
    must not surface as a bare sqlite "unable to open database file". The refusal names
    `build_or_refresh` WITH the target argument, so the advice is a call the caller can
    make rather than one that would build the wrong repository.

    @brief An unbuilt routed target is refused with the remedy spelled out.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo = tmp_path / "registered_not_built"
    repo.mkdir()
    reg.register(str(repo))

    with pytest.raises(RuntimeError) as exc:
        state.tools.graph_stats(target=str(repo))
    message = str(exc.value)
    assert str(repo) in message
    assert "index(action='refresh'" in message
    assert "target=" in message, "the remedy must be a call that names THIS target"


def test_a_tool_set_with_no_resolver_refuses_a_target_rather_than_ignoring_it(
    rich_db: Path,
) -> None:
    """The bound-to-one-database shape — what a direct constructor call produces — cannot
    route. It must say so, because the alternative is answering from the repository it IS
    bound to while the reply's `target` field names that repository, which reads as a
    successful routed call and is the worst available outcome.

    @brief A tool set with no resolver refuses an explicit target.
    @version 1
    """
    tools = QueryTools(lambda: rich_db, lambda: rich_db.parent)
    with pytest.raises(RuntimeError, match="cannot route"):
        tools.dossier("sensor_poll", target="/somewhere/else")

    assert tools.dossier("sensor_poll")["target"] == str(rich_db.parent), (
        "omitting the target must keep working on the bound shape"
    )


@pytest.mark.anyio
async def test_a_routed_build_registers_the_target_without_adopting_it(
    tmp_path: Path,
) -> None:
    """Building a target the server has never seen must allocate and record it — that is
    what makes `list_targets` and `cull` able to see it later — while leaving the DERIVED
    target alone. Registration is bookkeeping about a database on disk; adoption is state
    about which repository this server answers for by default, and the whole point of
    routing is that a call does not change the second.

    @brief A routed build registers its target and leaves the active one untouched.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    derived = tmp_path / "derived"
    fresh = tmp_path / "fresh"
    derived.mkdir()
    fresh.mkdir()
    state.adopt(str(derived), st.TARGET_SOURCE_FLAG)

    def _fake_build(
        target, doxyfile, scope="from-guard", exclude=None, options=None, skip_if_fresh=False
    ):
        """@brief Stand-in build leaving a current index.
        @version 1
        """
        Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
        sqlite3.connect(target.db_path).close()
        write_build_signature(Path(target.db_path))
        return {"ok": True, "built": True, "doxyfile": "(stand-in)", "output": ""}

    state._run_build = _fake_build
    result = await state.build_or_refresh(_FakeCtx(), target=str(fresh))

    assert result["ok"] is True and result["built"] is True
    assert result["target"] == str(fresh)
    assert Path(state.active.repo_path) == derived, "a routed build must not retarget"
    assert str(fresh) in [t.repo_path for t in reg.targets()], "but must be registered"


@pytest.mark.anyio
async def test_a_stalled_refresh_does_not_hang_a_later_query(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FIELD-OBSERVED, 2026-08-26: a single MCP call hung indefinitely. The build lock is held
    across the whole build, and the acquire was unbounded, so one stalled build queued every later
    query that found the index stale — with no way out. `_auto_refresh`'s own docstring promised
    the opposite: "a stale answer plus a warning is strictly better than an error." It honoured
    that for an exception and not for a STALL.

    THE STALL HAS TO BE DELIBERATE OR THIS CANNOT BE TESTED AT ALL. The sibling
    `test_concurrent_refreshes_of_one_target_build_it_once` passes today and always did, because
    its stand-in build returns promptly — a fast build never exercises the queue. So this one holds
    the lock for longer than the bounded wait and asserts the waiter RETURNS.

    Asserted as "returns within a bound", not on wall-clock precision: the point is termination,
    not latency.

    @brief A query behind a stalled refresh answers stale instead of hanging.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo = tmp_path / "stalled"
    repo.mkdir()
    (repo / "a.c").write_text("int main(void){return 0;}\n", encoding="utf-8")

    ## Shrink the wait so the test is fast; the production value is a backstop, not a budget.
    monkeypatch.setattr(server_module, "_LOCK_WAIT_SECONDS", 1)

    target = state.resolve_target(str(repo))
    monkeypatch.setattr(state, "_data_stale", lambda _t: True)

    released = anyio.Event()
    waiter_returned = anyio.Event()

    async def _hold_the_lock() -> None:
        """@brief Occupy the build lock far longer than the bounded wait.
        @version 1
        """
        async with state._build_lock(target.repo_path):
            await anyio.sleep(5)
            released.set()

    async def _query_behind_it() -> None:
        """@brief A second query that must not wait for the holder.
        @version 1
        """
        await state._auto_refresh(str(repo))
        waiter_returned.set()

    with anyio.move_on_after(4):
        async with anyio.create_task_group() as tg:
            tg.start_soon(_hold_the_lock)
            await anyio.sleep(0.1)  # let the holder take it
            tg.start_soon(_query_behind_it)
            await waiter_returned.wait()
            tg.cancel_scope.cancel()

    assert waiter_returned.is_set(), (
        "the query behind a stalled refresh never returned. That is the hang: the build lock is "
        "held across the whole build, so an unbounded acquire makes one slow build block every "
        "later stale query in the process."
    )
    assert not released.is_set(), (
        "the holder finished, so the waiter was never actually made to queue — this test would "
        "be vacuous"
    )


## @brief A sub-index is addressed by name, and a bare root prefers the whole-repo index.
## @param tmp_path Pytest temp dir.
## @return None.
## @version 1
def test_a_sub_index_resolves_by_name(tmp_path: Path) -> None:
    """TWO SPELLINGS, NOT THREE. `sub_index` is its own parameter rather than a suffix folded
    into `target` — a composite string a caller has to construct has no schema of its own for a
    model to read, while a second named parameter does, and `index(action='targets')` reports the
    legal values without anyone building a string. So a sub-index resolves by (`target`,
    `sub_index`) together, or by its bare slug alone.

    A BARE ROOT WITH NO `sub_index` MEANS THE WHOLE REPOSITORY when one is indexed — not
    "whichever sub-index sorted first". That distinction is the point of the next test.

    @brief Sub-indexes resolve by (target, sub_index) and by slug.
    @version 2
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo = tmp_path / "split"
    repo.mkdir()

    whole = reg.register(repo)
    vendor = reg.register(repo, name="llama-cpp")

    assert state.resolve_target(str(repo.resolve()), "llama-cpp").slug == vendor.slug
    assert state.resolve_target(vendor.slug).slug == vendor.slug
    assert state.resolve_target(str(repo.resolve())).slug == whole.slug, (
        "a bare repository path must resolve to the whole-repository index, not a sub-index"
    )


## @brief With only sub-indexes, a bare root is refused rather than guessed.
## @param tmp_path Pytest temp dir.
## @return None.
## @version 1
def test_an_ambiguous_bare_root_is_refused(tmp_path: Path) -> None:
    """THE GUARD AGAINST THIS MODULE'S OWN WORST-NAMED DEFECT. `Answering`'s docstring states it:
    "a reply that read one repository's database and stamped another's path would be
    indistinguishable from a correct answer, and answering from the wrong index is this project's
    most expensive recorded defect."

    Once a root can hold several indexes, matching a bare path against the first record that
    happens to sort first is exactly that. So it REFUSES, and the refusal names every sub-index —
    a caller who cannot act on the error is being told half of one.

    @brief An ambiguous bare root raises and lists the alternatives.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo = tmp_path / "onlysubs"
    repo.mkdir()

    reg.register(repo, name="first-party")
    reg.register(repo, name="llama-cpp")

    with pytest.raises(RuntimeError) as excinfo:
        state.resolve_target(str(repo.resolve()))
    message = str(excinfo.value)
    ## The names are the actionable half; without them the caller knows only that it failed.
    assert "first-party" in message and "llama-cpp" in message, message


## @brief dossier() and search() reach the named sub-index's own database.
## @param tmp_path Pytest temp dir.
## @return None.
## @version 1
def test_dossier_and_search_route_to_the_named_sub_index(tmp_path: Path) -> None:
    """END TO END THROUGH THE TOOL METHODS THEMSELVES, not through `resolve_target` alone —
    `sub_index` was threaded through `db()`, `_route()`, `_answered()` and every `_search_*`
    handler individually, and a routing-layer test cannot see a spot where one of those forwards
    stayed `None` on its way to `self.db(...)`. Each sub-index gets its own marker table, so the
    only way `dossier`/`search` can see the right marker is if `sub_index` reached the file.

    ALSO PINS THE REPLY'S OWN `sub_index` FIELD. `_target_name` reports the shared repo root for
    every sub-index of one repository, so a reply that omitted `sub_index` would make a
    first-party answer and a vendored answer read as indistinguishable — the wrong-index failure
    this module's docstring names as the project's most expensive.

    @brief dossier/search reach the sub-index's own file and label their reply with its name.
    @version 1
    """
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo = tmp_path / "split"
    repo.mkdir()

    first = reg.register(repo, name="first-party")
    vendor = reg.register(repo, name="llama-cpp")
    for target, marker in ((first, "FIRST_PARTY_MARK"), (vendor, "VENDOR_MARK")):
        Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(target.db_path)
        conn.execute(f"CREATE TABLE {marker} (x INTEGER)")
        conn.commit()
        conn.close()
        write_build_signature(Path(target.db_path))

    def _table_exists(db_path: str, name: str) -> bool:
        conn = sqlite3.connect(db_path)
        try:
            row = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
            ).fetchone()
        finally:
            conn.close()
        return row is not None

    ## db() is the seam every tool method funnels through; proving it resolves to the right
    ## FILE is the load-bearing half of this test.
    db_first = state.tools.db(str(repo.resolve()), "first-party")
    db_vendor = state.tools.db(str(repo.resolve()), "llama-cpp")
    assert _table_exists(str(db_first), "FIRST_PARTY_MARK")
    assert not _table_exists(str(db_first), "VENDOR_MARK")
    assert _table_exists(str(db_vendor), "VENDOR_MARK")
    assert not _table_exists(str(db_vendor), "FIRST_PARTY_MARK")

    ## And a reply is labelled with the sub-index that actually answered it, not merely the
    ## shared repo root both would report identically.
    reply = state.tools.search(
        "nonexistent-symbol", target=str(repo.resolve()), sub_index="llama-cpp"
    )
    assert reply.get("sub_index") == "llama-cpp", (
        f"reply did not name which sub-index answered: {reply.get('sub_index')!r}"
    )
