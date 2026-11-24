# SPDX-License-Identifier: MIT
"""The opt-in channel push of wiki comments (2.1, owner Q/A 2026-11-24).

CLEW_CHANNEL=1 makes the server declare Claude Code's experimental `claude/channel` capability;
a repository whose `wiki.comments.deliver` names `channel` has each comment pushed as a
`notifications/claude/channel`. A session on MCP revision 2026-07-28 is not registered as a
channel by Claude Code (research preview), so clew logs that and does not send; the hook count
and `index(action='comments')` still deliver.

@brief Tests the channel push.
@version 1
"""

from __future__ import annotations

from types import SimpleNamespace

import anyio
import pytest

from clew.mcp_server import channel


def test_the_query_tools_take_the_session_without_changing_their_schema(tmp_path) -> None:  # noqa: ANN001
    """THE SCHEMA IS THE ONE SURFACE A CLIENT CANNOT TRUNCATE, so the session is taken through the
    SDK's own context injection — a `ctx` the SDK fills and leaves out of the JSON Schema.

    @brief Session capture leaves schemas alone.
    """
    from mcp.server.mcpserver.utilities.context_injection import find_context_parameter

    from clew.mcp_server.server import _answering_with_refresh

    def dossier(subject: str, target: str | None = None) -> dict:
        return {"subject": subject}

    async def before(target, sub_index):  # noqa: ANN001, ANN202
        return None

    wrapped = _answering_with_refresh(dossier, before)
    assert find_context_parameter(wrapped) == "ctx"
    seen = SimpleNamespace(session=object())
    channel.CHANNEL.session = None
    assert anyio.run(lambda: wrapped(subject="x", ctx=seen)) == {"subject": "x"}
    assert channel.CHANNEL.session is seen.session


