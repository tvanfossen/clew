# SPDX-License-Identifier: MIT
"""R3 tier-1 tools: thin MCP wrappers, 1:1 with the R2 query library.

MVVM: `clew.query` is the ViewModel. These wrappers are a View —
they resolve the active database, call the R2 function, and serialize the
frozen dataclasses R2 returns (`dataclasses.asdict`). NO query or traversal
logic lives here; if a wrapper ever needs SQL, the function belongs in R2
instead.

THE TARGET TRAVELS ON THE CALL. Every wrapper takes an optional `target`; omitting it
answers from the repository the server derived, naming one answers from that repository
instead, and the tool set holds nothing between calls either way. One process therefore
serves any number of indexed repositories, which is what the alternative — one server
process per repository — was a workaround for.

@brief Tier-1 MCP tool wrappers over the R2 query library.
@version 3
"""

from __future__ import annotations

import re
import json
from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any

from pydantic import Field

from .. import query as q
from .. import wire
from ..query import export as _export
from ..query.payload import (  # noqa: F401 — re-bound here: tests and callers read these names
    _DOSSIER_OPTIONAL,
    _GATE_DEFINITION_CAP,
    _GATE_INVARIANTS,
    _MAX_CANDIDATES,
    _NO_SEED_NOTE,
    _accepted_batch,
    _ambiguity_block,
    _batch_miss,
    _candidates_capped,
    _compact_gate_panel,
    _config_found_on_the_wire,
    _constructor_note,
    _distinct_identities,
    _empty_callers_note,
    _flatten_subject,
    _gate_definition_gaps,
    _gate_definitions,
    _hoist_build_wide,
    _kind_limitation_clause,
    _refusal_note,
)
from ..query.recovery import recovery_hint
from .descriptions import load_descriptions
from .routing import MAX_LISTED_SIBLINGS, no_index_message
from .state import Answering

DbProvider = Callable[[], Path]
RepoProvider = Callable[[], Path]

## Resolves a target string the CALLER supplied into the repository that answers for it.
##
## Kept apart from the three providers below rather than folded into them as an argument,
## because the two resolutions are different operations rather than one with a parameter.
## The providers report the target the SERVER derived — from `--repo`, the environment, or
## the client's roots — and that chain may issue a request to the client. This one resolves
## a string against the registry and the filesystem and consults none of those sources.
##
## OPTIONAL: a tool set bound without one serves exactly the database its providers name.
## It then REFUSES an explicit target instead of ignoring it, because answering from the
## bound repository while stamping that repository's name onto the reply is indistinguishable
## from a successful routed call.
##
## `None` AS THE TARGET ASKS FOR THE DEFAULT, through the same resolution (gh#48), so a reply to a
## call that named nothing is attributed — `sub_index`, `not_searched` — exactly as a routed one is.
Answerer = Callable[[str | None, str | None], Answering]

## Supplies the staleness axes in play at reply time, or an empty list when the tool is
## current. A CALLABLE for the same reason the db path is one — it must be measured per
## reply, since the whole point is to catch an edit the caller made a moment ago — and
## OPTIONAL because a tool set bound without one is the test-only shape, and because the
## previous behaviour (no annotation at all) is what an absent provider must reproduce.
StalenessProvider = Callable[[], list[dict[str, str]]]

## Supplies the note and the extra envelope keys for an empty result whose emptiness
## may not mean absence. Deferred as a callable rather than computed eagerly, because
## the diagnosis costs extra queries and must not be paid on the common path.
Diagnoser = Callable[[], tuple[str, dict[str, Any]]]

## Tool name → description, in registration order. The prose lives in
## `descriptions/<tool>.json`, one file per tool: it is CONTENT a model reads before
## choosing a tool, it gets reworded far more often than the wrapper it describes, and
## as ~180 inline lines it made this module mostly text. Loaded, not hardcoded — the
## loader refuses an unknown key, a missing template or an empty directory rather than
## letting a tool ship with no description.
TIER1_TOOLS: dict[str, str] = load_descriptions()


## Byte budget for ONE tool response. Enforced only here, at the MCP boundary —
## never in the query layer, which must keep returning everything because a
## direct R2 caller has no context window and must not inherit a limit that
## exists solely to protect a model's prompt.
##
## This cap is the ONLY thing confined to this boundary, and the reason is that it is
## LOSSY: it drops rows. The neighbouring temptation is to confine anything that makes
## a response smaller, which was tried and was wrong — row-field elision loses nothing
## (absent and null carry the same information), so it belongs to every surface and
## lives in `clew.wire`. Confining a lossless transform bought two payload
## shapes for no benefit and would have made a front end read fields differently
## depending on which surface handed them over.
##
## MEASURED cause: `dossier('size')` on a real C++ index returned **125,559 bytes**
## for a symbol with 331 callers, and 138 functions on that target have >50 callers.
## Nothing capped the flat one-hop lists; only `chain_trace` had a fan-out bound, so
## the surface a model reaches for FIRST was the unbounded one.
## RAISED 32,768 -> 65,536 (owner, 2026-08-12), PROVISIONALLY — revisit once the call count settles.
##
## THE ARITHMETIC THAT MOVED IT. Cost per turn is the fixed prefix plus everything already returned, so
## the marginal cost of ONE MORE ROUND TRIP is the whole current context — measured at 70-90k tokens on
## a real cell. The marginal cost of 32 KB more payload is ~8k tokens, re-read on each REMAINING turn.
## Break-even is therefore around ELEVEN remaining turns: below that a fatter payload is cheaper than
## the round trip it prevents, above it the trim wins. The surface is moving from 13-14 calls toward
## single digits, which carries it under the break-even.
##
## MEASURED, NOT ARGUED: capping neighbour lists to 10 (with the total disclosed AND an explicit way to
## ask for more) cost +47.9% tokens and +40.3% calls against an uncapped control, because the model did
## not ask for more — it ran five extra searches. Trimming produced exploration, not focus. And across a
## whole Q1 cell the index arm's total payload was 27,627 bytes against the source arm's 36,174: payload
## is ~0.18% of the bill, so this cap was never buying what it appeared to buy.
##
## THE NUMBER IS PROVISIONAL AND SHOULD BE RE-DERIVED, not defended. It is a function of turn count, and
## turn count is the variable currently being changed. Re-measure after the surface settles.
##
## WHAT STAYS TRUE AT ANY VALUE:
## - Enforced only HERE, at the MCP boundary, never in the query layer — a direct R2 caller has no
##   context window and must not inherit a limit that exists to protect a model's prompt.
## - The cap is LOSSY, which is why `_shrink_to_budget` discloses what it dropped. A silent truncation
##   is the worst option available.
## - Some ceiling is required. MEASURED cause: `dossier('size')` on a real C++ index returned 125,559
##   bytes for a symbol with 331 callers, and 138 functions on that target have >50 callers. Nothing
##   capped the flat one-hop lists; only `chain_trace` had a fan-out bound, so the surface a model
##   reaches for FIRST was the unbounded one.
RESPONSE_BUDGET_BYTES = 65_536

## Callers and callees listed per dossier subject before the rest is disclosed rather than sent.
## Enough for every "where is this used" set the acceptance rubrics grade (the largest is eight
## files), and a bound on a hub: `doFetch` on mattermost-mobile listed 229 callers in 50,692 bytes,
## re-read on every later turn of the agent that asked.
DEFAULT_MAX_NEIGHBORS = 25

## A deeper walk's per-hop fan-out when the caller sets none — `chain_trace`'s own default, so a
## dossier at depth > 1 is the same walk `chain_trace` returns.
CHAIN_MAX_NEIGHBORS = 8

## Headroom reserved for the `_limited` block itself, which is appended AFTER the
## payload has been trimmed. Without it the disclosure pushes the response back over
## the cap it exists to describe.
##
## Sized for the WORST case, which is `dossier`: its block is a per-field dict with
## one entry per trimmed list (up to six) where `_many`'s is a single entry. Measured
## at ~250 bytes per entry, so six entries plus slack.
##
## ALL BUDGETING HERE MEASURES COMPACT JSON, which is what JSON-RPC puts on the wire.
## A diagnostic script that pretty-printed with `indent=2` reported these responses
## ~30% larger and sent a bug hunt after a cap that was working correctly — the
## serialization used to MEASURE has to match the serialization used to SEND.
_LIMITED_BLOCK_ALLOWANCE = 1_800


## What a staleness notice is reduced to when the full prose will not fit beside an
## already-large payload, and then again when even that will not. The AXIS TOKEN SURVIVES
## EVERY TIER — it is the field a consumer branches on, and dropping it to save bytes
## would leave a warning that cannot be acted on programmatically. Only the explanation is
## traded, first for a pointer to where the full one lives and finally for three words.
_STALENESS_COMPACT_MESSAGE = (
    "this index is stale on this axis; call status for the full diagnosis and the remedy "
    "(the explanation did not fit beside this payload)"
)
_STALENESS_MINIMAL_MESSAGE = "stale — call status"


## @brief Fit a staleness block into whatever budget the payload left.
## @param payload The reply as it will be sent, staleness excluded.
## @param found The full notice list.
## @return The notices to attach — full prose, compacted, or minimal.
## @version 2
## @dg_internal
def _staleness_within_budget(
    payload: dict[str, Any], found: list[dict[str, str]]
) -> list[dict[str, str]]:
    """MEASURED AGAINST THE REAL PAYLOAD rather than reserved up front, and the choice
    matters. Reserving headroom the way `_LIMITED_BLOCK_ALLOWANCE` does would lower the
    trim ceiling for EVERY response including the overwhelming majority that carry no
    annotation at all, changing how much data a current index returns because a stale one
    might have needed the room. This spends only what is actually free.

    Compacting rather than dropping, because a warning that disappears exactly when the
    answer is largest inverts the point: a big payload is a lot of reasoning to do on a
    possibly-outdated graph.

    THREE TIERS, BECAUSE TWO WERE NOT ENOUGH AND A CONTROL PROVED IT. The first version
    fell back to the compact form and returned it unconditionally — but the compact form
    is ~170 bytes PER AXIS, so three axes beside a payload with 190 bytes free still went
    over the very cap this function exists to respect. A fallback that is merely smaller
    is not bounded. The last tier is ~40 bytes per axis and is taken unconditionally,
    which is safe rather than lucky: `_shrink_to_budget` trims to
    `RESPONSE_BUDGET_BYTES - _LIMITED_BLOCK_ALLOWANCE`, so a real reply arrives here with
    most of 1,800 bytes free and never reaches the third tier at all.

    @brief Choose the largest staleness block that fits.
    @return Notices sized to fit.
    @version 2
    """
    room = RESPONSE_BUDGET_BYTES - len(json.dumps(payload))
    tiers = (
        found,
        [{"axis": n["axis"], "message": _STALENESS_COMPACT_MESSAGE} for n in found],
        [{"axis": n["axis"], "message": _STALENESS_MINIMAL_MESSAGE} for n in found],
    )
    fitting = (t for t in tiers if len(json.dumps({"staleness": t})) <= room)
    return next(fitting, tiers[-1])


## The axis whose presence makes a definitive-negative claim unearned. `data` staleness means the
## index describes slightly older code, which does not undermine "this database holds no such
## row"; `schema` means the index was built by an older pipeline and MAY BE MISSING WHOLE LAYERS,
## which undermines exactly that.
_SCHEMA_AXIS = "schema"

## AND `data` UNDOES IT TOO, BUT ONLY FOR A MISSING SUBJECT (gh#12). The comment above is right
## about row lists and wrong about subject misses, which is the case that got reported: a symbol
## written minutes earlier came back `found: false` as "a definitive negative", beside a `data`
## notice in the SAME envelope saying 39 files had changed since the build. For "does this symbol
## exist", data staleness is not a footnote — it is the single likeliest explanation, and the note
## spent its advice sending the reader to check `target`, which was correct all along.
##
## SCOPED TO `found is False` ON PURPOSE. Applying it to every empty list would hedge "no callers"
## and "no locks" on any slightly-stale index, which is the over-hedging gh#393 built and reverted.
## A subject miss is the one shape where a newer working tree fully explains the answer.
_DATA_AXIS = "data"

## A layer that FAILED rather than went stale (see `freshness.AXIS_PARTIAL`). Its own sentence,
## because the schema remedy — refresh with force — re-runs the doxygen that crashed.
_PARTIAL_AXIS = "partial"
_UNEARNED_BY_PARTIAL = (
    " NOT DEFINITIVE: this index was built without its C/C++ layer because doxygen failed (see "
    "`staleness` below), so a C/C++ symbol may exist and simply not be indexed. Fix the cause named "
    "there, then refresh, before concluding the repository has none."
)

