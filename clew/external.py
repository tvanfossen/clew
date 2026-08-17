# SPDX-License-Identifier: MIT
"""Per-file EXTERNAL provenance — which indexed files belong to someone else's repo.

gh#333 stopped cutting nested git trees out of the index, because a `chain_trace`
that stops at a submodule boundary answers "this call leaves the repo" when it
could answer what the call does. gh#335 is the other half of that trade: once two
codebases share one index, every aggregate over it becomes a claim about BOTH, and
a coverage ratio that silently averages a repo with its vendored dependency is not
noisy, it is false.

THE RULE, and it is a fact rather than a convention:

    a directory with its own git tree (a `.gitmodules` entry, or a directory
    containing `.git`)  ->  EXTERNAL
    anything else this repo tracks                            ->  FIRST PARTY

NO NAME MATCHING. `vendor/` and `third_party/` are naming conventions, and a
detector built on them would be exactly the hardcoded repo shape the project
mandate forbids. It is also WRONG on the common case: a copied-in third-party
header with no git tree of its own IS first party — this repo committed it, owns
it, builds it, and has to maintain it, so its metrics should say so.

WHERE THE ANSWER COMES FROM: `scope.nested_repo_roots`, which is the same bounded
walk that used to produce these paths only to EXCLUDE them. The pipeline already
computed this on every build and threw it away into a warning — the identical shape
as the scope provenance gh#319 persisted, and as the macro hop doxygen was already
emitting. Nothing new is detected here; what was discarded is now stored.

WHAT IS TAGGED IS THE FILE, NOT THE SYMBOL. `path` is the one table every other
row reaches through — `memberdef.file_id`, `memberdef.bodyfile_id`, and by
extension every edge, lock, thread and requirement attributed to a symbol — so one
column on `path` tags the whole graph without a second source of truth to drift.

NO QUERY FILTERS ON THIS COLUMN. `chain_trace`, `callers`, `callees` and `dossier`
cross the boundary FREELY and always did; hiding external rows from them would
defeat the entire point of admitting the submodule. The tag changes what the
AGGREGATES say (coverage, orphan and file counts report FIRST PARTY by default),
never what a traversal can reach. An empty answer that is actually a filtered
answer is the precise failure the emptiness notes exist to prevent.

@brief Tag indexed files that belong to a nested foreign git tree.
@version 1
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from .vocabulary import EXTERNAL_ROOT_COLUMN, UNRESOLVED_PATH_COLUMN

logger = logging.getLogger(__name__)

## `path.type` for a file row; directory rows carry a different value and are
## never tagged, because nothing joins to them.
PATH_TYPE_FILE = 1

## build_meta key listing the external roots this build found, comma-joined and
## repo-relative. Stored because the COLUMN answers "is this file external" while
## a reader also needs "which foreign trees are in here at all" — and computing
## that from the column means a DISTINCT over every path row.
EXTERNAL_ROOTS_META_KEY = "external_roots"


## @brief Whether a table already carries a column.
## @param conn Open connection to the index.
## @param table Table to inspect.
## @param column Column name to look for.
## @return True when the column is present.
## @version 1
## @dg_internal
def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    """@brief Report whether one column exists on one table.

    @return True when present.
    @version 1
    """
    return any(row[1] == column for row in conn.execute(f"PRAGMA table_info({table})"))


## @brief Add the provenance columns to `path`, idempotently.
## @param conn Open connection to the index.
## @version 2
## @req REQ-DDB-INDEX-005
def ensure_external_provenance(conn: sqlite3.Connection) -> None:
    """`path` is DOXYGEN'S table — its sqlite3 backend creates it and we copy the
    file — so the column is namespaced (`dg_`) for the same reason `dg_source` is on
    `memberdef`: an unprefixed `external` would collide the day doxygen grows one,
    and the failure mode of that collision is not a loud `duplicate column name` but
    an idempotent ADD COLUMN finding a column already there and our reader then
    interpreting doxygen's semantics as ours.

    NULL, not `0`, is the untagged value, and the distinction is load-bearing on a
    partial build: `NULL` means "this row was never considered", while a stamped
    empty string would assert first-party membership the walk never checked. The
    reader treats NULL as first party for reporting and says so, rather than
    pretending the two are the same fact.

    TWO COLUMNS, because "owned by a named foreign tree" and "not a file of this
    repository at all" are different facts. Doxygen registers a `path` row for every
    unresolvable `#include`, spelled as a bare filename; those are neither first
    party nor attributable, and folding them into the external column would put a
    fabricated root into every `DISTINCT dg_external_root` listing.

    @brief Ensure `path` carries the external-root and unresolved columns.
    @version 2
    """
    if not _has_column(conn, "path", EXTERNAL_ROOT_COLUMN):
        conn.execute(f"ALTER TABLE path ADD COLUMN {EXTERNAL_ROOT_COLUMN} TEXT")
    if not _has_column(conn, "path", UNRESOLVED_PATH_COLUMN):
        conn.execute(f"ALTER TABLE path ADD COLUMN {UNRESOLVED_PATH_COLUMN} INTEGER")


## @brief The repo-relative spelling of a nested root, for storage.
## @param root Resolved repository root.
## @param nested Absolute path of a nested git tree beneath it.
## @return POSIX repo-relative path, or '' when the nested tree is not beneath the root.
## @version 1
## @dg_internal
def _relative_root(root: Path, nested: Path) -> str:
    """REPO-RELATIVE, ALWAYS. Anything stored here is published over MCP, and
    stamping an absolute path is the machine-layout disclosure that forced the
    build-version-9 bump — where `path.name` held the builder's home directory in
    112 of 112 rows.

    Returns '' rather than raising for a path outside the root, which the caller
    drops: an external root we cannot express relative to the repo cannot be matched
    against a repo-relative `path.name` either, so tagging from it would silently
    match nothing while looking like it worked.

    @brief Express a nested root relative to the repo.
    @return Repo-relative POSIX path, or ''.
    @version 1
    """
    try:
        return Path(nested).resolve().relative_to(root).as_posix()
    except ValueError:
        return ""


## @brief The external roots for a repo, repo-relative and outermost-first.
## @param repo_root Repository root to walk.
## @return Repo-relative POSIX paths of the trees the repo declares as dependencies.
## @version 2
## @req REQ-DDB-INDEX-005
def external_roots(repo_root: Path) -> list[str]:
    """A THIN WRAPPER OVER `scope.dependency_roots` ON PURPOSE. The detection is
    the scope module's, and duplicating its walk here would produce a second answer
    to "which trees are foreign" that could disagree with the one the build actually
    indexed under.

    IT WRAPS `dependency_roots`, NOT `nested_repo_roots`, since gh#352 half 2. The wider
    walk answers "is there a separate git tree here?", which the scope tier needs so it can
    honour each tree's own `.gitignore`; this one answers "did the repository DECLARE this as
    somebody else's code?", which is a claim about the committed tree rather than about whoever
    happened to build it. Measured on entropic, the difference was three tagged roots against
    the one `.gitmodules` declares.

    Imported inside the function because `scope` pulls in the declaration loader and
    this module is reached from the query layer as well as the pipeline.

    @brief List the trees a repo declares as dependencies, repo-relative.
    @return Repo-relative paths.
    @version 2
    """
    from .scope import dependency_roots

    root = Path(repo_root).expanduser().resolve()
    return [rel for rel in (_relative_root(root, n) for n in dependency_roots(root)) if rel]


## @brief Whether a repo-relative path lies inside one of the external roots.
## @param name Repo-relative indexed path.
## @param roots Repo-relative external roots.
## @return The matching root, or '' when the path is first party.
## @version 1
## @dg_internal
def _owning_root(name: str, roots: list[str]) -> str:
    """PREFIX MATCHING ON A PATH SEPARATOR, never a bare `startswith`. `vendor/llama`
    and `vendor/llama-utils` share a prefix, and matching without the `/` would tag
    the second repo's files as belonging to the first — a wrong attribution that
    reads as a confident measurement rather than as absent knowledge.

    @brief Find which external root owns a path.
    @return The owning root, or ''.
    @version 1
    """
    for root in roots:
        if name == root or name.startswith(f"{root}/"):
            return root
    return ""


## @brief Tag every indexed file that belongs to a nested foreign git tree.
## @param db_path Built index to stamp.
## @param repo_root Working tree the indexed paths are relative to.
## @return (number of file rows tagged external, the external roots that own at least one).
## @version 3
## @req REQ-DDB-INDEX-005
def stamp_external_provenance(db_path: Path, repo_root: Path) -> tuple[int, list[str]]:
    """FAILS SOFT, like every other measurement stamped onto an already-successful
    build. A walk that raises must not destroy the index it is describing; the column
    then stays NULL everywhere, which the reader reports as "not recorded" rather
    than as "all first party".

    Returns the CONTRIBUTING roots as well as the count, because the caller stamps
    them into `build_meta` and re-deriving them there would walk the tree a second
    time. Contributing, not detected: a nested tree that some other rule already
    excluded owns no indexed row, and naming it would both mislead and publish a
    directory name this index deliberately does not cover.

    THE UNRESOLVED PASS IS WHAT MAKES THE FIRST-PARTY FIGURES INVARIANT, and it was
    added because the invariance was measured FAILING. On entropic, admitting the
    llama.cpp submodule added 324 bare-filename rows from its Ascend and Hexagon
    backends — unresolvable `#include` targets, all counted as first party because a
    bare filename matches no external root — and `indexed_files` moved 488 → 804 on a
    change that must move no first-party figure. The ratios held throughout, purely
    because those files do not exist on disk and the line count already dropped them
    from the substantive set. An invariant preserved by an accident one layer down is
    not preserved.

    @brief Stamp per-file external and unresolved provenance into the index.
    @return Rows tagged external, and the roots that own at least one of them.
    @version 3
    """
    root = Path(repo_root).expanduser().resolve()
    roots = external_roots(root)
    ## RUNS EVEN WITH NO NESTED TREE. The unresolved half is unconditional — a repo
    ## that vendors nothing still has unresolvable `#include` targets — and an early
    ## return on `not roots` would leave the columns absent, which the readers
    ## correctly report as "not recorded" and would therefore make every such repo
    ## look like an index that predates gh#335.
    try:
        conn = sqlite3.connect(str(db_path))
    except sqlite3.Error as exc:
        logger.warning("external provenance not recorded (%s)", exc)
        return 0, roots
    try:
        ensure_external_provenance(conn)
        rows = conn.execute(
            "SELECT rowid, name FROM path WHERE type=?", (PATH_TYPE_FILE,)
        ).fetchall()
        owned = [(_owning_root(name, roots), rid) for rid, name in rows if name]
        updates = [pair for pair in owned if pair[0]]
        conn.executemany(f"UPDATE path SET {EXTERNAL_ROOT_COLUMN}=? WHERE rowid=?", updates)
        missing = [(rid,) for rid, name in rows if name and not (root / name).is_file()]
        conn.executemany(f"UPDATE path SET {UNRESOLVED_PATH_COLUMN}=1 WHERE rowid=?", missing)
        conn.commit()
        tagged = len(updates)
    except sqlite3.Error as exc:
        logger.warning("external provenance not recorded (%s)", exc)
        return 0, []
    finally:
        conn.close()
    ## ONLY THE ROOTS THAT ACTUALLY OWN A ROW ARE REPORTED, and the empty ones are
    ## counted rather than named. Two independent reasons, and either alone is enough:
    ##
    ## - A root that contributed nothing is a fact about the FILESYSTEM, not about
    ##   this index, and publishing it as an `external_roots` entry invites the exact
    ##   misreading that cost a measurement here — "0 files belong to 1 nested tree"
    ##   reads like a broken detector and is usually a tree some other rule excluded.
    ## - ANYTHING STAMPED HERE IS PUBLISHED OVER MCP. A nested tree that is excluded
    ##   from the index is precisely the one whose NAME we have no business emitting;
    ##   this walk sees every directory on disk, including ones no rule wants indexed.
    contributing = sorted({owner for owner, _ in updates})
    logger.info(
        "external provenance: %d indexed file(s) belong to %d nested git tree(s) (%s); "
        "%d further nested tree(s) contributed no indexed file and are not listed; "
        "%d row(s) resolve to no file in this repository (unresolved #include targets, "
        "which doxygen records by bare filename). The nested trees are INDEXED and "
        "queryable — chain_trace and callers/callees cross the boundary — but coverage, "
        "orphan and file counts report FIRST PARTY by default.",
        tagged,
        len(contributing),
        ", ".join(contributing) or "none",
        len(roots) - len(contributing),
        len(missing),
    )
    return tagged, contributing
