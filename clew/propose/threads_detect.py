# SPDX-License-Identifier: MIT
"""Detect repo-specific thread-spawn WRAPPERS by transitive forwarding.

`W` is a wrapper iff its body calls a known spawn `K` and the argument sitting
at `K.entry_arg_index` is one of `W`'s own parameters. `W.entry_arg_index` is
then that parameter's position in `W`. Seeded on `threads.DEFAULT_SPAWN_PATTERNS`
and iterated to a fixpoint, so a chain of any depth resolves.

Three rules do the real work and each was measured, not reasoned:

1. **The scope gate.** Nothing is proposed unless `derive_scope(...).is_derived()`
   — i.e. the repo declares an `index_scope:` that actually yields roots.
   Without it the detector has no notion of "first-party", and the first thing
   it proposes is a vendored library's own thread helper.

2. **Two corpora.** RESOLUTION runs repo-wide (a C/POSIX library's chain passes through
   a submodule macro), PROPOSAL only over definitions INSIDE the derived roots.
   This one rule — structural, not a directory blacklist — is what discards
   libmicrohttpd's `MHD_create_named_thread_`, paho's `ThreadStart`, and the
   out-of-scope `SYSTEM_TASKCREATE` whose declaration was measured to
   grow `thread_membership` from 194 to 796 with 515 of 600 functions collapsed
   into a single closure.

3. **`kind` is ALWAYS emitted.** `threads.load_thread_patterns` defaults an
   omitted `kind` to `'task'`, so staying silent asserts the ESP-IDF arm of a
   `#if` on a repo that only ever compiles the POSIX one.

@brief Transitive forwarding detector for `thread_patterns.spawns`.
@version 2
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from ..declaration import SECTION_THREADS
from ..threads import DEFAULT_SPAWN_PATTERNS
from .astdefs import FuncDef
from .context import Context
from .dryrun import measure_threads
from .model import Entry, Rejection, SectionProposal, SectionStatus
from .scanning import CallSite, census_call_sites

## Fixpoint round cap. It has to cover the deepest chain TWICE over: once to
## resolve down to a spawn primitive, and again for a disagreement discovered at
## the top to propagate back down to everything derived from it. The deepest
## measured real chain is four hops (`svc_start_task` -> macro ->
## `System_TaskCreate` -> `sys_thread_create` -> `pthread_create`),
## which converges in five rounds; eight leaves slack and still bounds a
## pathological mutually-forwarding tree.
_MAX_ROUNDS = 8

## The `kind` a fold emits when the reachable definitions disagreed. No spawn
## primitive carries it (`DEFAULT_SPAWN_PATTERNS` is task/pthread/process/
## coroutine), so seeing it in a resolved value can only mean it was WITHHELD —
## which is what lets a downstream candidate report the conflict it inherited.
_KIND_WITHHELD = "unknown"


## @brief One resolved spawn convention: arg indices, kind, and how it was derived.
## @version 1
@dataclass(frozen=True)
class Derived:
    """`conflicts` names the fields whose reachable definitions disagreed, so the
    emitted entry can say WHY a value was withheld instead of silently omitting
    it. `defs` are the definitions that produced the evidence.

    @brief A resolved (or partly resolved) spawn convention.
    @version 1
    """

    entry_arg_index: int
    name_arg_index: int | None
    kind: str
    via: tuple[str, ...]
    conflicts: tuple[str, ...] = ()
    defs: tuple[FuncDef, ...] = ()


## @brief One definition's forwarding evidence for a candidate wrapper.
## @version 1
@dataclass(frozen=True)
class _Evidence:
    """@brief Evidence that one definition forwards a parameter to a known spawn.

    @version 1
    """

    fdef: FuncDef
    via: str
    entry_arg_index: int
    name_arg_index: int | None
    kind: str


## @brief The built-in spawn primitives, as the fixpoint's seed map.
## @return Name -> Derived for every DEFAULT_SPAWN_PATTERNS entry.
## @version 1
## @req REQ-DDB-CONFIG-001
def seed_map() -> dict[str, Derived]:
    """@brief Seed the fixpoint with the language/OS spawn primitives."""
    return {
        pattern.name: Derived(
            entry_arg_index=pattern.entry_arg_index,
            name_arg_index=pattern.name_arg_index,
            kind=pattern.kind,
            via=(),
        )
        for pattern in DEFAULT_SPAWN_PATTERNS
    }


## @brief Resolve every forwarding wrapper reachable from the spawn primitives.
## @param defs Repo-wide definitions by name.
## @param max_rounds Fixpoint round cap.
## @return (resolved name -> Derived including seeds, refused name -> conflicting entry indices).
## @version 3
## @req REQ-DDB-CONFIG-001
def resolve_fixpoint(
    defs: dict[str, list[FuncDef]], max_rounds: int = _MAX_ROUNDS
) -> tuple[dict[str, Derived], dict[str, tuple[int, ...]]]:
    """Two-phase per round: collect ALL evidence against the currently-resolved
    map, then resolve. Deriving a downstream index from a value that is itself
    still unresolved is how a chain ends up asserting an argument position no
    definition actually declares.

    A later round may REVISE an earlier answer, and must. A wrapper's evidence is
    only as complete as `known` was when it was collected, so a `#if` whose arms
    reach a spawn primitive at different depths is seen one arm at a time: the IoT
    lib's `SYSTEM_TASKCREATE` resolved from its ESP-IDF arm in round 1 and
    its POSIX arm only became visible in round 3. Freezing the first answer
    published `kind: "task"` for a repo that only ever compiles pthreads — this
    feature's headline failure, a plausible wrong declaration. The disagreement is
    a property of the DEFINITIONS, not of the order they resolve in.

    @brief Iterate forwarding evidence to a fixpoint, revising as it widens.
    @version 2
    """
    known = seed_map()
    seeds = frozenset(known)
    refused: dict[str, tuple[int, ...]] = {}
    for _round in range(max_rounds):
        if not _apply_round(known, refused, _collect_evidence(defs, known, seeds)):
            break
    return known, refused


## @brief Fold one round's evidence into the resolved map.
## @param known Resolved conventions (mutated).
## @param refused Refused candidates (mutated).
## @param evidence This round's evidence, by candidate name.
## @return True when the round changed anything, so another round is warranted.
## @version 1
## @dg_internal
def _apply_round(
    known: dict[str, Derived],
    refused: dict[str, tuple[int, ...]],
    evidence: dict[str, list[_Evidence]],
) -> bool:
    """`known` and `refused` are kept DISJOINT. A name that only becomes
    contradictory once its later arms are visible has to leave `known`, or
    `proposable_names` keeps offering a candidate the report is simultaneously
    rejecting — one draft asserting both.

    Termination is bounded by the caller's round cap rather than argued from
    monotonicity: `known` normally only grows, but the refusal path can remove a
    name, so a non-converged tree stops on the cap instead of spinning.

    @brief Apply one round's resolutions, reporting whether anything moved.
    @version 1
    """
    changed = False
    for name, items in sorted(evidence.items()):
        resolved = _resolve_one(items)
        if resolved is None:
            refused[name] = tuple(sorted({e.entry_arg_index for e in items}))
            changed = known.pop(name, None) is not None or changed
        elif known.get(name) != resolved:
            known[name] = resolved
            refused.pop(name, None)
            changed = True
    return changed


## @brief Collect forwarding evidence for every not-yet-resolved definition.
## @param defs Repo-wide definitions by name.
## @param known Currently resolved spawn conventions.
## @param seeds Names of the built-in primitives (never redefined).
## @return Candidate name -> its per-definition evidence.
## @version 1
## @dg_internal
def _collect_evidence(
    defs: dict[str, list[FuncDef]], known: dict[str, Derived], seeds: frozenset[str]
) -> dict[str, list[_Evidence]]:
    """@brief Gather one round's parameter-forwarding evidence."""
    found: dict[str, list[_Evidence]] = {}
    for name, definitions in defs.items():
        if name in seeds:
            continue
        for fdef in definitions:
            for item in _definition_evidence(fdef, known):
                found.setdefault(name, []).append(item)
    return found


