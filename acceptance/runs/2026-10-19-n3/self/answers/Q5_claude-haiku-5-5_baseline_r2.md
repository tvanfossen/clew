There are three ways a repository can change clew's indexing, plus the built-in defaults underneath them. When two of them disagree, the higher tier replaces the lower one for that option, and some conflicts are refused outright.

**The routes, from lowest to highest precedence**

| Route | Tier | How it's stated |
|---|---|---|
| Built-in defaults | 5 (heuristic) | Name-pattern guesses, whole-repo scope, Doxyfile discovered by convention |
| The target's own files | 3 and 4 (target-fact, ecosystem) | Doxyfile ALIASES/PREDEFINED, generator manifests, known-ecosystem signatures |
| The repo's `.clew.yaml` | 2 (declared) | Sections at the repo root, such as `index_scope:`, `shared_key_patterns:`, `thread_patterns:`, `preprocessor:`, `entry_patterns:`, `kconfig:` |
| A stated declaration | 1 (explicit) | `--declare FILE` on the CLI, the `options` argument of `build_index`, or MCP `index(action="refresh")` |

Two more things sit alongside these. The CLI keeps only `--output`, `--repo-root`, `--exclude`, `--rebuild` and `--verbose`. `--exclude` is recorded into the index and replayed by later builds, and it is deliberately not a route for declared conventions. The `guard:` section of `.clew.yaml` belongs to the gate, not the indexer. The indexer reads only its `@req` pattern and its requirements catalog from there.

**When two disagree**

- **Tier 1 vs tier 2:** a stated section replaces the declared section for that option, as a whole section rather than key by key. This is in `clew/tiers.py` and `clew/buildoptions.py`. An empty stated document (`{}`) withdraws the stated value and falls back to the file. An absent one inherits.
- **Tier 3 and 4 never lose to a stated tier:** these accumulate. A stated `entry_patterns` replaces the built-in name guesses, but language entry points such as `main` survive.
- **Tier 5 always loses:** any stated tier displaces the heuristics.
- **`index_scope` specifically:** a stated block replaces the declared one (`clew/scope.py`, `_declared_index_scope`). A CLI build refuses instead of guessing when the scope is contradictory. Examples are an `excludes:` with no `roots:`, a root that doesn't exist, or an unknown key. `derive_scope` itself quietly falls back to whole-repo, but the CLI checks for rejection first and exits with an error.
- **Unknown section names** in `.clew.yaml` cause a refusal. Unparseable YAML, or a file that isn't a mapping, degrades to defaults with a warning. Sections prefixed `x-` are tolerated and ignored, with a warning.
- **Provenance:** tier-1 statements are hashed and recorded in `build_meta` so later builds can replay them. Tier-2 values are re-read from the file on every build.

**Not verified:** I did not confirm how a CLI `--exclude` combines with `index_scope.excludes` when both are present. Check `clew/cli.py` if that matters to you.