# SPDX-License-Identifier: MIT
"""Every C/C++ `#include`, read from the parse and resolved to an indexed file (T3; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mbedtls F6), and re-checked before this was written:
doxygen's own `includes` table held 2 includers of `library/constant_time_internal.h` where the
tree has 17 (`grep -l '#include "constant_time_internal.h"' library/*.c`, mbedtls at the pinned
acceptance commit), so a "what reaches this header" question had no index route.

ITS OWN TABLE. `includes` is doxygen's (copied from its sqlite3 output) and has no provenance
column, so rows written into it would claim doxygen saw them. `ast_includes` keeps the spec as
written, its line and whether it was quoted, and `dst_id` is NULL when no indexed file matches —
"seen, not resolved", which a missing row could not say.

RESOLUTION, NEVER A GUESS. A quoted spec is tried beside the including file first (the C rule for
`"..."`); then any spec resolves to the ONE indexed path equal to it or ending in `/<spec>`. Two
candidates resolve to none: picking one would assert an edge the build may not have.

@brief The AST include layer.
@version 2
"""

from __future__ import annotations

import posixpath
import sqlite3
from pathlib import Path
from typing import Any

from ._common import logger
from .harvest import Harvester, run_harvest
from .indexcache import IndexCache
from .vocabulary import STAGE_INCLUDES

## The directive's node, and the two path forms the grammar gives it.
_INCLUDE_NODE = "preproc_include"
_QUOTED = "string_literal"
_SYSTEM = "system_lib_string"


## @brief Per-file `#include` harvester.
## @version 1
class _IncludesHarvester(Harvester):
    """Every indexed file, like every stage: a non-C file's parse holds no directive and yields an
    empty payload. A `#include MACRO` names no file at parse time and is skipped.

    @brief Include-directive harvester.
    @version 1
    """

    stage = STAGE_INCLUDES
    stage_version = 1
    label = "includes"

    ## @brief Harvest one file's include directives.
    ## @param tree The parsed tree.
    ## @param src_bytes The file's raw bytes (unused; the tree carries the text).
    ## @return [[spec, quoted (1|0), line], ...] — lists, so a cache hit equals a fresh parse.
    ## @version 1
    ## @req REQ-DDB-INDEX-010
    def harvest(self, tree: Any, src_bytes: bytes) -> Any:
        """@brief Walk one file's `#include`s. @return Entries."""
        found: list[list[Any]] = []
        stack = [tree.root_node]
        while stack:
            node = stack.pop()
            stack.extend(node.children)
            if node.type != _INCLUDE_NODE:
                continue
            path = node.child_by_field_name("path")
            if path is None or path.type not in (_QUOTED, _SYSTEM):
                continue
            spec = path.text.decode("utf-8", "replace")[1:-1].strip()
            if spec:
                found.append([spec, 1 if path.type == _QUOTED else 0, node.start_point[0] + 1])
        return found


## @brief The include stage's harvester.
## @return A Harvester whose cache key this stage will look for.
## @version 1
## @req REQ-DDB-INDEX-010
def includes_harvester() -> Harvester:
    """ONE CONSTRUCTION SITE, shared with the plan's parse pass. @brief Build it. @return It."""
    return _IncludesHarvester()


## @brief Create the ast_includes table.
## @param conn Open connection.
## @return None.
## @version 1
## @req REQ-DDB-INDEX-010
def ensure_ast_includes_table(conn: sqlite3.Connection) -> None:
    """Created unconditionally, so a tree with no `#include` yields an EMPTY table, not an absent
    one. @brief Create the table. @return None."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS ast_includes (
          src_id INTEGER NOT NULL REFERENCES path(rowid),
          dst_id INTEGER REFERENCES path(rowid),
          spec TEXT NOT NULL,
          local INTEGER NOT NULL,
          line INTEGER NOT NULL,
          UNIQUE(src_id, line)
        );
        CREATE INDEX IF NOT EXISTS idx_ast_includes_dst ON ast_includes(dst_id);
        """
    )


## @brief Resolve include specs against the indexed file set.
## @version 1
class IncludeResolver:
    """@brief Spec → indexed path rowid, or None.
    @version 1
    """

    ## @brief Index the path table by name and by every suffix.
    ## @param names {rowid: repo-relative path}.
    ## @version 1
    ## @dg_internal
    def __init__(self, names: dict[int, str]) -> None:
        self.by_name = {name: rowid for rowid, name in names.items()}
        self.by_suffix: dict[str, list[int]] = {}
        for rowid, name in names.items():
            parts = name.split("/")
            for i in range(len(parts)):
                self.by_suffix.setdefault("/".join(parts[i:]), []).append(rowid)

    ## @brief Resolve one spec from one including file.
    ## @param spec The spec as written (`mbedtls/aes.h`).
    ## @param quoted Whether it was `"..."` (tried beside the includer first).
    ## @param includer The including file's path.
    ## @return The rowid, or None (absent or ambiguous).
    ## @version 1
    ## @req REQ-DDB-INDEX-010
    def resolve(self, spec: str, quoted: bool, includer: str) -> int | None:
        """@brief Resolve a spec. @return Rowid or None."""
        if quoted:
            beside = posixpath.normpath(posixpath.join(posixpath.dirname(includer), spec))
            if beside in self.by_name:
                return self.by_name[beside]
        candidates = self.by_suffix.get(posixpath.normpath(spec), [])
        return candidates[0] if len(candidates) == 1 else None


