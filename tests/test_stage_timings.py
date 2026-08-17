# SPDX-License-Identifier: MIT
"""Where a build's time goes, persisted beside what the build cost in total.

`refresh.duration_ms` is one number over thirty stages: enough to decide whether to
refresh, not enough to decide what to make faster. The per-stage timings existed at
runtime and were thrown away, the same shape as the scope decision that was computed,
logged and discarded before anyone stamped it.

The weakness of mark-based timing is worth stating because it decides what these
tests can and cannot prove: a stage whose `timer.mark` is MISSING is not reported
missing — its cost is charged to whichever segment closes next. So the recorded name
set is pinned against a real build here. That catches a deleted or renamed mark. It
does not catch a newly added stage that nobody marked, and nothing cheap does.

@brief Per-stage build timing: the timer itself, and a real build's breakdown.
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from clew.cli import build_index
from clew.stagetimer import STAGES_KEY, StageTimer, parse_stages

## Stages every build of any repo runs, whatever it contains. Deliberately not the
## whole list: `enrich` is conditional on a flag and `index_cache_scan` on a cache,
## and asserting a conditional stage unconditionally would pin the fixture's
## configuration rather than the pipeline's shape.
REQUIRED_STAGES = frozenset(
    {
        "resolve",
        "declaration",
        "doxygen",
        "copy",
        "sanitize",
        "fix_paths",
        "repair_names",
        "supplementary_docs",
        "kconfig",
        "kconfig_gates",
        "ast_symbols",
        "coverage",
        "file_docs",
        "call_edges",
        "macro_hop_edges",
        "ast_call_edges",
        "callback_edges",
        "locks",
        "dispatch_edges",
        "dominated_fuzzy",
        "threads",
        "shared_key_inferred",
        "shared_key_declared",
        "mqtt_dispatch",
        "event_edges",
        "thread_boundaries",
        "requirements",
        "req_edges",
        "req_test_edges",
        "reachability",
        "scope_provenance",
        "signature",
        "swap",
        "report_stats",
    }
)


## @brief A timer with no marks stamps no key at all.
## @version 1
def test_an_unmarked_timer_records_nothing() -> None:
    """`write_build_signature` drops falsy values, so an empty string would vanish
    anyway — but it would vanish silently, and a reader inspecting the timer directly
    would see a measurement that was never taken.

    @brief No marks means no section fragment.
    @version 1
    """
    assert StageTimer().as_meta() == {}
    assert StageTimer().stages() == ()


## @brief Marks partition the timed span, in order, and survive a round trip.
## @version 1
def test_marks_record_in_order_and_round_trip_through_the_stored_form() -> None:
    """The round trip is the load-bearing half: the value is stored as text in a TEXT
    column and read back by `status`, so a writer and a reader that disagreed about
    the separator would produce a breakdown that silently decodes to nothing.

    @brief Encode and decode a breakdown without loss.
    @version 1
    """
    timer = StageTimer()
    timer.mark("first")
    timer.mark("second")
    timer.mark("third")

    names = [name for name, _ in timer.stages()]
    assert names == ["first", "second", "third"], "order is the reading order"

    rendered = timer.as_meta()[STAGES_KEY]
    assert parse_stages(rendered) == timer.stages()


## @brief A malformed stored breakdown decodes to what it can, and does not raise.
## @version 1
def test_a_malformed_breakdown_decodes_without_raising() -> None:
    """This value is read in a reporting path. A breakdown that cannot be shown must
    not take a `status` call down with it, so a bad segment is dropped rather than
    raised on.

    @brief Decoding is fail-soft.
    @version 1
    """
    assert parse_stages("good=12 broken nonnumeric=xy also_good=3") == (
        ("good", 12),
        ("also_good", 3),
    )
    assert parse_stages("") == ()


@pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="the breakdown is asserted against a real build",
)
## @brief A real build records every stage of the pipeline, in execution order.
## @version 1
def test_a_real_build_records_a_breakdown_covering_every_stage(tmp_path: Path) -> None:
    """Pinned against a REAL build rather than a stubbed one, because the thing that
    can break is a `timer.mark` deleted from `_build_stages` — and a stub of
    `_build_stages` is exactly the thing that would not notice.

    Ordering is asserted at the two ends rather than as a full sequence: `doxygen`
    must precede `reachability` because the graph cannot be traversed before it is
    parsed, and pinning all thirty-four positions would fail on any reordering the
    pipeline is free to make.

    @brief Every pipeline stage appears in the stored breakdown.
    @version 1
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "unit.c").write_text("/** @brief A unit. */\nvoid unit(void) {}\n", encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(
        f"INPUT = {root}\nOUTPUT_DIRECTORY = {root}/out\nRECURSIVE = YES\nGENERATE_SQLITE3 = YES\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    build_index(output=out, repo_root=root, doxyfile=doxyfile)

    refresh = _refresh_meta(out)
    stages = parse_stages(refresh[STAGES_KEY])
    names = [name for name, _ in stages]

    missing = REQUIRED_STAGES - set(names)
    assert not missing, (
        f"stages ran but were never marked, so their cost is misattributed: {missing}"
    )
    assert names.index("doxygen") < names.index("reachability")
    assert all(elapsed >= 0 for _, elapsed in stages)
    assert "enrich" not in names, "a stage that did not run must not be reported"


@pytest.mark.skipif(
    shutil.which("doxygen") is None,
    reason="the breakdown is asserted against a real build",
)
## @brief The breakdown accounts for the whole measured duration.
## @version 1
def test_the_breakdown_sums_to_within_the_reported_duration(tmp_path: Path) -> None:
    """The segments partition the timed span, so their sum cannot exceed the total —
    and if it does, marks are being taken on more than one clock. The lower bound is
    the useful half: it says the breakdown covers the build rather than some inner
    fraction of it, which is what makes "where did the time go" answerable at all.

    @brief Segments cover the duration they are reported beside.
    @version 1
    """
    root = tmp_path / "repo"
    root.mkdir()
    (root / "unit.c").write_text("/** @brief A unit. */\nvoid unit(void) {}\n", encoding="utf-8")
    doxyfile = root / "Doxyfile"
    doxyfile.write_text(
        f"INPUT = {root}\nOUTPUT_DIRECTORY = {root}/out\nGENERATE_SQLITE3 = YES\n",
        encoding="utf-8",
    )
    out = tmp_path / "clew.db"
    build_index(output=out, repo_root=root, doxyfile=doxyfile)

    refresh = _refresh_meta(out)
    total = int(refresh["duration_ms"])
    summed = sum(elapsed for _, elapsed in parse_stages(refresh[STAGES_KEY]))
    assert summed <= total, "segments cannot exceed the span they partition"
    assert summed >= total // 2, (
        f"the breakdown accounts for only {summed}ms of a {total}ms build — "
        "a stage boundary is being missed"
    )


## @brief The `refresh.*` build_meta section of a built index.
## @param db Database path.
## @return Mapping of unprefixed refresh key to value.
## @version 1
def _refresh_meta(db: Path) -> dict[str, str]:
    """@brief Read the stamped refresh record."""
    conn = sqlite3.connect(str(db))
    try:
        rows = conn.execute(
            "SELECT key, value FROM build_meta WHERE key LIKE 'refresh.%'"
        ).fetchall()
    finally:
        conn.close()
    return {key.split(".", 1)[1]: value for key, value in rows}
