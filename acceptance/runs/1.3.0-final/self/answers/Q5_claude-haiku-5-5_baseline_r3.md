The ways to configure indexing are layered, and the layers combine by a fixed rule. Nothing I found was run, so this comes from reading the source and its docstrings.

**The ways to say so, highest precedence first**

| Tier | Source | How it combines |
|---|---|---|
| 1 | Explicit statement for this build: `--declare FILE`, the `options` argument of `build_index` / `index(action='refresh')`, or a single flag such as `--entry-patterns`, `--scope`, `--exclude` | Replaces the layer below |
| 2 | The repo's own `.clew.yaml` (`preprocessor:`, `index_scope:`, `entry_patterns:`, `kconfig:`, `shared_key_patterns:`, and so on) | Replaces the guesses |
| 3 | Facts already written by the target, such as a Doxyfile's ALIASES/PREDEFINED, generator manifests, or language entry points | Accumulates; no stated tier removes it |
| 4 | Known-ecosystem signatures (UDM, ingot) | Accumulates, same as tier 3 |
| 5 | Name-pattern heuristics, such as `main` or `tests/*` | The floor; any stated tier displaces it |

The rule is in `clew/tiers.py`: `resolved = (tier1 or tier2 or tier5) ∪ tier3 ∪ tier4`. The short version is "you can correct our guesses; you cannot un-discover a fact."

Some options sit outside the declaration route. `--repo-root` and `--output` are endpoints, and `--exclude` is an index-shape argument that is recorded into the index. `guard:` in `.clew.yaml` configures the gate, not the index, except for the `@req` id pattern and the requirements catalog path, which the index also reads.

**When two of them disagree**

- **Flag or `--declare` against `.clew.yaml`:** tier 1 wins. For manifest-style options, `_declared_or_flag` returns the explicit value and ignores the declaration. A stated section replaces the declared one wholesale; it is never deep-merged. `preprocessor:` is the example given: stating `predefined:` does not keep the declared `config_header`.
- **Empty values withdraw a statement:** `{}`, an empty file, or a bare flag like `--exclude` with no values withdraws the tier-1 statement and falls back to the declaration or the guesses. An absent flag inherits the recorded statement.
- **Tier-1 statements are sticky:** `--exclude` and tier-1 `--entry-patterns` are recorded in the database and replayed by later builds, including MCP refreshes that pass no flags. A tier-2 declaration is re-read from the file on each build and is not replayed.
- **Two stated tiers under the accumulating rule:** tiers 3 and 4 never lose to a stated value. A Doxyfile `PREDEFINED` still counts even when `preprocessor.predefined` is declared.
- **`index_scope` against `--scope`:** this is a hard error, not a silent override. A stated `index_scope` is only read with `--scope from-guard`, so `_apply_scope` exits 1 and says to drop one of them. The docstring explains that a warning would be invisible to the agent callers this is built for.
- **Visibility:** the winning tier for each option is stamped into `build_meta` as `options.<name>.tier`, so two indexes of one commit that differ in policy show it in their metadata.

The key files are `clew/tiers.py`, `clew/cli.py` (`_declared_or_flag`, `_apply_scope`, `_apply_declared_document`, `_manifest_option_tiers`, and the `--declare` help text), `clew/buildoptions.py` (`apply_options`), `clew/preprocessor.py`, and `clew/guardconfig.py`.