# SPDX-License-Identifier: MIT
"""Gate accessor pairs on a measured dry run and write the evidence.

The gate is the deliverable. Every structural filter in `sharedkey_detect` is
necessary and none of them is sufficient: a pair can share a stem, share keys,
pass the arity test and still produce ZERO shared-key edges, because the writers
and readers never touch the same key from two different functions. That is not a
hypothetical — it is exactly what the build-time diagnostic's own top suggestion
for a C/POSIX library does, measured at 0 edges, while the pair proposed here measures
364. No heuristic separates those two; running the real import function does.

FAIL-CLOSED without an index. With no database, or under `--no-dry-run`, this
section proposes NOTHING and says so. A shared-key declaration that turns out to
be wrong mints a bipartite blob of fabricated causal edges — the #47 failure
class — so an unverified one is worse than none.

@brief Dry-run gating and evidence for `shared_key_patterns`.
@version 1
"""

from __future__ import annotations

from pathlib import Path

from ..declaration import SECTION_SHARED_KEY
from ..shared_key_edges import NamePrefixPattern, resolve_shared_key_patterns
from .context import Context
from .dryrun import measure_shared_key
from .model import Entry, Rejection, SectionProposal, SectionStatus
from .sharedkey_detect import (
    MIN_PAIR_SITES,
    MIN_SHARED_KEYS,
    READER_ARITY,
    WRITER_ARITY,
    Family,
    Pair,
    above_threshold,
    accessor_families,
    arity_consistent,
    candidate_pairs,
    covering_prefix,
    pair_families,
)

## A read-modify-write inside ONE function is not a causal edge, and clew
## emits those today. A candidate whose measured yield is mostly self-loops is
## describing intra-function code motion, not a dataflow seam.
MAX_SELF_LOOP_RATIO = 0.25

## Rejections worth printing. Beyond this the list stops being evidence and
## starts being a dump; the total is reported instead.
_MAX_REJECTIONS = 8

_SECTION_KEY = "shared_key_patterns:"

_NOT_DETECTED = (
    "NOT DETECTED: argument-keyed accessors (`pattern:` + `key_arg_index:`). "
    "clew will not propose these. Ranked by distinct constant first argument, "
    "every codebase measured top candidates are LOGGING macros, and declaring one "
    "makes every log site a writer — a complete bipartite blob of fabricated "
    "causal edges. If this repo keys state by ARGUMENT, declare it BY HAND. "
    "Tracked as clew task #37.",
)


## @brief Detect `shared_key_patterns` writer/reader pairs for a repo.
## @param ctx Shared detector inputs.
## @return The section proposal (entries, rejections, and what was checked).
## @version 3
## @req REQ-DDB-CONFIG-001
def propose_shared_key_patterns(ctx: Context) -> SectionProposal:
    """@brief Harvest families, pair them, and gate each pair on a dry run."""
    families = accessor_families(ctx.corpus.accessor_sites)
    active = _active_prefixes(ctx)
    pairs = pair_families(families)
    if not ctx.can_measure():
        return _unmeasurable(ctx, families, pairs)
    baseline = measure_shared_key(Path(str(ctx.db_path)), ctx.repo_root, None)
    accepted: list[tuple[Pair, Entry]] = []
    rejections: list[Rejection] = []
    for pair in pairs:
        outcome = _judge(ctx, pair, baseline, active)
        if isinstance(outcome, Entry):
            accepted.append((pair, outcome))
        else:
            rejections.append(outcome)
    rejections.extend(_threshold_rejections(families))
    rejections.extend(_family_rejections(families, pairs))
    return _section(ctx, families, pairs, accepted, rejections[:_MAX_REJECTIONS], active)


## @brief The name prefixes the active patterns already cover.
## @param ctx Shared detector inputs.
## @return Prefix strings from every active NamePrefixPattern.
## @version 1
## @dg_internal
def _active_prefixes(ctx: Context) -> tuple[str, ...]:
    """@brief Read the built-in plus declared name-prefix patterns."""
    declared = ctx.declared.get(SECTION_SHARED_KEY)
    writers, readers, _aliases = resolve_shared_key_patterns(
        declared if isinstance(declared, dict) else None
    )
    return tuple(
        p.prefix for p in (*writers, *readers) if isinstance(p, NamePrefixPattern) and p.prefix
    )


