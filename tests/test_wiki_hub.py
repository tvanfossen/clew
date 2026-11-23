# SPDX-License-Identifier: MIT
"""The wiki hub inside the MCP server (round 3, P4c-1).

Owner 2026-11-16: "not a separate server — embed it into the MCP server", and "a central spot to
explore all clew indexed repos". The MCP process runs an OPT-IN (`CLEW_WIKI=1`) HTTP thread:

  * bound to 127.0.0.1 on a port the OS picks, every request carrying the per-session token (a
    `?t=` query sets a strict cookie; anything else is refused);
  * `/` lists every registered target — its path, its index, and its wiki: built, building, not
    built, or UNREACHABLE when its checkout is gone (listed, never silently dropped);
  * `/r/<slug>/...` serves that target's wiki, built ON DEMAND by one builder at a time, a
    "building" page meanwhile; nothing outside the built site is ever served;
  * it never writes to stdout — stdout is the JSON-RPC wire.

@brief Tests for the wiki hub's HTTP thread.
@version 1
"""

from __future__ import annotations

import threading
import urllib.error
import urllib.request
from pathlib import Path

import anyio
import pytest

from clew.mcp_server.state import TargetRegistry


def _get(url: str, cookie: str = "") -> tuple[int, str, dict]:
    request = urllib.request.Request(url)
    if cookie:
        request.add_header("Cookie", cookie)
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            return reply.status, reply.read().decode(), dict(reply.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode(), dict(exc.headers)


class _Builder:
    """Writes a one-page 'site' instead of running Sphinx; can be held to observe "building"."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.calls: list[str] = []

    def __call__(self, target, out: Path) -> Path:  # noqa: ANN001
        self.calls.append(target.slug)
        self.release.wait(10)
        html = out / "html"
        html.mkdir(parents=True, exist_ok=True)
        (html / "index.html").write_text(f"<h1>wiki of {target.slug}</h1>")
        return html


@pytest.fixture
def hub(tmp_path: Path):  # noqa: ANN201
    """A registry with one live and one vanished target, and a running hub over it."""
    from clew.mcp_server.wikihub import WikiHub

    home = tmp_path / "state"
    live = tmp_path / "live"
    live.mkdir()
    gone = tmp_path / "gone"
    gone.mkdir()
    registry = TargetRegistry(home)
    live_t = registry.register(live)
    gone_t = registry.register(gone)
    gone.rmdir()
    builder = _Builder()
    server = WikiHub(home, builder=builder)
    server.start()
    yield server, builder, live_t, gone_t
    builder.release.set()
    server.stop()


def test_the_hub_binds_loopback_and_refuses_a_request_without_its_token(hub) -> None:  # noqa: ANN001
    """@brief 127.0.0.1 only; no token, no page."""
    server, *_ = hub
    assert server.host == "127.0.0.1" and server.port > 0
    status, _body, _h = _get(f"http://127.0.0.1:{server.port}/")
    assert status == 403
    status, _body, _h = _get(f"http://127.0.0.1:{server.port}/?t=wrong")
    assert status == 403


def test_the_hub_lists_every_target_and_says_which_are_unreachable(hub) -> None:  # noqa: ANN001
    """@brief The index of indexes; a vanished checkout stays listed."""
    server, _builder, live, gone = hub
    status, body, headers = _get(server.url)
    assert status == 200
    assert live.slug in body and f'href="/r/{live.slug}/"' in body
    row = body[body.index(gone.slug) :].split("</tr>")[0]
    assert "unreachable" in row
    assert (
        "HttpOnly" in headers.get("Set-Cookie", "") and "SameSite=Strict" in headers["Set-Cookie"]
    )


def test_a_wiki_is_built_on_demand_and_then_served(hub) -> None:  # noqa: ANN001
    """@brief First visit starts a build and says so; once built, the site is served."""
    server, builder, live, _gone = hub
    cookie = f"clew_wiki={server.token}"
    status, body, _h = _get(f"http://127.0.0.1:{server.port}/r/{live.slug}/", cookie)
    assert status == 202 and "Building" in body and 'http-equiv="refresh"' in body
    builder.release.set()
    for _ in range(100):
        status, body, _h = _get(f"http://127.0.0.1:{server.port}/r/{live.slug}/", cookie)
        if status == 200:
            break
        threading.Event().wait(0.05)
    assert status == 200 and f"wiki of {live.slug}" in body
    assert builder.calls == [live.slug]


def test_nothing_outside_the_site_is_served(hub) -> None:  # noqa: ANN001
    """@brief A path that climbs out of the built site is refused."""
    server, builder, live, _gone = hub
    builder.release.set()
    cookie = f"clew_wiki={server.token}"
    _get(f"http://127.0.0.1:{server.port}/r/{live.slug}/", cookie)
    for path in (
        f"/r/{live.slug}/../../registry.json",
        f"/r/{live.slug}/%2e%2e/%2e%2e/registry.json",
        "/r/nope/",
    ):
        status, _body, _h = _get(f"http://127.0.0.1:{server.port}{path}", cookie)
        assert status in (403, 404), path


def test_the_hub_writes_nothing_to_stdout(hub, capfd: pytest.CaptureFixture[str]) -> None:  # noqa: ANN001
    """THE STDOUT IS THE JSON-RPC WIRE: request logging goes to the logger, never print.

    @brief Clean stdout.
    """
    server, builder, live, _gone = hub
    builder.release.set()
    capfd.readouterr()
    _get(server.url)
    _get(f"http://127.0.0.1:{server.port}/r/{live.slug}/?t={server.token}")
    _get(f"http://127.0.0.1:{server.port}/")
    assert capfd.readouterr().out == ""


def test_serve_runs_the_hub_only_when_asked_and_records_its_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """OPT-IN: with `CLEW_WIKI=1` the hub runs beside the transport and its URL is written to the
    state root's `wiki.json`; when the transport ends the hub stops and the file goes.

    @brief serve() and the hub.
    """
    from clew.mcp_server import server as srv

    monkeypatch.setenv("CLEW_STATE_HOME", str(tmp_path / "state"))
    seen: dict[str, object] = {}

    async def transport(_mcp: object) -> None:
        record = tmp_path / "state" / "wiki.json"
        seen["exists"] = record.is_file()
        seen["text"] = record.read_text() if record.is_file() else ""

    class _State:
        async def keep_current(self, interval: float) -> None:  # noqa: ARG002
            await anyio.sleep_forever()

    monkeypatch.setenv("CLEW_WIKI", "1")
    anyio.run(srv.serve, None, _State(), 0, transport)
    assert seen["exists"] and "http://127.0.0.1:" in str(seen["text"])
    assert not (tmp_path / "state" / "wiki.json").exists()
    monkeypatch.delenv("CLEW_WIKI")
    anyio.run(srv.serve, None, _State(), 0, transport)
    assert seen["exists"] is False


# --- Round 3, P4c-2a: the live layer ------------------------------------------------------------

import json  # noqa: E402
import queue  # noqa: E402


def _stream(url: str, cookie: str, into: "queue.Queue[dict]") -> None:
    """Read server-sent events into a queue until the stream ends."""
    request = urllib.request.Request(url, headers={"Cookie": cookie})
    try:
        with urllib.request.urlopen(request, timeout=15) as reply:
            for raw in reply:
                line = raw.decode().strip()
                if line.startswith("data: "):
                    into.put(json.loads(line[6:]))
    except OSError:
        return


def test_a_refreshed_target_with_a_built_wiki_is_rebuilt_and_announced(hub) -> None:  # noqa: ANN001
    """LIVE VIEW: after the refresh loop refreshes a target whose wiki is built, the hub rebuilds
    it and tells every open page; a target with no built wiki is left alone.

    @brief P4c-2a: rebuild after refresh, `rebuilt` events.
    """
    server, builder, live, gone = hub
    builder.release.set()
    site = server.site_dir(live)
    site.mkdir(parents=True)
    (site / "index.html").write_text("old")
    events: queue.Queue[dict] = queue.Queue()
    reader = threading.Thread(
        target=_stream,
        args=(f"http://127.0.0.1:{server.port}/events", f"clew_wiki={server.token}", events),
        daemon=True,
    )
    reader.start()
    threading.Event().wait(0.3)
    server.refreshed([live.slug, gone.slug])
    event = events.get(timeout=10)
    assert event == {"type": "rebuilt", "slug": live.slug}
    assert builder.calls == [live.slug]


def test_pages_served_by_the_hub_carry_the_live_script(hub) -> None:  # noqa: ANN001
    """THE STATIC SITE STAYS SERVER-FREE: the hub injects `/live.js` into the pages it serves.

    @brief P4c-2a: live script injection.
    """
    server, builder, live, _gone = hub
    builder.release.set()
    site = server.site_dir(live)
    site.mkdir(parents=True)
    (site / "index.html").write_text("<html><body><p>x</p></body></html>")
    cookie = f"clew_wiki={server.token}"
    _status, page, _h = _get(f"http://127.0.0.1:{server.port}/r/{live.slug}/", cookie)
    assert '<script src="/live.js"></script></body>' in page
    status, script, headers = _get(f"http://127.0.0.1:{server.port}/live.js", cookie)
    assert status == 200 and "EventSource" in script and "javascript" in headers["Content-Type"]


def test_the_api_answers_with_the_query_engine(tmp_path: Path) -> None:
    """THE SAME ENGINE THE TOOLS USE: `/api/<slug>/dossier` and `/api/<slug>/search` answer
    through `clew.query.export`.

    @brief P4c-2a: JSON API.
    """
    from clew.cli import _build_argparser, _run_pipeline
    from clew.mcp_server.wikihub import WikiHub

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text(
        'def alpha():\n    """Alpha."""\n    return beta()\n\n\ndef beta():\n    """Beta."""\n    return 1\n'
    )
    home = tmp_path / "state"
    target = TargetRegistry(home).register(repo)
    _run_pipeline(
        _build_argparser().parse_args(["--output", target.db_path, "--repo-root", str(repo)])
    )
    server = WikiHub(home, builder=_Builder())
    server.start()
    try:
        cookie = f"clew_wiki={server.token}"
        base = f"http://127.0.0.1:{server.port}/api/{target.slug}"
        status, body, headers = _get(f"{base}/dossier?subject=alpha", cookie)
        reply = json.loads(body)
        assert status == 200 and "json" in headers["Content-Type"]
        assert reply["name"] == "alpha" and [c["name"] for c in reply["callees"]] == ["beta"]
        status, body, _h = _get(f"{base}/search?text=beta", cookie)
        assert status == 200 and any(r["name"] == "beta" for r in json.loads(body)["results"])
        status, _body, _h = _get(f"{base}/dossier", cookie)
        assert status == 400
    finally:
        server.stop()


def test_a_dossier_reply_carries_a_wiki_url_only_while_the_hub_runs(tmp_path: Path) -> None:
    """ADDITIVE, AND ONLY WHILE SERVING: a found function's reply names its symbol section on the
    hub (no token — the browser holds the session cookie), and the hub tells open pages the
    agent looked there. Without a linker no key is added.

    @brief P4c-2a: wiki_url and focus.
    """
    from clew.cli import _build_argparser, _run_pipeline
    from clew.mcp_server.tools_query import QueryTools
    from clew.mcp_server.wikihub import WikiHub

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "m.py").write_text('def alpha():\n    """Alpha."""\n    return 1\n')
    home = tmp_path / "state"
    target = TargetRegistry(home).register(repo)
    db = Path(target.db_path)
    _run_pipeline(_build_argparser().parse_args(["--output", str(db), "--repo-root", str(repo)]))
    plain = QueryTools(lambda: db, lambda: repo)
    assert "wiki_url" not in plain.dossier("alpha")
    server = WikiHub(home, builder=_Builder())
    seen: list[dict] = []
    server.publish = seen.append  # type: ignore[method-assign]
    server.port = 4242
    linked = QueryTools(lambda: db, lambda: repo)
    linked.wiki_linker = server.link
    reply = linked.dossier("alpha")
    assert reply["wiki_url"] == f"http://127.0.0.1:4242/r/{target.slug}/sym-m-py.html#s-alpha"
    assert "t=" not in reply["wiki_url"]
    assert seen == [{"type": "focus", "slug": target.slug, "url": reply["wiki_url"]}]
    assert "wiki_url" not in linked.dossier("no_such_function")


def test_serve_attaches_the_hub_to_the_tools_and_the_refresh_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """@brief P4c-2a: with the hub on, replies gain links and refreshes reach the hub."""
    from clew.mcp_server import server as srv

    monkeypatch.setenv("CLEW_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.setenv("CLEW_WIKI", "1")
    seen: dict[str, object] = {}

    class _Tools:
        wiki_linker = None

    class _State:
        tools = _Tools()
        wiki_hub = None

        async def keep_current(self, interval: float) -> None:  # noqa: ARG002
            await anyio.sleep_forever()

    state = _State()

    async def transport(_mcp: object) -> None:
        seen["linker"] = state.tools.wiki_linker
        seen["hub"] = state.wiki_hub

    anyio.run(srv.serve, None, state, 0, transport)
    assert seen["linker"] is not None and seen["hub"] is not None
    assert state.tools.wiki_linker is None and state.wiki_hub is None


def test_the_refresh_loop_tells_the_hub_what_it_refreshed(monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief P4c-2a: keep_current hands the refreshed slugs to the hub."""
    from clew.mcp_server.server import DocsDbServer

    told: list[list[str]] = []

    class _Hub:
        def refreshed(self, slugs: list[str]) -> None:
            told.append(slugs)

    server = DocsDbServer.__new__(DocsDbServer)
    server.wiki_hub = _Hub()

    async def refresh() -> list[str]:
        return ["a-123456"]

    monkeypatch.setattr(server, "refresh_touched", refresh, raising=False)
    server._watcher = type("W", (), {"sync": lambda self, paths: None, "stop": lambda self: None})()
    server._touched = {}

    async def run() -> None:
        with anyio.move_on_after(0.5):
            await server.keep_current(0.05)

    anyio.run(run)
    assert told and told[0] == ["a-123456"]
