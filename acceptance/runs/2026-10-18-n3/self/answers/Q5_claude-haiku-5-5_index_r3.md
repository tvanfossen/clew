Clew takes configuration from four places, layered by a five-tier rule. When two sources disagree, the higher stated tier wins, and the lower tiers either fill in or get dropped depending on the tier.

**The ways to say so**

| Route | Tier | Notes |
|---|---|---|
| CLI flag (e.g. `--shared-key-patterns`, `--scope`) | 1 (explicit) | One build only. An embedding caller can pass the same thing as a structured `options` argument; the MCP `index` tool exposes that as `options`. |
| `.clew.yaml` at the repo root | 2 (declared) | The repo's standing statement. Sections are checked against a fixed list (`KNOWN_SECTIONS`); an unknown section is refused by name. |
| Facts already in the repo (language, platform, manifests) | 3 (facts) | Always present. Nothing stated can remove them. |
| Known-ecosystem signatures | 4 (ecosystem) | Accumulates underneath. Nothing stated can remove it. |
| Name-pattern guesses | 5 (heuristic) | The floor. The only layer a stated tier is allowed to displace. |

Two other settings sit outside the tiers:
- **Scope** (`index_scope:` in `.clew.yaml`) is the only declaration that decides what gets indexed. If none is stated, the whole repo is indexed. The Doxyfile is no longer a fallback (gh#333).
- **Gate config** lives in a `guard:` section of the same `.clew.yaml`. The index ignores it. The old `.doxygen-guard.yaml` is not read at all.

**When they disagree**

- **Facts and ecosystem signatures always accumulate.** They are unioned with whatever is stated.
- **Among the stated tiers (1, 2, 5), the highest one present wins outright.** The winning tier's values replace the lower tiers' values, rather than merging with them. So an explicit flag beats the declaration, and a declaration beats the guesses. `test_tier_one_beats_tier_two` pins this.
- **An empty explicit list is a withdrawal, not a statement.** `[]` falls through to the declaration and then the guesses, so an operator can undo a recorded flag without deleting the database.
- **Scope conflicts are refused, not resolved.** A stated `index_scope` paired with a non-default `--scope` makes the build exit 1, rather than silently building a different boundary.
- **A rejected declaration fails the build.** The scope path refuses it instead of quietly falling back to the whole repo.
- **A malformed `.clew.yaml` is ignored with a message.** It degrades to built-in defaults, and the refusal text says so (`describe_declaration`).

The index confirmed the tier mechanics through `resolve_layered`, `STATED_TIERS`, `ACCUMULATING_TIERS`, `derive_scope`, and `_apply_scope`. I did not read the full body of `clew/tiers.py` itself, since the file was not directly queryable as a dossier subject.