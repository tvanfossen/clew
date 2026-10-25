The repo has a five-tier precedence model, and a conflict is resolved by tier rank, not by merging.

**The ways to say so, by tier** (from `clew/tiers.py` and related docs):

| Tier | Source | Role |
|---|---|---|
| 1 | Explicit, per build: CLI flags, or the structured `options` argument for embedding callers | Operator states a value for this build only |
| 2 | Standing declaration: `.clew.yaml` in the target repo | The repo's own statement, persists across builds |
| 3 | Facts: language, platform, or the target's own manifests | Accumulates; nothing stated can remove it |
| 4 | Known-ecosystem signatures (e.g. `DEFAULT_KEY_ALIAS_PREFIXES`) | Accumulates; a declaration can add but not remove |
| 5 | Name-pattern guesses (e.g. `ENTRY_PATTERN_HEURISTICS`) | Floor; any stated tier displaces it |

Other inputs that touch scope:
- **Doxyfile** (`scope='doxyfile'` on `index`): its `INPUT` is replaced by a declared `index_scope`, but it is still read for `ALIASES` and `PREDEFINED`. `INPUT`, `EXCLUDE`/`EXCLUDE_PATTERNS` and `FILE_PATTERNS` each decide scope independently, so changing only one does nothing useful.
- **`index` tool's `exclude`**: recorded and replayed by later builds. Pass an empty list to withdraw it.
- **`index` tool's `options`**: keyed by `.clew.yaml` section names; unknown keys are refused by name. I did not confirm from the index which tier it maps to.
- **`propose_declaration`**: writes a starter `.clew.yaml` entirely as comments. It changes nothing until a human uncomments it.

**When two disagree**

- **Within a layered option, one stated tier wins and the rest are discarded.** The rule is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. An explicit flag replaces the declaration for that option, and the declaration is not merged in. The test `test_tier_one_beats_tier_two` pins this, and `test_explicit_flag_wins_over_the_declaration` says a flag is a deliberate one-off override.
- **Facts and ecosystem defaults never lose.** Tiers 3 and 4 always union into the result, so a declaration cannot remove a fact.
- **An empty explicit list is a withdrawal, not a statement.** `[]` falls through to the declaration, then to the guesses. That lets an operator undo a recorded flag without deleting the database.
- **Key alias prefixes are the exception.** The declared `path` and `extra` sections are additive, not competing. A flag-supplied manifest only changes the recorded tier label to `explicit`; it does not drop the declared prefixes.
- **Scope precedence:** a declaration beats the whole-repo default (`C_INTEGRATION.md`).
- **Visibility:** `_options_meta` records which tier chose each setting in the index, so a surprising result can be traced to the winning tier. The index does not record that a losing tier existed.

Caveats: `dossier` would not resolve file paths, so the tier table comes from the `tiers.py` symbols and docstrings rather than the file-level comment. I did not read `.clew.yaml` section names or the `index` tool's `options` mapping directly.