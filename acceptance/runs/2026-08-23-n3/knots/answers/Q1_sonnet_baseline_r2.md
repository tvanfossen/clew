I have enough now to answer directly from what's in the file.

## What counts as a duplicate

Two functions land in the same group when their **AST subtree hashes match exactly** (`lang_parsing_substrate::fingerprint` / `duplicate_groups`) — same node kinds, same shape, all the way down, *ignoring* identifier names and literal values. That's classic **Type-1 (byte-identical) and Type-2 (renamed-identifier) clone detection**. Two functions with completely different variable/parameter names and different string/number literals still hash identically if the control-flow and expression structure is the same.

Every group gets a stable content-derived `group_id` (a hash of the shared shape, not a positional index), so two runs of the tool can be diffed and you can tell "this specific duplicated shape shrank from 4 members to 2" rather than just "group #3 changed" — group numbers reshuffle as files come and go, the shape hash doesn't.

On top of the raw grouping there are two **default noise filters** (both opt-out via CLI flags):
- **Fixture pairs** (`is_fixture_pair_group`): if every member sits under a recognized pass/fail-style directory pair (`pass`/`fail`, `compliant`/`noncompliant`, `good`/`bad`, `accept`/`reject`, `valid`/`invalid`), at least two distinct tags are represented, and the paths are identical once the tag is stripped out — that's a CERT-C-style test fixture pair that's *intentionally* near-identical, not extraction debt. Two genuine duplicates that both happen to live under `tests/pass/` are **not** caught by this (needs a cross-pair, not two same-tag files).
- **Trivial noise** (`is_trivial_noise_group`): every member's body is ≤3 lines AND the group has fewer than 4 members. A getter duplicated across only two files reads as boilerplate, not debt; the same getter duplicated across 4+ files is kept, on the theory that's likely deliberate copy-paste worth a shared trait. There's also a hard floor of 20 AST nodes below which single-line bodies aren't compared at all.

Each member also gets an optional `diff_from_first` — a Levenshtein-based byte-diff percentage against the group's first member — so you can tell a byte-identical clone (0%) from a renamed-but-structurally-identical one, capped at 20,000 characters per body because O(n·m) edit distance on multi-page functions isn't worth the wait.

## What it deliberately misses

**Type-3 near-miss clones** — the same logic with one extra statement, a reordered check, an inserted log line — are explicitly out of scope. The module comment says this outright: that would need a fuzzy similarity threshold, and "the substrate deliberately doesn't provide" one. This is a structural-hash-equality tool, not a similarity-scoring one; anything that doesn't hash identically is invisible to it, no matter how obviously copy-pasted-and-tweaked it looks to a human.

## Why it's a separate pass, not part of normal analysis

Per-function metrics (McCabe, cognitive, SLOC, etc.) fall out of the single per-file parse `--recursive` already does — free by-product of the pass that's happening anyway. Duplicate detection needs something categorically different: a **second, corpus-wide parse** to build structural fingerprints for every function, then compare all of them against each other — corpus-wide grouping, not a per-function property computed independently. That's real extra cost (full re-parse + hashing across the whole tree), so it's deliberately gated behind `--find-duplicates` rather than folded into the default pass. Note it's also gated to require `--recursive` (`recursive_duplicate_groups` only runs when both `ctx.recursive && ctx.find_duplicates`), consistent with it being a whole-corpus operation, not something that makes sense against a single file.
