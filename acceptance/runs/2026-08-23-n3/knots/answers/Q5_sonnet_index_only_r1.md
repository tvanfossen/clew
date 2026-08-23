I have enough grounded detail from the index to answer fully.

## How thresholds/exclusions can be set — and precedence order

The index locates this logic in `EffectiveThresholds` (`src/main.rs:465`), whose own brief states it directly:

> "Merges CLI thresholds (highest precedence), `knots.toml`'s per-language [thresholds], ... "

and `src/config.rs`'s file doc confirms the same rule from the config side: *"CLI flags always take precedence over anything loaded here, and the legacy `--include`/`--exclude` JSON sidecar (`FilterRules`) keeps working unchanged."*

**Thresholds — three layers, resolved per metric per file:**

1. **CLI flags** (`--aird-threshold`, `--aicp-threshold`, `--external-calls-threshold`, and the McCabe/Cognitive/Nesting/SLOC/ABC/Returns equivalents shown in the README's Command-Line Options) — **highest precedence, always wins if set.**
2. **`knots.toml` per-language thresholds** (`TomlThresholds`, keyed by language) — used when no CLI flag overrides that metric.
3. **`knots.toml` global thresholds** — the fallback under the per-language table.

`EffectiveThresholds::for_file(file_path)` (member of the struct at `src/main.rs:502`) is what resolves this merge for a given file at check time — `check_thresholds` calls `t.for_file(&func.file_path)` per function before comparing each metric (McCabe, Cognitive, Nesting, SLOC, ABC, Returns, AIRD, AICP, ExternalCalls, UnreachableBlocks). `has_active_threshold()` (`src/main.rs:493`) is the gate that decides whether *any* threshold is active at all — it's `true` if the CLI thresholds are active, OR the global toml section has anything set, OR any per-language toml section has anything set.

**Exclusions — two independent, coexisting mechanisms:**

1. **Legacy `--include`/`--exclude` JSON sidecar** — `FilterRules` (`src/lib.rs:67`), loaded via `FilterRules::from_file`, checked by `should_process_file` (`src/main.rs:1399`): include rules are a whitelist checked first (file must match to proceed), then exclude rules are a blacklist (file is dropped if it matches). There's also a plain regex-list path, `path_is_excluded` (`src/main.rs:1394`), used during file discovery (`collect_files`).
2. **`knots.toml` `[[filter.exclude]]` entries** — `FilterExclude` (`src/config.rs:77`), each entry with `file_patterns` (glob) and `function_patterns` (regex), evaluated by `exclude_matches` (`src/config.rs:112`) — a rule matches only if *both* the file glob and the function-name regex match (empty pattern lists are treated as "matches anything"). This is called from `collect_all_metrics` and `run_single_file_mode`, i.e. it filters at the function level, not just the file level.

The config file's own doc comment is explicit that this is not a replacement but an addition: the JSON sidecar "keeps working unchanged" alongside `knots.toml`.

## Which one wins

- For **thresholds**: CLI flag > `knots.toml` per-language > `knots.toml` global. A CLI flag on any given metric always wins outright — this is stated directly in `EffectiveThresholds`'s brief and structurally enforced by `for_file`'s merge order.
- For **exclusions**: the two mechanisms are independent and both applied — a file/function excluded by *either* the JSON sidecar (`--include`/`--exclude`) or `knots.toml`'s `[[filter.exclude]]` is excluded. There's no single override winner here; they're additive gates, not a precedence chain.

## Likely explanation for the user's report

Given the precedence rule, the most probable cause of "knots ignored my configured threshold" is that a **CLI flag for that same metric was also set** (e.g., in a CI script, an alias, or a wrapper) and silently overrode the `knots.toml` value — that's the one documented precedence collision in this system. The index can't tell me what the user's actual CLI invocation or `knots.toml` file contained (that's data, not code structure), so if you want to confirm this specific case, I'd need the actual command line and config file used, not just the index.

One gap I could not close from the index alone: I could not pull the exact TOML shape (`[thresholds]` vs `[thresholds.<language>]` key names) — `TomlThresholds`'s fields weren't returned in the dossier body (only its `any_set`/`default`/derive methods showed), so I'm relying on the struct name and doc-comment for the "global vs per-language" split rather than having read the literal field list. If precision on the TOML key names matters, that's worth a source read of `src/config.rs` rather than the index.
