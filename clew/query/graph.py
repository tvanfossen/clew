# SPDX-License-Identifier: MIT
"""The ONE aggregate: how much of this graph should a consumer trust (gh#7).

Every other accessor in this package is per-symbol or per-seed. `dossier`,
`callers`, `callees`, `chain_trace`, `thread_of`, `req_trace`, `source`,
`lookup_class` all take a name; `list_files` aggregates FILES and `thread_roster`
inventories THREADS. Nothing aggregated the EDGES — so the index graded every
edge it stores (`source`, `confidence`) and instructed a consumer to weigh that
grading, while giving it no way to learn how much of the graph carries which
value. Two benchmark cells on different models reached the
same conclusion independently: *"the database does not expose a summary of X% of
all edges are fuzzy"*.

Three things this module refuses to do, each because the alternative has already
gone wrong here:

1. **It does not report one "edge count".** `call_edges` stores one row per
   extraction LAYER — `UNIQUE(caller_rowid, callee_rowid, source)` — so the row
   count and the relationship count are different numbers. #38 shipped
   `callees('_run_pipeline')` returning 8 rows for four real callees; publishing a
   single aggregate would repeat that at whole-graph scale, one order of magnitude
   louder. Both numbers ship, plus a sentence carrying both.

2. **It does not re-measure file coverage.** gh#6 already computes the
   barren/undocumented ratios and `coverage.IndexCoverage.as_meta` persists them
   into `build_meta`; this reads that section. A second implementation of one
   question is what the single-path gate exists to refuse, and the two would
   disagree the first day the barren rule changed on one side.

3. **It does not report a layer's emptiness as a fact about the repository.**
   `layer_state` has three values, not two. An absent table is a statement about
   the BUILD; an empty one is a measurement whose meaning still depends on whether
   the detector could see anything at all. This repo has recorded a "correct
   negative" that was a blind detector (mbedtls's `STORE_SET_*` accessors are
   macros: 1093 call sites, 0 `memberdef` rows) and has the retraction in
   CLAUDE.md to prove the cost.

COST. Seven aggregate scans plus one `COUNT(*)` per layer, on a table whose
largest measured instance is 32,720 rows — milliseconds, and paid only when asked.
That is why this is its own tool and not a section of `status`: `status` is tier-0,
must answer before any database exists, and is called reflexively at the start of
every session.

@brief Whole-graph trust aggregate over one built index.
@version 1
"""

from __future__ import annotations

import sqlite3

from ..signature import read_build_signature
from ..vocabulary import (
    CALL_MATCH_FUZZY,
    EXTERNAL_ROOT_COLUMN,
    GRAPH_LAYERS,
    LAYER_STATE_ABSENT,
    LAYER_STATE_EMPTY,
    LAYER_STATE_POPULATED,
    SYMBOL_SOURCE_COLUMN,
    UNRESOLVED_PATH_COLUMN,
)
from ._common import (
    DbSource,
    connect,
    has_columns,
    meta_section,
    records_provenance,
    table_exists,
)
from .models import EdgeCounts, FileCounts, GraphStats, LayerStat

## The sentence that ships beside the two call-edge counts. A `{}`-templated
## CONSTANT rather than an f-string built at the call site, so the one wording a
## consumer may quote has one source — and so a test can assert the payload explains
## itself without pinning a whole paragraph written inline.
ROW_MEANING = (
    "{rows} rows over {pairs} distinct (caller_rowid, callee_rowid) pairs "
    "(inflation {inflation:.2f}x). `call_edges` stores ONE ROW PER EXTRACTION LAYER, "
    "so `rows` is NOT the number of call relationships and must never be quoted as "
    "one: `logical_pairs` is."
)

## Said when there are no call edges at all, because the templated sentence above
## would divide by zero and, worse, would report an inflation figure for a graph that
## has none. An empty call graph is a real state (a prose-only or unbuilt index) and
## it gets a sentence that says so rather than a formatted zero.
EMPTY_ROW_MEANING = (
    "This index holds NO call edges. That is a statement about the index, not a "
    "proof that the repository has no calls — check status for staleness and scope "
    "before concluding anything about the code."
)


