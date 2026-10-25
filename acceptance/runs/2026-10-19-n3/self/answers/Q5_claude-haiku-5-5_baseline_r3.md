Clew reads indexing overrides from five places, ordered by precedence. Each option resolves independently, so a stated value for one option doesn't change the others.

| Tier | Source | How it's given | Effect |
|---|---|---|---|
| 1, explicit | `--declare FILE` on the CLI, or the `options` argument on `build_index` / `index(action='refresh')` over MCP | Same YAML shape as `.clew.yaml` | Replaces the lower tiers for the option it names. Recorded in `build_meta` and replayed by later builds of that database. Intended for repos you don't own (`clew/cli.py:484`, `clew/buildoptions.py`). |
| 1, explicit (mechanics) | `--exclude`, `--output`, `--repo-root`, `--rebuild` | Flags | `--exclude` is recorded as `scope.operator_excludes` and replayed. The others are per-run and not stored (`clew/cli.py:500`). |
| 2, declared | `<repo>/.clew.yaml` | Sections such as `index_scope`, `shared_key_patterns`, `thread_patterns`, `dispatch`, `locks`, `preprocessor`, `kconfig`, `doxyfile` | Replaces the heuristic and ecosystem guesses. Re-read from the file on every build, so it isn't frozen (`clew/declaration.py:277`). |
| 3, target-fact | Files the target already has, such as a Doxyfile's `ALIASES`/`PREDEFINED` or its manifests | Nothing to configure | Accumulates. No stated tier can remove it (`clew/tiers.py:1-30`). |
| 4, ecosystem | Known-ecosystem signatures such as UDM or ingot | Nothing to configure | Accumulates, same as tier 3. |
| 5, heuristic | Name-pattern guesses | Nothing to configure | The floor. Any stated tier displaces it. |

Things that aren't configurable: git-ignored files are always excluded, and nested git trees are indexed and tagged rather than excluded (`clew/scope.py:1-36`).

**When two sources disagree**

- **Tier 1 vs tier 2 on the same option:** the stated value replaces the declared one. It does not merge. A `--declare` `index_scope` makes `.clew.yaml`'s `index_scope` unread for that build. Replacement is deliberate: it lets an operator withdraw a declared exclude they disagree with (`clew/scope.py`, `declared_sub_index_excludes`).
- **`--exclude` vs `index_scope` roots:** `--exclude` is an index-shape argument that is recorded and replayed. It is not a route for declared conventions. Those go through `--declare` or `.clew.yaml` so the CLI and MCP can't diverge (`clew/cli.py:500-512`).
- **Tier 3 or 4 vs anything stated:** no conflict. The fact is kept, and the stated value is added on top. If you want to remove a fact a Doxyfile supplies, you have to edit the Doxyfile.
- **Invalid declaration:** `apply_options` validates the whole `options` mapping before assigning anything, so one bad entry means nothing is applied and the build errors. This is meant to avoid a half-applied policy that still reports success (`clew/buildoptions.py:695`).
- **Unusable `index_scope` in `.clew.yaml`:** `derive_scope` logs a WARNING and falls back to the whole repository, recording the rejection reason. It does not fail the build (`clew/scope.py`, `derive_scope`).
- **Unknown top-level section in `.clew.yaml`:** refused with `DeclarationError`. Keys prefixed `x-` are tolerated and ignored with a warning.
- **Stale replays:** a tier-1 value from `--declare` or `--exclude` is replayed onto later builds. A tier-2 value is re-derived from the file, so editing `.clew.yaml` changes the next build but a `--declare` value persists until you restate it.

The `guard:` section of `.clew.yaml` configures the doc-validation gate, not the index. The index ignores it (`clew/declaration.py`, `SECTION_GUARD`). This repo's own `.clew.yaml` sets only `guard:`, so it builds on defaults.

I read the code but did not run a build to confirm these paths, so treat the precedence claims as read-from-source.