## @brief The rows one file's payload becomes.
## @param resolver The resolver over the indexed path set.
## @param src The including file's path rowid.
## @param includer The including file's path.
## @param payload The harvest payload, or None.
## @return (src_id, dst_id, spec, local, line) rows.
## @version 1
## @dg_internal
def _rows(resolver: IncludeResolver, src: int, includer: str, payload: Any) -> list[tuple]:
    """ONE CONVERSION for the full stage and the fast tier, so a fast-refreshed row is the row a
    full build writes for the same bytes.

    @brief Payload to rows.
    @return Rows.
    """
    return [
        (src, resolver.resolve(spec, bool(quoted), includer), spec, quoted, line)
        for spec, quoted, line in payload or ()
    ]


## @brief The resolver over this index's indexed files.
## @param conn Open connection.
## @return (resolver, {rowid: path}).
## @version 1
## @dg_internal
def _resolver(conn: sqlite3.Connection) -> tuple[IncludeResolver, dict[int, str]]:
    """ONLY FILES THAT EXIST resolve a spec. Doxygen writes a `path` row, `found = 0`, for every
    include it could not find, so `<stdio.h>` has a row named `stdio.h`; resolving against those
    rows turned "not in this tree" into an edge to a phantom file, and made a full build (which
    has the phantom rows) disagree with a fast refresh (found by tests/test_file_includes.py).
    `names` keeps every row, because an includer is named whatever its row says.

    @brief Build the resolver. @return Resolver and names.
    """
    columns = {row[1] for row in conn.execute("PRAGMA table_info(path)")}
    found = "AND COALESCE(found, 1) = 1" if "found" in columns else ""
    names = {r: str(n) for r, n in conn.execute("SELECT rowid, name FROM path WHERE type = 1")}
    real = {
        r: str(n) for r, n in conn.execute(f"SELECT rowid, name FROM path WHERE type = 1 {found}")
    }  # noqa: S608
    return IncludeResolver(real), names


_INSERT = (
    "INSERT OR IGNORE INTO ast_includes (src_id, dst_id, spec, local, line) VALUES (?, ?, ?, ?, ?)"
)


## @brief Rewrite the edited files' `#include` rows (the fast tier).
## @param conn Open connection, inside the fast tier's transaction.
## @param repo_root The working tree.
## @param cache The index cache.
## @param files {repo-relative path: path rowid} of the edited files.
## @return Rows written.
## @version 1
## @req REQ-DDB-INDEX-010
def refresh_ast_includes(
    conn: sqlite3.Connection, repo_root: Path, cache: IndexCache, files: dict[str, int]
) -> int:
    """EXACT, NOT APPROXIMATE (T3 served, 2.0.0). The fast tier runs only when the file set is
    unchanged, so every spec resolves against the same paths a full build would see; only the
    edited files' own directives can differ, and those are re-read here. NOT
    `ensure_ast_includes_table`: its `executescript` would COMMIT mid-transaction, and an index
    without the table never ran the layer.

    @brief Refresh edited files' includes.
    @return Rows written.
    """
    from .harvest import HarvestTally, _harvest_one_file

    if conn.execute("SELECT 1 FROM sqlite_master WHERE name = 'ast_includes'").fetchone() is None:
        return 0
    resolver, _names = _resolver(conn)
    written = 0
    for rel, rowid in files.items():
        conn.execute("DELETE FROM ast_includes WHERE src_id = ?", (rowid,))
        payload = _harvest_one_file(
            rel, repo_root / rel, includes_harvester(), {}, cache, HarvestTally()
        )
        written += conn.executemany(_INSERT, _rows(resolver, rowid, rel, payload)).rowcount
    return written


## @brief Record every indexed file's `#include` directives.
## @param db_path The index.
## @param repo_root The repository.
## @param cache The run's index cache, or None.
## @return Directives recorded.
## v2: rows built by `_rows`, shared with the fast tier (2.0.0, T3 served)
## @version 2
## @req REQ-DDB-INDEX-010
def import_ast_includes(db_path: Path, repo_root: Path, cache: IndexCache | None = None) -> int:
    """@brief Fill ast_includes. @return Row count."""
    conn = sqlite3.connect(str(db_path))
    try:
        ensure_ast_includes_table(conn)
        conn.execute("DELETE FROM ast_includes")
        resolver, names = _resolver(conn)
        rows = [
            row
            for src, payload in run_harvest(conn, repo_root, includes_harvester(), cache)
            for row in _rows(resolver, src, names.get(src, ""), payload)
        ]
        conn.executemany(_INSERT, rows)
        conn.commit()
    finally:
        conn.close()
    resolved = sum(1 for r in rows if r[1] is not None)
    logger.info("includes: %d directive(s), %d resolved to an indexed file", len(rows), resolved)
    return len(rows)
