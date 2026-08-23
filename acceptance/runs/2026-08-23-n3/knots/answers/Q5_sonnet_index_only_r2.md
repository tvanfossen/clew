Here's what the index shows, grounded in `src/main.rs` and `src/config.rs`.

## Thresholds — three sources, merged by `EffectiveThresholds`

`EffectiveThresholds::new` (`src/main.rs:472`) builds this from two inputs: CLI-parsed `Thresholds` and an optional `KnotsToml` (`knots.toml`, discovered via `KnotsToml::discover`). It splits the toml side into a `global` `TomlThresholds` (top-level `[thresholds]`) and a `per_language` map (each `[languages.<key>].thresholds` section, keyed by `language_info_for_file`'s key).

The actual precedence is resolved lazily, per file, in `EffectiveThresholds::for_file` (`src/main.rs:502`) — for every metric (mccabe, cognitive, nesting, sloc, abc, returns, aird, aicp, external_calls, unreachable_blocks) it does:

```
self.cli.<metric>.or(lang_cfg.<metric>).or(self.global.<metric>)
```

So the precedence, highest to lowest, is:

1. **CLI flag** (`Thresholds` parsed from argv) — always wins if set.
2. **`knots.toml` per-language section** (`[languages.<lang>].thresholds`) — wins over global if CLI didn't set it.
3. **`knots.toml` global `[thresholds]`** — the fallback.

`has_active_threshold` (used by `check_thresholds` to short-circuit entirely) is true if *any* of the three layers (`cli.active()`, `global.any_set()`, or any per-language `any_set()`) has anything set — so a threshold configured only in a per-language block, with no CLI flag and no global block, is still active.

**Most likely explanation for the user's report:** if they set a threshold under `[languages.<lang>]` in `knots.toml` and *also* passed the corresponding CLI flag (even a default value baked into a wrapper script), the CLI value silently wins — the per-language and global toml values are never consulted for that metric. This is the classic "I configured it in the file but it's ignored" bug shape, since `.or()` short-circuits on the first `Some`.

## Exclusions — two independent mechanisms, applied at different stages

These are **not** merged into one precedence chain like thresholds — they're two separate filters applied at different points in the pipeline, so both can be active simultaneously and either can suppress a result:

1. **File/function `FilterRules`** (`include_rules` / `exclude_rules`, `src/lib.rs`) — glob-based include and exclude regex lists (with `!`-negation support in `matches_file`), applied by `should_process_file` during file discovery (`collect_files`), and again against function names via `matches_function`/`matches_complexity` during metric collection (`collect_function_metrics`). Include is checked first (whitelist), then exclude (blacklist) — exclude wins if both would otherwise pass.

2. **Path-pattern exclusion** (`exclude_path_patterns: &[regex::Regex]`, checked by `path_is_excluded`) — a separate raw-regex list applied in `collect_files` *before* `should_process_file`, at the whole-file level, independent of `FilterRules`.

3. **`knots.toml` `[[filter.exclude]]`** (`FilterExclude` / `exclude_matches`, `src/config.rs`) — glob `file_patterns` **and** regex `function_patterns`, ANDed per entry, ORed across entries. This is applied *after* parsing, in `collect_all_metrics` (`all_metrics.retain(|f| !exclude_matches(...))`) and in `run_single_file_mode` — it's a final post-filter on already-computed `FunctionMetrics`, distinct from and later than both of the above.

So for exclusions there's no single "winner" — a function/file is excluded if **any** of the three mechanisms would exclude it (CLI `--exclude` patterns, CLI `--exclude-path` patterns, or `knots.toml`'s `[[filter.exclude]]`), since they're applied as sequential filters, not merged with override semantics.

**Gap the index can't close:** I don't have the clap attribute strings (flag names like `--mccabe-threshold` vs `--threshold`) since those live in field attributes the index doesn't surface as separate symbols — you'd want to read the `Thresholds`/CLI struct definition directly in `src/main.rs` around line 411 to confirm exact flag spellings before telling the user which flag is overriding their `knots.toml`.
