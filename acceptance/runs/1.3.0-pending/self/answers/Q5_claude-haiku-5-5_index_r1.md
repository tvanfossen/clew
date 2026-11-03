The main way is a `.clew.yaml` at the repository root. Other inputs can also set conventions, and they are ranked by a five-tier precedence rule.

**The ways to say so**

| Tier | Source | How it combines |
|---|---|---|
| 1 | CLI flag, e.g. `--shared-key-patterns`, `--thread-patterns`, `--mqtt-dispatch`, `--data-model`, `--entry-patterns` | Replaces the stated layer |
| 2 | `.clew.yaml` in the repo root | Replaces the stated layer |
| 3 | Facts someone else wrote: a Doxyfile's ALIASES/PREDEFINED, a generator manifest, a language or platform entry point | Accumulates |
| 4 | Known-ecosystem signatures (UDM, ingot) | Accumulates |
| 5 | Name-pattern heuristics, explicitly provisional | Replaces the stated layer |

The main channel is `.clew.yaml`. Its sections hold the same content as the standalone manifests, so a repo can move an existing file's contents in unchanged. The sections include `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `dispatch`, `entry_patterns`, `locks`, `requirements`, `sub_indexes`, `vendored`, `preprocessor`, `kconfig`, `data_model`, `index_scope` and `test_paths`. Because the file is read from the repo root, both the CLI and the MCP server pick it up. The MCP server passes no flags, so the file is its only route to declared conventions.

Two other points about the file:
- `index_scope:` is the one tier that decides what gets indexed. It takes `roots:` and `excludes:`. Without it, the scope is the whole repository minus what git ignores. The Doxyfile's `INPUT` no longer sets scope, so a repo that ships one is not narrowed by it.
- The `guard:` section belongs to the doxygen gate, not the index. The index accepts it and ignores it.

**What happens when they disagree**

1. **Flag versus declaration, same option:** the flag wins outright. The declaration's value for that option is not merged in. The flag is meant as a deliberate one-off override.
2. **Declaration versus a Doxyfile or ecosystem fact:** these accumulate, so both survive. Facts from tiers 3 and 4 are kept under any stated tier.
3. **Declaration versus heuristic guesses:** the declaration replaces the guesses. This is how you correct them. Facts cannot be replaced this way, so a declaration cannot un-discover a fact.
4. **Declared `index_scope` versus no scope:** the declared roots are used. If the declaration is unusable, the build falls back to the whole repository and logs the reason. Nothing is silently guessed.
5. **Declared key-alias prefixes:** these replace the built-in defaults rather than extend them.

The resolved tier for each setting is recorded in the index metadata, so you can see which source chose a value.

**Errors**

- An unknown top-level section is refused by name. Only keys prefixed `x-` are tolerated and ignored, so newer experimental keys do not break older clew builds.
- A malformed `.clew.yaml` is ignored with a message that names the file, and built-in defaults apply.
- An unknown key inside `index_scope:` rejects that scope and falls back to the whole repository, with a warning.
- The old `.doxygen-guard.yaml` is not read. A repo still carrying one gets the defaults.

I did not run `propose_declaration`. Its permission was denied in this session, so the proposed-file route is unverified here. The rules above come from the index's documentation and dossiers for `clew/tiers.py`, `clew/declaration.py` and `clew/scope.py`. I did not run the tests, so they reflect the code's stated design rather than a verified run.