There are three ways to tell clew about a repository, plus a fourth route that only sets the index scope. When they disagree, the outcome depends on the option. Layered options follow one five-tier rule. Scope and some refusals follow their own rules.

**Ways to say so**

| Route | Where | Tier / role |
|---|---|---|
| Built-in defaults | clew itself | Tier 4 (ecosystem signatures) and tier 5 (name-pattern guesses) |
| Target's own facts | Doxyfile `ALIASES`/`PREDEFINED`, generator manifests, language/platform entry points | Tier 3, facts that accumulate |
| Declaration | `<repo>/.clew.yaml`, or `--declare` for a repo you don't own | Tier 2 |
| CLI flag | `--entry-patterns`, `--scope`, `--extra-input`, `--requirements`, `--dispatch`, etc. | Tier 1 |
| MCP `index(options=…)` | The `options` argument, keyed by `.clew.yaml` section names | Same as a declaration, since MCP passes no flags |

The Doxyfile's `INPUT` is no longer a scope tier (gh#333). Scope now comes from the declaration's `index_scope:`, or else the whole repository. `--scope doxyfile` survives only as an explicit opt-out.

`.clew.yaml` accepts the sections in `KNOWN_SECTIONS` (`clew/declaration.py:238`): `index_scope`, `shared_key`, `threads`, `mqtt`, `data_model`, `requirements`, `enrich`, `locks`, `entry_patterns`, `test_paths`, `vendored`, `dispatch`, `preprocessor`, `kconfig`, `doxyfile`, `event_tags`, `sub_indexes`. The `guard:` section belongs to the gate, not the index. An unknown section is refused by name (`load_declaration` raises `DeclarationError`). A section with the experimental prefix is tolerated and ignored. This repo's own `.clew.yaml` declares only `guard:` plus a `requirements` file path, so its index runs on defaults.

**When they disagree**

1. **Layered options (`resolve_layered`, `clew/tiers.py:307`)**
   - Resolved set = (tier 1 or tier 2 or tier 5) ∪ tier 3 ∪ tier 4.
   - A CLI flag or declaration *replaces* only the guesses. Facts and ecosystem entries always survive.
   - Example: declaring `%trampoline%` as an entry pattern yields `main, app_main, %trampoline%`. The guesses are dropped and `main` is kept.
   - An empty explicit list (`[]`) is a withdrawal. It falls through to the declaration, then to the guesses.
   - The winning tier is stamped into `build_meta` and reported by status. Flag beats declaration beats guess.
   - In short: "you can correct our guesses; you cannot un-discover a fact."

2. **`--scope` versus a stated `index_scope`** (`_apply_scope`, `clew/cli.py:758`)
   - Passing a non-default `--scope` while `index_scope:` is stated is refused with exit 1, not silently resolved. The stated boundary would otherwise be replaced without warning.

3. **A rejected `index_scope`** (missing roots)
   - Internal callers (`derive_scope`) log a WARNING and fall back to the whole repository.
   - CLI and MCP refresh call `declared_scope_rejection` and refuse the build instead. An operator-facing caller cannot quietly get the widest scope.

4. **Malformed declarations**
   - Unparseable or comment-only files degrade to defaults, and the status line says so (`describe_declaration`).
   - An unknown section name is a hard refusal, not a degradation.

Two caveats. I read the `index(options=…)` behaviour from the tool schema and the code comments, not from a test. The README's `--declare` description is also paraphrased, not verified against the parser.