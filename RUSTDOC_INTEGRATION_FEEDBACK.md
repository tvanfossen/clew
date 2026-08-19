# Feedback on Rust support (`feat/rustdoc-support`, PR #8), from integrating clew into `knots`

Context: this is feedback from actually wiring `clew` into a real, non-toy Rust repo
(`knots`) end to end — `clew init`, a real index build, MCP server registration, and
querying it live via `dossier`/`search`/`index(action='status')` from an agent session.
The PR body already cites `knots: 158 symbols/16 compounds/115 call edges` as
verification; the finding below is that number is real but incomplete, and the gap is
silent. Filing this for whoever is iterating on PR #8 before it merges.

## 1. A package's bin target is silently dropped whenever it also has a lib target — even when the bin isn't a thin wrapper

`_discover_targets` in `clew/rustdoc.py` picks a package's lib target *instead of* its
bin target(s) when both exist, on the stated assumption that "a `main.rs` binary is
usually a thin wrapper around it." That assumption fails for `knots` itself:

```toml
# knots/Cargo.toml
[[bin]]
name = "knots"
...
[lib]
name = "knots"
```

`src/main.rs` and its private modules (`config.rs`, `duplicate_diff.rs`,
`duplicates.rs`, `output.rs` — the CLI arg parsing, config-file loading,
duplicate-diff computation, and all output formatting) are the bin target, are **not
a thin wrapper**, and are **entirely absent from the index**. Confirmed live:

```
dossier(subject="run_single_file_mode")  -> not indexed
dossier(subject="ExplainMetric")         -> not indexed
```

Both are real, live symbols in `main.rs`. `search(corpus="files")` shows only 3 files
under `src/` indexed (`lib.rs`, `complexity.rs`, `coupling.rs`) — every module reachable
only from the bin target is missing. Nothing in the build log, `clew init`'s doctor
output, or `index(action='status')` mentions that a target was skipped — this was only
discovered by manually diffing "files in `src/`" against "files clew reports."

**This isn't a knots-specific quirk.** `tools_sqc`'s `Cargo.toml` has the identical
shape — a `[lib]` and a `[[bin]]` both named `sqc` — so the same silent gap will
reproduce there the moment it's onboarded, unless this is fixed first.

**Suggested fix**: when a package declares both a lib and one or more bin targets, run
`cargo +nightly rustdoc` for **all of them**, not lib-instead-of-bin. The three required
tables (`path`/`refid`/`memberdef`) are already keyed by file path, so a bin target's
rows don't collide with the lib's. Short of that, at minimum: log which targets were
*not* documented and why, the same way `--exclude` and `index_scope` already report
what's out of scope — a skip that's this consequential shouldn't be quieter than an
intentional exclude.

## 2. Confirmed working, but non-obvious enough to call out explicitly in the PR/README: doc comments are not required for indexing

Verified directly: private, fully undocumented functions (`glob_match`, `name_field` in
`knots/src/lib.rs`, zero `///` lines, not `pub`) came back from `dossier` with complete
signature, body, callers, callees, and liveness — everything *except* `brief`/`detail`,
which are just empty strings. The mechanical rustdoc-JSON → doxygen-table translation
described in `rustdoc.py`'s module docstring holds regardless of doc-comment presence;
`///`/`//!` only fill in the two prose fields.

This is good behavior, but worth stating plainly in the PR description or README rather
than leaving it implicit in the module docstring — anyone onboarding a Rust repo
(including us, about to do this for `tools_sqc`) will otherwise over-invest in writing
doc comments before indexing "works," when the actual requirement is zero.

## 3. File-level `//!` docs matter for a different reason than `///` — worth stating alongside the C/C++ `@file` docs

`clew/filedocs.py`'s own docstring (gh#10) explains that file-level doc comments feed
`search`'s conceptual-query path (`search("deadlock")` finding a module about lock
nesting even though no function is named that), separately from the per-symbol
`brief`/`detail` that `///` produces. This applies identically to Rust's `//!`, but
nothing in the Rust-facing parts of the PR (or `README.md`'s "doxygen-guard is
optional" section) says so. Worth a line noting that a Rust repo benefits from a `//!`
module doc at the top of any file whose value is conceptual (a metrics-formula module,
a dispatch/threading module) for the same reason a C file benefits from a leading
`/*! ... */` block — independent of whether individual functions get `///`.

## 4. `clew init`'s doxygen doctor check fails even for a repo that will never invoke doxygen

Running `clew init` against `knots` (pure Rust, no Doxyfile) reports:

```
[fail] doxygen   /usr/bin/doxygen was built WITHOUT sqlite3 support ...
```

...and exits 1, even though this repo's build path is `run_rustdoc`, which never shells
out to doxygen at all (confirmed in the build log: `Running rustdoc: cargo +nightly
rustdoc ...`, no doxygen invocation). The check is unconditional in
`init_command.py`'s check list, independent of whether the target repo would actually
exercise it. For a Rust-only repo this is a false alarm that costs a debugging detour
(we initially assumed it was a real blocker before checking `cli.py`'s
`_run_doxygen_or_rustdoc` decision logic).

**Suggested fix**: either detect "this repo has no doxygen-usable target" (mirrors
`_discover_targets`'s own lib/bin logic — if every discovered target routes to
`run_rustdoc`, doxygen is moot) and downgrade the check to informational for that case,
or at least word the failure as conditional ("...if this repo ever indexes a C/C++
target") so a pure-Rust adopter isn't left thinking `clew init` is broken.
