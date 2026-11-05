There are four ways to say so, ordered by precedence, plus one piece of side input. When two disagree, the rule depends on the tier: a stated value replaces the layer below it, but facts are never removed.

**The ways to say so**

| Tier | Source | How it combines |
|---|---|---|
| 1 | CLI flag, or the `options` argument for embedding callers | Replaces the stated layer for that run |
| 2 | `.clew.yaml` at the repo root | Replaces the stated layer |
| 3 | Facts someone already wrote: Doxyfile `ALIASES`/`PREDEFINED`, generator manifests, language or platform entry points | Accumulates |
| 4 | Known-ecosystem signatures (UDM, ingot) | Accumulates |
| 5 | Name-pattern heuristics, the floor | Replaced by any stated tier |

- **`.clew.yaml`** holds one section per option, and the section name is the option name. The format is the same as the standalone manifest files, so an existing file can be moved in verbatim. The `guard:` section belongs to the doxygen gate and is ignored by the index. The old `.doxygen-guard.yaml` is no longer read.
- **Doxyfile** is not a scope decision. Its `INPUT`, `EXCLUDE*` and `FILE_PATTERNS` are replaced by the index's own scope (gh#333). Its `ALIASES` and `PREDEFINED` are still used. Only the `index_scope:` section decides what gets indexed. The `doxyfile:` section points clew at a Doxyfile in a non-standard location, and that path must exist.

**When two disagree**

- **Flag vs. declaration:** the flag wins for that run. The declaration's values for that layer are replaced, not merged. Only a tier-1 statement is recorded for replay, so a one-off flag does not persist into later builds.
- **Empty explicit list:** `[]` is a withdrawal, not a statement. It falls through to the declaration, then to the heuristics. This is how you undo a recorded flag without deleting the database.
- **Declaration vs. built-in default:** the declaration wins. A bug once inverted this for shared-key patterns, where the default's accessor class was stamped on the edge. That is now fixed and tested.
- **Declaration vs. facts:** facts always survive. Stating `entry_patterns` displaces only the name-pattern guesses, so `main` stays reachable whatever you declare.
- **Malformed or partial declarations:**
  - An unknown section name is refused by name with `DeclarationError`.
  - A file that is unreadable or not a mapping is ignored, and the build uses defaults.
  - A comments-only file states nothing, and the build uses defaults.
  - Each of these is reported in the refusal message, so the owner can see why.

**Caveat:** the index flagged `clew/tiers.py` as possibly out of date (anchor mismatch), so the line numbers I cite are from the source, not the index. I checked the stated-layer logic against the file by grep, and it matches. The source tests I relied on are `tests/test_tiers.py` and `tests/test_declaration.py`.