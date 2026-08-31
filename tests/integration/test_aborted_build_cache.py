# SPDX-License-Identifier: MIT
"""An aborted build must keep its harvest payloads and claim nothing.

WHY THIS EXISTS. A target whose corpus outgrew what fits in one uninterrupted run could never
get warm: `IndexCache.commit()` runs only after the atomic swap, and every abort path closes the
connection uncommitted, so a killed build discarded every parsed payload. Measured in the field
as a 103 MB sidecar whose mtime did not move across six build attempts, several of them running
twenty minutes — attempt N+1 cost exactly what attempt 1 cost, forever.

THE SPLIT THIS PINS. Two different claims shared one transaction and only one of them needs the
swap:

  * a per-(file, stage) payload is keyed by the file's `content_sha`, so it is TRUE whether or
    not the build that computed it finished;
  * `source_files` asserts "this tree was successfully indexed", which an aborted build has NOT
    earned and must never write.

So the tests below are a pair, and the second is the one that stops the fix from becoming a bug:
payloads survive, and the claim does not. Asserting only the first would pass just as well for a
change that committed everything — the exact "two indistinguishable ways to be empty" shape this
repo has recorded more than any other.

THE CONTROL IS NOT OPTIONAL. `test_a_completed_build_populates_payloads` exists because
`COUNT(*) > 0` on a fixture that harvests nothing would fail for a reason that has nothing to do
with the abort path, and would read as this defect for as long as anyone believed it.

@brief Integration tests for cache durability across an aborted build.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import cli
from clew.cli import _build_argparser, _run_pipeline

pytestmark = pytest.mark.integration


## @brief Run the real pipeline against the pinned target with an explicit sidecar.
## @param root The target repository to index.
## @param out Database path for this build.
## @param cache Sidecar path, kept explicit so a test can inspect it independently of `out`.
## @return The output path, for chaining.
## @version 1
def _build(root: Path, out: Path, cache: Path) -> Path:
    """The sidecar is passed EXPLICITLY rather than derived from `out`, so a test can point two
    builds at one cache and read it without guessing the derivation.

    @brief Execute the build pipeline against the pinned target.
    @return The output database path.
    @version 1
    """
    args = _build_argparser().parse_args(["--repo-root", str(root), "--output", str(out)])
    args.index_cache = str(cache)
    _run_pipeline(args)
    return out


## @brief Count rows in one sidecar table, tolerating a table that was never created.
## @param sidecar The cache database.
## @param table The table to count.
## @return Row count, or -1 when the table does not exist.
## @version 1
def _rows(sidecar: Path, table: str) -> int:
    """Returns -1 rather than raising for an absent table, so a failure message can distinguish
    "the build never got far enough to create it" from "it is empty" — two different bugs.

    @brief Count rows in a sidecar table.
    @return The count, or -1 when the table is absent.
    @version 1
    """
    if not sidecar.exists():
        return -1
    conn = sqlite3.connect(str(sidecar))
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.OperationalError:
        return -1
    finally:
        conn.close()


## @brief A build that runs to completion records harvest payloads.
## @version 1
def test_a_completed_build_populates_payloads(guard_repo: Path, tmp_path: Path) -> None:
    """THE ANTI-VACUITY CONTROL for the two tests below. If this fixture harvested nothing, their
    `> 0` assertions would fail for a reason unrelated to the abort path and would be read as this
    defect. Run it first and believe the others only while it passes.

    @brief A successful build writes payloads.
    @version 1
    """
    out = tmp_path / "ok.db"
    sidecar = tmp_path / "ok.idxcache"
    _build(guard_repo, out, sidecar)
    assert _rows(sidecar, "extract_cache") > 0, (
        "the fixture harvests nothing; the pair below is vacuous"
    )
    assert _rows(sidecar, "source_files") > 0, "a completed build must record its scan"


## @brief An aborted build keeps every payload it managed to compute.
## @version 1
def test_an_aborted_build_keeps_its_harvest_payloads(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """FAILS BEFORE THE FIX with 0 rows. The stage patched to raise sits well AFTER the shared
    parse, so the payloads genuinely exist in the connection at the moment the build unwinds —
    the question this asks is purely whether they were flushed or rolled back.

    @brief Payloads survive an abort.
    @version 1
    """

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("stage failed after the shared parse")

    monkeypatch.setattr(cli, "mark_reachability", _boom)
    out = tmp_path / "aborted.db"
    sidecar = tmp_path / "aborted.idxcache"

    with pytest.raises(RuntimeError):
        _build(guard_repo, out, sidecar)

    assert _rows(sidecar, "extract_cache") > 0, (
        "an aborted build discarded its harvest payloads, so the next attempt pays full cold "
        "price — the defect that makes a large target unbuildable"
    )


## @brief A build killed DURING the shared parse still banks what it parsed.
## @version 1
def test_a_build_killed_during_the_shared_parse_keeps_what_it_parsed(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """WRITTEN BECAUSE THE OBVIOUS TEST WAS A MISS. `test_an_aborted_build_keeps_its_harvest_
    payloads` aborts in a LATE stage, by which point `run_harvest` has already flushed for every
    per-file stage — so it passes with both shared-parse flushes deleted. Verified by mutation,
    not assumed. It pins durability in general and says nothing about the pass that matters.

    THE SHARED PARSE IS THE LONG STAGE, and on a large target a kill lands INSIDE it. Only the
    periodic flush can bank anything there, because no `run_harvest` has run yet.

    `_FLUSH_EVERY` IS MONKEYPATCHED DOWN, and that is the point rather than a convenience: the
    production interval is 500 files and the fixture holds 63, so at the shipped value the
    periodic flush never executes in this suite at all. A test that cannot reach the condition it
    names is the "subject too small to exercise it" trap, and it would read as coverage forever.

    @brief Payloads survive a kill inside the shared parse.
    @version 1
    """
    from clew import harvest

    monkeypatch.setattr(harvest, "_FLUSH_EVERY", 5)
    real = harvest._shared_parse_one_file
    seen = {"n": 0}

    def _fail_partway(*args: object, **kwargs: object) -> None:
        seen["n"] += 1
        ## Far enough in that several flush intervals have elapsed, so a passing result means
        ## flushed-and-kept rather than "the abort happened after everything anyway".
        if seen["n"] > 20:
            raise RuntimeError("killed inside the shared parse")
        return real(*args, **kwargs)  # type: ignore[no-any-return]

    monkeypatch.setattr(harvest, "_shared_parse_one_file", _fail_partway)
    out = tmp_path / "midparse.db"
    sidecar = tmp_path / "midparse.idxcache"

    with pytest.raises(RuntimeError):
        _build(guard_repo, out, sidecar)

    assert seen["n"] > 20, "the probe never reached the shared parse"
    assert _rows(sidecar, "extract_cache") > 0, (
        "a kill inside the shared parse banked nothing — on a large target that is the whole "
        "twenty-minute pass discarded, which is the trap #505 exists to break"
    )


## @brief An aborted build does not claim the tree was indexed.
## @version 1
def test_an_aborted_build_claims_nothing(
    guard_repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """THE HALF THAT STOPS THE FIX BECOMING A BUG. `source_files` is what a later build reads to
    decide a file is unchanged; written by a build that never swapped, it would assert the index
    describes a tree it does not describe.

    Passes today (nothing is committed at all) and must KEEP passing after the fix — which is
    exactly why it is written now rather than after.

    @brief The success claim stays gated on the swap.
    @version 1
    """

    def _boom(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("stage failed after the shared parse")

    monkeypatch.setattr(cli, "mark_reachability", _boom)
    out = tmp_path / "claimless.db"
    sidecar = tmp_path / "claimless.idxcache"

    with pytest.raises(RuntimeError):
        _build(guard_repo, out, sidecar)

    assert _rows(sidecar, "source_files") <= 0, (
        "an aborted build wrote source_files, claiming a tree it never finished indexing"
    )
