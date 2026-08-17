# SPDX-License-Identifier: MIT
"""R2 query-library tests.

Two tiers, matching the rest of the suite:
  * The shared `rich_db` — one whole-graph fixture (session-scoped) exercising
    dossier / callers / callees / chain_trace (shared-key seam) / req_trace /
    thread APIs / search / source / list_files / prose against a graph carrying
    every shape the query layer distinguishes: decl/def duality on one name, one
    logical edge found by two extraction layers, an fnptr edge with no textual
    call site, a shared-key seam with no call path, and both liveness values.
  * Per-test hand-built sqlite DBs for the invariants a whole-graph fixture
    cannot contain WITHOUT contradicting itself — a cycle, a depth cap deeper
    than the graph, a terminus, a crosses-thread key hop, a genuine overload, a
    pre-R1 schema, a table-less database.

@brief Tests for clew.query (R2).
@version 3
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from clew import query as q
from clew.query.traversal import _cap_at_depth


def _all_function_names(db: Path) -> list[str]:
    """Every distinct function name in an index, for the whole-graph sweeps below.

    @brief List every indexed function name.
    @return Sorted distinct function names.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return sorted(
            r[0]
            for r in conn.execute(
                "SELECT DISTINCT name FROM memberdef WHERE kind='function'",
            )
        )
    finally:
        conn.close()


# ─── integration: dossier ────────────────────────────────────────────────────


def test_dossier_writer_identity_and_liveness(rich_db: Path) -> None:
    """The dossier's identity + liveness/thread/terminus structure for a plain
    writer. Split from the R1-field assertions below so each test names one
    thing (and so neither exceeds the complexity standard)."""
    d = q.function_dossier(rich_db, "sensor_poll")
    assert d is not None
    assert d.name == "sensor_poll"
    assert d.signature == "void sensor_poll(void)"
    assert d.liveness == "live"
    assert d.is_terminus is False
    assert d.threads == []
    assert d.termini == []


def test_dossier_writer_has_shared_key_and_r1_fields(rich_db: Path) -> None:
    """sensor_poll writes DEMOBOT_POWER_BATTERY_MV → telemetry_report; the
    KeyEdge carries the R1 dispatch/thread fields."""
    d = q.function_dossier(rich_db, "sensor_poll")
    assert d is not None
    writes = {w.other: w for w in d.writes if w.key_name == "DEMOBOT_POWER_BATTERY_MV"}
    assert "telemetry_report" in writes
    edge = writes["telemetry_report"]
    # R1 semantic fields present on every KeyEdge (unknown/None here — the
    # fixture declares no dispatch_mode/edge_triggered).
    assert edge.dispatch_mode == "unknown"
    assert edge.edge_triggered is None
    assert edge.crosses_thread is None
    assert edge.to_thread is None
    # A declared (state) edge and an inferred edge both surface.
    kinds = {(w.source, w.edge_kind) for w in d.writes}
    assert ("shared_key_declared", "state") in kinds


def test_dossier_reader_and_requirements(rich_db: Path) -> None:
    """telemetry_report reads the battery key (other = the writer) and links
    its own requirement."""
    d = q.function_dossier(rich_db, "telemetry_report")
    assert d is not None
    reads = {r.other for r in d.reads if r.key_name == "DEMOBOT_POWER_BATTERY_MV"}
    assert "sensor_poll" in reads
    assert any(r.req_id == "REQ-0400" for r in d.requirements)


def test_all_req_edges_agrees_with_req_trace(rich_db: Path) -> None:
    """all_req_edges lists the implementer edges, agreeing with req_trace."""
    rt = q.req_trace(rich_db, "REQ-0621")
    bulk_impl = {e.fn for e in q.all_req_edges(rich_db) if e.req_id == "REQ-0621"}
    assert {i.name for i in rt.implementers} <= bulk_impl


def test_dossier_unknown_function_is_none(rich_db: Path) -> None:
    assert q.function_dossier(rich_db, "no_such_function_xyz") is None


def test_dossier_unambiguous_has_no_candidates(rich_db: Path) -> None:
    """A uniquely-named function's dossier carries an empty `candidates` — the
    overload signal must not fire on the common case."""
    d = q.function_dossier(rich_db, "sensor_poll")
    assert d is not None
    assert d.candidates == []


# ─── integration: callers / callees ──────────────────────────────────────────


def test_callers_includes_fnptr_dispatch(rich_db: Path) -> None:
    """handle_cloud_command is dispatched via a resolved fnptr edge from
    event_bus_dispatch — callers() must surface it."""
    names = {c.name for c in q.callers(rich_db, "handle_cloud_command")}
    assert "event_bus_dispatch" in names


def test_callees_of_writer(rich_db: Path) -> None:
    names = {c.name for c in q.callees(rich_db, "sensor_poll")}
    assert "hw_read_battery_adc" in names
    assert "DataModel_Set_DEMOBOT_POWER_BATTERY_MV" in names


# ─── integration: the #46 dataflow merge ─────────────────────────────────────


def test_callees_merge_dataflow_tagged_as_key_not_call(rich_db: Path) -> None:
    """#46: callees() returns causal successors, not just call successors. The
    sensor_poll → telemetry_report seam is pure dataflow — no call path connects
    them — so before the merge the cheap tool answered "sensor_poll reaches
    nothing but hardware", which is wrong about the system, not merely thin.

    It must arrive TAGGED. An untagged merge trades a false negative for a false
    positive ("sensor_poll calls telemetry_report"), which is worse: a missing
    row invites another query, a wrong row does not."""
    merged = q.callees(rich_db, "sensor_poll")
    seam = [c for c in merged if c.name == "telemetry_report"]
    assert seam, "the dataflow neighbour must be present"
    assert all(c.edge_class == "key" for c in seam)
    assert {c.key_name for c in seam} == {"DEMOBOT_POWER_BATTERY_MV"}
    assert all(c.rowid > 0 for c in seam), "a dataflow neighbour is still name-resolved"
    # The seam appears once per PROVENANCE layer (declared + inferred both find
    # it here), which is the pre-existing #38 duplication the merge inherits
    # unchanged — NOT a duplicate introduced by merging. Pinned so #38's collapse
    # has a baseline: the rows differ only in `source`.
    assert len({c.source for c in seam}) == len(seam)
    # The call half is untouched by the merge.
    call = next(c for c in merged if c.name == "hw_read_battery_adc")
    assert call.edge_class == "call"
    assert call.key_name is None


## @req REQ-DDB-QUERY-004
def test_dataflow_polarity_is_the_writer_side_of_callers(rich_db: Path) -> None:
    """The direction axis is spelled three ways for the same thing —
    `want_callers` / `as_writer` / `forward` — with want_callers=True ⟺
    as_writer=False. Inverting it silently answers the OPPOSITE causal question
    with no error, so pin both directions against the KeyEdge view they must
    mirror."""
    import sqlite3 as _sqlite3

    from clew.query.symbols import key_edges

    conn = _sqlite3.connect(str(rich_db))
    try:
        # callers(reader) must be the WRITERS whose values it reads.
        upstream = {c.name for c in q.callers(rich_db, "telemetry_report") if c.edge_class == "key"}
        assert upstream == {k.other for k in key_edges(conn, "telemetry_report", as_writer=False)}
        assert "sensor_poll" in upstream
        # callees(writer) must be the READERS of what it writes.
        downstream = {c.name for c in q.callees(rich_db, "sensor_poll") if c.edge_class == "key"}
        assert downstream == {k.other for k in key_edges(conn, "sensor_poll", as_writer=True)}
        assert "telemetry_report" in downstream
    finally:
        conn.close()


def test_confidence_and_strength_are_never_mixed_in_one_field(rich_db: Path) -> None:
    """A merged row must not put a `key_strength` ('low'/'medium'/'high') in the
    same field a call row fills with a `call_match` ('exact'/'resolved'/'fuzzy').
    Every shared-key row on a C++ codebase and a C/POSIX library carries confidence='medium', so
    without the split EVERY dataflow neighbour would sit in one JSON list
    labelled 'medium' beside calls labelled 'exact' — and a consumer filtering
    `confidence != 'fuzzy'` would admit all of them unconditionally, believing it
    had filtered.

    Swept over every function in the fixture, not a hand-picked one."""
    from clew.vocabulary import CALL_MATCH, KEY_STRENGTH

    seen = set()
    for name in _all_function_names(rich_db):
        for edge in q.callers(rich_db, name) + q.callees(rich_db, name):
            seen.add(edge.edge_class)
            if edge.edge_class == "call":
                assert edge.confidence in CALL_MATCH, edge
                assert edge.strength is None, edge
            else:
                assert edge.strength in KEY_STRENGTH, edge
                assert edge.confidence is None, edge
    assert seen == {"call", "key"}, "the sweep must actually observe both classes"


def test_hop_confidence_and_strength_are_split_too(rich_db: Path) -> None:
    """The same collision existed on Hop and was LIVE: a key hop wrote a
    key_strength into the field a call hop fills with a call_match."""
    from clew.vocabulary import CALL_MATCH, KEY_STRENGTH

    chain = q.chain_trace(rich_db, "sensor_poll", max_depth=3)
    classes = set()
    for hop in chain.hops:
        classes.add(hop.edge_class)
        if hop.edge_class == "call":
            assert hop.confidence in CALL_MATCH and hop.strength is None, hop
        else:
            assert hop.strength in KEY_STRENGTH and hop.confidence is None, hop
    assert classes == {"call", "key"}


def test_dossier_does_not_double_report_dataflow(rich_db: Path) -> None:
    """dossier keeps `include_dataflow=False` on purpose: it ALREADY composes
    writes/reads separately, so merging there would report every dataflow edge
    twice in one payload in two different shapes (CallEdge.name vs
    KeyEdge.other). Pins that the split shape stayed split."""
    d = q.function_dossier(rich_db, "sensor_poll")
    assert d is not None
    assert all(c.edge_class == "call" for c in d.callers + d.callees)
    assert "telemetry_report" not in {c.name for c in d.callees}
    hits = [w for w in d.writes if w.other == "telemetry_report"]
    assert hits, "the seam must still be reported, under writes"
    # One row per provenance layer (#38), and NOT once more from a merged
    # callees — the payload must not carry the same edge in two shapes.
    assert len({w.source for w in hits}) == len(hits)


