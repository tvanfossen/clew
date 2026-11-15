The index describes a five-tier precedence model. Stated values override defaults, and a stated value replaces the default layer rather than merging into it. Facts that something else already wrote are never displaced.

**The ways to say so**

| Tier | Source | How it combines |
|---|---|---|
| 1 | Explicit: CLI flags (`--shared-key-patterns`, `--thread-patterns`, `--mqtt-dispatch`, `--doxyfile`, `--scope`, `--entry-patterns`…), or the single `options` argument for embedding callers (`clew/buildoptions.py`) | Replaces the stated layer |
| 2 | Declared: the repo's `.clew.yaml` | Replaces the stated layer |
| 3 | Target facts: a Doxyfile's ALIASES/PREDEFINED, a generator manifest, a language or platform entry point | Accumulates |
| 4 | Ecosystem signatures (e.g. UDM, ingot) | Accumulates |
| 5 | Heuristic name-pattern guesses, the floor | Replaced by any stated tier |

Two details matter here:

- **Index scope** is separate. It is the `index_scope:` section of `.clew.yaml`, or else the whole repository minus what git ignores. A Doxyfile's `INPUT` no longer decides scope (gh#333). The Doxyfile is still used for ALIASES and PREDEFINED, but its `INPUT` is replaced.
- **The gate's config** lives in the `guard:` section of `.clew.yaml`. `clew guard` reads it, not the index, so it does not change what gets indexed.

**When two of them disagree**

- **Flag vs. `.clew.yaml`:** the flag wins for that build. The declaration is the standing statement and the flag is a deliberate one-off. The declaration file is not edited.
- **Empty values are withdrawals, not statements.** An empty list or `{}` falls through to the declaration, then to the defaults. That is how an operator undoes a recorded flag without deleting the database.
- **Stated tiers never remove facts.** A declaration or flag can correct a guess, but it cannot un-discover a Doxyfile- or manifest-derived fact. The model's own summary: "you can correct our guesses; you cannot un-discover a fact."
- **Tier 3 and tier 4 disagreements are inert.** Both accumulate and survive every stated tier, so only the label changes.
- **Tier-1 statements are replayed.** A flag is recorded in `build_meta` and reapplied on the next build that states nothing. A declaration is not replayed, because it is read from the file each time. The index reports which options were operator-stated, so two operators on the same commit can end up with different indexes, but visibly.

Caveat: the body of `resolve_layered` came back flagged `anchor_mismatch`, so its line numbers may be stale. The semantics above come from its docstring and the matching tests, which agree with each other.