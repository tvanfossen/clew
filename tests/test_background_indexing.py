# SPDX-License-Identifier: MIT
"""gh#48 — the server builds and refreshes indexes the way a language server does.

Owner decision on the issue: "full #48 including background refresh, as this is no different than
an LSP contextually". Two behaviours follow from that, and both are pinned here:

  * A QUERY AGAINST AN INDEX THAT DOES NOT EXIST STARTS BUILDING IT. `_auto_refresh` only ever
    refreshed an index that resolved AND was stale, and an absent one is neither — so the state
    that most needed handling refused with advice, and on a split repository the advice was the
    one build that cannot finish. The build runs off the event loop; the query waits a bounded
    time and then answers or says it is still building.
  * THE INDEXES A SESSION USES ARE KEPT CURRENT BETWEEN QUERIES, so the next question after an
    edit does not pay for the refresh.

Builds are stubbed throughout: what is asserted is WHICH index gets built and WHEN, not doxygen.

@brief Tests for automatic first builds and the background refresh loop.
@version 1
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import anyio
import pytest

pytest.importorskip("mcp", reason="the MCP SDK is a REQUIRED dependency")

from clew.mcp_server import server as server_module
from clew.mcp_server import state as st
from clew.mcp_server.server import build_server, refresh_interval, serve
from clew.scope import FIRST_PARTY_INDEX


## @brief A stand-in `_run_build` that records what it was asked to build.
## @version 1
class _RecordingBuild:
    """Copies a real fixture index into the target's slot, so a query after the build answers,
    or returns a failure when constructed with one.

    @brief Recording stand-in build.
    @version 1
    """

    ## @brief Construct the stand-in.
    ## @param db Fixture database to install as each built index.
    ## @param error Failure message to return instead of building, or None.
    ## @version 1
    def __init__(self, db: Path, error: str | None = None) -> None:
        self.db = db
        self.error = error
        self.built: list[str | None] = []

    ## @brief Record and perform (or fail) one build.
    ## @param target The Target being built.
    ## @param _args Remaining positional build arguments, ignored.
    ## @return A `_run_build`-shaped result dict.
    ## @version 1
    def __call__(self, target: st.Target, *_args: object) -> dict[str, object]:
        """@brief Stand-in build. @return The result dict. @version 1"""
        self.built.append(target.name)
        if self.error is not None:
            return {"ok": False, "built": False, "error": self.error}
        Path(target.db_path).parent.mkdir(parents=True, exist_ok=True)
        Path(target.db_path).write_bytes(self.db.read_bytes())
        return {"ok": True, "built": True}


## @brief Make a directory a git work tree root.
## @param root The directory.
## @return The resolved root.
## @version 1
def _git_repo(root: Path) -> Path:
    """@brief Initialise a git work tree. @return The root. @version 1"""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    return root.resolve()


@pytest.mark.anyio
async def test_a_query_on_an_unbuilt_repository_builds_it_and_then_answers(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE LSP CASE. A git repository nobody has indexed is asked about; the query starts the
    build and, because this one finishes inside the bounded wait, the same call answers.

    @brief An absent index is built by the query that needed it.
    @version 1
    """
    repo = _git_repo(tmp_path / "plain")
    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    build = _RecordingBuild(rich_db)
    state._run_build = build

    await state._auto_refresh(str(repo))
    reply = state.tools.dossier("sensor_poll", target=str(repo))

    assert build.built == [None], f"the unsplit repository is built whole, got {build.built}"
    assert "found" not in reply, reply


@pytest.mark.anyio
async def test_an_unbuilt_split_repository_builds_first_party_never_the_whole(
    tmp_path: Path, rich_db: Path
) -> None:
    """THE BUILD gh#48 RECORDED DYING. A bare query on a split repository resolves to the whole
    target; building THAT indexes every vendored tree. First-party is what a bare call defaults
    to, so it is what gets built, and the reply says which part answered.

    @brief A bare query on an unbuilt split repository builds its first-party index.
    @version 1
    """
    repo = _git_repo(tmp_path / "split")
    (repo / "app.c").write_text("int app(void) { return 0; }\n", encoding="utf-8")
    nested = repo / "deps" / "vendored"
    nested.mkdir(parents=True)
    (nested / ".git").write_text("gitdir: ../../.git/modules/vendored\n", encoding="utf-8")
    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    build = _RecordingBuild(rich_db)
    state._run_build = build

    await state._auto_refresh(str(repo))
    reply = state.tools.dossier("sensor_poll", target=str(repo))

    assert build.built == [FIRST_PARTY_INDEX], f"expected only first-party, got {build.built}"
    assert reply.get("sub_index") == FIRST_PARTY_INDEX, reply


