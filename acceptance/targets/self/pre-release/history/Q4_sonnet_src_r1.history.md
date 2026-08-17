# Q4 — src — sonnet — run 1

> Machine-generated narrative of one benchmark cell. The authoritative record is the
> sibling `.transcript.jsonl`; this document exists so a reviewer can follow what the
> agent did without parsing JSON. If the two disagree, the JSONL is correct.

### 1. `Bash`
- **asked:** command=find ~/ddb-targets/self -maxdepth 2 -type d | sort
- **got:** ~/ddb-targets/self ~/ddb-targets/self/acceptance ~/ddb-targets/self/acceptance/bench ~/ddb-targets/self/acceptance/method ~/ddb-targets/self/acceptance/targets ~/ddb-targets/self/.claude-plugin ~/ddb-targets/self/docs ~/…

### 2. `Grep`
- **asked:** pattern=precedence|override|declared|build_argv|CLI flag|effective_|resolve_setting, path=~/ddb-targets/self/doxyguard_db
- **got:** Found 65 files ~/ddb-targets/self/doxyguard_db/vocabulary.py ~/ddb-targets/self/doxyguard_db/signature.py ~/ddb-targets/self/doxyguard_db/threads.py ~/ddb-targets/self/doxyguard_db/tiers.py ~/ddb-targets/self/doxyguard_d…

### 3. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/buildoptions.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""TIER 1, REACHABLE — one structured `options` argument for an embedding caller. 3	 4	`.doxyguard-db.yaml` is TIER 2 and has been reachable since a declaration became 5	discoverable fr…

### 4. `Grep`
- **asked:** pattern=tier 1|tier 2|tier 3|tier 4|tier 5|TIER 1|TIER 2|TIER 3|TIER 4|TIER 5, path=~/ddb-targets/self/doxyguard_db
- **got:** Found 11 files ~/ddb-targets/self/doxyguard_db/tiers.py ~/ddb-targets/self/doxyguard_db/scope.py ~/ddb-targets/self/doxyguard_db/shared_key_edges.py ~/ddb-targets/self/doxyguard_db/reachability.py ~/ddb-targets/self/doxy…

**Reasoning.** tiers.py looks like the definitive module for this.

### 5. `Read`
- **asked:** file_path=~/ddb-targets/self/doxyguard_db/tiers.py
- **got:** 1	# SPDX-License-Identifier: MIT 2	"""Five-tier precedence for every layered build option — ONE combination rule. 3	 4	`resolved = (tier1 or tier2 or tier5) union tier3 union tier4` 5	 6	In one line: **you can correct ou…

**Reasoning.** I found the exact mechanism. This is a complete, precise answer.

## Answer

This program resolves every layered setting (things like `entry_patterns`, `shared_key_patterns`, spawn/lock/dispatch manifests, etc.) through one shared combination rule, implemented once in `doxyguard_db/tiers.py:1-568` rather than per-option.

### The five tiers

`doxyguard_db/tiers.py:8-14` (docstring table) and `tiers.py:57-68` define:

| tier | name | source | combines by |
|---|---|---|---|
| 1 | `explicit` | a CLI flag stated for this one build | REPLACES |
| 2 | `declared` | the target repo's own `.doxyguard-

---

## Final answer as submitted

I found the exact mechanism. This is a complete, precise answer.

## Answer

This program resolves every layered setting (things like `entry_patterns`, `shared_key_patterns`, spawn/lock/dispatch manifests, etc.) through one shared combination rule, implemented once in `doxyguard_db/tiers.py:1-568` rather than per-option.

### The five tiers

`doxyguard_db/tiers.py:8-14` (docstring table) and `tiers.py:57-68` define:

| tier | name | source | combines by |
|---|---|---|---|
| 1 | `explicit` | a CLI flag stated for this one build | REPLACES |
| 2 | `declared` | the target repo's own `.doxyguard-db.yaml` (or its `x-doxyguard-db` passthrough) | REPLACES |
| 3 | `target-fact` | facts already written elsewhere (a Doxyfile's ALIASES/PREDEFINED, a generator manifest, a language/platform entry point) | ACCUMULATES |
| 4 | `ecosystem` | a known-ecosystem signature (e.g. UDM/ingot) | ACCUMULATES |
| 5 | `heuristic` | built-in name-pattern guessing — the floor | REPLACES |

### The rule

`doxyguard_db/tiers.py:4`:

```
resolved = (tier1 or tier2 or tier5) union tier3 union tier4
```

In prose (`tiers.py:6`): **"you can correct our guesses; you cannot un-discover a fact."**

Mechanically, per `resolve_layered`/`_stated_layer` (`tiers.py:300-358`):
- Tiers 1, 2, and 5 are mutually exclusive competitors for one "replaceable" slot: tier 1 wins if stated (truthy), else tier 2 if declared (truthy), else tier 5 (the built-in heuristic) is used unconditionally as the floor. This is a strict override chain, not a merge — whichever of the three wins supplies the *entire* replaceable layer, and the losers contribute nothing.
- Tiers 3 and 4 always accumulate underneath, in that order, ahead of whichever stated layer won (`tiers.py:314-316,332`): `values = ordered_unique((*facts, *ecosystem, *stated))`. No CLI flag or declaration can suppress a tier-3/4 fact — they are guaranteed to survive.
- `tiers.py:24-29` explicitly notes tiers 3 and 4 are behaviorally identical (both accumulate, both are irremovable); the only load-bearing split is "3-or-4 (fact, permanent) vs 5 (guess, discardable)".
- For manifest/document-shaped options (`shared_key_patterns`, `thread_patterns`, `locks`, `dispatch`, `mqtt_dispatch`), the analogous `resolve_document` (`tiers.py:258-288`) makes the same three-way choice — explicit, else declared, else the `heuristic` floor label (meaning "nothing stated, so only tiers 3/4's accumulation applies") — since a whole document can't be "unioned" the way a list can.
- The winning tier is recorded in `build_meta` under an `options.<name>.tier` key (`LayeredResolution.as_meta`/`DocumentResolution.as_meta`, `tiers.py:149-165,230-249`) so a later read (`recorded_explicit`/`recorded_document`, `tiers.py:432-465,474-498`) only replays a tier-1 statement, cross-checked against the recorded tier — never a stale or withdrawn one.

To predict the outcome for any setting not yet examined: find whether it's a plain list-valued option (uses `resolve_layered`) or a whole-document option (uses `resolve_document`), then apply: explicit flag wins if truthy → else declared value if truthy → else built-in heuristic guess; and separately, whatever tier-3 (target-fact) and tier-4 (ecosystem) values exist for it are always included regardless of what wins tier 1/2/5.

### What an empty value on the command line means

An empty/falsy explicit CLI value (e.g. `[]` for a list option, or `{}` for a manifest document) is **not treated as "nothing stated" but is also not silently equivalent to omitting the flag** — it is a **withdrawal**, explicitly distinguished from `None` (flag absent):

- `tiers.py:293,321-324`: *"An empty `explicit` IS A WITHDRAWAL, not a statement. `[]` is falsy, so it falls through to the declaration and then to the guesses, which is what lets an operator undo a recorded flag without deleting the database. `None` means the flag was absent."*
- Same logic for documents at `tiers.py:267-271`: *"AN EMPTY DOCUMENT IS A WITHDRAWAL... `{}` is falsy, so it falls through to the declaration and then to the floor, and no statement is recorded."*
- `_stated_layer` (`tiers.py:345-358`) implements this: `if explicit: return TIER_EXPLICIT, ...` — an empty sequence/mapping is falsy in Python, so it falls through to the `declared`-then-`heuristic` check, exactly as if the flag had never been passed at that call, **except** that no tier-1 record is written, so a previously-recorded tier-1 statement stops being replayed on the next build too.

So: passing an empty value on the CLI actively clears/undoes a prior explicit statement (letting tier 2 or tier 5 take over again), rather than being ignored as a no-op.

## Gaps

- I traced the *general* resolution rule and its precise semantics from `tiers.py`. I did not exhaustively verify that every one of the ~14 settings in `buildoptions.py` (`SECTION_DOCUMENT_OPTIONS`, `MANIFEST_OPTIONS`, etc.) actually calls `resolve_layered`/`resolve_document` — I inspected `buildoptions.py:1-697` which documents and validates the *options surface* (tier 1/tier 2 merge point) but did not grep every call site (e.g. in `scope.py`, `shared_key_edges.py`, `declaration.py`) to confirm each individually routes through `tiers.py`'s primitives rather than some option having a bespoke resolver. The docstring in `tiers.py:16-22` implies this unification was a deliberate fix for prior inconsistency, suggesting it is now universal, but I did not check every consumer file to be certain no option still has a bespoke rule.
