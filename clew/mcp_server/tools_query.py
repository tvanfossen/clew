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
from typing import Any

from .. import query as q
from .. import wire
from .descriptions import load_descriptions
from .emptiness import prose_emptiness, search_emptiness
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
Answerer = Callable[[str], Answering]

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
## @req REQ-DDB-MCP-004
## @version 1
def _withdraw_definitive(payload: dict[str, Any], staleness: list[dict[str, str]]) -> None:
    """@brief Withdraw a definitive-negative claim a schema-stale index cannot earn. @version 1"""
    note = payload.get("note")
    if not isinstance(note, str) or not any(n.get("axis") == _SCHEMA_AXIS for n in staleness):
        return
    lowered = note.lower()
    if not any(claim in lowered for claim in _DEFINITIVE_CLAIMS):
        return
    ## Rewritten rather than appended-to: leaving "this is a definitive empty result" in place and
    ## adding "not definitive" after it is two claims again, in one sentence.
    kept = re.split(r"(?i)this is a definitive|do not retry", note)[0].rstrip()
    payload["note"] = f"{kept}{_UNEARNED_DEFINITIVE}"


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


## @brief The same-name ambiguity behind a function subject's neighbour lists, or None.
## @param db Active database path.
## @param built The resolved subject dossier.
## @return Per-direction ambiguity blocks, or None when the name is unambiguous.
## @version 1
## @dg_internal
def _ambiguity_block(db: Path, built: Any) -> dict[str, Any] | None:
    """`candidates` DISAMBIGUATES THE IDENTITY; NOTHING DISAMBIGUATES THE EDGES. That
    sentence is this repo's own recorded finding (gh#26): `dossier('_classify')` names
    three same-named functions in `candidates` and then lists the UNION of all three
    functions' neighbours, at `confidence: exact`, because corroboration means three
    layers agreed and all three resolve by name. A reader who checks `candidates` and
    then reads `callers` is still misled.

    So the block ships on the composite payload, where it never used to be. It was on the
    deleted `callers`/`callees` tools only — i.e. on the two surfaces a model reaches for
    SECOND — while the tool it is told to call FIRST said nothing. Folding those tools in
    without their disclosure would have removed the warning from the whole surface.

    IT DISCLOSES, IT DOES NOT TRIM. The standalone tools capped an ambiguous list at a
    sample; the composite dossier never did, and adding a cap here would change what a
    call returns in order to deliver a warning about it. The budget trimmer is the only
    thing that removes rows, and it says so separately.

    @brief Disclose same-name edge ambiguity on a function subject.
    @return {direction: block} for each ambiguous direction, or None.
    @version 1
    """
    if built.function is None:
        return None
    blocks: dict[str, Any] = {}
    for field_name, want_callers in (("callers", True), ("callees", False)):
        found = q.name_ambiguity(db, built.function.name, want_callers=want_callers)
        if found is None:
            continue
        blocks[field_name] = {
            "name": found.name,
            "candidates": found.candidates,
            "shared_rows": found.shared_rows,
            "why": (
                f"'{found.name}' matches {found.candidates} distinct function "
                f"signatures. {found.shared_rows} of the {field_name} rows were "
                "recovered from member calls that name only the unqualified tail, so the "
                "receiver's type was never checked and the SAME rows belong to every one "
                "of those functions. At most one per call site is real."
            ),
            "how_to_narrow": (
                "`candidates` in this same payload lists the signatures; re-ask dossier "
                f"with qualified= set to the one you mean. Do NOT report these as "
                f"{field_name} of a specific overload until you have."
            ),
        }
    return blocks or None


## What a `depth > 1` request gets back when the subject has nothing to traverse FROM.
## Only a function is an endpoint of call and shared-key edges, so a lock, a requirement,
## a class or a config symbol has no seed — and the honest reply says which, rather than
## returning a depth-1 payload that looks exactly like a depth-3 one that found nothing.
_NO_SEED_NOTE = (
    "depth > 1 was requested and no traversal was run: only a function is an endpoint of "
    "the call and shared-key edges a chain follows, so a subject of this kind has nothing "
    "to walk from. The adjacency below is complete for depth 1."
)


## @brief Warn when an empty `callers` is a modelling gap rather than a real absence.
## @param payload The flat subject payload, already built.
## @param also The other kinds this same name resolves to.
## @return A note string, or "" when the empty list can be trusted.
## @version 1
## @dg_internal
def _empty_callers_note(payload: dict[str, Any], also: tuple[str, ...]) -> str:
    """gh#4, AND IT CHANGED A REAL DECISION. A reporter asked `dossier("ProgressBar")`, got the
    constructor with `callers: []`, and reported the class as having two production callers in a
    commit message. It has one. Four brace-initialised construction sites existed; none was a call
    edge.

    "HOW MANY CALLERS DOES THIS HAVE" IS THE QUESTION THAT DECIDES WHETHER A SHARED PRIMITIVE CAN
    BE CHANGED, so an empty list there is not a neutral fact — it is a green light. Everything else
    in that same reply was right: free functions returned their callers at `confidence: "exact"`,
    a constexpr variable returned its declaration site. It is specifically the CONSTRUCTOR edge
    that is absent.

    THE SIGNAL IS `also`. A name that resolves as BOTH a function and a class is a constructor in
    every case this can see, and that is a fact already on the payload rather than a new
    extraction — which is why this is a wording fix and not a pipeline change.

    NOT A DISCLAIMER ON EVERY EMPTY LIST. A free function with no callers genuinely has none, and
    annotating that would train a reader to ignore the annotation. The reporter's own words: option
    (3) alone would have prevented the error.

    @brief Say that an empty caller list may be a missing construction edge.
    @return The note, or "".
    @version 1
    """
    if payload.get("subject_kind") != "function" or "class" not in also:
        return ""
    if payload.get("callers"):
        return ""
    return (
        "`callers` is EMPTY and this name also resolves to a class, so this is very likely a "
        "constructor. Construction sites are NOT modelled as call edges — brace-initialised "
        "locals in particular produce none — so an empty list here does NOT mean nothing "
        "constructs this type. Ask `dossier` for the CLASS (kind='class') and read `candidates`, "
        "or `search` the type name, before concluding it has no users."
    )


