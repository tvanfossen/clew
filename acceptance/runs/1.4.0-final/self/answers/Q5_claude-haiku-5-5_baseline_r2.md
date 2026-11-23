There are four ways to say so, ordered by who can see the statement and whether it is durable. When they disagree, the stated (tier 1) statement replaces the declared one as a whole section, and "excludes" are the one thing that unions.

**The ways to say so**

| Route | Tier | What it covers | Durability |
|---|---|---|---|
| `.clew.yaml` at the repo root | 2, declared | Every convention: `index_scope` (`roots`/`excludes`), `sub_indexes`, `preprocessor`, `kconfig`, `entry_patterns`, `locks`, `thread_patterns`, `dispatch`, `requirements`, and so on. The `guard:` section belongs to the gate. | Committed with the code. Read fresh on every build. |
| `--declare FILE` (or the `options` argument of `build_index` / MCP `index(action="refresh")`) | 1, explicit | The same YAML shape, for a repo you don't own and must leave byte-identical. | Recorded in `build_meta` and replayed by later builds of that database. |
| `--exclude PATH…` | 1, explicit | Index-shape only: leave these paths out. It is deliberately not a route for conventions. | Recorded as `scope.operator_excludes` and replayed. `--exclude` with no values withdraws it; omitting the flag inherits it. |
| `toolchain.toml` `[ignore].paths` (and `suppress.toml`) | Excluded from the index on every build | Shared ignores for all tools. | Re-read every build, not replayed, so removing a glob takes effect at once. |

Two things to know about the defaults. The Doxyfile is no longer a scope fallback (gh#333). With no declaration, the scope is the whole repository minus git-ignored paths and dot/cache directories. The environment variables I found (`JOBS`, state home, project dir, refresh interval, `CLAUDE_CONFIG_DIR`) control runtime behaviour, not what gets indexed.

**When they disagree**

- **Same option in `.clew.yaml` and `--declare`:** the stated section replaces the declared one. It is not a deep merge, because a merged `preprocessor` would describe a configuration nobody chose. Stating `{}` withdraws the statement and the target's own file answers again.
- **`index_scope` specifically:** a stated `index_scope` replaces the declared one wholesale, so a `--declare` that carries only `excludes` discards the file's `roots`. The rejection rules are these:
  - An `index_scope` with `excludes` but no `roots` is rejected. The CLI exits 1, and internal callers fall back to the whole repository with a warning.
  - A stated `index_scope` combined with a non-default `--scope` is refused with exit 1 (gh#382), because `index_scope` is only read on the `from-guard` path.
- **Sub-index declarations:** a stated `sub_indexes` block replaces the declared one. Unknown sub-index names are refused rather than ignored, and only `excludes` is accepted.
- **Tiers 3 and 4 (target facts and ecosystem signatures):** these accumulate and survive any stated tier. Tier 5 (heuristics) is the only one a stated value displaces. So `entry_patterns` stated in config replaces the built-in name-shape guesses, but language entry points still apply.
- **`--exclude` against `index_scope.excludes`:** these union. The scope's excludes and the operator's excludes are both appended to the same exclusion list, and the toolchain globs join it too.
- **Refresh with `--exclude`:** a stated list replaces the recorded one. It is not merged with it.

Every resolved option stamps `options.<name>.tier` into `build_meta`, so you can check which layer won for a given database. Note that the `--scope` flag is not in the argparse surface I could find, so I did not verify its CLI wiring beyond the `_apply_scope` logic.