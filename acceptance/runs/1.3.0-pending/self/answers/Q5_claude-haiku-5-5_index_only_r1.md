Clew has five layers of configuration. The first two are things a repository or caller states; the other three are facts or guesses clew derives itself. The rule for conflicts is that a stated value replaces the layer beneath it, while facts and ecosystem signatures are never discarded.

**The ways to say so**

| Tier | Source | Combines by |
|---|---|---|
| 1 explicit | CLI flag, or the `options` argument for an embedding caller (MCP `index`, `--declare`) | Replaces the stated layer |
| 2 declared | `.clew.yaml` at the repo root | Replaces the stated layer |
| 3 target-fact | Facts the repo already wrote: a Doxyfile's `ALIASES`/`PREDEFINED`/`INPUT`, a generator manifest, a language or platform entry point | Accumulates |
| 4 ecosystem | Known-ecosystem signatures | Accumulates |
| 5 heuristic | Name-pattern guesses, the explicitly provisional floor | Replaces the stated layer |

The `.clew.yaml` sections I could confirm are `index_scope`, `preprocessor`, `kconfig`, `shared_key_patterns`, `locks`, `entry_patterns`, `dispatch`, `requirements`, and `doxyfile`. The `guard:` section belongs to the doxygen gate, and the index ignores it. Keys prefixed `experimental_` are tolerated and ignored. The old `.doxygen-guard.yaml` is no longer read at all.

**When two disagree**

- **Flag vs. declaration:** the flag wins and replaces the declared value outright, with no merge. The test `test_an_explicit_flag_replaces_the_declaration` shows a declared macro being dropped when a flag states its own list.
- **Declared vs. built-in default:** the declaration replaces the default. In `test_a_declaration_displaces_the_default_patterns`, a declared `t/*` stops `tests/*` from applying, so a repo can narrow the rule as well as widen it.
- **Facts vs. stated tiers:** tiers 3 and 4 survive any stated value. The module's summary is "you can correct our guesses; you cannot un-discover a fact."
- **Index scope:** declaration beats the Doxyfile's `INPUT`, which beats whole-repo. An unusable declaration refuses the build instead of quietly widening it. The excludes-only case is the reason: it had silently fallen back to the whole repo and caused a 900-second doxygen timeout.
- **Empty values:** an empty stated value is a withdrawal, so it falls back to the declaration. An empty `shared_key_patterns: {}` is one example.

**How bad input is handled**

- An unknown top-level section refuses the build, with an error naming the allowed sections. The reason is that the build would otherwise use defaults while reporting the declaration was honoured.
- Malformed YAML is logged at WARNING and treated as absent.
- Inline `options` are validated all-or-nothing, so one bad entry leaves the build untouched.

I answered from the index alone, so I did not enumerate every CLI flag or confirm that every scope path routes through `clew/tiers.py`. The scope and kconfig precedence I cited is in the tests and docs, not in a single resolver I read.