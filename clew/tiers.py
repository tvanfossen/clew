# SPDX-License-Identifier: MIT
"""Five-tier precedence for every layered build option — ONE combination rule.

`resolved = (tier1 or tier2 or tier5) union tier3 union tier4`

In one line: **you can correct our guesses; you cannot un-discover a fact.**

| tier | name | what it is | combines by |
|---|---|---|---|
| 1 | explicit | a CLI flag | REPLACES the stated layer |
| 2 | declared | `.clew.yaml` / the `x-clew` passthrough | REPLACES the stated layer |
| 3 | target-fact | facts someone else already wrote — a Doxyfile's ALIASES/PREDEFINED, a generator manifest, a language or platform entry point | ACCUMULATES |
| 4 | ecosystem | a known-ecosystem signature (UDM, ingot) | ACCUMULATES |
| 5 | heuristic | name-pattern matching; the floor, explicitly provisional | REPLACES the stated layer |

WHY THIS MODULE EXISTS. "Supersede" meant three different things across the
pipeline, so moving one value from a declaration to a flag silently changed
behaviour: `cli._entry_patterns` had the flag REPLACE and the declaration EXTEND;
`shared_key_edges` had the declaration REPLACE; `--extra-input` APPENDS. The
collapse that motivated the work: passing `--entry-patterns` dropped `main`,
reachability collapsed, and NOTHING reported it. Under this rule a stated tier
can only displace the guesses, so `main` survives whatever anyone states.

TIERS 3 AND 4 HAVE IDENTICAL COMBINATION BEHAVIOUR, and saying so is the point
rather than an omission. Both accumulate and both survive every stated tier, so
an arguable 3-vs-4 call is inert — it changes the label a reader sees and nothing
about the resolved set. The load-bearing distinction is 3-or-4 versus 5: calling
a fact a guess makes it discardable, and calling a guess a fact makes it
permanent. Spend the argument there.

NOT IN `vocabulary.py`, deliberately. That module's contract is an enumerated
COLUMN's allowed values: a `Vocabulary` carries members, meaning and rank so the
DDL can ask it for a constraint clause, and a test scans the package to prove the
literal spelling of that clause appears in no other file. A tier is not a column —
the winning tier is stored in `build_meta`, whose schema is
`(key TEXT PRIMARY KEY, value TEXT)`, so there is no clause here to generate.
Forcing it in would put a value set there that nothing can generate one for, which
is how that file starts becoming "constants". This module takes the same LEAF
discipline instead: `dataclasses` and `collections.abc`, no intra-package imports,
so `signature.py` can import it without acquiring `rich`.

(That scan is not a hypothetical: the first draft of this docstring quoted the
clause keyword verbatim while explaining why the module does not use it, and the
test failed. A gate that reads text cannot tell an example from a usage.)

@brief Tiered precedence and the single layered-option resolution primitive.
@version 1
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

## Tier 1 — an operator's explicit CLI flag for this one build.
TIER_EXPLICIT = "explicit"
## Tier 2 — the target repo's standing declaration.
TIER_DECLARED = "declared"
## Tier 3 — a fact someone else already wrote down (language, platform, or the
## target's own manifests). Accumulates; no stated tier can remove it.
TIER_TARGET_FACT = "target-fact"
## Tier 4 — a known-ecosystem signature. Accumulates, exactly as tier 3 does.
TIER_ECOSYSTEM = "ecosystem"
## Tier 5 — a name-pattern guess. The floor, and the only built-in layer a stated
## tier is allowed to displace.
TIER_HEURISTIC = "heuristic"

## Highest precedence first. Used for reporting and for pinning the tier names in
## one place; the combination rule below is not derived from position, because
## tiers 3 and 4 do not participate in precedence at all.
TIER_ORDER: tuple[str, ...] = (
    TIER_EXPLICIT,
    TIER_DECLARED,
    TIER_TARGET_FACT,
    TIER_ECOSYSTEM,
    TIER_HEURISTIC,
)

## The three tiers that compete to supply the REPLACEABLE layer, highest first.
STATED_TIERS: tuple[str, ...] = (TIER_EXPLICIT, TIER_DECLARED, TIER_HEURISTIC)

## The two tiers that accumulate underneath and survive every stated tier.
ACCUMULATING_TIERS: tuple[str, ...] = (TIER_TARGET_FACT, TIER_ECOSYSTEM)

## The `build_meta` prefix the resolved options are stamped under, imported by
## both the writer (`signature`) and the reader (`cli`) rather than spelled twice.
## The four older sections still carry their prefix as a literal in both places;
## that duplication predates this constant and churning it is unrelated work.
OPTIONS_META_PREFIX = "options"

## Per-option keys inside that section.
TIER_KEY = "tier"
EXPLICIT_KEY = "explicit"

## How a stored DOCUMENT is serialised: sorted keys and no whitespace, i.e. CANONICAL.
## Byte-stability across processes is the requirement, not compactness. A manifest
## document arrives as a mapping whose insertion order is whatever the caller (or a YAML
## parser) happened to produce, so an unsorted dump of two equal documents differs by
## bytes — and `build_meta` is compared verbatim by
## `test_warm_rebuild_is_deterministic`, which would then fail intermittently rather
## than usefully. Sorting also means a re-stated identical document produces an
## identical row, so nothing downstream sees a change where none was made.
DOCUMENT_SEPARATORS: tuple[str, str] = (",", ":")

## How a stored value LIST is joined. A NEWLINE, not `scope.py`'s `", "`, and the
## difference is load-bearing rather than stylistic: the values here are SQL LIKE
## patterns and a pattern containing a comma or a space (`handle,%`, `on %`) is
## perfectly ordinary, while one containing a newline is not something a shell
## invocation produces. `scope`'s separator is safe for the repo-relative PATHS it
## joins and would corrupt the replay here.
VALUE_SEPARATOR = "\n"


## @brief One layered option's resolved values together with the tier that won.
## @version 1
@dataclass(frozen=True)
class LayeredResolution:
    """The values AND their provenance, bound together so a caller cannot hold one
    without the other.

    That binding is the mechanism, not decoration. The task this implements states
    that a tiered resolution is only useful if the tier that won is recorded and
    reported — otherwise it is the same opacity with more steps. A resolver
    returning a bare list makes forgetting the default; returning this makes
    forgetting require deliberately discarding a field, and `options_meta` below
    REFUSES anything that is not one of these, so the stamping path cannot be fed
    values whose tier was dropped along the way.

    `stated` is the winning stated layer verbatim, kept apart from `values`
    because only a tier-1 statement is ever replayed onto a later build — a tier-2
    declaration re-derives itself from a file that may have changed since, and
    replaying a stored copy would freeze a stale declaration.

    @brief A resolved layered option: values, winning tier, stated layer.
    @version 1
    """

    values: tuple[str, ...]
    tier: str
    stated: tuple[str, ...]

    ## @brief Flatten this resolution into `build_meta` rows for one option.
    ## @param option The option's name, used as the key prefix inside the section.
    ## @return Mapping of unprefixed build_meta key to value.
    ## @version 1
    ## @req REQ-DDB-CONFIG-006
    def as_meta(self, option: str) -> dict[str, str]:
        """The tier is ALWAYS recorded; the stated layer only when tier 1 won.

        Writing `explicit` unconditionally would make the read-back replay a
        declaration or the built-in guesses as though an operator had typed them,
        which is the failure `_operator_excludes` avoids by recording only what the
        operator actually stated. An absent key honestly reads as "nothing to
        replay", matching the writer's rule that falsy values are dropped.

        @brief Build the build_meta fragment for this resolution.
        @return Unprefixed key/value mapping.
        @version 1
        """
        meta = {f"{option}.{TIER_KEY}": self.tier}
        if self.tier == TIER_EXPLICIT and self.stated:
            meta[f"{option}.{EXPLICIT_KEY}"] = VALUE_SEPARATOR.join(self.stated)
        return meta


## @brief Serialise a stated document to the byte-stable form `build_meta` stores.
## @param value The stated document, or the path string that names one.
## @return Canonical JSON: sorted keys, no whitespace.
## @version 1
## @req REQ-DDB-CONFIG-006
def canonical_document(value: str | Mapping[str, Any]) -> str:
    """CANONICAL MEANS BYTE-STABLE ACROSS PROCESSES, and that is a correctness
    property here rather than tidiness. Two builds of one unchanged tree must produce
    an identical `build_meta`, which is what `test_warm_rebuild_is_deterministic`
    asserts; a dump that preserved insertion order would make the stored row a
    function of how the caller happened to spell its mapping, so re-stating an
    equal document would read as a change.

    A PATH and a DOCUMENT share this one row and JSON tells them apart for free — a
    path serialises as a JSON string, a document as a JSON object — so the reader
    needs no second key to say which form was stated, and cannot get that answer
    wrong.

    @brief Canonically serialise a stated manifest document or path.
    @return The stored representation.
    @version 1
    """
    return json.dumps(value, sort_keys=True, separators=DOCUMENT_SEPARATORS)


## @brief One manifest-shaped option's stated document together with the tier that supplied it.
## @version 1
@dataclass(frozen=True)
class DocumentResolution:
    """THE DOCUMENT COUNTERPART of `LayeredResolution`, for the five manifest options
    whose stated layer is a whole document (or a path to one) rather than a list of
    strings — `shared_key_patterns`, `thread_patterns`, `locks`, `dispatch`,
    `mqtt_dispatch`.

    IT CARRIES NO `values`, deliberately. A manifest's resolved effect is rows in a
    dozen tables, computed several frames down inside the loaders; there is no short
    value to record and inventing one would put a summary in `build_meta` that the
    tables are free to disagree with. What is recordable — and what a later build
    needs — is WHO supplied the document and, when that was an operator, the document
    itself.

    WHY THE STAMP IS LOAD-BEARING AND NOT DECORATION (owner decision, gh#364).
    Replaying a statement means the index carries a policy the REPOSITORY does not
    declare, so two operators of the same commit can get different indexes. That is
    the shape of the defect rejected in gh#352, where an external tag was a property
    of the working COPY rather than of the repository. What makes it acceptable here
    is that a statement is DELIBERATE and RECORDED where the gitlink case was
    accidental and silent. If this row is missing, this becomes that defect. Two
    operators may differ; they must never differ SILENTLY.

    @brief A resolved manifest option: the winning tier and the stated document.
    @version 1
    """

    tier: str
    stated: str | Mapping[str, Any] | None = None

    ## @brief Flatten this resolution into `build_meta` rows for one option.
    ## @param option The option's name, used as the key prefix inside the section.
    ## @return Mapping of unprefixed build_meta key to value.
    ## @version 1
    ## @req REQ-DDB-CONFIG-006
    def as_meta(self, option: str) -> dict[str, str]:
        """THE TIER IS ALWAYS WRITTEN, exactly as `LayeredResolution.as_meta` writes
        it, and for the reason `recorded_explicit` documents: the tier row is what
        makes a withdrawal unreplayable. `write_build_signature` upserts and never
        deletes, so a retracted statement can survive beside a fresh tier row, and the
        reader resolves that contradiction by trusting the tier. Skip the tier row for
        a withdrawal and that guard has nothing to compare against.

        The DOCUMENT is written only for a tier-1 win. A tier-2 declaration re-derives
        itself from a file that may have changed since, so replaying a stored copy
        would freeze a stale declaration.

        @brief Build the build_meta fragment for this resolution.
        @return Unprefixed key/value mapping.
        @version 1
        """
        meta = {f"{option}.{TIER_KEY}": self.tier}
        if self.tier == TIER_EXPLICIT and self.stated:
            meta[f"{option}.{EXPLICIT_KEY}"] = canonical_document(self.stated)
        return meta


## @brief Resolve one manifest option: an operator's statement, else the declaration.
## @param explicit Tier-1 statement — a path string, the document inline, or falsy.
## @param declared The target's own declared document, or falsy when it declares none.
## @return The resolution, carrying the winning tier and the statement to record.
## @version 1
## @req REQ-DDB-CONFIG-006
def resolve_document(
    *,
    explicit: str | Mapping[str, Any] | None = None,
    declared: Mapping[str, Any] | None = None,
) -> DocumentResolution:
    """THE SAME THREE-WAY CHOICE `_stated_layer` makes, on a document instead of a
    list, so `cli._declared_or_flag`'s precedence and this label cannot disagree about
    which tier won.

    AN EMPTY DOCUMENT IS A WITHDRAWAL, not a statement — `{}` is falsy, so it falls
    through to the declaration and then to the floor, and no statement is recorded.
    That is one spelling doing both jobs on purpose (owner decision, gh#364): clearing
    an option means "stop overriding", which is the same intent as "fall back to the
    target's own declaration".

    THE FLOOR IS LABELLED `heuristic` AND THAT NEEDS READING CAREFULLY. It does NOT
    say the built-in lock, spawn and accessor patterns are guesses — those are tier-3
    and tier-4 layers that ACCUMULATE underneath and no stated tier can displace them.
    It says nobody stated a document, so the replaceable layer is empty and the
    resolved set is exactly what accumulates. That is the identical meaning
    `_stated_layer` gives the label when no list is stated either.

    @brief Resolve which tier supplied one manifest document.
    @return The resolution for that option.
    @version 1
    """
    if explicit:
        return DocumentResolution(TIER_EXPLICIT, explicit)
    if declared:
        return DocumentResolution(TIER_DECLARED)
    return DocumentResolution(TIER_HEURISTIC)


## @brief Resolve one layered option: (tier1 or tier2 or tier5) union tier3 union tier4.
## @param facts Tier-3 values — facts someone else already wrote. Always present.
## @param explicit Tier-1 values from a CLI flag; None absent, [] withdrawn.
## @param declared Tier-2 values from the target's declaration, or None.
## @param ecosystem Tier-4 values from a known-ecosystem signature.
## @param heuristics Tier-5 name-pattern guesses — the layer a stated tier displaces.
## @return The resolved values and the stated tier that won.
## @version 1
## @req REQ-DDB-CONFIG-006
def resolve_layered(
    *,
    facts: Iterable[str],
    explicit: Sequence[str] | None = None,
    declared: Sequence[str] | None = None,
    ecosystem: Iterable[str] = (),
    heuristics: Iterable[str] = (),
) -> LayeredResolution:
    """KEYWORD-ONLY, because five same-typed sequence arguments in a row is a
    transposition waiting to happen and transposing `facts` with `heuristics` would
    invert the whole rule silently — the accumulating layer would become
    discardable and the guesses would become permanent, with every count still
    looking legitimate.

    THE ACCUMULATING LAYERS COME FIRST in the resolved order, so a target that
    states nothing resolves to exactly `(*facts, *ecosystem, *heuristics)` — the
    built-in default set, unchanged and comparable by equality rather than by set
    membership. That makes the success-path control a strict assertion instead of a
    loose one, which matters here: this repo has shipped a check that tested only
    its failure path.

    AN EMPTY `explicit` IS A WITHDRAWAL, not a statement. `[]` is falsy, so it
    falls through to the declaration and then to the guesses, which is what lets an
    operator undo a recorded flag without deleting the database. `None` means the
    flag was absent.

    @brief Combine the five tiers into one resolved option.
    @return The resolution, carrying the winning stated tier.
    @version 1
    """
    tier, stated = _stated_layer(explicit, declared, heuristics)
    return LayeredResolution(
        values=_ordered_unique((*facts, *ecosystem, *stated)),
        tier=tier,
        stated=stated,
    )


## @brief Pick the stated layer: tier 1, else tier 2, else the tier-5 floor.
## @param explicit Tier-1 values, or None.
## @param declared Tier-2 values, or None.
## @param heuristics Tier-5 values.
## @return (winning tier name, that tier's values).
## @version 1
## @dg_internal
def _stated_layer(
    explicit: Sequence[str] | None,
    declared: Sequence[str] | None,
    heuristics: Iterable[str],
) -> tuple[str, tuple[str, ...]]:
    """@brief Choose which of the three replaceable tiers supplies the stated layer.
    @return The tier name and its values.
    @version 1
    """
    if explicit:
        return TIER_EXPLICIT, tuple(str(v) for v in explicit)
    if declared:
        return TIER_DECLARED, tuple(str(v) for v in declared)
    return TIER_HEURISTIC, tuple(heuristics)


## @brief De-duplicate while preserving first-seen order.
## @param values The concatenated layers.
## @return Order-preserving unique tuple.
## @version 1
## @dg_internal
def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    """A stated tier may legitimately restate a fact (`--entry-patterns main …`),
    and a duplicated SQL LIKE pattern would add a redundant `OR name LIKE ?` term
    rather than break anything — but the stored provenance and the reported set
    would both show it, so it is removed here once instead of at each consumer.

    @brief Remove duplicates, keeping the first occurrence.
    @return Unique values in order.
    @version 1
    """
    seen: dict[str, None] = {}
    for value in values:
        seen.setdefault(value, None)
    return tuple(seen)


## The two resolution types the stamping path accepts — a list-valued option and a
## document-valued one. A TUPLE rather than a widened `isinstance` written inline,
## because the REFUSAL is the mechanism: adding a third resolution type must be a
## deliberate edit here, and a bare list or mapping must keep being rejected.
RESOLUTION_TYPES: tuple[type, ...] = (LayeredResolution, DocumentResolution)


## @brief Flatten resolved options into the `build_meta` section they are stamped as.
## @param resolutions Option name to its LayeredResolution or DocumentResolution.
## @return Unprefixed build_meta mapping covering every option given.
## @version 2
## @req REQ-DDB-CONFIG-006
def options_meta(**resolutions: LayeredResolution | DocumentResolution) -> dict[str, str]:
    """THE ONLY PRODUCER of the `options.*` rows, and it accepts only resolutions.

    That refusal is what makes "record the tier" structural rather than a habit. A
    caller cannot stamp a layered option from a bare list, because there is no code
    path from a list to these rows; it has to hold the object that knows which tier
    won. Raising `TypeError` rather than coercing follows the repo's fail-closed
    rule — a silently skipped option would present exactly as an older index that
    never recorded one.

    A DOCUMENT-VALUED OPTION goes through the same door (gh#364). The five manifest
    options state a whole document rather than a list, and routing them through a
    second producer would give the `options.*` section two writers free to disagree
    about the key layout the reader depends on.

    @brief Build the `options` build_meta section from resolutions.
    @return Unprefixed key/value mapping.
    @version 2
    """
    meta: dict[str, str] = {}
    for option, resolution in resolutions.items():
        if not isinstance(resolution, RESOLUTION_TYPES):
            raise TypeError(
                f"options_meta({option}=...) needs a LayeredResolution or "
                f"DocumentResolution carrying its winning tier, got "
                f"{type(resolution).__name__}. Resolve the option through "
                f"resolve_layered() or resolve_document() rather than passing bare values."
            )
        meta.update(resolution.as_meta(option))
    return meta


## @brief Read back the tier-1 statement a previous build recorded for one option.
## @param section The prefix-stripped `options` build_meta section.
## @param option The option's name.
## @return The recorded explicit values, or () when none was recorded or the tier disagrees.
## @version 2
## @req REQ-DDB-CONFIG-006
def recorded_explicit(section: Mapping[str, str], option: str) -> tuple[str, ...]:
    """ONLY tier 1 is replayable, and this CROSS-CHECKS the tier rather than
    trusting the statement key alone.

    The first version read the statement key by itself, on the argument that the
    policy lived in the writer so the reader had no decision to get wrong. A
    control written in the awkward direction — stamp an explicit statement, then
    stamp its WITHDRAWAL onto the same database — showed that wrong.
    `write_build_signature` upserts and never deletes, so the retracted
    `<option>.explicit` row survived beside a fresh `<option>.tier = heuristic` and
    this function replayed a statement the operator had just withdrawn.

    The real pipeline does not reach it today, because every build stamps a fresh
    temp database that then replaces the live one — but that is an invariant in a
    DIFFERENT module, and depending on it silently means a later caller stamping
    onto a live database (which `_stamp_refresh_metrics` already does, for another
    section) turns a retraction into a replay with nothing to notice it.

    So the TIER is authoritative: it is written on every stamp, and a statement
    that disagrees with it is a contradictory record, which resolves to "nothing to
    replay" rather than to the more interesting of the two readings.

    Same defect this closes as `_operator_excludes`: a resolution that is applied
    and recorded but never read back is discarded by the next refresh, which then
    reports success over exactly the shape the operator asked for.

    @brief Read one option's recorded explicit statement, if the tier agrees.
    @return The recorded values, or ().
    @version 2
    """
    if section.get(f"{option}.{TIER_KEY}") != TIER_EXPLICIT:
        return ()
    raw = section.get(f"{option}.{EXPLICIT_KEY}", "")
    return tuple(part for part in raw.split(VALUE_SEPARATOR) if part)


## @brief Read back the tier-1 manifest DOCUMENT a previous build recorded for one option.
## @param section The prefix-stripped `options` build_meta section.
## @param option The option's name.
## @return The recorded document or path, or None when none was recorded or the tier disagrees.
## @version 1
## @req REQ-DDB-CONFIG-006
def recorded_document(section: Mapping[str, str], option: str) -> str | dict[str, Any] | None:
    """THE SAME TIER CROSS-CHECK `recorded_explicit` DOES, and it is checked here for
    the document form rather than assumed to carry over: the guard lives in the READER,
    so a second reader that skipped it would replay a withdrawn statement while the
    first one refused to. `write_build_signature` upserts and never deletes, so a
    retracted `<option>.explicit` row can outlive the statement it recorded; the tier
    row is written on every stamp, so the tier is authoritative and a statement that
    disagrees with it resolves to "nothing to replay".

    A CORRUPT RECORD RAISES rather than reading as "no statement". Reverting silently
    to the target's own declaration is precisely the defect this whole read-back
    exists to remove — a build that cannot honour the recorded policy must not report
    success over a different one. Nothing but this module writes the row, so reaching
    the raise means the database was edited by hand.

    @brief Read one option's recorded manifest statement, if the tier agrees.
    @return The recorded document, the recorded path, or None.
    @version 1
    """
    if section.get(f"{option}.{TIER_KEY}") != TIER_EXPLICIT:
        return None
    raw = section.get(f"{option}.{EXPLICIT_KEY}", "")
    if not raw:
        return None
    return _decoded_document(option, raw)


## @brief Decode one stored document row, refusing anything that is not a path or a mapping.
## @param option The option's name, for the message.
## @param raw The stored canonical JSON.
## @return The path string or the document mapping.
## @version 1
## @dg_internal
def _decoded_document(option: str, raw: str) -> str | dict[str, Any]:
    """THE TYPE IS CHECKED, not just the syntax. A row decoding to a list or a number
    is well-formed JSON that no loader can read, and handing it on would push the
    failure into a manifest parser several frames away where the message would name a
    shape rather than a corrupt record.

    @brief Decode and type-check a stored manifest statement.
    @return The decoded statement.
    @version 1
    """
    try:
        value = json.loads(raw)
    except ValueError as exc:  # json.JSONDecodeError is a ValueError
        raise ValueError(
            f"the recorded tier-1 statement for {option!r} is not readable ({exc}). "
            f"Nothing but clew writes this row, so the index's build_meta has "
            f"been edited. Re-state the option, or clear it with {{}}, rather than "
            f"letting the build silently fall back to the target's declaration."
        ) from exc
    if not isinstance(value, (str, dict)):
        raise ValueError(
            f"the recorded tier-1 statement for {option!r} decodes to a "
            f"{type(value).__name__}, but a manifest statement is a path (string) or a "
            f"document (mapping). Re-state the option, or clear it with {{}}."
        )
    return value


## @brief Which options the index carries an operator's own statement for.
## @param section The prefix-stripped `options` build_meta section.
## @return Sorted option names whose recorded tier is tier 1.
## @version 1
## @req REQ-DDB-CONFIG-006
def stated_options(section: Mapping[str, str]) -> tuple[str, ...]:
    """THE VISIBLE STAMP, and the owner's condition for allowing a statement to be
    replayed at all (gh#364). A replayed statement makes this index a function of what
    an operator once said as well as of the commit, so two operators of one commit can
    legitimately hold different indexes — acceptable ONLY because it is deliberate and
    recorded. This is what makes it findable without reading seven option rows and
    knowing which tier name matters.

    DERIVED FROM THE STORED SECTION, never stamped as a row of its own. A stored
    summary is a second source of truth that can disagree with the rows it summarises,
    which is exactly where a silent wrong answer hides — the same reason the per-target
    state directory was rejected as a home for the record itself.

    @brief Name the options carrying a tier-1 statement.
    @return Sorted option names.
    @version 1
    """
    suffix = f".{TIER_KEY}"
    return tuple(
        sorted(
            key[: -len(suffix)]
            for key, value in section.items()
            if key.endswith(suffix) and value == TIER_EXPLICIT
        )
    )
