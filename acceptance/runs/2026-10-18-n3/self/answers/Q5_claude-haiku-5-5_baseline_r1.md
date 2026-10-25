clew has several ways for a repo to override its defaults, and they combine by a fixed rule. Tier 1 beats tier 2 for a given option, and nothing beats tiers 3 and 4. I worked this out from the source, not by running a build.

**Ways to say so**

| Tier | Source | Scope |
|---|---|---|
| 1, explicit | CLI flags such as `--declare FILE`, `--entry-patterns`, `--test-paths`, `--scope`, `--exclude` | One build. `--declare` (and `--exclude`) are recorded in the index and replayed by later builds. |
| 1, explicit | MCP `index(action="refresh")` and `build_index(options=...)` | Same mapping as `--declare`, so agents without a shell can state the same things. |
| 2, declared | `.clew.yaml` at the repo root | Standing declaration, re-read on every build. Sections include `index_scope`, `shared_key_patterns`, `thread_patterns`, `mqtt_dispatch`, `entry_patterns`, `test_paths`, `preprocessor`, `kconfig`, `requirements`, `enrich` and others. |
| 3, target-fact | Facts the repo already wrote: Doxyfile ALIASES/PREDEFINED, generator manifests, entry points such as `pyproject` scripts | Accumulates. The Doxyfile's INPUT is replaced rather than honoured. |
| 4, ecosystem | Built-in signatures for known ecosystems (UDM, ingot) | Accumulates. |
| 5, heuristic | Built-in name-pattern guesses | The floor; displaceable. |

Two notes on this table. The `guard:` section of `.clew.yaml` configures the gate, and the index reads it with the gate's schema. Keys prefixed `x-` are tolerated and ignored, with a warning. The environment variable `CLEW_JOBS` is deliberately not a config route.

**When two disagree**

The rule is `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. Tier 1 and tier 2 never merge. Whichever wins replaces the whole stated layer for that option, and only tiers 3 and 4 accumulate underneath. So `--entry-patterns` displaces a declared `entry_patterns` list entirely, but `main` and `app_main` survive because they are tier-3 facts.

Other details:
- Stated document sections replace the declared section wholesale. There is no deep merge.
- An empty value withdraws the statement: `[]` or `{}` falls through to the next tier, and an absent flag inherits.
- Tier 2 is re-read from the file on each build, so edits take effect. Tier 1 is replayed from the record.
- `test_paths` displaces the built-in guesses, while `entry_patterns` keeps its facts. So the same tier-1 statement has a different effect depending on the option.
- Some combinations are refused outright instead of resolved. A stated `index_scope` with a non-default `--scope` exits with an error. An invalid `--declare` document is rejected before anything is applied. An `--extra-input` root that `FILE_PATTERNS` excludes entirely is also refused.
- Each displacement is logged at INFO, and the winning tier is stamped into `build_meta`. Nothing warns loudly when a declaration is overridden.

Relevant source: `clew/tiers.py` (the rule), `clew/cli.py` (`_apply_declared_document`, `_with_stated_sections`, `_entry_patterns`), `clew/buildoptions.py` (`apply_options`), `clew/declaration.py` (`KNOWN_SECTIONS`), and `clew/scope.py` (the `index_scope` tier).

A PostToolUse hook message in one of my Bash results suggested using a `dossier`/`search` index tool. I didn't use it, since I'm working from the source directly.