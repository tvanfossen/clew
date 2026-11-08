The ways to say so, and how conflicts resolve, depend on what kind of setting it is. Clew has no single config file or precedence chain. Each option family has its own rule, and they are mostly consistent with one principle: a stated value can correct a guess, but cannot remove a fact.

## The ways to say it

| Channel | Who uses it | Reaches | Persists? |
|---|---|---|---|
| **`.clew.yaml`** at the repo root | Repo owner, checked in | All declared conventions (`entry_patterns`, `preprocessor`, `kconfig`, `locks`, `dispatch`, `index_scope`, `guard:`, and so on) | Yes, in the repo |
| **`--declare FILE`** / `options` argument on `build_index` / MCP | Operator or agent who can't write to the target | Same sections as `.clew.yaml`, applied as "tier 1" | Recorded in the index and replayed by later builds |
| **Individual flags**: `--output`, `--repo-root`, `--exclude`, `--rebuild`, `--verbose` | CLI user | Index shape (`--exclude`), build endpoints, and run mechanics only | `--exclude` is recorded and replayed; the others are per-run |
| **`toolchain.toml` / `suppress.toml`** at the root | Repo owner shared across tools | `[ignore].paths` and `tool = "*"` suppressions as exclusions; `tool = "clew"` entries only affect the gate | Read fresh every build, not replayed |
| **Environment variables** | Machine owner | `CLEW_JOBS` (worker count, capped at 8), `CLEW_STATE_HOME`, `CLAUDE_CONFIG_DIR` | Not in the index; a property of the host, not the repo |

Per the code comments, `--declare` and `.clew.yaml` are two routes to the same vocabulary, so the choice is about reachability, not capability.

## What happens when they disagree

**Layered options (entry patterns, predefined, and the like).** `tiers.py` defines five tiers and resolves them as `(tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`:

- **Tier 1** (flag or `--declare`/`options`) and **tier 2** (`.clew.yaml`) **replace** the tier-5 name-pattern guesses. Only one of them wins, with explicit beating declared.
- **Tiers 3 and 4** (facts from target manifests, and known-ecosystem signatures) **accumulate**. No stated value removes them. For example, `main` and `app_main` survive any `--entry-patterns` you pass.
- Each resolution records which tier won, so the index can report it.

**Path options (`requirements`, `doxyfile`, and similar).** A stated value wins over the declared one. `_apply_declared_paths` checks `is not None`, so `requirements: ""` withdraws the catalog rather than falling through to the declaration.

**Whole sections from `--declare` vs `.clew.yaml`.** The stated section **replaces** the file's section wholesale. There is no deep merge, so `{}` withdraws the statement and the file answers again.

**Exclusions.** These do not conflict. `--exclude`, `toolchain.toml` `[ignore].paths`, and `tool = "*"` suppressions are all unioned into one exclusion list.

**Replay across builds.** This is the subtle one. A tier-1 value recorded by an earlier build is replayed on a plain refresh, and it beats the current `.clew.yaml` for that option. Passing a flag or `--declare` overrides the recorded value. `--exclude` with no values withdraws a recorded exclusion, and manifest/section statements can be withdrawn with an empty value. Toolchain exclusions are deliberately not replayed, so editing `toolchain.toml` takes effect immediately.

## Caveat I found

The docstring for `resolve_layered` says an empty explicit list is a withdrawal, but `_stated_layer` tests truthiness (`if explicit:`). So `--entry-patterns` with no values does **not** suppress `.clew.yaml`'s list; the declared list is inherited. Only the `is not None` path options behave as the docstrings describe. If you rely on withdrawal, check the specific option.

Sources: `clew/tiers.py` (tier table and `resolve_layered`), `clew/buildoptions.py` (tier-1 options and validation), `clew/cli.py` (`_build_argparser` ~L420, `_apply_declared_paths` ~L1360, `_with_stated_sections` ~L1307, `_entry_patterns` ~L1231, the replay block ~L3080–3135, `_apply_toolchain_exclusions` ~L2518), `clew/toolchain.py`.