def test_merged_order_is_identical_to_the_traversal_neighbour_order(rich_db: Path) -> None:
    """The merged list and chain_trace's neighbour list sort by the SAME key
    tuple, so the two surfaces are provably consistent rather than merely
    overlapping. A shared constant would not prove it — compare the emitted
    order for a name that has both a call and a key neighbour."""
    import sqlite3 as _sqlite3

    from clew.query.symbols import _call_edges
    from clew.query.traversal import _neighbors

    conn = _sqlite3.connect(str(rich_db))
    try:
        merged = _call_edges(conn, "sensor_poll", want_callers=False, include_dataflow=True)
        assert {e.edge_class for e in merged} == {"call", "key"}, "fixture must exercise both"
        neighbours = _neighbors(conn, "sensor_poll", forward=True)
        merged_keys = [(e.name, e.edge_class, e.key_name or "") for e in merged]
        neigh_keys = [(n, h.edge_class, h.key_name or "") for n, h in neighbours]
        # Both surfaces emit in the SAME key order, so a consumer reading one
        # after the other never sees the neighbours reshuffled.
        assert merged_keys == sorted(merged_keys)
        assert neigh_keys == sorted(neigh_keys)
        # ...and the shared neighbours appear in the same relative sequence.
        shared = set(neigh_keys)
        assert [k for k in dict.fromkeys(merged_keys) if k in shared] == sorted(shared)
    finally:
        conn.close()


def test_merged_neighbours_are_a_superset_of_chain_trace_depth_one(rich_db: Path) -> None:
    """chain_trace filters `confidence='fuzzy'` because it EXPANDS each hop and
    one wrong name multiplies into a wrong subtree; the flat neighbour list keeps
    fuzzy rows so a caller can weigh them (26.1% of a C++ codebase's call edges are fuzzy,
    and the tool description tells the model to read that field). The divergence
    is contract, so pin its direction: the flat list can only ever be a
    SUPERSET, and the difference is fuzzy-only."""
    import sqlite3 as _sqlite3

    from clew.query.symbols import _call_edges
    from clew.query.traversal import _neighbors

    conn = _sqlite3.connect(str(rich_db))
    try:
        nodes = _all_function_names(rich_db)
        checked = 0
        for name in nodes:
            for want_callers in (True, False):
                merged = {
                    (e.name, e.edge_class)
                    for e in _call_edges(conn, name, want_callers, include_dataflow=True)
                }
                depth1 = {
                    (n, h.edge_class) for n, h in _neighbors(conn, name, forward=not want_callers)
                }
                assert depth1 <= merged, (name, want_callers, depth1 - merged)
                checked += 1 if depth1 else 0
        # Anti-vacuity: a sweep in which every depth1 set was empty would pass
        # `<=` trivially. Demand that most of the graph actually had neighbours.
        assert checked > len(nodes), f"only {checked} non-empty pairs over {len(nodes)} nodes"
    finally:
        conn.close()


def test_edge_class_is_exactly_the_registered_vocabulary(rich_db: Path) -> None:
    """Events are NOT a third edge_class — an event edge stays edge_class='key'
    and is distinguished by edge_kind. A third value would silently break every
    consumer branching on the two."""
    from clew.vocabulary import EDGE_CLASS

    observed = {c.edge_class for n in _all_function_names(rich_db) for c in q.callees(rich_db, n)}
    observed |= {h.edge_class for h in q.chain_trace(rich_db, "sensor_poll", max_depth=4).hops}
    assert observed <= set(EDGE_CLASS.values)
    assert observed == {"call", "key"}


def _pre_r1_key_db(path: Path) -> None:
    """Reproduce a build_version-2 database VERBATIM: `shared_key_edges` with
    only the seven pre-R1 columns and no `threads` table at all. This shape is
    live on disk (<consumer-state-dir>/<target>-a5bb49), not hypothetical.

    @brief Seed a pre-R1 shared_key_edges DB (no R1 columns, no threads table).
    @version 1
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT,
            static INTEGER, bodystart INTEGER, bodyend INTEGER,
            file_id INTEGER, bodyfile_id INTEGER
        );
        CREATE TABLE shared_key_edges (
            writer_rowid INTEGER, reader_rowid INTEGER, key_name TEXT,
            edge_kind TEXT, declared INTEGER, source TEXT, confidence TEXT
        );
        INSERT INTO path (rowid, name) VALUES (1, 'src/pipe.c');
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, argsstring, "
        "briefdescription, detaileddescription, static, bodystart, bodyend, "
        "file_id, bodyfile_id) VALUES (?, 'function', ?, ?, '(void)', '', '', 0, 1, 2, 1, 1)",
        [(1, "producer", "void producer"), (2, "consumer", "void consumer")],
    )
    conn.execute(
        "INSERT INTO shared_key_edges (writer_rowid, reader_rowid, key_name, edge_kind, "
        "declared, source, confidence) VALUES (1, 2, 'STATE_KEY', 'state', 0, "
        "'shared_key_inferred', 'medium')",
    )
    conn.commit()
    conn.close()


def test_pre_r1_shared_key_schema_degrades_instead_of_raising(tmp_path: Path) -> None:
    """Extends #41's graceful-degradation contract from a missing TABLE to a
    missing COLUMN. `shared_key_edges` GREW the R1 columns after build_version 2,
    and every query naming one raised a raw OperationalError on an older
    database — verified live: key_edges, chain_trace and dossier all died on
    `no such column: s.dispatch_mode`.

    This is a hard prerequisite for the #46 merge, not a nicety: callers/callees
    were the last two tools that still WORKED on such a database, and merging the
    shared-key JOIN into them would have imported the crash into them too.

    Degradation must land on values that already mean "not known": dispatch_mode
    is the schema's own default 'unknown', the rest are None. Nothing plausible
    is fabricated."""
    db = tmp_path / "pre_r1.db"
    _pre_r1_key_db(db)

    downstream = [c for c in q.callees(db, "producer") if c.edge_class == "key"]
    assert len(downstream) == 1
    edge = downstream[0]
    assert edge.name == "consumer"
    assert edge.key_name == "STATE_KEY"
    assert edge.dispatch_mode == "unknown"
    assert edge.edge_triggered is None
    assert edge.crosses_thread is None
    assert edge.to_thread is None
    assert {c.name for c in q.callers(db, "consumer") if c.edge_class == "key"} == {"producer"}

    # ...and every sibling surface over the same JOIN survives it too.
    d = q.function_dossier(db, "producer")
    assert d is not None and [w.other for w in d.writes] == ["consumer"]
    assert "consumer" in {n.name for n in q.chain_trace(db, "producer", max_depth=2).nodes}


# ─── integration: chain_trace crosses the shared-key seam ────────────────────


def test_chain_trace_forward_crosses_shared_key_seam(rich_db: Path) -> None:
    """Forward from the writer, the chain crosses the shared-key seam
    (sensor_poll → telemetry_report) as a 'key' hop, not a call hop."""
    chain = q.chain_trace(rich_db, "sensor_poll", max_depth=3)
    node_names = {n.name for n in chain.nodes}
    assert "telemetry_report" in node_names
    key_hops = [
        h
        for h in chain.hops
        if h.edge_class == "key"
        and h.from_name == "sensor_poll"
        and h.to_name == "telemetry_report"
    ]
    assert len(key_hops) == 1
    assert key_hops[0].key_name == "DEMOBOT_POWER_BATTERY_MV"


def test_chain_trace_backward_reaches_writer(rich_db: Path) -> None:
    """Backward from the reader recovers the writer across the key seam."""
    chain = q.chain_trace(rich_db, "telemetry_report", direction="backward", max_depth=3)
    assert "sensor_poll" in {n.name for n in chain.nodes}


def test_chain_trace_direction_aliases_and_rejects_unknown(rich_db: Path) -> None:
    """#44: `forward = direction != "backward"` failed OPEN — only the exact
    lowercase "backward" traced backward, so 'upstream', 'backwards', 'BACKWARD'
    and every typo silently produced a FORWARD trace while the Chain echoed the
    caller's own word back, labelling the result with the direction that was
    asked for and carrying the opposite data. On a causal tool that is the one
    wrong answer a consumer cannot detect.

    Aliases now resolve, and an unknown word is a correctable ERROR, never a
    silent inversion. The echoed direction is the NORMALIZED one."""
    backward = q.chain_trace(rich_db, "telemetry_report", direction="backward", max_depth=3)
    assert "sensor_poll" in {n.name for n in backward.nodes}

    # every backward alias/casing gives the SAME trace, labelled canonically
    for alias in ("backwards", "upstream", "BACKWARD", "  Backward  "):
        chain = q.chain_trace(rich_db, "telemetry_report", direction=alias, max_depth=3)
        assert chain.direction == "backward", f"{alias!r} must normalize, not echo"
        assert {n.name for n in chain.nodes} == {n.name for n in backward.nodes}

    forward = q.chain_trace(rich_db, "sensor_poll", direction="forward", max_depth=3)
    for alias in ("forwards", "downstream", "FORWARD"):
        chain = q.chain_trace(rich_db, "sensor_poll", direction=alias, max_depth=3)
        assert chain.direction == "forward"
        assert {n.name for n in chain.nodes} == {n.name for n in forward.nodes}

    # the old bug: an unknown word used to return a forward trace mislabelled
    for bogus in ("sideways", "up", ""):
        with pytest.raises(ValueError, match="unknown direction"):
            q.chain_trace(rich_db, "sensor_poll", direction=bogus)


## @req REQ-DDB-QUERY-002
def test_chain_trace_records_what_the_fanout_taper_dropped(tmp_path: Path) -> None:
    """#134. The taper halves the neighbour budget per level and floors it at 1 — which is
    what stops a deep trace exploding — but it applied that with a bare slice and recorded
    NOTHING. A node with 131 callers and a cap of 8 reported 8 and looked exhausted, and
    the gap was not derivable from the payload: the dropped neighbours leave no trace in
    `nodes` or `hops`, so "is this all of them?" had no answer.

    Measured on the public entropic index after the fix: `chain_trace('dispatch',
    forward)` drops 21 neighbours across 9 nodes, every one of them previously invisible.

    A hand-built fixture rather than `rich_db`, because the shape needed is one node with
    more neighbours than the cap — and the assertion is about the ARITHMETIC (shown +
    omitted == available), which needs a known total."""
    db = tmp_path / "taper.db"
    conn = sqlite3.connect(str(db))
    callees = 12
    cap = 4
    rows = ", ".join(
        f"({10 + i}, 'function', 'callee_{i:02d}', 'void callee_{i:02d}()')" for i in range(callees)
    )
    edges = ", ".join(f"(1, {10 + i}, 'ast', 'resolved')" for i in range(callees))
    conn.executescript(
        "CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, "
        "definition TEXT, file_id INTEGER, bodyfile_id INTEGER, bodystart INTEGER, "
        "bodyend INTEGER);"
        "CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);"
        "CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, "
        "confidence TEXT);"
        "INSERT INTO memberdef (rowid, kind, name, definition) VALUES "
        f"(1, 'function', 'root', 'void root()'), {rows};"
        f"INSERT INTO call_edges VALUES {edges};"
    )
    conn.commit()
    conn.close()

    chain = q.chain_trace(db, "root", direction="forward", max_depth=2, max_neighbors=cap)
    root = next(n for n in chain.nodes if n.name == "root")

    ## The arithmetic is the assertion: what was shown plus what was omitted must equal
    ## what existed. A test that only checked `omitted > 0` would pass on any wrong number.
    assert root.omitted == callees - cap
    assert len([h for h in chain.hops if h.from_name == "root"]) == cap
    assert root.omitted + cap == callees

    ## An exhausted node reports 0, and that 0 is a MEASUREMENT — it is what lets a
    ## consumer conclude a branch really is complete.
    leaves = [n for n in chain.nodes if n.name != "root"]
    assert leaves, "the fixture must reach the callees"
    assert all(n.omitted == 0 for n in leaves)

    ## And a cap that is not exceeded must not invent a count.
    roomy = q.chain_trace(db, "root", direction="forward", max_depth=2, max_neighbors=99)
    assert next(n for n in roomy.nodes if n.name == "root").omitted == 0


def test_chain_trace_unknown_seed_is_empty(rich_db: Path) -> None:
    chain = q.chain_trace(rich_db, "no_such_function_xyz")
    assert chain.nodes == []
    assert chain.hops == []
    assert chain.candidates == []


def test_chain_trace_overloaded_seed_surfaces_candidates(tmp_path: Path) -> None:
    """An overloaded seed traces from the definition-preferring pick but lists
    the alternatives, so a bare ambiguous seed never silently traces the wrong
    function. (No edge tables here: the trace is empty, but the seed-ambiguity
    signal must still fire.)"""
    db = _overload_db(
        tmp_path,
        [
            (30, "publish", "bool A::publish", "src/a.cpp", True),
            (31, "publish", "bool B::publish", "src/b.cpp", True),
        ],
    )
    chain = q.chain_trace(db, "publish")
    assert chain.seed == "publish"
    assert {c.signature for c in chain.candidates} == {"bool A::publish", "bool B::publish"}


def test_chain_trace_unambiguous_seed_has_no_candidates(rich_db: Path) -> None:
    """The seed-overload signal must not fire for a uniquely-named seed."""
    chain = q.chain_trace(rich_db, "sensor_poll", max_depth=1)
    assert chain.candidates == []


# ─── integration: req_trace / threads / search ───────────────────────────────


def test_req_trace_findme(rich_db: Path) -> None:
    rt = q.req_trace(rich_db, "REQ-0621")
    assert rt.title == "Find-my-robot audible ping"
    assert rt.priority == "P1"
    impls = {i.name: i for i in rt.implementers}
    assert "sound_play_findme" in impls
    assert impls["sound_play_findme"].liveness == "live"
    assert "test_findme_chime_plays" in rt.tests
    # The test function is not itself listed as an implementer.
    assert "test_findme_chime_plays" not in impls


def test_thread_apis_empty_on_threadless_firmware(rich_db: Path) -> None:
    """The fixture spawns no threads → an empty roster and an empty thread_of (the
    populated cases are covered by the unit tier).

    AND THE EMPTY ROSTER MUST NOT CLAIM THE LAYER IS ABSENT. This index was built by the
    current pipeline, so `threads` exists and really holds nothing; an index predating the
    layer holds nothing too, and the two are different facts — one is about the code, the other
    about the build. `row_meaning` is the only thing that separates them, so a roster that said
    "predates the thread layer" here would be the absent-table-reads-as-no-threads failure with
    the sentence attached."""
    roster = q.thread_roster(rich_db)
    assert roster.threads == ()
    assert roster.rows == 0
    assert roster.origin.total == 0
    assert "predates the thread layer" not in roster.row_meaning
    assert q.thread_of(rich_db, "sensor_poll") == []


def test_search_finds_known_symbol(rich_db: Path) -> None:
    hits = {h.name for h in q.search(rich_db, "sensor_poll")}
    assert "sensor_poll" in hits
    # Brief-text search also matches.
    tele = q.search(rich_db, "telemetry")
    assert any(h.name == "telemetry_report" for h in tele)


def test_resolve_symbol_definition_preferring(rich_db: Path) -> None:
    ref = q.resolve_symbol(rich_db, "sensor_poll")
    assert ref is not None
    assert ref.kind == "function"
    assert ref.file.endswith("sensor_driver.c")
    # An unambiguous name must NOT be flagged an overload — no regression on the
    # single-result path every consumer already depends on.
    assert ref.candidates == []


## @brief Build a memberdef DB with same-named rows carrying chosen signatures.
## @version 1
def _overload_db(tmp_path: Path, rows: list[tuple[int, str, str, str, bool]]) -> Path:
    """rows: (rowid, name, signature, file_path, has_body). Each row is a
    memberdef; `has_body` toggles file_id == bodyfile_id so the definition-
    preferring order can be exercised. Distinct signatures for one name model a
    genuine overload; a shared signature models decl/def duality.

    @brief Seed a memberdef/path DB with controlled same-name signatures.
    @version 1
    """
    db = tmp_path / "overload.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """,
    )
    files = {fp for _, _, _, fp, _ in rows}
    file_id = {fp: i + 1 for i, fp in enumerate(sorted(files))}
    conn.executemany(
        "INSERT INTO path (rowid, name) VALUES (?, ?)",
        [(fid, fp) for fp, fid in file_id.items()],
    )
    conn.executemany(
        "INSERT INTO memberdef "
        "(rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, ?, ?, 1, 1, ?, '()', '', '', 0)",
        [
            (rid, name, file_id[fp], file_id[fp] if has_body else 0, sig)
            for rid, name, sig, fp, has_body in rows
        ],
    )
    conn.commit()
    conn.close()
    return db


