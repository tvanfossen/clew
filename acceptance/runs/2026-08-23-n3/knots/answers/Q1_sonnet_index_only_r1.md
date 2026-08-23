I now have the full picture from the index. Here's the answer.

## What counts as a duplicate

Two or more functions are grouped together when their fingerprints — computed by the external `lang_parsing_substrate::function_fingerprints` (an out-of-repo crate the index can't see inside; treat that hashing algorithm as a genuine blind spot) — collide exactly. Per the file-level doc on `src/duplicates.rs`, that's "AST subtrees hash identically — same node kinds in the same [structure]", i.e. this is **structural** duplication (shape of the parse tree), not textual diffing and not semantic equivalence. Two functions with different variable names but the same control-flow/node-kind skeleton will match; two functions that do the same thing via different syntactic shapes will not.

The pipeline (`recursive_duplicate_groups` → `collect_corpus_fingerprints` → `find_duplicate_groups` → `sorted_duplicate_groups` → `grouped_members`/`duplicate_groups`) is two phases:
1. **Fingerprint** every file in parallel (`extract_file_fingerprints`, `.par_iter()`), producing one `CorpusFingerprint` per function subtree that clears `MIN_DUPLICATE_NODES = 20` AST nodes.
2. **Group** fingerprints by identical hash into groups of 2+ members, sorted largest-group-first then by node count (`group_sort_key`) — "the clones most worth acting on come first."

## What it deliberately misses

- **Anything under 20 AST nodes** (`MIN_DUPLICATE_NODES`) never gets fingerprinted at all — trivially small functions are excluded up front, not filtered after the fact.
- **CERT-C-style fixture pairs** — `tests/pass/foo.c` vs `tests/fail/foo.c` and similar pass/fail, accept/reject, good/bad directory pairs. `is_fixture_pair_group` detects when a group's members sit in exactly two such tagged directories but are otherwise path-identical once the tag is normalized out, and drops them (gated by `filters.exclude_fixture_pairs`) — these are *intentionally* near-identical test fixtures, not extraction candidates.
- **Trivial noise groups** — `is_trivial_noise_group`: every member's body is ≤3 lines (`TRIVIAL_BODY_LINE_SPAN`) *and* the group repeats fewer than 4 times (`TRIVIAL_MIN_REPEAT`). The doc comment is explicit about why `MIN_DUPLICATE_NODES` alone isn't sufficient here: a one-line accessor can clear the 20-node floor purely from type annotations and field-access chains, and — notably — per-type accessor glue produced *by fixing* real duplication elsewhere would otherwise show up as new "unresolved debt," which is a false signal worth suppressing.
- Both exclusions are optional filters (`DuplicateFilters`, driven by `--include-fixture-pairs` / `--include-trivial-duplicates`), so a user can turn either back on.
- Structural-only matching also means it misses **semantic** duplicates (same behavior, different shape) and near-duplicates that differ by even one AST node kind — there's no fuzzy/similarity scoring, only exact hash equality.

## Why it isn't part of the normal analysis pass

Two structural reasons show up in the call graph itself:

1. **It needs the whole corpus in memory before it can say anything**, unlike per-function metrics (McCabe, cognitive, SLOC, etc.) which are computed file-by-file/function-by-function as a stream. `collect_corpus_fingerprints` explicitly parses and fingerprints *every* file first (phase 1) before `find_duplicate_groups` can compare anything across files (phase 2) — there's no meaningful "duplicate" answer for a single file in isolation.
2. **It's explicitly gated**, not run by default: `recursive_duplicate_groups` only runs when `ctx.recursive && ctx.find_duplicates` — it requires both `--recursive` (since a single file has no corpus to compare against) and the opt-in `--find-duplicates` flag. `run_multi_file_mode` calls it as a distinct, separately-gated step alongside (not inside) `collect_all_metrics`.

The index can't tell me the actual cost/perf rationale (e.g., whether fingerprinting all functions is expensive enough to justify opt-in) — that would require reading the CLI help text or a design doc, which isn't captured as a queryable fact. But structurally, it's a corpus-wide batch pass bolted onto the recursive/multi-file path, not a per-function metric, which is consistent with why it's flag-gated rather than always-on.