## @brief Accept a pair as an Entry or refuse it as a Rejection.
## @param ctx Shared detector inputs.
## @param pair The candidate writer/reader pair.
## @param baseline Dry-run measurement with no candidate applied.
## @param active Prefixes already covered by an active pattern.
## @return An Entry when the dry run passes, else a Rejection.
## @version 1
## @dg_internal
def _judge(ctx: Context, pair: Pair, baseline: dict, active: tuple[str, ...]) -> Entry | Rejection:
    """@brief Apply the coverage and dry-run gates to one pair."""
    cover = covering_prefix(pair.writer.prefix, active)
    if cover:
        return Rejection(
            _label(pair),
            f"already covered by the active name_prefix {cover!r} — declaring it "
            "again would change nothing",
            _structure_lines(pair),
        )
    section = {
        "writers": [{"name_prefix": pair.writer.prefix}],
        "readers": [{"name_prefix": pair.reader.prefix}],
    }
    measured = measure_shared_key(Path(str(ctx.db_path)), ctx.repo_root, section)
    delta = _delta(baseline, measured)
    verdict = _verdict(delta)
    if verdict:
        return Rejection(_label(pair), verdict, (*_structure_lines(pair), *_measured_lines(delta)))
    return Entry(
        yaml_lines=(),
        evidence=(*_structure_lines(pair), *_measured_lines(delta)),
        measured=delta,
    )


## @brief The measured yield a candidate adds over the baseline.
## @param baseline Measurement with no candidate applied.
## @param measured Measurement with the candidate applied.
## @return New edge count, new self-loop count, and the busiest new keys.
## @version 1
## @dg_internal
def _delta(baseline: dict, measured: dict) -> dict:
    """Diffed rather than read absolutely, because the built-in ingot defaults
    may already produce edges on this repo and attributing those to the
    candidate would overstate it.

    @brief Compute a candidate's net contribution.
    @version 1
    """
    base_keys = baseline.get("by_key", {})
    new_keys = {
        key: count - base_keys.get(key, 0)
        for key, count in measured.get("by_key", {}).items()
        if count - base_keys.get(key, 0) > 0
    }
    return {
        "edges_before": baseline.get("edges", 0),
        "edges_after": measured.get("edges", 0),
        "new_edges": measured.get("edges", 0) - baseline.get("edges", 0),
        "new_self_loops": measured.get("self_loops", 0) - baseline.get("self_loops", 0),
        "new_keys": len(new_keys),
        "top_keys": sorted(new_keys.items(), key=lambda kv: (-kv[1], kv[0]))[:4],
    }


## @brief The dry-run refusal reason for a measured pair, if any.
## @param delta The candidate's measured contribution.
## @return A refusal reason, or "" when the measurement passes.
## @version 1
## @dg_internal
def _verdict(delta: dict) -> str:
    """@brief Judge a shared-key dry run against the yield and self-loop gates."""
    new_edges = delta["new_edges"]
    if new_edges <= 0:
        return (
            f"dry run against the index yields {new_edges} net new shared_key_edges — "
            "the families share a name shape but never a key across two functions"
        )
    ratio = delta["new_self_loops"] / new_edges
    if ratio >= MAX_SELF_LOOP_RATIO:
        return (
            f"{delta['new_self_loops']} of {new_edges} measured edges ({ratio:.0%}) are "
            "SELF-LOOPS (writer == reader) — read-modify-write inside one function, "
            "not a causal seam"
        )
    return ""


## @brief The whole section's YAML for every accepted writer/reader pair.
## @param pairs The accepted pairs, in proposal order.
## @return The complete `shared_key_patterns:` block, or () when nothing passed.
## @version 1
## @dg_internal
def _section_yaml(pairs: list[Pair]) -> tuple[str, ...]:
    """SECTION-level, not per-entry, because `writers:` and `readers:` are two
    LISTS that the entries interleave. Emitting one writers/readers block per
    accepted pair produced DUPLICATE mapping keys under a single
    `shared_key_patterns:` — PyYAML resolves those silently to the LAST one, so a
    second accepted pair would have deleted the first without any error. That is
    the fabrication class this whole feature exists to avoid, arriving through the
    renderer instead of a detector.

    @brief Shape the merged shared_key_patterns block.
    @version 1
    """
    if not pairs:
        return ()
    return (
        _SECTION_KEY,
        "  writers:",
        *(f'    - name_prefix: "{pair.writer.prefix}"' for pair in pairs),
        "  readers:",
        *(f'    - name_prefix: "{pair.reader.prefix}"' for pair in pairs),
    )


