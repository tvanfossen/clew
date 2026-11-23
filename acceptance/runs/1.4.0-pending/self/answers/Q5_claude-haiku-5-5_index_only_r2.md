**Ways to say so, from weakest to strongest:**

| Tier | Source | Combines with others by |
|---|---|---|
| 5 | Built-in heuristics (name-pattern guesses, the floor) | Replaced by any stated tier |
| 4 | Known-ecosystem signatures (UDM, ingot) | Accumulates |
| 3 | Facts a target already wrote: a Doxyfile's `ALIASES`/`PREDEFINED`, generator manifests, language entry points | Accumulates |
| 2 | The repo's `.clew.yaml`, one section per convention (`index_scope`, `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `data_model`, `preprocessor`, `kconfig`, `doxyfile`, `sub_indexes`, and others) | Replaces the layer below it |
| 1 | Explicit statement at call time: a CLI flag, or the `options` argument / MCP parameters (`scope`, `exclude`, `doxyfile`, `target`, `force`) | Replaces the stated layer |

Every declaration section can also be given as a call-time option, so an MCP caller that cannot reach a shell still has tier 1. The one exception is the `predefined` alias.

Scope has its own two-tier rule. Only a declared `index_scope:` decides what is indexed. Otherwise the whole repo is indexed, minus what git ignores. A Doxyfile's `INPUT` no longer narrows scope; the Doxyfile is still used for its aliases and predefines.

**When two disagree:**

- **Flag vs. `.clew.yaml`:** the flag wins for that run. The declared section is replaced, not merged. An empty flag or mapping counts as a withdrawal, so the declaration applies.
- **Stated tiers (1 and 2) vs. guesses (5):** the stated value displaces the guess. Built-in entry points such as `main` survive any stated override.
- **Facts (3 and 4):** these accumulate and survive any stated tier. A declaration cannot remove a fact a Doxyfile already states.
- **A rejected `index_scope`:** the internal pipeline logs a warning and falls back to whole-repo scope. The CLI and MCP refresh check first and refuse the build instead. One known failure: an excludes-only `.clew.yaml` silently widened scope and caused a 900-second doxygen timeout.
- **Malformed `.clew.yaml`:** logged at WARNING and treated as absent, so the build runs on defaults.
- **Unknown section name:** a hard refusal. A typo would otherwise run on defaults while reporting the declaration was honoured.
- **Gate config:** the `guard:` section is the gate's, not the index's, and is stripped before index parsing.

I worked from the index's docstrings and test names, not the function bodies beyond what the dossiers returned, so the exact precedence in edge cases is as the code documents it rather than something I traced line by line.