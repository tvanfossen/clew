I have the full picture now. Here's the answer:

## Ways to set thresholds

1. **CLI flags** — `--mccabe-threshold`, `--cognitive-threshold`, `--nesting-threshold`, `--sloc-threshold`, `--abc-threshold`, `--return-threshold`, `--aird-threshold`, `--aicp-threshold`, `--external-calls-threshold`, `--unreachable-blocks-threshold`. If a flag is repeated, last occurrence wins (clap "last-wins" behavior, tested in `test_threshold_arg_override_last_wins`).
2. **`knots.toml` per-language section** — `[<lang>.thresholds]` (e.g. `[c.thresholds]`), keyed on the language's canonical key (`"c"`, `"cpp"`, `"rust"`, …), resolved by the file being analyzed.
3. **`knots.toml` global section** — `[thresholds]`, applies to every language not overridden per-language.
4. **Inline suppression comments** — `// tools:suppress knots:<metric> JUSTIFICATION:"..."` suppresses one metric for the function whose line the comment targets; an unqualified `// tools:off` … `// tools:on` region suppresses *all* metrics for any function it spans. These short-circuit the check entirely regardless of any threshold value set above.
5. **Baseline ratcheting** — `--baseline <file>` (with `--write-baseline` to snapshot). This doesn't change the threshold value itself, but it changes what counts as a *violation*: a function already over threshold is tolerated as long as it hasn't gotten worse than its baseline snapshot. This is probably the most likely "threshold got ignored" surprise — the threshold is still active, but pre-existing offenders are silenced by the baseline file.

**Precedence for the threshold *value* itself** (`EffectiveThresholds::for_file`, in `src/main.rs`): **CLI flag → per-language `knots.toml` section → global `knots.toml` section**, resolved independently per metric per function's language. CLI always wins; there's a dedicated test (`effective_thresholds_cli_wins_over_config`) pinning that CLI beats `knots.toml` "regardless of layer."

`knots.toml` itself is discovered by walking up from `cwd` to the filesystem root looking for the first `knots.toml` found — so a stray `knots.toml` in a parent directory (not the repo the user thinks they're in) can silently supply thresholds/excludes nobody intended.

## Ways to set exclusions (separate resolution path — not merged with thresholds)

1. **`--exclude <file>`** — legacy JSON sidecar (`FilterRules`), blacklists files/functions.
2. **`--exclude-path <regex>`** — repeatable CLI regex on file path (same syntax as pre-commit `exclude:`).
3. **`knots.toml` `[[filter.exclude]]`** — glob `file_patterns` AND regex `function_patterns` (both optional; empty = matches everything for that field); excluded if *any* entry matches.
4. **Inline suppression** (`tools:off`/`tools:suppress`) also effectively "excludes" specific metrics/functions from gating, as above.

For exclusions there's no single "highest wins" merge like thresholds — they're **additive/OR'd**: a file or function excluded by *any one* of `--exclude`, `--exclude-path`, or `knots.toml`'s `[[filter.exclude]]` is dropped, independent of the others (each filter is applied via its own `retain`/`should_process_file` check). So for exclusions there's no single winner — any one of them silencing a function is sufficient to make it disappear from the report, which is the other likely source of the user's "ignored threshold" complaint (the function was thresholded correctly but excluded before the check ever ran).

**Most likely explanation for the report:** either (a) a `knots.toml` sitting in a parent directory that CLI flags don't override for *other* metrics (the value the user tried to set only wins for the specific metric they passed on the CLI — a per-language section can still override the metrics they didn't pass), (b) an active `--baseline` file tolerating an old offender, or (c) the function got matched by an exclude rule (JSON sidecar, `--exclude-path`, or `knots.toml`'s `[[filter.exclude]]`) before the threshold check ever ran.