## @brief Flatten a SubjectDossier to the wire shape: envelope keys plus the one section.
## @param built The resolved subject dossier, or None.
## @param db Active database path, for the function-subject ambiguity probe; omit to skip it.
## @param depth The depth the CALLER asked for, so an unhonoured one can be disclosed.
## @return The flat payload, or None when nothing resolved.
## @version 3
## @dg_internal
def _flatten_subject(built: Any, db: Path | None = None, depth: int = 1) -> dict[str, Any] | None:
    """FLAT, NOT NESTED, and the reason is the budget rather than taste. Every trimmer on
    this surface — `_DOSSIER_LISTS`, `_shrink_to_budget`, `_budget_batch` — addresses
    TOP-LEVEL keys, so a payload that buried `callers` one level down under a `function`
    key would have silently stopped being budgeted at all: the 125,559-byte reply that
    motivated the cap would have come back, with the cap still in the code and still
    passing its tests.

    It is also the better shape for a reader. `subject_kind` names what resolved and the
    section's own fields sit beside it, so a variable payload has `sites` and simply has
    no `callers` key — which is what "say so by ABSENCE" means in practice.

    `also` and `chain` are elided when empty, like every other added key on this surface;
    `subject` and `subject_kind` are always present because a consumer branches on them.

    @brief Serialize a subject dossier to its flat wire form.
    @return Flat payload dict, or None.
    @version 3
    """
    if built is None:
        return None
    section = wire.one(built.section)
    if section is None:
        return None
    payload: dict[str, Any] = {"subject": built.subject, "subject_kind": built.kind, **section}
    if built.also:
        payload["also"] = list(built.also)
    if built.chain is not None:
        payload["chain"] = wire.one(built.chain)
    elif depth > 1:
        payload["depth_note"] = _NO_SEED_NOTE
    ambiguity = None if db is None else _ambiguity_block(db, built)
    if ambiguity:
        payload["ambiguous"] = ambiguity
    gates = None if db is None else _gate_definitions(db, payload)
    if gates:
        payload["gate_definitions"] = gates
    ## PRESENT ONLY WHEN IT APPLIES, like every other added key here — an annotation on every
    ## empty list is one a reader learns to skip.
    callers_note = _empty_callers_note(payload, built.also or ())
    if callers_note:
        payload["callers_note"] = callers_note
    return payload


## Keys whose value describes THE BUILD rather than the subject, so every entry in a batch carries
## an identical copy. Hoisted to the envelope once.
##
## MEASURED, and it is a token defect on the axis under test: a 6-subject `dossier([...])` on
## mbedtls returned `configured_macros` — ~140 macros, ~2,400 tokens — THREE TIMES VERBATIM in one
## response, roughly 7k tokens of pure duplication. It missed the Q1 cell entirely (no config
## subject was asked for) and would land squarely on any question about conditional compilation,
## which on this target is most of them.
##
## MEMBERSHIP IS BY MEANING, NOT BY SIZE. A big field that differs per subject (a `body`, a caller
## list) must stay where it is; only a field whose value is a property of the INDEX belongs here.
## Adding a subject-varying key to this set would silently drop every entry's own value but the
## first, which is why the hoist requires every entry to agree before it fires.
_BUILD_WIDE_KEYS = ("configured_macros", "configured_macros_source", "config_header")


## @brief Move build-wide fields out of every batch entry and onto the envelope, once.
## @param entries The per-subject payloads, mutated in place.
## @param out The batch envelope to receive the hoisted values.
## @return None.
## @version 1
## @dg_internal
def _hoist_build_wide(entries: list[dict[str, Any]], out: dict[str, Any]) -> None:
    """FIRES ONLY ON UNANIMITY, which is the guard that makes this safe rather than merely
    smaller. If two entries disagree about a key, that key is not build-wide in this reply — it is
    subject data wearing a build-wide name — and hoisting would delete a real difference. So
    disagreement leaves every entry untouched.

    A key present on SOME entries and absent from others also fails the check: absence is
    meaningful here (`prune_absent_keys` removes what does not apply to a subject kind), and
    hoisting would assert the value for subjects that never carried it.

    @brief Deduplicate build-wide fields into the envelope.
    @version 1
    """
    for key in _BUILD_WIDE_KEYS:
        values = [entry[key] for entry in entries if key in entry]
        if len(values) < 2 or len(values) != len(entries):
            continue
        if any(value != values[0] for value in values[1:]):
            continue
        out[key] = values[0]
        for entry in entries:
            entry.pop(key, None)