## @brief One scalar aggregate, tolerating a table this index predates.
## @param conn Open connection.
## @param sql Statement returning exactly one row of one integer column.
## @return The integer, or 0 when the query cannot run.
## @version 1
## @dg_internal
def _scalar(conn: sqlite3.Connection, sql: str) -> int:
    """Fails soft to 0 for the same reason every other read on this surface degrades
    rather than raising: an aggregate over a database missing a later layer must
    describe what IS there. The layer inventory is what distinguishes that zero from
    a measured zero, so the softness here cannot be mistaken for a finding.

    @brief Run a one-integer aggregate, or 0.
    @return The scalar value.
    @version 1
    """
    try:
        row = conn.execute(sql).fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0]) if row and row[0] is not None else 0


## @brief A GROUP BY count as a name→count mapping.
## @param conn Open connection.
## @param sql Statement returning (label, count) rows.
## @return Mapping of label to count, descending by count; {} when the query cannot run.
## @version 1
## @dg_internal
def _distribution(conn: sqlite3.Connection, sql: str) -> dict[str, int]:
    """A NULL label becomes the empty string rather than being dropped: a row whose
    `confidence` was never set is part of the distribution, and silently omitting it
    would make the counts fail to sum to the total — which is the one arithmetic check
    a reader of a distribution actually performs.

    @brief Run a labelled count, ordered by count.
    @return label → count.
    @version 1
    """
    try:
        rows = conn.execute(sql).fetchall()
    except sqlite3.Error:
        return {}
    return {(label or ""): int(count) for label, count in rows}


## @brief Aggregate the call graph: rows, logical pairs, and the trust shares.
## @param conn Open connection.
## @return Populated EdgeCounts; an all-zero one with the empty-graph note when there are no edges.
## @version 3
## @req REQ-DDB-QUERY-008
def call_edge_counts(conn: sqlite3.Connection) -> EdgeCounts:
    """`pairs_without_nonfuzzy` is computed with `SUM(...) = 0` over a per-pair
    grouping rather than by filtering rows, and the difference is the whole point: a
    pair with one `exact` row and nine `fuzzy` ones HAS non-fuzzy evidence, and a
    row-level filter would count it on the wrong side. The question is "did ANY layer
    resolve this endpoint", which is a property of the pair.

    `confidence IS NOT NULL` is part of the non-fuzzy test because the column is
    nullable and a NULL is not evidence. Treating it as non-fuzzy would inflate the
    trustworthy share using rows that assert nothing.

    @brief Build the call-edge aggregate.
    @return EdgeCounts for this index.
    @version 3
    """
    if not table_exists(conn, "call_edges"):
        return _empty_edge_counts()
    rows = _scalar(conn, "SELECT COUNT(*) FROM call_edges")
    pairs = _scalar(
        conn,
        "SELECT COUNT(*) FROM (SELECT 1 FROM call_edges GROUP BY caller_rowid, callee_rowid)",
    )
    if not pairs:
        return _empty_edge_counts()
    unresolved = _scalar(
        conn,
        "SELECT COUNT(*) FROM (SELECT 1 FROM call_edges "
        "GROUP BY caller_rowid, callee_rowid HAVING SUM(CASE WHEN confidence IS NOT NULL "
        f"AND confidence <> '{CALL_MATCH_FUZZY}' THEN 1 ELSE 0 END) = 0)",
    )
    inflation = rows / pairs
    return EdgeCounts(
        rows=rows,
        logical_pairs=pairs,
        row_inflation=round(inflation, 4),
        pairs_without_nonfuzzy=unresolved,
        pairs_without_nonfuzzy_share=round(unresolved / pairs, 4),
        rows_by_confidence=_distribution(
            conn,
            "SELECT confidence, COUNT(*) FROM call_edges GROUP BY confidence ORDER BY 2 DESC",
        ),
        rows_by_source=_distribution(
            conn, "SELECT source, COUNT(*) FROM call_edges GROUP BY source ORDER BY 2 DESC"
        ),
        row_meaning=ROW_MEANING.format(rows=rows, pairs=pairs, inflation=inflation),
    )


