Clew reads indexing preferences from four places. When they conflict, the answer depends on whether the option replaces or accumulates. I read the source and did not run a build, so the behaviour below is from the code and its docstrings.

**The ways to say so**

| Tier | Where | What it can do |
|---|---|---|
| 1. Explicit, per build | CLI flags (`--scope`, `--extra-input`, `--extra-exclude`, `--doxyfile`, `--shared-key-patterns`, …) or the `options` argument for embedding callers and MCP | Overrides the repo's declaration for one build only. Not persisted. |
| 2. Declared | `.clew.yaml` at the repo root (`index_scope:`, `sub_indexes:`, `shared_key_patterns:`, `thread_patterns:`, `mqtt_dispatch:`, `entry_patterns:`, `test_paths:`, `vendored:`, `predefined:`, `event_tags:`, `kconfig:`, `doxyfile:`, `requirements:`, `enrich:`, `data_model:`, `locks:`, plus a `guard:` section for the gate) | The repo's standing statement. `clew/declaration.py`, `clew/buildoptions.py`. |
| Shared ignores | `toolchain.toml` `[ignore].paths` and `suppress.toml` entries with `tool = "*"` (or `tool = "clew"` for gate-only) | Exclusions only. `clew/toolchain.py`, applied in `cli.py:_apply_toolchain_exclusions`. |
| Target facts and heuristics | Doxyfile ALIASES/PREDEFINED, `pyproject.toml` entry points (accumulate); built-in name patterns (floor) | Not configuration you write, but they feed the same resolution. |

Two things narrow the picture. A Doxyfile's `INPUT` no longer decides scope (gh#333), so only its ALIASES, PREDEFINED and filters carry over. And `--extra-input` is the one flag that appends rather than replaces.

**When two disagree**

The rule is the five-tier one in `clew/tiers.py`: "you can correct our guesses; you cannot un-discover a fact."

- **Replaceable options** (`entry_patterns`, shared-key and thread patterns, and similar): explicit replaces declared, and declared replaces heuristic. The lists are not merged. Target facts and ecosystem entries accumulate under every stated tier, so no flag or declaration removes them.
- **Scope** (`derive_scope` in `clew/scope.py`): a stated `index_scope` beats a declared one, which beats the whole repository. A declared `index_scope` replaces the whole scope and is not unioned with it. Roots outside the repo are refused, and roots that don't exist are ignored with a warning. A present but unusable `index_scope` is rejected loudly and falls back to whole-repo, with the reason logged. Stating an `index_scope` alongside a `--scope` other than `from-guard` is refused outright.
- **Exclusions** (`toolchain.toml`, `suppress.toml`, `--extra-exclude`): these union into the excludes list and cannot be removed by a declared include. I did not trace whether a declared `index_scope` root inside an ignored path is re-admitted, so treat that as unverified.
- **Failure severity differs.** A malformed `.clew.yaml` section is refused by name (fail closed). A broken `toolchain.toml` or `suppress.toml` is logged and its exclusions ignored, so a build still runs.
- **Traceability:** the winning tier for each option is recorded in `build_meta` (`options.<name>.tier`), and the scope reason is logged, so you can see which tier won after the fact.