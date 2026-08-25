# SPDX-License-Identifier: MIT
"""An incrementally refreshed index must equal a full rebuild — THROUGH THE REAL PIPELINE.

WHY THIS FILE EXISTS, AND IT IS THE MOST-EARNED TEST IN THIS SUITE. Three separate defects
shipped in the incremental splice, each found by a real target or an adversarial review and
never by the suite, and all three had the SAME shape: the unit was covered and the
ORCHESTRATION THAT CALLS IT was covered nowhere. Confirmed by mutation, one at a time, each
leaving the whole suite green:

  - delete the `include_expansion(...)` call in `_incremental_doxygen` — green;
  - delete the `in_doxygen_scope(...)` call in `_incremental_plan`   — green;
  - delete the `await before(...)` in the MCP query wrapper          — green.

`tests/integration/test_doxygen_splice.py` cannot catch any of them, because it assembles the
closure, the scope filter and the splice ITSELF rather than driving the build. It tests the
pieces correctly and then wires them the way the author believed the pipeline does. This test
drives `clew.cli.build_index`, so the wiring IS the thing under test.

THE ASSERTION IS AN INVARIANCE, NOT A COUNT: refresh incrementally, rebuild the same tree from
scratch, demand the two databases agree. Counts cannot distinguish a correct splice from a
lossy one that looks plausible, which is precisely how the four delete-only tables and the lost
cross-file edge both survived a green suite.

THE EDIT EXERCISES EVERY MECHANISM THE PIPELINE STITCHES TOGETHER, because an edit that touches
only one leaves the rest asserted-but-unexercised:

  - a NEW cross-file call to a previously-uncalled function, plus its `#include`, which only
    the second pass can resolve (the pre-edit xref table cannot name that callee);
  - an edit to a file the Doxyfile EXCLUDES by glob, which only the scope filter keeps out;
  - a C++ class gaining a derived type, which exercises the inheritance tables the splice was
    silently stripping;
  - a plain body change, the ordinary case.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew._common import captured_output
from clew.cli import build_index

pytestmark = pytest.mark.integration

FIXTURE = Path(__file__).resolve().parent.parent / "data" / "csample"


##
# @brief Lay down a C/C++ tree with an excluded subdirectory and an inheritance pair.
# @param root Destination repository root.
# @return None.
# @version 1
def _seed(root: Path) -> None:
    """@brief Copy the fixture and add the shapes and vendor trees.
    @return None.
    @version 1
    """
    shutil.copytree(FIXTURE, root)
    (root / "src" / "shapes.cpp").write_text(
        "struct Base { virtual int area() const; virtual ~Base() {} };\n"
        "struct Derived : Base { int area() const override; };\n"
        "int Base::area() const { return 0; }\n"
        "int Derived::area() const { return 1; }\n",
        encoding="utf-8",
    )
    (root / "vendor").mkdir(parents=True, exist_ok=True)
    (root / "vendor" / "third_party.c").write_text(
        "int vendored_helper(void) { return 7; }\n", encoding="utf-8"
    )
    (root / "Doxyfile").write_text(
        "PROJECT_NAME = pipeline\nINPUT = .\nEXCLUDE_PATTERNS = */vendor/*\n",
        encoding="utf-8",
    )


##
# @brief Apply one edit per mechanism the incremental path stitches together.
# @param root Repository root to edit.
# @return None.
# @version 1
def _edit(root: Path) -> None:
    """@brief Touch a new cross-file call, an excluded file, an inheritance tree and a body.
    @return None.
    @version 1
    """
    main = root / "src" / "main.c"
    main.write_text(
        main.read_text(encoding="utf-8").replace(
            '#include "telemetry/telemetry.h"',
            '#include "telemetry/telemetry.h"\n#include "sound/sound_service.h"',
            1,
        )
        + "\n\nvoid pipeline_probe(void)\n{\n    sound_play_findme(1);\n}\n",
        encoding="utf-8",
    )
    shapes = root / "src" / "shapes.cpp"
    shapes.write_text(
        shapes.read_text(encoding="utf-8")
        + "struct Extra : Base { int area() const override; };\n"
        + "int Extra::area() const { return 2; }\n",
        encoding="utf-8",
    )
    vendored = root / "vendor" / "third_party.c"
    vendored.write_text(
        vendored.read_text(encoding="utf-8") + "int vendored_added(void) { return 8; }\n",
        encoding="utf-8",
    )


##
# @brief Reduce a built index to the content two builds of one tree must share.
# @param db The clew database to read.
# @return Comparable sets keyed on names and paths.
# @version 1
def _snapshot(db: Path) -> dict[str, set]:
    """Keyed on NAMES and repo-relative paths, never rowids: two independent builds number
    their rows independently, so a rowid comparison would pass vacuously or fail meaninglessly.

    @brief Snapshot a built index.
    @return Dict of comparable sets.
    @version 1
    """
    conn = sqlite3.connect(db)
    try:
        return {
            "members": {
                (str(f), str(n), str(k))
                for f, n, k in conn.execute(
                    "SELECT p.name, md.name, md.kind FROM memberdef md "
                    "JOIN path p ON p.rowid = md.file_id"
                )
            },
            "edges": {
                (str(a), str(b), str(s))
                for a, b, s in conn.execute(
                    "SELECT cr.name, ce.name, e.source FROM call_edges e "
                    "JOIN memberdef cr ON cr.rowid = e.caller_rowid "
                    "JOIN memberdef ce ON ce.rowid = e.callee_rowid"
                )
            },
            "indexed": {str(n) for (n,) in conn.execute("SELECT name FROM path WHERE type = 1")},
            ## QUALIFIED, because `reimplements` links the METHODS and both ends are named
            ## `area` — the class that distinguishes them lives in `memberdef.scope`. Keying on
            ## the bare name made the non-vacuity gate look for "Extra" among a set of
            ## ("area", "area") pairs and conclude the rebuild had no override at all.
            "reimplements": {
                (f"{a or ''}::{b}", f"{c or ''}::{d}")
                for a, b, c, d in conn.execute(
                    "SELECT ma.scope, ma.name, mb.scope, mb.name FROM reimplements x "
                    "JOIN memberdef ma ON ma.rowid = x.memberdef_rowid "
                    "JOIN memberdef mb ON mb.rowid = x.reimplemented_rowid"
                )
            },
        }
    finally:
        conn.close()


##
# @brief A pipeline-driven incremental refresh must equal a pipeline-driven full rebuild.
# @param tmp_path Pytest scratch directory.
# @return None.
# @version 1
def test_an_incremental_refresh_equals_a_full_rebuild(tmp_path: Path) -> None:
    """THE WIRING IS THE SUBJECT. Every call goes through `build_index`, so removing any step
    from `_incremental_plan` or `_incremental_doxygen` changes this test's answer.

    The incremental build reuses ONE output path across two invocations, which is what makes
    the second one incremental: the sidecar beside that path holds the previous doxygen output
    and the scan state. The full rebuild goes to a FRESH path, so it has no sidecar and cannot
    take the splice branch at all.

    @brief Incremental and full builds of one tree agree.
    @return None.
    @version 1
    """
    root = tmp_path / "repo"
    _seed(root)
    incremental = tmp_path / "incremental.db"

    with captured_output():
        build_index(output=incremental, repo_root=root, doxyfile=root / "Doxyfile")
    _edit(root)
    with captured_output():
        build_index(output=incremental, repo_root=root, doxyfile=root / "Doxyfile")

    ## THE NON-VACUITY GATE FOR THIS WHOLE FILE. If the second build fell back to a full run
    ## — no previous output, a config_sha mismatch, an exception swallowed by the fallback —
    ## then every comparison below passes while testing NOTHING about the splice. The sidecar's
    ## generation counter is the structural witness: `record_splice(reset=...)` zeroes it after
    ## a full build and increments it after a splice, so a positive value can only mean the
    ## incremental branch ran.
    sidecar = sqlite3.connect(str(incremental) + ".idxcache")
    try:
        row = sidecar.execute(
            "SELECT value FROM cache_meta WHERE key = 'splice_generation'"
        ).fetchone()
    finally:
        sidecar.close()
    assert row is not None and int(row[0]) > 0, (
        f"the second build did NOT take the incremental branch (splice_generation={row}), so "
        f"this test compares two full rebuilds and proves nothing about the splice"
    )

    full = tmp_path / "full.db"
    with captured_output():
        build_index(output=full, repo_root=root, doxyfile=root / "Doxyfile")

    got, want = _snapshot(incremental), _snapshot(full)

    ## NON-VACUITY, per mechanism. Each of these is a thing the pipeline had to do correctly to
    ## get here; if the rebuild lacks it, the comparison below cannot see that mechanism at all.
    assert ("pipeline_probe", "sound_play_findme", "doxygen_sqlite") in want["edges"] or any(
        a == "pipeline_probe" and b == "sound_play_findme" for a, b, _ in want["edges"]
    ), "the rebuild has no pipeline_probe -> sound_play_findme edge; the second pass is untested"
    assert not any("vendor" in f for f in want["indexed"]), (
        "the rebuild indexed the excluded vendor/ tree, so EXCLUDE_PATTERNS is not in force "
        "and the scope filter is untested here"
    )
    assert any("Extra" in a or "Extra" in b for a, b in want["reimplements"]), (
        "the rebuild has no Extra override, so the inheritance tables are untested here"
    )

    for layer in ("members", "edges", "indexed", "reimplements"):
        missing = want[layer] - got[layer]
        extra = got[layer] - want[layer]
        assert not missing and not extra, (
            f"{layer}: the incrementally refreshed index disagrees with a full rebuild.\n"
            f"  missing from incremental ({len(missing)}): {sorted(missing)[:8]}\n"
            f"  only in incremental ({len(extra)}): {sorted(extra)[:8]}"
        )