## @brief The all-zero call aggregate, carrying the empty-graph explanation.
## @return EdgeCounts with every count zero and `row_meaning` set to EMPTY_ROW_MEANING.
## @version 2
## @dg_internal
def _empty_edge_counts() -> EdgeCounts:
    """Split out so BOTH empty paths — no table, and a table with no rows — produce
    the identical payload. They are different facts about the BUILD and the layer
    inventory reports them differently; they are the same fact about the call
    aggregate, and letting one of them fall through to a formatted `0.00x` inflation
    would put a computed-looking number on a graph that was never measured.

    @brief The empty-graph EdgeCounts.
    @return All-zero EdgeCounts.
    @version 2
    """
    return EdgeCounts(
        rows=0,
        logical_pairs=0,
        row_inflation=0.0,
        pairs_without_nonfuzzy=0,
        pairs_without_nonfuzzy_share=0.0,
        rows_by_confidence={},
        rows_by_source={},
        row_meaning=EMPTY_ROW_MEANING,
    )


## @brief Every richness layer's state, distinguishing empty from absent.
## @param conn Open connection.
## @return One LayerStat per name in `vocabulary.GRAPH_LAYERS`, in declared order.
## @version 2
## @req REQ-DDB-QUERY-008
def layer_states(conn: sqlite3.Connection) -> tuple[LayerStat, ...]:
    """`table_exists` is asked FIRST and its answer is carried, not inferred from the
    count. A `COUNT(*)` on a missing table raises, and catching that to produce 0
    would collapse `'absent'` into `'empty'` — erasing exactly the distinction this
    function exists to publish.

    @brief Report each layer as populated / empty / absent.
    @return LayerStat per declared layer.
    @version 2
    """
    stats: list[LayerStat] = []
    for layer in GRAPH_LAYERS:
        if not table_exists(conn, layer):
            stats.append(LayerStat(layer=layer, state=LAYER_STATE_ABSENT, rows=0))
            continue
        rows = _scalar(conn, f"SELECT COUNT(*) FROM {layer}")
        state = LAYER_STATE_POPULATED if rows else LAYER_STATE_EMPTY
        stats.append(LayerStat(layer=layer, state=state, rows=rows))
    return tuple(stats)


## @brief Read one persisted integer coverage figure, tolerating an absent section.
## @param meta The `coverage.*` section without its prefix.
## @param key Key to read.
## @return The parsed count, or 0 when absent or unparseable.
## @version 1
## @dg_internal
def _int_figure(meta: dict[str, str], key: str) -> int:
    """`build_meta` is a TEXT table and `write_build_signature` drops falsy values, so
    every coverage figure is stored as a string — including `"0"`, deliberately, so a
    measured zero survives. Parsing has to tolerate a key that predates the section
    without inventing a value.

    @brief Parse one stored integer coverage figure.
    @return The count, or 0.
    @version 1
    """
    try:
        return int(meta[key])
    except (KeyError, TypeError, ValueError):
        return 0


## @brief Read one persisted ratio coverage figure, tolerating an absent section.
## @param meta The `coverage.*` section without its prefix.
## @param key Key to read.
## @return The parsed ratio, or 0.0 when absent or unparseable.
## @version 1
## @dg_internal
def _float_figure(meta: dict[str, str], key: str) -> float:
    """Split from `_int_figure` rather than parameterised by a `cast` callable, so
    neither call site can be read as returning the other's type — the ratios and the
    counts sit next to each other in `FileCounts` and a `0` where `0.0` belongs is the
    kind of quiet type drift a frozen dataclass will not catch.

    @brief Parse one stored ratio coverage figure.
    @return The ratio, or 0.0.
    @version 1
    """
    try:
        return float(meta[key])
    except (KeyError, TypeError, ValueError):
        return 0.0


