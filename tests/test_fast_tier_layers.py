# SPDX-License-Identifier: MIT
"""Every table of a built index is either kept current by the fast tier, named stale, or unaffected.

PR0 OF THE 2.0.0 PLAN (owner 2026-11-17, "is LSP-like refresh achievable?"). The fast tier updates
an edited file's own layers in place and NAMES the whole-index layers it leaves behind
(`STALE_LAYERS`, served as the `derived` staleness axis). Nothing checked that the two lists
covered the index: a layer added without a classification would go silently stale after a save,
reading as current. This test builds a real index and requires every table to be classified in
`fasttier.TABLE_CLASSES`, and every stale class to be a layer the notice names.

@brief The fast tier's layer accounting covers every table.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from clew.fasttier import FAST, STALE_LAYERS, TABLE_CLASSES, UNAFFECTED

## FTS5 keeps its rows in shadow tables named after the virtual table; they follow it.
_SHADOW = ("_data", "_idx", "_docsize", "_config", "_content")


def _tables(tmp_path: Path) -> set[str]:
    """@brief Build a small C + Python index and list its tables. @return Table names."""
    from clew.cli import _build_argparser, _run_pipeline

    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "a.c").write_text(
        '#include "a.h"\n/** @brief f. @req REQ-A-001 */\nint f(int x) {\n#if defined(X)\n'
        "  return g(x);\n#else\n  return 0;\n#endif\n}\n"
    )
    (repo / "src" / "a.h").write_text("int f(int x);\nint g(int x);\n")
    (repo / "tool.py").write_text('"""Tool."""\n\n\ndef main():\n    """Run."""\n    return 1\n')
    out = tmp_path / "clew.db"
    _run_pipeline(_build_argparser().parse_args(["--output", str(out), "--repo-root", str(repo)]))
    conn = sqlite3.connect(str(out))
    names = {
        r[0]
        for r in conn.execute("SELECT name FROM sqlite_master WHERE type IN ('table')")
        if not r[0].startswith("sqlite_")
    }
    conn.close()
    virtual = {n for n in names if any(f"{n}{s}" in names for s in _SHADOW)}
    return {n for n in names if not any(n == f"{v}{s}" for v in virtual for s in _SHADOW)}


def test_every_table_is_classified(tmp_path: Path) -> None:
    """@brief No table is unaccounted for after a fast refresh."""
    missing = sorted(_tables(tmp_path) - set(TABLE_CLASSES))
    assert missing == [], f"classify these in fasttier.TABLE_CLASSES: {missing}"


def test_every_stale_class_is_a_named_layer() -> None:
    """A table classed stale is disclosed under a layer name the `derived` notice carries.

    @brief Stale classes are notice layers.
    """
    stale = {c for c in TABLE_CLASSES.values() if c not in (FAST, UNAFFECTED)}
    assert stale <= set(STALE_LAYERS), sorted(stale - set(STALE_LAYERS))