## @brief Evidence that one definition forwards a parameter to a known spawn.
## @param fdef The definition to inspect.
## @param known Currently resolved spawn conventions.
## @return Zero or more evidence records.
## @version 1
## @dg_internal
def _definition_evidence(fdef: FuncDef, known: dict[str, Derived]) -> list[_Evidence]:
    """@brief Read one definition's forwarding calls against the known map."""
    found: list[_Evidence] = []
    for call in fdef.forwards:
        target = known.get(call.callee)
        if target is None:
            continue
        mapping = dict(call.arg_params)
        entry_param = mapping.get(target.entry_arg_index)
        if entry_param is None:
            continue
        name_param = (
            mapping.get(target.name_arg_index) if target.name_arg_index is not None else None
        )
        found.append(_Evidence(fdef, call.callee, entry_param, name_param, target.kind))
    return found


## @brief Resolve one candidate's evidence into a Derived, or refuse it.
## @param items Every definition's evidence for one candidate name.
## @return The resolved convention, or None when definitions disagree on the entry index.
## @version 3
## @dg_internal
def _resolve_one(items: Sequence[_Evidence]) -> Derived | None:
    """Disagreement is handled per FIELD, because the failure modes differ. A
    disagreeing `entry_arg_index` makes the whole declaration meaningless and
    refuses the candidate. A disagreeing `kind` or `name_arg_index` only means
    the two `#if` arms differ, so the value is withheld ('unknown' / omitted)
    and the candidate survives — which is exactly a C/POSIX library's shape.

    A kind INHERITED as the withheld sentinel counts as a conflict too. The
    disagreement can sit several hops upstream, and a candidate that agrees with
    itself would otherwise emit a bare `kind: "unknown"` with no explanation
    anywhere in the draft — as unauditable as a wrong value, which is the one
    thing this feature may not ship. `name_arg_index` gets NO such rule: `None`
    there is also what `pthread_create` legitimately reports, so a withheld one is
    indistinguishable from a primitive that simply does not name its thread.

    @brief Fold a candidate's evidence into one convention.
    @version 3
    """
    entries = {item.entry_arg_index for item in items}
    if len(entries) != 1:
        return None
    kinds = {item.kind for item in items}
    names = {item.name_arg_index for item in items}
    kind = next(iter(kinds)) if len(kinds) == 1 else _KIND_WITHHELD
    conflicts = tuple(
        field
        for field, disagreed in (
            ("kind", len(kinds) > 1 or kind == _KIND_WITHHELD),
            ("name_arg_index", len(names) > 1),
        )
        if disagreed
    )
    return Derived(
        entry_arg_index=next(iter(entries)),
        name_arg_index=next(iter(names)) if len(names) == 1 else None,
        kind=kind,
        via=tuple(sorted({item.via for item in items})),
        conflicts=conflicts,
        defs=tuple(item.fdef for item in items),
    )


