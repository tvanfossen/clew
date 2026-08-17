# SPDX-License-Identifier: MIT
"""Turn resolved spawn wrappers into gated entries, rejections and evidence.

Split from `threads_detect` so the derivation (a fixpoint) and the judgement
(four gates plus the prose that justifies each verdict) stay separately
readable.

Rejections are a deliverable here, not debug output. A C/POSIX library's most
prolific spawn wrapper drives 12 concrete call sites repo-wide and is REFUSED
because it is defined in a submodule outside the index scope; an owner who
cannot see that reasoning will conclude clew simply missed it. The rejection
therefore carries the measurement that justifies it.

@brief Gating, evidence prose and YAML shaping for `thread_patterns`.
@version 1
"""

from __future__ import annotations

from ..declaration import SECTION_THREADS
from .context import Context
from .model import Entry, Rejection, SectionProposal, SectionStatus
from .scanning import CallSite
from .threads_detect import (
    Census,
    Derived,
    chain_text,
    classify_sites,
    measure_candidate,
)

## Cap on how many concrete call sites are listed per entry. The point of the
## list is to let an owner spot-check attribution, not to reproduce a grep.
_MAX_SITES_SHOWN = 6

_HEADER = ("thread_patterns:", "  spawns:")


## @brief Build the whole `thread_patterns` section from resolved candidates.
## @param ctx Shared detector inputs.
## @param known Resolved spawn conventions including the built-in seeds.
## @param refused Candidates whose definitions disagreed on the entry argument index.
## @param candidates Resolved non-seed names, sorted.
## @param by_callee Repo-wide call sites grouped by callee name.
## @return The section proposal.
## @version 2
## @req REQ-DDB-CONFIG-001
def build_section(
    ctx: Context,
    known: dict[str, Derived],
    refused: dict[str, tuple[int, ...]],
    candidates: list[str],
    by_callee: dict[str, list[CallSite]],
) -> SectionProposal:
    """@brief Gate every candidate and assemble the section."""
    entries: list[Entry] = []
    rejections: list[Rejection] = [
        Rejection(
            name=name,
            reason=(
                "reachable definitions disagree on the entry-argument index "
                f"({', '.join(str(i) for i in indices)}) — no single declaration is true"
            ),
            evidence=_definition_lines(ctx, name),
        )
        for name, indices in sorted(refused.items())
    ]
    for name in candidates:
        outcome = _judge(ctx, name, known, by_callee.get(name, []))
        if isinstance(outcome, Entry):
            entries.append(outcome)
        else:
            rejections.append(outcome)
    return SectionProposal(
        name=SECTION_THREADS,
        status=SectionStatus.PROPOSED if entries else SectionStatus.NO_CANDIDATES,
        reason=_reason(ctx, entries, candidates),
        checked={
            "files_scanned": ctx.corpus.files_parsed,
            "definitions": sum(len(v) for v in ctx.corpus.defs.values()),
            "forwarding_candidates": len(candidates),
            "proposed": len(entries),
        },
        entries=tuple(entries),
        rejections=tuple(rejections),
        notes=_NOT_DETECTED,
        yaml_header=_HEADER if entries else (),
    )


## @brief One-line summary of what the detector did.
## @param ctx Shared detector inputs.
## @param entries Accepted entries.
## @param candidates Every resolved candidate name.
## @return The reason string.
## @version 2
## @dg_internal
def _reason(ctx: Context, entries: list, candidates: list[str]) -> str:
    """@brief Summarise the thread scan for the section header."""
    return (
        f"scanned {ctx.corpus.files_parsed} C/C++ files repo-wide for forwarding "
        f"definitions; {len(candidates)} candidate(s), {len(entries)} proposed. "
        "A candidate is proposed only when its DEFINITION is inside the index "
        "scope — a wrapper defined outside it matches call sites clew cannot "
        "attribute."
    )


## @brief Accept a candidate as an Entry or refuse it as a Rejection.
## @param ctx Shared detector inputs.
## @param name Candidate name.
## @param known The whole resolved map (the chain walk needs it).
## @param sites Its repo-wide call sites.
## @return An Entry when every gate passes, else a Rejection.
## @version 1
## @dg_internal
def _judge(
    ctx: Context, name: str, known: dict[str, Derived], sites: list[CallSite]
) -> Entry | Rejection:
    """@brief Apply the scope, census and dry-run gates to one candidate."""
    derived = known[name]
    census = classify_sites(sites, derived.entry_arg_index)
    refusal = _gate(ctx, name, known, census)
    if refusal is not None:
        return refusal
    measured = measure_candidate(ctx, name, derived)
    fabrication = _fabrication(measured) if measured else ""
    if fabrication:
        return Rejection(name, fabrication, _evidence(ctx, name, known, census, measured))
    return Entry(
        yaml_lines=_yaml(name, derived),
        evidence=_evidence(ctx, name, known, census, measured),
        measured=measured,
    )


