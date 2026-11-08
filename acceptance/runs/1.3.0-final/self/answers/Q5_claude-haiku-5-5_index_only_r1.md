**Ways to say so, from strongest to weakest.** `clew/tiers.py` defines five tiers. Stated values (tiers 1 and 2) are the ones that can override clew's guesses.

| Tier | Source | Combines by |
|---|---|---|
| 1 explicit | CLI flags, or the structured `options` argument for embedding callers (`clew/buildoptions.py`) | Replaces the stated layer |
| 2 declared | `.clew.yaml` at the repo root, found from `--repo-root` | Replaces the stated layer |
| 3 target-fact | Facts the repo already wrote, such as a Doxyfile's ALIASES/PREDEFINED or a generator manifest | Accumulates |
| 4 ecosystem | Known-ecosystem signatures (UDM, ingot) | Accumulates |
| 5 heuristic | Name-pattern matching, the provisional floor | Replaces the stated layer |

- **Tier 1 (CLI or `options`).** Per-run flags. Only tier-1 values are recorded for replay. The `options` argument matches the `.clew.yaml` vocabulary, and every declaration section can be stated this way.
- **Tier 2 (`.clew.yaml`).** The repo's standing declaration. Sections include `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `doxyfile`, `kconfig`, `preprocessor`, `requirements`, `sub_indexes` and `dispatch`. The `guard:` section configures the doc gate, and the index never reads it. A standalone manifest file uses the same parser as the section.
- **Tiers 3 and 4.** Not declared by the repo; they are read from what the repo already has or from its ecosystem.
- **Tier 5.** Heuristics, which any stated tier displaces.
- **Helper.** `propose_declaration` drafts a commented `.clew.yaml`. It does not overwrite an existing file without `force`.

**When two disagree**

- **Flag vs. declaration (1 vs. 2).** The flag wins for that run. Declared values are the default, and the flag is a one-off override.
- **Stated vs. guesses (1 or 2 vs. 5).** The stated value replaces the guesses entirely.
- **Facts and ecosystem (3 and 4).** These accumulate and survive every stated tier, so a `--entry-patterns` flag cannot drop `main`. Tiers 3 and 4 combine identically, so an argument over which one a value belongs to changes the label only.
- **Empty values.** An empty explicit list `[]` is a withdrawal, not a statement. It falls through to the declaration and then to the guesses. `None` means the flag was absent. An empty `options` mapping changes nothing and is not an error. An empty per-manifest mapping such as `shared_key_patterns: {}` falls back to the declaration.
- **Bad input.** `apply_options` validates the whole mapping before assigning anything, so one bad entry refuses the whole thing rather than half-applying it.
- **Missing declared path.** A `doxyfile` that is stated but missing is refused. It does not fall back to indexing the whole repo.
- **Visibility.** The winning tier and the resolved values are stored in `build_meta`, so you can see which tier won.

**Caveats.** The `resolve_layered` record is flagged `anchor_mismatch`, so its line numbers may be stale, though its docstring matched the rule above. I did not read the body of `_stated_layer` or the full `buildoptions.py` docstring, which was truncated. The precedence statements above come from docstrings and tests, not from reading the code paths.