## @brief Human label for a pair, used as a rejection's name.
## @param pair The pair.
## @return "writers X x readers Y".
## @version 1
## @dg_internal
def _label(pair: Pair) -> str:
    """@brief Name a writer/reader pair for reporting."""
    return f"writers {pair.writer.prefix}* x readers {pair.reader.prefix}*"


## @brief Structural evidence lines for a pair (keys, sites, arity, files).
## @param pair The pair.
## @return Evidence lines.
## @version 1
## @dg_internal
def _structure_lines(pair: Pair) -> tuple[str, ...]:
    """@brief Describe how a pair was derived from call sites."""
    files = sorted({s.rel_path for s in (*pair.writer.sites, *pair.reader.sites)})
    outside = sorted({s.rel_path.split("/")[0] for s in pair.writer.out_of_scope})
    lines = [
        f"{_label(pair)}",
        f"  {len(pair.writer.keys)} writer keys / {len(pair.writer.sites)} call sites; "
        f"{len(pair.reader.keys)} reader keys / {len(pair.reader.sites)} call sites; "
        f"{len(pair.shared_keys)} shared",
        f"  arity: every {pair.writer.prefix}* site takes 1 argument, every "
        f"{pair.reader.prefix}* takes 0 — the key is in the NAME, not an argument",
        f"  {len(files)} in-scope file(s): {', '.join(files[:6])}"
        + (" ..." if len(files) > 6 else ""),
    ]
    if outside:
        lines.append(
            f"  CONFLICT: this family also has {len(pair.writer.out_of_scope)} call site(s) "
            f"OUTSIDE the index scope (under {', '.join(outside[:4])}). Widening the "
            "index changes these numbers — re-run this command if you do."
        )
    return tuple(lines)


## @brief The measured-yield lines for a pair.
## @param delta The candidate's measured contribution.
## @return Evidence lines.
## @version 2
## @dg_internal
def _measured_lines(delta: dict) -> tuple[str, ...]:
    """@brief Render a shared-key dry run's measured delta."""
    top = ", ".join(f"{key} {count}" for key, count in delta["top_keys"])
    return (
        "  MEASURED — dry run of import_shared_key_edges_inferred on a copy of the index:",
        f"    shared_key_edges   {delta['edges_before']} -> {delta['edges_after']}   "
        f"(+{delta['new_edges']} over {delta['new_keys']} keys)",
        f"    busiest new keys: {top}" if top else "    (no per-key detail)",
        f"    {delta['new_self_loops']} of {delta['new_edges']} are SELF-LOOPS "
        "(writer == reader); clew emits these today and they are not causal edges",
    )


## @brief Rejections for writer/reader pairs that fell below the evidence floors.
## @param families Every harvested family.
## @return Rejections, one per under-evidenced pair.
## @version 2
## @dg_internal
def _threshold_rejections(families: dict[str, Family]) -> list[Rejection]:
    """These were being dropped in silence, which is the one outcome an owner
    cannot recover from: the family exists, its arity is right, and a reader who
    sees nothing about it concludes clew cannot see their data model. Measured
    on the demobot fixture, whose whole point is that exactly ONE key is both
    written and read — so its data model landed below the floor and vanished.

    @brief Explain the pairs the evidence floors removed.
    @version 2
    """
    return [
        Rejection(
            _label(pair),
            f"{len(pair.shared_keys)} key(s) are both written and read, over "
            f"{len(pair.writer.sites) + len(pair.reader.sites)} attributed call site(s) — "
            f"below the floor of {MIN_SHARED_KEYS} shared key(s) / {MIN_PAIR_SITES} site(s). "
            "Two similarly-named functions are not a data model, and one coincidence is "
            "not evidence. Widen the index, or declare it by hand if you know it is real.",
            _structure_lines(pair),
        )
        for pair in candidate_pairs(families)
        if not above_threshold(pair)
    ]


