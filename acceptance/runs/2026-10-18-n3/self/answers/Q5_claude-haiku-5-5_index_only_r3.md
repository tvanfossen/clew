There are three ways to tell clew how to index a repo, and they are resolved by one five-tier rule.

**The ways to say so**

| Tier | Source | Role |
|---|---|---|
| 1 | Explicit statement at call time: a CLI flag, or the `options` argument on the MCP `index` tool | Operator's one-off override |
| 2 | The repo's checked-in `.clew.yaml` (the "declaration") | The repo's standing statement |
| 3 | Facts someone else already wrote, such as a Doxyfile | Always present, always accumulates |
| 4 | Ecosystem signatures for a known language or platform | Always accumulates |
| 5 | Built-in name-pattern guesses | The layer any stated tier displaces |

`.clew.yaml` is the main route. Its top-level sections are checked against a fixed list (`ACCEPTED_SECTIONS`). An unknown section is refused by name, so a misspelling fails loudly. The `guard:` section belongs to the doxygen gate, and the index ignores it. Keys with an `x-` prefix are tolerated and ignored, so an older clew doesn't refuse a newer file. The old `.doxygen-guard.yaml` is no longer read at all. A malformed file degrades to built-in defaults with a message. A comments-only file is reported as stating nothing.

**When two disagree**

The rule, as stated in `clew/tiers.py` and `resolve_layered`, is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

- **Flag vs. declaration:** the flag wins outright. The declaration's values for that option are dropped, not merged in. The test `test_explicit_flag_wins_over_the_declaration` pins this.
- **Stated tier vs. guesses:** a stated value (tier 1 or 2) displaces only the tier-5 guesses. Facts and ecosystem values (tiers 3–4) always stay.
- **Empty flag:** `[]` is a withdrawal, not a statement. It falls through to the declaration, and then to the guesses. This lets an operator undo a recorded flag without deleting the database.
- **Provenance:** the winning tier is recorded in build metadata. Only a tier-1 statement is stored for replay, so a declaration or guess is never replayed as if someone had typed it.

**Caveats**

- Scope resolution follows a separate order: scope's declaration beats the guard, which beats the Doxyfile.
- Shared-key matching was once inverted, with a built-in default beating a declared pattern. That was fixed, and a declaration now beats a default.
- I did not call `propose_declaration`, since it was not permitted. Its output would show what the defaults would find, so it is the next check if you want to see what a repo gets without a file.