## @brief The first gate a candidate fails, or None when it passes all of them.
## @param ctx Shared detector inputs.
## @param name Candidate name.
## @param known The whole resolved map.
## @param census Its classified call sites.
## @return A Rejection, or None.
## @version 2
## @dg_internal
def _gate(ctx: Context, name: str, known: dict[str, Derived], census: Census) -> Rejection | None:
    """@brief Apply the structural gates (scope, then concrete call sites)."""
    in_scope_defs = [d for d in ctx.corpus.defs.get(name, ()) if d.in_scope]
    evidence = _evidence(ctx, name, known, census, {})
    if not in_scope_defs:
        return Rejection(
            name,
            "definition outside the index scope — clew cannot attribute its "
            f"call sites ({census.concrete_repo_wide} concrete repo-wide). Widen the "
            "index to cover it and re-run rather than declaring it.",
            evidence,
        )
    if not census.concrete:
        return Rejection(
            name,
            f"no concrete call site in the index scope ({census.forwarding} forwarding, "
            f"{census.opaque} opaque) — it is an internal hop of a longer chain",
            evidence,
        )
    return None


## @brief The dry-run fabrication verdict for a measured candidate.
## @param measured Dry-run counters.
## @return A refusal reason, or "" when the measurement is clean.
## @version 1
## @dg_internal
def _fabrication(measured: dict[str, int]) -> str:
    """A thread with a NULL entry has no closure, and a thread NAMED after the
    wrapper's own parameter is a row invented from a forwarded argument. Either
    means the declaration writes rows describing nothing in the repo.

    @brief Judge a dry run's fabrication metrics.
    @version 1
    """
    if measured.get("threads_new", 0) <= 0:
        return "dry run against the index added no threads — declaring it changes nothing"
    fabricated = measured.get("unresolved_entry_new", 0) + measured.get("param_named_new", 0)
    if fabricated:
        return (
            f"dry run fabricates {fabricated} thread row(s): "
            f"{measured.get('unresolved_entry_new', 0)} with an unresolved entry, "
            f"{measured.get('param_named_new', 0)} named after a wrapper parameter"
        )
    return ""


## @brief The YAML lines for one accepted spawn entry.
## @param name Candidate name.
## @param derived Its resolved convention.
## @return Indented YAML list-item lines.
## @version 1
## @dg_internal
def _yaml(name: str, derived: Derived) -> tuple[str, ...]:
    """`kind` is emitted unconditionally — see the module docstring of
    `threads_detect` on why silence is an assertion here.

    @brief Shape one spawns list entry.
    @version 1
    """
    lines = [f'    - name: "{name}"', f"      entry_arg_index: {derived.entry_arg_index}"]
    if derived.name_arg_index is not None:
        lines.append(f"      name_arg_index: {derived.name_arg_index}")
    lines.append(f'      kind: "{derived.kind}"')
    return tuple(lines)


## @brief Where a candidate is defined, one line per definition.
## @param ctx Shared detector inputs.
## @param name Candidate name.
## @return Evidence lines naming each definition and its scope membership.
## @version 1
## @dg_internal
def _definition_lines(ctx: Context, name: str) -> tuple[str, ...]:
    """@brief List a candidate's definitions and whether each is in scope."""
    return tuple(
        f"defined  {d.rel_path}:{d.line}"
        f"   [{'inside' if d.in_scope else 'OUTSIDE'} index scope]"
        f"{'   (macro)' if d.is_macro else ''}"
        for d in ctx.corpus.defs.get(name, ())
    )


