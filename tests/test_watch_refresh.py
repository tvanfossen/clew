# SPDX-License-Identifier: MIT
"""A save wakes the refresh loop; a query never waits long behind someone else's build.

1.3.6, Track 2 (owner 2026-11-13: the `watchdog` dependency). With the fast tier landing a
one-file refresh in well under a second, what remained between a save and a current index was the
WAIT: the 15-second sweep, and a query queued up to 120 s behind a follow-up full build.

@brief Tests for event-driven refresh and the bounded query wait.
@version 1
"""

from __future__ import annotations

import time
from pathlib import Path

import anyio
import pytest

from clew.mcp_server import server as server_module
from clew.mcp_server import state as st
from clew.mcp_server.server import build_server
from clew.mcp_server.watcher import relevant


def test_index_and_vcs_writes_do_not_wake_the_loop() -> None:
    """A REFRESH WRITES ITS OWN INDEX; if that woke the loop it would refresh forever.

    @brief VCS internals and clew's own files are filtered out.
    @return None.
    @version 1
    """
    assert relevant("/repo/src/a.c")
    for path in (
        "/repo/.git/index",
        "/repo/x/__pycache__/m.pyc",
        "/s/clew.db",
        "/s/clew.db.idxcache",
    ):
        assert not relevant(path), path


@pytest.mark.anyio
async def test_a_saved_file_wakes_the_refresh_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WITHIN A SECOND, NOT AN INTERVAL: the loop runs with a 60 s interval, and a file written
    into a watched repository must trigger a pass long before that.

    @brief A file event wakes keep_current.
    @version 1
    """
    registry = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(registry)
    repo = tmp_path / "repo"
    repo.mkdir()
    state._touched["t"] = registry.register(repo)
    passes: list[float] = []

    async def _record() -> list[str]:
        passes.append(time.monotonic())
        return []

    monkeypatch.setattr(state, "refresh_touched", _record)
    with anyio.move_on_after(10):
        async with anyio.create_task_group() as tg:
            tg.start_soon(state.keep_current, 60)
            await anyio.sleep(1.0)  # let the watch start
            started = time.monotonic()
            (repo / "saved.c").write_text("int x;\n")
            while not passes:
                await anyio.sleep(0.05)
            tg.cancel_scope.cancel()
    assert passes, "no refresh pass followed the save"
    assert passes[0] - started < 2.0, f"the pass came {passes[0] - started:.2f} s after the save"


@pytest.mark.anyio
async def test_a_query_waits_at_most_a_second_behind_another_build(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE BACKGROUND BUILD MAY HOLD THE LOCK FOR SECONDS; the query answers from the index as it
    stands — with its staleness notice — after one.

    @brief A stale query behind a held build lock returns within ~1 s.
    @version 1
    """
    monkeypatch.setattr(server_module, "_LOCK_WAIT_SECONDS", 120)
    reg = st.TargetRegistry(tmp_path / "state")
    _mcp, state = build_server(reg)
    repo = tmp_path / "busy"
    repo.mkdir()
    (repo / "a.c").write_text("int main(void){return 0;}\n", encoding="utf-8")
    target = state.resolve_target(str(repo))
    monkeypatch.setattr(state, "_data_stale", lambda _t: True)
    elapsed: list[float] = []

    async def _hold() -> None:
        async with state._build_lock(target.repo_path):
            await anyio.sleep(6)

    async def _query() -> None:
        started = time.monotonic()
        await state._auto_refresh(str(repo))
        elapsed.append(time.monotonic() - started)

    with anyio.move_on_after(5):
        async with anyio.create_task_group() as tg:
            tg.start_soon(_hold)
            await anyio.sleep(0.1)
            tg.start_soon(_query)
            while not elapsed:
                await anyio.sleep(0.05)
            tg.cancel_scope.cancel()
    assert elapsed and elapsed[0] < 2.0, f"the query waited {elapsed} s behind another build"