## @brief Classification counts for one candidate's call sites.
## @version 1
@dataclass(frozen=True)
class Census:
    """@brief Concrete / forwarding / opaque call-site counts, in and out of scope.

    @version 1
    """

    concrete: tuple[CallSite, ...] = ()
    forwarding: int = 0
    opaque: int = 0
    concrete_repo_wide: int = 0


## @brief Classify a candidate's call sites the way the pipeline would read them.
## @param sites Repo-wide call sites of the candidate.
## @param entry_idx The candidate's entry-argument position.
## @return The census (in-scope detail plus a repo-wide concrete count).
## @version 1
## @req REQ-DDB-CONFIG-001
def classify_sites(sites: Sequence[CallSite], entry_idx: int) -> Census:
    """CONCRETE means the entry argument names a function; FORWARDING means it
    names one of the ENCLOSING definition's parameters (so the enclosing
    definition is itself a wrapper, and declaring this one would mint a thread
    named after a parameter); OPAQUE is everything else.

    @brief Count concrete / forwarding / opaque spawn sites.
    @version 1
    """
    concrete: list[CallSite] = []
    forwarding = opaque = repo_wide = 0
    for site in sites:
        kind = _site_kind(site, entry_idx)
        repo_wide += 1 if kind == "concrete" else 0
        if not site.in_scope:
            continue
        if kind == "concrete":
            concrete.append(site)
        elif kind == "forwarding":
            forwarding += 1
        else:
            opaque += 1
    return Census(tuple(concrete), forwarding, opaque, repo_wide)


## @brief How one call site supplies its entry argument.
## @param site The call site.
## @param entry_idx The entry-argument position.
## @return "concrete", "forwarding" or "opaque".
## @version 1
## @dg_internal
def _site_kind(site: CallSite, entry_idx: int) -> str:
    """@brief Classify one spawn call site's entry argument."""
    if entry_idx < 0 or entry_idx >= len(site.arg_texts):
        return "opaque"
    token = site.arg_texts[entry_idx].strip().lstrip("&").strip()
    if not token or not _is_name(token):
        return "opaque"
    return "forwarding" if token in site.enclosing_params else "concrete"


