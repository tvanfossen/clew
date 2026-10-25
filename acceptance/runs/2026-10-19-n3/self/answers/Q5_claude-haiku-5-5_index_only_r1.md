Clew has five ways to take a repository's indexing choices, ranked in tiers. Stated choices (tiers 1, 2 and 5) compete and the highest one wins whole. Facts (tiers 3 and 4) are added on top and no stated choice can remove them. I answered from the index alone. The rules come from the docstrings and test names, not from reading the code, and I didn't run `propose_declaration` because it needed a permission I wasn't given.

**The ways to say so**

| Tier | Name | Where it comes from | Behaviour |
|---|---|---|---|
| 1 | Explicit | CLI flag, or the structured `options` argument for embedding callers and MCP | Applies to one build. Stated `index_scope` is recorded and replayed on later plain rebuilds. |
| 2 | Declared | `.clew.yaml` at the repo root | The standing statement. Sections include `index_scope`, `dispatch`, `preprocessor`, `kconfig`, and the requirements catalog path. |
| 3 | Target fact | Language, platform, the target's own manifests | Accumulates. |
| 4 | Ecosystem | Known-ecosystem signatures | Accumulates. |
| 5 | Heuristic | Name-pattern guesses | The floor. Any stated tier displaces it. |

Other things that affect this:
- `guard:` inside `.clew.yaml` belongs to the doxygen-guard gate. The index drops it.
- Keys prefixed with the experimental prefix are tolerated and ignored, so an older clew doesn't refuse the file.
- Old `.doxygen-guard.yaml` is no longer read. Repos that haven't moved their declaration get the built-in defaults.
- `propose_declaration` drafts a commented `.clew.yaml` for a repo. It doesn't apply anything.

**When two of them disagree**

- **Flag vs declaration, same key:** the flag wins outright. Tests cover `preprocessor`, and the index treats the file as the standing statement and the flag as a deliberate one-off override.
- **Declaration vs guessed default:** the declaration replaces the guess. For some options, such as entry patterns, a stated tier displaces only the tier-5 guesses and tier-3 language entry points still accumulate underneath.
- **Facts vs anything:** `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. Stated tiers can correct guesses but can't un-discover a fact.
- **Index scope:** `declared > guard > Doxyfile INPUT > whole repo`. A declared scope is the only tier that yields index roots. The gate's `files:` pattern never supplies roots. An empty `index_scope` falls through to the whole repo.
- **Which tier won** is stamped into the build metadata and reported by `status`, so the winner is checkable after the fact.

**Errors in the declaration itself**

- An unknown top-level section name refuses the build and names the offender. Silently falling back would report a declaration as honoured when it wasn't.
- Unparseable YAML is logged at WARNING and treated as absent.
- An unknown key inside `index_scope` refuses by name.
- A rejected declaration refuses the build rather than silently widening the index.