## @brief Resolve the symbols a payload's `gated_by` rows NAME to where they are defined.
## @param db Index path for the same target the payload came from.
## @param payload The flattened dossier payload, read for its gate rows.
## @return Mapping of gate symbol to its definition sites, or {} when nothing resolves.
## @version 1
## @dg_internal
def _gate_definitions(db: Any, payload: dict[str, Any]) -> dict[str, Any]:
    """A NAMED UNKNOWN IN A PAYLOAD IS AN INSTRUCTION TO GO LOOKING. `gated_by` said the code is
    conditional on `MBEDTLS_ALLOW_PRIVATE_ACCESS` and never said where that symbol is DEFINED, so
    the reply left an open loop: a name the caller now needs and cannot resolve from what it holds.

    Measured on mbedtls 2026-08-14. The Q2 cell had the two `#if` branches of `MBEDTLS_PRIVATE` in
    hand — the whole direction-of-the-default answer — and then ran `Grep MBEDTLS_ALLOW_PRIVATE_ACCESS`
    FOUR TIMES with widening scope rather than making one more index call. Those four greps are
    half that cell's fallbacks. The three sites they were hunting are `library/common.h:132`,
    `programs/ssl/ssl_client2.c:8` and `programs/ssl/ssl_server2.c:8` — and two of them are graded
    marks, so the gap cost accuracy as well as tokens.

    THE COST ARGUMENT IS DECISIVE HERE. Resolving every distinct gate symbol adds a few hundred
    bytes; the call it removes costs a full context re-read. There is no version of this trade
    where withholding the sites wins.

    WHY IT RESOLVES RATHER THAN HINTING. `_DOSSIER_HINTS['gated_by']` already points at `kconfig`
    for the configuration SPACE, which is a different question — "what are the build variants"
    rather than "where is this one symbol written down". A hint the caller must act on is still a
    turn; the answer is not.

    DISTINCT SYMBOLS ONLY, AND SELF-REFERENCE DROPPED: a config symbol's own dossier lists itself
    among its gates, and echoing its definition sites back under a second key would be pure
    duplication of the payload it is already in.

    @brief Attach each gate symbol's definition sites.
    @return Gate symbol -> definition sites.
    @version 1
    """
    rows = payload.get("gated_by") or []
    subject = payload.get("name") or payload.get("subject")
    names = sorted(
        {
            str(row["symbol"])
            for row in rows
            if isinstance(row, dict) and row.get("symbol") and row["symbol"] != subject
        }
    )
    out: dict[str, Any] = {}
    for name in names[:_GATE_DEFINITION_CAP]:
        ## PROJECTED, NOT PASSED THROUGH. A full `MacroDef` carries its own `referenced_by`,
        ## `gated_by` and expansion per site, and three of those nested inside a block that exists
        ## to save one call would put the payload back in the budget the trimmer fights over. The
        ## caller needs WHERE, and the expansion only because a gate's value is usually empty and
        ## saying so is the answer.
        sites = [
            {"file": site.file, "line": site.line, "expansion": site.expansion}
            for site in q.macro_definitions(db, name)
        ]
        if sites:
            out[name] = sites
    return out


## Gate symbols resolved per payload. A line is usually gated by one or two symbols; the cap is a
## runaway guard on a deeply nested conditional, not a budget the ordinary case approaches.
_GATE_DEFINITION_CAP = 6


## Nested lists inside a dossier, longest-first, that a budget may trim. Ordered so
## the biggest contributor is reduced before the smaller ones — trimming `writes`
## while 331 `callers` remain would achieve nothing.
_DOSSIER_LISTS = (
    "callers",
    "callees",
    "writes",
    "reads",
    "covering_tests",
    "candidates",
    ## The one-shot panels are budgeted like every other list. `locks_held` is the one
    ## that can grow without bound — a section carries its FULL membership, and a
    ## widely-called function under a coarse lock can be inside many of them.
    "sections",
    "locks_held",
    "external_callees",
    ## gh#373. Budgeted like the rest even though the realistic count is one to three:
    ## a `#define` conditionally redefined per platform can have dozens of sites, and a
    ## list left out of the budget is a list that grows without one.
    "macros",
    ## gh#372 — the lists the NON-FUNCTION subject kinds contribute. A key that is not in
    ## this tuple is a list nothing can trim, so a subject kind added without its lists
    ## reintroduces the unbounded payload one kind at a time. Named here rather than
    ## derived, because deriving them would mean trimming any list-shaped key including
    ## ones whose truncation is meaningless (`also`, `bases`).
    "sites",
    "siblings",
    "implementers",
    "tests",
    "members",
    "symbols",
    "gates",
    ## The FUNCTION subject's preconditions, which is the other direction from the config
    ## subject's `gates` above and therefore a separate key. Budgeted because a function inside
    ## deeply nested conditionals can be covered by several, and mbedtls nests them freely.
    "gated_by",
    "threads",
    "nodes",
    "hops",
)

## Envelope keys the dossier ELIDES when they say nothing. Only the one-shot additions:
## the pre-existing keys have always been present on every reply and a consumer reading
## `doss["callees"] == []` must keep working. An absent `sections` reads as "opens no
## critical section", which is the common case on almost every function in any repo.
_DOSSIER_OPTIONAL = (
    "body",
    "sections",
    "locks_held",
    "external_callees",
    "macros",
    ## Elided for an ungated function, which is the common case in any repo that does not gate
    ## everything. `gates_unplaceable` is NOT elided: a zero there is a measurement — "every gate
    ## in this file had a recorded extent, so an empty `gated_by` means ungated" — and eliding it
    ## would leave a reader unable to tell that from "this index cannot tell".
    "gated_by",
    ## gh#403. '' on every ordinary function — a defined function has a body extent — so eliding
    ## it costs a reader nothing. UNLIKE `gates_unplaceable`, an empty one is not a measurement:
    ## it says "the two conditions did not both hold", which is the absence of news rather than a
    ## finding about this symbol.
    "macro_collision",
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
    "sections": "call lock_roster() then runs_under_lock() for the unabridged holds",
    "locks_held": "call lock_roster() then runs_under_lock() for the unabridged holds",
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
        "kconfig() for the full configuration space — the gates shown are the innermost by line"
    ),
    "macros": (
        "no tool enumerates definition sites — search() collapses a name to one row; "
        "the sites shown are the first by file and line"
    ),
}


