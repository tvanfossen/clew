# SPDX-License-Identifier: MIT
"""The readiness gate: can a real index actually ANSWER the acceptance matrix?

Every question in `acceptance/targets/self/questions.md` rests on specific
data being present — a symbol resolving, a causal chain connecting, a requirement
mapping to implementers. If that data is missing, the matrix does not measure the
tool; it measures a broken index, and the resulting numbers look like the tool
failing.

This existed as `.claude/tmp/bench/docsdb_richness_audit.py` and ran only when
somebody remembered. `.claude/` is gitignored, so the gate protecting the benchmark
lived somewhere it could vanish without a trace and CI could never see it. Moved
here (#93) so it runs like everything else.

**Every name below is a load-bearing data point of a frozen matrix question**, not
a sample of the codebase. Adding one means a question started depending on it.

@brief Integration gate: the self-index answers every matrix question.
@version 1
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration

## The six frozen questions reduced to the data each one needs.
##
## Q6 covers requirement traceability: the package tags its own functions with `@req`, so
## IMPLEMENTATION traceability resolves; TEST traceability is partial. The exact state is
## pinned by `test_requirement_traceability_state_is_known`.
Q_FUNCTIONS: dict[str, tuple[str, ...]] = {
    "Q1 no-Doxyfile repo -> indexed artifacts": (
        "load_declaration",
        "derive_scope",
        "discover_doxyfile",
        "_run_pipeline",
        "_build_stages",
    ),
    "Q2 macro-hidden dataflow -> empty layer": (
        "import_shared_key_edges_inferred",
        "detect_undeclared_accessor_families",
        "resolve_shared_key_patterns",
    ),
    # Deliberately the PUBLIC query surface only. An earlier draft also probed
    # `_collapse_variants`, the private helper implementing #38, and it reported a
    # gap the moment that helper was added — because the served index had not been
    # rebuilt. That measured index STALENESS, not richness. The #38 and #46
    # behaviours are asserted for real below, by reading data rather than looking
    # up a name, which is the stronger check anyway.
    "Q3 who feeds this function?": (
        "callers",
        "callees",
        "chain_trace",
        "resolve_symbol",
    ),
    "Q4 does clew dogfood its own gate?": (
        "load_guard_config",
        "resolve_req_id_pattern",
        "ingest_requirements_yaml",
    ),
    "Q5 when does build_or_refresh rebuild?": (
        "read_build_signature",
        "write_build_signature",
    ),
}

## The causal traversal must connect these. A resolvable name is not enough for a
## question that asks how one thing reaches another.
Q_CHAINS: tuple[tuple[str, str], ...] = (("_run_pipeline", "_build_stages"),)


## @brief Names the index resolves to at least one indexed function.
## @param db Database to read.
## @return Set of the names present.
## @version 1
def _indexed(db: Path) -> set[str]:
    """@brief Read every indexed function name once.

    @return The set of function names in the index.
    @version 1
    """
    conn = sqlite3.connect(str(db))
    try:
        return {r[0] for r in conn.execute("SELECT name FROM memberdef WHERE kind='function'")}
    finally:
        conn.close()


## @brief Every matrix question's load-bearing symbols are indexed.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_every_question_has_its_symbols(self_index_db: Path) -> None:
    """Reported per question rather than as one flat set, because "the index is
    missing something" is not actionable while "Q2 cannot be answered" is.

    @brief Each frozen question's symbols resolve in a real index.
    @version 1
    """
    present = _indexed(self_index_db)
    assert present, "precondition: the index must contain functions at all"

    missing = {
        question: sorted(set(names) - present)
        for question, names in Q_FUNCTIONS.items()
        if set(names) - present
    }
    assert missing == {}, f"matrix questions whose data is absent from the index: {missing}"


## @brief The causal traversal connects the pairs a question depends on.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_declared_causal_chains_connect(self_index_db: Path) -> None:
    """A separate claim from symbol presence, and a stronger one: Q1 asks how a
    build reaches its stages, which needs an actual PATH, not two resolvable names.

    Uses the shipped `chain_trace` rather than its own SQL, so this measures what a
    consumer would get.

    @brief Each declared (seed, target) pair is reachable.
    @version 1
    """
    from clew import query as q

    for seed, target in Q_CHAINS:
        chain = q.chain_trace(self_index_db, seed, max_depth=6)
        reached = {node.name for node in chain.nodes}
        assert target in reached, (
            f"chain_trace({seed!r}) does not reach {target!r} — a matrix question "
            f"depends on that path existing"
        )


## @brief The #46 edge_class tag and #38 collapse hold on real data.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 1
def test_query_surface_invariants_hold_on_real_data(self_index_db: Path) -> None:
    """Reads the DATA rather than checking that a helper's name exists, which is why
    it replaced an earlier name-probe that reported a false gap whenever the index
    lagged the source.

    Two invariants a matrix answer can rest on:
      * #46 — every neighbour row is TAGGED with its `edge_class`, so a consumer can
        tell a call from a dataflow hand-off.
      * #38 — neighbours are COLLAPSED to one row each, so counts mean something.
        The raw table stores one row per extraction layer by design.

    @brief The public neighbour surface is tagged and collapsed.
    @version 1
    """
    from clew import query as q

    subject = "_run_pipeline"
    callees = q.callees(self_index_db, subject)
    assert callees, f"precondition: {subject} must have neighbours for this to mean anything"

    assert all(e.edge_class for e in callees), "#46: every neighbour row must carry edge_class"

    names = [e.name for e in callees]
    assert len(names) == len(set(names)), (
        f"#38: {subject} returned duplicate neighbours — the per-layer rows are not "
        f"being collapsed, so every count and depth cap downstream is inflated"
    )


## @brief Q6's requirement traceability: implementers work, tests are still the gap.
## @param self_index_db A real, cold index of this repository.
## @return None.
## @version 2
def test_requirement_traceability_state_is_known(self_index_db: Path) -> None:
    """THE HALF THIS TEST USED TO PIN IS RETIRED, and it retired itself exactly as
    designed. It asserted `implementers == []` because the package carried ZERO `@req`
    tags (task #62), with an escape hatch saying that if implementers ever appeared
    the limitation should be removed rather than the assertion loosened. They
    appeared: the package now tags itself, and `REQ-DDB-CONFIG-001` alone resolves to
    ~80 live implementers on a fresh self-index. The CHANGELOG had already been
    updated to say implementation traceability works; only this test lagged, which is
    why it failed (gh#362) — a STALE EXPECTATION, not a regression.

    THE TEST HALF HAS RETIRED TOO, and that was found here rather than believed: the
    CHANGELOG still claimed "no TEST function carries a `@req` tag, so `req_test_edges`
    is empty", while a real self-index emits SIX `req_test_edges` rows and
    `req_trace('REQ-DDB-MCP-003').tests` names two covering tests. Both halves of Q6
    are therefore asserted POSITIVELY, on two different requirement ids, because they
    populate from different tables through different code paths and one working says
    nothing about the other.

    NO EXACT COUNT IS ASSERTED, deliberately. Both counts move with every tag anyone
    adds — neither is a property of the tool — and a number that has to be re-derived
    on each commit is a number that gets loosened rather than fixed. What is asserted
    is the SHAPE: rows exist, each names a function, and the catalog metadata that
    makes the answer useful came through with them.

    @brief Both halves of requirement traceability resolve on a real self-index.
    @version 2
    """
    from clew import query as q

    trace = q.req_trace(self_index_db, "REQ-DDB-CONFIG-001")
    assert trace.implementers, (
        "REQ-DDB-CONFIG-001 resolves to no implementers. The package tags itself, so "
        "this is a req_edges regression, not the old task #62 gap — check that the "
        "declared id pattern in .doxygen-guard.yaml still matches the tags."
    )
    assert all(imp.name and imp.liveness for imp in trace.implementers), (
        "an implementer with no name or no liveness verdict is an unusable row"
    )
    assert trace.title, (
        "the catalog metadata did not come through — req_edges populate from TAGS and "
        "the catalog is read separately, so titles can be NULL while coverage looks fine"
    )

    ## A DIFFERENT id on purpose: `REQ-DDB-MCP-003` is one of the few this repo tags
    ## from a test as well as from the implementation, so it is the only id that can
    ## demonstrate the `req_test_edges` path at all. Asserting `tests` on
    ## `REQ-DDB-CONFIG-001` would assert emptiness and pass for the wrong reason.
    covered = q.req_trace(self_index_db, "REQ-DDB-MCP-003")
    assert covered.tests, (
        "REQ-DDB-MCP-003 reports no covering tests — req_test_edges regressed. Two "
        "test functions in tests/test_mcp_server.py tag it; if the tags are still "
        "there, the edge builder stopped reading them."
    )
