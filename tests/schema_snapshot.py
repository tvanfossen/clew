# SPDX-License-Identifier: MIT
"""Schema/content snapshot helper for the vocabulary work.

Two jobs, both needed to prove that centralizing the enumerated CHECK clauses
changed the schema TEXT and nothing else:

  `checks  <db> [out.json]`   — parse every `CHECK(<col> IN (...))` out of
                                `sqlite_master.sql` and emit the
                                `table.column -> sorted values` map. Backs the
                                committed golden snapshot at
                                `tests/data/schema_vocabulary.json`.

  `content <db> [out.json]`   — per user table, the row count plus a sha256 over
                                its rows in a stable order. Two databases with
                                identical output carry identical DATA even when
                                their DDL is formatted differently.

Deliberately standalone (stdlib only, no clew import) so it can run
against a database built by a DIFFERENT checkout of the pipeline — which is
exactly what the before/after comparison needs.

@brief Emit a database's CHECK-constraint map or its per-table content digest.
@version 1
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

## `CHECK(col IN ('a','b'))` / `CHECK(col IN (0,1))`, tolerating the newlines and
## run-on whitespace the hand-wrapped DDL used before generation.
_CHECK_RE = re.compile(r"CHECK\s*\(\s*(\w+)\s+IN\s*\(([^)]*)\)\s*\)", re.IGNORECASE)
## One quoted value inside a CHECK list, with SQL's doubled-apostrophe escape.
_VALUE_RE = re.compile(r"'((?:[^']|'')*)'")

## Tables whose content legitimately differs between two builds of the same
## source tree (build stamp / wall-clock), so a content digest over them proves
## nothing. Everything else must match exactly. `meta` is DOXYGEN's own table
## and its third column is the run's wall-clock time to the second — measured:
## two builds six seconds apart differ there and nowhere else.
VOLATILE_TABLES = frozenset({"build_meta", "meta"})


## @brief Parse every enumerated CHECK constraint out of a database's DDL.
## @param db Path to the SQLite database to read.
## @return Mapping of "table.column" to its sorted allowed-value list.
## @version 1
def parse_checks(db: Path) -> dict[str, list[str]]:
    """Reads `sqlite_master.sql`, not `PRAGMA table_info`, because SQLite does
    not expose CHECK constraints structurally anywhere else.

    @brief Map every CHECK-constrained column to its allowed values.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL",
    ).fetchall()
    conn.close()
    out: dict[str, list[str]] = {}
    for table, sql in rows:
        for column, body in _CHECK_RE.findall(sql):
            out[f"{table}.{column}"] = _check_values(body)
    return out


## @brief Split one CHECK list body into its member values.
## @param body The raw text between the CHECK list's parentheses.
## @return Sorted member values; bare integers (0/1) come back as strings.
## @version 1
def _check_values(body: str) -> list[str]:
    """@brief Extract and unescape the values inside a CHECK IN list.

    @version 1
    """
    quoted = [m.replace("''", "'") for m in _VALUE_RE.findall(body)]
    if quoted:
        return sorted(quoted)
    return sorted(tok.strip() for tok in body.split(",") if tok.strip())


## @brief Per-table row count and a stable content digest.
## @param db Path to the SQLite database to read.
## @return Mapping of table name to {"rows": int, "sha256": str}.
## @version 1
def content_digest(db: Path) -> dict[str, dict]:
    """Rows are sorted by their repr rather than by a key, so the digest is
    insensitive to insertion order while still being sensitive to every value.

    @brief Digest every non-volatile table's contents.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    tables = [
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name",
        ).fetchall()
    ]
    out: dict[str, dict] = {}
    for table in tables:
        if table in VOLATILE_TABLES:
            continue
        rows = sorted(repr(r) for r in conn.execute(f'SELECT * FROM "{table}"').fetchall())
        digest = hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest()
        out[table] = {"rows": len(rows), "sha256": digest}
    conn.close()
    return out


## @brief Print a database's per-table row counts as a readable table.
## @param db Path to the SQLite database to read.
## @return None.
## @version 1
def print_counts(db: Path) -> None:
    """@brief Report each non-volatile table's row count, plus the total.

    @version 1
    """
    data = content_digest(db)
    total = 0
    for table, info in sorted(data.items()):
        print(f"{table:34s} {info['rows']:6d}")
        total += info["rows"]
    print(f"{'TOTAL':34s} {total:6d}")


## @brief CLI entry point: dispatch `checks` / `content` / `counts`.
## @return Process exit status (0 on success, 2 on bad usage).
## @version 2
def main() -> int:
    """@brief Run one subcommand against one database.

    @version 2
    """
    if len(sys.argv) < 3 or sys.argv[1] not in ("checks", "content", "counts"):
        print(
            "usage: schema_snapshot.py {checks|content|counts} <db> [out.json]",
            file=sys.stderr,
        )
        return 2
    command, db = sys.argv[1], Path(sys.argv[2])
    if command == "counts":
        print_counts(db)
        return 0
    data = parse_checks(db) if command == "checks" else content_digest(db)
    text = json.dumps(data, indent=2, sort_keys=True) + "\n"
    if len(sys.argv) > 3:
        Path(sys.argv[3]).write_text(text, encoding="utf-8")
    else:
        print(text, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