## @brief Trim a serialized dossier's nested lists to the response budget.
## @param doss Serialized dossier, or None.
## @return The dossier, trimmed and annotated when it exceeded the budget.
## @version 3
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
                    f"call {field_name}() directly for a focused view, or resolve_symbol() "
                    f"first if the name is overloaded",
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


## @brief The clause that turns a bare miss into a KIND limitation when it is one.
## @param unresolved Unsupported kinds the index nevertheless holds for the name.
## @return A sentence to append, or "" when the name is genuinely absent.
## @version 1
## @dg_internal
def _kind_limitation_clause(unresolved: tuple[str, ...]) -> str:
    """gh#6. `SUBJECT_KINDS` has no `enumeration`, while `SEARCHED_MEMBERDEF_KINDS` does — so
    `search` finds a C enum, its enumerators and a C++ `enum class`, and `dossier` calls the same
    names "a definitive negative from the database". A reporter asked about four enum symbols they
    knew existed and got that on all four.

    THE WORDING WAS THE DAMAGE. A gap described as a gap costs one follow-up call; a gap worded as
    a definitive negative reads as "this tool is wrong about my repo" — and on a codebase whose
    authoritative definitions are C enums, wrong about the thing that matters most.

    ONE SENTENCE, AND IT ROUTES: it names the kind, says this surface does not describe it yet, and
    names the tool that can. Route, do not disclaim.

    @brief Say the name is indexed under a kind this surface cannot describe.
    @return The clause, or "" when nothing was found under any kind.
    @version 1
    """
    if not unresolved:
        return ""
    kinds = ", ".join(f"`{k}`" for k in unresolved)
    return (
        f" HOWEVER this name IS in the index, as {kinds} — a kind `dossier` does not describe "
        f"yet. So this is a COVERAGE LIMITATION of this tool, not a statement that the symbol "
        f"does not exist. Use `search` to see it."
    )


## @brief The reply for a batched name that resolves to nothing.
## @param name The unresolved function name.
## @param unresolved Unsupported kinds the index holds for it, from `unresolved_kinds`.
## @return A per-symbol miss envelope.
## @version 2
## @dg_internal
def _batch_miss(name: str, unresolved: tuple[str, ...] = ()) -> dict[str, Any]:
    """PER SYMBOL, NEVER PER CALL. One unresolvable name in a batch of five must not
    fail the other four, and it must not vanish either: a dropped entry would silently
    re-align the reader's mapping from names to answers, which is a worse error than the
    miss it is hiding.

    Wording is the short form of `_answered`'s miss note. The long one repeats the
    target-and-staleness advice, which is already stamped ONCE on the batch envelope
    rather than eight times inside it.

    @brief Miss envelope for one name in a batch.
    @return The miss entry.
    @version 2
    """
    return {
        "name": name,
        "found": False,
        "note": (
            "Not indexed in this repository. A definitive negative from the database, "
            "not an error — check the envelope's `target` before concluding it does not "
            "exist." + _kind_limitation_clause(unresolved)
        ),
    }


## @brief Validate and normalise a batch request, refusing what cannot be answered.
## @param names The requested symbol list, as given.
## @param qualified The `qualified` argument, which has no meaning against a list.
## @return The de-duplicated names, in request order.
## @version 1
## @dg_internal
def _accepted_batch(names: list[str], qualified: str | None) -> list[str]:
    """REFUSES, NEVER TRIMS. Each of the three rejections here has a silent alternative
    that looks like success and is worse than an error:

    - an empty list would answer `count: 0` to a request that asked for something, which
      reads as "none of your symbols is indexed";
    - a list over the cap answered for its first eight would report a count the caller
      has to re-check against its own request to notice the loss;
    - `qualified` beside a list would scope every dossier in the batch by one identity
      key that belongs to at most one of them.

    De-duplication is the ONE normalisation that is not a refusal, because it removes no
    information: the same name twice has one answer, and the entry it frees goes to a
    symbol that was actually asked about.

    @brief Normalise a batch request or raise.
    @return De-duplicated names in request order.
    @version 1
    """
    if qualified is not None:
        raise ValueError(
            "`qualified` selects ONE identity among same-named functions, so it cannot "
            "be combined with a list of symbols. Call dossier with that single name and "
            "its qualified spelling, then batch the rest."
        )
    unique = list(dict.fromkeys(names))
    if not unique:
        raise ValueError("dossier needs at least one function name.")
    if len(unique) > q.MAX_BATCH_SYMBOLS:
        raise ValueError(
            f"dossier answers for at most {q.MAX_BATCH_SYMBOLS} symbols in one call and "
            f"{len(unique)} were requested. Split the list — the request is REFUSED "
            "rather than answered for the first "
            f"{q.MAX_BATCH_SYMBOLS}, so a partial answer cannot be mistaken for a "
            "complete one."
        )
    return unique


