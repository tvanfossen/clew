# SPDX-License-Identifier: MIT
"""Hitting the scope walk's depth limit must be recorded, not only logged.

WHY IT MATTERS, AND WHY IT IS NOT A CURIOSITY. Past `_MAX_DEPTH` the walk stops descending, which
means nothing below is pruned and nothing below is checked for nested git trees — everything
there is admitted wholesale. On a deeply nested vendored dependency that is tens of thousands of
files the operator never chose, and the index could not say so: the build emitted a WARNING and
the log was gone by the time anyone queried.

REPORT ONLY, BY OWNER RULING. What gets indexed is deliberately unchanged, so `CLEW_BUILD_VERSION`
does not move and no existing index is invalidated. The point is to make the condition visible so
the decision about it can be taken against a number.

THE FIXTURE IS BUILT, NOT BORROWED. No real target in this suite is 16 directories deep, so a
test using one would assert against a limit it never reaches — the "subject too small to exercise
the condition" trap. These tests construct a tree past the limit and one comfortably inside it,
and the shallow case is what proves the reporting is not simply always-on.

MUTATION RESULTS, RECORDED SO THE NEXT READER DOES NOT RE-DERIVE THEM:

  * Removing the per-derivation reset is CAUGHT, by both the shallow-tree control and the
    reset test.
  * Removing EITHER prune site's recording is INERT, and that is a property of the design
    rather than a hole. The walk hits its limit twice on the same tree — once in the
    dot/cache prune and once in the nested-git-tree scan — so the two are independent
    recorders of one condition and no single-site edit can make a deep tree look shallow.
    Asserting which site fired would pin an implementation detail, not the property. If a
    future change makes the sites cover different trees, this note stops being true and the
    tests need splitting.

@brief Tests that the scope walk records where it stopped descending.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from clew import scope
from clew.scope import depth_limited_paths, derive_scope


## @brief Build a directory chain `depth` levels below root, with a source file at the bottom.
## @param root Directory to build under.
## @param depth How many nested directories to create.
## @return The deepest directory created.
## @version 1
def _nest(root: Path, depth: int) -> Path:
    """@brief Create a nested directory chain.
    @return The deepest directory.
    @version 1
    """
    here = root
    for level in range(depth):
        here = here / f"d{level}"
    here.mkdir(parents=True, exist_ok=True)
    (here / "deep.c").write_text("int deep(void) { return 0; }\n", encoding="utf-8")
    return here


## @brief A tree deeper than the limit records where the walk stopped.
## @version 1
def test_a_deep_tree_records_where_the_walk_stopped(tmp_path: Path) -> None:
    """FAILS BEFORE THE FIX with an empty list: the condition was detected and logged and then
    discarded, so nothing downstream could report it.

    Asserts the recorded path is INSIDE the deep chain rather than merely non-empty — a recorder
    that noted the repo root on every build would satisfy a count-only assertion while naming
    nothing useful.

    @brief The depth limit is recorded with its location.
    @version 1
    """
    _nest(tmp_path, scope._MAX_DEPTH + 3)
    derive_scope(tmp_path)

    hit = depth_limited_paths()
    assert hit, (
        f"the walk descended {scope._MAX_DEPTH}+ levels and recorded nothing, so an index built "
        "from this tree cannot say why its corpus is the size it is"
    )
    assert any("d0" in str(p) for p in hit), (
        f"the recorded paths do not point into the deep chain: {[str(p) for p in hit]}"
    )


## @brief A shallow tree records nothing, so the signal means something.
## @version 1
def test_a_shallow_tree_records_nothing(tmp_path: Path) -> None:
    """THE CONTROL, AND IT CARRIES THE WHOLE VALUE OF THE OTHER TEST. A recorder that fired on
    every build would pass the deep case and make the stamp meaningless — every index would
    report a depth limit and no reader could tell the affected targets from the rest. The
    presence of the key IS the signal, so its absence has to be real.

    @brief An ordinary tree hits no limit.
    @version 1
    """
    _nest(tmp_path, 3)
    derive_scope(tmp_path)

    assert depth_limited_paths() == [], (
        "a three-deep tree reported a depth limit, so the stamp fires on ordinary repositories "
        "and tells a reader nothing"
    )


## @brief The record describes the latest derivation, not an accumulation.
## @version 1
def test_the_record_is_reset_per_derivation(tmp_path: Path) -> None:
    """A BUILD DERIVES MORE THAN ONCE — `_scope_provenance` re-derives on the whole-repo tier —
    so a record that grew across derivations would report the same directory two or three times
    and read as a wider problem than exists. Worse, a shallow repo derived after a deep one in
    the same process would inherit the deep one's paths.

    @brief Each derivation replaces the previous record.
    @version 1
    """
    deep = tmp_path / "deep"
    deep.mkdir()
    _nest(deep, scope._MAX_DEPTH + 3)
    derive_scope(deep)
    assert depth_limited_paths(), "the deep derivation recorded nothing; this test is vacuous"

    shallow = tmp_path / "shallow"
    shallow.mkdir()
    _nest(shallow, 2)
    derive_scope(shallow)

    assert depth_limited_paths() == [], (
        "a shallow derivation inherited the previous one's record, so the stamp describes some "
        "other repository's walk"
    )