## @brief Indexed files vs files yielding symbols vs files yielding bodies.
## @param conn Open connection.
## @param db Path to the same database, for its persisted coverage section.
## @return Populated FileCounts, first party unless a field says otherwise.
## @version 2
## @req REQ-DDB-QUERY-008
def file_counts(conn: sqlite3.Connection, db: DbSource) -> FileCounts:
    """`files_with_bodies` counts DISTINCT non-null `bodyfile_id`, and the definition
    is stated because the decl/def duality makes "a file that yielded a body"
    genuinely ambiguous — doxygen attributes a C++ method to its declaring HEADER via
    `file_id` and to the `.cpp` holding its body via `bodyfile_id`. Counting one alone
    is wrong in one direction or the other, so both are reported and neither is called
    "the" file count.

    The gh#6 figures are READ from `build_meta`, never recomputed here. `db` is taken
    separately from `conn` for that read alone: an in-memory or caller-supplied
    connection has no path, so `coverage_recorded` correctly reports False rather than
    the reader inventing a healthy-looking zero.

    THE THREE COUNTED FIGURES ARE FIRST PARTY (gh#335), which is a change to what the
    SQL asks and NOT to what the graph contains. `_first_party` is a WHERE fragment
    over `path`, so a file inside a nested git tree stays fully indexed, fully
    reachable from `chain_trace` and `callers`, and simply lands in `external_files`
    instead of `indexed_files`. On an index predating the tag the fragment is `1`,
    which counts everything — correct, because such a build EXCLUDED nested trees, so
    everything in it really is first party.

    @brief Build the file-coverage aggregate.
    @return FileCounts for this index.
    @version 2
    """
    meta = meta_section(db, "coverage") if not isinstance(db, sqlite3.Connection) else {}
    tagged = _records_external(conn)
    mine = _first_party(tagged)
    return FileCounts(
        indexed_files=_scalar(conn, f"SELECT COUNT(*) FROM path WHERE type=1 AND {mine}"),
        files_with_symbols=_scalar(
            conn,
            "SELECT COUNT(*) FROM ("
            "SELECT file_id AS f FROM memberdef WHERE file_id IS NOT NULL "
            "UNION SELECT bodyfile_id FROM memberdef WHERE bodyfile_id IS NOT NULL"
            f") WHERE f IN (SELECT rowid FROM path WHERE {mine})",
        ),
        files_with_bodies=_scalar(
            conn,
            "SELECT COUNT(DISTINCT bodyfile_id) FROM memberdef WHERE bodyfile_id IS NOT NULL "
            f"AND bodyfile_id IN (SELECT rowid FROM path WHERE {mine})",
        ),
        coverage_recorded=bool(meta),
        substantive_files=_int_figure(meta, "substantive_files"),
        barren_files=_int_figure(meta, "barren_files"),
        barren_ratio=_float_figure(meta, "barren_ratio"),
        undocumented_files=_int_figure(meta, "undocumented_files"),
        undocumented_ratio=_float_figure(meta, "undocumented_ratio"),
        external_files=(
            _scalar(
                conn,
                f"SELECT COUNT(*) FROM path WHERE type=1 AND {EXTERNAL_ROOT_COLUMN} IS NOT NULL "
                f"AND {EXTERNAL_ROOT_COLUMN} <> ''",
            )
            if tagged
            else 0
        ),
        external_roots=_external_roots(conn) if tagged else (),
        external_recorded=tagged,
        unresolved_files=(
            _scalar(
                conn,
                f"SELECT COUNT(*) FROM path WHERE type=1 AND {UNRESOLVED_PATH_COLUMN} = 1",
            )
            if tagged
            else 0
        ),
    )


## @brief Whether this index carries the per-file provenance tags.
## @param conn Open connection.
## @return True when `path` has both provenance columns.
## @version 2
## @dg_internal
def _records_external(conn: sqlite3.Connection) -> bool:
    """BOTH columns, because the first-party predicate reads both and a half-stamped
    index would otherwise raise on the missing one. They are added by the same
    `ensure_external_provenance` call, so requiring both costs nothing and closes the
    one shape that would turn a non-raising aggregate into a raising one.

    @brief Report whether `path` carries the provenance columns.
    @return True when both columns are present.
    @version 2
    """
    return has_columns(conn, "path", EXTERNAL_ROOT_COLUMN, UNRESOLVED_PATH_COLUMN)


