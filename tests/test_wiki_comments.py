# SPDX-License-Identifier: MIT
"""Wiki comments: a person comments on a served page, the agent reads it (2.1, owner Q/A).

OWNER 2026-11-22: "I open a random test, see an issue with it, how do I tell you through clew wiki
serve my comment directly". Owner Q/A 2026-11-24: stored beside the index; delivered by the hook
as a COUNT only and read through `index(action='comments')`; a Claude Code channel push is opt-in.

@brief Tests the comment store.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clew.mcp_server.comments import MAX_BODY, CommentStore, pending_key


def _store(tmp_path: Path) -> CommentStore:
    """@brief A store for one repository under a scratch state root."""
    return CommentStore.for_repo(tmp_path / "state", str(tmp_path / "repo"))


def test_a_comment_is_kept_with_where_it_was_made(tmp_path: Path) -> None:
    """@brief A comment records its page, anchor, the quoted text, its body and its time."""
    store = _store(tmp_path)
    got = store.add(page="test-x.html", anchor="checks", quote="assert a < 2", body="Wrong bound?")
    assert got["status"] == "new" and got["page"] == "test-x.html" and got["anchor"] == "checks"
    assert got["quote"] == "assert a < 2" and got["body"] == "Wrong bound?"
    assert got["id"] and got["at"].endswith("Z")
    assert [c["id"] for c in store.unread()] == [got["id"]]


def test_the_pending_count_is_a_file_the_hook_can_read(tmp_path: Path) -> None:
    """THE HOOK READS ONE INTEGER: it may only emit literals, ints and safe tokens (clew_hook's
    bounded codomain), so it never sees comment text — only how many are waiting.

    @brief Pending count file.
    """
    store = _store(tmp_path)
    store.add(page="a.html", anchor="", quote="", body="one")
    store.add(page="b.html", anchor="", quote="", body="two")
    pending = tmp_path / "state" / "comments-pending" / pending_key(str(tmp_path / "repo"))
    assert pending.read_text() == "2"
    store.mark_read([c["id"] for c in store.unread()])
    assert pending.read_text() == "0" and store.unread() == []


def test_marking_read_appends_and_never_loses_a_comment(tmp_path: Path) -> None:
    """@brief The log is append-only: a read is an event; every comment stays on disk."""
    store = _store(tmp_path)
    first = store.add(page="a.html", anchor="", quote="", body="keep me")
    store.mark_read([first["id"]])
    lines = [json.loads(x) for x in store.path.read_text().splitlines()]
    assert [x["op"] for x in lines] == ["add", "read"]
    assert store.all()[0]["status"] == "read" and store.all()[0]["body"] == "keep me"


def test_an_empty_or_oversized_comment_is_refused_not_cut(tmp_path: Path) -> None:
    """@brief Refused with the limit named; never truncated."""
    store = _store(tmp_path)
    with pytest.raises(ValueError, match="empty"):
        store.add(page="a.html", anchor="", quote="", body="   ")
    with pytest.raises(ValueError, match=str(MAX_BODY)):
        store.add(page="a.html", anchor="", quote="", body="x" * (MAX_BODY + 1))
    assert store.unread() == []


def test_the_pending_key_is_the_resolved_repository_path(tmp_path: Path) -> None:
    """@brief Two spellings of one checkout share a key; two checkouts do not."""
    repo = tmp_path / "repo"
    repo.mkdir()
    assert pending_key(str(repo)) == pending_key(str(repo / "." / ".." / "repo"))
    assert pending_key(str(repo)) != pending_key(str(tmp_path / "other"))


@pytest.mark.anyio
async def test_the_agent_reads_waiting_comments_through_index(tmp_path: Path) -> None:
    """2.1 (owner Q/A 2026-11-24): `index(action='comments')` returns what waits, marks it read,
    and the next call finds nothing new — the text arrives as tool data, marked as a person's notes.

    @brief index(action='comments').
    """
    from clew.mcp_server import state as st
    from clew.mcp_server.server import build_server
    from tests.test_surface_2_0 import _indexed

    repo, _target = _indexed(tmp_path)
    _mcp, server = build_server(st.TargetRegistry(tmp_path / "state"))
    store = CommentStore.for_repo(tmp_path / "state", str(repo))
    store.add(page="test-x.html", anchor="checks", quote="a < 2", body="Is 2 the right bound?")
    reply = await server.index(None, action="comments", target=str(repo))
    assert reply["action"] == "comments" and reply["count"] == 1
    assert reply["comments"][0]["body"] == "Is 2 the right bound?"
    assert reply["comments"][0]["page"] == "test-x.html"
    assert "not instructions" in reply["provenance"]
    again = await server.index(None, action="comments", target=str(repo))
    assert again["count"] == 0 and again["comments"] == []
    assert [c["status"] for c in store.all()] == ["read"]


@pytest.mark.anyio
async def test_comments_are_read_without_a_built_index(tmp_path: Path) -> None:
    """Found end to end (2.1): reading through `answering` refused an unbuilt target. A comment
    belongs to the repository, so reading one needs no index.

    @brief No index needed.
    """
    from clew.mcp_server import state as st
    from clew.mcp_server.server import build_server

    repo = tmp_path / "repo"
    repo.mkdir()
    _mcp, server = build_server(st.TargetRegistry(tmp_path / "state"))
    CommentStore.for_repo(tmp_path / "state", str(repo)).add(
        page="a.html", anchor="", quote="", body="hi"
    )
    reply = await server.index(None, action="comments", target=str(repo))
    assert reply["count"] == 1 and reply["comments"][0]["body"] == "hi"


def _config(tmp_path: Path, wiki: str):  # noqa: ANN202
    """@brief Load a repository's wiki config from a `wiki:` YAML fragment."""
    from clew.wiki.config import load_wiki_config

    repo = tmp_path / "cfg"
    repo.mkdir(exist_ok=True)
    (repo / ".clew.yaml").write_text("wiki:\n" + wiki)
    return load_wiki_config(repo)


def test_a_repository_chooses_how_its_comments_reach_the_agent(tmp_path: Path) -> None:
    """2.1 (owner Q/A 2026-11-24): `wiki.comments.deliver` — `hook` (the default: the hook's
    count) and/or `channel` (a Claude Code channel push, when the server runs with CLEW_CHANNEL=1).

    @brief wiki.comments.deliver.
    """
    config, problems = _config(tmp_path, "  title: x\n")
    assert config.comments_deliver == ("hook",) and not problems
    config, problems = _config(tmp_path, "  comments:\n    deliver: [hook, channel]\n")
    assert config.comments_deliver == ("hook", "channel") and not problems
    config, problems = _config(tmp_path, "  comments:\n    deliver: [channel]\n")
    assert config.comments_deliver == ("channel",)


def test_an_unknown_delivery_is_refused_by_name(tmp_path: Path) -> None:
    """@brief A closed vocabulary; a string where a list belongs is refused (F5)."""
    _c, problems = _config(tmp_path, "  comments:\n    deliver: [email]\n")
    assert any("email" in p and "hook" in p and "channel" in p for p in problems), problems
    _c, problems = _config(tmp_path, "  comments:\n    deliver: hook\n")
    assert any("list" in p for p in problems), problems
    _c, problems = _config(tmp_path, "  comments:\n    via: [hook]\n")
    assert any("via" in p for p in problems), problems