## A fast in-place refresh left whole-index layers behind (see `freshness.AXIS_DERIVED`). Any
## definitive negative may be drawn from one of them, so it is withdrawn whatever its shape.
_DERIVED_AXIS = "derived"
_UNEARNED_BY_DERIVED = (
    " NOT DEFINITIVE: this index was just updated in place for an edit, and the whole-index "
    "layers named in `staleness` below still describe the code before it — so callers, threads "
    "or reachability involving the edited files may be missing rather than absent. Ask again once "
    "the full refresh completes, or call index(action='refresh')."
)

## Why this is still the residual case in 1.0.8 rather than a solved one: a data-stale query now
## refreshes BEFORE answering, so a miss with a live `data` notice means the refresh did not run —
## the `code` axis refuses it, or it failed. Both are conditions the reader must act on, so the
## replacement names the refresh AND the reason it may not have happened by itself.
_UNEARNED_BY_DRIFT = (
    " NOT DEFINITIVE: the sources have changed since this index was built (see `staleness` "
    "below), so a symbol added after the build is missing rather than absent. An automatic "
    "refresh normally corrects this before answering, so if you are reading this the refresh was "
    "refused or failed — check the `code` axis. Refresh and ask again before concluding the "
    "symbol does not exist."
)

## What replaces the strong wording. It names the action, because "route, don't disclaim" is the
## standing rule here: a hedge that does not say what to do next just spends bytes.
_UNEARNED_DEFINITIVE = (
    " NOT DEFINITIVE: this index was built by an older pipeline than this server (see `staleness` "
    "below), so a layer this query needs may be missing rather than empty. Call "
    "index(action='refresh', force=True) and ask again before concluding the repository has none."
)

## The claim being withdrawn, and the instruction that rides with it. Matched case-insensitively
## on the two phrases every definitive note in this module shares.
_DEFINITIVE_CLAIMS = ("definitive", "do not retry")


## @brief Withdraw an unearned definitive-negative claim when the index is schema-stale.
## @details ONE REPLY MUST NOT MAKE TWO INCOMPATIBLE CLAIMS. An empty result carried the standard
##          note — "a definitive empty result from the database ... Do not retry this query or
##          fall back to guessing" — beside a staleness block stating that whole layers may be
##          missing. A caller acting on the first half concludes the repository has no locks; the
##          cause was an unrebuilt index. That is this project's own lesson ("no rows" is a claim
##          about the DETECTOR) shipped as a default, and it is the likeliest first bug report
##          from someone who has just upgraded.
##
##          DELIBERATELY NOT AN ABSENT-CORPUS DOWNGRADE. gh#393 proposed a second one of those
##          inside `_verdict` and it was BUILT AND REVERTED, because most indexes lacking a layer
##          lack it because a fixture never made one, so downgrading on absence hedges nearly
##          every reply and spends the strong wording gh#31 earned. This keys on a MEASURED fact
##          about this database that the same reply already reports, fires only on the `schema`
##          axis, and lives at the one place staleness is stamped rather than inside any
##          per-query verdict — so no tool's own reasoning changes.
## @param payload The reply, staleness already attached.
## @param staleness The notices attached to this reply.
##
## v3: a `partial` axis withdraws a definitive negative too, with its own sentence — the
## schema remedy (refresh with force) would only re-run the doxygen that failed.
## v4 (1.3.5): so does the `derived` axis, a fast in-place refresh awaiting its full refresh.
## @req REQ-DDB-MCP-004
## @version 4
def _withdraw_definitive(payload: dict[str, Any], staleness: list[dict[str, str]]) -> None:
    """@brief Withdraw a definitive-negative claim a stale index cannot earn. @version 3"""
    note = payload.get("note")
    if not isinstance(note, str):
        return
    axes = {n.get("axis") for n in staleness}
    ## Two different unearned-ness conditions, and they need different sentences: `schema` means a
    ## layer may be MISSING, `data` means the symbol may POSTDATE the build (gh#12). The data case
    ## is restricted to a subject miss — see `_DATA_AXIS`.
    replacement = None
    if _SCHEMA_AXIS in axes:
        replacement = _UNEARNED_DEFINITIVE
    elif _PARTIAL_AXIS in axes:
        replacement = _UNEARNED_BY_PARTIAL
    elif _DERIVED_AXIS in axes:
        replacement = _UNEARNED_BY_DERIVED
    elif _DATA_AXIS in axes and payload.get("found") is False:
        replacement = _UNEARNED_BY_DRIFT
    if replacement is None:
        return
    lowered = note.lower()
    if not any(claim in lowered for claim in _DEFINITIVE_CLAIMS):
        return
    ## Rewritten rather than appended-to: leaving "this is a definitive empty result" in place and
    ## adding "not definitive" after it is two claims again, in one sentence.
    ## The split DROPS the old advice as well as the old claim, which is the point: the reported
    ## note spent its second half telling the reader to check `target`, and `target` was right.
    kept = re.split(r"(?i)this is a definitive|do not retry", note)[0].rstrip()
    payload["note"] = f"{kept}{replacement}"


## The claim a partial answer cannot make, matched where every definitive note in this module
## makes it. `a definitive negative` is the batch entry's spelling of the same sentence.
_DEFINITIVE_SPLIT = r"(?i)this is a definitive|(?<!not )a definitive negative|do not retry"


## @brief A name list capped for a reply, with the overflow counted in a final entry.
## @param names Every name.
## @return At most `MAX_LISTED_SIBLINGS` names, plus one "+N more" entry when any were dropped.
## @version 1
## @dg_internal
def _bounded_names(names: tuple[str, ...]) -> list[str]:
    """@brief Cap a name list for a reply. @return The capped list. @version 1"""
    shown = list(names[:MAX_LISTED_SIBLINGS])
    if len(names) > MAX_LISTED_SIBLINGS:
        shown.append(
            f"+{len(names) - MAX_LISTED_SIBLINGS} more — index(action='targets') lists them"
        )
    return shown


## What a HIT from one part of a split repository says about its own unresolved edges. gh#48 ask 3:
## "a dossier answered from first-party whose callees live in a vendored sub-index should say so,
## rather than presenting an apparently complete neighbour list." A miss is rewritten by
## `_scope_definitive`; a hit reads as complete, which is why it needs saying here.
_UNRESOLVED_ACROSS_INDEXES = (
    "{count} call site(s) in `external_callees` resolve to no function in THIS index, and this "
    "answer read only sub-index {name!r} — `not_searched` lists the parts of this repository it "
    "did not read, and an unresolved name may be defined in one of them. Ask again with "
    "sub_index=<one of those> to follow the edge."
)


## @brief Say that a hit's unresolved call sites may resolve in a part this answer did not read.
## @param payload The reply or batch entry.
## @param answered_from The sub-index that answered.
## @return None.
## @version 1
## @req REQ-DDB-MCP-001
def _scope_hit(payload: dict[str, Any], answered_from: str) -> None:
    """ONLY WHEN THERE IS AN EDGE TO EXPLAIN. A first-party hit whose every callee resolved is
    complete as far as the question goes, and annotating it would be the over-hedging gh#393
    reverted. `external_callees` being non-empty is the measured signal that something this
    reply names is defined somewhere it did not look.

    @brief Annotate a hit whose unresolved edges may cross into an unread index.
    @return None.
    @version 1
    """
    external = payload.get("external_callees")
    if payload.get("found") is False or not external:
        return
    payload["scope_note"] = _UNRESOLVED_ACROSS_INDEXES.format(
        count=len(external), name=answered_from
    )


## @brief Withdraw a definitive negative that was answered from one part of a split repository.
## @details gh#48. A bare call on a split repository is answered from its first-party index, and a
##          symbol that lives in a vendored tree came back "a definitive negative from the
##          database" — a confident false negative about code one index over. The measured fact
##          is `not_searched`: the same reply names built indexes it did not read. So a negative
##          is scoped to the part that answered and routed to the parts that did not.
##
##          ONLY ON A NEGATIVE — a subject miss, or an empty result list. A hit from first-party is
##          a hit; hedging every reply because siblings exist is the over-hedging gh#393 reverted.
## @param payload The reply or batch entry, whose note may carry a definitive claim.
## @param answered_from The sub-index that answered.
## @return None.
## @version 1
## @req REQ-DDB-MCP-004
def _scope_definitive(payload: dict[str, Any], answered_from: str, others: bool = True) -> None:
    """`others` SAYS WHETHER ANY OTHER PART IS ON RECORD. Found by driving a model at a fixture
    (gh#48 ask 5): a first-party index built by the CLI registers no sibling and records no
    split, so `not_searched` was empty and the negative kept its definitive wording — and the
    model then reported a symbol as absent from the REPOSITORY. The repository still declares
    itself split in `.gitmodules`; with no names to offer, the reply says how to find them.

    @brief Scope a negative to the sub-index that answered it.
    @version 2
    """
    note = payload.get("note")
    negative = payload.get("found") is False or payload.get("count") == 0
    if not isinstance(note, str) or not negative:
        return
    if not re.search(_DEFINITIVE_SPLIT, note):
        return
    kept = re.split(_DEFINITIVE_SPLIT, note)[0].rstrip()
    where = (
        "`not_searched` lists this repository's other parts. Ask again with sub_index=<one of "
        "those> before concluding it does not exist — a part with no index yet starts building "
        "on that call."
        if others
        else "this repository is split into parts and no other part is indexed yet. Call "
        "index(action='targets') to see them, and refresh one with sub_index=<name> before "
        "concluding it does not exist."
    )
    payload["note"] = (
        f"{kept} NOT DEFINITIVE FOR THE REPOSITORY: only sub-index {answered_from!r} was "
        f"searched, and {where}"
    )


## @brief Trim a row list to the byte budget, describing what it dropped.
## @param rows Serialized rows.
## @param budget Byte budget for the whole response.
## @param overhead Bytes already committed to envelope fields.
## @param arg_name Name of the caller-visible argument this list is governed by.
## @param how_to_narrow Advice for getting the rest.
## @param ceiling Byte ceiling this ONE payload must fit, or None for the whole-response default.
## @return (kept rows, `_limited` block or None).
## @version 2
## @dg_internal


## The key `_shrink_to_budget` reports a depth step under. NOT a field name — it is the one
## entry in that mapping that does not describe a list, which is why it is spelled distinctly
## and why `_limited` words it as a depth rather than as a count.
CHAIN_DEPTH_CUT = "chain_depth"


## @brief Drop the outermost ring of a payload's causal chain, if it has one.
## @param payload The dossier payload, possibly carrying a `chain` block.
## @return The depth that was dropped, or None when there is nothing left to step.
## @version 1
## @dg_internal
def _step_chain_depth(payload: dict[str, Any]) -> int | None:
    """gh#383. THE CHAIN WAS NEVER BUDGETED AT ALL, which is a sharper statement than the
    plan's "step depth before halving". `_DOSSIER_LISTS` holds TOP-LEVEL keys and
    `payload["chain"]` is a nested dict of `nodes`/`hops`, so `_shrink_to_budget` could
    not see it: an oversized chain was carried in full while the IMMEDIATE neighbours —
    `callers`, `callees`, the highest-value rows in the reply — were halved to pay for it.

    Depth 1 is adjacency, which the populated section already carries; depth 2+ is
    traversal. So the outermost ring is the cheapest thing in the payload to lose and the
    immediate neighbours are the dearest, and the old order spent them in exactly the wrong
    sequence. Fan-out is roughly geometric, so one ring usually frees more than several
    halvings of a neighbour list would.

    NODES CARRY THEIR OWN `depth` and hops reference nodes BY NAME, so a ring can be
    removed exactly rather than estimated: drop every node at the maximum depth, then every
    hop that touches a name no longer present. A hop kept after its endpoint left would
    assert an edge into nothing.

    Returns the depth removed so the caller can disclose it. Stops at depth 1 — stripping
    that too would leave a `chain` block claiming a traversal with no reachable nodes, which
    is worse than a smaller chain.

    @brief Remove the outermost depth ring from the chain.
    @return The dropped depth, or None.
    @version 1
    """
    chain = payload.get("chain")
    if not isinstance(chain, dict):
        return None
    nodes = chain.get("nodes")
    if not isinstance(nodes, list) or not nodes:
        return None
    depths = [n.get("depth", 0) for n in nodes if isinstance(n, dict)]
    deepest = max(depths, default=0)
    if deepest <= 1:
        return None
    chain["nodes"] = [n for n in nodes if not (isinstance(n, dict) and n.get("depth") == deepest)]
    kept = {n.get("name") for n in chain["nodes"] if isinstance(n, dict)}
    hops = chain.get("hops")
    if isinstance(hops, list):
        chain["hops"] = [
            h
            for h in hops
            if isinstance(h, dict) and h.get("from_name") in kept and h.get("to_name") in kept
        ]
    return deepest


