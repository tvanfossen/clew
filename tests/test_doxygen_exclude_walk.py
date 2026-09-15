# SPDX-License-Identifier: MIT
"""An excluded directory is pruned from doxygen's walk, not read and then discarded.

MEASURED against doxygen 1.18.0 while closing gh#48's refresh-cost follow-up. Doxygen EXPANDS
every directory named in `EXCLUDE` into the set of files beneath it, so excluding a vendored
tree costs a full read of that tree. An `EXCLUDE_PATTERNS` wildcard is matched while doxygen
recurses, so a matching directory is never entered. On a 60k-file fixture:

    EXCLUDE = <dir>                       1.73 s
    EXCLUDE_PATTERNS = */deps/slam/*      0.03 s
    both                                  1.30 s   (the EXCLUDE entry alone costs the read)

On real repositories, a full build's doxygen pass with the same file set in both runs (compared
file for file):

    entropic first-party   10.83 s -> 4.48 s   614 files, identical sets
    clew                    5.48 s -> 2.41 s   309 files, identical sets
    greenwood-clock         4.65 s -> 2.74 s   170 files, identical sets

@brief Tests that directory excludes reach doxygen as pruning patterns.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest

from clew.doxygen import _build_doxyfile_content, synthesize_doxyfile


## @brief A tree with a kept source, an excluded directory holding a nested subtree, and a file.
## @param root Directory to populate.
## @return (root, excluded directory, excluded file).
## @version 1
def _tree(root: Path) -> tuple[Path, Path, Path]:
    """@brief Build the exclusion fixture. @return The paths. @version 1"""
    (root / "src").mkdir(parents=True)
    (root / "src" / "kept.c").write_text("/** @brief kept. */\nint kept_fn(void) { return 0; }\n")
    vendored = root / "deps" / "vendored"
    (vendored / "inner").mkdir(parents=True)
    (vendored / "v.c").write_text("int vendored_fn(void) { return 0; }\n")
    (vendored / "inner" / "i.c").write_text("int inner_fn(void) { return 0; }\n")
    scratch = root / "src" / "scratch.c"
    scratch.write_text("int scratch_fn(void) { return 0; }\n")
    return root.resolve(), vendored.resolve(), scratch.resolve()


def test_an_absolute_directory_exclude_becomes_an_anchored_pattern(tmp_path: Path) -> None:
    """THE SHAPE. A directory goes to `EXCLUDE_PATTERNS` as `<absolute dir>/*` — anchored at
    its own absolute path, so it cannot match a same-named directory elsewhere the way
    `*/vendored/*` would — and is NOT also left in `EXCLUDE`, because that entry alone is what
    costs the read. A file, a relative path, and a path whose name contains wildcard characters
    stay in `EXCLUDE`: a pattern matches doxygen's absolute path, and a `[` in a directory name
    would be read as a character class.

    @brief Directory excludes are rewritten; files, relative and glob-shaped paths are not.
    @version 1
    """
    root, vendored, scratch = _tree(tmp_path / "repo")
    globby = root / "deps" / "odd[1]"
    globby.mkdir()
    doxyfile = synthesize_doxyfile(root, tmp_path / "synth")

    content = _build_doxyfile_content(
        doxyfile,
        [str(root)],
        [str(vendored), str(scratch), "relative/dir", str(globby)],
        replace_input=True,
    )

    assert f"EXCLUDE_PATTERNS += {vendored}/*" in content
    assert f"EXCLUDE += {vendored}\n" not in content, "the EXCLUDE entry alone costs the read"
    assert f"EXCLUDE += {scratch}" in content
    assert "EXCLUDE += relative/dir" in content
    assert f"EXCLUDE += {globby}" in content
    assert content.index("\nEXCLUDE_PATTERNS =\n") < content.index(
        f"EXCLUDE_PATTERNS += {vendored}/*"
    ), "the pattern must follow the clear, or the clear erases it"


@pytest.mark.skipif(shutil.which("doxygen") is None, reason="asserted against real doxygen")
def test_the_pattern_excludes_exactly_what_the_directory_exclude_did(tmp_path: Path) -> None:
    """THE EQUIVALENCE, AGAINST DOXYGEN ITSELF. The rewrite is only a speedup if doxygen indexes
    the same files. So the kept file is indexed, and nothing under the excluded directory is,
    nested subdirectory included. The excluded single file is also absent.

    @brief Doxygen indexes the same files with the rewritten excludes.
    @version 1
    """
    root, vendored, scratch = _tree(tmp_path / "repo")
    doxyfile = synthesize_doxyfile(root, tmp_path / "synth")
    out = tmp_path / "out"
    content = _build_doxyfile_content(
        doxyfile, [str(root)], [str(vendored), str(scratch)], replace_input=True, output_dir=out
    )

    subprocess.run(
        ["doxygen", "-"], input=content, text=True, capture_output=True, cwd=root, check=True
    )

    db = next(out.rglob("doxygen_sqlite3.db"))
    names = {r[0] for r in sqlite3.connect(db).execute("SELECT name FROM path WHERE type=1")}
    assert any(n.endswith("src/kept.c") for n in names), names
    assert not any("deps/vendored" in n for n in names), names
    assert not any(n.endswith("scratch.c") for n in names), names
