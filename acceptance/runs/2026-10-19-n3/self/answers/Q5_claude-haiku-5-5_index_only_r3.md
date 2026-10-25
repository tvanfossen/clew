The index describes five precedence tiers, one combination rule, and an explicit rule for when a stated value beats a declared one. I answered from the index alone, so I could not check the full CLI flag list or the scope-option details against source.

**The ways to say so, highest precedence first** (`clew/tiers.py`, `TIER_ORDER`):

| Tier | Source | Effect |
|---|---|---|
| 1 `explicit` | A CLI flag for one build, or the same value passed inline as a mapping by an embedding caller (gh#360, REQ-DDB-CONFIG-008) | Replaces the lower stated layers for that build |
| 2 `declared` | The target's `.clew.yaml` | Replaces tier 5 |
| 3 `target-fact` | Facts already in the repo, such as language, platform, or its own manifests | Accumulates; no stated tier removes it |
| 4 `ecosystem` | Built-in known-ecosystem signatures | Accumulates; a declaration can add to it but not remove it |
| 5 `heuristic` | Name-pattern guesses | Only the floor; any stated tier displaces it |

Two other things to know:
- `.clew.yaml` is read from the repo root. An unknown section name makes the load refuse with an error, rather than silently falling back to defaults. A file that only has `guard:` declares nothing to the index.
- `clew propose` and the `propose_declaration` tool only write a commented draft `.clew.yaml`. They change nothing until someone uncomments it.

**When two disagree**

- **Tier 1 vs tier 2 (flag vs declaration):** the flag wins, because it is a deliberate one-off override of the repo's standing statement. The declaration is still read but not used for that build.
- **Stated vs guess:** a declared or flagged value displaces the heuristic guesses entirely.
- **Facts and ecosystem defaults:** these never lose to a stated value. A declaration adds to them and cannot subtract.
- **An empty flag is a withdrawal, not a statement.** `[]` falls through to the declaration and then to the guesses. This lets an operator undo a recorded flag without deleting the database.
- **Per-section, not whole-file:** some options take a union across sections. For example, shared-key alias prefixes from the accessor manifest and the dispatch manifest's `shared_key_wrappers` add together, and passing a flag for one of them does not drop the other. The flag only changes the label recorded for the winning tier.
- **Scope is special:** only a declaration yields index roots. A rejected declaration refuses the build instead of silently widening the scope.

**Recording the outcome:** the index stores which tier won for each layered option. `db_status` reports it, and an index built before build 30 has no record. That lets a surprising result be traced back to a flag, the declaration, or a guess.