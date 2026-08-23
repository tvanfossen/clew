I now have the full precedence chain from the index. Here's the answer.

## Ways to set thresholds

1. **CLI flags** (`--mccabe`, `--cognitive`, `--nesting`, `--sloc`, `--abc`, `--returns`, `--aird`, `--aicp`, `--external-calls`, `--unreachable-blocks`) — stored in `Thresholds` (`src/main.rs`).
2. **`knots.toml`, per-language section** — parsed into `TomlThresholds` (`src/config.rs`), one block per language key.
3. **`knots.toml`, global section** — same `TomlThresholds` shape but applied repo-wide when no per-language value exists.
4. **Inline per-function suppression** — a `tools:suppress knots: <rule>` comment targeting a line inside the function, or an unqualified/`knots`-scoped `tools:off` region covering it. Resolved by `suppressed_metrics_for` (`src/lib.rs:850`) into `FunctionMetrics.suppressed`, and checked first in `check_u32_threshold`/`check_f64_threshold` (`src/main.rs:550`) — if suppressed, the metric is skipped entirely regardless of what any threshold says.
5. **Baseline mode** (`--baseline`/`--write-baseline`) — doesn't set a threshold itself, but changes what counts as a violation: a function that already exceeded the limit is only flagged if it got *worse* than its snapshotted (`BaselineEntry`) value.
6. **`--changed`/`--since` scoping** — also not a threshold setter, but narrows *which* functions get checked at all (`check_thresholds`, `src/main.rs:788`, skips functions outside the changed-line ranges).

## Precedence — which one wins

`EffectiveThresholds::for_file` (`src/main.rs:502`) merges layers 1–3 **per metric, per file**, using Rust's `Option::or` chain:

```rust
self.cli.mccabe.or(lang_cfg.mccabe).or(self.global.mccabe)
```

So for every individual metric, independently:

**CLI flag > `knots.toml` per-language block (matched by the file's language) > `knots.toml` `[global]` block.**

If none of the three set a value, that metric simply has no active threshold and is never checked (`has_active_threshold`, `src/main.rs:493`).

On top of whatever numeric limit wins that merge, **inline suppression always wins outright** — `check_u32_threshold`/`check_f64_threshold` return immediately if `suppressed` is true, before even looking at the limit. That's almost certainly the answer to "knots ignored my configured threshold": either (a) a CLI flag is overriding the `knots.toml` value the user set, (b) the function has a `tools:suppress knots: <rule>` or `tools:off` comment covering it, or (c) baseline mode is masking a pre-existing violation that didn't get worse.

## Ways to set exclusions

Two independent mechanisms, and they compose (not "winner-takes-all" — both are applied):

1. **`--exclude-path` CLI regex patterns** — checked by `path_is_excluded` (`src/main.rs:1394`) against the raw path string, applied to every file during discovery (`collect_files`, `src/main.rs:1322`), before include/exclude rules.
2. **`FilterRules` include/exclude** (`src/lib.rs:67`), sourced from CLI file-pattern flags or `knots.toml`'s `[[filter.exclude]]` entries (`FilterExclude`, `src/config.rs:77`, matched by `exclude_matches`). `should_process_file` (`src/main.rs:1399`) applies include rules as a whitelist first, then exclude rules as a blacklist — a file matching exclude is dropped even if it matched include.
3. **`.gitignore`** — `collect_files` walks directories with `ignore::WalkBuilder`, which respects `.gitignore` by default (not overridable from what the index shows — no flag surfaced to disable it).
4. **Function-level exclusion inside `FilterRules`** — `matches_function` (regex allowlist) and `matches_complexity` (min/max bounds) apply after file-level filtering, at the function-collection stage.

A file must survive **all** of: not matched by `--exclude-path`, not `.gitignore`-ignored, matched by include patterns (if any), and not matched by exclude patterns (`FilterExclude`/`FilterRules`) — any one of these can silently drop a file the user expected to be analyzed, which is the other likely explanation if "threshold ignored" actually means "file never got analyzed at all."

One gap the index can't settle: I don't have visibility into exactly how CLI flags for file/function include-exclude patterns get parsed into `FilterRules` (that's argument-parsing wiring in `main.rs` I didn't pull the body for) — if you need that detail, it's worth reading the `clap` arg struct directly rather than trusting a guess here.
