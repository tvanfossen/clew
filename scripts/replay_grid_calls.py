# SPDX-License-Identifier: MIT
"""Replay the clew calls that failed or overflowed in the 1.4.0 grid, against that grid's own indexes.

WHY A SCRIPT. The 1.4.0 grid's transcripts named four call shapes that cost turns or tokens:
`direction='back'` refused, a variable `qualified` ignored (48.9 KB, three times), a 9-subject
batch of 48.5 KB, and a `found:false` note that sent agents to `index(action='status')`. Each is
replayed here through the real MCP tool layer, in the compact shape the plugin ships, and its reply
size and outcome are printed — so the fix is measured on the exact calls that motivated it, not on
a fixture. Run it on two trees (before / after) and compare.

    .venv/bin/python scripts/replay_grid_calls.py acceptance/runs/1.4.0-pending

@brief Replay the 1.4.0 grid's failing calls and report size and outcome.
@version 1
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ["CLEW_WIRE"] = "compact"

from clew.mcp_server.tools_query import QueryTools  # noqa: E402

## (target, label, dossier kwargs) — copied verbatim from the 1.4.0 transcripts.
CALLS = (
    (
        "entropic",
        "direction='back' (entropic c3d5640e call 3)",
        {"subject": "tokenize", "kind": "function", "depth": 2, "direction": "back"},
    ),
    (
        "mattermost",
        "variable qualified (mattermost c0a51f44 call 16)",
        {
            "subject": "enhanced",
            "qualified": "app.screens.browse_channels.index.enhanced",
            "max_body_lines": 40,
        },
    ),
    (
        "mattermost",
        "9-subject batch (mattermost 62c6894a call 2)",
        {
            "subject": [
                "NavigationSearch",
                "AgentChatHeader",
                "ChannelHeader",
                "GlobalDraftsAndScheduledPosts",
                "GlobalThreads",
                "ParticipantPlaybooks",
                "RecentMentionsScreen",
                "SavedMessages",
                "SearchScreen",
            ],
            "max_body_lines": 80,
            "max_neighbors": 5,
        },
    ),
    ("mattermost", "found:false note", {"subject": "no_such_symbol_xyz"}),
)


## @brief The run's index database and checkout for one target.
## @param run The run directory.
## @param target The target name.
## @return (db, repo) paths.
## @version 1
def _paths(run: Path, target: str) -> tuple[Path, Path]:
    """@brief Locate a target's index and checkout. @return Paths."""
    db = next((run / target / "state" / "targets").glob("*/clew.db"))
    return db, run / target / "repo"


## @brief Replay every call and print its size and outcome.
## @param run The run directory.
## @return Exit status.
## @version 1
def main(run: Path) -> int:
    """@brief Replay. @return 0."""
    for target, label, kwargs in CALLS:
        db, repo = _paths(run, target)
        tools = QueryTools(lambda db=db: db, lambda repo=repo: repo)
        try:
            reply = tools.dossier(**kwargs)
        except Exception as exc:  # the refusal IS the measurement
            print(f"{label:52} REFUSED  {exc}")
            continue
        size = len(json.dumps(reply, separators=(",", ":")))
        facts = {
            "found": reply.get("found", True),
            "sites": len(reply.get("sites") or []) or None,
            "selector_note": bool(reply.get("selector_note")),
            "not_answered": reply.get("not_answered"),
            "limited": bool(reply.get("_limited")),
            "says_call_status": "call status" in str(reply.get("note", "")),
        }
        print(f"{label:52} {size:>7,} B  {json.dumps({k: v for k, v in facts.items() if v})}")
    return 0


if __name__ == "__main__":
    sys.exit(main(Path(sys.argv[1])))
