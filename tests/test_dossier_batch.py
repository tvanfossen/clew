# SPDX-License-Identifier: MIT
"""Tests for the BATCHED dossier — several symbols, one call, one shared byte budget.

The measurement that motivated it: across three graded mbedtls runs of one question the
model called `dossier` five times each, one symbol per call, and the three transcripts
agree on nothing else. Per-call token cost was already below the raw-source arm's, so
the remaining gap was volume — turns, not bytes.

Which is exactly why the assertions here are about TURNS AND FAIRNESS rather than size.
A batch that costs the same bytes as five separate replies is the win; a batch that
saves bytes by quietly dropping the fifth symbol is the failure, and it is the failure
this file exists to catch. So every test that trims also checks that what was trimmed is
NAMED, and that the smallest payload in the batch is the LAST thing cut.

@brief Tests for the batched dossier and its shared response budget.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from clew import query as q
from clew.mcp_server.tools_query import (
    RESPONSE_BUDGET_BYTES,
    QueryTools,
    _budget_batch,
    _fair_shares,
    _shrink_to_budget,
)

## Two functions the csample fixture indexes, plus one it certainly does not. Named
## rather than discovered, so a fixture change that removes them fails loudly here
## instead of turning these assertions vacuous.
INDEXED = ("sensor_poll", "telemetry_report")
MISSING = "no_such_function_xyz"


## @brief A tool set bound to the session fixture index.
## @param rich_db The synthetic index.
## @return Query tools over it.
## @version 1
def _tools(rich_db: Path) -> QueryTools:
    """@brief Bind QueryTools to the shared fixture database.

    @return The tool set.
    @version 1
    """
    return QueryTools(lambda: rich_db, lambda: rich_db.parent)


## @brief Compact-JSON byte length, matching the wire.
## @param payload Any serializable reply.
## @return Byte count.
## @version 1
def _size(payload: object) -> int:
    """@brief Measure a payload the way the transport does.

    @return Bytes.
    @version 1
    """
    return len(json.dumps(payload, default=str))


def test_a_batch_returns_the_same_payload_per_symbol_as_the_single_calls(rich_db: Path) -> None:
    """THE WHOLE PREMISE. A batch is only a saving if it is the same answer in fewer
    turns; if the batched entry differs from the single-call payload the saving is
    bought with data the caller then has to go back for, which is a net loss of a turn
    rather than a gain of four.

    Compared field by field over the panels that carry rows, because comparing whole
    dicts would fail on the envelope keys a single reply carries and a batch entry
    deliberately does not (`target`, stamped once for the batch).

    @brief Each batch entry matches its single-call dossier.
    @version 1
    """
    tools = _tools(rich_db)
    singles = [tools.dossier(n) for n in INDEXED]
    batch = tools.dossier(list(INDEXED))

    assert batch["kind"] == "dossiers"
    assert batch["count"] == len(INDEXED)
    assert batch["found"] == len(INDEXED)
    assert [e["name"] for e in batch["results"]] == list(INDEXED)
    for single, entry in zip(singles, batch["results"], strict=True):
        for panel in ("callers", "callees", "writes", "reads", "requirements"):
            assert entry.get(panel) == single.get(panel), panel
        for ident in ("name", "signature", "file", "brief", "liveness"):
            assert entry.get(ident) == single.get(ident), ident


def test_one_unresolvable_name_misses_in_its_own_slot_and_the_rest_still_answer(
    rich_db: Path,
) -> None:
    """POSITIONAL, INCLUDING THE MISSES. Dropping the miss would silently re-align every
    entry after it, so a reader pairing names with answers by position would attribute
    the third symbol's dossier to the second name — a wrong answer delivered with full
    confidence, which is worse than the miss it hides.

    The miss is placed in the MIDDLE deliberately: a miss at the end is caught by a
    length check alone, and a length check is what a dropped-and-shifted list passes.

    @brief A miss occupies its own slot and does not fail the batch.
    @version 1
    """
    names = [INDEXED[0], MISSING, INDEXED[1]]
    batch = _tools(rich_db).dossier(names)

    assert [e["name"] for e in batch["results"]] == names
    assert batch["count"] == 3
    assert batch["found"] == 2
    assert batch["results"][1]["found"] is False
    assert "not an error" in batch["results"][1]["note"]
    assert batch["results"][0].get("found") is None
    assert batch["results"][2]["signature"]


def test_a_qualified_argument_beside_a_list_is_refused_not_ignored(rich_db: Path) -> None:
    """`qualified` names ONE identity among namesakes. Applied to a list it would scope
    four dossiers by a key belonging to the fifth; ignored, the caller who asked for a
    specific identity would receive an arbitrary one and no indication of it. Both silent
    options produce a confidently mislabelled answer, so the call is refused.

    @brief A list plus `qualified` raises.
    @version 1
    """
    with pytest.raises(ValueError, match="cannot be combined with a list"):
        _tools(rich_db).dossier(list(INDEXED), qualified="some::identity")


def test_the_batch_cap_refuses_rather_than_answering_for_the_first_n(rich_db: Path) -> None:
    """A truncated request answered as if complete is the failure the `_limited`
    disclosure exists to prevent, one level up. At the cap the call must still work —
    an off-by-one that refused the documented maximum would make the constant a lie.

    @brief Over the cap raises; at the cap answers.
    @version 1
    """
    tools = _tools(rich_db)
    over = [f"{INDEXED[0]}_{i}" for i in range(q.MAX_BATCH_SYMBOLS + 1)]
    with pytest.raises(ValueError, match="at most"):
        tools.dossier(over)
    assert tools.dossier(over[: q.MAX_BATCH_SYMBOLS])["count"] == q.MAX_BATCH_SYMBOLS


def test_an_empty_list_is_refused_rather_than_answered_with_zero_results(
    rich_db: Path,
) -> None:
    """`count: 0` to a request that asked for nothing reads as "none of your symbols is
    indexed", which is a measurement the database never made.

    @brief An empty list raises.
    @version 1
    """
    with pytest.raises(ValueError, match="at least one"):
        _tools(rich_db).dossier([])


def test_a_repeated_name_is_answered_once(rich_db: Path) -> None:
    """A duplicate costs a whole dossier of the shared budget to say the same thing
    twice, and the entry it occupies is better spent on a symbol that was asked about.

    @brief Duplicates collapse to one entry.
    @version 1
    """
    batch = _tools(rich_db).dossier([INDEXED[0], INDEXED[0], INDEXED[1]])
    assert [e["name"] for e in batch["results"]] == [INDEXED[0], INDEXED[1]]


def test_a_single_string_argument_is_unchanged_by_the_batch_path(rich_db: Path) -> None:
    """The common case and every existing caller. A polymorphic first argument is only
    safe if the string branch is byte-identical to what it always returned.

    @brief The single-symbol form still returns a bare dossier.
    @version 1
    """
    single = _tools(rich_db).dossier(INDEXED[0])
    assert single["name"] == INDEXED[0]
    assert single["kind"] != "dossiers"
    assert "results" not in single


def test_n_dossiers_share_the_budget_instead_of_each_claiming_it() -> None:
    """THE FAILURE THIS PREVENTS IS ARITHMETIC. Trimming each entry to the whole-response
    ceiling would produce a reply that respects `RESPONSE_BUDGET_BYTES` N times over and
    exceeds it once — and nothing downstream would notice, because every individual
    payload passed its own check.

    Driven through `_budget_batch` with synthetic entries rather than a real index,
    because the fixture repository is too small to overflow the cap and a mechanism only
    exercised on a target nobody runs in CI is a mechanism nobody tests.

    THE FIXTURE IS DERIVED FROM THE CAP, NOT HARDCODED. A literal row count silently stops
    testing the mechanism the moment the cap moves: at 400 rows this test overflowed a
    32,768-byte budget and merely fitted a 65,536-byte one, so raising the cap turned the
    oversize PRECONDITION into the failure — the assertion that fired was the guard, not
    the property. The cap is documented as PROVISIONAL and expected to move again, so the
    fixture scales with it and the guard below stays meaningful at any value.

    @brief A batch of oversized dossiers still fits the single-response cap.
    @version 2
    """
    ## Sized so ONE entry alone overflows the whole budget, which makes five of them
    ## comfortably clear the 4x guard however the serialiser's per-row overhead drifts.
    rows = RESPONSE_BUDGET_BYTES // 64
    entries = [
        {"name": f"fat_{i}", "callers": [{"name": f"c{j}" * 12, "line": j} for j in range(rows)]}
        for i in range(5)
    ]
    assert sum(_size(e) for e in entries) > RESPONSE_BUDGET_BYTES * 4

    limited = _budget_batch(entries, overhead=200)

    assert sum(_size(e) for e in entries) + 200 <= RESPONSE_BUDGET_BYTES
    assert limited is not None
    ## NAMES THE SYMBOL, not just the field: in a one-symbol reply `_limited: {callers}`
    ## is unambiguous, in a batch it is useless.
    assert set(limited["adjusted"]) == {f"fat_{i}.callers" for i in range(5)}
    assert all(f"{rows} ->" in v for v in limited["adjusted"].values())


def test_the_small_symbol_in_a_batch_is_not_starved_by_the_large_one() -> None:
    """THE FAIRNESS PROPERTY, stated as the task states it: a batch where symbol 1 is
    complete and symbol 5 is empty is worse than five thin ones, because the reader
    cannot tell truncation from absence.

    Max-min fairness gives exactly the guarantee wanted — nothing is trimmed while
    something larger is still above its share — so the tiny entry beside a 400-row hub
    must come through untouched, and the hub must be the only one cut.

    @brief A cheap dossier survives a batch with an expensive one.
    @version 1
    """
    small = {"name": "small", "callers": [{"name": "only_caller"}]}
    big = {"name": "big", "callers": [{"name": f"c{j}" * 12, "line": j} for j in range(2_000)]}
    entries = [small, big]
    assert _size(big) > RESPONSE_BUDGET_BYTES, "the big entry must actually overflow"

    limited = _budget_batch(entries, overhead=200)

    assert small["callers"] == [{"name": "only_caller"}], "the small entry was trimmed"
    assert limited is not None
    assert set(limited["adjusted"]) == {"big.callers"}


def test_fair_shares_gives_a_payload_that_fits_exactly_what_it_needs() -> None:
    """The waterfill itself, at the unit level, because the property it provides is not
    visible in a pass/fail on the batch: an EQUAL split would also keep the batch under
    the cap while stranding budget on payloads that did not need it.

    @brief Max-min fairness releases the surplus of the payloads that fit.
    @version 1
    """
    ## 100 fits any share; the other two need everything left over, split evenly.
    assert _fair_shares([100, 5_000, 5_000], 3_100) == [100, 1_500, 1_500]
    ## Nobody fits: an even split, and no share is zero.
    assert _fair_shares([9_000, 9_000], 1_000) == [500, 500]
    ## Everybody fits: nothing is capped below its own size.
    assert _fair_shares([100, 200], 10_000) == [100, 200]


def test_r2_dossiers_is_positional_and_matches_the_single_symbol_function(
    rich_db: Path,
) -> None:
    """The library contract underneath the tool: one entry per requested name, in
    request order, `None` where a name resolves to nothing — and each one equal to what
    the single-symbol `dossier` would have built for it.

    Guards the split that makes the batch cheap. `_dossier_conn` was extracted so five
    symbols share one connection; if that extraction changed an answer, the saving would
    have been bought with correctness.

    @brief R2 `dossiers` is positional and agrees with `dossier`.
    @version 1
    """
    names = [INDEXED[0], MISSING, INDEXED[1]]
    built = q.function_dossiers(rich_db, names)

    assert len(built) == len(names)
    assert built[1] is None
    for name, doss in zip(names, built, strict=True):
        assert doss == q.function_dossier(rich_db, name)


def test_the_chain_loses_its_outermost_ring_before_a_neighbour_list_is_trimmed() -> None:
    """gh#383, and the defect is sharper than "step depth before halving". `_DOSSIER_LISTS`
    holds TOP-LEVEL keys and `payload["chain"]` is a NESTED dict of nodes/hops, so
    `_shrink_to_budget` could not see the chain at all: an oversized traversal was carried in
    full while `callers` and `callees` — the highest-value rows in the reply — were halved to
    pay for it. Exactly backwards. Depth 1 is adjacency, which the populated section already
    carries; depth 2+ is traversal, and fan-out is roughly geometric, so the outermost ring is
    both the cheapest thing to lose and usually the largest.

    THE ORDERING IS THE CLAIM, so it is what is asserted: with a chain big enough to blow the
    budget on its own, the neighbour list must come through UNTOUCHED. A test that only
    checked "the payload fits" would pass on the old behaviour too.

    HOPS ARE PRUNED WITH THEIR NODES. A hop whose endpoint left would assert an edge into
    nothing, which is a worse answer than a smaller chain.

    @brief Depth is spent before rows, and hops leave with their nodes.
    @version 1
    """
    payload: dict = {
        "subject": "seed",
        "callers": [{"name": f"caller_{i}"} for i in range(8)],
        "chain": {
            "seed": "seed",
            "nodes": [{"name": "seed", "depth": 1}]
            + [{"name": f"far_{i}" * 30, "depth": 3} for i in range(400)],
            "hops": [
                {"edge_class": "call", "from_name": "seed", "to_name": f"far_{i}" * 30}
                for i in range(400)
            ],
        },
    }
    cut = _shrink_to_budget(payload, ("callers",))

    assert len(payload["callers"]) == 8, (
        "the immediate neighbours are the DEAREST rows and must survive a chain that "
        "could have been dropped instead"
    )
    assert cut.get("chain_depth") == 3, "the dropped depth must be reported as a depth"
    assert all(n["depth"] < 3 for n in payload["chain"]["nodes"])
    ## Every hop pointed at a depth-3 node, so all of them must go with it.
    assert payload["chain"]["hops"] == []
    assert _size(payload) <= RESPONSE_BUDGET_BYTES


def test_a_depth_one_chain_is_never_stripped_to_nothing() -> None:
    """FAIL TOWARD KEEPING SOMETHING. Depth 1 is the last ring, and removing it would leave a
    `chain` block claiming a traversal with no reachable nodes — a shape that reads as "the
    traversal found nothing" rather than "the traversal was trimmed". Better a chain that is
    smaller than one that lies.

    @brief The depth-1 ring survives; row trimming takes over instead.
    @version 1
    """
    payload: dict = {
        "subject": "seed",
        "callers": [{"name": f"c_{i}" * 40} for i in range(400)],
        "chain": {"seed": "seed", "nodes": [{"name": "seed", "depth": 1}], "hops": []},
    }
    cut = _shrink_to_budget(payload, ("callers",))

    assert payload["chain"]["nodes"], "the last ring must not be stripped"
    assert "chain_depth" not in cut, "nothing was stepped, so nothing may be claimed"
    assert cut.get("callers"), "with no depth to give, row trimming is what pays"