## @brief Whether a token is a bare (optionally qualified) identifier.
## @param token Argument text with `&` and whitespace already stripped.
## @return True when the token names something rather than computing it.
## @version 1
## @dg_internal
def _is_name(token: str) -> bool:
    """@brief Test an argument token for bare-identifier shape."""
    head = token.replace("::", "_")
    return head.isidentifier()


## @brief The candidate names worth censusing, given the resolved fixpoint.
## @param known Resolved spawn conventions including seeds.
## @param corpus_defs Repo-wide definitions by name.
## @return Names that are wrappers (not primitives) and have a definition in scope.
## @version 1
## @req REQ-DDB-CONFIG-001
def proposable_names(known: dict[str, Derived], corpus_defs: dict[str, list[FuncDef]]) -> list[str]:
    """@brief Candidates whose definition sits inside the derived index scope."""
    seeds = frozenset(seed_map())
    return sorted(
        name
        for name, derived in known.items()
        if name not in seeds
        and derived.defs
        and any(fdef.in_scope for fdef in corpus_defs.get(name, ()))
    )


## @brief Detect `thread_patterns.spawns` entries for a repo.
## @param ctx Shared detector inputs.
## @return The section proposal (entries, rejections, and what was checked).
## @version 2
## @req REQ-DDB-CONFIG-001
def propose_thread_patterns(ctx: Context) -> SectionProposal:
    """@brief Run the forwarding fixpoint and gate every candidate."""
    from .threads_report import build_section

    known, refused = resolve_fixpoint(ctx.corpus.defs)
    seeds = frozenset(seed_map())
    candidates = sorted(name for name in known if name not in seeds)
    watch = frozenset(candidates)
    sites = census_call_sites(ctx.repo_root, ctx.files, ctx.in_scope, ctx.ts_classes, watch)
    by_callee: dict[str, list[CallSite]] = {}
    for site in sites:
        by_callee.setdefault(site.callee, []).append(site)
    return build_section(ctx, known, refused, candidates, by_callee)


## @brief Render the resolution chain for one candidate as one line of evidence.
## @param name Candidate name.
## @param known Resolved spawn conventions including seeds.
## @return "a -> b -> pthread_create (entry arg 2)".
## @version 1
## @req REQ-DDB-CONFIG-001
def chain_text(name: str, known: dict[str, Derived]) -> str:
    """@brief Describe how a candidate reaches a spawn primitive."""
    seeds = seed_map()
    hops = [name]
    cur = name
    while cur in known and known[cur].via and cur not in seeds and len(hops) < 8:
        cur = known[cur].via[0]
        hops.append(cur)
    tail = known.get(cur)
    suffix = f" (entry arg {tail.entry_arg_index})" if tail is not None else ""
    return " -> ".join(hops) + suffix


## @brief Measure one candidate against the real index, if there is one.
## @param ctx Shared detector inputs.
## @param name Candidate name.
## @param derived The candidate's resolved convention.
## @return The dry-run counters, empty when no measurement was possible.
## @version 1
## @req REQ-DDB-CONFIG-001
def measure_candidate(ctx: Context, name: str, derived: Derived) -> dict[str, int]:
    """@brief Run the candidate through a copy of the index."""
    if not ctx.can_measure():
        return {}
    spawn: dict[str, object] = {"name": name, "entry_arg_index": derived.entry_arg_index}
    if derived.name_arg_index is not None:
        spawn["name_arg_index"] = derived.name_arg_index
    spawn["kind"] = derived.kind
    params = frozenset(p for fdef in derived.defs for p in fdef.params if p)
    return measure_threads(Path(str(ctx.db_path)), ctx.repo_root, [spawn], params)


__all__ = [
    "SECTION_THREADS",
    "Census",
    "Derived",
    "Entry",
    "Rejection",
    "SectionProposal",
    "SectionStatus",
    "chain_text",
    "classify_sites",
    "measure_candidate",
    "proposable_names",
    "propose_thread_patterns",
    "resolve_fixpoint",
    "seed_map",
]