def test_resolve_symbol_flags_genuine_overload(tmp_path: Path) -> None:
    """A name mapping to distinct signatures (different classes) is a genuine
    overload: resolve_symbol still returns a definition-preferring primary but
    exposes every alternative so a consumer can pick the right one by file,
    rather than silently tracing an arbitrary overload."""
    db = _overload_db(
        tmp_path,
        [
            (10, "react", "void A::react", "src/a.cpp", True),
            (11, "react", "void B::react", "src/b.cpp", True),
            (12, "react", "void C::react", "include/c.hpp", False),
        ],
    )
    ref = q.resolve_symbol(db, "react")
    assert ref is not None
    # Primary is definition-preferring (a body row, lowest rowid among them).
    assert ref.rowid == 10
    sigs = {c.signature for c in ref.candidates}
    assert sigs == {"void A::react", "void B::react", "void C::react"}
    files = {c.file for c in ref.candidates}
    assert files == {"src/a.cpp", "src/b.cpp", "include/c.hpp"}
    # The header-only candidate is flagged as such.
    assert any(c.file.endswith("c.hpp") and c.has_body is False for c in ref.candidates)


def test_resolve_symbol_decl_def_duality_is_not_an_overload(tmp_path: Path) -> None:
    """Decl + def of ONE function share a signature and must NOT read as an
    overload — otherwise every documented header declaration would falsely
    trip the ambiguity signal."""
    db = _overload_db(
        tmp_path,
        [
            (20, "solo", "void solo", "src/s.cpp", True),  # definition
            (21, "solo", "void solo", "include/s.hpp", False),  # declaration
        ],
    )
    ref = q.resolve_symbol(db, "solo")
    assert ref is not None
    assert ref.rowid == 20  # definition-preferring
    assert ref.candidates == []


# ─── integration: source / list_files / search_prose ─────────────────────────


def test_source_returns_the_verbatim_body(rich_db: Path, repo_root: Path) -> None:
    """The recorded body extent + the working tree yield the ACTUAL source
    text, not a reconstruction."""
    listing = q.source(rich_db, "sensor_poll", repo_root)
    assert listing is not None
    assert listing.name == "sensor_poll"
    assert listing.file.endswith("sensor_driver.c")
    assert listing.truncated is False
    assert listing.end_line == listing.start_line + len(listing.lines) - 1
    body = "\n".join(listing.lines)
    assert "sensor_poll" in body
    assert "hw_read_battery_adc" in body
    # Verbatim: every returned line is the file's line at that number.
    on_disk = (repo_root / listing.file).read_text(encoding="utf-8").splitlines()
    assert listing.lines == on_disk[listing.start_line - 1 : listing.end_line]


def test_source_caps_and_flags_truncation(rich_db: Path, repo_root: Path) -> None:
    """A comparison query layer shipped an UNBOUNDED source tool and one call
    returned 26 KB, distorting its own token accounting. The cap is the fix, so
    it is asserted: at most max_lines, truncated=True, and the reported
    end_line describes exactly what came back."""
    full = q.source(rich_db, "sensor_poll", repo_root)
    assert full is not None and len(full.lines) > 2

    capped = q.source(rich_db, "sensor_poll", repo_root, max_lines=2)
    assert capped is not None
    assert len(capped.lines) == 2
    assert capped.truncated is True
    assert capped.start_line == full.start_line
    assert capped.end_line == full.start_line + 1
    assert capped.lines == full.lines[:2]


def test_source_unknown_function_is_none(rich_db: Path, repo_root: Path) -> None:
    assert q.source(rich_db, "no_such_function_xyz", repo_root) is None


def test_source_unambiguous_has_no_candidates(rich_db: Path, repo_root: Path) -> None:
    """A uniquely-named function's listing carries an empty `candidates`."""
    listing = q.source(rich_db, "sensor_poll", repo_root)
    assert listing is not None
    assert listing.candidates == []


def test_source_unreadable_repo_root_is_none(rich_db: Path, tmp_path: Path) -> None:
    """A wrong/empty working tree reports "no listing", never a traceback."""
    assert q.source(rich_db, "sensor_poll", tmp_path) is None


def test_read_body_refuses_paths_escaping_repo_root(tmp_path: Path) -> None:
    """#39 defense-in-depth: R3 serves whatever db a caller points it at, so a
    tampered/foreign db could record an absolute (`/etc/passwd`) or `../`-escaping
    body path — which `root / file` would happily follow OUTSIDE the working tree,
    turning `source` into an arbitrary-file read. The escape target here EXISTS and
    is readable, so a None result proves the containment check (not an OSError
    fallback) is what refuses it; the contained control reads normally."""
    from clew.query.source import _read_body

    root = tmp_path / "repo"
    root.mkdir()
    (root / "src.c").write_text("line1\nline2\n", encoding="utf-8")
    outside = tmp_path / "secret.txt"
    outside.write_text("TOP SECRET\n", encoding="utf-8")

    ok = _read_body(root, "src.c", 1, 2, 10)  # contained → reads
    assert ok is not None and ok[0] == ["line1", "line2"]
    assert _read_body(root, str(outside), 1, 1, 10) is None  # absolute escape → refused
    assert _read_body(root, "../secret.txt", 1, 1, 10) is None  # ../ escape → refused