@pytest.mark.anyio
async def test_a_query_during_a_long_first_build_says_so_without_waiting_again(
    tmp_path: Path, rich_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE LONG-BUILD CASE. Only the call that started a build waits out the bound; the next one
    refuses at once, saying the index is being built — not that none exists, and not after another
    wait. Once the build lands, the same call answers.

    @brief In-progress first builds are reported immediately and answer once finished.
    @version 1
    """
    import threading
    import time

    monkeypatch.setattr(server_module, "_FIRST_BUILD_WAIT_SECONDS", 0.2)
    repo = _git_repo(tmp_path / "slow")
    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    release = threading.Event()
    finish = _RecordingBuild(rich_db)

    def _slow_build(target: st.Target, *args: object) -> dict[str, object]:
        release.wait(10)
        return finish(target, *args)

    state._run_build = _slow_build

    await state._auto_refresh(str(repo))
    started = time.monotonic()
    await state._auto_refresh(str(repo))
    assert time.monotonic() - started < 0.15, "a second query must not wait the bound again"
    with pytest.raises(RuntimeError, match="being built in the background"):
        state.tools.dossier("sensor_poll", target=str(repo))

    release.set()
    for job in list(state._first_builds.values()):
        await anyio.to_thread.run_sync(job.done.wait, 10)
    assert "found" not in state.tools.dossier("sensor_poll", target=str(repo))


@pytest.mark.anyio
async def test_a_failed_first_build_is_reported_and_not_retried_by_every_query(
    tmp_path: Path, rich_db: Path
) -> None:
    """A BUILD THAT FAILS DETERMINISTICALLY must not be relaunched by each call — that is the retry
    loop gh#48 saw agents fall into, moved inside the server. The refusal carries the failure, so
    the caller learns why instead of being told to build what just failed to build.

    @brief One failed automatic build; later queries report it instead of repeating it.
    @version 1
    """
    repo = _git_repo(tmp_path / "broken")
    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    build = _RecordingBuild(rich_db, error="doxygen was not found on PATH")
    state._run_build = build

    await state._auto_refresh(str(repo))
    await state._auto_refresh(str(repo))
    with pytest.raises(RuntimeError) as exc:
        state.tools.dossier("sensor_poll", target=str(repo))

    assert build.built == [None], f"one attempt, not one per query: {build.built}"
    assert "FAILED" in str(exc.value) and "doxygen was not found on PATH" in str(exc.value), (
        exc.value
    )


@pytest.mark.anyio
async def test_a_directory_that_is_not_a_repository_is_never_built_automatically(
    tmp_path: Path, rich_db: Path
) -> None:
    """A QUERY NAMING A DIRECTORY IS NOT CONSENT TO INDEX IT. `target=` accepts any directory, and a
    mistyped path must not start doxygen over a home directory. Without a git root or a registry
    record, the refusal still names the explicit build.

    @brief No automatic build for an unregistered non-git directory.
    @version 1
    """
    loose = tmp_path / "loose"
    loose.mkdir()
    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    build = _RecordingBuild(rich_db)
    state._run_build = build

    await state._auto_refresh(str(loose))

    assert build.built == []
    with pytest.raises(RuntimeError, match=r"index\(action='refresh'"):
        state.tools.dossier("sensor_poll", target=str(loose))


@pytest.mark.anyio
async def test_the_background_pass_refreshes_only_indexes_this_session_used(
    tmp_path: Path, rich_db: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE WORKING SET, NOT THE DISK. A session keeps current what it has answered from; a
    repository some other session registered is not this process's to rebuild on a timer.

    @brief refresh_touched rebuilds a stale index the session queried, and nothing else.
    @version 1
    """
    registry = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(registry)
    used, other = tmp_path / "used", tmp_path / "other"
    for repo in (used, other):
        repo.mkdir()
        target = registry.register(repo)
        Path(target.db_path).write_bytes(rich_db.read_bytes())
    state.tools.dossier("sensor_poll", target=str(used))

    monkeypatch.setattr(state, "_data_stale", lambda _target: True)
    build = _RecordingBuild(rich_db)
    state._run_build = build

    refreshed = await state.refresh_touched()

    assert refreshed == [st.target_for(used, registry.home).slug], refreshed
    assert build.built == [None]


@pytest.mark.anyio
async def test_serve_runs_the_background_loop_beside_the_transport(tmp_path: Path) -> None:
    """THE WIRING. `keep_current` can be perfect and never run; this drives `serve` with a stand-in
    transport that returns only once a background pass has happened, and with the loop disabled
    asserts no pass happens at all.

    @brief serve starts the refresh loop when enabled and not when disabled.
    @version 1
    """
    _mcp, state = build_server(st.TargetRegistry(tmp_path / "state"))
    passes: list[int] = []
    ran = anyio.Event()

    async def _pass() -> list[str]:
        passes.append(1)
        ran.set()
        return []

    state.refresh_touched = _pass

    async def _until_a_pass(_mcp: object) -> None:
        await ran.wait()

    with anyio.fail_after(5):
        await serve(_mcp, state, 0.01, _until_a_pass)
    assert passes, "an enabled loop must run beside the transport"

    passes.clear()

    async def _immediately(_mcp: object) -> None:
        await anyio.sleep(0.05)

    await serve(_mcp, state, 0, _immediately)
    assert passes == [], "interval 0 disables the loop"


def test_the_refresh_interval_reads_the_environment() -> None:
    """@brief Default, disabled, explicit and malformed interval values. @version 1"""
    assert refresh_interval({}) == server_module.DEFAULT_REFRESH_INTERVAL_SECONDS
    assert refresh_interval({server_module.REFRESH_INTERVAL_ENV: "0"}) == 0
    assert refresh_interval({server_module.REFRESH_INTERVAL_ENV: "5"}) == 5
    assert (
        refresh_interval({server_module.REFRESH_INTERVAL_ENV: "soon"})
        == server_module.DEFAULT_REFRESH_INTERVAL_SECONDS
    )
