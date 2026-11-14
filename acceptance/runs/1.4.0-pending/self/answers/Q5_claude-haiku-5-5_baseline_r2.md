Clew has four ways for a repository to change how it is indexed, plus a few smaller ones. When they disagree, the tier table decides, and most conflicts resolve in the more explicit source's favour. The one exception is a contradiction that cannot be resolved, which makes the build exit with an error rather than pick a winner.

**The ways to say so**

| Route | Who uses it | Notes |
|---|---|---|
| `.clew.yaml` at the repo root (tier 2) | The repo's standing declaration | One section per option (`preprocessor:`, `index_scope:`, `shared_key_patterns:`, `event_tags:`, `guard:`, and so on). `clew/declaration.py` lists the known sections. |
| `--declare FILE` (tier 1) | An operator or script, for one build | Same YAML shape as `.clew.yaml`. Relative paths resolve against `--repo-root`. |
| `options=` argument to `build_index` / `index(action='refresh')` (tier 1) | An MCP or embedding caller with no shell | Same vocabulary as the declaration file. Manifest options accept either a path or an inline mapping. Validated before anything is applied, and stricter than the file route. |
| Named CLI flags (tier 1) | Operator on the command line | Collapsed to a six-argument build surface. `--exclude` is recorded into the index and replayed. `--rebuild` and `--verbose` are per-run only. |
| `toolchain.toml` / `suppress.toml` | Shared across tools (knots, moldy, aurora-lint) | `[ignore].paths` and `tool = "*"` suppressions exclude from the index. `[clew.ignore]` and `tool = "clew"` affect only the gate. |
| `CLEW_JOBS` env var | The machine, not the repo | Worker count only. Deliberately not a declaration. |

There are also auto-discovered inputs that need no statement: the Doxyfile is found by name in the root, `docs/` or `doc/`. Its `INPUT` is replaced but its `ALIASES` and `PREDEFINED` are kept. Its location can be stated with the `doxyfile` option when discovery misses it.

**When two disagree**

The rule is in `clew/tiers.py`: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

- **Tier 1 beats tier 2, and replaces it.** `_declared_or_flag` prefers a flag or `--declare` value over the section. A stated tier-1 list is not merged with the declared list. The declared one is ignored for that option.
- **An empty value is a withdrawal, not a statement.** `[]` or `{}` falls through to the declaration, and then to the built-in floor. This is how an operator undoes a recorded flag without deleting the database.
- **Tiers 3 and 4 always survive.** These are target facts (a Doxyfile's aliases, a generator manifest) and ecosystem signatures. No stated tier can remove them. For example, `--entry-patterns` cannot drop `main`.
- **Tier 5 is the floor.** Name-pattern guesses are the only layer a stated value replaces.
- **Two stated sections are additive, not competing.** `shared_key_patterns` and the dispatch key-wrapper section both contribute prefixes. A flag for one does not drop the other.
- **`index_scope` against `--scope` is refused.** A stated `index_scope` is only read on the `from-guard` path. Pairing it with any other scope exits with status 1 rather than building a different boundary and reporting success. A declared `index_scope` that is invalid (no `roots:`, or no declared root exists) is also refused rather than silently widened to the whole repo.
- **Malformed `toolchain.toml` does not fail the build.** It is reported as a problem and its exclusions are ignored.
- **Bad `CLEW_JOBS` values fall back** to a default, with a log line, because the setting only affects speed.

Each build records which tier won for each option in `build_meta`, so a later reader can see whether a value came from a flag, the declaration, or the default.

I read the code and the design comments in `buildoptions.py`, `tiers.py`, `cli.py`, `scope.py`, `preprocessor.py`, `shared_key_edges.py` and `toolchain.py`. I did not run a build to confirm the behaviour end to end. I also did not verify the default `--scope` value in the current CLI, since the flag does not appear in `cli.py` as I searched it.