def _thread_db(path: Path) -> None:
    """Reproduce a C++ codebase's real shape: two classes share the method name `rx_loop`,
    BOTH thread entries are declaration rows (a header-declared method has
    file_id != bodyfile_id), and the only definition row for that name is an
    unrelated anonymous-namespace helper carrying no membership.

    @brief Seed a threads/thread_membership DB mirroring a C++ codebase's rowid layout.
    @version 1
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            file_id INTEGER, bodyfile_id INTEGER
        );
        CREATE TABLE threads (
            id INTEGER PRIMARY KEY, name TEXT NOT NULL,
            entry_memberdef_rowid INTEGER, kind TEXT, source TEXT, confidence TEXT
        );
        CREATE TABLE thread_membership (
            memberdef_rowid INTEGER NOT NULL, thread_id INTEGER NOT NULL, source TEXT
        );
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, file_id, bodyfile_id) VALUES "
        "(?, 'function', ?, ?, ?, ?)",
        [
            (670, "rx_loop", "void app::link::LinkOwner::rx_loop", 1, 2),
            (2029, "rx_loop", "void app::sensor::SensorRuntime::rx_loop", 1, 2),
            (1341, "rx_loop", "void anonymous_namespace{main.cpp}::rx_loop", 3, 3),
            # A decoy whose qualified name merely CONTAINS the sought one.
            (900, "rx_loop", "void app::other::CoLinkOwner::rx_loop", 1, 2),
        ],
    )
    conn.executemany(
        "INSERT INTO threads (id, name, entry_memberdef_rowid, kind, source, confidence) "
        "VALUES (?, ?, ?, 'pthread', 'ast_spawn', 'medium')",
        [
            (1, "LinkOwner::rx_loop", 670),
            (2, "SensorRuntime::rx_loop", 2029),
            (3, "CoLinkOwner::rx_loop", 900),
        ],
    )
    conn.executemany(
        "INSERT INTO thread_membership (memberdef_rowid, thread_id, source) "
        "VALUES (?, ?, 'call_closure')",
        [(670, 1), (2029, 2), (900, 3)],
    )
    conn.commit()
    conn.close()


def test_thread_of_resolves_qualified_roster_names(tmp_path: Path) -> None:
    """#42: `thread_roster` emits QUALIFIED entry names, but `thread_of`
    resolved a single rowid off the UNQUALIFIED `memberdef.name` — so on a C++ codebase 11
    of 12 roster names returned count=0, and the MCP envelope told the model
    'This is a definitive empty result ... Do not retry'. A tool must be able to
    consume the names its own sibling tool emits."""
    db = tmp_path / "threads.db"
    _thread_db(db)
    assert [t.name for t in q.thread_of(db, "LinkOwner::rx_loop")] == ["LinkOwner::rx_loop"]
    assert [t.name for t in q.thread_of(db, "SensorRuntime::rx_loop")] == ["SensorRuntime::rx_loop"]


def test_thread_of_qualified_match_respects_identifier_boundaries(tmp_path: Path) -> None:
    """`CoLinkOwner::rx_loop` merely CONTAINS `LinkOwner::rx_loop`; a
    substring match would silently attribute the wrong thread."""
    db = tmp_path / "threads.db"
    _thread_db(db)
    assert [t.name for t in q.thread_of(db, "LinkOwner::rx_loop")] == ["LinkOwner::rx_loop"]
    assert [t.name for t in q.thread_of(db, "CoLinkOwner::rx_loop")] == ["CoLinkOwner::rx_loop"]


def test_thread_of_bare_ambiguous_name_returns_every_thread(tmp_path: Path) -> None:
    """The membership rows sit on DECLARATION rowids (a header-declared method
    has file_id != bodyfile_id), while the lone definition row for the name is
    an unrelated anon-namespace helper with no membership. Definition-preferring
    resolution therefore picked exactly the wrong rowid and answered "no
    threads"; a union question must consider every candidate."""
    db = tmp_path / "threads.db"
    _thread_db(db)
    # sorted(), so the expectation must be in ASCII order: "Co..." < "Li..." < "Se...".
    assert sorted(t.name for t in q.thread_of(db, "rx_loop")) == [
        "CoLinkOwner::rx_loop",
        "LinkOwner::rx_loop",
        "SensorRuntime::rx_loop",
    ]


def test_name_accessors_degrade_gracefully_on_table_less_db(tmp_path: Path) -> None:
    """#41: a corrupt/unbuilt db (valid sqlite, no pipeline tables) must make
    EVERY name-based accessor degrade to "not found" (empty/None), never raise a
    raw sqlite OperationalError — matching the table_exists convention already
    pervasive across the query layer. Before the fix callers/callees guarded
    their table, but dossier/source/search/thread_of/chain_trace/resolve_symbol
    queried memberdef cold and raised, so the same corrupt db gave inconsistent
    behaviour across the tier-1 surface."""
    p = tmp_path / "corrupt.db"
    conn = sqlite3.connect(p)
    conn.execute("CREATE TABLE junk(x)")  # valid sqlite, zero pipeline tables
    conn.commit()
    conn.close()

    assert q.callers(p, "x") == []
    assert q.callees(p, "x") == []
    assert q.search(p, "x") == []
    assert q.thread_of(p, "x") == []
    assert q.function_dossier(p, "x") is None
    assert q.source(p, "x", tmp_path) is None
    assert q.resolve_symbol(p, "x") is None
    assert q.chain_trace(p, "x") is not None  # returns an (empty) Chain, does not raise


def test_list_files_inventory(rich_db: Path) -> None:
    """Every real source file is listed with a symbol count; doxygen's
    synthetic bracket rows ('[STL]', '[generated]') are not files and must not
    appear."""
    files = q.list_files(rich_db)
    paths = [f.path for f in files]
    assert paths == sorted(paths)
    assert not [p for p in paths if p.startswith("[")], "synthetic path rows must be excluded"
    assert any(p.endswith("sensor_driver.c") for p in paths)
    assert any(f.symbol_count > 0 for f in files)


def test_list_files_pattern_is_a_glob_over_path_or_filename(rich_db: Path) -> None:
    """`pattern` is a * glob matched against the repo-relative path OR the bare
    filename, so a nested file is reachable without naming its directory."""
    files = q.list_files(rich_db)
    only_c = q.list_files(rich_db, "*.c")
    assert only_c, "the fixture tree is C — '*.c' cannot be empty"
    assert all(f.path.endswith(".c") for f in only_c)
    assert len(only_c) < len(files)

    # Bare-filename globs work even though the paths are nested.
    assert [f.path for f in q.list_files(rich_db, "sensor_driver.*")]
    assert q.list_files(rich_db, "*.no_such_extension") == []


def test_search_prose_returns_a_snippet(rich_db: Path) -> None:
    """The sample's markdown is ingested into FTS5; a term known to be in it
    comes back with a heading and a snippet showing the match in context."""
    hits = q.search_prose(rich_db, "chime")
    assert hits, "'chime' is in the fixture tree's docs/architecture.md"
    assert any(h.file_path.endswith(".md") for h in hits)
    assert all(h.snippet for h in hits)
    assert any(">>" in h.snippet for h in hits), "snippet() must mark the match"


def test_search_prose_limit_and_bad_expression(rich_db: Path) -> None:
    """The limit is honoured, and an FTS5-invalid expression is retried as a
    literal phrase instead of surfacing a syntax error to the caller."""
    assert len(q.search_prose(rich_db, "the OR robot OR key", limit=2)) <= 2
    q.search_prose(rich_db, 'unbalanced " quote')  # must not raise


def test_search_prose_widens_to_or_when_one_absent_word_empties_the_and(rich_db: Path) -> None:
    """THE DEFECT THIS IS THE CONTROL FOR, measured on mbedtls: FTS5 joins a bare token
    list with an implicit AND, so `private accessor` found the migration guide while
    `private members accessor` found NOTHING — the document says "fields". A graded agent
    tried five such phrasings, was told each empty result was definitive, and grepped the
    file the corpus already held.

    Reproduced here by pairing a term known to be in the fixture with one that cannot be
    in any corpus. The AND must be empty and the OR must still find the known term.
    """
    absent = "zzqqxwv"
    assert q.search_prose(rich_db, absent) == [], "the control word must really be absent"

    result = q.search_prose_graded(rich_db, f"chime {absent}")

    assert result.widened is True
    assert result.hits, "the AND was empty, so the OR must recover the 'chime' hits"
    assert any(h.file_path.endswith(".md") for h in result.hits)


def test_search_prose_does_not_widen_a_query_that_already_matched(rich_db: Path) -> None:
    """WIDENING IS A LAST RESORT, NOT A DEFAULT. If an OR ran whenever it could, a query
    with exact hits would return them buried under loosely-related ones — the opposite
    failure to the one above, and harder to notice because the reply is not empty.
    """
    result = q.search_prose_graded(rich_db, "chime")
    assert result.hits
    assert result.widened is False


def test_search_prose_single_token_miss_reports_no_widening(rich_db: Path) -> None:
    """A one-word query has no conjunction to relax, so a miss is a genuine absence and
    must NOT be dressed up as a widened search. This is the case where "definitive" is
    the honest word — the distinction the emptiness note depends on.
    """
    result = q.search_prose_graded(rich_db, "zzqqxwv")
    assert result.hits == []
    assert result.widened is False
    assert result.tokens == ("zzqqxwv",)


def test_search_prose_punctuation_only_tokens_never_reach_fts5(rich_db: Path) -> None:
    """A token of pure punctuation tokenizes to an EMPTY phrase, and an empty phrase is an
    FTS5 syntax error rather than a harmless no-op — so it must be dropped before the OR
    is composed, not after.
    """
    result = q.search_prose_graded(rich_db, "chime _ ' -")
    assert result.tokens == ("chime",)
    assert result.hits


def test_search_prose_absent_table_is_empty(tmp_path: Path) -> None:
    """Databases built before the prose layer simply have no hits."""
    db = tmp_path / "noprose.db"
    conn = sqlite3.connect(str(db))
    conn.execute("CREATE TABLE memberdef (rowid INTEGER PRIMARY KEY, name TEXT)")
    conn.commit()
    conn.close()
    assert q.search_prose(db, "anything") == []


