# SPDX-License-Identifier: MIT
"""Same-key sites: the other symbols carrying a property key a function writes (F1-mm; 2.0.0).

FOUND BY THE 2.0.0 UNDERPERFORMANCE REVIEW (mattermost F1, Q1 m2). `buildRequestOptions` writes
`retryPolicyConfiguration = {retryLimit: 0}`; its default, `retryLimit: 3`, is in the
`DEFAULT_CONFIG` literal of another class. Every winning cell followed the key with grep, and every
losing index cell had no route from one to the other.

RARITY-GATED. A key held by more than `KEY_RARITY` other non-test symbols names a shape, not a
link (`headers`, `body`), and listing every holder would bury the rare key that is the answer, so
it is left out. FIVE, the review's own proposal: it keeps `retryPolicyConfiguration` (1 other
non-test holder on mattermost-mobile) and drops `headers`. Test files never count and are never
listed: a test helper building the same literal says nothing about the default build.

@brief Same-key sites for a function dossier.
@version 1
"""

from __future__ import annotations

import sqlite3

from ._common import table_exists
from .models import KeySite

## The most other non-test holders a key may have and still be listed. See the module docstring.
KEY_RARITY = 5


## @brief Other non-test symbols carrying the keys one function writes.
## @param conn Open connection.
## @param file The function's file (its body's).
## @param start First body line.
## @param end Last body line.
## @return Sites, by key then file then line; empty when the layer is absent or nothing qualifies.
## @version 1
## @req REQ-DDB-QUERY-004
def same_key_sites(
    conn: sqlite3.Connection, file: str, start: int | None, end: int | None
) -> list[KeySite]:
    """THE FUNCTION'S KEYS ARE ITS BODY'S, by span rather than by holder name, so a key written in
    a nested arrow function still belongs to the function a reader asked about.

    @brief Find same-key sites.
    @return Sites.
    """
    if not table_exists(conn, "property_keys") or not start or not end:
        return []
    tests = (
        "AND k.path_rowid NOT IN (SELECT path_rowid FROM test_scope)"
        if table_exists(conn, "test_scope")
        else ""
    )
    own = conn.execute(
        "SELECT DISTINCT k.key FROM property_keys k JOIN path p ON p.rowid = k.path_rowid "
        "WHERE p.name = ? AND k.line BETWEEN ? AND ?",
        (file, start, end),
    ).fetchall()
    sites: list[KeySite] = []
    for (key,) in own:
        rows = conn.execute(
            "SELECT k.holder, p.name, MIN(k.line) FROM property_keys k JOIN path p ON p.rowid = k.path_rowid "  # noqa: S608
            f"WHERE k.key = ? AND NOT (p.name = ? AND k.line BETWEEN ? AND ?) {tests} "
            "GROUP BY k.holder, p.name ORDER BY p.name, 3",
            (key, file, start, end),
        ).fetchall()
        if len(rows) <= KEY_RARITY:
            sites += [KeySite(key=key, holder=h, file=f, line=int(ln)) for h, f, ln in rows]
    return sorted(sites, key=lambda s: (s.key, s.file, s.line))
