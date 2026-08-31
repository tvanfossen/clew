# SPDX-License-Identifier: MIT
"""The index must record how big the job was, not only how much of it produced rows.

`coverage.indexed_files` counts FIRST-PARTY files that produced doxygen rows. It reads like the
size of the corpus and is not: doxygen records what it parsed, and the tree the build was asked
to index can be orders of magnitude larger. Measured on a vendored C++ target, 526 against
84,502 — and the small number is the one everybody reasoned from, two agents and the operator
included, during an investigation into why that build took half an hour.

So `scope.files_in_scope` is stamped beside the roots and excludes that selected them. It is the
denominator every other coverage number was implicitly quoted against and which nothing recorded.

WHY THE ASSERTION IS AN INEQUALITY. Pinning a literal count would break whenever the fixture
gains a file, teaching whoever hits it to update the number rather than ask why it moved. The
PROPERTY is that the scope is wider than the rows it produced, which is what makes the two
numbers different facts rather than one restated.

@brief Integration test for the stamped in-scope file count.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew.cli import _build_argparser, _run_pipeline

pytestmark = pytest.mark.integration


## @brief Read one build_meta value as an int, or None when absent.
## @param db The built index.
## @param key The build_meta key.
## @return The integer value, or None.
## @version 1
def _meta_int(db: Path, key: str) -> int | None:
    """@brief Read an integer build_meta value.
    @return The value, or None when the key is absent.
    @version 1
    """
    conn = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        row = conn.execute("SELECT value FROM build_meta WHERE key = ?", (key,)).fetchone()
    finally:
        conn.close()
    return int(row[0]) if row and str(row[0]).lstrip("-").isdigit() else None


## @brief A build records the file count its scope selected.
## @version 1
def test_a_build_records_how_many_files_were_in_scope(guard_repo: Path, tmp_path: Path) -> None:
    """FAILS BEFORE THE FIX with the key absent entirely.

    The inequality against `coverage.indexed_files` is the load-bearing half: it is what
    distinguishes a real enumeration from a value copied off the row count, which would satisfy
    "the key exists" while restating the number the key was added to contrast with.

    @brief `scope.files_in_scope` is stamped and exceeds the rows produced.
    @version 1
    """
    out = tmp_path / "counted.db"
    args = _build_argparser().parse_args(["--repo-root", str(guard_repo), "--output", str(out)])
    _run_pipeline(args)

    in_scope = _meta_int(out, "scope.files_in_scope")
    indexed = _meta_int(out, "coverage.indexed_files")

    assert in_scope is not None, (
        "scope.files_in_scope is not stamped, so the index still cannot say how large the tree "
        "it was asked to cover actually was"
    )
    ## Anti-vacuity: a build that indexed nothing would make any inequality below trivially true.
    assert indexed, "the fixture produced no first-party rows; this comparison is vacuous"
    assert in_scope > indexed, (
        f"scope.files_in_scope ({in_scope}) is not larger than coverage.indexed_files "
        f"({indexed}). The two are different facts — files OFFERED to the build versus "
        "first-party files that produced rows — and a value that merely restates the second "
        "leaves the gap this key exists to expose invisible."
    )