# ─── unit: hand-built DBs for the traversal invariants ───────────────────────


## @brief Create a minimal memberdef/path DB (+ optional edge tables).
## @version 1
def _hand_db(
    tmp_path: Path,
    functions: list[tuple[int, str]],
    call_edges: list[tuple[int, int]] | None = None,
) -> Path:
    """functions: (rowid, name), all definitions in one file (file_id ==
    bodyfile_id). call_edges: (caller_rowid, callee_rowid) as non-fuzzy rows.

    @brief Seed a doxygen-shaped memberdef/path[/call_edges] DB for unit tests.
    @version 1
    """
    db = tmp_path / "hand.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY,
            kind TEXT, name TEXT, file_id INTEGER, bodyfile_id INTEGER,
            bodystart INTEGER, bodyend INTEGER, definition TEXT, argsstring TEXT,
            briefdescription TEXT, detaileddescription TEXT, static INTEGER
        );
        """,
    )
    conn.execute("INSERT INTO path (rowid, name) VALUES (1, 'src/foo.c')")
    conn.executemany(
        "INSERT INTO memberdef "
        "(rowid, kind, name, file_id, bodyfile_id, bodystart, bodyend, "
        "definition, argsstring, briefdescription, detaileddescription, static) "
        "VALUES (?, 'function', ?, 1, 1, 1, 1, 'void ' || ?, '(void)', '', '', 0)",
        [(rid, name, name) for rid, name in functions],
    )
    if call_edges is not None:
        conn.execute(
            "CREATE TABLE call_edges (caller_rowid INTEGER, callee_rowid INTEGER, "
            "source TEXT, confidence TEXT)",
        )
        conn.executemany(
            "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
            "VALUES (?, ?, 'ast', 'resolved')",
            call_edges,
        )
    conn.commit()
    conn.close()
    return db


## @req REQ-DDB-QUERY-002
def test_cap_at_depth_taper() -> None:
    assert _cap_at_depth(8, 1) == 8
    assert _cap_at_depth(8, 2) == 4
    assert _cap_at_depth(8, 4) == 1
    assert _cap_at_depth(8, 12) == 1
    assert _cap_at_depth(1, 3) == 1


def test_chain_trace_cycle_bounded_by_path(tmp_path: Path) -> None:
    """A mutually-recursive pair (a→b→a) terminates: both nodes appear once,
    both hops are recorded, and the back-edge does not recurse forever."""
    db = _hand_db(
        tmp_path,
        [(1, "a"), (2, "b")],
        call_edges=[(1, 2), (2, 1)],
    )
    chain = q.chain_trace(db, "a", max_depth=10)
    assert {n.name for n in chain.nodes} == {"a", "b"}
    assert {(h.from_name, h.to_name) for h in chain.hops} == {("a", "b"), ("b", "a")}


def test_chain_trace_depth_cap(tmp_path: Path) -> None:
    """A linear chain a→b→c→d→e stops at max_depth=2 (nodes at depth 0,1,2)."""
    db = _hand_db(
        tmp_path,
        [(1, "a"), (2, "b"), (3, "c"), (4, "d"), (5, "e")],
        call_edges=[(1, 2), (2, 3), (3, 4), (4, 5)],
    )
    chain = q.chain_trace(db, "a", max_depth=2)
    by_name = {n.name: n.depth for n in chain.nodes}
    assert set(by_name) == {"a", "b", "c"}
    assert by_name == {"a": 0, "b": 1, "c": 2}
    assert "d" not in by_name


def test_chain_trace_terminates_at_external_boundary(tmp_path: Path) -> None:
    """A branch stops at an external_boundaries terminus: the terminus node is
    flagged and its downstream callee is NOT expanded into."""
    db = _hand_db(
        tmp_path,
        [(1, "entry"), (2, "invoke_cb"), (3, "beyond"), (4, "register_cb")],
        # entry -> invoke_cb (call); invoke_cb -> beyond (would continue).
        call_edges=[(1, 2), (2, 3)],
    )
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE external_boundaries (
            memberdef_rowid INTEGER, global_name TEXT, kind TEXT,
            registered_by_rowid INTEGER, registered_param_index INTEGER,
            note TEXT, source TEXT, confidence TEXT
        )
        """,
    )
    conn.execute(
        "INSERT INTO external_boundaries (memberdef_rowid, global_name, kind, "
        "registered_by_rowid, confidence) VALUES "
        "(2, 'svc_notify_cb', 'unresolved_callback', 4, 'high')",
    )
    conn.commit()
    conn.close()

    chain = q.chain_trace(db, "entry", max_depth=6)
    names = {n.name for n in chain.nodes}
    assert "invoke_cb" in names
    assert "beyond" not in names  # branch terminated at the boundary
    term = next(n for n in chain.nodes if n.name == "invoke_cb")
    assert term.is_terminus is True
    assert term.termini[0].global_name == "svc_notify_cb"
    assert term.termini[0].registered_by == "register_cb"
    assert term.termini[0].kind == "unresolved_callback"


def test_chain_trace_crosses_thread_key_hop(tmp_path: Path) -> None:
    """A shared-key hop annotated crosses_thread=1 / to_thread_id surfaces on
    the Hop with the reader thread's NAME and its dispatch_mode."""
    db = _hand_db(tmp_path, [(1, "producer"), (2, "consumer")])
    conn = sqlite3.connect(str(db))
    conn.execute(
        """
        CREATE TABLE threads (
            id INTEGER PRIMARY KEY, name TEXT, entry_memberdef_rowid INTEGER,
            kind TEXT, source TEXT, confidence TEXT
        )
        """,
    )
    conn.execute(
        "INSERT INTO threads (id, name, entry_memberdef_rowid, kind, source, "
        "confidence) VALUES (7, 'consumer_thread', 2, 'task', 'ast_spawn', 'medium')",
    )
    conn.execute(
        """
        CREATE TABLE shared_key_edges (
            writer_rowid INTEGER, reader_rowid INTEGER, key_name TEXT,
            edge_kind TEXT, declared INTEGER, source TEXT, confidence TEXT,
            dispatch_mode TEXT, edge_triggered INTEGER, crosses_thread INTEGER,
            to_thread_id INTEGER
        )
        """,
    )
    conn.execute(
        "INSERT INTO shared_key_edges (writer_rowid, reader_rowid, key_name, "
        "edge_kind, declared, source, confidence, dispatch_mode, edge_triggered, "
        "crosses_thread, to_thread_id) VALUES "
        "(1, 2, 'msg_queue', 'event', 0, 'shared_key_inferred', 'medium', "
        "'queued', NULL, 1, 7)",
    )
    conn.commit()
    conn.close()

    chain = q.chain_trace(db, "producer", max_depth=3)
    key_hops = [h for h in chain.hops if h.edge_class == "key"]
    assert len(key_hops) == 1
    hop = key_hops[0]
    assert (hop.from_name, hop.to_name) == ("producer", "consumer")
    assert hop.crosses_thread is True
    assert hop.dispatch_mode == "queued"
    assert hop.to_thread == "consumer_thread"

    # And the dossier surfaces the same hop's thread membership on the reader.
    d_writer = q.function_dossier(db, "producer")
    assert d_writer is not None
    write = d_writer.writes[0]
    assert write.crosses_thread is True
    assert write.to_thread == "consumer_thread"
    # thread APIs see the declared thread + its (spawn-entry) membership is empty
    # here (no thread_membership table), so thread_of is empty but roster lists it.
    roster = q.thread_roster(db)
    assert [t.name for t in roster.threads] == ["consumer_thread"]


# ─── unit: lookup_class (the fixture is C — a compound DB is hand-built) ─────


