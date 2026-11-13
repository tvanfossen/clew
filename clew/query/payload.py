# SPDX-License-Identifier: MIT
"""The answer-content transforms a dossier or search reply carries on every surface.

MOVED FROM `clew.mcp_server.tools_query` in 1.3.1 (Track 1, export API), bodies unchanged. These
are the parts of a reply that are ANSWER CONTENT rather than MCP boundary — flattening a subject
dossier, the same-name ambiguity block, the empty-`callers` notes, the candidate-cap disclosure,
gate definition sites, the build-wide hoist, batch validation and misses, and the config `found`
reconciliation. Both `clew.query.export` and the MCP tools read them from here, so the two
surfaces cannot word the same answer differently.

The byte budget, the neighbour cap and the server stamps stay in `tools_query`.

@brief Shared reply-content transforms for the export API and the MCP tools.
@version 1
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import query as q
from .. import wire
from . import _common


## @brief The same-name ambiguity behind a function subject's neighbour lists, or None.
## @param db Active database path.
## @param built The resolved subject dossier.
## @return Per-direction ambiguity blocks, or None when the name is unambiguous.
##
## v2: the served `how_to_narrow` said `candidates` "lists the signatures" and to re-ask with the
## one you mean. The accessor takes `candidates[i].qualified` and compares by exact match, so a
## signature — which carries a return type — selects NOTHING. This text was read at the exact
## moment a model had been told its name was ambiguous, so it steered the retry into a guaranteed
## miss. It now names the field the code accepts.
## @version 2
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
                "`candidates` in this same payload carries a `qualified` per identity; re-ask "
                "dossier with `qualified=` set to the one you mean — that field, not the "
                f"`signature`. Do NOT report these as {field_name} of a specific overload "
                f"until you have."
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
## @version 2
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

    gh#15 MADE THE SIGNAL A MEASUREMENT. `also` says what KIND of symbol this is; the build now
    records what it actually REFUSED, per symbol, so the strong case no longer has to be inferred
    from a category. The measured branch therefore wins where both apply — it is a fact about
    this symbol, where `also` is a fact about its name — and a measured ZERO says nothing at all,
    which is what lets an ordinary empty list keep its full confidence.

    @brief Say that an empty caller list may be a missing construction edge.
    @return The note, or "".
    @version 2
    """
    if payload.get("subject_kind") != "function" or payload.get("callers"):
        return ""
    return _refusal_note(payload.get("callers_unresolved")) or _constructor_note(also)


## @brief Note for an empty caller list the build recorded refusals against.
## @param sites The recorded unresolved inbound site count, or None when unmeasured.
## @return The note, or "" when there is nothing measured to report.
## @version 1
## @dg_internal
def _refusal_note(sites: Any) -> str:
    """None IS NOT ZERO. An index built before the measurement existed reports None, and reading
    that as "nothing was refused" would assert a clean bill of health from a detector that could
    not look — so None returns "" and leaves the older `also` rule to answer, exactly as it did
    before this existed.

    @brief Qualify an empty caller list against the recorded refusal count.
    @return The note, or "".
    @version 1
    """
    if not isinstance(sites, int) or isinstance(sites, bool) or sites <= 0:
        return ""
    return (
        f"`callers` is EMPTY but this is NOT a measured negative: {sites} call site(s) in this "
        f"index named a function this one could be and did not resolve to a specific one, so "
        f"callers may exist that no edge records. A member call reached through a pointer or "
        f"reference receiver resolves only when the receiver's declared type pins the class. "
        f"Read the body at the reported line range, or `search` the name, before concluding "
        f"nothing calls this."
    )


## @brief Note for an empty caller list on a name that is also a class.
## @param also The other kinds this same name resolves to.
## @return The note, or "" when this is not the constructor case.
## @version 1
## @dg_internal
def _constructor_note(also: tuple[str, ...]) -> str:
    """gh#4's rule, kept because it answers on an index that carries no measurement — and
    because it names a DIFFERENT missing thing: not a call whose receiver went unresolved, but a
    construction the grammar records no call for at all.

    NARROWED BY gh#15. `std::make_unique<T>` and `make_shared<T>` now DO resolve to the
    constructor, and a direct `T(...)` always did, so the blanket "construction is not modelled"
    is no longer true and would send a reader looking for a gap that has been closed. What
    remains unmodelled is brace initialisation, which is what gh#4 was reported against.

    @brief Say that an empty caller list may be a missing brace-initialised construction.
    @return The note, or "".
    @version 1
    """
    if "class" not in also:
        return ""
    return (
        "`callers` is EMPTY and this name also resolves to a class, so this is very likely a "
        "constructor. Brace-initialised construction (`T x{...}`) is NOT modelled as a call "
        "edge, so an empty list here does NOT mean nothing constructs this type — though "
        "`T(...)` and `std::make_unique<T>` / `make_shared<T>` do resolve. Ask `dossier` for the "
        "CLASS (kind='class') and read `candidates`, or `search` the type name, before "
        "concluding it has no users."
    )