## @brief A WHERE fragment selecting first-party `path` rows.
## @param tagged Whether the index carries the provenance columns.
## @return SQL predicate text, `1` on an index predating the tags.
## @version 2
## @dg_internal
def _first_party(tagged: bool) -> str:
    """A NULL tag counts as FIRST PARTY, and both spellings of untagged are handled:
    `IS NULL` for a row the stamping stage never reached, `= ''` for one it reached
    and found first party. Treating NULL as external would be the worse direction —
    a partial build would silently disown its own repository and report a coverage
    ratio over nothing.

    @brief Build the first-party predicate.
    @return SQL text usable inside a WHERE clause.
    @version 2
    """
    if not tagged:
        return "1"
    return (
        f"({EXTERNAL_ROOT_COLUMN} IS NULL OR {EXTERNAL_ROOT_COLUMN} = '') "
        ## AND actually a file of this repository. Doxygen records an unresolvable
        ## `#include` as a bare filename, and 324 of those arrived with entropic's
        ## llama.cpp submodule — counted as first party, because a bare filename
        ## matches no external root. That moved `indexed_files` 488 → 804 on a change
        ## whose whole contract is that first-party figures do not move.
        f"AND ({UNRESOLVED_PATH_COLUMN} IS NULL OR {UNRESOLVED_PATH_COLUMN} = 0)"
    )


## @brief The distinct nested git trees this index holds files from.
## @param conn Open connection.
## @return Repo-relative external roots, sorted.
## @version 1
## @dg_internal
def _external_roots(conn: sqlite3.Connection) -> tuple[str, ...]:
    """@brief List the external roots present in the index.

    @return Sorted repo-relative roots.
    @version 1
    """
    rows = conn.execute(
        f"SELECT DISTINCT {EXTERNAL_ROOT_COLUMN} FROM path "
        f"WHERE {EXTERNAL_ROOT_COLUMN} IS NOT NULL AND {EXTERNAL_ROOT_COLUMN} <> '' "
        f"ORDER BY 1"
    ).fetchall()
    return tuple(row[0] for row in rows)


## @brief The `memberdef` provenance distribution (gh#11), or {} when unrecorded.
## @param conn Open connection.
## @return dg_source → row count; {} on an index predating the column.
## @version 2
## @dg_internal
def _symbol_provenance(conn: sqlite3.Connection) -> dict[str, int]:
    """Returns `{}` rather than `{'doxygen': N}` on an index without the column. The
    invented split would be TRUE — every row in such an index is doxygen's by
    construction — and would still be wrong to publish, because a consumer cannot
    tell a measured all-doxygen index from one that was never able to measure, and the
    honest answer to "what is the mix" on an index with no column is "not recorded".

    @brief Distribution of memberdef rows by provenance.
    @return dg_source → count, or {}.
    @version 2
    """
    if not records_provenance(conn):
        return {}
    return _distribution(
        conn,
        f"SELECT {SYMBOL_SOURCE_COLUMN}, COUNT(*) FROM memberdef "
        f"GROUP BY {SYMBOL_SOURCE_COLUMN} ORDER BY 2 DESC",
    )


## @brief Aggregate the whole graph: edges, files, layers and symbol provenance.
## @param db Path, str or open connection to a built index.
## @return The GraphStats aggregate.
## @version 1
## @req REQ-DDB-QUERY-008
def graph_stats(db: DbSource) -> GraphStats:
    """The single entry point gh#7 asks for, and the only accessor on this surface
    whose subject is the GRAPH rather than a symbol or a seed.

    NON-RAISING throughout: an index missing a later layer, a database with no
    tables, and a fully-built one all return a `GraphStats`. A trust aggregate that
    raises on a thin index is useless exactly when a consumer most needs to find out
    the index is thin — the same reasoning `coverage.measure_index_coverage` states
    for failing soft.

    @brief Build the whole-graph trust aggregate.
    @return GraphStats for this index.
    @version 1
    """
    with connect(db) as conn:
        return GraphStats(
            build_version=(
                None if isinstance(db, sqlite3.Connection) else read_build_signature(db)
            ),
            symbol_rows=_scalar(conn, "SELECT COUNT(*) FROM memberdef"),
            calls=call_edge_counts(conn),
            files=file_counts(conn, db),
            layers=layer_states(conn),
            symbol_provenance=_symbol_provenance(conn),
        )