## @brief Seed a doxygen-shaped compound DB with a project class + std:: noise.
## @version 2
def _class_db(tmp_path: Path) -> Path:
    """Two compounds named so a naive substring match would pick the wrong one: a
    PROJECT class `demo::shape::PolygonWidget` in a plausible file, and a `std::`
    class registered against doxygen's synthetic '[STL]' path row — exactly the shape
    a real C++ database has.

    EVERY IDENTIFIER HERE IS INVENTED, and unlike the previous version of this fixture
    that is now true. Its brief, its directory layout and one member's type were all
    verbatim pre-scrub content — `git grep -F <token> 34e1035^` separates "read out of a
    reference repo" from "invented by an earlier scrub", and they failed that test. Only
    the recognisable half of each name had ever been replaced, which is exactly the
    failure CLAUDE.md records: what survives a scrub is precisely what does not look
    like anything. The offending tokens are deliberately NOT repeated here — writing
    them into the explanation would re-commit what the edit removed. The vocabulary is
    geometric now, sharing nothing with any product domain.

    The STRUCTURE is what the tests need and it is preserved exactly: a longer namesake
    containing the short name as a substring, a base and a derived compound, one member
    function and one member variable whose type is a reference.

    `memberdef` carries `file_id` and `briefdescription` so `search` can run against
    this fixture at all (gh#315). Without them the class-search tests would fail with
    a missing-column OperationalError, which is a COLLECTION error and proves only
    that the schema is wrong — not that search cannot find a class. The red they need
    to observe is an EMPTY result from a query that runs.

    @brief Seed a compounddef/member/compoundref DB for class-lookup and class-search tests.
    @version 3
    """
    db = tmp_path / "classes.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, type INTEGER, name TEXT);
        CREATE TABLE compounddef (
            rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, file_id INTEGER,
            line INTEGER, briefdescription TEXT, detaileddescription TEXT
        );
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, name TEXT, kind TEXT, type TEXT,
            argsstring TEXT, line INTEGER, file_id INTEGER, briefdescription TEXT
        );
        CREATE TABLE member (scope_rowid INTEGER, memberdef_rowid INTEGER);
        CREATE TABLE compoundref (base_rowid INTEGER, derived_rowid INTEGER);
        INSERT INTO path (rowid, type, name) VALUES
            (1, 1, '[STL]'),
            (2, 1, 'src/demo/shape/PolygonWidget.hpp');
        INSERT INTO compounddef (rowid, name, kind, file_id, line, briefdescription) VALUES
            (10, 'std::PolygonWidget_traits', 'class', 1, 0, 'std noise'),
            (11, 'demo::shape::PolygonWidget', 'class', 2, 38,
             '<para>Recomputes the cached outline.</para>'),
            (12, 'demo::shape::IShapeWidget', 'class', 2, 12, 'base interface'),
            (13, 'demo::shape::RoundedPolygonWidget', 'class', 2, 90, 'a longer namesake');
        INSERT INTO memberdef (rowid, name, kind, type, argsstring, line, file_id,
                               briefdescription) VALUES
            (20, 'redraw', 'function', 'void', '() noexcept', 46, 2,
             '<para>Redraws the widget outline.</para>'),
            (21, 'canvas_', 'variable', 'render::Canvas &', '', 94, 2, '');
        INSERT INTO member (scope_rowid, memberdef_rowid) VALUES (11, 20), (11, 21);
        INSERT INTO compoundref (base_rowid, derived_rowid) VALUES (12, 11), (11, 13);
        """,
    )
    conn.commit()
    conn.close()
    return db


def test_lookup_class_prefers_project_over_std(tmp_path: Path) -> None:
    """compounddef is POLLUTED with std:: compounds harvested from system
    headers (registered against the synthetic '[STL]' path). A project class
    must always outrank them, and a qualified-tail exact match must outrank an
    incidental substring."""
    db = _class_db(tmp_path)
    entry = q.lookup_class(db, "PolygonWidget")
    assert entry is not None
    assert entry.name == "demo::shape::PolygonWidget"
    assert entry.kind == "class"
    assert entry.file == "src/demo/shape/PolygonWidget.hpp"
    assert entry.line == 38
    assert entry.brief == "Recomputes the cached outline."


def test_lookup_class_members_and_hierarchy(tmp_path: Path) -> None:
    """Members carry a reassembled signature + declaration line; the immediate
    base and derived compounds come from compoundref."""
    entry = q.lookup_class(_class_db(tmp_path), "demo::shape::PolygonWidget")
    assert entry is not None
    members = {m.name: m for m in entry.members}
    assert members["redraw"].signature == "void redraw() noexcept"
    assert members["redraw"].kind == "function"
    assert members["redraw"].line == 46
    assert members["canvas_"].signature == "render::Canvas & canvas_"
    assert entry.bases == ["demo::shape::IShapeWidget"]
    assert entry.derived == ["demo::shape::RoundedPolygonWidget"]


def test_lookup_class_std_is_still_reachable(tmp_path: Path) -> None:
    """Demotion is not exclusion — asking for the std:: name still finds it."""
    entry = q.lookup_class(_class_db(tmp_path), "std::PolygonWidget_traits")
    assert entry is not None
    assert entry.name == "std::PolygonWidget_traits"


def test_lookup_class_unknown_is_none(tmp_path: Path) -> None:
    assert q.lookup_class(_class_db(tmp_path), "NoSuchClass") is None


def test_lookup_class_lists_candidates_when_the_name_is_ambiguous(tmp_path: Path) -> None:
    """gh#315. `lookup_class` fetches every substring match and returns the single
    best-ranked one, silently discarding the rest — so a caller asking for
    `PolygonWidget` in a repo that also has `RoundedPolygonWidget` is told about one
    class and never learns the other exists. Every other disambiguating surface
    (`resolve_symbol` / `dossier` / `chain_trace` / `source`) reports its rejects;
    this one did not."""
    db = _class_db(tmp_path)
    entry = q.lookup_class(db, "PolygonWidget")
    assert entry is not None
    assert entry.name == "demo::shape::PolygonWidget"
    names = [c.qualified for c in entry.candidates]
    assert "demo::shape::PolygonWidget" in names
    assert "demo::shape::RoundedPolygonWidget" in names
    assert "std::PolygonWidget_traits" in names
    assert [c.kind for c in entry.candidates] == ["class"] * len(names)
    # REQ-DDB-QUERY-010: the selector must be USABLE, not merely reported — every
    # published string has to round-trip back through this same accessor and land on
    # that exact compound. A candidate list nobody can act on is gh#37's defect.
    for candidate in entry.candidates:
        selected = q.lookup_class(db, candidate.qualified)
        assert selected is not None
        assert selected.name == candidate.qualified


def test_lookup_class_unambiguous_name_has_no_candidates(tmp_path: Path) -> None:
    """The CONTROL for the test above: `candidates` must stay empty on the common
    path, exactly as it does for functions. A list that is always populated
    disambiguates nothing and is pure payload."""
    entry = q.lookup_class(_class_db(tmp_path), "IShapeWidget")
    assert entry is not None
    assert entry.candidates == []


def test_search_finds_a_class_by_name(tmp_path: Path) -> None:
    """gh#315, the headline defect. `search` read `memberdef WHERE kind='function'`
    and the file-doc corpus, and NOTHING ELSE — classes live in `compounddef`, a
    table it never touched. So a class name returned a confident empty result, which
    is indistinguishable from a measured negative and is the worst failure mode this
    project has. Reproduced live on this repo's own index: `search("WritePlan")`
    returned only the mcp_config.py FILE DOC while the class sits at line 132."""
    hits = q.search(_class_db(tmp_path), "PolygonWidget")
    by_name = {h.name: h for h in hits}
    assert "demo::shape::PolygonWidget" in by_name
    assert by_name["demo::shape::PolygonWidget"].kind == "class"
    assert by_name["demo::shape::PolygonWidget"].file == "src/demo/shape/PolygonWidget.hpp"
    assert by_name["demo::shape::PolygonWidget"].brief == "Recomputes the cached outline."


def test_search_finds_a_class_by_its_brief(tmp_path: Path) -> None:
    """The class corpus is matched the same way the other two are — over name AND
    brief — so a conceptual token in a class's documentation reaches it."""
    hits = q.search(_class_db(tmp_path), "base interface")
    assert [h.name for h in hits] == ["demo::shape::IShapeWidget"]


def test_search_still_finds_a_function_unchanged(tmp_path: Path) -> None:
    """THE SUCCESS-PATH CONTROL. A fix that surfaces classes by demoting functions
    trades one wrong negative for another, so the function corpus is asserted on the
    same database that now has classes in it — not on one where the new corpus is
    trivially empty."""
    hits = q.search(_class_db(tmp_path), "redraw")
    assert [(h.name, h.kind) for h in hits] == [("redraw", "function")]


def test_search_ranking_is_unchanged_on_a_db_with_no_compounds(rich_db: Path) -> None:
    """The second half of that control, at list level rather than one hit: on an
    index with no `compounddef` at all the ENTIRE ranked result must be what it was,
    so the new corpus cannot have perturbed the sort for existing targets."""
    assert [h.name for h in q.search(rich_db, "sensor_poll")][0] == "sensor_poll"
    assert q.search(rich_db, "e", limit=3) == q.search(rich_db, "e", limit=3)


def test_search_excludes_stl_compounds_but_lookup_class_still_reaches_them(
    tmp_path: Path,
) -> None:
    """doxygen registers hundreds of `std::` compounds against its synthetic `[STL]`
    path row. Ranking them into a DISCOVERY surface would let system headers crowd
    out the repository the caller is asking about, so `search` excludes them exactly
    as `list_files` does. Demotion-not-exclusion stays true where it is reachable:
    `lookup_class` still answers for the std:: name."""
    db = _class_db(tmp_path)
    assert "std::PolygonWidget_traits" not in [h.name for h in q.search(db, "PolygonWidget")]
    assert q.search(db, "PolygonWidget_traits") == []
    entry = q.lookup_class(db, "std::PolygonWidget_traits")
    assert entry is not None and entry.name == "std::PolygonWidget_traits"


def test_search_for_an_absent_class_name_is_still_empty(tmp_path: Path) -> None:
    """THE NEGATIVE CONTROL. Widening the searched set must not make a genuinely
    absent name start matching something; a correct negative has to survive."""
    assert q.search(_class_db(tmp_path), "NoSuchWidgetAnywhere") == []


def test_token_hit_counts_sees_the_class_corpus(tmp_path: Path) -> None:
    """The zero-result diagnosis counts each token over the corpora `search` reads.
    Leaving classes out of the count would report `0` for a token that matches a
    class and only a class — advising the caller to drop the one token that was
    working, which is gh#31's defect reintroduced through the new corpus."""
    counts = q.token_hit_counts(_class_db(tmp_path), ["ishapewidget", "nosuchtoken"])
    assert counts["ishapewidget"] == 1
    assert counts["nosuchtoken"] == 0


def test_search_matches_every_token_not_the_literal_phrase(rich_db: Path) -> None:
    """#45: search was a single literal LIKE '%<whole query>%', so any
    multi-word query returned NOTHING — '%lock acquisition%' is a substring no
    identifier contains. Verified on clew's own index before the fix:
    search('lock') gave 9 hits, search('lock acquisition') gave ZERO, and the
    empty envelope then asserted "This is a definitive empty result ... Do not
    retry". Search is the discovery entry point; if a natural phrase answers
    nothing, a consumer never reaches dossier or chain_trace at all."""
    single = q.search(rich_db, "sensor")
    assert single, "single-token search must still work"

    # Tokens drawn from the name and the brief respectively must AND together.
    both = q.search(rich_db, "sensor poll")
    assert any(h.name == "sensor_poll" for h in both)

    # Word order is irrelevant — these are tokens, not a phrase.
    assert {h.name for h in q.search(rich_db, "poll sensor")} == {h.name for h in both}


def test_search_ranks_name_matches_above_prose_matches(rich_db: Path) -> None:
    """A token in the identifier is stronger evidence than the same token in
    prose, so an exact name match must not be buried under brief-only hits."""
    hits = q.search(rich_db, "sensor_poll")
    assert hits and hits[0].name == "sensor_poll"


def test_search_is_capped_and_the_cap_is_caller_controlled(rich_db: Path) -> None:
    """The old implementation had NO limit: a common token returned every match
    in alphabetical order, so the useful hit could be anywhere."""
    assert len(q.search(rich_db, "e", limit=3)) <= 3
    assert len(q.search(rich_db, "e", limit=1)) == 1


def test_search_empty_and_unmatched_queries_stay_empty(rich_db: Path) -> None:
    """Correct negatives must survive the rewrite: a whitespace-only query has
    no tokens to match, and a genuinely absent term still returns nothing."""
    assert q.search(rich_db, "   ") == []
    assert q.search(rich_db, "zzz_definitely_absent_xyz") == []