## The candidate cap, read from the query layer rather than restated — one source for "how many
## identities is a sample".
_MAX_CANDIDATES = _common.MAX_CANDIDATES


## @brief How many distinct function identities a bare name really has.
## @param db Active database path.
## @param name The bare name.
## @return The count, or 0 when it cannot be read.
## @version 1
## @dg_internal
def _distinct_identities(db: Path, name: str) -> int:
    """COUNTED FROM THE SAME PREDICATE `candidate_rows` SLICES, so the total and the sample cannot
    describe different sets. Tolerates any failure with 0, because this runs while decorating an
    answer that already succeeded and a disclosure must never be the thing that breaks a reply.

    @brief Count same-named function rows.
    @return The count, or 0.
    @version 1
    """
    if not name:
        return 0
    try:
        with _common.connect(db) as conn:
            if not _common.table_exists(conn, "memberdef"):
                return 0
            row = conn.execute(
                "SELECT COUNT(*) FROM memberdef WHERE name=? AND kind='function'", (name,)
            ).fetchone()
    except Exception:
        return 0
    return int(row[0]) if row else 0


## @brief Disclose that the candidate list hit its cap, and how many identities really exist.
## @param db Active database path.
## @param payload The flat subject payload, already built.
## @return A disclosure dict, or None when the list was not capped.
##
## v2: same defect as `_ambiguity_block` v2 — "`qualified=` set to the signature you mean" sends
## the model to a value the accessor refuses. It also advertised "Narrow by file", and no accessor
## takes a file selector: `matching_identity`'s docstring records that one was considered and
## REJECTED. Advertising a parameter that does not exist is the same defect in a second place, so
## that clause is gone rather than reworded.
## @version 2
## @dg_internal
def _candidates_capped(db: Path | None, payload: dict[str, Any]) -> dict[str, Any] | None:
    """SILENT TRUNCATION ON THE ONE FIELD WHOSE JOB IS DISAMBIGUATION. `MAX_CANDIDATES` is 8 and
    `candidate_rows` slices to it with no disclosure, so `dossier("main")` on mbedtls returned 8 of
    **143** `main` rows and the one that mattered — the stub `main` in `ssl_pthread_server.c` that
    a non-threading build compiles — was not among them. There was no `_limited` entry, no count,
    nothing to say a choice had been made: `candidates` reads as "the identities this name has".
    That is the failure every other cap on this surface refuses or discloses to avoid.

    NOT `_limited_block`, deliberately. That block states "the full response exceeded the
    65,536-byte cap", which is a different and here FALSE reason — this list is capped by policy
    regardless of size, and a disclosure that misattributes its own cause sends a reader to shrink
    a payload that was never too big.

    COUNTED, NOT ESTIMATED. `total_available` is the whole point: "this name has 143 signatures" is
    more useful than the eight rows, and it is what tells a reader that `qualified=` is now
    mandatory rather than optional.

    @brief Say the candidate list was capped and how many identities exist.
    @return The disclosure, or None.
    @version 1
    """
    shown = payload.get("candidates")
    if db is None or not isinstance(shown, list) or len(shown) < _MAX_CANDIDATES:
        return None
    total = _distinct_identities(db, str(payload.get("subject") or ""))
    if total <= len(shown):
        return None
    return {
        "reason": (
            f"`candidates` is capped at {_MAX_CANDIDATES} identities by policy, not by response "
            f"size"
        ),
        "adjusted": {"candidates": f"{total} -> {len(shown)}"},
        "total_available": total,
        "how_to_narrow": (
            "The listed rows are a SAMPLE, not the identity set. Re-ask with `qualified=` set to "
            "a `candidates[i].qualified` — the qualified name, not the signature; `search` can "
            "enumerate the rest."
        ),
    }