## @brief Spend chain DEPTH, then halve the largest list, until the payload fits.
## @param payload The reply being trimmed, mutated in place.
## @param list_keys Top-level list fields eligible for row trimming.
## @param ceiling Byte ceiling this ONE payload must fit, or None for the whole-response default.
## @return Field name → ORIGINAL length for each field cut, plus `chain_depth` when a ring went.
## @version 3
## @dg_internal
def _shrink_to_budget(
    payload: dict[str, Any], list_keys: tuple[str, ...], ceiling: int | None = None
) -> dict[str, int]:
    """SELF-LIMITING, AND IT SAYS SO. A silent truncation is the worst option
    available: a model handed 82 of 331 rows with no indication believes it has the
    whole picture and reasons confidently from a quarter of the evidence. That is the
    same failure class as every silent-degradation bug recorded here — an empty layer
    read as "no dataflow", a refused judge verdict read as "not measured".

    CONVERGES ON THE ACTUAL SERIALIZED SIZE by halving the largest list until the
    payload fits. An earlier version estimated from a 5-row sample and multiplied,
    which failed twice: the estimate ran UNDER, so the response stayed above the cap;
    and spending the budget list-by-list in declaration order charged small lists for
    what large ones had consumed, cutting a 2-element list to 1 while reporting "full
    response would be about 540 bytes" against a 32 KB cap. Measuring beats
    estimating when the measurement is one `json.dumps` away.

    Halving rather than computing an exact keep-count is deliberate: row sizes vary by
    an order of magnitude within one list, so any arithmetic on a mean is a guess.
    Halving converges in at most ~log2(n) passes and each pass is measured.

    `ceiling` IS A PARAMETER BECAUSE A BATCH SHARES ONE RESPONSE. When several dossiers
    travel in one reply they must divide the 32,768 bytes between them, not each claim
    it — five dossiers trimmed to the whole-response ceiling would produce a 160 KB
    reply that respects the cap five times over and exceeds it once. The default is the
    single-payload ceiling, so every existing caller is unchanged.

    @brief Halve the largest list until the payload fits, reporting what was cut.
    @return Mapping of field name to its ORIGINAL length, for fields that were cut.
    @version 2
    """
    original = {
        key: len(payload[key])
        for key in list_keys
        if isinstance(payload.get(key), list) and payload[key]
    }
    if ceiling is None:
        ceiling = RESPONSE_BUDGET_BYTES - _LIMITED_BLOCK_ALLOWANCE

    ## DEPTH FIRST, ROWS SECOND (gh#383). The outermost chain ring is the cheapest content
    ## in the payload and the immediate neighbours are the dearest, so they are spent in
    ## that order. Recorded under a reserved key rather than mixed into `original`, because
    ## "depth reduced 3 -> 1" and "callers 331 -> 82" are DIFFERENT FACTS and collapsing
    ## them into one number is how a caller comes to think it has the whole graph.
    stepped: list[int] = []
    while len(json.dumps(payload, default=str)) > ceiling:
        dropped = _step_chain_depth(payload)
        if dropped is None:
            break
        stepped.append(dropped)

    for _ in range(64):
        if len(json.dumps(payload, default=str)) <= ceiling:
            break
        biggest = max(
            original,
            key=lambda k: len(payload.get(k) or []),
            default=None,
        )
        if biggest is None or len(payload.get(biggest) or []) <= 1:
            break  # nothing left to give; the non-list fields alone exceed the cap
        payload[biggest] = payload[biggest][: max(1, len(payload[biggest]) // 2)]

    cut = {k: was for k, was in original.items() if was > len(payload.get(k) or [])}
    if stepped:
        cut[CHAIN_DEPTH_CUT] = max(stepped)
    return cut


## @brief A dossier with its depth-1 callers and callees capped at `cap`, each cut disclosed.
## @param doss The flattened, budgeted dossier, or None.
## @param cap The per-list limit.
## @return The dossier.
## @version 1
## @dg_internal
def _capped_neighbors(doss: dict[str, Any] | None, cap: int) -> dict[str, Any] | None:
    """THE PARAMETER SAID IT CAPPED, AND AT DEPTH 1 IT DID NOT. `max_neighbors` reached only a
    depth > 1 walk, so a depth-1 reply listed every caller up to the byte budget. Capped here, and
    NEVER SILENTLY: the cut list's `_limited` entry carries `total_available` — the single most
    useful fact about a hub — and says to raise `max_neighbors` for the rest.

    @brief Cap and disclose depth-1 neighbours.
    @return The dossier.
    @version 1
    """
    if doss is None or cap < 1:
        return doss
    for field_name in ("callers", "callees"):
        rows = doss.get(field_name)
        if not isinstance(rows, list) or len(rows) <= cap:
            continue
        doss[field_name] = rows[:cap]
        block = _limited_block(
            field_name,
            len(rows),
            cap,
            f"raise `max_neighbors` (currently {cap}) to list more of the {len(rows)} {field_name}",
        )
        block["reason"] = f"`max_neighbors` lists at most {cap} {field_name} per symbol"
        limited = doss.setdefault("_limited", {})
        if field_name in limited:
            limited[field_name]["total_available"] = max(
                limited[field_name].get("total_available", 0), len(rows)
            )
        else:
            limited[field_name] = block
    return doss


## @brief Build the `_limited` disclosure for one trimmed field.
## @param field_name Field that was reduced.
## @param was Its original length.
## @param now Its length after trimming.
## @param how_to_narrow Advice for retrieving the rest.
## @return The disclosure block.
## @version 1
## @dg_internal
def _limited_block(field_name: str, was: int, now: int, how_to_narrow: str) -> dict[str, Any]:
    """Names the FIELD and its before/after count, so the degradation is
    reproducible and reversible by the caller rather than a hidden policy; reports
    `total_available`, which turns a truncation into a MEASUREMENT — "this symbol has
    331 callers" is the single most useful fact about a hub; and says how to get the
    rest.

    @brief Describe one field's reduction.
    @return Disclosure dict.
    @version 1
    """
    return {
        "reason": f"the full response exceeded the {RESPONSE_BUDGET_BYTES:,}-byte cap",
        "adjusted": {field_name: f"{was} -> {now}"},
        "total_available": was,
        "how_to_narrow": how_to_narrow,
    }


## Nested lists inside a dossier, longest-first, that a budget may trim. Ordered so
## the biggest contributor is reduced before the smaller ones — trimming `writes`
## while 331 `callers` remain would achieve nothing.
_DOSSIER_LISTS = (
    "callers",
    "callees",
    "writes",
    "reads",
    ## gh#32. The virtual fan-out, both directions, and the largest of the four function lists
    ## that had no trimmer: 46 rows on entropic's widest interface and 39 on sassafras-class,
    ## set by the codebase rather than by anything this repository controls.
    "overridden_by",
    "overrides",
    "covering_tests",
    "candidates",
    ## The one-shot panels are budgeted like every other list. `locks_held` is the one
    ## that can grow without bound — a section carries its FULL membership, and a
    ## widely-called function under a coarse lock can be inside many of them.
    "sections",
    "locks_held",
    "context_conflicts",
    "external_callees",
    ## gh#373. Budgeted like the rest even though the realistic count is one to three:
    ## a `#define` conditionally redefined per platform can have dozens of sites, and a
    ## list left out of the budget is a list that grows without one.
    "macros",
    ## Budgeted for the same reason as `macros` directly above, and measured: mbedtls declares
    ## twelve alternate config profiles plus several test configs, so one option can carry a dozen
    ## sites. TRIMMING IS SAFE HERE ONLY BECAUSE THE ORDER IS LOAD-BEARING —
    ## `config_defaults_conn` sorts shipped-config first, then declared over heuristic, so a
    ## trim drops alternate profiles and keeps the row that answers "what does the default build
    ## do". Reordering that sort would make this budget lossy in the one way that matters.
    "config_defaults",
    ## 1.3.0. A class's merged same-name declarations: one in practice (a TypeScript interface
    ## twin), but each row is independent, so a trim drops whole declarations, never half of one.
    "merged",
    ## 1.3.0. A requirement's mentions across the indexed files: one row per line, independent,
    ## and on a widely cited requirement there can be dozens.
    "mentioned_in",
    ## gh#372 — the lists the NON-FUNCTION subject kinds contribute. A key that is not in
    ## this tuple is a list nothing can trim, so a subject kind added without its lists
    ## reintroduces the unbounded payload one kind at a time. Named here rather than
    ## derived, because deriving them would mean trimming any list-shaped key including
    ## ones whose truncation is meaningless (`also`, `bases`).
    ## The files one generator produces. Bounded by the repository rather than by clew — mbedtls
    ## has 13 generated outputs and one script could plausibly produce many — so it is budgeted
    ## like every other list. Trimming is safe here because the entries are bare basenames and
    ## `generated_by` on each produced file carries the detail.
    "generates",
    "sites",
    "siblings",
    "implementers",
    "tests",
    ## gh#32. An enum's values, which doxygen emits none of — so this list is entirely
    ## recovered rows, and its length is the enum's length: 75 in entropic's widest, 640
    ## measured at 46,647 bytes against a 65,536-byte cap. Bounded by the source, not by clew.
    "enumerators",
    "members",
    "symbols",
    "gates",
    ## gh#32. Capped at 400 names by `_gate_symbol_names`, which bounds it but does not make it
    ## small: 400 config symbols is a sizeable share of the whole budget, and `gates` beside it
    ## is already trimmed. A bounded list still has to yield when the payload as a whole does.
    "gate_symbol_names",
    ## The FUNCTION subject's preconditions, which is the other direction from the config
    ## subject's `gates` above and therefore a separate key. Budgeted because a function inside
    ## deeply nested conditionals can be covered by several, and mbedtls nests them freely.
    "gated_by",
    "threads",
    ## gh#32. Small on every target measured — 6 requirement edges on the widest symbol in
    ## entropic — and listed anyway: the reason a list is in this tuple is that it CAN grow,
    ## and a repository that tags every function is the one where these two do.
    "requirements",
    "termini",
    "nodes",
    "hops",
)


## How to get the rest of a trimmed panel. A MAPPING rather than one interpolated
## sentence because the default read `call {field}() directly` and NONE of the one-shot
## panels has a focused tool any more — a truncation disclosure that names a nonexistent
## tool sends the reader on a call that fails, which is worse than saying nothing.
##
## `sections_in`, `locks_held_when` and `source` USED to be the named remedy here and were
## deleted with the rest of the per-symbol tools: their whole payload is now these panels,
## so the remedy for a trimmed panel is the one route that still widens it. For the two
## lock panels that is the LOCK-KEYED inventory, which is a different question class and
## survives; for a body it is raising the cap on this same call.
_DOSSIER_HINTS = {
    "sections": "call search(corpus='locks') for the unabridged lock-keyed inventory",
    "locks_held": "call search(corpus='locks') for the unabridged lock-keyed inventory",
    "external_callees": (
        "no focused tool returns these — read the body at the reported line range for the remainder"
    ),
    ## gh#373. Says NO ROUTE rather than naming one, because there is none and the
    ## near-miss is worse than silence: `search` finds the macro by name but collapses
    ## to one row per distinct name, so it cannot enumerate the remaining sites. A hint
    ## pointing at it would send a reader to a tool that answers a different question
    ## and looks like it answered this one.
    ## The definition sites of every symbol named here now ride along in `gate_definitions`, so
    ## this no longer has to route for the commonest follow-up ("where is that symbol written
    ## down"). What it still routes for is the question a single payload genuinely cannot hold.
    "gated_by": (
        "each gate symbol's own definition sites are in `gate_definitions` on this reply; call "
        "search(corpus='config') for the full configuration space — the gates shown are the "
        "innermost by line"
    ),
    "macros": (
        "no tool enumerates definition sites — search() collapses a name to one row; "
        "the sites shown are the first by file and line"
    ),
}


## @brief Trim a serialized dossier's nested lists to the response budget.
## @param doss Serialized dossier, or None.
## @return The dossier, trimmed and annotated when it exceeded the budget.
## @version 4
## @dg_internal
def _budgeted_dossier(doss: dict[str, Any] | None) -> dict[str, Any] | None:
    """`dossier` is the tool a model is told to CALL FIRST, and it was the largest
    unbounded response in the surface: **125,559 bytes measured** for a symbol with
    331 callers.

    Trims the nested lists rather than refusing the call, because the identity
    fields — signature, file, brief, liveness, thread membership — are small, always
    wanted, and are the reason the tool is called first. Losing them to protect the
    budget would defeat the purpose; losing the 300th caller costs nothing.

    Each trimmed list gets its own `_limited` entry naming the field and its
    before/after count, so a model can see WHICH panel was reduced instead of being
    told the response was "large".

    Ends by ELIDING the one-shot panels that say nothing (`_DOSSIER_OPTIONAL`), after
    trimming rather than before: a panel `_shrink_to_budget` reported in `_limited`
    always keeps at least one row, so the disclosure can never end up describing a key
    that was then removed.

    @brief Trim a dossier's nested lists to budget, reporting each reduction.
    @return The dossier, possibly trimmed, with a `_limited` block when it was.
    @version 2
    """
    if doss is None:
        return None
    cut = _shrink_to_budget(doss, _DOSSIER_LISTS)
    if cut:
        ## The depth step is worded as a DEPTH, not as a row count (gh#383). Reusing
        ## `_limited_block` here would print "chain_depth: 3 -> 0" and offer to call
        ## `chain_depth()`, which is neither a field nor a tool — a disclosure that
        ## misdescribes what it cut is worse than the silence it replaced.
        depth = cut.pop(CHAIN_DEPTH_CUT, None)
        doss["_limited"] = {
            field_name: _limited_block(
                field_name,
                was,
                len(doss.get(field_name) or []),
                _DOSSIER_HINTS.get(
                    field_name,
                    f"re-ask dossier for a focused view of `{field_name}`, passing "
                    f"`qualified` first if the name is overloaded",
                ),
            )
            for field_name, was in cut.items()
        }
        if depth is not None:
            doss["_limited"][CHAIN_DEPTH_CUT] = {
                "reason": (
                    f"the full response exceeded the {RESPONSE_BUDGET_BYTES:,}-byte cap, so "
                    f"the chain's outermost ring(s) were dropped BEFORE any neighbour list "
                    f"was trimmed — depth 1 is adjacency and the section already carries it"
                ),
                "depth_dropped_at_or_above": depth,
                "how_to_narrow": (
                    "re-ask with a lower depth= to get a complete chain, or depth=1 for "
                    "adjacency alone"
                ),
            }
    return wire.prune_absent_keys(doss, _DOSSIER_OPTIONAL)


## Headroom for the BATCH `_limited` block. Larger than the single-payload allowance
## because the disclosure is per symbol AND per field: eight symbols each losing three
## panels is 24 entries. Each entry is a short `"symbol.field": "31 -> 8"` pair (~45
## bytes measured) rather than the single-payload block's four-key dict, because
## repeating the same `reason` and `how_to_narrow` 24 times would cost more than the
## rows it is apologising for. Those two strings are hoisted to the block itself.
_BATCH_LIMITED_ALLOWANCE = 2_400


## @brief Divide a byte budget between payloads so no one of them starves.
## @param sizes Serialized size of each payload, in request order.
## @param total Bytes available to all of them together.
## @return Per-payload byte ceiling, same order.
## @version 1
## @dg_internal
def _fair_shares(sizes: list[int], total: int) -> list[int]:
    """MAX-MIN FAIR, not equal, and the difference is the whole point of the function.

    An equal split wastes budget: a two-field dossier for an undocumented static helper
    might serialize to 900 bytes, and handing it 6,500 anyway strands 5,600 that the
    331-caller hub in the same batch desperately needs. So every payload that fits
    inside an equal share takes exactly what it needs and RELEASES the remainder, which
    is then re-divided among the ones still over. Repeat until nobody is under.

    The failure this avoids is the one the task names: a batch where symbol 1 arrives
    complete and symbol 5 arrives empty is worse than five thin ones, because the reader
    cannot tell truncation from absence. Under max-min fairness the smallest payload is
    the LAST thing cut — no symbol is trimmed while a larger one is still above its
    share.

    Terminates: each pass either removes at least one index from `pending` or assigns
    the even share to all of them and stops.

    @brief Waterfill a byte budget across payloads.
    @return One ceiling per payload.
    @version 1
    """
    shares = [0] * len(sizes)
    pending = set(range(len(sizes)))
    remaining = total
    while pending:
        even = max(remaining // len(pending), 1)
        under = [i for i in pending if sizes[i] <= even]
        if not under:
            for i in pending:
                shares[i] = even
            break
        for i in under:
            shares[i] = sizes[i]
            remaining -= sizes[i]
            pending.discard(i)
    return shares


## @brief Trim a batch of serialized dossiers to ONE shared response budget.
## @param entries Serialized dossiers (misses already replaced by their envelopes), in request order.
## @param overhead Bytes the surrounding envelope already commits.
## @return The `_limited` block naming every symbol/field pair that lost rows, or None.
## @version 1
## @dg_internal
def _budget_batch(entries: list[dict[str, Any]], overhead: int) -> dict[str, Any] | None:
    """N DOSSIERS SHARE THE CAP, THEY DO NOT MULTIPLY IT. `_budgeted_dossier` trims one
    payload against the whole-response ceiling, which is correct for one and catastrophic
    for five.

    THE DISCLOSURE NAMES THE SYMBOL, NOT JUST THE FIELD. In a single-symbol reply
    `_limited: {callers: ...}` is unambiguous because there is only one subject; in a
    batch it is useless. Keys are `"<symbol>.<field>"` so a reader can see that
    `psa_get_and_lock_key_slot` lost callers while the other four are intact — which is
    exactly the "is this truncation or absence?" question a batch makes easy to get
    wrong.

    @brief Divide the response budget across a batch, disclosing per-symbol cuts.
    @return The batch `_limited` block, or None when nothing was trimmed.
    @version 1
    """
    available = RESPONSE_BUDGET_BYTES - _BATCH_LIMITED_ALLOWANCE - overhead
    sizes = [len(json.dumps(e, default=str)) for e in entries]
    adjusted: dict[str, str] = {}
    for entry, share in zip(entries, _fair_shares(sizes, available), strict=True):
        cut = _shrink_to_budget(entry, _DOSSIER_LISTS, ceiling=share)
        for field_name, was in cut.items():
            adjusted[f"{entry.get('name', '?')}.{field_name}"] = (
                f"{was} -> {len(entry.get(field_name) or [])}"
            )
    if not adjusted:
        return None
    return {
        "reason": (
            f"{len(entries)} dossiers shared the {RESPONSE_BUDGET_BYTES:,}-byte response "
            "cap, so each got a fair share of it"
        ),
        "adjusted": adjusted,
        "how_to_narrow": (
            "ask for FEWER symbols in one call — a single-symbol dossier gets the whole "
            "budget — or name the one symbol you need in full"
        ),
    }


## @brief Serialize a list of R2 dataclasses to plain JSON types, within the response budget.
## @param items Iterable of dataclass instances.
## @return List of dicts.
## v10 (1.3.1): the envelope and its emptiness notes moved to `clew.query.export.envelope`, shared
## with the export API; this adds only the byte budget, which belongs to the MCP boundary.
## @version 10
## @dg_internal
def _many(
    items: Any,
    *,
    kind: str = "results",
    subject: str | None = None,
    diagnose: Diagnoser | None = None,
) -> dict[str, Any]:
    """THE SHARED ENVELOPE, THEN THE BUDGET. Everything that makes an empty list legible — the
    explicit `count`, the strong default note, a graded note when `diagnose` says emptiness can
    have another cause — is `clew.query.export.envelope`, so an export caller gets the same words.
    Only the trim is here: it is lossy and exists to protect a model's context window.

    `count` reports the TRUE total, not the rows shown, so the `_limited` block can disclose the
    difference.

    @brief Serialize a list of dataclass results with explicit emptiness, budgeted.
    @param items Iterable of dataclass results.
    @param kind Plural noun for what was searched for (e.g. "callers").
    @param subject What it was searched for (e.g. a function name).
    @param diagnose Optional callable supplying a graded note + extra keys when empty.
    @return Envelope dict with `count`, `kind`, `results`, and `note` if empty.
    @version 12
    """
    out = _export.envelope(items, kind=kind, subject=subject, diagnose=diagnose)
    cut = _shrink_to_budget(out, ("results",))
    if cut:
        out["_limited"] = _limited_block(
            kind,
            cut["results"],
            len(out["results"]),
            f"re-query with a narrower subject, or use search to scope before asking for {kind}",
        )
    return out


## @brief The one message a caller gets when the database they need does not exist yet.
## @param repo_path Repository the missing database would describe, or "" when unknown.
## @return An actionable sentence naming the call that fixes it.
## @version 2
## @req REQ-DDB-MCP-003
def unbuilt_index_message(repo_path: str = "") -> str:
    """SPELLED ONCE, because it was spelled twice and neither copy covered the common path. The
    ROUTED path checked `is_file()` and raised this; the DERIVED path did not, so a query against
    a server whose target had no database raised `sqlite3.OperationalError: unable to open
    database file` — naming neither the repository, nor that an index is missing, nor the call
    that builds one.

    That asymmetry is why `dossier` and `search` were REGISTERED conditionally: a tool that dies
    with a driver error is worse than an absent one. A tool that says what to call next is better
    than both, which is what lets the registration gate go away.

    SPELLED IN `routing.no_index_message` SINCE gh#48, with the split-aware refusal, so the
    three wordings that had already drifted once cannot drift again. This shape has no registry
    behind it — it is `QueryTools` bound to one database — so it states the sentence and no
    sub-index clauses.

    @brief The actionable message for an index that has not been built.
    @return The message.
    @version 2
    """
    what = repo_path or "the repository these tools are bound to"
    target = f", target={repo_path!r}" if repo_path else ""
    return no_index_message(what, f"index(action='refresh'{target})")


## @brief Tier-1 tool implementations, routed per call to any indexed repository.
## @version 2
class QueryTools:
    """Holds the providers for the DERIVED target (callables resolving its db path, repo
    root and staleness at call time, so a retarget needs no re-binding) plus an answerer
    that resolves a target a CALL named. Exposes one bound method per R2 function;
    methods are registered with `FastMCP.add_tool`, and each one is a call + `asdict`.

    Stateless with respect to the target: nothing a routed call resolves is remembered,
    so two calls naming two repositories in either order give the same answers.

    @brief Bound tier-1 tool methods, routable to any indexed repository.
    @version 2
    """

    ## @brief Construct the tool set around a db-path provider.
    ## @param db_provider Callable returning the active clew.db path.
    ## @param repo_provider Callable returning the active repo root (needed to read source text).
    ## @param staleness_provider Callable returning the staleness axes in play, or None for no annotation.
    ## @param answerer Callable resolving a caller-supplied target string, or None for a single-repository tool set.
    ## @version 4
    ## @dg_internal
    def __init__(
        self,
        db_provider: DbProvider,
        repo_provider: RepoProvider | None = None,
        staleness_provider: StalenessProvider | None = None,
        answerer: Answerer | None = None,
    ) -> None:
        self._db_provider = db_provider
        self._repo_provider = repo_provider
        self._staleness_provider = staleness_provider
        self._answerer = answerer

    ## @brief Resolve an explicit per-call target, refusing when this set cannot route.
    ## @param target Target string the caller supplied.
    ## @return The repository that answers for it.
    ## @version 1
    ## @dg_internal
    def _route(self, target: str, sub_index: str | None = None) -> Answering:
        """Refusing beats falling back. A tool set with no answerer is bound to one
        database, and serving that database for a call that named a different one would
        produce a reply whose `target` field names the bound repository — which reads as a
        successful routed call and hides the mistake completely.

        @brief Resolve a routed target, or say this tool set cannot route.
        @return The resolved repository.
        @version 2
        """
        if self._answerer is None:
            raise RuntimeError(
                f"These tools cannot route to {target!r}: they are bound to a single "
                "repository. Call status to see which repository answers here."
            )
        return self._answerer(target, sub_index)

    ## @brief The database path this call reads.
    ## @param target Repository to read, or None for the one the server derived.
    ## @param sub_index Name of the part to read, or None for the whole repository.
    ## @return Path to the clew.db the tools should read.
    ## @version 5
    ## @req REQ-DDB-MCP-003
    def db(self, target: str | None = None, sub_index: str | None = None) -> Path:
        """Resolve the db path for this call: the routed target when one was named, else
        the derived one. Omitting `target` reproduces the previous behaviour exactly.

        `sub_index` NAMES THE PART, not a suffix on `target`. A composite string a caller has to
        construct (`f"{target}#{name}"`) has no schema of its own for a model to read; a second
        parameter does — `list_targets` reports the legal names, and the tool's own schema says
        the parameter exists.

        @brief Resolve this call's database path.
        @return clew.db path.
        @version 4
        """
        if target is not None:
            return self._route(target, sub_index).db
        if sub_index is not None:
            raise RuntimeError(
                f"sub_index={sub_index!r} was given without target — a sub-index belongs to a "
                "named repository, so target= must be stated too."
            )
        ## GUARDED HERE, NOT ONLY ON THE ROUTED PATH. Every tier-1 tool funnels through this
        ## method, so one check covers the whole surface; the routed branch above already refuses
        ## inside `resolve_target`. Without this, a derived target with no database reached
        ## sqlite3 and surfaced `unable to open database file`.
        db = Path(self._db_provider())
        if not db.is_file():
            raise RuntimeError(unbuilt_index_message())
        return db

    ## @brief The working-tree root this call reads source from.
    ## @param target Repository to read, or None for the one the server derived.
    ## @param sub_index Name of the part to read, or None for the whole repository.
    ## @return Path to the repo the answering database was built from.
    ## @version 4
    ## @req REQ-DDB-MCP-003
    def repo(self, target: str | None = None, sub_index: str | None = None) -> Path:
        """Resolve the working tree the recorded paths are relative to. The model is
        NEVER asked for it as a filesystem path — it names a repository and the server
        resolves it, or it names none and the server's derived target answers.

        A SUB-INDEX SHARES ITS PARENT'S WORKING TREE. Every sub-index of one repository is built
        with `repo_root` set to the same root (Phase 1), so recorded paths are already relative to
        it regardless of which sub-index answered — routing to a sub-index changes the DATABASE,
        never the tree its paths are read against.

        @brief Resolve this call's repo root.
        @return Repo root path.
        @version 4
        """
        if target is not None:
            return self._route(target, sub_index).repo
        if self._repo_provider is None:
            raise RuntimeError(
                "No repo root bound to these tools — the server has no target. It "
                "derives one from --repo, $CLAUDE_PROJECT_DIR, or the client's "
                "roots/list; call status to see which, or name one with target=."
            )
        return self._repo_provider()

    ## @brief The working tree for this call, or None when there isn't one.
    ## @param target Repository to read, or None for the one the server derived.
    ## @param sub_index Name of the part to read, or None for the whole repository.
    ## @return Repo root, or None when no working tree is bound or resolvable.
    ## @version 2
    ## @dg_internal
    def _repo_or_none(self, target: str | None = None, sub_index: str | None = None) -> Path | None:
        """NON-RAISING, unlike `repo()`, and that is the whole reason it exists.

        `source` MUST fail loudly without a working tree — its entire answer is bytes off
        disk, so a silent empty reply would be indistinguishable from "this function has
        no body". `dossier` must not: the working tree is needed for two panels out of
        twenty fields, it answered without them for its whole life before the one-shot,
        and a tool set bound without a repo provider is the shape every unit test uses.
        Turning that into an exception would make the composite payload fail where the
        narrow tool it replaces succeeded.

        `sub_index` HAS TO REACH `repo()` HERE TOO, not only at the `db()` call beside it. A
        repository with ONLY sub-indexes has no whole-repository record for `resolve_target` to
        fall back on, so `repo(target, None)` raised "ambiguous bare root" and this method's own
        non-raising contract turned that into a silent `None` — the database routed correctly
        while the `body` panel vanished, reading exactly like "this function has no recorded
        source" instead of the routing gap it actually was.

        @brief Resolve this call's working tree, or None.
        @return Repo root or None.
        @version 2
        """
        try:
            return self.repo(target, sub_index)
        except (RuntimeError, ValueError, OSError):
            return None

    ## @brief The repository this reply answered from, for attribution.
    ## @param answering The routed repository, or None when the derived one answered.
    ## @return Repo root as a string, falling back to the database path.
    ## @version 3
    ## @dg_internal
    def _target_name(self, answering: Answering | None) -> str:
        """Non-raising by contract, unlike `repo()`. It is called on the way OUT of
        every reply, including replies that succeeded, so it must never be the thing
        that turns a good answer into an error. A tool set constructed without a repo
        provider is a test-only shape; naming the database there is still a truthful
        answer to "what answered this?".

        REPORTS THE REPO ROOT ONLY, deliberately, which is now shared by every sub-index of one
        repository — a reply from `extern-llama.cpp` names the same root a reply from
        `first-party` would. `_answered` stamps `sub_index` as its own key for exactly the reason
        this docstring's sibling warns about: two different databases must not produce
        indistinguishable `target` fields, or a reply from the wrong sub-index reads as correct.

        @brief Name the repository (or database) that answered.
        @return Target name.
        @version 3
        """
        if answering is not None:
            return str(answering.repo)
        provider = self._repo_provider if self._repo_provider is not None else self._db_provider
        return str(provider())

    ## @brief What to try instead, for a subject this index could not answer.
    ## @param subject The subject as the caller passed it.
    ## @param target Repository the call named, or None.
    ## @param sub_index Name of the part the call named, or None.
    ## @return A hint sentence, or "" when the index holds no neighbour.
    ## @version 1
    ## @dg_internal
    def _recovery_for(
        self, subject: str | None, target: str | None, sub_index: str | None = None
    ) -> str:
        """SAME TOLERANCE AS `_unresolved_for`, and for the same reason: this runs while building a
        reply that has already failed, so nothing here may turn a clean negative into a traceback.

        Measured on the 1.1.0 grid: the old miss note advised checking `target` and staleness,
        which is true and was almost never the problem — 80.6% of the 237 unanswered subjects were
        recoverable from what the index already held.

        @brief Probe for a recovery hint, tolerating any failure.
        @return The hint, or "".
        @version 1
        """
        if not subject:
            return ""
        try:
            return recovery_hint(self.db(target, sub_index), subject)
        except Exception:
            return ""

    ## @brief Unsupported kinds this index holds for a name that failed to resolve.
    ## @param subject The name that missed, or None.
    ## @param target Repository the call named, or None for the derived one.
    ## @param sub_index Name of the part the call named, or None.
    ## @return The unsupported kinds, or () when there are none or nothing can be read.
    ## @version 2
    ## @dg_internal
    def _unresolved_for(
        self, subject: str | None, target: str | None, sub_index: str | None = None
    ) -> tuple[str, ...]:
        """NEVER RAISES ON THE MISS PATH. This runs while building an answer that has already
        failed to find something, so a database that cannot be opened — the very case
        `unbuilt_index_message` exists for — must not turn a clean negative into a traceback.
        A probe that cannot run contributes no clause, which is the same discipline as
        `doxygen_supports_sqlite3` returning None rather than False.

        @brief Probe the unsupported kinds behind a miss, tolerating any failure.
        @return The kinds, or ().
        @version 2
        """
        if not subject:
            return ()
        try:
            return q.unresolved_kinds(self.db(target, sub_index), subject)
        except Exception:
            return ()

    ## @brief Stamp a reply with the target it came from, making a miss self-describing.
    ## @param payload The serialized reply, or None for "not found".
    ## @param kind What was looked for (e.g. "dossier").
    ## @param subject What it was looked for by (e.g. a function name).
    ## @param target Repository the call named, or None when the derived one answered.
    ## @param sub_index Name of the part the call named, or None.
    ## @return The reply, always a dict, always carrying `target` and any staleness.
    ##
    ## v9: the miss note carries a recovery hint. It previously advised checking `target` and
    ## staleness and nothing else — both true, and almost never the cause. Measured on the 1.1.0
    ## grid, 82 of 129 unanswered subjects were recoverable from what the index already held, so a
    ## model with the right target and a fresh index had nowhere to go but retry the same name.
    ## `found` is unchanged: a hint is an extra field on a negative.
    ## @version 9
    ## @dg_internal
    def _answered(
        self,
        payload: dict[str, Any] | None,
        *,
        kind: str = "result",
        subject: str | None = None,
        target: str | None = None,
        sub_index: str | None = None,
    ) -> dict[str, Any]:
        """EVERY REPLY NAMES THE REPOSITORY IT ANSWERED FROM (gh#22). The server no
        longer holds a target it was told to hold — it derives one — so "which
        repository is this?" has to be answerable from the payload rather than from a
        launch argument nobody can see. A stale target that no reply disclosed has
        already invalidated a 36-cell benchmark run: 15 of 18 cells said in prose that
        they were looking at the wrong repository, and all 36 were recorded valid.

        AND IT TURNS A BARE `None` INTO AN ENVELOPE, for the same reason `_many` turns
        a bare `[]` into one. A `None` from `dossier` means "not in this index", which
        is indistinguishable from "malformed call" — and it is the reply where the
        target matters MOST, because the commonest cause of a missing symbol is an
        index of the wrong repository. Returning None there would omit the attribution
        from precisely the case that motivated it.

        `found` is present only on a miss; a caller discriminates on it or on `note`,
        the same convention `_many` already uses for an empty list.

        AND IT CARRIES STALENESS, WHEN THERE IS ANY (gh#2). Same argument as the target
        stamp, one axis over: a payload should say what produced it, and "an index built
        before the edit you just made" is as much a property of what produced an answer as
        the repository is. `status` already said so, but only if asked — and a consumer
        looking at a confident, fresh-LOOKING answer has no reason to ask.

        ABSENT WHEN THE TOOL IS CURRENT, which is the half that keeps it worth reading.
        An annotation on every reply is an annotation nobody reads, and this repo's own
        record is that a warning which fires on the ordinary case gets ignored and then
        gets switched off.

        AND THE STAMP IS THE ROUTED REPOSITORY WHEN THE CALL NAMED ONE, resolved once here
        and used for both the name and the staleness so the two cannot disagree.

        @brief Stamp the answering target, and any staleness, onto a reply.
        @return The reply as a dict carrying `target`.
        @version 8
        """
        answering = self._route(target, sub_index) if target is not None else self._default()
        out = (
            payload
            if payload is not None
            else {
                "kind": kind,
                "subject": subject,
                "found": False,
                "note": (
                    f"No {kind} for {subject!r} in this index. This is a definitive "
                    "negative from the database, NOT an error and NOT a malformed call. "
                    "Before concluding the symbol does not exist, check `target` below "
                    "names the repository you meant, and call status to see whether the "
                    "index is stale."
                    ## gh#6: and if the name IS indexed under a kind this surface cannot
                    ## describe, the sentence above is FALSE as a negative — so it is
                    ## qualified here rather than left to mislead.
                    + _kind_limitation_clause(self._unresolved_for(subject, target, sub_index))
                    ## THE ADVICE ABOVE WAS TRUE AND ALMOST NEVER THE PROBLEM. Measured on the
                    ## 1.1.0 grid: 26.7% of dossier calls returned nothing, and 80.6% of the 237
                    ## unanswered subjects were recoverable from what this index already held —
                    ## the qualified form of a bare name, the bare tail of a qualified one, or the
                    ## file itself for all 48 subjects that were a path. Checking `target` was the
                    ## only thing the reply suggested, so a model with the right target and a
                    ## fresh index had nowhere to go but retry the same name.
                    ##
                    ## STILL A MISS. `found` stays False; a hint is an extra field on a negative,
                    ## never a softening of one.
                    + self._recovery_for(subject, target, sub_index)
                ),
            }
        )
        ## Stamped AFTER any budget trim, which is safe rather than lucky:
        ## `_shrink_to_budget` trims to `RESPONSE_BUDGET_BYTES - _LIMITED_BLOCK_ALLOWANCE`,
        ## and a path plus a key is a rounding error against that 1,800-byte headroom.
        out["target"] = self._target_name(answering)
        ## PRESENT WHENEVER A SUB-INDEX ANSWERED, named or defaulted (gh#48). It used to be
        ## stamped only when the caller NAMED one, so a bare call answered from first-party read
        ## exactly like a whole-repository answer. Absent — not `null` — for a whole-repository
        ## answer, the falsy-drop convention every stamped field here uses.
        if answering is not None and answering.sub_index is not None:
            out["sub_index"] = answering.sub_index
            if answering.not_searched:
                out["not_searched"] = _bounded_names(answering.not_searched)
        ## AFTER the target, so the fit is measured against the finished payload rather
        ## than one that is still going to grow.
        staleness = self._staleness(out, answering)
        if staleness:
            out["staleness"] = staleness
            _withdraw_definitive(out, staleness)
        if answering is not None and answering.sub_index is not None:
            ## `split` WITHOUT `not_searched` IS THE CLI-BUILT REPOSITORY: nothing else on record,
            ## and the repository's own `.gitmodules` saying there is more of it.
            others = bool(answering.not_searched)
            if others or answering.split:
                _scope_definitive(out, answering.sub_index, others)
                _scope_hit(out, answering.sub_index)
                for entry in out.get("results") or []:
                    if isinstance(entry, dict):
                        _scope_definitive(entry, answering.sub_index, others)
                        _scope_hit(entry, answering.sub_index)
        return out

    ## @brief The default target's routing record, or None when it cannot be resolved.
    ## @return The Answering for the default target, or None.
    ## @version 1
    ## @dg_internal
    def _default(self) -> Answering | None:
        """NON-RAISING, like `_target_name`: it attributes a reply that has already been
        answered, so a default that cannot be resolved costs the attribution, never the answer.
        A tool set with no answerer — the bound, test-only shape — keeps its old stamps.

        @brief Resolve the default target for attribution, tolerating failure.
        @return Answering or None.
        @version 1
        """
        if self._answerer is None:
            return None
        try:
            return self._answerer(None, None)
        except Exception:
            return None

    ## @brief The staleness axes to attach to this reply, sized to fit.
    ## @param payload The reply as it stands, target included.
    ## @param answering The routed repository, or None when the derived one answered.
    ## @return Notices to attach; empty when current, unmeasurable, or unbound.
    ## @version 2
    ## @dg_internal
    def _staleness(
        self, payload: dict[str, Any], answering: Answering | None = None
    ) -> list[dict[str, str]]:
        """NON-RAISING, like `_target_name`, and for the same reason: it runs on the way
        out of every reply including the ones that succeeded. A tool set bound without a
        provider — the test-only shape, and the pre-gh#2 behaviour — annotates nothing.

        A ROUTED REPLY IS ANNOTATED FOR THE REPOSITORY IT READ, never for the derived one.
        Reporting the derived target's staleness beside another repository's data would be
        a warning about a database this reply never opened, which is worse than silence:
        the caller would act on it.

        @brief Measure and size this reply's staleness annotation.
        @return Notices sized to the remaining budget, possibly empty.
        @version 2
        """
        if answering is not None:
            found = answering.staleness
        elif self._staleness_provider is not None:
            found = self._staleness_provider()
        else:
            return []
        return _staleness_within_budget(payload, found) if found else []

    ## @brief Dossiers for several subjects in ONE reply, sharing one response budget.
    ## @param subjects Names, already de-duplicated, at most MAX_BATCH_SYMBOLS.
    ## @param kind Restrict every subject to one kind, or None for best-first resolution.
    ## @param target Repo root or slug to answer from, or None for the derived one.
    ## @param max_body_lines Cap on each body excerpt.
    ## @param depth Hops to traverse per subject.
    ## @return The batch envelope: one entry per requested name, in request order.
    ##
    ## v7: each miss entry carries a recovery hint, probed on the same miss that already probes
    ## `unresolved_kinds`. A BATCH NEEDS IT MORE THAN A SINGLE CALL, not less: the model receives
    ## up to eight negatives at once with no indication which were near misses, so advice omitted
    ## here is advice omitted exactly where the reply is hardest to read.
    ## v8 (1.3.1): the envelope is `clew.query.export.batch_payload`, shared with the export API;
    ## this adds the batch budget and the absent-panel elision after it.
    ## @version 8
    ## @dg_internal
    def _batched_dossiers(
        self,
        subjects: list[str],
        kind: str | None,
        target: str | None,
        sub_index: str | None,
        max_body_lines: int,
        depth: int,
    ) -> dict[str, Any]:
        """ONE TURN, NOT FIVE. Measured across three graded mbedtls runs of the same
        question: every run called `dossier` five times, one symbol per call. Per-call
        token cost was already below the raw-source arm's, so the remaining gap was pure
        VOLUME — and a turn is the unit that costs, not a byte.

        The entries stay POSITIONAL against `subjects`, misses included, so a reader can
        pair every requested name with an answer. `count` is the number of entries, which
        equals the number of names asked for; `found` counts the ones that resolved, so
        "four of five are indexed" is readable without diffing two lists.

        SUBJECT-AGNOSTIC SINCE gh#372, and the batch is where that matters most. The
        motivating question — "does mbedtls use mutexes, show where and explain how" — is
        answered by one batch over four names, and ONE of those four is a variable. A
        batch that resolved only functions would have returned three dossiers and a miss
        for the symbol the whole question turns on.

        @brief Batch dossier envelope for several subjects of any kind.
        @return The serialized batch.
        @version 6
        """
        out = _export.batch_payload(
            self.db(target, sub_index),
            subjects,
            kind=kind,
            repo_root=self._repo_or_none(target, sub_index),
            max_body_lines=max_body_lines,
            depth=depth,
        )
        entries = out["results"]
        ## Overhead measured against the envelope MINUS the entries, so the fair shares
        ## are divided over what is actually left rather than over the whole cap. The
        ## `+ 2 * len(entries)` covers the JSON separators the entries themselves add.
        overhead = len(json.dumps({**out, "results": []})) + 2 * len(entries)
        limited = _budget_batch(entries, overhead)
        for entry in entries:
            wire.prune_absent_keys(entry, _DOSSIER_OPTIONAL)
        if limited is not None:
            out["_limited"] = limited
        return self._answered(out, kind="dossiers", target=target, sub_index=sub_index)

    ## @brief Full multi-layer dossier for one subject of ANY kind, or for several at once.
    ## @param subject ONE bare name or repo-relative file path, or a LIST of them for a batched reply.
    ## @param kind Restrict resolution to one subject kind (see SUBJECT_KINDS), or omit for the best-first pick.
    ## @param depth Hops of adjacency to traverse; 1 is the subject and its neighbours, up to MAX_SUBJECT_DEPTH.
    ## @param direction Traversal direction when depth > 1 — 'forward' (downstream) or 'backward' (upstream).
    ## @param max_neighbors Fan-out cap at each hop of a depth > 1 traversal.
    ## @param qualified Optional `candidates[i].qualified` from a prior reply, selecting which same-named function to describe. Single-symbol only.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @param max_body_lines Cap on the verbatim `body` excerpt; raise it to read past a `truncated` body.
    ## @return The resolved subject's payload, a batch envelope, or a miss envelope when nothing of that name is indexed.
    ## C1 of the 1.1.0 acceptance review: `subject` now accepts a repo-relative FILE PATH, which
    ## 48 of 237 missed subjects already were. The served description said a file could never be
    ## one; it can, and five graded clusters carrying 31 weight were losing file-level marks.
    ## v15 (1.3.1): resolves through `clew.query.export.subject_payload`, the builder the export
    ## API shares; this adds the budget, the neighbour cap and the server stamps.
    ## @version 15
    ## @req REQ-DDB-MCP-003
    ## @req REQ-DDB-QUERY-010
    def dossier(
        self,
        subject: Annotated[
            str | list[str],
            Field(
                description=(
                    "One name, or a list of up to 8 for one reply. A function, variable, macro, "
                    "class, enumeration, lock, thread, requirement id, config symbol — or a "
                    "repo-relative FILE PATH, which returns that file's documentation and the "
                    "symbols it defines — with `harvested: false` when the index knows the "
                    "file's name but could not read it."
                )
            ),
        ],
        *,
        kind: Annotated[
            str | None,
            Field(description="Narrow to one kind when a name resolves to several."),
        ] = None,
        depth: Annotated[
            int,
            Field(
                description=(
                    "How far to walk. Depth 1 is the symbol and its immediate neighbours. "
                    "Depth 2-6 also returns `chain`, a bounded causal walk across call and "
                    "shared-key edges; 6 is the maximum. Only a function is an endpoint of "
                    "those edges, so a deeper walk on any other kind returns `depth_note` "
                    "saying so instead of pretending."
                )
            ),
        ] = 1,
        direction: Annotated[
            str, Field(description="'forward' for downstream, 'back' for upstream, on depth >= 2.")
        ] = "forward",
        max_neighbors: Annotated[
            int | None,
            Field(
                description=(
                    "Cap on callers and callees listed per symbol. Omitted: 25 at depth 1, 8 "
                    "per hop of a deeper walk. A cut list is disclosed in `_limited` with its "
                    "`total_available`; raise this to see the rest."
                )
            ),
        ] = None,
        qualified: Annotated[
            str | None,
            Field(
                description=(
                    "A `candidates[i].qualified` from a previous reply — the QUALIFIED NAME, "
                    "such as `Owner::method`, NOT the `signature`, which carries a return type "
                    "and will match nothing. Selects one identity; same-class overloads share "
                    "one. Keep `subject` bare. Single name only."
                )
            ),
        ] = None,
        target: Annotated[
            str | None,
            Field(description="Repo root or slug to query; omit for the default target."),
        ] = None,
        sub_index: Annotated[
            str | None,
            Field(
                description=(
                    "Name of one PART of `target`, when the repository is split into several "
                    "indexes — a first-party index plus one per vendored dependency. Omit and "
                    "the whole-repository index answers, or first-party when only the split is "
                    "built; the reply's `sub_index` says which and `not_searched` names the parts "
                    "it did not read."
                )
            ),
        ] = None,
        max_body_lines: Annotated[
            int,
            Field(
                description=(
                    "Lines of VERBATIM SOURCE returned in `body`, including inline comments. "
                    "Raise it when a reply comes back `truncated: true` — this is how you read "
                    "the actual code without opening the file."
                )
            ),
        ] = q.DEFAULT_BODY_LINES,
    ) -> dict[str, Any]:
        """A LIST IN THE SAME ARGUMENT, NOT A SECOND ARGUMENT. The alternative — keeping
        `function: str` and adding `functions: list[str]` — puts two ways to name a symbol
        in one schema, and the failure mode is a model passing both, or passing the list
        to the parameter it already knows and getting a type error on the one call this
        change exists to encourage. One parameter has one meaning: the symbols you want.
        The cost is an `anyOf` in the generated schema, which is a shape every MCP client
        already handles for optional arguments.

        `qualified` IS REFUSED WITH A LIST rather than ignored. It selects ONE identity
        among namesakes, so against five symbols there is no honest interpretation: it
        cannot say which one it disambiguates, and silently applying it to all five would
        scope four dossiers by a qualified name that belongs to a different function.
        Ignoring it would be worse still — the caller asked for a specific identity and
        would receive an arbitrary one, labelled as if it had been disambiguated.

        THE LIST IS CAPPED AND THE CAP REFUSES. `MAX_BATCH_SYMBOLS` names it; going over
        raises rather than answering for the first eight, because a truncated request
        answered as if complete is the failure this whole surface's `_limited` disclosure
        exists to prevent.

        Duplicates are collapsed HERE and not in R2. A repeated name costs a full dossier
        of the shared budget to say the same thing twice, and the entry it would have
        occupied is better spent on a symbol that was actually asked about; R2 stays
        positional because a library caller has no budget to protect.

        `qualified` is OPTIONAL and additive (gh#37) — omitting it reproduces the
        previous behaviour exactly. `subject` stays BARE even when `qualified` is
        supplied: they are two different columns, and passing a qualified spelling as
        `subject` matches nothing.

        EVERYTHING AFTER `subject` IS KEYWORD-ONLY, and that is a correctness measure
        rather than a style one. `qualified` used to be the second POSITIONAL parameter;
        `kind` is now in that slot, and both take a string. A caller that had learned
        `dossier(name, qualified_spelling)` would have had its identity selector read as a
        subject-kind filter — which raises on a qualified name and would SILENTLY filter
        for any value that happens to be a kind. The bare `*` makes every such call a
        TypeError at the call site instead.

        THE ONE-SHOT. The working tree is resolved from the SAME `target` as the
        database, exactly as the deleted `source` tool did — this payload quotes bytes off
        disk using line numbers out of an index, and a mismatch between the two would show
        one repository's text under another's symbol. Resolved non-raising, so a tool set
        with no working tree bound still answers with every index-only panel.

        `max_body_lines` EXISTS BECAUSE `source` IS GONE, and it is the one thing that tool
        could do that this panel could not. Measured on mbedtls:
        `mbedtls_x509_crt_parse_path` is a 139-line function, so the 120-line default
        returns `truncated: true` and the tail was reachable only through `source`'s
        `max_lines`. Deleting the tool without this argument would have made a long body's
        remainder unreachable from the whole surface — a capability loss dressed as a cull.
        The default is unchanged, so every existing call returns exactly what it did.

        SUBJECT-AGNOSTIC (gh#372), WHICH IS WHY THERE ARE FOUR TOOLS AND NOT NINETEEN.
        `lookup_class`, `req_trace`, `runs_under_lock` and `kconfig` existed because this
        tool resolved through `function_candidates` and therefore refused every subject
        that is not a function. Measured live on the public mbedtls index:
        `dossier('mbedtls_mutex_lock')` answered `found: false` for the symbol its entire
        locking API runs through, because that symbol is a function POINTER — a variable.
        `resolve_subject` now classifies the name and the matching section is built; the
        function path is byte-for-byte what it was.

        `depth` ABSORBS `chain_trace`. Depth 1 is adjacency — the neighbour lists this
        payload has always carried — and depth 2+ runs `chain_trace`'s own bounded walk,
        reusing its fan-out taper rather than writing a second one. Bounded at
        `MAX_SUBJECT_DEPTH` and REFUSED above it, because an unbounded depth on a hub
        symbol is how a single reply reached 125,559 bytes.

        A DEPTH THAT CANNOT BE HONOURED SAYS SO. Only a function is an endpoint of call
        and shared-key edges, so a lock or a requirement has nothing to walk from — and a
        `depth` argument that silently did nothing would be worse than one that refused.
        The reply carries a `depth_note` in that case.

        @brief Composite dossier for one or several subjects of any kind.
        @return The subject payload, a batch envelope, or a miss envelope.
        @version 14
        """
        if not isinstance(subject, str):
            names = _accepted_batch(list(subject), qualified)
            return self._batched_dossiers(names, kind, target, sub_index, max_body_lines, depth)
        payload = _export.subject_payload(
            self.db(target, sub_index),
            subject,
            kind=kind,
            qualified=qualified,
            repo_root=self._repo_or_none(target, sub_index),
            max_body_lines=max_body_lines,
            depth=depth,
            direction=direction,
            ## THE WALK KEEPS ITS OWN FAN-OUT (8 per hop) unless the caller set one: widening every
            ## hop of a depth-3 walk was never the point of capping the depth-1 lists.
            max_neighbors=max_neighbors if max_neighbors is not None else CHAIN_MAX_NEIGHBORS,
        )
        cap = max_neighbors if max_neighbors is not None else DEFAULT_MAX_NEIGHBORS
        return self._answered(
            _capped_neighbors(_budgeted_dossier(payload), cap),
            kind="dossier",
            subject=subject,
            target=target,
            sub_index=sub_index,
        )

    ## @brief The whole lock layer: every lock, the mutex count, the origin split, the nestings.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @return Serialized LockInventory, always present so an empty layer says why.
    ## @version 6
    ## @req REQ-DDB-MCP-003
    ## @dg_internal
    def _lock_inventory(
        self, target: str | None = None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """Through `wire.one` and NOT `_many`, for the same reason `kconfig` is: the
        answer is a single object carrying every count and the sentence that keeps them
        apart, not a list. Routing it through `_many` would flatten away
        `distinct_mutexes`, `origin` and `row_meaning` — the fields that stop a caller
        reporting the row count as the mutex count, or a vendored submodule's mutexes as
        this repository's, which are the errors this tool exists to make harder.

        `origin` rides in the ENVELOPE rather than in the rows, so its zero buckets
        survive: `_absent` prunes empty strings and sequences inside rows, and a
        `first_party: 0` that vanished would read as "not measured".

        AND IT IS BUDGETED NOW, WHICH IT WAS NOT BEFORE. `_shrink_to_budget` only ever ran
        inside `_many`, so every `wire.one` envelope — this one included — was UNCAPPED: a
        target with enough locks would have blown the 32,768-byte cap silently, which is the
        exact silent-truncation failure the cap exists to convert into a disclosure. Folding
        the nestings in is what made it live rather than latent. Measured on the public
        entropic index the reply went 23,510 -> 30,556 bytes, leaving ~400 bytes of headroom
        under the trim ceiling once `target` and a two-axis staleness block are stamped on.
        A fold that quietly truncated the POPULATED target to save a call on the empty one
        would be a regression dressed as an optimisation.

        `nestings` IS TRIMMED BEFORE `locks`, by giving `_shrink_to_budget` only that key.
        The roster is the answer to the question the caller asked; the nestings ride along
        because they are cheap, and a passenger must not evict the payload. `_limited` names
        which list was cut and how to recover it — `query.lock_nestings` still returns the
        whole set to a direct R2 consumer, and that is what the advice says.

        @brief The whole lock inventory in one call.
        @return Serialized LockInventory.
        @version 4
        """
        out = wire.one(q.lock_roster(self.db(target, sub_index)))
        if out is not None:
            cut = _shrink_to_budget(out, ("nestings",))
            if cut:
                out["_limited"] = _limited_block(
                    "nestings",
                    cut["nestings"],
                    len(out["nestings"]),
                    "the locks themselves are complete and untrimmed; only the nesting "
                    "pairs were reduced. Ask dossier for a named lock's sections, "
                    "or read the full set from the query library's lock_nestings",
                )
        return self._answered(out, target=target, sub_index=sub_index)

    ## @brief The repo's Kconfig configuration space: what build variants exist.
    ## @param symbol Restrict the gating-site list to one CONFIG symbol, or None for all.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @return Serialized KconfigSpace, always present so an empty space says why it is empty.
    ## v4: the Kconfig-discovery fact travels as `kconfig_found` here too, so all three routes
    ## that serialize this dataclass reconcile the two meanings of `found` the same way.
    ## @version 4
    ## @req REQ-DDB-MCP-003
    ## @dg_internal
    def _config_space(
        self,
        symbol: str | None = None,
        target: str | None = None,
        sub_index: str | None = None,
    ) -> dict[str, Any]:
        """Returned through `wire.one` and NOT through `_many`, deliberately. `_many`
        wraps a list and produces the definitive-sounding "the database records none"
        note on an empty result — which is exactly the wrong answer here, because three
        different repositories yield zero symbols and `found`/`source`/`error` are what
        tell them apart. An envelope that hides those fields would turn a parse failure
        into "this firmware has no variants".

        @brief Query the configuration space, its choice groups and its gating sites.
        @return Serialized KconfigSpace.
        @version 2
        """
        return self._answered(
            _config_found_on_the_wire(
                wire.one(q.kconfig_space(self.db(target, sub_index), symbol))
            ),
            kind="configuration space",
            subject=symbol,
            target=target,
            sub_index=sub_index,
        )

    ## @brief Whole-graph trust aggregate: edge counts, coverage, per-layer state.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @return Serialized GraphStats.
    ## @version 2
    ## @req REQ-DDB-MCP-003
    def graph_stats(
        self, target: str | None = None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """Returned through `wire.one` and NOT through `_many`, for the same reason
        `kconfig` is: this is an ENVELOPE, not a list. Every one of its keys must reach
        the caller even at zero — an aggregate that elided `pairs_without_nonfuzzy: 0`
        would make a perfectly-resolved graph indistinguishable from an unmeasured one,
        which is the precise misreading the payload exists to prevent.

        Narrows nothing but the repository. The subject is the whole index, and
        `_answered` still stamps the target, which matters more here than anywhere: an
        aggregate is the reply most likely to be quoted as a headline number, and a
        headline number about the wrong repository is how a 36-cell benchmark run was
        voided.

        @brief Aggregate the graph so a consumer can calibrate how much to trust it.
        @return Serialized GraphStats.
        @version 2
        """
        return self._answered(
            wire.one(q.graph_stats(self.db(target, sub_index))),
            kind="graph statistics",
            target=target,
            sub_index=sub_index,
        )

    ## @brief Ranked search across ONE named corpus, or across the searchable text ones.
    ## @param text What to look for; empty lists a whole inventory corpus.
    ## @param corpus Which corpus to read — see CORPORA.
    ## @param limit Maximum hits to return from a text corpus.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @return The corpus's own envelope: ranked rows for a text corpus, the inventory object for a layer corpus.
    ## @version 8
    ## @req REQ-DDB-MCP-003
    def search(
        self,
        text: Annotated[
            str,
            Field(
                description=(
                    "Words to match. EVERY whitespace-separated token must appear in ONE "
                    "searchable unit, so give the two most distinctive words. Ignored by the "
                    "`locks` and `threads` corpora, which enumerate everything."
                )
            ),
        ] = "",
        *,
        corpus: Annotated[
            str,
            Field(
                description=(
                    "What to read. 'symbols' (default) for functions, variables, macros, types "
                    "and per-file docs; 'prose' for the repo's markdown and reStructuredText, "
                    "full-text; 'code' for "
                    "the functions whose BODY contains the words — a literal, a config key, a "
                    "string no symbol is named for. Or enumerate "
                    "a whole layer: 'locks', 'threads', 'files', 'config'. Each row's `kind` is "
                    "what you pass to dossier verbatim."
                )
            ),
        ] = "symbols",
        limit: Annotated[int, Field(description="Maximum rows returned.")] = 25,
        target: Annotated[
            str | None,
            Field(description="Repo root or slug to query; omit for the default target."),
        ] = None,
        sub_index: Annotated[
            str | None,
            Field(
                description=(
                    "Name of one PART of `target`, when the repository is split into several "
                    "indexes — a first-party index plus one per vendored dependency. Omit and "
                    "the whole-repository index answers, or first-party when only the split is "
                    "built; the reply's `sub_index` says which and `not_searched` names the parts "
                    "it did not read."
                )
            ),
        ] = None,
    ) -> dict[str, Any]:
        """ONE FINDER, N CORPORA — `search_prose` WAS NEVER A TOOL, IT WAS AN ARGUMENT.
        The two searches differed in which table they read and in nothing a caller cares
        about, so shipping them as separate tools meant a model had to know which corpus
        held its answer BEFORE it could ask, which is the thing it was searching to find
        out. The markdown corpus is now `corpus='prose'` and the default is unchanged.

        AND THE ROSTERS ARE CORPORA TOO. `lock_roster`, `thread_roster` and the
        whole-space `kconfig()` are all "list what this repository has of kind X" — the
        same question `search` answers, with the filter empty. Folding them in is what
        let the surface reach four tools without dropping an inventory; each keeps its
        OWN envelope rather than being flattened into rows, because `distinct_mutexes`,
        `row_meaning`, `origin` and `found`/`error` are precisely the fields that stop a
        row count being misreported as a mutex count or a parse failure as an absence.

        `kind` IS ON EVERY ROW of a text corpus, which is the field that makes the
        surface navigable: a caller reads it and knows what to pass `dossier` — and since
        gh#372 `dossier` accepts every one of them, so the round trip actually completes.

        The `diagnose` callable rides only on the SYMBOL corpus, where the match is a
        conjunction a single token can empty (gh#31). Attaching it to a prose or roster
        query would word an empty result with a per-token analysis of a corpus that was
        never token-matched.

        @brief Search or enumerate one corpus, with the subject kind on every row.
        @return The corpus's envelope.
        @version 8
        """
        if corpus not in CORPORA:
            raise ValueError(
                f"Unknown corpus {corpus!r}. Known corpora: {', '.join(CORPORA)}. "
                "`symbols` and `prose` RANK against `text`; `config` FILTERS its symbol "
                "names by it; `locks` and `threads` list their whole layer and ignore it."
            )
        return CORPORA[corpus](self, text, limit, target, sub_index)

    ## @brief One corpus's reply through the shared builder, budgeted and stamped.
    ## @param corpus Corpus name.
    ## @param text Search text or filter.
    ## @param limit Maximum rows.
    ## @param target Repo root or slug to answer from.
    ## @param sub_index Sub-index name, or None.
    ## @param kind Noun for a None reply's miss envelope.
    ## @param subject Subject for a None reply's miss envelope.
    ## @return The stamped reply.
    ## @version 1
    ## @dg_internal
    def _corpus(
        self,
        corpus: str,
        text: str,
        limit: int,
        target: str | None,
        sub_index: str | None,
        *,
        kind: str = "result",
        subject: str | None = None,
    ) -> dict[str, Any]:
        """ONE BUILDER FOR BOTH SURFACES (1.3.1). `clew.query.export.corpus_payload` builds the
        answer; `_many` is passed as its list envelope so text corpora are budgeted here and only
        here, and `_answered` stamps the server facts.

        @brief Build, budget and stamp a corpus reply.
        @return The reply.
        @version 1
        """
        payload = _export.corpus_payload(
            self.db(target, sub_index),
            text,
            corpus,
            limit,
            self._repo_or_none(target, sub_index),
            _many,
        )
        return self._answered(
            payload, kind=kind, subject=subject, target=target, sub_index=sub_index
        )

    ## @brief The code corpus: functions whose body contains every word.
    ## @param text Words to match.
    ## @param limit Maximum hits.
    ## @param target Repo root or slug to answer from.
    ## @return `_many` envelope of CodeHit rows; a stated absence when the index has no corpus.
    ## v2 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 2
    ## @dg_internal
    def _search_code(
        self, text: str, limit: int, target: str | None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """ABSENT IS NOT EMPTY. An index built before this corpus existed has no table; saying
        "no matches" there would be a measurement of nothing, so the reply says the corpus is
        missing and how to get it.

        @brief Search function bodies.
        @return Envelope.
        @version 1
        """
        return self._corpus("code", text, limit, target, sub_index)

    ## @brief The symbol corpus: functions, variables, macros, typedefs, enums, classes, file docs.
    ## @param text Ranked search text.
    ## @param limit Maximum hits.
    ## @param target Repo root or slug to answer from.
    ## @return `_many` envelope of SymbolHit rows, graded when empty.
    ## v2 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 2
    ## @dg_internal
    def _search_symbols(
        self, text: str, limit: int, target: str | None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """The pre-gh#372 `search`, verbatim, so the default path is unchanged.

        @brief Search the symbol corpus.
        @return Serialized SymbolHit list, best match first.
        @version 1
        """
        return self._corpus("symbols", text, limit, target, sub_index)

    ## @brief The prose corpus: the repo's markdown, full-text.
    ## @param text Search text.
    ## @param limit Maximum hits.
    ## @param target Repo root or slug to answer from.
    ## @return `_many` envelope of ProseHit rows, with `matched` when the query was widened.
    ## v5 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 5
    ## @dg_internal
    def _search_prose(
        self, text: str, limit: int, target: str | None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """The former `search_prose` tool. It now calls the GRADED form so it can say when
        the answer came from a relaxed query.

        WHY THE DISCLOSURE IS NOT OPTIONAL. FTS5's implicit AND meant one word the author
        did not use emptied an otherwise perfect query, and the reply then told the reader
        the miss was definitive — measured five times in one benchmark cell, each followed
        by a fall back to grep. Widening removes the false negative. Announcing it is what
        stops it becoming a false positive: "these matched SOME of your terms" is a weaker
        claim than "these matched all of them", and a reader who cannot tell them apart has
        simply swapped one wrong answer for another.

        @brief Search the supplementary documentation corpus.
        @return Serialized ProseHit list, plus a `matched` note when the AND was relaxed.
        @version 4
        """
        return self._corpus("prose", text, limit, target, sub_index)

    ## @brief The thread corpus: every thread, with the origin split beside the count.
    ## @param text Ignored — a roster is enumerated, not ranked.
    ## @param limit Ignored.
    ## @param target Repo root or slug to answer from.
    ## @return Serialized ThreadInventory, always present so an empty layer says why.
    ## v2 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 2
    ## @req REQ-DDB-QUERY-011
    ## @dg_internal
    def _search_threads(
        self, text: str, limit: int, target: str | None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """Through `wire.one` and NOT `_many`, as the former `thread_roster` tool was: the
        answer is a single object carrying `origin` and the sentence that says whose
        threads the count counts. `_many` would flatten both away, and it would replace a
        pre-35 index's "this build recorded no spawn sites" with the definitive-sounding
        "the database records none" — turning an unattributable index into a claim about
        the code.

        @brief Enumerate the thread roster.
        @return Serialized ThreadInventory.
        @version 1
        """
        return self._corpus("threads", text, limit, target, sub_index)

    ## @brief The file corpus: what is in this repo, by directory or by glob.
    ## @param text A path glob (`tests/*`, `*.c`) listing the matching files; empty rolls up by directory.
    ## @param limit Ignored — the rollup and the file list each carry their own bound.
    ## @param target Repo root or slug to answer from.
    ## @return Serialized DirectoryInventory, or the matching FileEntry rows for a glob.
    ## v4 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 4
    ## @dg_internal
    def _search_files(
        self, text: str, limit: int, target: str | None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """THE CAPABILITY EXISTED AND NO SURFACE COULD REACH IT. `q.list_files` has always
        inventoried the indexed files with their symbol counts, and the `list_files` TOOL was
        DELETED in the four-tool consolidation — so the library kept the answer and the agent lost
        it. Measured on mbedtls 2026-08-14: Q4 replaced it with six `find … | wc -l` shell calls,
        6 of that cell's 11 fallbacks, and still missed the four marks it was computing them for.

        ROLLED UP BY DEFAULT, listed on request. 450 file rows is the shape that made the config
        corpus unusable at 2.1 MB; ten directory rows is an answer. A glob reaches the files.

        THE ROLLUP SAYS WHAT IT COUNTS, because a reader takes `indexed_files` for the directory's
        size and on this target that inverts the answer: `tests/` has 310 tracked files and 44
        indexed, so the largest directory HERE is `library` and in the REPOSITORY is `tests`.

        @brief Inventory the indexed files by directory, or list a glob's matches.
        @return Serialized DirectoryInventory or file rows.
        @version 3
        """
        return self._corpus(
            "files",
            text,
            limit,
            target,
            sub_index,
            kind="indexed file inventory" if not text else "result",
        )

    ## @brief The context every files reply carries, whatever was asked.
    ## @param target Repo root or slug to answer from.
    ## @return Mapping with the directory inventory and the declared doc scope.
    ## v2 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 2
    ## @dg_internal
    def _files_context(self, target: str | None, sub_index: str | None = None) -> dict[str, Any]:
        """A BIGGER PAYLOAD IS THE CHEAP SIDE OF THIS TRADE. Measured 2026-08-14 on this harness: a
        turn re-reads the whole accumulated context at roughly 55-85k tokens, while these two blocks
        cost a few hundred. A payload may grow TENFOLD and still win if it removes ONE call, which
        inverts the instinct to keep a reply tidy.

        IT FIXES TWO MEASURED DEFECTS AT ONCE, both of which were capabilities that already worked
        and could not be reached:

          * THE ROLLUP WAS BEHIND AN OMITTED ARGUMENT. It answered only when `text` was empty. The
            Q4 cell called this corpus four times — `docs/*`, `Doxyfile`, `doxygen`, `library/*` —
            always WITH text, so it never once saw the inventory, and then ran three
            `find … -type d` shell calls to rebuild it. Behaviour that appears only when a
            parameter is omitted is undescribable and therefore unreachable: a caller predicts
            arguments from the description, and "omit this to get a different answer" has no way
            into that description. So the inventory now rides along with the glob.
          * THE DECLARED DOXYFILE WAS UNREACHABLE. See `q.doc_scope` for what that cost.

        @brief Build the always-present files context.
        @return Inventory and declared-scope blocks.
        @version 1
        """
        return _export.files_context(self.db(target, sub_index))

    ## @brief The note for a glob that matched no indexed file.
    ## @param text The glob that missed.
    ## @return A note naming what this corpus holds and where else to ask.
    ## v2 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 2
    ## @dg_internal
    def _files_miss(self, text: str) -> str:
        """ROUTE, DO NOT CLAIM EXHAUSTION. The default `_many` wording — "a definitive empty result
        from the database … Do not retry this query or fall back to guessing" — is TRUE of this
        corpus and FALSE of the index, and the difference decides what the caller does next.

        Measured on mbedtls 2026-08-14: `search(corpus='files', text='doxygen')` returned that
        sentence, the Q4 cell correctly read it as "the index cannot answer this", and went to the
        shell for four calls. The Doxyfile was in `build_meta` the entire time. We wrote a sentence
        that handed the question to grep, and the model obeyed it.

        So this names the corpus's actual boundary — INDEXED SOURCE FILES, which is why a build
        script, a Doxyfile or a data file is absent by construction rather than by ignorance — and
        points at the two places that DO hold those answers.

        @brief Explain a files-corpus miss and route onward.
        @return The note.
        @version 1
        """
        return _export.files_miss(text)

    ## @brief The configuration corpus: which build-variant symbols this repo has.
    ## @param text Substring filter over the gating symbol NAMES; empty lists them all (capped).
    ## @param limit Ignored — the name list has its own cap, and it reports when it applies.
    ## @param target Repo root or slug to answer from.
    ## @return Serialized KconfigSpace with the symbol inventory and no per-site rows.
    ## v3: the Kconfig-discovery fact moves to `kconfig_found` and `found` answers what it
    ## answers on every other corpus — did this reply find anything. A reply serving five
    ## matching symbols beside `found: false` is what three mbedtls Q1 cells abandoned.
    ## v4 (1.3.1): built by `clew.query.export.corpus_payload`, shared with the export API.
    ## @version 4
    ## @dg_internal
    def _search_config(
        self, text: str, limit: int, target: str | None, sub_index: str | None = None
    ) -> dict[str, Any]:
        """THE SYMBOLS, NOT THE SITES, and previously it returned neither honestly. This corpus's
        own contract is "the question `dossier` cannot answer: which symbols EXIST" — and it was
        asking for the whole space with no symbol, so the reply carried every gate SITE instead.
        Measured on mbedtls 2026-08-14: `search(corpus='config', text='MBEDTLS_THREADING_C')`
        returned 2,149,463 characters, all 12,096 rows, while reporting `found: false` for a symbol
        named in `configured_macros` in the same reply. A caller wanting the NAMES had nowhere to
        look, because `kconfig_symbols` is empty for a repo configured by a header.

        `text` IS NOW HONOURED, unlike the other inventory corpora. Filtering an inventory by name
        is not ranking, costs one `LIKE`, and is what makes a 1,107-symbol space usable — an
        ignored argument that silently returns everything is the defect above.

        A SINGLE SYMBOL'S SITES STAY `dossier`'S JOB, which it already did correctly:
        `resolve_subject` classifies a gating macro as `kind='config'` and returns its rows
        filtered. `gates_meaning` says so in the reply, so an empty `gates` list reads as
        "omitted, ask there" rather than as "nothing gates code here".

        `found` IS RENAMED ON THE WIRE and that is the other half of the measurement above. That
        note records the reply "reporting `found: false` for a symbol named in `configured_macros`
        in the same reply" — the row count was fixed and the false negative was not.

        `KconfigSpace.found` means "this build located a Kconfig FILE", which the layer needs and
        `test_kconfig` defends directly ("this fixture has no Kconfig — `found` must stay honest
        about that"). On a header-configured repository it is correctly False. But `found` means
        something else everywhere on this surface, and clew's own `_verdict` says so: its negative
        test is `payload.get("found") is False or payload.get("count") == 0`. One key, two
        meanings, and the reader cannot tell which it was handed.

        MEASURED COST, replayed from the frozen 1.1.0 grid: mbedtls Q1 asks what runs concurrently
        in a default build. Three of three `index_only` cells called
        `search(corpus="config", text="THREADING")`; the index holds 154 `kconfig_gates` rows for
        `MBEDTLS_THREADING_C`; the reply named five matching symbols beside `found: false`. All
        three stopped pursuing configuration and the question's central symbol never reached
        `dossier`.

        So the discovery fact travels as `kconfig_found` and `found` answers the question every
        other corpus answers with it: did this reply find anything. The library field is untouched.

        @brief Enumerate the configuration symbols matching `text`.
        @return Serialized KconfigSpace, with Kconfig discovery under `kconfig_found`.
        @version 3
        """
        return self._corpus(
            "config",
            text,
            limit,
            target,
            sub_index,
            kind="configuration space",
            subject=text or None,
        )


## Corpus name -> the method that reads it. A MAPPING and not a branch chain so the tool's
## `corpus` argument, its refusal message and its dispatch all read from one list — a
## corpus advertised in a description but missing from the dispatch is a tool that offers a
## corpus it cannot serve, which is one of the ways the surface grew to nineteen.
##
## AT MODULE LEVEL, NOT IN THE CLASS BODY. A dict is not a descriptor, so a class-level
## copy would hand back an unbound function that `self.CORPORA[c](...)` then has to be
## called with `self` explicitly — a shape that reads as a bug at every call site. Here the
## unbound-function call is obviously deliberate.
##
## Two classes of corpus, and the difference is visible in what they return:
##   * TEXT corpora (`symbols`, `prose`) rank against `text` and return `_many` rows.
##   * INVENTORY corpora (`locks`, `threads`, `config`) return the layer's OWN envelope. Two of
##     them ignore `text`; `config` FILTERS on it, because its layer is 1,107 symbols over 12,096
##     sites and listing the sites whole cost 2.1 MB per reply — an ignored argument that silently
##     returns everything is not a smaller version of the same design, it is a defect. The
##     distinction that matters is the ENVELOPE — whose non-row fields are load-bearing — and not
##     whether `text` is read.
## Flattening the second kind into the first is the exact misreport `LockInventory.
## row_meaning` exists to prevent, so they are deliberately NOT normalised to one shape.
CORPORA: dict[str, Callable[[QueryTools, str, int, str | None, str | None], dict[str, Any]]] = {
    "symbols": QueryTools._search_symbols,
    "prose": QueryTools._search_prose,
    "code": QueryTools._search_code,
    "files": QueryTools._search_files,
    "locks": lambda tools, _text, _limit, target, sub_index: tools._lock_inventory(
        target, sub_index
    ),
    "threads": QueryTools._search_threads,
    "config": QueryTools._search_config,
}