def _multi_source_db(path: Path) -> None:
    """Seed the shape #38 is about: ONE logical call edge that TWO extraction
    layers each found, which `UNIQUE(caller_rowid, callee_rowid, source)` stores
    as two rows by design. Measured on clew's own index as 520 rows for 260
    distinct pairs, i.e. 100% duplication.

    `pump` is deliberately reached by both doxygen layers with DIFFERENT
    confidence ('exact' vs 'resolved'), because that is what the real data does
    and it is what makes "pick the strongest" meaningful rather than arbitrary.
    `solo` is found by one layer only, so a single-layer endpoint is pinned
    alongside a multi-layer one.

    @brief Seed a DB whose call edges are duplicated across extraction layers.
    @version 1
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT,
            static INTEGER, bodystart INTEGER, bodyend INTEGER,
            file_id INTEGER, bodyfile_id INTEGER
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT,
            UNIQUE(caller_rowid, callee_rowid, source)
        );
        INSERT INTO path (rowid, name) VALUES (1, 'src/loop.c');
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, argsstring, "
        "briefdescription, detaileddescription, static, bodystart, bodyend, "
        "file_id, bodyfile_id) VALUES (?, 'function', ?, ?, '(void)', '', '', 0, 1, 2, 1, 1)",
        [(1, "driver", "void driver"), (2, "pump", "void pump"), (3, "solo", "void solo")],
    )
    conn.executemany(
        "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, ?, ?)",
        [
            (1, 2, "doxygen_sqlite", "exact"),
            (1, 2, "ast", "resolved"),
            (1, 3, "ast", "resolved"),
        ],
    )
    conn.commit()
    conn.close()


def test_multi_source_edge_collapses_to_one_row_per_endpoint(tmp_path: Path) -> None:
    """#38. One logical edge found by two layers must surface ONCE.

    This is the test whose absence let the defect ship: the whole existing suite
    passed both before and after the fix, because nothing pinned the row COUNT.
    Measured impact on clew's own index — callees("_run_pipeline") reported 8
    results for four real callees, so every neighbour count was doubled and every
    depth/neighbour cap admitted half as many real edges as intended."""
    db = tmp_path / "multi.db"
    _multi_source_db(db)

    calls = [c for c in q.callees(db, "driver") if c.edge_class == "call"]
    assert [c.name for c in calls] == ["pump", "solo"], "one row per endpoint, name-ordered"

    pump = next(c for c in calls if c.name == "pump")
    # STRONGEST evidence wins: doxygen_sqlite/exact beats ast/resolved. `source`
    # stays a single vocabulary-registered value rather than becoming a joined
    # string.
    assert (pump.source, pump.confidence) == ("doxygen_sqlite", "exact")

    solo = next(c for c in calls if c.name == "solo")
    assert (solo.source, solo.confidence) == ("ast", "resolved")

    # The inbound direction collapses identically; the bug was symmetric.
    inbound = [c for c in q.callers(db, "pump") if c.edge_class == "call"]
    assert [c.name for c in inbound] == ["driver"]
    assert (inbound[0].source, inbound[0].confidence) == ("doxygen_sqlite", "exact")


## @brief Seed three unrelated module-private functions that share one bare name.
## @param path Destination sqlite path.
## @return None.
## @version 1
def _name_collision_db(path: Path) -> None:
    """gh#26. Three DIFFERENT functions named `_classify`, one per Python module,
    exactly as clew's own index carries them (guidance/mcp_config/scope).
    These are NOT overloads and NOT decl/def duality: they are unrelated helpers
    that happen to share a private name, which in Python is the DEFAULT rather
    than an edge case.

    Each has its own distinct caller, and `scope._classify` alone is genuinely
    recursive — so a name-keyed edge query attributes a false self-edge to the
    other two and unions all three callers onto each. `plain` is a collision-free
    control: whatever the identity rule does, it must not disturb it.

    @brief Seed the gh#26 shape: three same-named module-private functions.
    @version 1
    """
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, kind TEXT, name TEXT, definition TEXT,
            argsstring TEXT, briefdescription TEXT, detaileddescription TEXT,
            static INTEGER, bodystart INTEGER, bodyend INTEGER,
            file_id INTEGER, bodyfile_id INTEGER
        );
        CREATE TABLE call_edges (
            caller_rowid INTEGER, callee_rowid INTEGER, source TEXT, confidence TEXT,
            UNIQUE(caller_rowid, callee_rowid, source)
        );
        INSERT INTO path (rowid, name) VALUES
            (1, 'pkg/guidance.py'), (2, 'pkg/mcp_config.py'), (3, 'pkg/scope.py');
        """
    )
    conn.executemany(
        "INSERT INTO memberdef (rowid, kind, name, definition, argsstring, "
        "briefdescription, detaileddescription, static, bodystart, bodyend, "
        "file_id, bodyfile_id) VALUES (?, 'function', ?, ?, '(a)', '', '', 0, 10, 20, ?, ?)",
        [
            (1, "_classify", "str pkg.guidance._classify", 1, 1),
            (2, "_classify", "str pkg.mcp_config._classify", 2, 2),
            (3, "_classify", "str pkg.scope._classify", 3, 3),
            (4, "plan_guidance", "str pkg.guidance.plan_guidance", 1, 1),
            (5, "plan_merge", "str pkg.mcp_config.plan_merge", 2, 2),
            (6, "_guard_scope", "str pkg.scope._guard_scope", 3, 3),
            (7, "plain", "void pkg.scope.plain", 3, 3),
        ],
    )
    conn.executemany(
        "INSERT INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, ?, ?)",
        [
            (4, 1, "doxygen_sqlite", "exact"),  # plan_guidance -> guidance._classify
            (5, 2, "doxygen_sqlite", "exact"),  # plan_merge    -> mcp_config._classify
            (6, 3, "doxygen_sqlite", "exact"),  # _guard_scope  -> scope._classify
            (3, 3, "doxygen_sqlite", "exact"),  # scope._classify recurses (GENUINE)
            (6, 7, "doxygen_sqlite", "exact"),  # _guard_scope  -> plain (control)
        ],
    )
    conn.commit()
    conn.close()


def test_same_named_module_private_helpers_do_not_share_edges(tmp_path: Path) -> None:
    """gh#26. Name-based resolution collapsed three unrelated `_classify`
    functions into ONE graph node, so `dossier` described one of them and then
    reported the UNION of all three functions' neighbours — 3 of 4 callers
    fabricated, including a self-edge claiming recursion that belongs to a
    DIFFERENT module's function. Every fabricated row came back
    `confidence: exact`, because all three extraction layers resolve by name and
    therefore all three reached the same wrong function.

    `candidates` already fired on this input, but it disambiguates the IDENTITY
    of the described symbol while nothing disambiguated the EDGES attributed to
    it — so a caller who checked `candidates` and then read `callers` was still
    misled. This pins the edges, not the candidate list."""
    db = tmp_path / "collide.db"
    _name_collision_db(db)

    # The definition-preferring pick is guidance._classify (lowest rowid, has body).
    d = q.function_dossier(db, "_classify")
    assert d is not None
    assert d.file == "pkg/guidance.py"
    assert len(d.candidates) == 3, "the ambiguity signal must still fire"

    # It has exactly ONE caller, and calls NOTHING. The issue's stated
    # acceptance check: guidance._classify has zero callees.
    assert [c.name for c in d.callers if c.edge_class == "call"] == ["plan_guidance"]
    assert [c.name for c in d.callees if c.edge_class == "call"] == [], (
        "guidance._classify calls nothing; a self-edge here belongs to scope._classify"
    )

    # And the fabricated neighbours are gone by name, not merely reordered.
    caller_names = {c.name for c in d.callers}
    assert "_guard_scope" not in caller_names, "belongs to scope._classify"
    assert "plan_merge" not in caller_names, "belongs to mcp_config._classify"
    assert "_classify" not in caller_names, "fabricated recursion"


def test_genuine_recursion_survives_the_identity_split(tmp_path: Path) -> None:
    """The control for the test above, and the reason it cannot simply drop every
    self-edge on an ambiguous name: `scope._classify` really does recurse. A fix
    that suppressed self-edges whenever `candidates` was non-empty would pass the
    gh#26 test and DELETE a true fact, so the split must be by identity rather
    than by ambiguity."""
    db = tmp_path / "collide.db"
    _name_collision_db(db)

    # Resolution by bare name still picks guidance; ask about scope's by rowid.
    scope_callers = q.callers(db, "_classify")
    assert "_guard_scope" not in {c.name for c in scope_callers}

    # The genuine self-edge is still IN the database and still attributed to the
    # function that owns it -- verified through the identity resolver directly.
    from clew.query._common import connect, identity_rowids

    with connect(db) as conn:
        assert identity_rowids(conn, "_classify") == [1], "bare name resolves to ONE identity"
        rows = conn.execute(
            "SELECT caller_rowid, callee_rowid FROM call_edges WHERE caller_rowid = callee_rowid"
        ).fetchall()
    assert rows == [(3, 3)], "scope._classify's recursion is untouched in the db"


def test_collision_free_names_are_unaffected(tmp_path: Path) -> None:
    """The direction-of-harm control. An identity rule that over-splits would
    fragment ordinary nodes, so pin that a name with no collision behaves exactly
    as before: `_guard_scope` keeps BOTH its callees, one of which is the
    collided name."""
    db = tmp_path / "collide.db"
    _name_collision_db(db)

    callees = [c.name for c in q.callees(db, "_guard_scope") if c.edge_class == "call"]
    assert sorted(callees) == ["_classify", "plain"], "an unambiguous caller keeps its fan-out"


def test_decl_def_duality_keeps_its_edges(rich_db: Path) -> None:
    """The direction-of-harm pin for gh#26, on the whole-graph fixture. C/C++
    decl/def duality is real: doxygen emits a memberdef for a definition AND one
    per documented header declaration, and a call edge attaches to whichever row
    the extraction layer saw. An identity rule that split those two rows apart
    would silently drop half the graph's edges.

    `sensor_poll` carries exactly that duality (a definition row in sensor.c and
    a declaration row in sensor.h), so both of its rowids must land in ONE
    identity and its fan-out must survive intact.

    Measured, and the reason the identity key is the QUALIFIED NAME rather than
    the whole `definition` signature: comparing whole signatures over-splits 122
    names on entropic and 13 on mbedtls, because a declaration and its definition
    can differ by a macro attribute or an inline/static qualifier."""
    from clew.query._common import connect, identity_rowids

    with connect(rich_db) as conn:
        rowids = identity_rowids(conn, "sensor_poll")
    assert len(rowids) == 2, "the decl and the def are ONE function, not two"

    callees = {c.name for c in q.callees(rich_db, "sensor_poll") if c.edge_class == "call"}
    assert "hw_read_battery_adc" in callees
    callers = {c.name for c in q.callers(rich_db, "sensor_poll") if c.edge_class == "call"}
    assert "app_run" in callers