def test_a_comment_is_pushed_as_a_channel_notification(monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief On a handshake-era session the push is `notifications/claude/channel`."""
    sent = []

    async def notify(session, method, params):  # noqa: ANN001, ANN202
        sent.append((method, params))

    monkeypatch.setattr(channel, "raw_notify", notify)
    monkeypatch.setattr(channel, "protocol_version", lambda session: "2025-06-18")
    hub = channel.Channel()
    hub.session = object()
    comment = {
        "page": "test-x.html",
        "anchor": "checks",
        "quote": "a < 2",
        "body": "Bound?",
        "id": "ab",
    }
    assert anyio.run(lambda: hub.send("clew-123", comment)) is True
    method, params = sent[0]
    assert method == "notifications/claude/channel"
    assert "Bound?" in params["content"] and "test-x.html" in params["content"]
    assert params["meta"] == {"repo": "clew-123", "page": "test-x.html", "comment_id": "ab"}
    assert all(k.replace("_", "").isalnum() for k in params["meta"])


def test_a_2026_07_28_session_is_not_pushed_to(monkeypatch: pytest.MonkeyPatch, caplog) -> None:  # noqa: ANN001
    """@brief Claude Code drops channel events there; clew says so instead of sending."""
    sent = []

    async def notify(session, method, params):  # noqa: ANN001, ANN202
        sent.append(method)

    monkeypatch.setattr(channel, "raw_notify", notify)
    monkeypatch.setattr(channel, "protocol_version", lambda session: "2026-07-28")
    hub = channel.Channel()
    hub.session = object()
    with caplog.at_level("INFO"):
        assert (
            anyio.run(
                lambda: hub.send(
                    "r", {"page": "a", "anchor": "", "quote": "", "body": "b", "id": "1"}
                )
            )
            is False
        )
    assert not sent and "2026-07-28" in caplog.text


def test_no_session_yet_is_said_not_sent(caplog) -> None:  # noqa: ANN001
    """@brief Before any tool call there is no session to push on."""
    hub = channel.Channel()
    with caplog.at_level("INFO"):
        assert (
            anyio.run(
                lambda: hub.send(
                    "r", {"page": "a", "anchor": "", "quote": "", "body": "b", "id": "1"}
                )
            )
            is False
        )
    assert "no session" in caplog.text


def test_the_capability_is_declared_only_when_switched_on(monkeypatch: pytest.MonkeyPatch) -> None:
    """@brief CLEW_CHANNEL=1 → `{'claude/channel': {}}`; otherwise none."""
    monkeypatch.delenv(channel.CHANNEL_ENV, raising=False)
    assert channel.experimental_capabilities() == {}
    monkeypatch.setenv(channel.CHANNEL_ENV, "1")
    assert channel.experimental_capabilities() == {"claude/channel": {}}


def test_the_server_declares_the_channel_capability_only_when_switched_on(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:  # noqa: ANN001
    """@brief `initialize` carries `experimental: {claude/channel: {}}` with CLEW_CHANNEL=1."""
    from clew.mcp_server import state as st
    from clew.mcp_server.server import _init_options, build_server

    mcp, _state = build_server(st.TargetRegistry(tmp_path / "state"))
    monkeypatch.delenv(channel.CHANNEL_ENV, raising=False)
    assert not (_init_options(mcp).capabilities.experimental or {})
    monkeypatch.setenv(channel.CHANNEL_ENV, "1")
    assert _init_options(mcp).capabilities.experimental == {"claude/channel": {}}
    assert _init_options(mcp).capabilities.tools.list_changed is True


def _hub_with_repo(tmp_path, wiki_yaml: str | None):  # noqa: ANN001, ANN202
    """@brief A running hub over one repository, with an optional `wiki:` section."""
    from clew.mcp_server.state import TargetRegistry
    from clew.mcp_server.wikihub import WikiHub

    repo = tmp_path / "repo"
    repo.mkdir()
    if wiki_yaml is not None:
        (repo / ".clew.yaml").write_text("wiki:\n" + wiki_yaml)
    home = tmp_path / "state"
    target = TargetRegistry(home).register(repo)
    hub = WikiHub(home, builder=lambda t, out: out)
    pushed = []
    hub.on_comment = lambda slug, comment: pushed.append((slug, comment["body"]))
    hub.start()
    return hub, target, pushed


def _send(hub, target, body: str) -> int:  # noqa: ANN001
    """@brief POST one comment. @return HTTP status."""
    import json
    import urllib.error
    import urllib.request

    request = urllib.request.Request(
        f"http://127.0.0.1:{hub.port}/api/{target.slug}/comment",
        data=json.dumps({"page": "a.html", "anchor": "", "quote": "", "body": body}).encode(),
        method="POST",
    )
    request.add_header("Content-Type", "application/json")
    request.add_header("Cookie", f"clew_wiki={hub.token}")
    try:
        with urllib.request.urlopen(request, timeout=10) as reply:
            return reply.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_a_repository_that_chose_the_channel_has_its_comments_pushed(tmp_path) -> None:  # noqa: ANN001
    """@brief `deliver: [channel]` → pushed, and no hook count (the hook route was not chosen)."""
    from clew.mcp_server.comments import PENDING_DIR, pending_key

    hub, target, pushed = _hub_with_repo(tmp_path, "  comments:\n    deliver: [channel]\n")
    try:
        assert _send(hub, target, "push me") == 201
    finally:
        hub.stop()
    assert pushed == [(target.slug, "push me")]
    assert not (tmp_path / "state" / PENDING_DIR / pending_key(target.repo_path)).exists()


def test_by_default_a_comment_is_counted_for_the_hook_and_not_pushed(tmp_path) -> None:  # noqa: ANN001
    """@brief No `wiki.comments` → the hook's count, no push."""
    from clew.mcp_server.comments import PENDING_DIR, pending_key

    hub, target, pushed = _hub_with_repo(tmp_path, None)
    try:
        assert _send(hub, target, "count me") == 201
    finally:
        hub.stop()
    assert pushed == []
    assert (tmp_path / "state" / PENDING_DIR / pending_key(target.repo_path)).read_text() == "1"