## @brief The full evidence block for one candidate.
## @param ctx Shared detector inputs.
## @param name Candidate name.
## @param known The whole resolved map (the chain walk needs it).
## @param census Its classified call sites.
## @param measured Dry-run counters (may be empty).
## @return Evidence lines.
## @version 2
## @dg_internal
def _evidence(
    ctx: Context, name: str, known: dict[str, Derived], census: Census, measured: dict[str, int]
) -> tuple[str, ...]:
    """@brief Assemble the derivation, census and measurement prose."""
    derived = known[name]
    params = next((d.params for d in ctx.corpus.defs.get(name, ()) if d.params), ())
    forwarded = params[derived.entry_arg_index] if derived.entry_arg_index < len(params) else "?"
    lines = [
        f"{name}({', '.join(params) or '...'})",
        f"  forwards param {derived.entry_arg_index} `{forwarded}`",
        *(f"  {line}" for line in _definition_lines(ctx, name)),
        f"  chain    {chain_text(name, known)}",
        f"  call sites in scope: {len(census.concrete)} concrete, "
        f"{census.forwarding} forwarding, {census.opaque} opaque",
        *(
            f"    {s.rel_path}:{s.line}  entry={s.arg_texts[derived.entry_arg_index].strip()}"
            for s in census.concrete[:_MAX_SITES_SHOWN]
        ),
        f"  repo-wide: {census.concrete_repo_wide} concrete site(s), "
        f"{len(census.concrete)} in scope"
        + (
            ""
            if census.concrete_repo_wide == len(census.concrete)
            else f" — RECALL SHORTFALL of {census.concrete_repo_wide - len(census.concrete)}"
        ),
    ]
    lines.extend(_conflict_lines(derived))
    lines.extend(_measured_lines(measured) if measured else _not_measured(ctx))
    return tuple(lines)


## @brief Why a candidate carries no measurement.
## @param ctx Shared detector inputs.
## @return The explanation lines.
## @version 2
## @dg_internal
def _not_measured(ctx: Context) -> tuple[str, ...]:
    """Two different causes, and stating the wrong one is worse than saying
    nothing. A candidate refused at a structural gate is never measured even when
    an index is present — reporting that as "no built index" told a reader who had
    just passed one that their index was missing, and invited them to go looking
    for a problem that was not there.

    @brief Distinguish "refused before measuring" from "nothing to measure with".
    @version 2
    """
    if ctx.can_measure():
        return (
            "  NOT MEASURED — refused at a structural gate, before the dry run. Measuring "
            "a wrapper clew cannot attribute would only produce numbers for a "
            "declaration it is not going to make.",
        )
    return _NOT_MEASURED


## @brief Why a value was withheld, when definitions disagreed.
## @param derived The candidate's resolved convention.
## @return Zero or more evidence lines.
## @version 2
## @dg_internal
def _conflict_lines(derived: Derived) -> list[str]:
    """Each line stands alone. The two conflicts are independent — a kind can be
    withheld several hops upstream while `name_arg_index` agrees — so the kind
    line may be the only one printed and cannot lean on the other for its reason.

    @brief Explain each withheld field.
    @version 2
    """
    lines = []
    if "name_arg_index" in derived.conflicts:
        lines.append(
            "  name_arg_index WITHHELD — reachable definitions disagree; threads "
            "will be named after their entry function instead"
        )
    if "kind" in derived.conflicts:
        lines.append(
            '  kind: "unknown" — the reachable definitions disagree (here or further '
            "up the chain), so no single OS arm is true. Stated EXPLICITLY because an "
            'OMITTED kind means "task" (threads.load_thread_patterns default), which '
            "would assert a different OS arm than this target compiles"
        )
    return lines


## @brief The measured-yield block for one candidate.
## @param measured Dry-run counters.
## @return Evidence lines describing the delta.
## @version 1
## @dg_internal
def _measured_lines(measured: dict[str, int]) -> list[str]:
    """@brief Render a thread dry run's before/after counters."""
    return [
        "  MEASURED — dry run of extract_threads on a copy of the index:",
        f"    threads            {measured['threads_before']} -> {measured['threads_after']}",
        f"    thread_membership  {measured['membership_before']} -> "
        f"{measured['membership_after']}  "
        f"(+{measured['membership_after'] - measured['membership_before']})",
        f"    distinct functions {measured['distinct_fns_after']}; "
        f"in >1 thread {measured['multi_thread_fns_after']}",
        f"    new threads with an unresolved entry: {measured['unresolved_entry_new']}; "
        f"named after a parameter: {measured['param_named_new']}",
    ]


_NOT_MEASURED = (
    "  NOT MEASURED — no built index (or --no-dry-run): the numbers a dry run "
    "would produce are unknown, so this entry is unverified.",
)

_NOT_DETECTED = (
    "NOT DETECTED: the trampoline idiom (pthread_create(&t, NULL, tramp, ctx) "
    "with the real entry inside ctx) and multi-call lambda entries. Both are "
    "fail-closed by construction and must be hand-declared.",
)
