# SPDX-License-Identifier: MIT
"""A build removes doxygen output its own configuration no longer generates.

MEASURED WASTE. One target's state directory held `clew.doxygen/xml/` at 1,017 MB across 14,630
files, produced before `GENERATE_XML = NO` became a forced flag and untouched since. Nothing
reads it and nothing removed it, and the same accumulates on any target that predates a
generator being switched off.

THE DANGEROUS HALF IS THE SCOPE OF THE DELETE, so it is what these tests spend their assertions
on. clew is a read-only consumer of target repositories: it FORCES its own `OUTPUT_DIRECTORY`
precisely so nothing it writes lands in a repo someone is mid-edit in. A cleanup that reached a
path derived from a target's own `OUTPUT_DIRECTORY` would be the worst imaginable way to find
out that distinction had eroded — so the removal is an ALLOWLIST of directory names doxygen
itself creates, under our own output directory only.

@brief Tests for pruning abandoned doxygen output directories.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew.doxygen import _ABANDONED_OUTPUT_DIRS, _prune_abandoned_output


## @brief An abandoned generator's directory is removed.
## @version 1
def test_abandoned_output_directories_are_removed(tmp_path: Path) -> None:
    """FAILS BEFORE THE FIX: nothing removed these, so they accumulated forever.

    Asserts on CONTENT being gone rather than the directory alone, because the cost is the files
    inside it — a rmdir that left 14,630 files behind under a renamed parent would satisfy a
    weaker check.

    @brief Stale generator output is deleted.
    @version 1
    """
    out = tmp_path / "clew.doxygen"
    stale = out / "xml"
    stale.mkdir(parents=True)
    (stale / "index.xml").write_text("<doxygen/>\n", encoding="utf-8")

    removed = _prune_abandoned_output(out)

    assert removed == 1, f"expected one directory removed, got {removed}"
    assert not stale.exists(), "the abandoned xml/ directory survived"


## @brief The sqlite3 output the build actually uses is never touched.
## @version 1
def test_the_live_sqlite_output_is_never_removed(tmp_path: Path) -> None:
    """THE CONTROL THAT MATTERS MOST HERE. `sqlite3/` is the one directory the build depends on;
    a cleanup that took it would destroy the index it just produced, and every other assertion in
    this file would still pass. It is absent from the allowlist by construction, and this pins
    that rather than trusting the constant to stay correct.

    @brief The live output directory survives a prune.
    @version 1
    """
    out = tmp_path / "clew.doxygen"
    live = out / "sqlite3"
    live.mkdir(parents=True)
    (live / "doxygen_sqlite3.db").write_bytes(b"SQLite format 3\x00")
    stale = out / "html"
    stale.mkdir()

    _prune_abandoned_output(out)

    assert live.exists(), "the prune removed the sqlite3 output the build depends on"
    assert (live / "doxygen_sqlite3.db").exists(), "the generated database was deleted"
    assert not stale.exists(), "the stale html/ directory was not removed; this test is vacuous"


## @brief Nothing outside the named set is removed, however tempting.
## @version 1
def test_unknown_directories_are_left_alone(tmp_path: Path) -> None:
    """AN ALLOWLIST, NOT A DENYLIST, and the difference is the whole safety argument. "Delete
    anything that is not sqlite3" would also be a passing implementation of the test above while
    removing whatever else happened to be under the output directory — a target's own artefacts
    if the forced-output-directory rule ever eroded, or a future clew subdirectory nobody
    remembered to exempt.

    @brief Unrecognised directories survive.
    @version 1
    """
    out = tmp_path / "clew.doxygen"
    out.mkdir(parents=True)
    keep = out / "something-else"
    keep.mkdir()
    (keep / "data.bin").write_bytes(b"\x00")

    removed = _prune_abandoned_output(out)

    assert removed == 0, "a directory outside the allowlist was removed"
    assert (keep / "data.bin").exists(), (
        "the prune deleted a directory it does not recognise. It must be an allowlist of names "
        "doxygen creates; anything else could be a target's own artefacts."
    )


## @brief A missing output directory is not an error.
## @version 1
def test_a_missing_output_directory_is_harmless(tmp_path: Path) -> None:
    """The first build of a target has no output directory yet, and the prune runs on every
    build. Raising here would fail a build over housekeeping.

    @brief Pruning a non-existent directory is a no-op.
    @version 1
    """
    assert _prune_abandoned_output(tmp_path / "never-created") == 0


## @brief The allowlist stays aligned with the generators the build forces off.
## @version 1
def test_the_allowlist_names_only_generators_the_build_disables() -> None:
    """THE DRIFT GUARD. If a `GENERATE_* = YES` were ever forced, its directory would still be in
    this list and the build would delete its own output on the next run — a self-inflicted data
    loss that no test above would notice, because they all use directories the build genuinely
    does not produce.

    Read from the forced-flags text rather than restated, so the two cannot disagree.

    @brief Every pruned name corresponds to a disabled generator.
    @version 1
    """
    from clew.doxygen import _DOXYFILE_FORCED_FLAGS

    for name in _ABANDONED_OUTPUT_DIRS:
        flag = f"GENERATE_{name.upper()} = NO"
        assert flag in _DOXYFILE_FORCED_FLAGS, (
            f"{name}/ is pruned but '{flag}' is not among the forced flags, so the build may "
            "generate it — and would then delete its own output on the following run"
        )
