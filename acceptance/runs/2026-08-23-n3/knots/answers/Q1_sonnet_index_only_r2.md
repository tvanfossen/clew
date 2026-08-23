I have enough to answer this fully from the index.

## What counts as a duplicate

Detection is entirely structural, not textual or semantic. `find_duplicate_groups` (`src/duplicates.rs:100`) groups functions by identical AST structural hash — from the file doc: "Two functions group together when their AST subtrees hash identically — same node kinds in the same [shape]." This is computed by `lang_parsing_substrate::function_fingerprints` (an external crate the index can't see the internals of) during `extract_file_fingerprints` (`src/main.rs:1703`), called per-file with a floor of `MIN_DUPLICATE_NODES = 20` AST nodes (`src/duplicates.rs:28`) — bodies smaller than that are never fingerprinted at all, so they can't form a group regardless of how identical they are.

A group is 2+ members sharing that hash. Groups are sorted largest-group-first, then by node count (`group_sort_key`), so the clones most worth acting on surface first.

## What it deliberately excludes

Two filters run after raw grouping, both on by default (`DuplicateFilters`, negated from `--include-fixture-pairs` / `--include-trivial-duplicates` in `duplicate_filters_from`):

- **Fixture pairs** (`is_fixture_pair_group`): every member sits under a recognized pass/fail-style fixture directory, at least two distinct tags are present, and the paths are identical once the tag is normalized away. This is explicitly there to auto-exclude CERT-C-style `tests/pass/*.c` vs `tests/fail/*.c` fixtures, which are intentionally near-identical by design — not extraction candidates.
- **Trivial noise** (`is_trivial_noise_group`): every member's body is ≤ `TRIVIAL_BODY_LINE_SPAN` lines (a getter, a one-`assert_eq!` test, a dispatch stub) *and* the group doesn't repeat often enough (`TRIVIAL_MIN_REPEAT`) to look like deliberate copy-paste. The node-count floor alone doesn't catch these because a one-line accessor can clear 20 AST nodes purely from type annotations and field-access chains. Notably, the doc comment flags a self-referential risk: post-refactor, the unavoidable per-type accessor glue produced *by fixing real duplication* would otherwise show up as new "duplicate" groups, misreading as unresolved debt.

Both exclusion counts are preserved in `DuplicateGroupsResult` (`excluded_fixture_pairs`, `excluded_trivial`) rather than silently dropped, so a report can say how much was filtered and why.

What the mechanism structurally can't catch, since the index confirms hashing is purely AST-shape: renamed variables/fields don't break a match (that's the point), but any semantic-but-differently-structured duplicate — reordered independent statements, an equivalent loop written a different way, a duplicate spread across two different node shapes — falls outside "identical hash" and is missed. The index has no visibility into `lang_parsing_substrate::fingerprint`'s exact hash inputs (it's an external crate), so I can't say precisely which token-level details (literal values, comments, whitespace) do or don't factor in — that would need reading that crate's source directly, which is outside what the index can answer.

## Why it's a separate pass, not part of normal analysis

`recursive_duplicate_groups` (`src/main.rs:1530`) is gated behind **both** `ctx.find_duplicates` (the `--find-duplicates` flag) and `ctx.recursive`. The doc comment states the reason for the second condition plainly: "a single file has no corpus to compare against" — duplicate detection is inherently corpus-wide, comparing every function against every other function across the whole recursive walk, which is a different shape of work than per-file metric computation (`collect_all_metrics`, run unconditionally). `collect_corpus_fingerprints` parses and fingerprints every file in parallel (`par_iter`) as an explicit "Phase 1," separate from the metrics pass, silently skipping unreadable/unparseable files (deliberately not warning again since the metrics pass already does). That two-phase, corpus-scale structure — plus the fact it produces a fundamentally different kind of report (cross-file groups, not per-function scores) — is why it's opt-in via its own flag rather than folded into the standard metrics output.
