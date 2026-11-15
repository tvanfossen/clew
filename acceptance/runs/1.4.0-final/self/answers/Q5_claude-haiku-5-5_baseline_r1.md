The short answer: clew has three ways to state a repository's configuration, plus environment and flags for things that are not properties of the repo. When two statements disagree, the more explicit one replaces the less explicit one for that option. Facts that someone already wrote down are never removed.

## Ways to say so

| Route | Tier | What it is for | Persistence |
|---|---|---|---|
| Target's own `.clew.yaml` | 2, declared | Standing conventions: `index_scope`, `preprocessor`, `entry_patterns`, `locks`, `thread_patterns`, `shared_key_patterns`, `data_model`, `dispatch`, `requirements`, `enrich`, and so on | Lives in the repo |
| `--declare FILE` on the CLI | 1, explicit | Same YAML shape, for one build. Meant for a repo you don't own and must leave byte-identical | Recorded in the index and replayed by later builds |
| `options=` on `build_index` / `index(action='refresh')` | 1, explicit | The MCP and embedding route, validated by the same `apply_options` as `--declare` | Same as above |
| `--exclude PATH…` | 1, index-shape | What the operator wants left out of the index | Recorded as `scope.operator_excludes` and replayed |
| `--scope`, `--doxyfile`, `--output`, `--repo-root`, `--rebuild`, `--verbose` | Build mechanics | Build endpoints and run properties, not declarations | Not recorded, except `--exclude` |
| `guard:` section of `.clew.yaml` | Gate config | What `clew guard` enforces. The index reads it too (`guardconfig.py`) | Lives in the repo. No flag exists |
| `CLEW_JOBS` env var | Machine-scoped | Shared-parse worker count, capped at 8 by default | Not recorded. Deliberately not a declaration, because a worker count belongs to the machine |

Tiers 3 and 4 are not user-settable. Tier 3 is facts the target already wrote, such as a Doxyfile's `PREDEFINED`/`ALIASES` or a generator manifest. Tier 4 is known-ecosystem signatures. Tier 5 is name-pattern heuristics, the floor.

## When they disagree

The combination rule is in `clew/tiers.py`: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

- **Explicit beats declared, wholesale.** If `--declare` or `options` states a value for an option, that value replaces the `.clew.yaml` value for that option. It does not merge with it. The `.clew.yaml` section is ignored for that option. Manifest options follow the same rule in `cli._declared_or_flag`: a flag wins over the declaration.
- **Facts accumulate.** Tier-3 and tier-4 values survive every stated tier. A declaration cannot remove a macro that the Doxyfile defines. Heuristics (tier 5) are the only layer a stated value displaces.
- **Empty is a withdrawal, not a statement.** `[]` or `{}` falls through to the declaration, then to the heuristics. Passing `--exclude` with no values clears a recorded exclude. An absent key inherits.
- **Recorded statements replay.** Tier-1 values are stored in `build_meta` along with the tier that won. A later refresh that omits `--exclude` still honours it. Declared values are not replayed, because the file may have changed since.
- **Scope conflicts are refused, not resolved.** A stated `index_scope` combined with a non-`from-guard` `--scope` exits 1 (gh#382). A declaration that fails validation (for example, no `roots:`) also exits 1. It does not silently fall back to the whole repo.
- **Invalid input is all-or-nothing.** `apply_options` validates the whole mapping before assigning anything. One bad or unknown key refuses the entire document.
- **Preprocessor:** the `predefined` list wins over `config_header`, according to the `preprocessor` docstring in `clew/preprocessor.py`.
- **Bad `CLEW_JOBS`** logs a warning and falls back to the automatic count rather than failing the build.

This is from reading the source of the repo at `acceptance/runs/1.4.0-final/self/repo`, which is clew itself. I did not run a build to confirm the precedence behaviour.