"""Feasibility measurements for incremental doxygen regeneration (task #483).

WHY THIS EXISTS. A warm refresh of this repository costs 8672 ms, of which doxygen is
6218 ms (72%), while the tree-sitter harvest layers hit their per-file cache 2007 times
and reprocess 9 payloads. So the incremental machinery already works everywhere EXCEPT
the stage that dominates the clock. `IndexCache.tree_sha` folds the whole tree into one
hash, so one edited file invalidates the entire doxygen run.

The owner ruled that refresh must become incremental and automatic. Before building the
splice, two numbers decide its shape, and neither is guessable:

  `subset`  — what doxygen costs over N files instead of the whole tree. If a two-file
              run is ~200 ms the splice is obviously worth building; if doxygen's
              per-run fixed cost dominates, subsetting buys nothing and the answer is a
              different design.

  `closure` — how many OTHER files hold an xref INTO a changed file. Doxygen's xref pass
              is GLOBAL: editing B invalidates A->B edges even though A did not change,
              and a subset run that omits A cannot re-emit them. So the correct subset is
              the changed set plus its one-hop xref closure, and this reports how much
              that closure actually widens the run on real data. A closure that pulls in
              most of the tree means subsetting is a mirage.

Neither number is a benchmark to publish; both are inputs to a design decision.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tempfile
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from clew.doxygen import run_doxygen  # noqa: E402


##
# @brief Time a doxygen run restricted to an explicit file list.
# @param doxyfile The synthesized Doxyfile to base the run on.
# @param paths Repo-relative files to make the WHOLE INPUT list.
# @return Elapsed milliseconds and the memberdef row count produced.
# @version 1
def _time_subset(doxyfile: Path, paths: list[str]) -> tuple[int, int]:
    """Run doxygen with `replace_input`, so the given files are the entire INPUT.

    @brief Time one subset doxygen run.
    @return (elapsed_ms, memberdef_rows).
    @version 1
    """
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        started = time.monotonic()
        db = run_doxygen(
            doxyfile,
            work,
            extra_input=[str(REPO / p) for p in paths],
            replace_input=True,
            output_dir=work,
        )
        elapsed = int((time.monotonic() - started) * 1000)
        rows = 0
        if db.exists():
            conn = sqlite3.connect(db)
            try:
                rows = conn.execute("SELECT COUNT(*) FROM memberdef").fetchone()[0]
            finally:
                conn.close()
        return elapsed, rows


##
# @brief Report doxygen's cost as the input set grows.
# @param args Parsed arguments carrying the Doxyfile and the master database.
# @return Process exit status.
# @version 1
def cmd_subset(args: argparse.Namespace) -> int:
    """Compare a whole-tree run against runs over 1, 2, 5 and 20 files.

    The point is the SHAPE of the curve, not any single figure: a flat curve means
    doxygen's fixed startup dominates and subsetting cannot pay for itself.

    @brief Measure doxygen cost versus input size.
    @return 0.
    @version 1
    """
    conn = sqlite3.connect(args.db)
    try:
        files = [
            row[0]
            for row in conn.execute(
                "SELECT name FROM path WHERE name LIKE 'clew/%.py' ORDER BY name"
            )
        ]
    finally:
        conn.close()

    if not files:
        print("no clew/*.py rows in path — wrong database?", file=sys.stderr)
        return 1

    print(f"{'files':>8}  {'doxygen_ms':>11}  {'memberdef':>10}")
    for count in (1, 2, 5, 20, len(files)):
        if count > len(files):
            continue
        elapsed, rows = _time_subset(Path(args.doxyfile), files[:count])
        print(f"{count:>8}  {elapsed:>11}  {rows:>10}")
    return 0


##
# @brief Report how far the one-hop xref closure widens a changed set.
# @param args Parsed arguments carrying the master database.
# @return Process exit status.
# @version 1
def cmd_closure(args: argparse.Namespace) -> int:
    """For each indexed file, count the OTHER files that xref into it.

    A file's closure is what a correct subset run must also re-read, because doxygen's
    xref pass is global and a subset cannot re-emit an incoming edge whose source it
    never saw.

    @brief Measure the one-hop xref closure per file.
    @return 0.
    @version 1
    """
    conn = sqlite3.connect(args.db)
    try:
        total_files = conn.execute("SELECT COUNT(*) FROM path").fetchone()[0]
        ## An xref row links two memberdefs; each memberdef belongs to a file. The
        ## closure of file F is every file holding a memberdef that refers to a
        ## memberdef in F.
        rows = conn.execute(
            """
            SELECT tgt.name AS target_file, COUNT(DISTINCT src.name) AS incoming_files
            FROM xrefs x
            JOIN memberdef ms ON ms.rowid = x.src_rowid
            JOIN memberdef mt ON mt.rowid = x.dst_rowid
            JOIN path src ON src.rowid = ms.file_id
            JOIN path tgt ON tgt.rowid = mt.file_id
            WHERE src.name != tgt.name
            GROUP BY tgt.name
            ORDER BY incoming_files DESC
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        print(f"schema mismatch reading xrefs: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    if not rows:
        print("no cross-file xrefs found")
        return 0

    counts = [r[1] for r in rows]
    print(f"indexed files:            {total_files}")
    print(f"files with incoming xrefs: {len(rows)}")
    print(f"closure max:               {max(counts)}")
    print(f"closure median:            {sorted(counts)[len(counts) // 2]}")
    print(f"closure mean:              {sum(counts) / len(counts):.1f}")
    print()
    print("widest closures (a change here forces the most re-reading):")
    for name, incoming in rows[:10]:
        print(f"  {incoming:>4}  {name}")
    return 0


##
# @brief Compare a file's outbound xrefs in a subset run against the master index.
# @param args Parsed arguments carrying the master database and Doxyfile.
# @return Process exit status.
# @version 1
def cmd_outbound(args: argparse.Namespace) -> int:
    """The mirror of `closure`, and the measurement that decides SAFETY rather than cost.

    `closure` covers edges INTO a changed file: their sources must join the subset or the
    edge cannot be re-emitted. This covers edges OUT of a changed file, where the callee's
    definition lives in a file the subset omits. If doxygen drops those silently, a splice
    writes a graph missing outbound edges and reports a plausible row count — the exact
    shape this project keeps shipping. So the number to read is `subset` against `master`
    for the SAME file: equal means subsetting is safe on its own, lower means the splice
    must re-resolve outbound edges against the master database by name.

    @brief Measure outbound xref loss under a subset run.
    @return 0, or 1 when the database cannot be read.
    @version 1
    """
    conn = sqlite3.connect(args.db)
    try:
        ## Pick the file with the most OUTGOING cross-file xrefs: the worst case for loss,
        ## and the one where a silent drop is most visible.
        row = conn.execute(
            """
            SELECT src.name, COUNT(*) AS outgoing
            FROM xrefs x
            JOIN memberdef ms ON ms.rowid = x.src_rowid
            JOIN memberdef mt ON mt.rowid = x.dst_rowid
            JOIN path src ON src.rowid = ms.file_id
            JOIN path tgt ON tgt.rowid = mt.file_id
            WHERE src.name != tgt.name
            GROUP BY src.name
            ORDER BY outgoing DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            print("no cross-file xrefs in this database")
            return 0
        target, master_outgoing = row
        ## The one-hop closure of that file, which a correct subset run would include.
        closure = [
            r[0]
            for r in conn.execute(
                """
                SELECT DISTINCT tgt.name
                FROM xrefs x
                JOIN memberdef ms ON ms.rowid = x.src_rowid
                JOIN memberdef mt ON mt.rowid = x.dst_rowid
                JOIN path src ON src.rowid = ms.file_id
                JOIN path tgt ON tgt.rowid = mt.file_id
                WHERE src.name = ? AND src.name != tgt.name
                """,
                (target,),
            )
        ]
    except sqlite3.OperationalError as exc:
        print(f"schema mismatch: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    print(f"file:              {target}")
    print(f"master outbound:   {master_outgoing} cross-file xrefs")
    print(f"one-hop closure:   {len(closure)} files")

    for label, paths in (
        ("alone", [target]),
        ("with closure", [target, *closure]),
    ):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            db = run_doxygen(
                Path(args.doxyfile),
                work,
                extra_input=[str(Path(args.repo) / p) for p in paths],
                replace_input=True,
                output_dir=work,
            )
            if not db.exists():
                print(f"{label:>14}:   doxygen produced no database")
                continue
            sub = sqlite3.connect(db)
            try:
                got = sub.execute(
                    """
                    SELECT COUNT(*)
                    FROM xrefs x
                    JOIN memberdef ms ON ms.rowid = x.src_rowid
                    JOIN memberdef mt ON mt.rowid = x.dst_rowid
                    JOIN path src ON src.rowid = ms.file_id
                    JOIN path tgt ON tgt.rowid = mt.file_id
                    WHERE src.name LIKE ? AND src.name != tgt.name
                    """,
                    (f"%{Path(target).name}",),
                ).fetchone()[0]
            except sqlite3.OperationalError as exc:
                print(f"{label:>14}:   {exc}")
                sub.close()
                continue
            sub.close()
            kept = 100.0 * got / master_outgoing if master_outgoing else 0.0
            print(f"{label:>14}:   {got:>5} outbound  ({kept:.0f}% of master)")
    return 0


##
# @brief Check whether doxygen's refid strings survive a change of input set.
# @param args Parsed arguments carrying the master database and Doxyfile.
# @return Process exit status.
# @version 1
def cmd_refids(args: argparse.Namespace) -> int:
    """THE ASSUMPTION THE WHOLE SPLICE RESTS ON, so it is measured and not reasoned about.

    `memberdef.rowid` REFERENCES `refid.rowid`, and `xrefs.src_rowid`/`dst_rowid` reference
    `refid` as well. So if doxygen's `refid.refid` TEXT is derived from the ENTITY, two
    databases built from the same source agree on it, and a splice can join on that string
    and never guess a rowid. If instead it carries any dependence on the input SET — a
    counter, an ordering, a per-run disambiguator — then the same function gets different
    refids in a subset run, every join silently misses, and the splice writes a graph whose
    edges all point at nothing while every row count looks sane.

    Compares the refid recorded for each of a changed file's members in the master index
    against the refid a subset run assigns the same member.

    @brief Verify refid stability across input sets.
    @return 0 when stable, 1 when not.
    @version 1
    """
    target = args.file
    conn = sqlite3.connect(args.db)
    try:
        master = dict(
            conn.execute(
                """
                SELECT md.name, r.refid
                FROM memberdef md
                JOIN path p ON p.rowid = md.file_id
                JOIN refid r ON r.rowid = md.rowid
                WHERE p.name = ?
                """,
                (target,),
            ).fetchall()
        )
    except sqlite3.OperationalError as exc:
        print(f"schema mismatch: {exc}", file=sys.stderr)
        return 1
    finally:
        conn.close()

    if not master:
        print(f"no memberdefs for {target} in the master index", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        db = run_doxygen(
            Path(args.doxyfile),
            work,
            extra_input=[str(Path(args.repo) / target)],
            replace_input=True,
            output_dir=work,
        )
        if not db.exists():
            print("subset run produced no database", file=sys.stderr)
            return 1
        sub = sqlite3.connect(db)
        try:
            subset = dict(
                sub.execute(
                    """
                    SELECT md.name, r.refid
                    FROM memberdef md
                    JOIN refid r ON r.rowid = md.rowid
                    """
                ).fetchall()
            )
        finally:
            sub.close()

    shared = sorted(set(master) & set(subset))
    if not shared:
        print("no member names in common — cannot compare", file=sys.stderr)
        return 1
    agree = [n for n in shared if master[n] == subset[n]]
    print(f"file:              {target}")
    print(f"master members:    {len(master)}")
    print(f"subset members:    {len(subset)}")
    print(f"comparable:        {len(shared)}")
    print(f"refid IDENTICAL:   {len(agree)} / {len(shared)}")
    for name in shared[:5]:
        flag = "==" if master[name] == subset[name] else "!="
        print(f"  {flag} {name}\n       master {master[name]}\n       subset {subset[name]}")
    return 0 if len(agree) == len(shared) else 1


##
# @brief Drive the MCP auto-refresh hook in-process against a real target.
# @param args Parsed arguments (unused; the target is the repo under test).
# @return Process exit status.
# @version 1
def cmd_autorefresh(args: argparse.Namespace) -> int:
    """END-TO-END CHECK FOR THE QUERY-TIME REFRESH, run in-process because the live MCP
    server in a session is a separate long-lived process holding older code.

    Reports the staleness axes before and after. A pass is: stale on the `data` axis before,
    no axes after, and the build log showing the INCREMENTAL path rather than a full run.

    @brief Verify auto-refresh brings a stale index current.
    @return 0 when the refresh cleared the data axis, 1 otherwise.
    @version 1
    """
    import anyio

    from clew.mcp_server.freshness import code_identity, notices
    from clew.mcp_server.server import build_server
    from clew.mcp_server.state import TargetRegistry, db_status

    _mcp, state = build_server(TargetRegistry())
    target = state.resolve_target(str(REPO))
    before = notices(db_status(target), code_identity())
    print("axes before:", [n["axis"] for n in before] or "(current)")
    if not any(n["axis"] == "data" for n in before):
        print("nothing to do — edit a file first so the data axis is stale", file=sys.stderr)
        return 1

    ## Pass the target EXPLICITLY. `state.active` is derived from --repo /
    ## CLAUDE_PROJECT_DIR, which this probe does not set, so `None` would make the hook
    ## return before measuring anything — and report a clean pass for the wrong reason.
    print("active target:", state.active.repo_path if state.active else "(none)")
    anyio.run(state._auto_refresh, str(REPO))

    after = notices(db_status(target), code_identity())
    print("axes after: ", [n["axis"] for n in after] or "(current)")
    return 0 if not any(n["axis"] == "data" for n in after) else 1


##
# @brief Parse arguments and dispatch a subcommand.
# @return Process exit status.
# @version 3
def main() -> int:
    """@brief Entry point.
    @return Exit status.
    @version 1
    """
    parser = argparse.ArgumentParser(description=__doc__)
    default_db = Path.home() / ".local/state/clew/targets/docs-db-57bf14/clew.db"
    default_doxyfile = (
        Path.home() / ".local/state/clew/targets/docs-db-57bf14/clew.doxygen/Doxyfile.synth"
    )
    parser.add_argument("--db", default=str(default_db))
    parser.add_argument("--doxyfile", default=str(default_doxyfile))
    parser.add_argument("--repo", default=str(REPO))
    parser.add_argument("--file", default="clew/mcp_server/tools_query.py")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("subset", help="doxygen cost versus input size")
    sub.add_parser("closure", help="one-hop xref closure per file")
    sub.add_parser("outbound", help="outbound xref loss under a subset run")
    sub.add_parser("refids", help="refid stability across input sets")
    sub.add_parser("autorefresh", help="drive the MCP auto-refresh hook in-process")
    args = parser.parse_args()
    return {
        "subset": cmd_subset,
        "closure": cmd_closure,
        "outbound": cmd_outbound,
        "refids": cmd_refids,
        "autorefresh": cmd_autorefresh,
    }[args.cmd](args)


if __name__ == "__main__":
    sys.exit(main())
