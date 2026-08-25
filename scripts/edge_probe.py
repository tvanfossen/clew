"""Why a specific call edge is missing from an index (task #482).

WHY A SCRIPT AND NOT AN INLINE QUERY. "Is this edge present?" is the question this project
gets wrong most often, and it has been answered three times from a throwaway command whose
exact shape nobody could reproduce afterwards. A missing edge has at least four distinct
causes and they need different fixes:

  1. the CALL SITE was never harvested (the file is out of scope, or the AST layer skipped it);
  2. the callee NAME was harvested but resolved to no rowid (nothing in `memberdef` matches);
  3. the edge was created and then PRUNED (dominated-fuzzy suppression, the self-edge guard);
  4. the edge exists and the QUERY layer is collapsing or hiding it.

Reporting "no edge" without saying which is the mistake this repo's own notes call out — "no
rows is a claim about the DETECTOR until you have read the source". So this walks the four in
order and names the one that applies.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))


##
# @brief Every memberdef row a bare name denotes, with the facts that decide ranking.
# @param conn Open index connection.
# @param name Bare function name.
# @return Rows of (rowid, file, scope, in_place, bodystart, is_test).
# @version 1
def _rows_for(conn: sqlite3.Connection, name: str) -> list[tuple]:
    """@brief List every row a name denotes.
    @return Row tuples.
    @version 1
    """
    has_scope_tbl = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='test_scope'"
    ).fetchone()[0]
    test_expr = (
        "EXISTS (SELECT 1 FROM test_scope ts WHERE ts.path_rowid = md.file_id)"
        if has_scope_tbl
        else "0"
    )
    return conn.execute(
        f"""SELECT md.rowid, p.name, COALESCE(md.scope, ''),
                   (md.file_id = md.bodyfile_id), COALESCE(md.bodystart, 0), {test_expr}
            FROM memberdef md JOIN path p ON p.rowid = md.file_id
            WHERE md.name = ? AND md.kind = 'function' ORDER BY md.rowid""",  # noqa: S608
        (name,),
    ).fetchall()


##
# @brief Diagnose why one caller-to-callee edge is absent, naming the stage responsible.
# @param args Parsed arguments carrying the database, caller and callee names.
# @return Process exit status; 0 when the edge is present.
# @version 1
def cmd_why(args: argparse.Namespace) -> int:
    """Walks the four causes in order and stops at the first that explains the absence.

    @brief Explain a missing call edge.
    @return 0 when present, 1 when absent.
    @version 1
    """
    conn = sqlite3.connect(args.db)
    try:
        callers = _rows_for(conn, args.caller)
        callees = _rows_for(conn, args.callee)
        print(f"caller {args.caller!r}: {len(callers)} row(s)")
        for r in callers:
            print(f"   rowid={r[0]:<7} in_place={bool(r[3])!s:<5} test={bool(r[5])!s:<5} {r[1]}")
        print(f"callee {args.callee!r}: {len(callees)} row(s)")
        for r in callees:
            print(f"   rowid={r[0]:<7} in_place={bool(r[3])!s:<5} test={bool(r[5])!s:<5} {r[1]}")

        if not callees:
            print("\nCAUSE 2: the callee resolves to NO memberdef row at all.")
            return 1

        caller_ids = [r[0] for r in callers]
        callee_ids = [r[0] for r in callees]
        marks_a = ",".join("?" * len(caller_ids))
        marks_b = ",".join("?" * len(callee_ids))

        edges = conn.execute(
            f"""SELECT e.source, e.confidence, e.caller_rowid, e.callee_rowid
                FROM call_edges e
                WHERE e.caller_rowid IN ({marks_a}) AND e.callee_rowid IN ({marks_b})""",  # noqa: S608
            [*caller_ids, *callee_ids],
        ).fetchall()
        if edges:
            print(f"\nEDGE PRESENT ({len(edges)} row(s)):")
            for e in edges:
                print(f"   source={e[0]:<16} confidence={e[1]:<10} {e[2]} -> {e[3]}")
            return 0

        ## Does the caller have ANY outgoing edges? None at all means the call site was never
        ## harvested; some means the harvest ran and this particular callee did not resolve.
        out = conn.execute(
            f"SELECT e.source, COUNT(*) FROM call_edges e "  # noqa: S608
            f"WHERE e.caller_rowid IN ({marks_a}) GROUP BY e.source",
            caller_ids,
        ).fetchall()
        print(f"\nNO EDGE. The caller's outgoing edges by source: {out or 'NONE'}")
        if not out:
            print("CAUSE 1: the call site was never harvested — no outgoing edges at all.")
        elif not any(src.startswith("ast") for src, _ in out):
            print(
                "CAUSE 1: doxygen edges exist but NO `ast`/`ast_member` edges do, so the "
                "tree-sitter layer did not harvest this file's call sites."
            )
        else:
            print(
                "CAUSE 2 or 3: the AST layer harvested this caller, so the callee name either "
                "resolved to no rowid or the edge was created and then pruned."
            )
        return 1
    finally:
        conn.close()


##
# @brief List one function's outgoing edges with callee names and provenance.
# @param args Parsed arguments carrying the database and the caller name.
# @return Process exit status.
# @version 1
def cmd_out(args: argparse.Namespace) -> int:
    """The follow-on question after `why` narrows to cause 2 or 3: the caller HAS ast edges, so
    which callees did they land on? A member-call site that produced one `ast_member` edge when
    the body makes two member calls says the unwrap succeeded once and failed once — which is a
    different bug from failing everywhere.

    @brief Show a caller's outgoing edges.
    @return 0.
    @version 1
    """
    conn = sqlite3.connect(args.db)
    try:
        rows = _rows_for(conn, args.caller)
        ids = [r[0] for r in rows]
        marks = ",".join("?" * len(ids))
        for src_row in conn.execute(
            f"""SELECT e.source, e.confidence, ce.name, cp.name, e.caller_rowid
                FROM call_edges e
                JOIN memberdef ce ON ce.rowid = e.callee_rowid
                JOIN path cp ON cp.rowid = ce.file_id
                WHERE e.caller_rowid IN ({marks})
                ORDER BY e.source, ce.name""",  # noqa: S608
            ids,
        ):
            print(
                f"  {src_row[0]:<16} {src_row[1]:<10} -> {src_row[2]:<28} "
                f"[{src_row[3]}] from rowid {src_row[4]}"
            )
    finally:
        conn.close()
    return 0


##
# @brief Parse arguments and dispatch.
# @return Process exit status.
# @version 1
def main() -> int:
    """@brief Entry point.
    @return Exit status.
    @version 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="index database to inspect")
    sub = parser.add_subparsers(dest="cmd", required=True)
    why = sub.add_parser("why", help="explain why one call edge is missing")
    why.add_argument("caller")
    why.add_argument("callee")
    out = sub.add_parser("out", help="list a caller's outgoing edges")
    out.add_argument("caller")
    args = parser.parse_args()
    return {"why": cmd_why, "out": cmd_out}[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
