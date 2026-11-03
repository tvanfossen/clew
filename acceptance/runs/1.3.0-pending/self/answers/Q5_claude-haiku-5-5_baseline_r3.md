**Short answer:** there are four ways to state a build option, ranked by precedence. Within one option, a higher tier replaces a lower one. Two kinds of values are the exception: exclusions accumulate, and built-in facts are never removed.

## The ways to say it

| Tier | Where it comes from | Reaches | Notes |
|---|---|---|---|
| 1 | CLI flags (`--exclude`, `--entry-patterns`, `--declare FILE`) and the `options` argument of `build_index` / MCP `index(action='refresh')` | One build | `--declare` loads a YAML mapping and applies it at tier 1 (`cli.py` `_apply_declared_document`). Inline `options` are applied after it, so inline wins. |
| 2 | The target's own `<repo>/.clew.yaml` | Every build, CLI and MCP alike | This is the standing declaration. The same section names are used at every tier. |
| 3 | Facts the target already wrote: its Doxyfile's ALIASES/PREDEFINED, manifests, entry points | Accumulates | Never removed by any stated tier. |
| 5 | Built-in name-pattern guesses (for example, `main`) | Replaced by any stated tier | The floor. |

Tier 4 (ecosystem signatures) also accumulates, like tier 3. `tiers.py` defines the rule as `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`.

The keys in `.clew.yaml` are the same ones the flags and `options` use: `index_scope`, `preprocessor`, `requirements`, `thread_patterns`, `shared_key_patterns`, `locks`, `dispatch`, `mqtt_dispatch`, `data_model`, `kconfig`, `event_tags`, `entry_patterns`, `enrich`, and others. Two things are separate from this:
- The `guard:` section is gate configuration. The index reads it only for the requirement-tag pattern and the catalog column mapping.
- `toolchain.toml` and `suppress.toml` at the repo root are a shared exclusion list. The index honours their all-tools entries.

## When two disagree

- **CLI or `options` vs `.clew.yaml`, same option:** the stated value wins. The merge is per section, not deep. Stating `preprocessor:` replaces the whole declared block. Stating `{}` withdraws the statement, and the `.clew.yaml` value applies again.
- **`--declare` vs inline `options`:** inline wins, because it is applied last.
- **Exclusions:** these do not replace. `--exclude` paths are added to the toolchain-config excludes. The operator's list is recorded and replayed on the next build. An absent flag inherits the recorded list, an empty `--exclude []` clears it, and a non-empty list replaces it. Toolchain globs are re-read every build and are not replayed.
- **`index_scope` vs `--scope`:** a stated `index_scope` combined with any non-default `--scope` is refused with exit 1. Silently ignoring the stated boundary would be worse.
- **A rejected `index_scope`** (for example, `excludes:` without `roots:`, or an unknown key) is refused with exit 1. It is not silently widened to the whole repository.
- **Doxyfile vs `index_scope`:** a Doxyfile's `INPUT` is no longer a scope tier. The repo's Doxyfile is still used for ALIASES and PREDEFINED, but its `INPUT` is replaced by the declared or whole-repo scope.
- **A stated tier 1 or 2 vs a built-in guess:** the guess is replaced. A built-in fact is kept.

Relevant code: `clew/tiers.py` (the rule), `clew/cli.py` (`_declared_or_flag`, `_apply_scope`, `_operator_excludes`, `_apply_toolchain_exclusions`), `clew/scope.py` (`_declared_index_scope`), `clew/buildoptions.py`, and `README.md` around line 280–330.

I did not run the test suite or a build to confirm this; the answer is from reading the code and its docstrings.