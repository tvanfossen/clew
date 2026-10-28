Clew has four ways to say how a repository should be indexed, and they resolve in a fixed order. The governing rule is in `clew/tiers.py`, and the index describes it as "you can correct our guesses; you cannot un-discover a fact."

**The ways to say so**

| Tier | Source | How it is set | Combines by |
|---|---|---|---|
| 1 | Explicit | CLI flag, or the structured `options` argument for an embedding caller or MCP (`clew/buildoptions.py`) | Replaces the stated layer |
| 2 | Declared | `.clew.yaml` at the repo root, one section per option (`clew/declaration.py`) | Replaces the stated layer |
| 3 | Target facts | Things the repo already wrote: a Doxyfile's ALIASES/PREDEFINED, a generator manifest, a language or platform entry point | Accumulates |
| 4 | Ecosystem | A known-ecosystem signature, such as UDM or ingot | Accumulates |
| 5 | Heuristic | Name-pattern matching, the provisional floor | Replaced by any stated tier |

- **Options argument** (tier 1) is the one an MCP caller can reach. Before it existed, MCP got only built-in defaults, because the flags were CLI-only. Its keys are the `.clew.yaml` section names, and the index says all 14 declaration sections are statable this way.
- **`.clew.yaml`** also carries a `guard:` section for the doxygen gate. The old `.doxygen-guard.yaml` is a hard break and is no longer read.
- **Per-run mechanics** such as `--scope`, `--index-cache` and `--rebuild` are deliberately not declarations.

**When two disagree**

- **Flag vs. declaration:** the flag wins outright for that option. It replaces the declared list rather than merging with it. The index describes the file as the repo's standing statement and the flag as a deliberate one-off override.
- **Declaration vs. heuristic:** the declaration replaces the guesses. Facts and ecosystem entries (tiers 3 and 4) are never displaced by any stated tier, so `main` survives a user-stated entry-pattern list.
- **Empty values are withdrawals, not statements.** An empty explicit list `[]` falls through to the declaration, and then to the guesses. An empty `{}` for a manifest option states nothing and falls back to the declaration.
- **Pattern matching:** a declared shared-key pattern beats a built-in default. This was once inverted, and a test now pins it.
- **Catalog and Kconfig discovery:** CLI flag, then declaration, then convention.
- **Invalid options:** the whole options mapping is validated before anything is applied, so one bad entry refuses the entire mapping instead of building a half-applied policy.
- **Recording:** each build stamps the winning tier into `build_meta`. Only a tier-1 statement is replayed on the next refresh. A record where the tier and the statement disagree resolves to "nothing to replay".

One caveat: the index flagged a line-anchor mismatch on `resolve_layered` and `_stated_layer`, so the source I read for those may be a little out of step with the index build. The rule they implement matches the module documentation and the tests.