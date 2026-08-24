"""Incremental doxygen regeneration: re-read a SUBSET and splice it into the master.

WHY THIS EXISTS (task #483). A warm refresh of this repository costs ~8.7 s, of which
doxygen is ~6.2 s — 72%. Every other stage is already incremental: the tree-sitter harvest
layers hit their per-file cache ~2000 times and reprocess a handful. Doxygen is the only
whole-tree stage left, because `IndexCache.tree_sha` folds the entire tree into ONE hash,
so editing one file invalidates the entire run.

The owner ruled refresh must be incremental and automatic, and the reason is ADOPTION, not
tidiness: an index that feels expensive to refresh is an index agents stop consulting, so a
manual refresh step is itself a cause of non-use.

THE JOIN KEY IS `refid.refid`, AND THAT IS MEASURED RATHER THAN ASSUMED. `memberdef.rowid`
REFERENCES `refid.rowid`, and `xrefs.src_rowid`/`dst_rowid` reference `refid` too. Doxygen
derives the refid TEXT from the entity, not from a per-run counter: a subset run and a
whole-tree run assign the SAME string to the same member (measured 70/70 on
`clew/mcp_server/tools_query.py`). So the splice joins on text and never guesses a rowid.
Had that gone the other way — any dependence on input ORDER or SET — every join would miss
silently and the splice would write a graph of edges pointing at nothing, with every row
count looking sane.

THE SUBSET NEEDS BOTH CLOSURE DIRECTIONS, WHICH IS ALSO MEASURED. Doxygen's xref pass is
global, so a subset sees only the calls it can resolve inside itself:

  - measured: a subset run of one changed file ALONE recovered 0 of that file's 38 outbound
    cross-file xrefs, and reported a perfectly plausible row count;
  - measured: adding the one-hop closure recovered 38 of 38.

Inbound closure (files whose members refer INTO a changed file) preserves edges arriving at
the change. Outbound closure (files holding the members a changed file refers TO) preserves
edges leaving it. They are DIFFERENT SETS and omitting either loses edges quietly, so
`xref_closure` unions both.

WHAT IS DELETED IS THE CHANGED SET, NOT THE SUBSET. The closure files are pulled into the
doxygen run purely so their edges resolve; their own rows in the master are still current
and are left untouched. Deleting them would throw away rows nothing asked to refresh.

REFID ROWS ARE NEVER DELETED. They are the join keys, and an orphan refid is inert — it
costs a row and breaks nothing, whereas deleting one would renumber the identity space that
the next splice joins against.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)

## Tables whose rows hang off a memberdef rowid and must go when that memberdef does.
_MEMBER_DEPENDENTS = (
    ("memberdef_param", "memberdef_id"),
    ("member", "memberdef_rowid"),
)

## Tables whose rows hang off a compounddef rowid.
_COMPOUND_DEPENDENTS = (
    ("contains", "inner_rowid"),
    ("contains", "outer_rowid"),
    ("compoundref", "base_rowid"),
    ("compoundref", "derived_rowid"),
    ("member", "scope_rowid"),
)


##
# @brief What one splice actually changed, for logging and for tests to assert on.
# @version 1
@dataclass
class SpliceReport:
    """Counts are per-table so a caller can see WHICH layer moved, not just that something
    did. A splice that deletes and inserts nothing is a bug the aggregate would hide.

    @brief Per-table record of a splice.
    @version 1
    """

    files_replaced: int = 0
    files_removed: int = 0
    members_deleted: int = 0
    members_inserted: int = 0
    compounds_deleted: int = 0
    compounds_inserted: int = 0
    xrefs_deleted: int = 0
    xrefs_inserted: int = 0
    xrefs_unresolved: int = 0
    relations_inserted: int = 0
    relations_dropped: int = 0
    skipped: list[str] = field(default_factory=list)

    ##
    # @brief One-line summary for the build log.
    # @return Human-readable description.
    # @version 2
    # @dg_internal
    def describe(self) -> str:
        """@brief Summarise the splice.
        @return Description string.
        @version 2
        """
        return (
            f"{self.files_replaced} file(s) respliced, "
            f"{self.files_removed} removed: "
            f"memberdef -{self.members_deleted}/+{self.members_inserted}, "
            f"compounddef -{self.compounds_deleted}/+{self.compounds_inserted}, "
            f"xrefs -{self.xrefs_deleted}/+{self.xrefs_inserted}, "
            f"relations +{self.relations_inserted} "
            f"({self.xrefs_unresolved} xref + {self.relations_dropped} relation dropped, "
            f"endpoint absent)"
        )


##
# @brief Reduce a doxygen path row to its repo-relative form.
# @param name The `path.name` value, absolute or already relative.
# @param repo_root Absolute repository root.
# @return Repo-relative path string, or the input when it lies outside the repo.
# @version 1
# @req REQ-DDB-INDEX-002
def normalize_path(name: str, repo_root: Path) -> str:
    """Doxygen emits MOSTLY repo-relative names but not exclusively — the pipeline's
    `fix_doxygen_paths` stage rewrites the remainder later, and this splice runs BEFORE
    that. So two databases can spell the same file differently and a naive string compare
    would treat one file as two, silently declining to delete the stale rows.

    @brief Normalise a doxygen path to repo-relative.
    @return Repo-relative string.
    @version 1
    """
    candidate = Path(name)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.relative_to(repo_root).as_posix()
    except ValueError:
        return candidate.as_posix()


##
# @brief Map every repo-relative file path in a doxygen database to its path rowid.
# @param conn Open connection to a doxygen database.
# @param repo_root Absolute repository root.
# @return Mapping of repo-relative path to path rowid.
# @version 1
# @dg_internal
def _file_rowids(conn: sqlite3.Connection, repo_root: Path) -> dict[str, int]:
    """@brief Index a database's file rows by normalised path.
    @return Path-to-rowid mapping.
    @version 1
    """
    return {
        normalize_path(str(name), repo_root): int(rowid)
        for rowid, name in conn.execute("SELECT rowid, name FROM path WHERE type = 1")
    }


##
# @brief The files a correct subset run must include alongside the changed set.
# @param master_db Path to the previous whole-tree doxygen database.
# @param changed Repo-relative paths whose content changed.
# @param repo_root Absolute repository root.
# @return Repo-relative paths to feed doxygen: the changed set plus both closure directions.
# @version 1
# @req REQ-DDB-INDEX-002
def xref_closure(master_db: Path, changed: set[str], repo_root: Path) -> set[str]:
    """BOTH DIRECTIONS, and the asymmetry is the whole point. A subset run can only emit an
    edge when it can see BOTH endpoints, so:

      - inbound  — files holding members that refer INTO a changed file. Without them the
        edges arriving at the change cannot be re-emitted.
      - outbound — files holding the members a changed file refers TO. Without them the
        edges leaving the change cannot be re-emitted. Measured: 0 of 38 survived a
        changed-file-only run.

    Returns the union including `changed` itself, so the result is directly the doxygen
    INPUT list.

    @brief Compute the bidirectional one-hop xref closure.
    @return Paths to re-read.
    @version 1
    """
    if not changed:
        return set()
    conn = sqlite3.connect(master_db)
    try:
        pairs = conn.execute(
            """
            SELECT src.name, tgt.name
            FROM xrefs x
            JOIN memberdef ms ON ms.rowid = x.src_rowid
            JOIN memberdef mt ON mt.rowid = x.dst_rowid
            JOIN path src ON src.rowid = ms.file_id
            JOIN path tgt ON tgt.rowid = mt.file_id
            """
        ).fetchall()
    except sqlite3.OperationalError as exc:
        logger.warning(
            "doxygen splice: cannot read xrefs from %s (%s) — falling back to a full run",
            master_db,
            exc,
        )
        return set()
    finally:
        conn.close()

    result = set(changed)
    for raw_src, raw_dst in pairs:
        src = normalize_path(str(raw_src), repo_root)
        dst = normalize_path(str(raw_dst), repo_root)
        ## Outbound: the change refers to dst, so dst's definitions must be visible.
        if src in changed:
            result.add(dst)
        ## Inbound: src refers to the change, so src's call sites must be visible.
        if dst in changed:
            result.add(src)
    return result


##
# @brief Resolve a refid string to a rowid in the target database, creating it if absent.
# @param conn Open connection to the database being written.
# @param refid The refid TEXT to resolve.
# @return The rowid that refid occupies.
# @version 1
# @dg_internal
def _refid_rowid(conn: sqlite3.Connection, refid: str) -> int:
    """`refid.refid` is UNIQUE, so INSERT OR IGNORE followed by SELECT is idempotent and
    yields a STABLE rowid across repeated splices. That stability is what lets a re-inserted
    memberdef reclaim the rowid it had before deletion, satisfying
    `memberdef.rowid REFERENCES refid.rowid` without any renumbering.

    @brief Get or create a refid row.
    @return Its rowid.
    @version 1
    """
    conn.execute("INSERT OR IGNORE INTO refid(refid) VALUES (?)", (refid,))
    row = conn.execute("SELECT rowid FROM refid WHERE refid = ?", (refid,)).fetchone()
    return int(row[0])


##
# @brief Ensure a file has a path row, returning its rowid.
# @param conn Open connection to the database being written.
# @param rel Repo-relative path.
# @param cache Mutable path-to-rowid map kept in step with the database.
# @return The path rowid for `rel`.
# @version 1
# @dg_internal
def _path_rowid(conn: sqlite3.Connection, rel: str, cache: dict[str, int]) -> int:
    """@brief Get or create a path row.
    @return Its rowid.
    @version 1
    """
    existing = cache.get(rel)
    if existing is not None:
        return existing
    cur = conn.execute(
        "INSERT INTO path(type, local, found, name) VALUES (1, 1, 1, ?)",
        (rel,),
    )
    if cur.lastrowid is None:
        ## Not defensive padding: a silent 0 here would point every member of this file at
        ## path rowid 0, which does not exist, and the file would read as indexed-but-empty.
        raise RuntimeError(f"sqlite reported no rowid inserting path {rel!r}")
    cache[rel] = int(cur.lastrowid)
    return cache[rel]


##
# @brief Delete every row belonging to one file, leaving refid rows intact.
# @param conn Open connection to the working copy.
# @param file_rowid The path rowid whose contents are being replaced.
# @param report Accumulating counts.
# @return None.
# @version 1
# @dg_internal
def _delete_file_rows(conn: sqlite3.Connection, file_rowid: int, report: SpliceReport) -> None:
    """Order matters: dependents before their parents, or a foreign key is briefly dangling.
    `xrefs` is cleared for BOTH endpoint directions because an edge is stale as soon as
    either end is re-read — the subset run re-emits it, and keeping the old row would
    duplicate it under a `UNIQUE ... ON CONFLICT IGNORE` that silently keeps the stale one.

    @brief Remove one file's rows from the working copy.
    @return None.
    @version 1
    """
    members = [
        int(r[0])
        for r in conn.execute("SELECT rowid FROM memberdef WHERE file_id = ?", (file_rowid,))
    ]
    compounds = [
        int(r[0])
        for r in conn.execute("SELECT rowid FROM compounddef WHERE file_id = ?", (file_rowid,))
    ]

    if members:
        marks = ",".join("?" * len(members))
        for column in ("src_rowid", "dst_rowid"):
            cur = conn.execute(
                f"DELETE FROM xrefs WHERE {column} IN ({marks})",  # noqa: S608 - marks are '?'
                members,
            )
            report.xrefs_deleted += cur.rowcount if cur.rowcount > 0 else 0
        for table, column in _MEMBER_DEPENDENTS:
            conn.execute(
                f"DELETE FROM {table} WHERE {column} IN ({marks})",  # noqa: S608
                members,
            )
        for column in ("memberdef_rowid", "reimplemented_rowid"):
            conn.execute(
                f"DELETE FROM reimplements WHERE {column} IN ({marks})",  # noqa: S608
                members,
            )
        conn.execute(f"DELETE FROM memberdef WHERE rowid IN ({marks})", members)  # noqa: S608
        report.members_deleted += len(members)

    if compounds:
        marks = ",".join("?" * len(compounds))
        for table, column in _COMPOUND_DEPENDENTS:
            conn.execute(
                f"DELETE FROM {table} WHERE {column} IN ({marks})",  # noqa: S608
                compounds,
            )
        conn.execute(f"DELETE FROM compounddef WHERE rowid IN ({marks})", compounds)  # noqa: S608
        report.compounds_deleted += len(compounds)

    conn.execute("DELETE FROM includes WHERE src_id = ?", (file_rowid,))


##
# @brief Column names of a table, in declaration order.
# @param conn Open connection.
# @param table Table to describe.
# @return Ordered column names.
# @version 1
# @dg_internal
def _columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """@brief List a table's columns.
    @return Column names in order.
    @version 1
    """
    return [str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")]


##
# @brief Copy one file's memberdef rows from the subset into the working copy.
# @param work Working copy connection (written).
# @param sub Subset database connection (read).
# @param rel Repo-relative path being replaced.
# @param ctx Path caches for both databases plus the repo root.
# @param report Accumulating counts.
# @return Mapping of subset memberdef rowid to working-copy memberdef rowid.
# @version 1
# @dg_internal
def _insert_members(
    work: sqlite3.Connection,
    sub: sqlite3.Connection,
    rel: str,
    ctx: dict,
    report: SpliceReport,
) -> dict[int, int]:
    """Rowid comes from the refid, never from the subset's own numbering: a subset database
    numbers its members from 1, so copying rowids across would collide with unrelated
    master entities. Resolving the refid TEXT instead lands each member on the rowid that
    identity already owns in the master.

    @brief Insert a file's memberdefs, keyed by refid.
    @return Subset-rowid to working-rowid map.
    @version 1
    """
    columns = [c for c in _columns(sub, "memberdef") if c != "rowid"]
    selected = ", ".join(f"md.{c}" for c in columns)
    sub_file = ctx["sub_paths"].get(rel)
    if sub_file is None:
        return {}
    rows = sub.execute(
        f"SELECT md.rowid, r.refid, {selected} "  # noqa: S608 - columns come from PRAGMA
        "FROM memberdef md JOIN refid r ON r.rowid = md.rowid WHERE md.file_id = ?",
        (sub_file,),
    ).fetchall()

    mapping: dict[int, int] = {}
    placeholders = ", ".join("?" * (len(columns) + 1))
    for row in rows:
        sub_rowid, refid = int(row[0]), str(row[1])
        values = dict(zip(columns, row[2:]))
        work_rowid = _refid_rowid(work, refid)
        values["file_id"] = _path_rowid(work, rel, ctx["work_paths"])
        values["bodyfile_id"] = _remap_optional_path(work, sub, values["bodyfile_id"], ctx)
        work.execute(
            f"INSERT OR REPLACE INTO memberdef(rowid, {', '.join(columns)}) "  # noqa: S608
            f"VALUES ({placeholders})",
            [work_rowid, *[values[c] for c in columns]],
        )
        mapping[sub_rowid] = work_rowid
        report.members_inserted += 1
    return mapping


##
# @brief Copy one file's compounddef rows from the subset into the working copy.
# @param work Working copy connection (written).
# @param sub Subset database connection (read).
# @param rel Repo-relative path being replaced.
# @param ctx Path caches for both databases plus the repo root.
# @param report Accumulating counts.
# @return None.
# @version 1
# @dg_internal
def _insert_compounds(
    work: sqlite3.Connection,
    sub: sqlite3.Connection,
    rel: str,
    ctx: dict,
    report: SpliceReport,
) -> None:
    """WITHOUT THIS THE SPLICE SILENTLY DROPS EVERY CLASS IN A CHANGED FILE. Doxygen emits a
    `compounddef` per class, struct, union and namespace, AND one of kind `file` for the file
    itself, so deleting a changed file's compounds without re-inserting them removes the very
    rows `contains` and `member` hang off. The first version of this module deleted them and
    inserted only memberdefs; the asymmetry was visible in the report as
    `compounds_deleted` rising while `compounds_inserted` stayed at zero, which is exactly
    the shape a per-table count exists to expose and an aggregate would have hidden.

    @brief Insert a file's compounddefs, keyed by refid.
    @return None.
    @version 1
    """
    columns = [c for c in _columns(sub, "compounddef") if c != "rowid"]
    selected = ", ".join(f"cd.{c}" for c in columns)
    sub_file = ctx["sub_paths"].get(rel)
    if sub_file is None:
        return
    rows = sub.execute(
        f"SELECT cd.rowid, r.refid, {selected} "  # noqa: S608 - columns come from PRAGMA
        "FROM compounddef cd JOIN refid r ON r.rowid = cd.rowid WHERE cd.file_id = ?",
        (sub_file,),
    ).fetchall()

    placeholders = ", ".join("?" * (len(columns) + 1))
    for row in rows:
        refid = str(row[1])
        values = dict(zip(columns, row[2:]))
        work_rowid = _refid_rowid(work, refid)
        values["file_id"] = _path_rowid(work, rel, ctx["work_paths"])
        if "header_id" in values:
            values["header_id"] = _remap_optional_path(work, sub, values["header_id"], ctx)
        work.execute(
            f"INSERT OR REPLACE INTO compounddef(rowid, {', '.join(columns)}) "  # noqa: S608
            f"VALUES ({placeholders})",
            [work_rowid, *[values[c] for c in columns]],
        )
        report.compounds_inserted += 1


##
# @brief The refids of everything a changed file defines, read from the subset database.
# @param sub Subset database connection.
# @param changed Repo-relative paths whose content changed.
# @param ctx Path caches for both databases plus the repo root.
# @return Refid strings for the changed files' memberdefs and compounddefs.
# @version 1
# @dg_internal
def _changed_refids(sub: sqlite3.Connection, changed: set[str], ctx: dict) -> set[str]:
    """THE FENCE FOR EVERY RE-INSERTION. A subset run resolves names against only the files
    it can see, so an edge or relation it emits between two CLOSURE files can disagree with
    what the whole tree says — measured on this repository as 8 edges a full rebuild does not
    emit, between functions the edit never touched. Restricting re-insertion to rows that
    touch a changed file's own definitions is exactly symmetric with deletion, and it is the
    rule the module already states for rows: replace the CHANGED set, leave the closure alone.

    Covers memberdefs AND compounddefs, because `member` and `contains` hang off compounds
    while `xrefs` hangs off members.

    @brief Collect the refids a changed file defines.
    @return Refid strings.
    @version 1
    """
    found: set[str] = set()
    for rel in changed:
        sub_file = ctx["sub_paths"].get(rel)
        if sub_file is None:
            continue
        for table in ("memberdef", "compounddef"):
            found.update(
                str(r[0])
                for r in sub.execute(
                    f"SELECT rf.refid FROM {table} t "  # noqa: S608 - literal table names
                    "JOIN refid rf ON rf.rowid = t.rowid WHERE t.file_id = ?",
                    (sub_file,),
                )
            )
    return found


##
# @brief Re-link class membership and containment for the respliced files.
# @param work Working copy connection (written).
# @param sub Subset database connection (read).
# @param report Accumulating counts.
# @return None.
# @version 2
# @dg_internal
def _insert_relations(
    work: sqlite3.Connection,
    sub: sqlite3.Connection,
    changed: set[str],
    ctx: dict,
    report: SpliceReport,
) -> None:
    """`member` and `contains` are the rows that make a class's methods findable AS members
    rather than as loose functions, and both were deleted alongside their compounds. Each is
    re-linked through refid TEXT on both ends and SKIPPED when either end is absent, for the
    same reason as `_insert_xrefs`: a row pointing at a missing compound is a dangling
    relation that reads as real at query time.

    @brief Re-insert member and contains rows.
    @return None.
    @version 2
    """
    changed_refids = _changed_refids(sub, changed, ctx)
    pairs = (
        ("member", "scope_rowid", "memberdef_rowid", "prot, virt"),
        ("contains", "inner_rowid", "outer_rowid", ""),
        ## BOTH WERE DELETE-ONLY UNTIL AN ADVERSARIAL REVIEW MEASURED IT. `_delete_file_rows`
        ## removes them per changed file and nothing put them back, so every override
        ## relationship and every base/derived link in a changed file was permanently stripped
        ## — silently, with a symmetric-looking SpliceReport. Measured on the docs-db
        ## self-index with master as its own subset: reimplements 19 -> 15, compoundref 29 ->
        ## 27. Readers that went empty: query/symbols.py and query/dossier.py (overrides and
        ## implementors), query/corpus.py (bases and derived).
        ("reimplements", "memberdef_rowid", "reimplemented_rowid", ""),
        ("compoundref", "base_rowid", "derived_rowid", "prot, virt"),
    )
    for table, left, right, extra in pairs:
        columns = f"{left}, {right}" + (f", {extra}" if extra else "")
        selected = "rl.refid, rr.refid" + (f", s.{extra.replace(', ', ', s.')}" if extra else "")
        rows = sub.execute(
            f"SELECT {selected} FROM {table} s "  # noqa: S608 - names are module literals
            f"JOIN refid rl ON rl.rowid = s.{left} "
            f"JOIN refid rr ON rr.rowid = s.{right}"
        ).fetchall()
        for row in rows:
            if str(row[0]) not in changed_refids and str(row[1]) not in changed_refids:
                continue
            lhs = work.execute("SELECT rowid FROM refid WHERE refid = ?", (str(row[0]),)).fetchone()
            rhs = work.execute("SELECT rowid FROM refid WHERE refid = ?", (str(row[1]),)).fetchone()
            if lhs is None or rhs is None:
                report.relations_dropped += 1
                continue
            marks = ", ".join("?" * (2 + len(row) - 2))
            work.execute(
                f"INSERT OR IGNORE INTO {table}({columns}) VALUES ({marks})",  # noqa: S608
                [int(lhs[0]), int(rhs[0]), *row[2:]],
            )
            report.relations_inserted += 1


##
# @brief Translate a subset path rowid into the working copy's equivalent.
# @param work Working copy connection.
# @param sub Subset database connection.
# @param value The subset path rowid, or None for a declaration with no definition.
# @param ctx Path caches plus the repo root.
# @return A working-copy path rowid, or None.
# @version 1
# @dg_internal
def _remap_optional_path(
    work: sqlite3.Connection,
    sub: sqlite3.Connection,
    value: int | None,
    ctx: dict,
) -> int | None:
    """A NULL `bodyfile_id` is meaningful — a declaration with no definition — so it is
    preserved rather than coerced to a rowid.

    @brief Remap a nullable path reference.
    @return Working-copy path rowid or None.
    @version 1
    """
    if value is None:
        return None
    row = sub.execute("SELECT name FROM path WHERE rowid = ?", (int(value),)).fetchone()
    if row is None:
        return None
    return _path_rowid(work, normalize_path(str(row[0]), ctx["repo_root"]), ctx["work_paths"])


##
# @brief Copy the xref edges the subset run produced for the respliced files.
# @param work Working copy connection (written).
# @param sub Subset database connection (read).
# @param report Accumulating counts.
# @return None.
# @version 1
# @dg_internal
def _insert_xrefs(
    work: sqlite3.Connection,
    sub: sqlite3.Connection,
    changed: set[str],
    ctx: dict,
    report: SpliceReport,
) -> None:
    """ENDPOINTS RESOLVE THROUGH `refid`, NOT THROUGH `memberdef`, and that is doxygen's own
    schema rather than a relaxation of mine: `xrefs.src_rowid`/`dst_rowid` REFERENCE `refid`,
    and NOT every refid owns a memberdef row.

    The first version of this function required both endpoints to be memberdefs, on the
    reasoning that a dangling edge reads as real at query time. The invariance test refuted
    it in one run: `main.c` refers to an ENUM VALUE in `event_bus.h` whose refid exists at a
    rowid with no memberdef — in the full rebuild too, not just the splice. So the guard was
    dropping an edge doxygen legitimately stores, and faithfully reproducing doxygen's output
    is the contract. The importer downstream joins memberdef and ignores these on its own.

    ONLY EDGES TOUCHING A CHANGED FILE ARE RE-INSERTED, and the first version got this
    wrong in a way only a real-repo comparison caught. It inserted EVERY edge the subset
    emitted, which sounds harmless — the closure files were re-read, so surely their edges
    are fine. They are not: doxygen resolves a name against the files it can SEE, and in a
    four-file subset an ambiguous name resolves differently than it does among 284. Measured
    on this repository, a modification-only refresh then carried 8 edges a full rebuild does
    not emit, between functions in files the edit never touched (`cull` -> `db_status`,
    `import_kconfig` -> `discover_kconfig`). Nothing was missing; the graph had grown edges
    that do not exist.

    The rule that fixes it is the one the module already states for rows — replace the
    CHANGED set, leave the closure alone — applied to edges. It is also exactly symmetric
    with deletion: `_delete_file_rows` removes the xrefs touching a changed file's members,
    so those are precisely the ones to put back. Everything else the master already had
    right.

    Duplicates remain harmless: `xrefs` is UNIQUE on the triple with ON CONFLICT IGNORE.

    @brief Insert the subset's xref edges that touch a changed file.
    @return None.
    @version 3
    """
    changed_refids = _changed_refids(sub, changed, ctx)
    rows = sub.execute(
        """
        SELECT rs.refid, rd.refid, x.context
        FROM xrefs x
        JOIN refid rs ON rs.rowid = x.src_rowid
        JOIN refid rd ON rd.rowid = x.dst_rowid
        """
    ).fetchall()
    for raw_src, raw_dst, context in rows:
        if str(raw_src) not in changed_refids and str(raw_dst) not in changed_refids:
            report.xrefs_unresolved += 1
            continue
        src = _refid_rowid(work, str(raw_src))
        dst = _refid_rowid(work, str(raw_dst))
        work.execute(
            "INSERT INTO xrefs(src_rowid, dst_rowid, context) VALUES (?, ?, ?)",
            (src, dst, context),
        )
        report.xrefs_inserted += 1


## @brief Restore a changed file's parameter rows and their memberdef links.
# @param work Working copy connection (written).
# @param sub Subset database connection (read).
# @param changed Repo-relative paths whose content changed.
# @param ctx Path caches for both databases plus the repo root.
# @param report Accumulating counts.
# @return None.
# @version 1
# @dg_internal
def _insert_params(
    work: sqlite3.Connection,
    sub: sqlite3.Connection,
    changed: set[str],
    ctx: dict,
    report: SpliceReport,
) -> None:
    """`param` CARRIES NO REFID, which is why this cannot ride on `_insert_relations`. Rows are
    matched on their full value tuple and inserted only when absent, because doxygen already
    shares one `param` row across many memberdefs (1072 param rows against 4239 links on this
    repo) and copying blindly would grow the table on every splice.

    Delete-only until an adversarial review measured it: memberdef_param 4322 -> 4162 on the
    docs-db self-index with master as its own subset. The visible consequence is in
    `query/macros.py`, which distinguishes a function-like macro from an object-like one by
    whether it has parameter rows — so a spliced function-like macro reads as object-like.

    @brief Re-link a changed file's parameters.
    @return None.
    @version 1
    """
    columns = [c for c in _columns(sub, "param") if c != "rowid"]
    joined = ", ".join(columns)
    marks = ", ".join("?" * len(columns))
    where = " AND ".join(f"COALESCE({c},'') = COALESCE(?,'')" for c in columns)
    for rel in sorted(changed):
        sub_file = ctx["sub_paths"].get(rel)
        if sub_file is None:
            continue
        rows = sub.execute(
            f"SELECT rf.refid, {', '.join('p.' + c for c in columns)} "  # noqa: S608
            "FROM memberdef_param mp "
            "JOIN memberdef m ON m.rowid = mp.memberdef_id "
            "JOIN refid rf ON rf.rowid = m.rowid "
            "JOIN param p ON p.rowid = mp.param_id "
            "WHERE m.file_id = ?",
            (sub_file,),
        ).fetchall()
        for row in rows:
            member = work.execute(
                "SELECT m.rowid FROM memberdef m JOIN refid r ON r.rowid = m.rowid "
                "WHERE r.refid = ?",
                (str(row[0]),),
            ).fetchone()
            if member is None:
                report.relations_dropped += 1
                continue
            values = list(row[1:])
            existing = work.execute(
                f"SELECT rowid FROM param WHERE {where} LIMIT 1",
                values,  # noqa: S608
            ).fetchone()
            if existing is None:
                cur = work.execute(
                    f"INSERT INTO param({joined}) VALUES ({marks})",
                    values,  # noqa: S608
                )
                param_rowid = cur.lastrowid
            else:
                param_rowid = int(existing[0])
            work.execute(
                "INSERT INTO memberdef_param(memberdef_id, param_id) VALUES (?, ?)",
                (int(member[0]), param_rowid),
            )
            report.relations_inserted += 1


## @brief Restore the `#include` edges a changed file declares.
# @param work Working copy connection (written).
# @param sub Subset database connection (read).
# @param changed Repo-relative paths whose content changed.
# @param ctx Path caches for both databases plus the repo root.
# @param report Accumulating counts.
# @return None.
# @version 1
# @dg_internal
def _insert_includes(
    work: sqlite3.Connection,
    sub: sqlite3.Connection,
    changed: set[str],
    ctx: dict,
    report: SpliceReport,
) -> None:
    """KEYED ON PATHS, NOT REFIDS — `includes` links two `path` rows, so it needs its own
    handler. Delete-only until measured: includes 1017 -> 958 on the mbedtls index.

    No clew query reads `includes` TODAY, so restoring it fixes nothing currently visible. It
    is restored anyway because a table the splice silently empties is a trap for whoever adds
    the first reader — they would find it empty on incrementally-refreshed indexes only, which
    is the hardest possible shape to debug.

    @brief Re-insert a changed file's include edges.
    @return None.
    @version 1
    """
    for rel in sorted(changed):
        sub_file = ctx["sub_paths"].get(rel)
        if sub_file is None:
            continue
        for local, dst_name in sub.execute(
            "SELECT i.local, d.name FROM includes i JOIN path d ON d.rowid = i.dst_id "
            "WHERE i.src_id = ?",
            (sub_file,),
        ):
            src = _path_rowid(work, rel, ctx["work_paths"])
            dst = _path_rowid(
                work, normalize_path(str(dst_name), ctx["repo_root"]), ctx["work_paths"]
            )
            work.execute(
                "INSERT INTO includes(local, src_id, dst_id) VALUES (?, ?, ?)",
                (local, src, dst),
            )
            report.relations_inserted += 1


##
# @brief Rebuild the master doxygen database by re-reading only the changed files.
# @param master_db The previous whole-tree doxygen database.
# @param subset_db A doxygen database from the closure-expanded subset, or None for a
#                  deletions-only splice where there is nothing to re-read.
# @param changed Repo-relative paths whose content changed.
# @param out The path to write the spliced database to.
# @param repo_root Absolute repository root.
# @return A report of what moved.
# @version 2
# @req REQ-DDB-INDEX-002
def splice_doxygen(
    master_db: Path,
    subset_db: Path | None,
    changed: set[str],
    out: Path,
    repo_root: Path,
    removed: set[str] | None = None,
) -> SpliceReport:
    """THE COPY HAPPENS FIRST, and that ordering is load-bearing. Every key in
    `doxygen_cache` names the SAME output path and each build OVERWRITES it, so a subset run
    clobbers the very database being spliced from. `master_db` must therefore be copied to
    `out` BEFORE the subset run — the caller's ordering, enforced here by refusing to run
    when the copy source is missing.

    Only the CHANGED files' rows are replaced. Closure files were re-read so their edges
    resolve; their own rows in the master are still correct and are left alone.

    `removed` is DELETE-ONLY and exists so an ordinary deletion does not force a full
    rebuild. A deleted file appears in no subset run — there is nothing to re-read — so
    without this it would land in `skipped` and its rows would persist as a phantom symbol
    the index still answers about. Branch switches make that common, not exotic.

    @brief Splice a subset doxygen run into the master database.
    @return The splice report.
    @version 3
    """
    report = SpliceReport()
    if not master_db.exists():
        report.skipped.append("master database missing")
        return report
    if subset_db is not None and not subset_db.exists():
        report.skipped.append("subset database missing")
        return report

    if out.resolve() != master_db.resolve():
        shutil.copy2(master_db, out)

    work = sqlite3.connect(out)
    ## DELETIONS-ONLY takes no subset run. Feeding the master back in as its own subset
    ## would re-insert the very rows the removal loop just deleted, so there is no
    ## connection to open and the insert phase is skipped outright.
    sub = sqlite3.connect(subset_db) if subset_db is not None else None
    try:
        work.execute("PRAGMA foreign_keys = OFF")
        ctx = {
            "repo_root": repo_root,
            "work_paths": _file_rowids(work, repo_root),
            "sub_paths": _file_rowids(sub, repo_root) if sub is not None else {},
        }
        for rel in sorted(removed or ()):
            gone = ctx["work_paths"].get(rel)
            if gone is not None:
                _delete_file_rows(work, gone, report)
                report.files_removed += 1
        for rel in sorted(changed):
            if rel not in ctx["sub_paths"]:
                ## The subset run did not produce this file. Refusing to delete its master
                ## rows is the fail-closed choice: dropping them would silently shrink the
                ## graph, where keeping them merely leaves them one build stale.
                report.skipped.append(rel)
                continue
            existing = ctx["work_paths"].get(rel)
            if existing is not None:
                _delete_file_rows(work, existing, report)
            _insert_compounds(work, sub, rel, ctx, report)
            _insert_members(work, sub, rel, ctx, report)
            report.files_replaced += 1
        if sub is not None:
            _insert_relations(work, sub, changed, ctx, report)
            _insert_params(work, sub, changed, ctx, report)
            _insert_includes(work, sub, changed, ctx, report)
            _insert_xrefs(work, sub, changed, ctx, report)
        work.commit()
    finally:
        if sub is not None:
            sub.close()
        work.close()

    if report.skipped:
        logger.warning(
            "doxygen splice: %d file(s) absent from the subset run and left stale: %s",
            len(report.skipped),
            ", ".join(report.skipped[:5]),
        )
    logger.info("doxygen splice: %s", report.describe())
    return report
