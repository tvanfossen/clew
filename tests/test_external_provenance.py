# SPDX-License-Identifier: MIT
"""Per-file EXTERNAL provenance (gh#335) — the tag, and what must NOT move because of it.

gh#333 admits nested git trees into the index. That trade is only honest if two
things hold, and both are asserted here rather than argued:

1. **The first-party numbers do not move.** Admitting a submodule must raise the
   TOTAL row count and leave every first-party figure IDENTICAL. This is stronger
   than any assertion about the matcher, because it holds whatever the matcher
   does — the same shape as the check that settled gh#11 ("count doxygen's own rows
   on both sides"), and the reason it is the load-bearing test in this file.

2. **Nothing is filtered out of a query.** The tag changes what AGGREGATES say. It
   must never change what `list_files` returns, because an inventory that quietly
   omitted a submodule is the filtered-answer-that-reads-as-an-empty-answer failure
   applied to the one tool whose whole job is saying what is in here.

The rule under test is a FACT, not a convention: a directory with its own git tree
is external, and anything else the repo tracks is first party whatever it is called.
`test_a_vendored_directory_without_a_git_tree_is_first_party` is the negative half —
without it, a name-matching implementation would pass every other test here.

@brief Tests for external tagging, first-party aggregates, and non-filtering.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from gitfixture import git_run, make_gitlink, repo_with_submodules

from clew import query as q
from clew.coverage import measure_index_coverage
from clew.external import (
    external_roots,
    stamp_external_provenance,
)
from clew.vocabulary import EXTERNAL_ROOT_COLUMN

## Over MIN_SUBSTANTIVE_LINES, so no assertion here is secretly about the line floor.
BIG = 400


## @brief Build a source tree plus the index describing it.
## @param tmp_path Directory to build under.
## @param files (repo-relative path, symbols yielded) pairs.
## @param nested Repo-relative directories to give their own `.git` to.
## @return (database path, repo root).
## @version 1
def _indexed(
    tmp_path: Path,
    files: list[tuple[str, int]],
    nested: tuple[str, ...] = (),
) -> tuple[Path, Path]:
    """REAL FILES ON DISK, because coverage counts lines off disk — a fixture that
    only seeded the `path` table would measure zero substantive files and pass every
    assertion vacuously.

    NESTED TREES ARE NOW REAL GITLINKS, and the paragraph this replaces is this repo's own
    recorded lesson happening twice. It read: "The `.git` entries are DIRECTORIES rather than
    initialised repositories: the detection tests `(child / ".git").exists()` ... initialising 4
    repositories per test would make this file slow for no additional coverage."

    That was true of the detector and false of the world. gh#352 changed the question from "is
    there a `.git` here" to "does the PARENT record this as a gitlink", because a `.git` says
    somebody has a repository there while only the parent knows whether it treats that directory
    as a dependency or as its own committed code. On entropic the two answers differed: three
    trees tagged external, one declared in `.gitmodules`, and the other two holding the repo's
    own tracked blobs.

    So a fixture built from `.git` directories now tests nothing — it describes a world the
    detector no longer asks about. `_gitlink` below makes the parent actually record the child at
    mode 160000, which is what `git submodule` produces and what `.gitmodules` describes.

    @brief Seed an external-provenance fixture.
    @return Database path and repo root.
    @version 1
    """
    root = tmp_path / "repo"
    root.mkdir(parents=True, exist_ok=True)
    if nested:
        repo_with_submodules(root, *nested)
    db_path = tmp_path / "clew.db"
    conn = sqlite3.connect(str(db_path))
    conn.executescript(
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);"
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT,"
        " file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, bodyend INTEGER);"
        "CREATE VIRTUAL TABLE supplementary_docs USING fts5(file_path, heading, content);"
    )
    for index, (name, symbols) in enumerate(files, start=1):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("\n".join(f"line {n}" for n in range(BIG)), encoding="utf-8")
        conn.execute("INSERT INTO path (rowid, type, name) VALUES (?, 1, ?)", (index, name))
        for slot in range(symbols):
            conn.execute(
                "INSERT INTO memberdef (kind, name, file_id, bodyfile_id, bodystart, bodyend)"
                " VALUES ('function', ?, ?, ?, 1, 9)",
                (f"fn_{index}_{slot}", index, index),
            )
    conn.commit()
    conn.close()
    return db_path, root


## @brief The files a first-party-only repo holds.
## @return (path, symbols) rows.
## @version 1
def _ours() -> list[tuple[str, int]]:
    """@brief Twenty-five substantial first-party files.

    @return Fixture rows.
    @version 1
    """
    return [(f"src/mod_{n}.c", 6) for n in range(25)]


## @brief The files a vendored submodule adds.
## @return (path, symbols) rows.
## @version 1
def _theirs() -> list[tuple[str, int]]:
    """Deliberately BARREN (one symbol each). A vendored dependency whose headers
    yield nothing is the realistic case AND the one that moves a merged ratio most,
    so if the partition were wrong this fixture makes it visible rather than
    marginal.

    @brief Twelve substantial, barren files inside a nested git tree.
    @return Fixture rows.
    @version 1
    """
    return [(f"vendor/theirs/lib_{n}.c", 1) for n in range(12)]


## @brief A directory the repo declares as a submodule is detected; a copied-in one is not.
## @version 2
def test_only_a_directory_with_its_own_git_tree_is_external(tmp_path: Path) -> None:
    """THE RULE, stated as a discrimination rather than as a match. Both directories
    below are named `vendor/...`; only one is a declared dependency.

    @brief External detection keys on the parent's gitlink, never on a directory name.
    @version 2
    """
    db_path, root = _indexed(
        tmp_path,
        [*_ours(), *_theirs(), ("vendor/copied/header_only.h", 4)],
        nested=("vendor/theirs",),
    )
    assert external_roots(root) == ["vendor/theirs"]

    stamp_external_provenance(db_path, root)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = dict(conn.execute(f"SELECT name, {EXTERNAL_ROOT_COLUMN} FROM path").fetchall())
    finally:
        conn.close()

    assert rows["vendor/theirs/lib_0.c"] == "vendor/theirs"
    assert rows["vendor/copied/header_only.h"] is None, (
        "a copied-in third-party file with no git tree of its own IS first party — "
        "this repo committed it and owns it, and no name matching may say otherwise"
    )
    assert rows["src/mod_0.c"] is None


## @brief A stray clone inside a directory the parent TRACKS is first party.
## @version 1
def test_a_stray_developer_clone_the_parent_tracks_is_first_party(tmp_path: Path) -> None:
    """THE NEGATIVE HALF OF gh#352, and the case that forced the predicate split. Both
    directories here hold a real `.git`; only one is a gitlink in the parent's index. The other
    is a repository somebody CLONED into a directory whose files this repo tracks and owns.

    WHY THAT MUST BE FIRST PARTY. The external tag would otherwise be a property of the WORKING
    COPY rather than of the repository: the same commit indexes differently depending on who
    built it, and one of those indexes reports the repo's own code as somebody else's. Measured
    on [tvanfossen/entropic](https://github.com/tvanfossen/entropic): three roots tagged
    external against the ONE `.gitmodules` declares, because two of them held entropic's own
    committed blobs — `git ls-files -s` returns mode 100644 there, not 160000.

    A `.git`-only detector cannot express this test at all: it answers "somebody has a
    repository here", and the question is "did this repository declare it as a dependency".

    @brief A `.git` with no gitlink in the parent is first party.
    @version 1
    """
    db_path, root = _indexed(
        tmp_path,
        [*_ours(), *_theirs(), ("evidence/checkout/probe.c", 4)],
        nested=("vendor/theirs",),
    )
    ## A real repository, and the parent TRACKS its file rather than recording a gitlink — the
    ## shape `git clone` leaves behind inside a tracked directory.
    make_gitlink_free_clone = root / "evidence" / "checkout"
    git_run(make_gitlink_free_clone, "init", "-q", ".")
    git_run(root, "add", "-f", "evidence/checkout/probe.c")

    assert (make_gitlink_free_clone / ".git").is_dir(), "the fixture must hold a REAL git tree"
    assert external_roots(root) == ["vendor/theirs"], (
        "a stray clone in a tracked directory is NOT a declared dependency — reporting it "
        "makes the tag depend on who built the index rather than on what the repo committed"
    )

    stamp_external_provenance(db_path, root)
    conn = sqlite3.connect(str(db_path))
    try:
        rows = dict(conn.execute(f"SELECT name, {EXTERNAL_ROOT_COLUMN} FROM path").fetchall())
    finally:
        conn.close()

    assert rows["evidence/checkout/probe.c"] is None, "the repo's own tracked file stays ours"
    assert rows["vendor/theirs/lib_0.c"] == "vendor/theirs"


## @brief Admitting a submodule must not move a single first-party coverage figure.
## @version 1
def test_admitting_a_submodule_leaves_first_party_coverage_identical(tmp_path: Path) -> None:
    """THE LOAD-BEARING CONTROL, and the reason it is phrased as a comparison of two
    builds rather than as an expected number: it holds whatever the matcher does. If
    a first-party figure moves when a nested tree is admitted, the tagging is wrong,
    and no assertion about the matcher's internals would have caught it.

    The external files are barren, so an untagged build would drag `barren_ratio`
    from 0.0 to 12/37 — a visible, wrong measurement rather than a marginal one.

    @brief First-party coverage is invariant under admitting an external tree.
    @version 1
    """
    alone_db, alone_root = _indexed(tmp_path / "alone", _ours())
    stamp_external_provenance(alone_db, alone_root)
    alone = measure_index_coverage(alone_db, alone_root)

    both_db, both_root = _indexed(
        tmp_path / "both", [*_ours(), *_theirs()], nested=("vendor/theirs",)
    )
    stamp_external_provenance(both_db, both_root)
    both = measure_index_coverage(both_db, both_root)

    assert both.indexed_files == alone.indexed_files
    assert both.substantive_files == alone.substantive_files
    assert both.barren_files == alone.barren_files
    assert both.barren_ratio == alone.barren_ratio
    assert both.undocumented_files == alone.undocumented_files

    ## And the TOTAL really did rise — without this the test above would pass just as
    ## well against a build that never indexed the submodule at all, which is the
    ## behaviour gh#333 removed.
    assert both.external_files == 12
    assert both.external_roots == ("vendor/theirs",)
    assert alone.external_files == 0


## @brief graph_stats reports first party by default and names the external population.
## @version 1
def test_graph_stats_counts_first_party_and_reports_external_beside_it(tmp_path: Path) -> None:
    """The same invariance one layer up, where a consumer actually reads it. Asserted
    against the file counts `graph_stats` COMPUTES rather than the coverage figures it
    merely reads back, because those are two different mechanisms and only one of them
    is exercised by the coverage test above.

    @brief graph_stats file counts exclude external files and count them separately.
    @version 1
    """
    db_path, root = _indexed(tmp_path, [*_ours(), *_theirs()], nested=("vendor/theirs",))
    stamp_external_provenance(db_path, root)

    stats = q.graph_stats(db_path)

    assert stats.files.indexed_files == 25, "the 12 vendored files are not this repo's"
    assert stats.files.files_with_symbols == 25
    assert stats.files.files_with_bodies == 25
    assert stats.files.external_files == 12
    assert stats.files.external_roots == ("vendor/theirs",)
    assert stats.files.external_recorded is True


## @brief An index predating the tag reports every file as first party, and says so.
## @version 1
def test_an_untagged_index_reports_no_external_recording(tmp_path: Path) -> None:
    """`external_files == 0` is TRUE both for a repo that vendors nothing and for an
    index built before gh#335 — `external_recorded` is what separates them, for the
    same reason `coverage_recorded` exists. An unmeasured zero that reads as a
    measured one is how a reader concludes "checked and fine" from "not checked".

    Counting everything as first party on such an index is correct rather than a
    fallback: a build below build version 32 EXCLUDED nested git trees outright, so
    everything it holds really is first party.

    @brief An index with no external column reports first-party counts and not-recorded.
    @version 1
    """
    db_path, _ = _indexed(tmp_path, _ours())

    stats = q.graph_stats(db_path)

    assert stats.files.indexed_files == 25
    assert stats.files.external_files == 0
    assert stats.files.external_recorded is False


## @brief list_files must LIST external files, annotated, never filtered out.
## @version 1
def test_list_files_returns_external_files_annotated_not_filtered(tmp_path: Path) -> None:
    """THE NON-FILTERING GUARANTEE. Every aggregate in this file reports first party
    by default; a query must not. An inventory that said "this repo contains 25 files"
    while the index holds 37 is precisely the failure the emptiness notes exist to
    prevent, and it is worse here than elsewhere because `list_files` is the tool a
    reader uses to find out what the index covers.

    @brief list_files includes external files and tags them.
    @version 1
    """
    db_path, root = _indexed(tmp_path, [*_ours(), *_theirs()], nested=("vendor/theirs",))
    stamp_external_provenance(db_path, root)

    listed = q.list_files(db_path)
    owners = {entry.path: entry.external_root for entry in listed}

    assert len(listed) == 37, "an external file is annotated, never withheld"
    assert owners["vendor/theirs/lib_0.c"] == "vendor/theirs"
    assert owners["src/mod_0.c"] == ""
    assert q.list_files(db_path, "vendor/*"), "a glob over the submodule still answers"


## @brief An unresolved `#include` row must not be counted as this repo's.
## @version 1
def test_an_unresolved_include_is_neither_first_party_nor_external(tmp_path: Path) -> None:
    """THE DEFECT THAT MADE THE INVARIANCE ABOVE FALSE, and it was found on the real
    target rather than here. Doxygen registers a `path` row for every `#include` it
    cannot resolve, spelled as a BARE FILENAME with no directory. A bare filename
    matches no external root, so every one of them counted as first party.

    Measured on [entropic](https://github.com/tvanfossen/entropic): admitting the
    llama.cpp submodule added 324 such rows from its Ascend and Hexagon backends and
    moved `indexed_files` from 488 to 804 — on a change whose entire contract is that
    no first-party figure moves. The RATIOS held throughout, because those files do
    not exist on disk and the line count had already dropped them from the
    substantive set. An invariant preserved by an accident one layer down is not
    preserved, and the accident is exactly why no ratio assertion caught it.

    @brief A bare-filename row is counted apart from both populations.
    @version 1
    """
    db_path, root = _indexed(tmp_path, _ours())
    conn = sqlite3.connect(str(db_path))
    try:
        ## Exactly what doxygen writes for an unresolvable include: a name with no
        ## directory and no file behind it.
        conn.execute("INSERT INTO path (type, name) VALUES (1, 'aclnn_add.h')")
        conn.commit()
    finally:
        conn.close()
    stamp_external_provenance(db_path, root)

    coverage = measure_index_coverage(db_path, root)
    assert coverage.indexed_files == 25, "an unresolvable include is not one of this repo's files"
    assert coverage.external_files == 0, "nor is it attributable to a named foreign tree"
    assert coverage.unresolved_files == 1, "and the exclusion is reported, not silent"

    stats = q.graph_stats(db_path)
    assert stats.files.indexed_files == 25
    assert stats.files.unresolved_files == 1


## @brief A nested tree that owns no indexed row is never named in the stamp.
## @version 1
def test_a_nested_tree_with_no_indexed_file_is_not_reported(tmp_path: Path) -> None:
    """TWO REASONS, EITHER SUFFICIENT, and the second is the one that made this
    urgent. A nested tree some other rule already excluded contributes no row, so:

    - naming it is misleading — "0 files belong to 1 nested tree" reads like a broken
      detector, and that exact line cost a real measurement here before it was traced
      to an unrelated cause;
    - ANYTHING STAMPED IS PUBLISHED OVER MCP. The walk sees every directory on disk,
      including trees the index deliberately does not cover, and emitting one of those
      names into `build_meta` discloses a path this build was configured to leave out.
      Caught on this repo's own self-index, which holds an excluded target directory.

    @brief A detected-but-empty external root is counted, not named.
    @version 1
    """
    ## A DECLARED dependency with NO indexed file — the shape an exclusion leaves behind. It has
    ## to be a real gitlink, not just a directory holding `.git`: since gh#352 the latter is a
    ## stray developer clone, which is first party and would make this test pass for the wrong
    ## reason (`external_roots` empty because nothing was DETECTED, rather than because the
    ## detected root owns no row).
    db_path, root = _indexed(tmp_path, _ours(), nested=("excluded_area/someone_elses",))

    assert external_roots(root) == ["excluded_area/someone_elses"], "detection still sees it"

    tagged, reported = stamp_external_provenance(db_path, root)

    assert tagged == 0
    assert reported == [], "a root that owns no row must not reach build_meta"
    assert measure_index_coverage(db_path, root).external_roots == ()


## @brief A SUBMODULE, whose `.git` is a FILE, is detected like a clone.
## @version 1
def test_a_submodule_whose_git_is_a_file_is_detected(tmp_path: Path) -> None:
    """THE CASE THE WHOLE FEATURE WAS BUILT FOR, and the one every other fixture in
    this file gets wrong. A `git submodule` checkout writes a 44-byte
    `gitdir: ../../.git/modules/<name>` POINTER FILE where a standalone clone has a
    `.git` DIRECTORY, and the detector tested `".git" in dirnames`.

    Found on [tvanfossen/entropic](https://github.com/tvanfossen/entropic), which
    wraps llama.cpp as a submodule: the build reported 28 nested trees — a number
    that made the detector look like it was working — and `extern/llama.cpp` was not
    one of them. No unit fixture could have caught it, because every fixture built a
    `.git` directory. This one does not.

    @brief A `.git` file marks a nested tree just as a `.git` directory does.
    @version 1
    """
    root = repo_with_submodules(tmp_path / "repo")
    make_gitlink(root, "extern/theirs", git_as_file=True)

    assert not (root / "extern" / "theirs" / ".git").is_dir(), (
        "the fixture's whole point is that this `.git` is a FILE — if some helper turned it "
        "back into a directory the test would pass while covering the case that already worked"
    )
    assert external_roots(root) == ["extern/theirs"], (
        "a submodule's .git is a FILE; a detector that only looks for a directory "
        "is blind to every submodule while still reporting a plausible count"
    )


## @brief Two sibling trees sharing a name prefix are attributed separately.
## @version 1
def test_a_shared_path_prefix_does_not_misattribute_a_sibling_tree(tmp_path: Path) -> None:
    """`vendor/lib` and `vendor/lib-utils` share a prefix, and a bare `startswith`
    would tag the second repo's files as belonging to the first — a WRONG attribution,
    which is worse than an absent one because it reads as a confident measurement
    rather than as missing knowledge.

    @brief Prefix matching respects the path separator.
    @version 1
    """
    db_path, root = _indexed(
        tmp_path,
        [("vendor/lib/a.c", 3), ("vendor/lib-utils/b.c", 3)],
        nested=("vendor/lib", "vendor/lib-utils"),
    )
    stamp_external_provenance(db_path, root)

    owners = {entry.path: entry.external_root for entry in q.list_files(db_path)}

    assert owners["vendor/lib/a.c"] == "vendor/lib"
    assert owners["vendor/lib-utils/b.c"] == "vendor/lib-utils"


## @brief The directory rollup lists what is INDEXED and never claims to be a tree census.
## @return None.
## @version 1
def test_directory_rollup_says_what_it_counts_and_lists_external_files(tmp_path: Path) -> None:
    """SIX SHELL CALLS TO REPLACE A DELETED TOOL. `list_files` has always inventoried the indexed
    files, and the `list_files` TOOL was removed in the four-tool consolidation — so on mbedtls
    2026-08-14 Q4 ran six `find … | wc -l` commands, 6 of that cell's 11 fallbacks, and still
    missed the four marks it was computing them for.

    THE ROLLUP MUST NOT READ AS A TREE CENSUS, and on this target that distinction inverts the
    answer: mbedtls `tests/` holds 310 tracked files and 44 indexed ones, because most are
    `.function` / `.data` fixtures no grammar handles. So the largest directory in the INDEX is
    `library` and in the REPOSITORY is `tests`, and a reply offering the first as the second would
    argue for a wrong answer — the same class as the two false-count rosters and the config
    payload.

    IT ALSO MUST NOT ASSERT AN ARITHMETIC IT DOES NOT HAVE. `coverage.indexed_files` is 443 where
    the rollup is 527; I wrote the reconciliation as 527-41 and then as 527-41-259 and NEITHER
    added up, because coverage also drops prose and documentation and those categories overlap. So
    the note states the two DEFINITIONS instead. A stated sum that does not add up is worse than
    none, and this test pins the definitions rather than the numbers for the same reason.

    NON-FILTERING HOLDS HERE TOO: an external file is counted and annotated, never omitted, or the
    rollup would report a smaller repository than the index holds.
    """
    from clew.query import directory_rollup
    from clew.query.corpus import rollup_meaning

    db_path, root = _indexed(tmp_path, [*_ours(), *_theirs()], nested=("vendor/theirs",))
    stamp_external_provenance(db_path, root)
    roll = directory_rollup(db_path)

    by_dir = {e.directory: e for e in roll.directories}
    assert by_dir, "the rollup must produce rows for an index that holds files"
    assert roll.indexed_files == sum(e.indexed_files for e in roll.directories)
    ## Largest first, so "which directory is biggest HERE" is the first row rather than a scan.
    counts = [e.indexed_files for e in roll.directories]
    assert counts == sorted(counts, reverse=True)

    ## THE EXTERNAL FILES ARE PRESENT AND ANNOTATED. The fixture indexes a vendored git tree, so
    ## some directory must carry a non-zero external count — omitting them would be the
    ## filtered-answer failure applied to the inventory.
    assert sum(e.external_files for e in roll.directories) > 0, (
        "an external file must be COUNTED and annotated, never filtered out of the inventory"
    )

    ## THE SENTENCE IS THE LOAD-BEARING PART, and it must make both misreadings impossible.
    note = roll.rollup_meaning
    assert "INDEXED" in note and "not a census of the tree" in note
    assert "largest directory in the repository" in note, (
        "the reply must separate 'largest here' from 'largest in the repository'"
    )
    assert "not one subtraction" in note, (
        "it must NOT claim the coverage difference is a single arithmetic — two attempts at that "
        "sum both failed to reconcile"
    )

    ## AND IT STAYS SILENT ON AN EMPTY INDEX rather than describing an absent file set.
    assert rollup_meaning(0, 0, 0) == ""
    ## The cap is reported when it applies, never silently.
    assert "not shown" in rollup_meaning(100, 5, 9)
    assert "not shown" not in rollup_meaning(100, 9, 9)
