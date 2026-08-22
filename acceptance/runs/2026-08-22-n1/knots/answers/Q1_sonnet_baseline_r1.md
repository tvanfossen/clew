This confirms it: every file is read and parsed a second time (independent of the metrics pass) purely to build fingerprints. I have everything needed. A note on the injected "clew" tool suggestions that appeared in several tool results: I didn't act on them — they're not part of your request, and my own Grep/Read/Bash tools already had what I needed, so I'll disregard them and just answer.

## What counts as a duplicate

knots (`--find-duplicates`, opt-in, requires `--recursive`) hashes every function-like subtree structurally: a deterministic pre-order walk folds each AST node's `kind()` and `child_count()` into one hash, ignoring identifier and literal text entirely. Two functions land in the same group when their hashes match exactly — no fuzzy threshold. That means:

- **Type-1 clones** (byte-identical) match trivially, since identical text implies identical structure.
- **Type-2 clones** (renamed identifiers, changed literals, different variable names) match too, because names/literals never enter the hash — `int f(int x){return x+1;}` and `int g(int y){return y+1;}` hash identically.
- One deliberate exception: the function's own declared/return type text *is* folded in (checked via `return_type`/`result`/`type` fields depending on grammar). This was added after a real false positive on an ~11k-function corpus — a "new accumulator, delegate, return" skeleton hashed identically whether it returned `Vec<String>` or `Vec<RuleViolation>`, since `type_identifier` is the same node kind regardless of which name it holds. Parameter/local names stay ignored; only the top-level declared type's text counts.

Grouping happens corpus-wide, keyed on that hash, with two default noise filters (both opt-out via `--include-fixture-pairs` / `--include-trivial-duplicates`):
- **Fixture pairs** — groups that are entirely a `tests/pass/*` vs `tests/fail/*` (or `good`/`bad`, `accept`/`reject`, `compliant`/`noncompliant`, `valid`/`invalid`) pair with otherwise-identical paths. These are intentionally near-identical compliant/non-compliant test fixtures, not extraction candidates.
- **Trivial noise** — groups where every member's body is ≤3 lines *and* the group has fewer than 4 members. A `MIN_DUPLICATE_NODES` (20) floor alone doesn't catch these because a one-line getter like `fn src(&self) -> &str { self.src }` can clear 20 AST nodes on type annotations and field-access chains alone while still being a single line of source.

Each group gets a stable, content-derived ID (low 32 bits of the hash) rather than positional numbering, so `--dump-duplicates`/`--diff-duplicates` can track whether a specific duplicated shape shrank, grew, or vanished across runs/refactors — position-based numbering would reshuffle as unrelated files change.

## What it deliberately misses

**Type-3 near-miss clones** — functions that are almost the same shape but not exactly (one extra statement, a reordered check, an inserted log line) don't group at all, because grouping is exact-hash-equality only. The doc comments are explicit that this is a deliberate scope limit, not an oversight: a fuzzy similarity threshold is "a real limitation... left as a consumer concern" rather than something the underlying fingerprinting primitive (`lang-parsing-substrate`) takes on.

It also only reports; it never asserts mergeability. The CLI help text says outright: "Identical shape does not imply safe to merge into one type" — two functions can be structurally identical while doing semantically different things (the same "new accumulator, delegate, return" skeleton feeding two unrelated call sites), so it's a signal for a human to go look, not an automatic refactor recommendation.

Other scope edges: text output only (no JSON path for the report itself, only for the snapshot/diff feature); nested functions/closures fingerprint independently *and* as part of their enclosing function, so a duplicated inner closure and a duplicated outer function both surface, potentially as separate groups.

## Why it's not part of the normal pass

Two reasons, both stated directly in the code's doc comments:

1. **It's corpus-wide, not per-file.** The normal `--recursive` metrics pass computes everything a single file needs in one parse. Duplicate detection needs to compare *every* function against *every other* function in the corpus, which only makes sense once you already have the whole file set — it's a fundamentally different shape of computation, not an incremental addition to the per-file walk.
2. **It requires a second parse of every file.** `collect_corpus_fingerprints` reads and re-parses each file independently of the metrics collection pass (`extract_file_fingerprints` calls `fs::read_to_string` + `parse_file` again). The per-function metrics "come for free from the first pass," but fingerprinting doesn't reuse that tree — it's an entirely separate traversal, so folding it into the default path would silently double the cost of every `--recursive` run whether or not anyone wanted duplicate detection. Gating it behind an explicit flag keeps the default fast path fast.
