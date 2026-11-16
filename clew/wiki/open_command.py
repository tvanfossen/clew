# SPDX-License-Identifier: MIT
"""`clew wiki open` — one click into a repository's wiki (round 3, P5a).

Owner 2026-11-15: "need a one click entry into the wiki". When the MCP server's wiki hub is
running (`<state>/wiki.json` names a live process), this opens the hub's page for the
repository: live, rebuilt as the index refreshes. Otherwise it brings the index current, builds
the static site where the hub keeps it (beside the index) and opens it as a file — reading never
needs a server. The URL it opened is printed either way; `--no-browser` opens nothing.

@brief The `clew wiki open` verb.
@version 1
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

from .build import build_wiki


## @brief Open a repository's wiki: the running hub's page, else a freshly built static site.
## @param argv Arguments after `clew wiki open`.
## @return Exit status: 0 opened, 1 the build failed.
## @version 1
## @req REQ-DDB-WIKI-037
def open_main(argv: list[str]) -> int:
    """@brief Entry point. @return Exit status."""
    from ..mcp_server.state import state_home, target_for

    parser = argparse.ArgumentParser(prog="clew wiki open")
    parser.add_argument("--repo-root", help="the repository (default: the current directory)")
    parser.add_argument("--no-browser", action="store_true", help="print the URL only")
    args = parser.parse_args(argv)
    repo = Path(args.repo_root or Path.cwd()).resolve()
    home = state_home()
    target = target_for(repo, home)
    hub = _live_hub(home)
    if hub is not None:
        base, _, query = hub.partition("?")
        url = f"{base.rstrip('/')}/r/{target.slug}/" + (f"?{query}" if query else "")
    else:
        db = Path(target.db_path)
        try:
            _ensure_index(repo, db)
            html = build_wiki(repo, db, db.parent / "wiki")
        except (ValueError, OSError) as exc:
            sys.stderr.write(f"clew wiki open: {exc}\n")
            return 1
        url = (html / "index.html").as_uri()
    sys.stdout.write(url + "\n")
    if not args.no_browser:
        webbrowser.open(url)
    return 0


## @brief The running hub's URL, when its recording process is alive.
## @param home The state root.
## @return The URL, or None.
## @version 1
## @dg_internal
def _live_hub(home: Path) -> str | None:
    """A RECORD LEFT BY A PROCESS THAT DIED (a crash skips the cleanup) is ignored: its port is
    closed, and opening it would show the person an error page instead of their wiki.

    @brief Live hub.
    @return URL or None.
    """
    try:
        record = json.loads((Path(home) / "wiki.json").read_text(encoding="utf-8"))
        os.kill(int(record["pid"]), 0)
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return str(record["url"])


## @brief Build or refresh the repository's index where the MCP server reads it.
## @param repo_root The repository.
## @param db The index path.
## @return None.
## @version 1
## @dg_internal
def _ensure_index(repo_root: Path, db: Path) -> None:
    """@brief Ensure the index. @return None."""
    from ..refresh_command import refresh_main

    refresh_main(["--repo-root", str(repo_root), "--output", str(db)])
