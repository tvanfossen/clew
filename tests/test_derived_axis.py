# SPDX-License-Identifier: MIT
"""A fast in-place refresh leaves whole-index layers behind, and every reply must say so.

1.3.5, Track 2 (two-tier refresh), phase 2: disclosure BEFORE mechanism. The fast tier updates
only the edited files' own layers in place; reachability, thread membership, context conflicts,
shared-key edges and the rest still describe the tree before the edit until the following full
refresh lands. The `data` axis cannot carry this: it compares source mtimes with the database's,
and an in-place write moves the database's mtime past the edit, so the axis CLEARS while those
layers are still old. That is exactly the silent staleness this repository's first rule forbids,
so the new `derived` axis exists before any code can produce the state it describes.

The state is recorded in `build_meta` as a `fast.*` section; a full build writes a fresh database
and so drops it.

@brief Tests for the `derived` staleness axis.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.mcp_server import freshness
from clew.mcp_server.tools_query import _withdraw_definitive

## A fast-tier record as the fast tier will write it.
_FAST = {"pending": "1", "files": "src/a.c", "layers": "reachability,threads,context_conflicts"}


def test_a_pending_fast_refresh_raises_the_derived_axis() -> None:
    """@brief notices() names the derived axis, the files and the stale layers.
    @return None.
    @version 1
    """
    found = freshness.notices({"fast": _FAST}, code={})
    derived = [n for n in found if n["axis"] == freshness.AXIS_DERIVED]
    assert len(derived) == 1
    message = derived[0]["message"]
    assert "src/a.c" in message and "reachability" in message and "threads" in message


def test_no_fast_record_means_no_derived_axis() -> None:
    """A WARNING THAT ALWAYS FIRES IS ONE NOBODY READS: a current index gets nothing.

    @brief No fast section, or a cleared one, adds no notice.
    @return None.
    @version 1
    """
    assert not [n for n in freshness.notices({}, code={}) if n["axis"] == "derived"]
    cleared = {"fast": {**_FAST, "pending": "0"}}
    assert not [n for n in freshness.notices(cleared, code={}) if n["axis"] == "derived"]


def test_a_definitive_negative_is_withdrawn_while_layers_are_derived_stale() -> None:
    """ "No callers" from a call graph that has not seen the edit is not a measurement of the
    edited code. The derived axis withdraws the definitive wording like `schema` does.

    @brief The derived axis replaces a definitive-negative note.
    @return None.
    @version 1
    """
    payload = {
        "note": "No callers. This is a definitive empty result from the database. Do not retry.",
    }
    staleness = freshness.notices({"fast": _FAST}, code={})
    _withdraw_definitive(payload, staleness)
    assert "NOT DEFINITIVE" in payload["note"]
    assert "definitive empty result" not in payload["note"]


def test_db_status_reports_the_fast_section_and_counts_it_as_stale(tmp_path: Path) -> None:
    """`stale` MUST INCLUDE IT: the server's follow-up full build is skipped when an index reads
    as fresh, and an in-place write makes it read fresh on every other axis.

    @brief db_status carries `fast` and sets `stale`.
    @return None.
    @version 1
    """
    from clew.mcp_server.state import Target, db_status
    from clew.signature import write_build_signature

    db = tmp_path / "clew.db"
    sqlite3.connect(db).close()
    write_build_signature(db)
    with sqlite3.connect(db) as conn:
        conn.executemany(
            "INSERT INTO build_meta (key, value) VALUES (?, ?)",
            [(f"fast.{k}", v) for k, v in _FAST.items()],
        )
    status = db_status(Target(repo_path=str(tmp_path), slug="t", db_path=str(db)))
    assert status["fast"]["pending"] == "1"
    assert status["stale"] is True
    assert any(n["axis"] == "derived" for n in status.get("staleness", []))
