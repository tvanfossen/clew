There are three layers, plus a set of individual flags. When two disagree, the higher-precedence one wins outright for that option; it does not merge with the lower one.

**Ways to say so**

| Route | Tier | What it covers | Persistence |
|---|---|---|---|
| `<repo>/.clew.yaml` | 2 (declared) | `index_scope: {roots, excludes}` plus sections such as `preprocessor`, `requirements`, `kconfig`, `event_tags`, `entry_patterns`, `locks`, `dispatch`. | Read on every build. This is the only file clew looks for. |
| `--declare FILE`, or the `options` argument of `build_index` / MCP `index(action="refresh")` | 1 (explicit) | The same YAML mapping, stated for one build. Meant for repos you don't own and must leave byte-identical. | Recorded in the database and replayed by later builds. Only tier-1 statements replay. |
| CLI flags | 1 | `--exclude`, `--doxyfile`, `--predefined`, and similar. `--scope` and `--rebuild` are per-run mechanics, not declarations. | `--exclude` is recorded and replayed. |
| Defaults | 5 (heuristic) | Whole repo, minus what git ignores, minus dot-dirs, `__pycache__` and `node_modules`. Doxyfile is found by name in the root, `docs/` or `doc/`. | Nothing to persist. |

The `guard:` section of `.clew.yaml` belongs to the gate. The index reads only its requirement-id pattern and catalog path from it, and drops the rest.

**When two disagree**

- **Tier 1 beats tier 2 for the same option.** A stated value replaces the file's value for that option. The file is not merged in. The stated layer is what gets recorded.
- **`index_scope` is replaced whole, never merged.** `roots` replaces the scope. `excludes` on its own does nothing, and a stated `index_scope` also overrides the file's.
- **Stated `index_scope` with a non-`from-guard` `--scope` is refused.** The build exits with an error. Silently ignoring the statement would produce a different boundary and report success.
- **Tiers 3 and 4 accumulate and survive any stated value.** Doxyfile aliases and predefined macros, and ecosystem signatures, are not discarded by a declaration. Only tier 5 name-pattern guesses are replaced.
- **Doxyfile `INPUT` never sets scope.** An `index_scope` replaces it. The Doxyfile is still used for aliases and predefined macros.
- **Bad declarations degrade differently by kind:**
  - Malformed YAML: warning, treated as absent, defaults apply.
  - Unknown key inside `index_scope` (e.g. `exclude:`): rejected, warning logged, falls back to whole repo.
  - Nonexistent root paths: dropped. If none remain, the section is rejected and falls back to whole repo.
  - Unknown top-level section name: the build refuses outright.
- **`--exclude` has three states.** Absent inherits the previous build's recorded excludes, `[]` withdraws them, and a non-empty list replaces them.

I did not trace how `--exclude` combines with `index_scope.excludes` in the same build. Check that before relying on it.

Two PostToolUse hook messages in this session suggested querying clew's own index tools instead of reading files. They are not part of your request, so I ignored them and answered from the source.