## @brief Serialize a list of R2 dataclasses to plain JSON types.
## @param items Iterable of dataclass instances.
## @return List of dicts.
## @version 9
## @dg_internal
def _many(
    items: Any,
    *,
    kind: str = "results",
    subject: str | None = None,
    diagnose: Diagnoser | None = None,
) -> dict[str, Any]:
    """Convert a list of R2 results into a self-describing envelope.

    A BARE empty list is indistinguishable from a broken tool: the caller
    cannot tell "this symbol genuinely has no callers" from "my call was
    malformed". That ambiguity is not hypothetical — an earlier benchmark of a
    different query layer was invalidated because agents read empty responses
    as failures, abandoned the index, and started guessing names.

    So every list-returning tool answers with an explicit count and, when the
    result is legitimately empty, a note saying so in as many words.

    THE DEFAULT NOTE IS THE STRONG ONE, and stays so. gh#21/gh#31 found the defect
    to be UNIFORM confidence, not confidence: for most tools here an empty result
    IS a definitive negative — a function with no callers has no callers — and
    weakening every note would trade one wrong answer for fifteen vague ones.

    A tool whose emptiness can have a cause OTHER than absence passes a
    `diagnose` callable instead, which is invoked ONLY when the result is empty
    and returns its own note plus extra envelope keys. ONE does today: `search`,
    where the match is a conjunction that a single token can empty. `list_files` was
    the second and is deleted — its diagnosis went with it, since a grading no tool
    can reach is a claim nothing tests against a real reply. See `emptiness.py`.

    @brief Serialize a list of dataclass results with explicit emptiness.
    @param items Iterable of dataclass results.
    @param kind Plural noun for what was searched for (e.g. "callers").
    @param subject What it was searched for (e.g. a function name).
    @param diagnose Optional callable supplying a graded note + extra keys when empty.
    @return Envelope dict with `count`, `kind`, `results`, and `note` if empty.
    @version 11
    """
    rows = wire.rows(items)
    ## `count` deliberately reports the TRUE total, not the number of rows shown.
    ## A count that shrank with the truncation would hide the very thing the
    ## `_limited` block exists to disclose.
    out: dict[str, Any] = {"kind": kind, "count": len(rows), "results": rows}
    cut = _shrink_to_budget(out, ("results",))
    if cut:
        out["_limited"] = _limited_block(
            kind,
            cut["results"],
            len(out["results"]),
            f"re-query with a narrower subject, or use search to scope before asking for {kind}",
        )
    if subject is not None:
        out["subject"] = subject
    if not rows and diagnose is not None:
        note, extra = diagnose()
        out["note"] = note
        out.update(extra)
    elif not rows:
        where = f" for {subject!r}" if subject else ""
        ## "— the database records none" is GONE, and only that clause. It restated
        ## "a definitive empty result from the database" in different words, and this
        ## note is the whole of five of the seven zero-row replies in the measured
        ## mbedtls cell (a 300-byte `lock_nestings` reply was 185 bytes of it). The
        ## two clauses a caller acts on — that it is definitive, and that retrying or
        ## guessing is wrong — are untouched and are what `test_emptiness.py` pins.
        ## `tests/test_mcp_server.py` separately asserts the removed phrase is ABSENT
        ## from an empty `lock_roster`, so nothing wants it back.
        out["note"] = (
            f"No {kind}{where}. This is a definitive empty result from the database, "
            f"not an error and not a malformed call. Do not retry this query or fall "
            f"back to guessing."
        )
    return out


