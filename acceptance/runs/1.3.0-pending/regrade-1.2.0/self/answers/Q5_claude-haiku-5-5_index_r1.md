The main way to say so is a `.clew.yaml` at the repo root, which is tier 2. Each top-level section takes the same shape as its standalone manifest, so an existing file can be moved in unchanged. Other ways to state a value, from highest to lowest precedence:

| Tier | Source | Combines by |
|---|---|---|
| 1 | Explicit: a CLI flag, or the `options` argument for an embedding caller | Replaces the stated layer |
| 2 | Declared: `.clew.yaml` | Replaces the stated layer |
| 3 | Target facts: a Doxyfile's `ALIASES`/`PREDEFINED`, a generator manifest, a language or platform entry point | Accumulates |
| 4 | Ecosystem signatures (UDM, ingot) | Accumulates |
| 5 | Heuristics: built-in name-pattern guesses | Replaced by any stated tier |

Tier 1 is reachable from MCP through `options`. Before that change, the built-in defaults were the whole policy for MCP callers. `clew propose` (`propose_declaration`) drafts a `.clew.yaml` as comments, so nothing changes until someone uncomments it.

**Where it bites:**

- **Scope is special.** Only `index_scope:` in `.clew.yaml` decides what gets indexed. A Doxyfile's `INPUT` no longer does (gh#333), because it is a documentation target, not a reasoning boundary. The Doxyfile still supplies `ALIASES` and `PREDEFINED`, and its `INPUT` is replaced.
- **Flag vs. declaration:** the flag wins outright. The file is the standing statement and the flag is a one-off override.
- **Declaration vs. heuristic:** the declaration displaces the built-in guesses entirely. `main` survives as an entry point regardless, because the tiers 3–4 accumulation rule keeps it.
- **Tiers 3 and 4 never get displaced.** A stated tier cannot remove a fact someone else already wrote.
- **Rejected scope:** `derive_scope` logs a WARNING and falls back to the whole repo. The CLI and MCP refresh paths call `declared_scope_rejection` first and refuse the build rather than silently widening it.
- **Bad `.clew.yaml`:** unparseable YAML or a non-mapping is logged and treated as absent. An unknown section name is refused by name, because a misspelled section would otherwise run on defaults while reporting the declaration was honoured. Sections prefixed `x-` are tolerated and ignored, so an older clew does not hard-fail on a newer file.
- **Gate-only file:** a `.clew.yaml` that configures only `guard:` declares nothing to the index.
- **Bad tier-1 options:** `apply_options` validates everything before assigning anything, so one bad entry leaves the namespace untouched.
- **Provenance:** the winning tier is recorded in `build_meta`, survives refreshes, and is reported by `status`.

Caveat: the index flags `load_declaration_located` as anchor-mismatched, meaning the file changed since the last build, so its body and version (shown as 2, dossier metadata says 4) may not match the current source. The precedence rules above come from the tier and test docs, which I did not re-check against the code line by line.