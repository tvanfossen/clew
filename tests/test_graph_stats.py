# SPDX-License-Identifier: MIT
"""gh#7 — the whole-graph aggregate, and the three misreadings it must prevent.

Each test here guards ONE mechanism, and every one of them was confirmed by
deleting that mechanism and watching this file go red. That matters more than
usual for an aggregate: the assertions are arithmetic, and arithmetic over a
fixture is the easiest thing in this repo to write green for the wrong reason.

The three misreadings:

  1. **A single "edge count".** `call_edges` stores one row per extraction LAYER,
     so its row count is not the number of call relationships. #38 shipped
     `callees('_run_pipeline')` returning 8 rows for four real callees; an
     aggregate reporting one number would republish that at whole-graph scale.

  2. **An empty layer read as a fact about the code.** `'empty'` and `'absent'`
     are different claims and only one of them is a measurement.

  3. **Non-fuzzy evidence tested per ROW instead of per PAIR.** A pair with one
     `exact` row and nine `fuzzy` ones HAS non-fuzzy evidence; a row filter counts
     it on the wrong side.

@brief Tests for clew.query.graph (gh#7).
@version 1
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest
from richdb import seed_doxygen_tables

from clew import query as q
from clew.ast_symbols import ensure_symbol_provenance
from clew.query.graph import EMPTY_ROW_MEANING, graph_stats
from clew.vocabulary import (
    CALL_MATCH_EXACT,
    CALL_MATCH_FUZZY,
    CALL_SOURCE_AST,
    CALL_SOURCE_AST_MEMBER,
    CALL_SOURCE_DOXYGEN_SQLITE,
    GRAPH_LAYERS,
    LAYER_STATE,
    LAYER_STATE_ABSENT,
    LAYER_STATE_EMPTY,
    LAYER_STATE_POPULATED,
    SYMBOL_SOURCE_AST,
    SYMBOL_SOURCE_DOXYGEN,
)


## @brief A writable private copy of the shared synthetic index.
## @param rich_db The session-scoped read-only index.
## @param tmp_path Per-test temporary directory.
## @return Path to the copy.
## @version 1
@pytest.fixture()
def own_db(rich_db: Path, tmp_path: Path) -> Path:
    """`rich_db` is session-scoped and SHARED, so every test that drops a table or
    rewrites `call_edges` has to work on its own copy. A byte copy is enough — none of
    these tests need the pipeline re-run.

    @brief Private copy of the synthetic index.
    @return Path to a writable clew.db.
    @version 1
    """
    own = tmp_path / "clew.db"
    shutil.copy(rich_db, own)
    return own


## @brief Replace every `call_edges` row with a declared set.
## @param db Database to rewrite.
## @param rows (caller_rowid, callee_rowid, source, confidence) tuples to insert.
## @return None.
## @version 1
def _set_call_edges(db: Path, rows: list[tuple[int, int, str, str]]) -> None:
    """Rewrites the layer wholesale so an arithmetic assertion has a KNOWN input.
    Deriving the expectation from the fixture's own rows would make the test agree with
    the code by construction, which is the failure mode this repo keeps finding in its
    own green suites.

    @brief Install a controlled call_edges layer.
    @version 1
    """
    conn = sqlite3.connect(db)
    try:
        conn.execute("DELETE FROM call_edges")
        conn.executemany(
            "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
            "VALUES (?,?,?,?)",
            rows,
        )
        conn.commit()
    finally:
        conn.close()


def test_rows_and_logical_pairs_are_separate_numbers_and_the_payload_says_which(
    own_db: Path,
) -> None:
    """The #38 misreading, refused at the aggregate level.

    THREE rows over TWO pairs is installed deliberately, so a payload that reported
    only one count would have to pick a wrong one. The assertions pin: both counts
    present and DIFFERENT, the inflation factor equal to their ratio, and
    `row_meaning` carrying BOTH figures plus the words that say which is the
    relationship count. That last clause is the actual contract — the numbers are
    useless to a consumer who cannot tell them apart, and `row_meaning` is the field
    that makes quoting one of them safe.
    """
    _set_call_edges(
        own_db,
        [
            # ONE relationship, stored once per layer that found it.
            (76, 158, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (76, 158, CALL_SOURCE_AST_MEMBER, CALL_MATCH_EXACT),
            # A second, distinct relationship found by one layer only.
            (76, 76, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
    )
    calls = graph_stats(own_db).calls

    assert calls.rows == 3
    assert calls.logical_pairs == 2
    assert calls.rows != calls.logical_pairs, "the two counts must not be conflated"
    assert calls.row_inflation == pytest.approx(1.5)

    # The self-describing half. Both numbers appear, and the sentence names which one
    # is the relationship count -- a consumer quoting `rows` as "the number of calls"
    # is the documented failure, so the payload has to refuse it in words.
    assert "3 rows" in calls.row_meaning
    assert "2 distinct" in calls.row_meaning
    assert "logical_pairs" in calls.row_meaning
    assert "ONE ROW PER EXTRACTION LAYER" in calls.row_meaning


def test_non_fuzzy_evidence_is_tested_per_pair_not_per_row(own_db: Path) -> None:
    """A pair with ONE exact row and one fuzzy row has non-fuzzy evidence.

    The installed layer has a majority of fuzzy ROWS and zero unresolved PAIRS, so a
    row-level filter would report the exact opposite of the truth. The second pair is
    all-fuzzy, which keeps the assertion from passing on a stubbed zero.
    """
    _set_call_edges(
        own_db,
        [
            (76, 158, CALL_SOURCE_DOXYGEN_SQLITE, CALL_MATCH_EXACT),
            (76, 158, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
            (76, 158, CALL_SOURCE_AST_MEMBER, CALL_MATCH_FUZZY),
            (158, 76, CALL_SOURCE_AST, CALL_MATCH_FUZZY),
        ],
    )
    calls = graph_stats(own_db).calls

    assert calls.rows_by_confidence[CALL_MATCH_FUZZY] == 3
    assert calls.rows_by_confidence[CALL_MATCH_EXACT] == 1
    # Two pairs; only the SECOND lacks non-fuzzy evidence.
    assert calls.logical_pairs == 2
    assert calls.pairs_without_nonfuzzy == 1
    assert calls.pairs_without_nonfuzzy_share == pytest.approx(0.5)


def test_an_empty_layer_reads_as_empty_and_a_dropped_one_as_absent(own_db: Path) -> None:
    """THIS REPO'S MOST-REPEATED LESSON, asserted rather than written down again.

    `'empty'` says a detector ran and found nothing — a measurement, whose meaning
    still depends on whether the detector could see (macro-defined accessors are
    invisible to a `memberdef`-reading detector, and that empty layer was once
    recorded as a correct negative and later retracted). `'absent'` says the table is
    not here at all, which is a fact about the BUILD and no evidence at all about the
    code.

    The control is the DROP: the same layer name is asserted `'empty'` before and
    `'absent'` after, on the same database, so a payload that collapsed the two into
    "no rows" cannot pass both halves.
    """
    layer = "external_boundaries"
    before = {s.layer: s for s in graph_stats(own_db).layers}
    assert before[layer].state == LAYER_STATE_EMPTY
    assert before[layer].rows == 0
    assert before["call_edges"].state == LAYER_STATE_POPULATED

    conn = sqlite3.connect(own_db)
    try:
        conn.execute(f"DROP TABLE {layer}")
        conn.commit()
    finally:
        conn.close()

    after = {s.layer: s for s in graph_stats(own_db).layers}
    assert after[layer].state == LAYER_STATE_ABSENT
    assert after[layer].rows == 0
    assert after[layer].state != before[layer].state, (
        "an absent layer must not report the same state as an empty one"
    )


def test_every_declared_layer_is_reported_with_a_registered_state(own_db: Path) -> None:
    """The inventory is TOTAL and its states are vocabulary members.

    A layer added to the schema and forgotten in `GRAPH_LAYERS` reports as nothing at
    all rather than as `absent`, which is a false negative that does not even look
    like one. And an unregistered state string would defeat the point of putting
    `layer_state` in `vocabulary.py`.
    """
    stats = graph_stats(own_db)
    assert [s.layer for s in stats.layers] == list(GRAPH_LAYERS)
    for stat in stats.layers:
        assert stat.state in LAYER_STATE.values, f"{stat.layer} reports unregistered {stat.state!r}"


def test_file_counts_read_the_persisted_coverage_and_admit_when_it_is_absent(
    own_db: Path,
) -> None:
    """gh#6's figures are READ, not re-measured — and their absence is disclosed.

    The first half proves the read reaches `build_meta`: a planted `coverage.*` value
    shows up in the payload, which a re-implementation computing its own barren ratio
    over the fixture could not do. The second half deletes the section and asserts
    `coverage_recorded` goes False with the figures at zero — the distinction between
    "measured healthy" and "never measured", which is the same absent-vs-empty rule
    one level up.
    """
    conn = sqlite3.connect(own_db)
    try:
        conn.executemany(
            "INSERT OR REPLACE INTO build_meta (key, value) VALUES (?,?)",
            [("coverage.substantive_files", "41"), ("coverage.barren_ratio", "0.125")],
        )
        conn.commit()
    finally:
        conn.close()

    files = graph_stats(own_db).files
    assert files.coverage_recorded is True
    assert files.substantive_files == 41
    assert files.barren_ratio == pytest.approx(0.125)
    # The three file counts are separate measurements, not one number restated.
    assert files.indexed_files >= files.files_with_symbols >= files.files_with_bodies

    conn = sqlite3.connect(own_db)
    try:
        conn.execute("DELETE FROM build_meta WHERE key LIKE 'coverage.%'")
        conn.commit()
    finally:
        conn.close()

    bare = graph_stats(own_db).files
    assert bare.coverage_recorded is False
    assert bare.substantive_files == 0
    assert bare.barren_ratio == 0.0
    # ...while the counts this module measures ITSELF are unaffected by the deletion.
    assert bare.indexed_files == files.indexed_files


def test_an_index_with_no_call_graph_says_so_instead_of_reporting_a_zero_ratio(
    own_db: Path,
) -> None:
    """An empty call graph must not present as a measured `0.00x` inflation.

    Both empty paths — the table dropped and the table emptied — have to produce the
    identical aggregate, because they are the same fact about the CALL GRAPH even
    though the layer inventory distinguishes them. The `EMPTY_ROW_MEANING` note is
    what stops a consumer reading zero pairs as "this repo has no calls".
    """
    _set_call_edges(own_db, [])
    emptied = graph_stats(own_db).calls
    assert emptied.logical_pairs == 0
    assert emptied.row_inflation == 0.0
    assert emptied.row_meaning == EMPTY_ROW_MEANING
    assert "statement about the index" in emptied.row_meaning

    conn = sqlite3.connect(own_db)
    try:
        conn.execute("DROP TABLE call_edges")
        conn.commit()
    finally:
        conn.close()

    dropped = graph_stats(own_db).calls
    assert dropped == emptied, "a dropped and an emptied call graph must aggregate alike"


def test_graph_stats_survives_a_database_with_no_tables(tmp_path: Path) -> None:
    """NON-RAISING, on the thinnest possible input.

    A trust aggregate that raises on a thin index is useless exactly when a consumer
    most needs to discover the index is thin — the same reasoning
    `coverage.measure_index_coverage` states for failing soft. Every layer reports
    `absent`, which is the honest answer and not a claim about any repository.
    """
    bare = tmp_path / "empty.db"
    sqlite3.connect(bare).close()

    stats = graph_stats(bare)
    assert stats.symbol_rows == 0
    assert stats.symbol_provenance == {}
    assert {s.state for s in stats.layers} == {LAYER_STATE_ABSENT}
    assert stats.calls.row_meaning == EMPTY_ROW_MEANING


def test_symbol_provenance_is_a_measured_distribution_or_nothing(
    tmp_path: Path,
    own_db: Path,
) -> None:
    """`{}` on an index that cannot answer, never an invented all-doxygen split.

    The invented split would be TRUE on such an index and still wrong to publish: a
    consumer cannot tell a measured mix from a fabricated one, so the honest answer
    to "what is the mix" on an index with no provenance column is "not recorded".

    THE `{}` HALF USED TO BE MEASURED ON `rich_db` AS IT SHIPPED, and cannot be any
    more (gh#362): the fixture was missing gh#11's `recover_ast_symbols`, the
    integration tier's fidelity check caught that as real schema drift, and the
    fixture now runs the stage — so it carries the provenance column like every real
    build. The pre-build-19 index is therefore built HERE from `seed_doxygen_tables`
    alone, which is still a genuine doxygen-only index rather than a simulated one:
    doxygen's verbatim schema has no `dg_source`, so nothing about it is hand-faked.
    The populated half then adds the column the way the pipeline does — through
    `ensure_symbol_provenance`, not a hand-written `ALTER TABLE`, so the retroactive
    `NOT NULL DEFAULT 'doxygen'` labelling is the pipeline's own and not this test's
    idea of it.

    `own_db` is kept as the second half's control: it PINS that the fixture now ships
    the column and reports a measured split, so a future fixture that silently loses
    the stage again fails here as well as in the integration tier.

    THAT CONTROL GOT STRONGER AT gh#372, and only because it FAILED. It used to assert
    `{doxygen: symbol_rows}` — an all-doxygen split — which was true of the fixture only
    because `recover_ast_symbols` happened to recover nothing from `csample`: every
    function there is a hand-made `memberdef` row. So the control could not tell "the
    stage ran and found nothing" from "the stage never ran", which is the exact
    distinction gh#362 added it to make. Recovering the six file-scope statics broke it,
    and the assertion now names BOTH provenances, so a fixture that loses the stage
    reports one key and fails rather than quietly matching.

    @brief Provenance is measured or absent, never invented.
    @version 3
    """
    pre19 = tmp_path / "pre19.db"
    seed_doxygen_tables(pre19)
    assert graph_stats(pre19).symbol_provenance == {}, (
        "an index with no provenance column must report {}, not an invented split"
    )

    conn = sqlite3.connect(pre19)
    try:
        assert ensure_symbol_provenance(conn) is True
        conn.commit()
    finally:
        conn.close()

    stats = graph_stats(pre19)
    assert stats.symbol_provenance == {SYMBOL_SOURCE_DOXYGEN: stats.symbol_rows}
    assert sum(stats.symbol_provenance.values()) == stats.symbol_rows

    shipped = graph_stats(own_db)
    assert set(shipped.symbol_provenance) == {SYMBOL_SOURCE_DOXYGEN, SYMBOL_SOURCE_AST}, (
        "the fixture must exercise BOTH provenances, or it cannot represent the "
        "`dg_source = 'doxygen'` filter every later test depends on"
    )
    assert shipped.symbol_provenance[SYMBOL_SOURCE_AST] > 0
    assert sum(shipped.symbol_provenance.values()) == shipped.symbol_rows


def test_the_aggregate_is_reachable_from_the_package_surface(rich_db: Path) -> None:
    """`graph_stats` is exported, and its export is the whole point of gh#7.

    The issue is not that the numbers were uncomputable — a consumer could sample
    `callers`/`callees` and estimate, and some benchmark cells did. It is that there
    was no endpoint. A private helper nobody can reach would leave the issue open with
    the code written.
    """
    assert "graph_stats" in q.__all__
    assert q.graph_stats(rich_db).calls.logical_pairs > 0
