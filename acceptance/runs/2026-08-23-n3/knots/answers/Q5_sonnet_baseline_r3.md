## Ways to set thresholds

There are three layers, resolved **per metric, per function** (not as one all-or-nothing config):

1. **CLI flags** — `--mccabe-threshold`, `--cognitive-threshold`, `--nesting-threshold`, `--sloc-threshold`, `--abc-threshold`, `--return-threshold`, `--aird-threshold`, `--aicp-threshold`, `--external-calls-threshold`, `--unreachable-blocks-threshold`. Repeating a flag is "last one wins" (`src/main.rs:49`, tested at `main.rs:1744`).
2. **`knots.toml` per-language section** — `[<lang>.thresholds]` (e.g. `[c.thresholds]`), keyed by the same canonical language key `language_for_file` resolves (`config.rs:31`).
3. **`knots.toml` global section** — `[thresholds]`.

`knots.toml` is auto-discovered by walking up from the current directory (`config.rs:88`); it's entirely optional, and there's no way to point knots at a different filename — that's likely the first place a "config was ignored" report comes from: the file has to be named exactly `knots.toml` and live in an ancestor of cwd.

**Resolution winner:** `EffectiveThresholds::for_file` (`main.rs:502`) does `self.cli.<metric>.or(lang_cfg.<metric>).or(self.global.<metric>)` **independently for every metric**. So it's not "CLI file wins entirely over toml file" — a user can set `--cognitive-threshold=20` on the CLI and still have `mccabe` come from `knots.toml`'s per-language or global section. Precedence order per metric: **CLI > per-language `knots.toml` > global `knots.toml`**. If none of the three set a given metric, that metric simply isn't gated at all (thresholds are opt-in; `has_active_threshold()` gates whether checking runs at all).

On top of raw threshold values, two more things can make a configured threshold appear to do nothing even though it resolved correctly:

- **`--baseline`** ratchets: an over-threshold function that's already in the baseline and hasn't gotten *worse* is tolerated, even though it's still over the numeric threshold.
- **`--since <REF>` / `--changed`** scope gating to only functions overlapping changed lines — a pre-existing violation in an untouched function is silently skipped.
- **Inline suppression comments** (`// tools:off` … `// tools:on`, or `// tools:suppress knots:<metric>`) suppress specific metrics (or all of them) for a function regardless of what threshold layer set the value (`lib.rs:830+`).

## Ways to set exclusions

Four independent mechanisms, and they're **not mutually exclusive — they AND together** (a file/function must survive all of them to be reported):

1. **`--exclude <FILE>`** — JSON sidecar, blacklist by file/function (legacy `FilterRules`), applied in `should_process_file` before a file is even parsed.
2. **`--include <FILE>`** — JSON whitelist counterpart, same gate.
3. **`--exclude-path <PATTERN>`** (repeatable regex, pre-commit `exclude:` syntax) — also a pre-parse file-level filter (`path_is_excluded`).
4. **`knots.toml`'s `[[filter.exclude]]`** — glob `file_patterns` AND regex `function_patterns` within an entry, matched against any entry (OR across entries). This one runs *after* metrics are computed (`metrics.retain(|f| !config::exclude_matches(...))`), so it's the only mechanism with real function-name granularity, not just file-path.

There's no precedence question among the exclusion mechanisms because none of them override each other — they're independent filters applied in sequence, so if a user's `knots.toml` exclusion isn't taking effect, check whether a `--exclude`/`--exclude-path` CLI filter or the JSON `--include` whitelist is already dropping the file earlier in the pipeline, or whether `knots.toml` simply wasn't discovered (wrong directory).

## Most likely cause of the report

Given the per-metric merge, the most probable explanation for "knots ignored a threshold I configured": the user set it in `knots.toml` (global or per-language) while **also** passing that same `--*-threshold` flag on the CLI (e.g. in a wrapper script or CI job) with a different — often default/unset — value, and CLI silently wins for that metric per `for_file`. Second most likely: `knots.toml` isn't being discovered because it's not in an ancestor directory of the invocation's cwd. Third: the offending function is covered by a `tools:off`/`tools:suppress` comment or is outside `--since`/`--changed` scope or tolerated by `--baseline`.
