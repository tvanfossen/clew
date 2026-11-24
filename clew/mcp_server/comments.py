# SPDX-License-Identifier: MIT
"""Wiki comments: what a person writes on a served page, kept for the agent (2.1, owner Q/A).

OWNER 2026-11-22: "I open a random test, see an issue with it, how do I tell you through clew wiki
serve my comment directly". Owner Q/A 2026-11-24 settled the route:

  * STORED WITH THE INDEXES, in an APPEND-ONLY log per repository
    (`<state>/comments/<key>.jsonl`, keyed like the pending count: a comment belongs to the
    repository, not to one of its sub-indexes).
    A comment is an `add` event; marking it read is a `read` event. Nothing is ever rewritten, so a
    read never loses a comment and the log is its own history.
  * THE HOOK SEES ONE INTEGER. `clew_hook` may only emit literals, ints and safe tokens (its
    bounded-codomain rule), so free comment text must never reach it. The store keeps a pending
    COUNT in `<state>/comments-pending/<key>`, keyed by `pending_key(repo_path)`; the hook derives
    the same key from `CLAUDE_PROJECT_DIR`.
  * THE AGENT READS THE TEXT through `index(action='comments')`: it arrives as tool data.

Limits refuse; they never cut. A comment over `MAX_BODY` characters is an error the page shows.

@brief Keep wiki comments for the agent.
@version 1
"""

from __future__ import annotations

import hashlib
import json
import os
import secrets
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

## Longest comment body accepted, in characters.
MAX_BODY = 4000
## Longest quoted selection, page name and anchor accepted.
MAX_QUOTE, MAX_PLACE = 1000, 512
## The directories, under the state root, of per-repository logs and pending counts.
LOG_DIR, PENDING_DIR = "comments", "comments-pending"
## One lock for every store in the process: the hub answers on several threads.
_LOCK = threading.Lock()


## @brief The pending-count file's name for a repository: a hash of its resolved path.
## @param repo_path The repository's root.
## @return 16 hex characters.
## @version 1
## @req REQ-DDB-WIKI-054
def pending_key(repo_path: str) -> str:
    """THE HOOK COMPUTES THIS TOO, from `CLAUDE_PROJECT_DIR` (`clew_hook._comment_key`), so both
    resolve the path the same way; a test pins that the two agree.

    @brief Pending key.
    @return Key.
    """
    return hashlib.sha256(os.path.realpath(repo_path).encode("utf-8")).hexdigest()[:16]


## @brief One repository's comment log and its pending count.
## @version 1
@dataclass(frozen=True)
class CommentStore:
    """@brief The log file and the pending-count file. @version 1"""

    path: Path
    pending: Path

    ## @brief The store for one repository.
    ## @param state_root clew's state root.
    ## @param repo_path The repository.
    ## @return The store.
    ## @version 1
    ## @req REQ-DDB-WIKI-054
    @classmethod
    def for_repo(cls, state_root: Path, repo_path: str) -> CommentStore:
        """@brief Locate a repository's store. @return Store."""
        key = pending_key(repo_path)
        return cls(
            Path(state_root) / LOG_DIR / f"{key}.jsonl", Path(state_root) / PENDING_DIR / key
        )

    ## @brief Record a comment.
    ## @param page The page it was made on.
    ## @param anchor The section it was made in, or "".
    ## @param quote The text the person selected, or "".
    ## @param body What they wrote.
    ## @return The stored comment.
    ## @version 1
    ## @req REQ-DDB-WIKI-054
    def add(self, page: str, anchor: str, quote: str, body: str) -> dict[str, Any]:
        """REFUSED, NEVER CUT: an empty body or a field over its limit raises ValueError naming it.

        @brief Add a comment.
        @return The comment.
        """
        _check(body, page, anchor, quote)
        record = {
            "op": "add",
            "id": secrets.token_hex(6),
            "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "page": page,
            "anchor": anchor,
            "quote": quote,
            "body": body,
        }
        with _LOCK:
            self._append(record)
            self._write_pending()
        return {**_public(record), "status": "new"}

    ## @brief Mark comments read (they stay in the log).
    ## @param ids The comments' ids.
    ## @return None.
    ## @version 1
    ## @req REQ-DDB-WIKI-054
    def mark_read(self, ids: list[str]) -> None:
        """@brief Mark read. @return None."""
        with _LOCK:
            for cid in ids:
                self._append({"op": "read", "id": cid})
            self._write_pending()

    ## @brief Every comment, oldest first, with its status.
    ## @return Comments.
    ## @version 1
    ## @req REQ-DDB-WIKI-054
    def all(self) -> list[dict[str, Any]]:
        """@brief All comments. @return List."""
        comments: dict[str, dict[str, Any]] = {}
        for event in self._events():
            if event.get("op") == "add":
                comments[event["id"]] = {**_public(event), "status": "new"}
            elif event.get("op") == "read" and event.get("id") in comments:
                comments[event["id"]]["status"] = "read"
        return list(comments.values())

    ## @brief The comments not yet read, oldest first.
    ## @return Comments.
    ## @version 1
    ## @req REQ-DDB-WIKI-054
    def unread(self) -> list[dict[str, Any]]:
        """@brief Unread comments. @return List."""
        return [c for c in self.all() if c["status"] == "new"]

    ## @brief Append one event to the log.
    ## @param event The event.
    ## @return None.
    ## @version 1
    ## @utility
    def _append(self, event: dict[str, Any]) -> None:
        """@brief Append. @return None."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as out:
            out.write(json.dumps(event, ensure_ascii=False) + "\n")

    ## @brief The log's events, in order; an unreadable line is skipped.
    ## @return Events.
    ## @version 1
    ## @utility
    def _events(self) -> list[dict[str, Any]]:
        """@brief Events. @return List."""
        if not self.path.is_file():
            return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return events

    ## @brief Rewrite the pending count, atomically.
    ## @return None.
    ## @version 1
    ## @utility
    def _write_pending(self) -> None:
        """@brief Pending count. @return None."""
        self.pending.parent.mkdir(parents=True, exist_ok=True)
        fresh = self.pending.with_suffix(".new")
        fresh.write_text(str(len(self.unread())), encoding="utf-8")
        os.replace(fresh, self.pending)


## @brief Refuse an empty body or any field over its limit.
## @param body The comment.
## @param page The page.
## @param anchor The anchor.
## @param quote The quoted text.
## @return None.
## @version 1
## @utility
def _check(body: str, page: str, anchor: str, quote: str) -> None:
    """@brief Validate. @return None."""
    if not body.strip():
        raise ValueError("a comment cannot be empty")
    limits = (("comment", body, MAX_BODY), ("quote", quote, MAX_QUOTE))
    limits += (("page", page, MAX_PLACE), ("anchor", anchor, MAX_PLACE))
    for name, value, limit in limits:
        if len(value) > limit:
            raise ValueError(f"the {name} is {len(value)} characters; the limit is {limit}")


## @brief A stored event's public fields.
## @param event The `add` event.
## @return Comment fields.
## @version 1
## @utility
def _public(event: dict[str, Any]) -> dict[str, Any]:
    """@brief Public fields. @return Dict."""
    return {k: event[k] for k in ("id", "at", "page", "anchor", "quote", "body")}
