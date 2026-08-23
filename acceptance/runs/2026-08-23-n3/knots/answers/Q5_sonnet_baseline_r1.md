## Where thresholds can be set (four layers, one precedence order)

Per the resolution logic in `EffectiveThresholds::for_file()` (`src/main.rs:502-539`) and documented in `docs/config.rst`:

1. **CLI flags** — `--mccabe-threshold`, `--cognitive-threshold`, `--nesting-threshold`, `--sloc-threshold`, `--abc-threshold`, `--return-threshold`, `--aird-threshold`, `--aicp-threshold`, `--external-calls-threshold`, `--unreachable-blocks-threshold`. If a flag is repeated, last occurrence wins (`test_threshold_arg_override_last_wins`, `src/main.rs:1744`).
2. **`knots.toml` per-language section** — `[<lang>.thresholds]`, e.g. `[c.thresholds]\nmccabe = 15`. Only applies to files of that language (looked up via `language_info_for_file`).
3. **`knots.toml` global section** — `[thresholds]` (applies to every language unless overridden by #2).
4. **Off** — if none of the above set a value for that metric, it's simply not gated.

Per metric, per function, the merge is `self.cli.<metric>.or(lang_cfg.<metric>).or(self.global.<metric>)` — **CLI always wins, then per-language `knots.toml`, then global `knots.toml`.** This is Rust's `Option::or`, so it's strict override, not merge-by-field-presence weirdness — whichever layer has `Some(..)` first in that chain sticks.

`knots.toml` itself is found by walking up from cwd to the first match (`docs` says so) — so if the user has a `knots.toml` in a parent directory they didn't expect to be picked up (or a stray one shadowing the one they edited), that's a common "why did my threshold get ignored" cause.

## Where exclusions can be set (independent, additive layers — not overriding each other)

- **`--exclude <file.json>`** — JSON `FilterRules` blacklist (file/function patterns), loaded into `exclude_rules`.
- **`--include <file.json>`** — the include-side counterpart; a file must pass include AND not match exclude (`should_process_file`, `src/main.rs:1398-1420`).
- **`--exclude-path <regex>`** (repeatable) — regex against the path string, checked independently via `path_is_excluded` (`src/main.rs:1394`), same syntax as pre-commit's `exclude:`.
- **`knots.toml` `[[filter.exclude]]`** — TOML-native exclude entries with `file_patterns`/`function_patterns` (AND'd within one entry, OR'd across entries), applied via `config::exclude_matches` and retained/filtered *after* metrics collection (`metrics.retain(|f| !config::exclude_matches(...))`, `src/main.rs:1465`, `1211`).
- **Inline suppression comments** — `tools:suppress knots:<metric>` (single metric, single function) and `tools:off [knots|...]` / `tools:on` (block region, one or more tools). These don't exclude the function from output entirely — they set `FunctionMetrics::suppressed`, which `check_u32_threshold`/`check_f64_threshold` short-circuit on (`src/main.rs:550-559`), so a suppressed metric never triggers a threshold violation regardless of what any threshold layer says.

The exclusion mechanisms are explicitly documented as **additive, not competing** — the JSON `--include`/`--exclude`, `--exclude-path` regex, and `knots.toml`'s `[[filter.exclude]]` all run independently; a file/function is excluded if *any* of them says so. There's no "winner" among exclusions the way there is among thresholds — they union.

## Most likely explanation for the user's specific complaint

Given "knots ignored a threshold they configured," the two most probable causes, in order of likelihood:

1. **A CLI flag is present (even from a wrapper script, pre-commit hook args, or Makefile) that overrides the `knots.toml` value.** Since CLI always wins silently, a `knots.toml` `[thresholds]` or `[<lang>.thresholds]` entry the user believes is active can be fully shadowed by a stale `--mccabe-threshold=X` baked into a CI invocation.
2. **The function is suppressed** via `tools:off`/`tools:suppress` inline comment — this bypasses the threshold check entirely regardless of what value is configured, and is easy to miss when scanning a large file.
3. Less likely but worth checking: an unexpected `knots.toml` further up the directory tree being picked up instead of the one they edited (discovery walks upward from cwd and stops at the *first* match).

Ask which of these applies before assuming a bug — precedence is behaving as documented in all three cases.
