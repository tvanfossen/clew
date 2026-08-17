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
# @brief Entry point.
# @return Process exit status.
# @version 1
def main() -> int:
    """@brief Dispatch a subcommand against a database.
    @return Exit status.
    @version 1
    """
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("command", choices=("inventory", "threads", "locks", "one"))
    ap.add_argument("--db", required=True, type=Path)
    ap.add_argument("--name", default="")
    args = ap.parse_args()

    if args.command == "one":
        one(args.db, args.name)
    else:
        {"inventory": inventory, "threads": threads, "locks": locks}[args.command](args.db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
