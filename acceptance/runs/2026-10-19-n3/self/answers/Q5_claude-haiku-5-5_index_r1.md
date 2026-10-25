There are three ways to tell clew how to index a repo, and when they disagree the rule is set by the kind of option, not by which route was used.

**The ways to say so**

1. **`.clew.yaml` at the repo root (the standing declaration).** Each top-level section holds the same content as the matching standalone manifest, so a file can be moved in verbatim. The sections include `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `dispatch`, `locks`, `preprocessor`, `kconfig`, and `entry_patterns`, among others. `guard:` is also allowed, but it belongs to the doxygen gate and the index never reads it. Unknown top-level keys are refused by name, with one exception: a key with an `x-` prefix is tolerated and ignored, so older clew versions don't refuse a newer experimental key. The old `.doxygen-guard.yaml` is no longer read at all, which is a hard break. A repo that hasn't moved its declaration gets the built-in defaults silently.
2. **CLI flags (`--shared-key-patterns`, `--thread-patterns`, `--entry-patterns`, `--scope`, etc.) for one build.** These are the explicit, per-invocation route.
3. **Arguments on the MCP `index` tool** (`scope`, `doxyfile`, `exclude`, `options`). The MCP server has no CLI flags, so these are its equivalent of tier 1. `exclude` is recorded and replayed by later builds. `scope` defaults to `from-declaration`, which reads the repo's own `index_scope:`, and `doxyfile` makes it use the Doxyfile's INPUT instead.

Two more inputs feed in without being "ways to say so": a Doxyfile (its ALIASES and PREDEFINED are facts), and the built-in defaults.

**When they disagree**

The rule is in `clew/tiers.py`, summarised as "you can correct our guesses; you cannot un-discover a fact." Each layered option resolves as `(explicit or declared or heuristic) ∪ target-fact ∪ ecosystem`.

| Tier | Source | Combines by |
|---|---|---|
| 1 | CLI flag / MCP argument | Replaces the stated layer |
| 2 | `.clew.yaml` | Replaces the stated layer |
| 3 | Target facts (Doxyfile ALIASES/PREDEFINED, generator manifests, language entry points) | Accumulates; no stated tier removes it |
| 4 | Known-ecosystem signatures | Accumulates, same as tier 3 |
| 5 | Name-pattern heuristics | Replaced by any stated tier |

So:

- **Flag vs. declaration:** the flag wins for that build. It replaces the whole declared value, not just the overlapping entries. Passing `--entry-patterns` used to drop `main`; that was fixed so `main` now survives.
- **Replacement is per section, not a deep merge.** Stating `preprocessor:` replaces the entire declared section. Stating `{}` withdraws your statement and the target's own declaration answers again.
- **Declared beats built-in defaults.** Declared shared-key patterns are matched before the defaults, because the matcher is first-match. An earlier bug let a default shadow a declared pattern silently.
- **Scope source:** the declaration beats the doxygen-guard config, which beats the Doxyfile (`scope.py`, per the comments in `shared_key_edges.py`). I didn't read `scope.py` directly, so treat that ordering as taken from comments.
- **Accumulating facts survive everything.** A flag can't remove a Doxyfile-declared alias or a `main` entry point.
- **Auditing the result:** the winning tier is recorded in `build_meta` as `<option>.tier`. Only a tier-1 statement is replayed onto a later build. The `explicit` row is only trusted when the recorded tier agrees.

If you want clew to propose a starter `.clew.yaml` from what it finds, `propose_declaration` renders a commented draft. It never overwrites an existing file without `force`.