## @brief The one message a caller gets when the database they need does not exist yet.
## @param repo_path Repository the missing database would describe, or "" when unknown.
## @return An actionable sentence naming the call that fixes it.
## @version 1
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

    @brief The actionable message for an index that has not been built.
    @return The message.
    @version 1
    """
    where = f" for {repo_path}" if repo_path else ""
    target = f", target={repo_path!r}" if repo_path else ""
    return (
        f"No database has been built{where} yet — call index(action='refresh'{target}) first. "
        f"Nothing is wrong with this repository; it has simply not been indexed."
    )


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
    def _route(self, target: str) -> Answering:
        """Refusing beats falling back. A tool set with no answerer is bound to one
        database, and serving that database for a call that named a different one would
        produce a reply whose `target` field names the bound repository — which reads as a
        successful routed call and hides the mistake completely.

        @brief Resolve a routed target, or say this tool set cannot route.
        @return The resolved repository.
        @version 1
        """
        if self._answerer is None:
            raise RuntimeError(
                f"These tools cannot route to {target!r}: they are bound to a single "
                "repository. Call status to see which repository answers here."
            )
        return self._answerer(target)

    ## @brief The database path this call reads.
    ## @param target Repository to read, or None for the one the server derived.
    ## @return Path to the clew.db the tools should read.
    ## @version 4
    ## @req REQ-DDB-MCP-003
    def db(self, target: str | None = None) -> Path:
        """Resolve the db path for this call: the routed target when one was named, else
        the derived one. Omitting `target` reproduces the previous behaviour exactly.

        @brief Resolve this call's database path.
        @return clew.db path.
        @version 3
        """
        if target is not None:
            return self._route(target).db
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
    ## @return Path to the repo the answering database was built from.
    ## @version 3
    ## @req REQ-DDB-MCP-003
    def repo(self, target: str | None = None) -> Path:
        """Resolve the working tree the recorded paths are relative to. The model is
        NEVER asked for it as a filesystem path — it names a repository and the server
        resolves it, or it names none and the server's derived target answers.

        @brief Resolve this call's repo root.
        @return Repo root path.
        @version 3
        """
        if target is not None:
            return self._route(target).repo
        if self._repo_provider is None:
            raise RuntimeError(
                "No repo root bound to these tools — the server has no target. It "
                "derives one from --repo, $CLAUDE_PROJECT_DIR, or the client's "
                "roots/list; call status to see which, or name one with target=."
            )
        return self._repo_provider()

    ## @brief The working tree for this call, or None when there isn't one.
    ## @param target Repository to read, or None for the one the server derived.
    ## @return Repo root, or None when no working tree is bound or resolvable.
    ## @version 1
    ## @dg_internal
    def _repo_or_none(self, target: str | None = None) -> Path | None:
        """NON-RAISING, unlike `repo()`, and that is the whole reason it exists.

        `source` MUST fail loudly without a working tree — its entire answer is bytes off
        disk, so a silent empty reply would be indistinguishable from "this function has
        no body". `dossier` must not: the working tree is needed for two panels out of
        twenty fields, it answered without them for its whole life before the one-shot,
        and a tool set bound without a repo provider is the shape every unit test uses.
        Turning that into an exception would make the composite payload fail where the
        narrow tool it replaces succeeded.

        @brief Resolve this call's working tree, or None.
        @return Repo root or None.
        @version 1
        """
        try:
            return self.repo(target)
        except (RuntimeError, ValueError, OSError):
            return None

    ## @brief The repository this reply answered from, for attribution.
    ## @param answering The routed repository, or None when the derived one answered.
    ## @return Repo root as a string, falling back to the database path.
    ## @version 2
    ## @dg_internal
    def _target_name(self, answering: Answering | None) -> str:
        """Non-raising by contract, unlike `repo()`. It is called on the way OUT of
        every reply, including replies that succeeded, so it must never be the thing
        that turns a good answer into an error. A tool set constructed without a repo
        provider is a test-only shape; naming the database there is still a truthful
        answer to "what answered this?".

        @brief Name the repository (or database) that answered.
        @return Target name.
        @version 2
        """
        if answering is not None:
            return str(answering.repo)
        provider = self._repo_provider if self._repo_provider is not None else self._db_provider
        return str(provider())

    ## @brief Unsupported kinds this index holds for a name that failed to resolve.
    ## @param subject The name that missed, or None.
    ## @param target Repository the call named, or None for the derived one.
    ## @return The unsupported kinds, or () when there are none or nothing can be read.
    ## @version 1
    ## @dg_internal
    def _unresolved_for(self, subject: str | None, target: str | None) -> tuple[str, ...]:
        """NEVER RAISES ON THE MISS PATH. This runs while building an answer that has already
        failed to find something, so a database that cannot be opened — the very case
        `unbuilt_index_message` exists for — must not turn a clean negative into a traceback.
        A probe that cannot run contributes no clause, which is the same discipline as
        `doxygen_supports_sqlite3` returning None rather than False.

        @brief Probe the unsupported kinds behind a miss, tolerating any failure.
        @return The kinds, or ().
        @version 1
        """
        if not subject:
            return ()
        try:
            return q.unresolved_kinds(self.db(target), subject)
        except Exception:
            return ()

    ## @brief Stamp a reply with the target it came from, making a miss self-describing.
    ## @param payload The serialized reply, or None for "not found".
    ## @param kind What was looked for (e.g. "dossier").
    ## @param subject What it was looked for by (e.g. a function name).
    ## @param target Repository the call named, or None when the derived one answered.
    ## @return The reply, always a dict, always carrying `target` and any staleness.
    ## @version 5
    ## @dg_internal
    def _answered(
        self,
        payload: dict[str, Any] | None,
        *,
        kind: str = "result",
        subject: str | None = None,
        target: str | None = None,
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
        @version 5
        """
        answering = None if target is None else self._route(target)
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
                    + _kind_limitation_clause(self._unresolved_for(subject, target))
                ),
            }
        )
        ## Stamped AFTER any budget trim, which is safe rather than lucky:
        ## `_shrink_to_budget` trims to `RESPONSE_BUDGET_BYTES - _LIMITED_BLOCK_ALLOWANCE`,
        ## and a path plus a key is a rounding error against that 1,800-byte headroom.
        out["target"] = self._target_name(answering)
        ## AFTER the target, so the fit is measured against the finished payload rather
        ## than one that is still going to grow.
        staleness = self._staleness(out, answering)
        if staleness:
            out["staleness"] = staleness
            _withdraw_definitive(out, staleness)
        return out

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
    ## @version 5
    ## @dg_internal
    def _batched_dossiers(
        self,
        subjects: list[str],
        kind: str | None,
        target: str | None,
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
        @version 5
        """
        built = q.dossiers(
            self.db(target),
            subjects,
            kind=kind,
            repo_root=self._repo_or_none(target),
            max_body_lines=max_body_lines,
            depth=depth,
        )
        db = self.db(target)
        ## PROBED ONLY ON A MISS (gh#6). `unresolved_kinds` is one indexed lookup, and running it
        ## for every hit would charge the hot path for a question only a miss asks.
        entries = [
            _batch_miss(name, q.unresolved_kinds(db, name))
            if doss is None
            else (
                _flatten_subject(doss, db, depth) or _batch_miss(name, q.unresolved_kinds(db, name))
            )
            for name, doss in zip(subjects, built, strict=True)
        ]
        out: dict[str, Any] = {
            "kind": "dossiers",
            "count": len(entries),
            "found": sum(1 for e in entries if e.get("found") is not False),
            "subject": subjects,
            "results": entries,
        }
        _hoist_build_wide(entries, out)
        ## Overhead measured against the envelope MINUS the entries, so the fair shares
        ## are divided over what is actually left rather than over the whole cap. The
        ## `+ 2 * len(entries)` covers the JSON separators the entries themselves add.
        overhead = len(json.dumps({**out, "results": []})) + 2 * len(entries)
        limited = _budget_batch(entries, overhead)
        for entry in entries:
            wire.prune_absent_keys(entry, _DOSSIER_OPTIONAL)
        if limited is not None:
            out["_limited"] = limited
        return self._answered(out, kind="dossiers", target=target)

    ## @brief Full multi-layer dossier for one subject of ANY kind, or for several at once.
    ## @param subject ONE bare name, or a LIST of them for a batched reply.
    ## @param kind Restrict resolution to one subject kind (see SUBJECT_KINDS), or omit for the best-first pick.
    ## @param depth Hops of adjacency to traverse; 1 is the subject and its neighbours, up to MAX_SUBJECT_DEPTH.
    ## @param direction Traversal direction when depth > 1 — 'forward' (downstream) or 'backward' (upstream).
    ## @param max_neighbors Fan-out cap at each hop of a depth > 1 traversal.
    ## @param qualified Optional `candidates[i].qualified` from a prior reply, selecting which same-named function to describe. Single-symbol only.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @param max_body_lines Cap on the verbatim `body` excerpt; raise it to read past a `truncated` body.
    ## @return The resolved subject's payload, a batch envelope, or a miss envelope when nothing of that name is indexed.
    ## @version 12
    ## @req REQ-DDB-MCP-003
    ## @req REQ-DDB-QUERY-010
    def dossier(
        self,
        subject: str | list[str],
        *,
        kind: str | None = None,
        depth: int = 1,
        direction: str = "forward",
        max_neighbors: int = 8,
        qualified: str | None = None,
        target: str | None = None,
        max_body_lines: int = q.DEFAULT_BODY_LINES,
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
        @version 12
        """
        if not isinstance(subject, str):
            names = _accepted_batch(list(subject), qualified)
            return self._batched_dossiers(names, kind, target, max_body_lines, depth)
        built = q.dossier(
            self.db(target),
            subject,
            kind=kind,
            qualified=qualified,
            repo_root=self._repo_or_none(target),
            max_body_lines=max_body_lines,
            depth=depth,
            direction=direction,
            max_neighbors=max_neighbors,
        )
        return self._answered(
            _budgeted_dossier(_flatten_subject(built, self.db(target), depth)),
            kind="dossier",
            subject=subject,
            target=target,
        )

    ## @brief The whole lock layer: every lock, the mutex count, the origin split, the nestings.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @return Serialized LockInventory, always present so an empty layer says why.
    ## @version 5
    ## @req REQ-DDB-MCP-003
    ## @dg_internal
    def _lock_inventory(self, target: str | None = None) -> dict[str, Any]:
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
        out = wire.one(q.lock_roster(self.db(target)))
        if out is not None:
            cut = _shrink_to_budget(out, ("nestings",))
            if cut:
                out["_limited"] = _limited_block(
                    "nestings",
                    cut["nestings"],
                    len(out["nestings"]),
                    "the locks themselves are complete and untrimmed; only the nesting "
                    "pairs were reduced. Ask runs_under_lock for a named lock's sections, "
                    "or read the full set from the query library's lock_nestings",
                )
        return self._answered(out, target=target)

    ## @brief The repo's Kconfig configuration space: what build variants exist.
    ## @param symbol Restrict the gating-site list to one CONFIG symbol, or None for all.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @return Serialized KconfigSpace, always present so an empty space says why it is empty.
    ## @version 3
    ## @req REQ-DDB-MCP-003
    ## @dg_internal
    def _config_space(self, symbol: str | None = None, target: str | None = None) -> dict[str, Any]:
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
            wire.one(q.kconfig_space(self.db(target), symbol)),
            kind="configuration space",
            subject=symbol,
            target=target,
        )

    ## @brief Whole-graph trust aggregate: edge counts, coverage, per-layer state.
    ## @param target Repo root or slug to answer from; omit for the server's derived target.
    ## @return Serialized GraphStats.
    ## @version 2
    ## @req REQ-DDB-MCP-003
    def graph_stats(self, target: str | None = None) -> dict[str, Any]:
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
            wire.one(q.graph_stats(self.db(target))), kind="graph statistics", target=target
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
        text: str = "",
        *,
        corpus: str = "symbols",
        limit: int = 25,
        target: str | None = None,
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
        return CORPORA[corpus](self, text, limit, target)

    ## @brief The symbol corpus: functions, variables, macros, typedefs, enums, classes, file docs.
    ## @param text Ranked search text.
    ## @param limit Maximum hits.
    ## @param target Repo root or slug to answer from.
    ## @return `_many` envelope of SymbolHit rows, graded when empty.
    ## @version 1
    ## @dg_internal
    def _search_symbols(self, text: str, limit: int, target: str | None) -> dict[str, Any]:
        """The pre-gh#372 `search`, verbatim, so the default path is unchanged.

        @brief Search the symbol corpus.
        @return Serialized SymbolHit list, best match first.
        @version 1
        """
        db = self.db(target)
        return self._answered(
            _many(
                q.search(db, text, limit=limit),
                kind="matching symbols",
                subject=text,
                diagnose=lambda: search_emptiness(db, text),
            ),
            target=target,
        )

    ## @brief The prose corpus: the repo's markdown, full-text.
    ## @param text Search text.
    ## @param limit Maximum hits.
    ## @param target Repo root or slug to answer from.
    ## @return `_many` envelope of ProseHit rows, with `matched` when the query was widened.
    ## @version 3
    ## @dg_internal
    def _search_prose(self, text: str, limit: int, target: str | None) -> dict[str, Any]:
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
        @version 3
        """
        found = q.search_prose_graded(self.db(target), text, limit=limit)
        ## THE DIAGNOSE CALLABLE, WITHOUT WHICH `_many` APPLIES ITS DEFAULT (gh#404). That default
        ## reads "a definitive empty result… Do not retry this query or fall back to guessing" —
        ## correct for a tool whose emptiness can only mean absence, and flatly wrong for a corpus
        ## that reads markdown and member docs while the token sits in a `#if` expression. The
        ## symbols corpus has been graded since D1; prose inherited the strong wording by simply
        ## never passing this argument.
        payload = _many(
            found.hits,
            kind="prose matches",
            subject=text,
            diagnose=lambda: prose_emptiness(self.db(target), text),
        )
        if found.widened:
            payload["matched"] = "some terms"
            payload["note"] = (
                f"No document contains ALL of {', '.join(found.tokens)}, so this reply "
                "answers the RELAXED query — each row matched at least one term, best "
                "matches first. Treat these as leads rather than as exact hits, and "
                "re-ask with fewer, more distinctive words to tighten them."
            )
        return self._answered(payload, target=target)

    ## @brief The thread corpus: every thread, with the origin split beside the count.
    ## @param text Ignored — a roster is enumerated, not ranked.
    ## @param limit Ignored.
    ## @param target Repo root or slug to answer from.
    ## @return Serialized ThreadInventory, always present so an empty layer says why.
    ## @version 1
    ## @req REQ-DDB-QUERY-011
    ## @dg_internal
    def _search_threads(self, text: str, limit: int, target: str | None) -> dict[str, Any]:
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
        return self._answered(wire.one(q.thread_roster(self.db(target))), target=target)

    ## @brief The file corpus: what is in this repo, by directory or by glob.
    ## @param text A path glob (`tests/*`, `*.c`) listing the matching files; empty rolls up by directory.
    ## @param limit Ignored — the rollup and the file list each carry their own bound.
    ## @param target Repo root or slug to answer from.
    ## @return Serialized DirectoryInventory, or the matching FileEntry rows for a glob.
    ## @version 3
    ## @dg_internal
    def _search_files(self, text: str, limit: int, target: str | None) -> dict[str, Any]:
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
        context = self._files_context(target)
        if not text:
            ## THE ROLLUP IS THE WHOLE REPLY HERE, so `inventory` is dropped rather than merged: it
            ## carries the SAME `directories` and the same ~700-character `rollup_meaning`, and
            ## emitting both put every row and that whole sentence in the payload TWICE. Measured on
            ## the p5-both run — a defect introduced by the fix that made the rollup accompany a
            ## glob, which is the ordinary shape of a context block added without checking the route
            ## that already had one.
            ##
            ## `doc_scope` still travels, because that genuinely is not in the rollup.
            return self._answered(
                {
                    **(wire.one(q.directory_rollup(self.db(target))) or {}),
                    **{k: v for k, v in context.items() if k != "inventory"},
                },
                kind="indexed file inventory",
                target=target,
            )
        rows = _many(
            q.list_files(self.db(target), text),
            kind="indexed files",
            subject=text,
            diagnose=lambda: (self._files_miss(text), {}),
        )
        return self._answered({**rows, **context}, target=target)

    ## @brief The context every files reply carries, whatever was asked.
    ## @param target Repo root or slug to answer from.
    ## @return Mapping with the directory inventory and the declared doc scope.
    ## @version 1
    ## @dg_internal
    def _files_context(self, target: str | None) -> dict[str, Any]:
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
        rollup = wire.one(q.directory_rollup(self.db(target))) or {}
        ## The rollup's own `indexed_files` total would collide with a glob reply's count and read
        ## as a contradiction, so only the per-directory rows and the sentence that says what they
        ## count travel — under a name that cannot be mistaken for the glob's own results.
        context: dict[str, Any] = {
            "inventory": {
                "directories": rollup.get("directories", []),
                "rollup_meaning": rollup.get("rollup_meaning", ""),
            }
        }
        scope = q.doc_scope(self.db(target))
        if scope:
            context["doc_scope"] = scope
        return context

    ## @brief The note for a glob that matched no indexed file.
    ## @param text The glob that missed.
    ## @return A note naming what this corpus holds and where else to ask.
    ## @version 1
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
        return (
            f"No indexed file matches {text!r}. This corpus holds INDEXED SOURCE FILES only, so a "
            f"build script, a Doxyfile, a data file or anything else the index does not parse is "
            f"absent here BY CONSTRUCTION — that is a fact about this corpus, not about the index. "
            f"Before going to the shell: `doc_scope` in this same reply names the doc build and "
            f"the vendored trees this repository declares, and `inventory.directories` is the "
            f"whole tree rolled up. Re-glob more broadly (`*.c`, `tests/*`) if you wanted files."
        )

    ## @brief The configuration corpus: which build-variant symbols this repo has.
    ## @param text Substring filter over the gating symbol NAMES; empty lists them all (capped).
    ## @param limit Ignored — the name list has its own cap, and it reports when it applies.
    ## @param target Repo root or slug to answer from.
    ## @return Serialized KconfigSpace with the symbol inventory and no per-site rows.
    ## @version 2
    ## @dg_internal
    def _search_config(self, text: str, limit: int, target: str | None) -> dict[str, Any]:
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

        @brief Enumerate the configuration symbols matching `text`.
        @return Serialized KconfigSpace.
        @version 2
        """
        return self._answered(
            wire.one(q.kconfig_space(self.db(target), text or None, include_gates=False)),
            kind="configuration space",
            subject=text or None,
            target=target,
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
CORPORA: dict[str, Callable[[QueryTools, str, int, str | None], dict[str, Any]]] = {
    "symbols": QueryTools._search_symbols,
    "prose": QueryTools._search_prose,
    "files": QueryTools._search_files,
    "locks": lambda tools, _text, _limit, target: tools._lock_inventory(target),
    "threads": QueryTools._search_threads,
    "config": QueryTools._search_config,
}