## @brief Flatten a SubjectDossier to the wire shape: envelope keys plus the one section.
## @param built The resolved subject dossier, or None.
## @param db Active database path, for the function-subject ambiguity probe; omit to skip it.
## @param depth The depth the CALLER asked for, so an unhonoured one can be disclosed.
## @return The flat payload, or None when nothing resolved.
## v6: a `config` section's `found` is reconciled on the way out — it means "a Kconfig FILE was
## located", which collides with what `found` means on every other reply this surface sends.
## v7: a requirement's `mentioned_in` is dropped when the index never scanned for mentions.
## @version 7
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
    @version 6
    """
    if built is None:
        return None
    section = wire.one(built.section)
    if section is None:
        return None
    payload: dict[str, Any] = {"subject": built.subject, "subject_kind": built.kind, **section}
    ## THE CONFIG SECTION BRINGS ITS OWN `found`, meaning "a Kconfig FILE was located", which
    ## collides with what `found` means everywhere else on this surface. Replayed against the
    ## frozen mbedtls index: `dossier("MBEDTLS_THREADING_C")` served 154 gate rows,
    ## `gate_symbols: 1107` and `found: false` in one reply. Reconciled by the same helper
    ## `_search_config` uses — one rule wherever that dataclass reaches the wire, because fixing
    ## the search route alone is exactly how this one stayed broken.
    if built.kind == "config":
        payload = _config_found_on_the_wire(payload)
    ## AN INDEX THAT NEVER SCANNED FOR MENTIONS has no field, not a null one: `mentioned_in: []`
    ## and `mentioned_in: null` would both read as "nothing names this requirement".
    if built.kind == "requirement" and payload.get("mentioned_in") is None:
        payload.pop("mentioned_in", None)
    if built.also:
        payload["also"] = list(built.also)
    if built.chain is not None:
        payload["chain"] = wire.one(built.chain)
    elif depth > 1:
        payload["depth_note"] = _NO_SEED_NOTE
    ambiguity = None if db is None else _ambiguity_block(db, built)
    if ambiguity:
        payload["ambiguous"] = ambiguity
    gates, gate_gaps = (None, None) if db is None else _gate_definitions(db, payload)
    if gates:
        payload["gate_definitions"] = gates
    if gate_gaps:
        payload["gate_definitions_limited"] = gate_gaps
    ## PRESENT ONLY WHEN IT APPLIES, like every other added key here — an annotation on every
    ## empty list is one a reader learns to skip.
    callers_note = _empty_callers_note(payload, built.also or ())
    if callers_note:
        payload["callers_note"] = callers_note
    capped = _candidates_capped(db, payload)
    if capped:
        payload["candidates_limited"] = capped
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
##
## v2: each miss entry now carries a recovery hint. A batch needs it MORE than a single
## call, because the model receives up to eight negatives at once with no indication which
## were near misses.
## @version 2
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


## @brief Disclose which gate symbols were not resolved, and why each was not.
## @param no_sites Symbols looked up whose definition site the index does not hold.
## @param not_attempted Symbols beyond the per-payload cap, never looked up.
## @return The disclosure, or None when every gate resolved.
## @version 1
## @dg_internal
def _gate_definition_gaps(no_sites: list[str], not_attempted: list[str]) -> dict[str, Any] | None:
    """TWO GAPS THAT LOOKED IDENTICAL AND MEAN OPPOSITE THINGS.

    `no_definition_site` is a FACT ABOUT THE REPOSITORY, and often it is the answer: a
    `//#define MBEDTLS_THREADING_C` is a definition the preprocessor never sees, so it produces no
    `memberdef` row and the index holds none. "This gate is nowhere actively defined" is exactly
    what a reader asking about the shipped default needs.

    `not_attempted` is a fact about THIS TOOL — the cap ran out. It promises more exists; it claims
    nothing about the repository.

    Collapsing both into one absent key made a real answer indistinguishable from a truncation.

    NAMED, NEVER COUNTED. A count leaves a reader unable to ask for the one they care about, which
    is exactly how the cap hurt: the symbol two graded marks ask about was tenth alphabetically and
    silently vanished.

    @brief Say which gates did not resolve and which were never tried.
    @return The disclosure, or None.
    @version 1
    """
    if not no_sites and not not_attempted:
        return None
    gaps: dict[str, Any] = {}
    if no_sites:
        gaps["no_definition_site"] = no_sites
        gaps["no_definition_site_means"] = (
            "The index holds NO definition site for these. That is usually a fact about the "
            "repository rather than a gap: a commented-out `//#define` is not a definition the "
            "preprocessor sees, so it produces no row. Read the header named in `config_header` "
            "to confirm the shipped default."
        )
    if not_attempted:
        gaps["not_attempted"] = not_attempted
        gaps["not_attempted_means"] = (
            f"More than {_GATE_DEFINITION_CAP} distinct gates guard this code, so these were not "
            f"looked up. Ask `dossier` for one by name. Their absence above is this tool's cap, "
            f"NOT a statement about the repository."
        )
    return gaps


## @brief Resolve the symbols a payload's `gated_by` rows NAME to where they are defined.
## @param db Index path for the same target the payload came from.
## @param payload The flattened dossier payload, read for its gate rows.
## @return Mapping of gate symbol to its definition sites, or {} when nothing resolves.
## @version 3
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

    @brief Attach each gate symbol's definition sites, and disclose what was not resolved.
    @return (gate symbol -> definition sites, disclosure or None).
    @version 3
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
    ## ATTEMPTED-AND-EMPTY IS NOT NOT-ATTEMPTED. `if sites:` dropped the key for a symbol whose
    ## definition site the index genuinely does not hold — a commented-out `//#define` produces no
    ## `memberdef` row at all — so its absence from this map was indistinguishable from having been
    ## capped out. Two different answers wearing one silence. Tracked separately below.
    no_sites: list[str] = []
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
        else:
            no_sites.append(name)
    return out, _gate_definition_gaps(no_sites, names[_GATE_DEFINITION_CAP:])


## Gate symbols resolved per payload.
##
## RAISED FROM 6, BECAUSE THE ORDINARY CASE DID APPROACH IT. The previous comment called this "a
## runaway guard ... not a budget the ordinary case approaches"; mbedtls'
## `programs/ssl/ssl_pthread_server.c` sits inside ONE conditional twelve macros wide, so half were
## cut. Worse, the slice is over `sorted(names)`, so the survivors were chosen ALPHABETICALLY —
## `MBEDTLS_THREADING_C` is tenth of twelve and never resolved, which is precisely the symbol two
## graded marks ask about. A cap that silently prefers the first letters of the alphabet is not a
## runaway guard, it is a lottery.
##
## Still capped, because a deeply nested conditional is real, but the omission is now DISCLOSED by
## name rather than left to look like an absence.
_GATE_DEFINITION_CAP = 24


## Envelope keys the dossier ELIDES when they say nothing. Only the one-shot additions:
## the pre-existing keys have always been present on every reply and a consumer reading
## `doss["callees"] == []` must keep working. An absent `sections` reads as "opens no
## critical section", which is the common case on almost every function in any repo.
_DOSSIER_OPTIONAL = (
    "body",
    "sections",
    "locks_held",
    ## gh#47 part 2. Elided when empty — most functions in any repo are not reachable from an
    ## interrupt — and `context_undecidable` is NOT in this tuple for the reason
    ## `callers_unresolved` is not: a zero is what makes the empty list trustworthy.
    "context_conflicts",
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
## @param hint What to try instead, from `recovery_hint`, or "" when nothing was found.
## @return A per-symbol miss envelope.
##
## v3: carries a recovery hint. The short note said "check the envelope's `target`", which the
## 1.1.0 grid showed was almost never the problem — 80.6% of unanswered subjects were recoverable
## from what the index already held. A batched miss needs it MORE than a single one, because the
## model gets eight negatives at once and no indication which were near misses.
## @version 3
## @dg_internal
def _batch_miss(name: str, unresolved: tuple[str, ...] = (), hint: str = "") -> dict[str, Any]:
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
            "exist." + _kind_limitation_clause(unresolved) + hint
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


## The gate-row fields worth hoisting when every row agrees. Each identifies the SYMBOL or its
## resolved default rather than the SITE, so a panel of N sites repeats them N times for one
## fact. `file_path`, `line` and `end_line` are deliberately absent: they are what varies, and
## they are the reason the rows exist.
_GATE_INVARIANTS = ("symbol", "macro", "form", "default_state", "default_site", "origin")


## @brief State a gate panel's invariant fields once instead of once per row.
## @param payload A serialized config reply.
## @return The same payload with shared gate fields hoisted to `gates_shared`.
## @version 1
## @dg_internal
def _compact_gate_panel(payload: dict[str, Any]) -> dict[str, Any]:
    """MEASURED on the rebuilt mbedtls index: `dossier("MBEDTLS_THREADING_C")` serves 154 gate
    rows at 39,884 bytes, and `symbol`, `macro`, `form`, `default_state` and `default_site` each
    hold ONE distinct value across all 154. Only `file_path` varies, over 31 files. The panel
    repeats ~185 bytes of invariant text 154 times.

    WHY BYTES HERE COST MORE THAN THEY LOOK. `cache_read` is 98% of the tokens this harness
    spends — 3,470,671 against 62,559 output on the `index_only` arm — because every byte served
    sits in the context and is re-read on each later turn. A 40 KB reply at turn 3 of 20 costs
    roughly 800 KB of `cache_read` by itself. Gate panels are 11.8% of all `dossier` reply bytes
    across the grid.

    NOTHING IS REMOVED, WHICH IS THE WHOLE POINT. A cost win that drops evidence trades one axis
    for the other, and a gain on one axis only counts if the other holds. Every value a reader
    could have read off a row is still in the reply — once rather than N times.

    PER FIELD, NOT ALL-OR-NOTHING, AND NEVER A FIELD THAT VARIES. Two sites of one symbol can
    genuinely disagree — a macro defined in one profile and undefined in another — and hoisting
    the majority value would state as settled a thing the index reports as varying. A field is
    hoisted only when every row carries the identical value.

    THE WIRE ONLY. `KconfigGate` keeps every field, so the library API and the tests reading
    `gates[0].default_state` are untouched. Same placement as the `found`/`kconfig_found`
    reconciliation above, for the same reason: the dataclass is right, the serialization was
    wasteful.

    @brief Hoist invariant gate fields to the panel.
    @return The compacted payload.
    @version 1
    """
    rows = payload.get("gates")
    if not isinstance(rows, list) or not rows:
        return payload
    shared = {}
    for field in _GATE_INVARIANTS:
        values = {json.dumps(r.get(field)) for r in rows if isinstance(r, dict)}
        if len(values) == 1 and field in rows[0]:
            shared[field] = rows[0][field]
    if not shared:
        return payload
    out = dict(payload)
    out["gates_shared"] = shared
    out["gates"] = [
        {k: v for k, v in r.items() if k not in shared} if isinstance(r, dict) else r for r in rows
    ]
    return out


## @brief Re-key a config payload so `found` means what it means everywhere else.
## @param payload The serialized KconfigSpace.
## @return The same payload with `kconfig_found` added, `found` reflecting the rows served, and the gate panel compacted.
## v2: chains `_compact_gate_panel`, so all three routes that serialize a `KconfigSpace` inherit
## the compaction — the lesson of the `found` collision, where fixing one route left two broken.
## @version 2
## @dg_internal
def _config_found_on_the_wire(payload: dict[str, Any]) -> dict[str, Any]:
    """Split out of `_search_config` so the re-keying is testable without a tool set, and so the
    one place the two meanings are reconciled is named rather than inline.

    `found` BECOMES A STATEMENT ABOUT THIS REPLY: did it carry any symbol names. That is what the
    rest of the surface means by the word and what `_verdict` tests for. A corpus that genuinely
    matched nothing still reports False, so this trades no false negative for a false positive —
    which would be the worse direction, because a reader cannot check a false positive.

    THE DISCOVERY FACT IS MOVED, NOT DROPPED. "No Kconfig in this repository" and "a Kconfig that
    failed to parse" are different facts, `error` carries the second and `kconfig_found` now
    carries the first. Deleting it to resolve the collision would be fixing a misleading field by
    removing a true one.

    @brief Reconcile the two meanings of `found` on the config reply.
    @return The re-keyed payload.
    @version 1
    """
    if "found" not in payload:
        return payload
    out = dict(payload)
    out["kconfig_found"] = out["found"]
    names = out.get("gate_symbol_names") or ()
    symbols = out.get("symbols") or ()
    gates = out.get("gates") or ()
    out["found"] = bool(names or symbols or gates)
    ## COMPACTED HERE so all three routes that serialize a `KconfigSpace` inherit it, which is the
    ## lesson of the `found` collision one function up: fixing one route left two broken.
    return _compact_gate_panel(out)