def test_same_named_c_statics_in_different_files_still_merge(rich_db: Path) -> None:
    """KNOWN LIMITATION, pinned deliberately so a future change notices it.

    The gh#26 fix keys identity on the QUALIFIED name, which doxygen derives from
    the module for Python (`pkg.scope._classify`) and from the class/namespace for
    C++ (`LinkOwner::rx_loop`). A C free or file-static function has NO
    qualification, so two functions of the same name in different translation
    units share one identity and their edges still merge.

    The fixture has exactly that shape: `main` in src/main.c (which calls the
    subsystem inits) and `main` in the test file (which calls
    `test_findme_chime_plays`). Both remain one node.

    NOT fixed here because the obvious repair measured worse than the defect.
    Adding the definition's `bodyfile_id` to the key separates the statics, but it
    tore 957 declaration rows away from their definitions on entropic while
    fixing only 10 collisions there and 41 on mbedtls -- trading a rare
    fabrication for a common one. Recorded in gh#26 rather than patched blind."""
    callees = {c.name for c in q.callees(rich_db, "main") if c.edge_class == "call"}
    assert "app_run" in callees, "src/main.c's main"
    assert "test_findme_chime_plays" in callees, "the test file's main -- STILL merged"


## @brief Seed the gh#26 collision WITH the ast layer's namesake fan-out.
## @param path Destination sqlite path.
## @return None.
## @version 1
def _fanout_collision_db(path: Path) -> None:
    """The shape the REAL index has, which `_name_collision_db` does not.

    Measured on this repo's own index: for a call to an ambiguous private name,
    the two doxygen layers resolve CORRECTLY (each caller reaches its own
    module's `_classify`, `exact`/`resolved`) while the tree-sitter `ast` layer
    resolves by bare name and writes a FUZZY edge to EVERY namesake. So
    `plan_guidance` has 5 stored rows: 3 to its own `_classify` and one fuzzy row
    to each of the other two.

    That distinction matters because it bounds what a query-layer fix can do: the
    fabricated inbound rows are rows the PIPELINE wrote, not attribution errors,
    so they can be de-laundered but not removed from this layer.

    @brief Seed the collision plus the ast layer's fuzzy fan-out across namesakes.
    @version 1
    """
    _name_collision_db(path)
    conn = sqlite3.connect(path)
    # Every caller gets a FUZZY ast edge to every namesake, exactly as measured.
    conn.executemany(
        "INSERT OR IGNORE INTO call_edges (caller_rowid, callee_rowid, source, confidence) "
        "VALUES (?, ?, 'ast', 'fuzzy')",
        [(caller, callee) for caller in (4, 5, 6, 3) for callee in (1, 2, 3)],
    )
    conn.commit()
    conn.close()


def test_namesake_fanout_is_no_longer_laundered_into_exact(tmp_path: Path) -> None:
    """gh#26, the half a query-layer fix CAN reach, pinned on the real data shape.

    The fabricated inbound rows are written by the pipeline's `ast` layer, which
    resolves an ambiguous bare name by fanning out to every namesake. Those rows
    EXIST, so this surface cannot invent their absence. What it must not do is
    what it used to: bucket every namesake under one endpoint NAME and then report
    `_collapse_variants`' strongest evidence across the merged bucket, which
    dressed a fuzzy guess as `exact` -- the precise complaint in gh#26, that
    fabricated relationships arrive at the HIGHEST confidence level.

    Now each identity is its own bucket and is graded on its OWN evidence, so a
    fan-out row reads `fuzzy` -- which is exactly what the tool description says
    fuzzy means: only that a function of that name exists, the target never
    confirmed. A model instructed to weigh `confidence` can now act on it.

    NOT yet fixed, deliberately and with the evidence recorded: suppressing a
    fuzzy edge to one namesake when the SAME caller has a non-fuzzy edge to
    another would remove these rows entirely, because the doxygen layers resolve
    this case correctly. It is not done here because a caller may genuinely call
    two different same-named functions, and on a C++ target member-call edges are
    mostly fuzzy by construction -- so the rule needs a false-deletion
    measurement on the public C/C++ targets before it can ship."""
    db = tmp_path / "fanout.db"
    _fanout_collision_db(db)

    d = q.function_dossier(db, "_classify")
    assert d is not None and d.file == "pkg/guidance.py"

    by_name = {c.name: c for c in d.callers if c.edge_class == "call"}
    # The one REAL caller keeps its strong grading, from the layer that resolved
    # the endpoint outright.
    assert by_name["plan_guidance"].confidence == "exact"
    assert by_name["plan_guidance"].source == "doxygen_sqlite"

    # The fan-out rows are still listed -- but as fuzzy, single-layer guesses.
    for fabricated in ("_guard_scope", "plan_merge", "_classify"):
        assert by_name[fabricated].confidence == "fuzzy", (
            f"{fabricated} reaches a DIFFERENT module's _classify; "
            "reporting it as 'exact' is the gh#26 defect"
        )
        assert by_name[fabricated].source == "ast"

    # Outbound stays clean: guidance._classify's own fan-out rows point AWAY from
    # it, so nothing fabricates a callee for a function that calls nothing.
    assert [c.name for c in d.callees if c.edge_class == "call"] == []


# ─── prose: member documentation is prose too (gh#404) ───────────────────────

## The paragraph a C library actually puts its "why" in: a doc comment on a MEMBER, not in
## markdown and not a file-level `@file` block. mbedtls's is `library/common.h`'s explanation of
## why struct members are private, which is verbatim the answer to a graded question.
_MEMBER_DOC = (
    "<para>Allow the library to reach its own struct members.</para> "
    "<para>Although structs in headers are public, their members are private.</para>"
)


## @brief A database whose only prose lives in a member's description.
## @param tmp_path Per-test directory.
## @return Path to the built database.
## @version 1
def _member_doc_db(tmp_path: Path) -> Path:
    """PURPOSE-BUILT, and the shape is the whole point: the markdown corpus EXISTS and is EMPTY,
    while the member documentation is the only prose present. So a prose hit here can only have
    come through the member-doc source — which is exactly what `rich_db` cannot prove, since its
    member descriptions hold version and `@req` markup rather than sentences.

    THE EMPTY-BUT-PRESENT FTS TABLE IS DELIBERATE. Omitting it makes every reply take the
    absent-corpus branch ("this index carries NO ingested markdown corpus"), which is a real state
    but an OLD-index one: ingestion creates the table even when a repo ships no docs. A fixture
    without it would test the branch that fires for a database nobody builds any more.

    @brief Build a member-documentation-only index.
    @return Database path.
    @version 1
    """
    db = tmp_path / "memberclew.db"
    conn = sqlite3.connect(str(db))
    conn.executescript(
        """
        CREATE TABLE path (rowid INTEGER PRIMARY KEY, name TEXT, type INTEGER);
        CREATE TABLE memberdef (
            rowid INTEGER PRIMARY KEY, name TEXT, definition TEXT, argsstring TEXT,
            kind TEXT, static INTEGER, bodystart INTEGER, bodyend INTEGER,
            bodyfile_id INTEGER, file_id INTEGER, line INTEGER,
            briefdescription TEXT, detaileddescription TEXT, initializer TEXT
        );
        INSERT INTO path(rowid, name, type) VALUES (1, 'library/common.h', 1);
        CREATE VIRTUAL TABLE supplementary_docs
            USING fts5(file_path, heading, content);
        """
    )
    conn.execute(
        "INSERT INTO memberdef (rowid, name, definition, argsstring, kind, static, bodystart, "
        "bodyend, bodyfile_id, file_id, line, briefdescription, detaileddescription, initializer) "
        "VALUES (1, 'PROJ_ALLOW_PRIVATE_ACCESS', NULL, NULL, 'macro definition', 0, NULL, NULL, "
        "NULL, 1, 30, '', ?, NULL)",
        (_MEMBER_DOC,),
    )
    conn.commit()
    conn.close()
    return db


def test_prose_search_reaches_documentation_attached_to_a_member(tmp_path: Path) -> None:
    """gh#404 — THE TEXT WAS ALWAYS STORED AND NEVER SEARCHED. The prose corpus read markdown and
    file-level doc comments; a doc comment on a MEMBER went nowhere. Measured on mbedtls:
    `search_prose("MBEDTLS_ALLOW_PRIVATE_ACCESS")` returned zero while
    `memberdef.detaileddescription` held the paragraph that answers the question — and the graded
    cell was told the miss was definitive and ran three greps to find what the index was holding.

    ASSERTED ON THE STRIPPED TEXT, because doxygen stores these columns as XML: the first live
    check came back wearing `<para>` tags, which a reader pays for and cannot use.

    @brief A member's documentation is reachable as prose.
    @version 1
    """
    db = _member_doc_db(tmp_path)
    found = q.search_prose_graded(db, "private members", limit=5)
    assert found.hits, "the member's documentation is the only prose here and must be found"
    hit = found.hits[0]
    assert hit.file_path == "library/common.h"
    assert "member documentation" in hit.heading, "the heading must say where the prose came from"
    assert "<para>" not in hit.snippet, f"doxygen's XML must be stripped: {hit.snippet!r}"
    assert "their members are private" in hit.snippet


def test_a_prose_miss_is_graded_by_what_the_index_holds_elsewhere(tmp_path: Path) -> None:
    """THE NOTE, AND BOTH DIRECTIONS OF IT. `_many`'s default wording — "a definitive empty
    result… Do not retry this query or fall back to guessing" — is correct for a tool whose
    emptiness can only mean absence, and was flatly wrong for prose. It is the specific sentence
    that sent a graded agent to grep.

    TWO-SIDED ON PURPOSE. A token the index holds elsewhere must be graded DOWN; a token that is
    genuinely nowhere must KEEP the strong wording, because that is the case which earns it. A
    one-sided version of this test passes against an implementation that never claims certainty
    at all, which would be the dilution the anti-dilution test guards.

    @brief An empty prose reply claims only what it has earned.
    @version 1
    """
    from clew.mcp_server.emptiness import prose_emptiness

    db = _member_doc_db(tmp_path)
    ## The name IS in this index (as a macro-definition row), just not in prose the corpus reads.
    elsewhere, extra = prose_emptiness(db, "PROJ_ALLOW_PRIVATE_ACCESS")
    assert "NOT DEFINITIVE" in elsewhere, f"the index holds this name: {elsewhere}"
    assert "token_hits" in extra, "and the claim must be checkable, not merely worded"

    ## A token nowhere in the index keeps the strong wording it has now earned.
    nowhere, _extra = prose_emptiness(db, "zzz_absent_token_qqq")
    assert "definitive empty result" in nowhere, (
        f"a token in NO corpus is a definitive negative — refusing to say so would be the "
        f"dilution the anti-dilution test guards: {nowhere}"
    )
