# SPDX-License-Identifier: MIT
"""A miss names the file types it did not read, so an empty answer is not read as absence.

1.1.0, sumac's item 4 — the half of its request that matters most. The index now reads
shell and CMake, and registers YAML and JSON, but THAT DEPENDS ON THE INSTALLED SUBSTRATE:
with a substrate that lacks the grammars they are absent, the files carry no symbols, and a query
about a deploy script comes back empty. `clew/mcp_server/emptiness.py` already grades an
empty answer and states the covered shape — the extensions it DOES hold. The complement
was missing, and it is the actionable half: *14 `.sh` files were in scope and none of them
are in this index.*

Without it the three cases below are indistinguishable from the caller's side:

| why the answer is empty | what the caller should do |
|---|---|
| the symbol does not exist | stop; trust the negative |
| the file type is not indexed by this build | read the file directly |
| the file type is outside the declared scope | widen the scope, or read the file |

MEASURED AT BUILD TIME, NOT ASKED AT QUERY TIME. The comparison needs the tree the build
walked, and a query-time walk of the repository would be both slow and wrong — the working
copy at query time is not the tree that was indexed. So the build stamps it and the query
reads the row, which also means an index built before this release reports nothing rather
than a fabricated empty set.

@brief The not-indexed report: stamped at build time, served on an empty answer.
@version 1
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from clew.cli import _not_indexed_scope
from clew.query.corpus import index_scope


## @brief A database holding a `path` table with the given indexed files.
## @version 1
def _db_with_paths(tmp_path: Path, indexed: list[str]) -> Path:
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INT, name TEXT)")
        conn.executemany("INSERT INTO path (type, name) VALUES (1, ?)", [(f,) for f in indexed])
        conn.commit()
    finally:
        conn.close()
    return db


## @brief Args carrying a scanned file set, as the doxygen stage leaves them.
## @version 1
def _args(scanned: list[str] | None) -> argparse.Namespace:
    args = argparse.Namespace()
    if scanned is not None:
        args.scanned_files = scanned
    return args


def test_the_file_types_in_scope_with_no_rows_are_counted(tmp_path: Path) -> None:
    """@brief Unindexed extensions are named with their counts. @version 1"""
    db = _db_with_paths(tmp_path, ["src/main.c", "src/util.c"])
    scanned = [
        "src/main.c",
        "src/util.c",
        "scripts/deploy.sh",
        "scripts/release.sh",
        "scripts/lib.sh",
        ".github/workflows/ci.yml",
    ]

    meta = _not_indexed_scope(db, _args(scanned))

    assert meta["not_indexed_count"] == "4"
    assert meta["not_indexed"] == ".sh=3, .yml=1"


def test_an_index_that_holds_everything_in_scope_stamps_nothing(tmp_path: Path) -> None:
    """THE FALSY-DROP RULE, which this repo applies everywhere: "nothing was missed" and
    "nobody measured" must not read the same, so the ordinary case writes no row at all
    and the PRESENCE of the key is the signal.

    @brief Full coverage stamps no row. @version 1
    """
    db = _db_with_paths(tmp_path, ["src/main.c"])

    assert _not_indexed_scope(db, _args(["src/main.c"])) == {}


def test_a_build_that_never_walked_the_tree_stamps_nothing(tmp_path: Path) -> None:
    """A rustdoc-only build has no scanned set. Reporting "everything is indexed" from a
    comparison that could not be made is the fabrication this whole surface exists to
    avoid.

    @brief No scanned set means no claim. @version 1
    """
    db = _db_with_paths(tmp_path, ["src/lib.rs"])

    assert _not_indexed_scope(db, _args(None)) == {}


def test_a_file_with_no_extension_is_named_as_such(tmp_path: Path) -> None:
    """An extensionless `deploy` with a `#!/bin/sh` line is exactly the file a reader asks
    about, so it must not vanish into a blank key.

    @brief Extensionless files are reported, not dropped. @version 1
    """
    db = _db_with_paths(tmp_path, ["src/main.c"])

    meta = _not_indexed_scope(db, _args(["src/main.c", "scripts/deploy", "Makefile"]))

    assert "(no extension)=2" in meta["not_indexed"]


def test_the_named_list_is_capped_and_the_count_is_not(tmp_path: Path) -> None:
    """The count is exact and the list is a sample — the same contract `scope.depth_limited`
    and `coverage.skipped_binary` already publish, and for the same reason: an empty reply
    is budgeted and a long tail of one-off extensions is not worth its bytes.

    @brief The list caps; the count stays exact. @version 1
    """
    db = _db_with_paths(tmp_path, ["src/main.c"])
    scanned = ["src/main.c"] + [f"f{i}.ext{i}" for i in range(20)]

    meta = _not_indexed_scope(db, _args(scanned))

    assert meta["not_indexed_count"] == "20"
    assert len(meta["not_indexed"].split(", ")) <= 12


def test_the_query_layer_serves_what_the_build_stamped(tmp_path: Path) -> None:
    """@brief `IndexScope.not_indexed` carries the stamped row. @version 1"""
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INT, name TEXT)")
        conn.execute("INSERT INTO path (type, name) VALUES (1, 'src/main.c')")
        conn.execute("CREATE TABLE build_meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany(
            "INSERT INTO build_meta (key, value) VALUES (?, ?)",
            [("scope.not_indexed", ".sh=3, .yml=1"), ("scope.not_indexed_count", "4")],
        )
        conn.commit()
    finally:
        conn.close()

    scope = index_scope(db)

    assert scope.not_indexed == (".sh=3", ".yml=1")
    assert scope.not_indexed_count == 4


def test_an_index_built_before_this_release_claims_nothing(tmp_path: Path) -> None:
    """The row is absent, which must read as "not recorded" and never as "nothing was
    missed" — the same rule `IndexScope.source` follows for an index built before the
    provenance was stamped.

    @brief No row means an empty report and a zero count. @version 1
    """
    db = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db))
    try:
        conn.execute("CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INT, name TEXT)")
        conn.execute("INSERT INTO path (type, name) VALUES (1, 'src/main.c')")
        conn.commit()
    finally:
        conn.close()

    scope = index_scope(db)

    assert scope.not_indexed == ()
    assert scope.not_indexed_count == 0


def test_an_unrecorded_report_is_absent_from_the_served_payload() -> None:
    """THE FALSY-DROP RULE ON THE SERVED SURFACE. An index built before this release has no
    row, and serving `not_indexed: []` beside it states that nothing was missed — which is
    the claim the build never made. `emptiness.py` puts it plainly: "the limit was not
    reached" and "nobody looked" must not read the same.

    So the keys are dropped entirely when the count is zero, and the caller distinguishes
    the two cases by presence, as it does for every other optional measurement here.

    @brief No stamped report means no key in the reply. @version 1
    """
    from clew.mcp_server.emptiness import _scope_payload
    from clew.query.models import IndexScope

    stamped = IndexScope("declared", "why", 12, ("src",), (".c",), (".sh=3", ".yml=1"), 4)
    unrecorded = IndexScope("declared", "why", 12, ("src",), (".c",))

    assert _scope_payload(stamped)["not_indexed"] == [".sh=3", ".yml=1"]
    assert _scope_payload(stamped)["not_indexed_count"] == 4
    assert "not_indexed" not in _scope_payload(unrecorded)
    assert "not_indexed_count" not in _scope_payload(unrecorded)