## @brief Rejections for families that never reached the pairing stage.
## @param families Every harvested family.
## @param pairs The pairs that did reach it.
## @return Rejections, largest family first.
## @version 1
## @dg_internal
def _family_rejections(families: dict[str, Family], pairs: list[Pair]) -> list[Rejection]:
    """Reported rather than dropped: a family the arity gate refuses is often
    the one an owner expected to see, and the observed arities are the answer to
    "why not mine?".

    @brief Explain the families the structural gates removed.
    @version 1
    """
    paired = {p.writer.prefix for p in pairs} | {p.reader.prefix for p in pairs}
    expect = {"set": WRITER_ARITY, "get": READER_ARITY}
    out: list[Rejection] = []
    for family in sorted(families.values(), key=lambda f: -len(f.keys)):
        if family.prefix in paired or arity_consistent(family, expect[family.verb]):
            continue
        out.append(
            Rejection(
                f"{family.prefix}*",
                f"arity varies — observed {sorted(family.arities())} at "
                f"{len(family.sites)} call sites, expected "
                f"{sorted(expect[family.verb])}. Its key is a VARIABLE, not the name.",
                (f"  {len(family.keys)} distinct name remainders",),
            )
        )
    return out


## @brief Assemble the section once every pair has a verdict.
## @param ctx Shared detector inputs.
## @param families Every harvested family.
## @param pairs Pairs that passed the structural gates.
## @param accepted Accepted (pair, entry) results, in proposal order.
## @param rejections Refused candidates.
## @param active Prefixes already covered by an active pattern.
## @return The section proposal.
## @version 2
## @dg_internal
def _section(
    ctx: Context,
    families: dict[str, Family],
    pairs: list[Pair],
    accepted: list[tuple[Pair, Entry]],
    rejections: list[Rejection],
    active: tuple[str, ...],
) -> SectionProposal:
    """@brief Build the shared_key_patterns SectionProposal."""
    in_scope_sites = sum(1 for s in ctx.corpus.accessor_sites if s.in_scope)
    entries = [entry for _pair, entry in accepted]
    return SectionProposal(
        name=SECTION_SHARED_KEY,
        status=SectionStatus.PROPOSED if entries else SectionStatus.NO_CANDIDATES,
        reason=(
            f"scanned {in_scope_sites} accessor-shaped call sites across "
            f"{ctx.corpus.files_in_scope} in-scope files -> {len(families)} families -> "
            f"{len(pairs)} arity-consistent pair(s) -> {len(entries)} with a positive dry run"
        ),
        checked={
            "accessor_call_sites_in_scope": in_scope_sites,
            "families": len(families),
            "arity_consistent_pairs": len(pairs),
            "active_name_prefixes": list(active),
            "proposed": len(entries),
        },
        entries=tuple(entries),
        rejections=tuple(rejections),
        notes=_NOT_DETECTED,
        yaml_header=_section_yaml([pair for pair, _entry in accepted]),
    )


## @brief The section when no index is available to measure against.
## @param ctx Shared detector inputs.
## @param families Every harvested family.
## @param pairs Pairs that passed the structural gates.
## @return A NOT_ANALYSED section explaining that measurement was impossible.
## @version 1
## @dg_internal
def _unmeasurable(ctx: Context, families: dict[str, Family], pairs: list[Pair]) -> SectionProposal:
    """@brief Refuse to propose shared keys without a measured dry run."""
    return SectionProposal(
        name=SECTION_SHARED_KEY,
        status=SectionStatus.NOT_ANALYSED,
        reason=(
            f"requires a built index to measure against. Found {len(families)} accessor "
            f"families and {len(pairs)} arity-consistent pair(s), but a shared-key "
            "declaration is proposed ONLY on a positive dry run — an unmeasured one can "
            "mint a bipartite blob of fabricated causal edges. Build the index (or drop "
            "--no-dry-run) and re-run."
        ),
        checked={
            "accessor_call_sites_in_scope": sum(1 for s in ctx.corpus.accessor_sites if s.in_scope),
            "families": len(families),
            "arity_consistent_pairs": len(pairs),
        },
        notes=_NOT_DETECTED,
    )
