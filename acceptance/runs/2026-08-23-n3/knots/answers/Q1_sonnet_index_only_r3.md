I now have enough to answer fully from the index.

## What counts as a duplicate

Duplication in knots is purely **structural**, not textual. `src/duplicates.rs`'s file doc says it's "built on the substrate's structural fingerprinting (`lang_parsing_substrate::fingerprint`). Two functions group together when their AST subtrees hash identically — same node kinds in the same [shape]." So it's a content-addressed hash of the parsed AST shape per function, computed corpus-wide by `collect_corpus_fingerprints` (parallel parse + fingerprint of every file), then `find_duplicate_groups` → `sorted_duplicate_groups` → `grouped_members` bins fingerprints that hash identically into groups of 2+. Groups are sorted largest-group-first, then by node count (`group_sort_key`), so the clones "most worth acting on" surface first.

Two floors keep this from being noise:
- **`MIN_DUPLICATE_NODES = 20`** — functions with fewer AST nodes than this are skipped entirely before fingerprinting; too small to be a meaningful match.
- **Two opt-out filters**, both on by default (`DuplicateFilters`, applied via `duplicate_filters_from`):
  - `exclude_fixture_pairs` (`--include-fixture-pairs` to disable) — drops groups matched by `is_fixture_pair_group`: every member sits under a recognized pass/fail-style directory pair (pass/fail, accept/reject, good/bad — matched as a whole path component so `passthrough/` isn't fooled), at least two distinct tags are represented, and the paths are otherwise identical once the tag is normalized away. This is explicitly there for CERT-C-style `tests/pass/*.c` vs `tests/fail/*.c` fixtures, which are *intentionally* near-identical and not real extraction candidates.
  - `exclude_trivial` (`--include-trivial-duplicates` to disable) — drops groups via `is_trivial_noise_group`: every member's body is ≤`TRIVIAL_BODY_LINE_SPAN` (3) lines *and* the group repeats fewer than `TRIVIAL_MIN_REPEAT` (4) times. The rationale documented on the function: a one-line accessor can clear the 20-node floor purely from type annotations and field-access chains while still being trivial, and — more subtly — per-type accessor glue produced *by fixing* real duplication elsewhere would otherwise reappear as new "unresolved debt."

## What it deliberately misses

Because matching is exact structural-hash equality, it deliberately misses:
- **Near-duplicates** — anything that differs in AST shape at all (renamed intermediate variables don't matter since it's node-kind-based, but a reordered statement, an extra branch, or a different literal type does change the hash). There's no fuzzy/similarity scoring here, only exact grouping.
- **Cross-language duplication** — fingerprinting is per-file AST, so a duplicated algorithm re-implemented in a different grammar can't hash the same.
- Anything under the 20-node floor, and (by default) the two filtered categories above.

## Why it isn't part of the normal analysis pass

`recursive_duplicate_groups` in `src/main.rs` is explicitly gated:

```rust
(ctx.recursive && ctx.find_duplicates).then(|| { ... })
```

Two separate gates, both required:
- **`ctx.recursive`** — a single-file run has no corpus to compare against, so duplicate detection is meaningless outside `--recursive` scans.
- **`ctx.find_duplicates`** — an explicit opt-in flag (`--find-duplicates`) even when scanning recursively. The per-function metrics pass (McCabe, Cognitive, SLOC, etc.) is a linear walk over each function in isolation; duplicate detection is a distinct **corpus-wide** phase — parse every file, fingerprint every function-sized subtree, then group and sort across the whole set — which is a different cost profile and a different question ("is this code repeated elsewhere") from per-function complexity ("is this function itself complex"). Bundling it into the default pass would pay that corpus-wide cost on every run regardless of whether the caller wants duplicate reporting, so it's opt-in and paired with snapshot/diff tooling (`--dump-duplicates`, `--diff-duplicates`) for tracking it over time rather than folding it into the always-on metrics output.

One honest gap: the actual fingerprint algorithm (what exactly "same node kinds in the same shape" normalizes away — e.g. whether identifiers/literals are elided) lives in the external `lang_parsing_substrate` crate, which isn't indexed in this repository, so I can't characterize its normalization rules precisely beyond what the file doc states.
