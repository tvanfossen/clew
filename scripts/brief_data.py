#!/usr/bin/env python
# SPDX-License-Identifier: MIT
"""Pull the real figures an internal brief quotes, from a built index.

Every number in the brief is printed by this script against a named database, so a reader
can re-run it rather than taking the brief's word. Public targets only.

@brief Emit the figures an internal explainer brief quotes.
@version 1
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

from clew import query as q


##
# @brief One scalar from a COUNT query, or None when the table is absent.
# @param conn Open connection.
# @param sql The COUNT statement.
# @return The count, or None.
# @version 1
def _count(conn: sqlite3.Connection, sql: str) -> int | None:
    """@brief Count, tolerating an absent table.
    @return Count or None.
    @version 1
    """
    try:
        return int(conn.execute(sql).fetchone()[0])
    except sqlite3.Error:
        return None


##
# @brief Print the layer inventory for a database.
# @param db Path to a built index.
# @return None.
# @version 1
def inventory(db: Path) -> None:
    """@brief Emit per-layer row counts.
    @return None.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        rows = {
            "functions": "SELECT COUNT(*) FROM memberdef WHERE kind='function'",
            "call_edges": "SELECT COUNT(*) FROM call_edges",
            "threads": "SELECT COUNT(*) FROM threads",
            "lock_acquisitions": "SELECT COUNT(*) FROM lock_acquisitions",
            "req_edges": "SELECT COUNT(*) FROM req_edges",
            "file_docs": "SELECT COUNT(*) FROM file_docs",
        }
        for label, sql in rows.items():
            print(f"{label:20s} {_count(conn, sql)}")
    finally:
        conn.close()


##
# @brief Print the thread roster with spawn sites.
# @param db Path to a built index.
# @return None.
# @version 1
def threads(db: Path) -> None:
    """@brief Emit every thread, its entry and its spawn site.
    @return None.
    @version 1
    """
    roster = q.thread_roster(db)
    print(json.dumps(roster, default=lambda o: getattr(o, "__dict__", str(o)), indent=2)[:2600])


##
# @brief Print the lock roster.
# @param db Path to a built index.
# @return None.
# @version 1
def locks(db: Path) -> None:
    """@brief Emit every lock identity and its acquisition counts.
    @return None.
    @version 1
    """
    roster = q.lock_roster(db)
    print(json.dumps(roster, default=lambda o: getattr(o, "__dict__", str(o)), indent=2)[:2600])


##
# @brief Print one symbol's dossier, trimmed to the panels a brief shows.
# @param db Path to a built index.
# @param name Symbol to describe.
# @return None.
# @version 1
def one(db: Path, name: str) -> None:
    """@brief Emit a trimmed dossier for one symbol.
    @return None.
    @version 1
    """
    d = q.dossier(db, name)
    if d is None:
        print(f"{name}: not indexed")
        return
    fn = d.function
    print(f"subject   {d.subject}\nkind      {d.kind}")
    if fn is None:
        return
    print(f"file      {fn.file}:{fn.line_start}-{fn.line_end}")
    print(f"brief     {fn.brief}")
    print(f"liveness  {fn.liveness}")
    print(f"threads   {[t.name for t in fn.threads]}")
    print(f"locks     {[getattr(s, 'lock', s) for s in fn.locks_held]}")
    print(f"callers   {[e.name for e in fn.callers][:8]}")
    print(f"callees   {[e.name for e in fn.callees][:8]}")


##
# @brief Print the exact MCP tool reply for one subject.
# @param db Path to a built index.
# @param name Symbol to describe.
# @param repo Working tree the index was built from.
# @return None.
# @version 1
def wire(db: Path, name: str, repo: Path) -> None:
    """THE SERVED PAYLOAD, not the library return value. `QueryTools.dossier` is what the MCP
    tool call resolves to, so its dict is byte-for-byte what a client receives once serialized —
    including the `target` stamp and any staleness block. Calling it here avoids needing the
    long-running server to have the target registered.

    @brief Emit the exact dossier tool reply.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: db, lambda: repo, lambda: [])
    print(json.dumps(tools.dossier(name), indent=2, default=str))


##
# @brief Print the exact MCP search reply for one corpus.
# @param db Path to a built index.
# @param corpus Corpus to enumerate.
# @param repo Working tree the index was built from.
# @return None.
# @version 1
def wiresearch(db: Path, corpus: str, repo: Path) -> None:
    """@brief Emit the exact search tool reply for a corpus.
    @return None.
    @version 1
    """
    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: db, lambda: repo, lambda: [])
    print(json.dumps(tools.search(corpus=corpus), indent=2, default=str))


##
# @brief Inject a full tool reply into the brief, HTML-escaped.
# @param db Path to a built index.
# @param name Symbol to describe.
# @param repo Working tree the index was built from.
# @param page The HTML file carrying the FULL_DOSSIER_HERE marker.
# @return None.
# @version 1
def inject(db: Path, name: str, repo: Path, page: Path) -> None:
    """Escaped, and by script rather than by hand: a 600-line payload pasted through an editor
    is a payload nobody re-derives, and any `<` in it would silently become markup.

    @brief Replace the page's marker with the escaped reply.
    @return None.
    @version 1
    """
    import html

    from clew.mcp_server.tools_query import QueryTools

    tools = QueryTools(lambda: db, lambda: repo, lambda: [])
    payload = json.dumps(tools.dossier(name), indent=2, default=str)

    ## RENDER FROM A TEMPLATE, NEVER IN PLACE. Substituting into the output file consumes its
    ## own markers, so the second run has nothing to substitute and silently emits the first
    ## run's page — which is exactly what happened, and it looked like the edit had not landed.
    template = page.parent / "brief.tmpl.html"
    source = template if template.is_file() else page
    text = source.read_text(encoding="utf-8")

    maze = page.parent / "maze.html"
    if maze.is_file():
        text = text.replace("MAZE_HERE", maze.read_text(encoding="utf-8"))
    text = text.replace("FULL_DOSSIER_HERE", html.escape(payload))

    for marker in ("MAZE_HERE", "FULL_DOSSIER_HERE"):
        if marker in text:
            print(f"WARNING: {marker} still unsubstituted")

    page.write_text(text, encoding="utf-8")
    print(
        f"rendered {source.name} -> {page.name}: maze + {len(payload.splitlines())} dossier lines"
    )


##
# @brief Entry point.
# @return Process exit status.
# @version 1
def main() -> int:
    """@brief Dispatch a subcommand against a database.
    @return Exit status.
    @version 1
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "command", choices=("inventory", "threads", "locks", "one", "wire", "wiresearch", "inject")
    )
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--name", default="")
    ap.add_argument("--repo", default=Path("."), type=Path)
    ap.add_argument("--page", default=Path(".claude/tmp/clew-brief.html"), type=Path)
    args = ap.parse_args()

    if args.command == "one":
        one(args.db, args.name)
    elif args.command == "wire":
        wire(args.db, args.name, args.repo)
    elif args.command == "wiresearch":
        wiresearch(args.db, args.name, args.repo)
    elif args.command == "inject":
        inject(args.db, args.name, args.repo, args.page)
    else:
        {"inventory": inventory, "threads": threads, "locks": locks}[args.command](args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
