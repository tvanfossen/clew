This is well documented in the module itself, so the answer is grounded directly in `src/duplicates.rs`.

**What counts as a duplicate**

knots hashes each function's AST subtree via the shared `lang_parsing_substrate::fingerprint` — same node kinds in the same shape, with identifiers and literals stripped out. Two or more functions land in the same group when their structural hashes match exactly (`duplicate_groups`, keyed on `content_hash`). That means it catches:

- **Type-1 clones** — byte-identical bodies.
- **Type-2 clones** — renamed identifiers/changed literals but identical structure.

It does **not** catch **Type-3 near-misses** (e.g. the same logic with one extra statement inserted) — that would require a fuzzy similarity threshold, which the fingerprinting substrate deliberately doesn't provide. There's a separate `byte_diff_percent` (Levenshtein-based) computed *within* an already-matched group, but that's just reporting how far a Type-2 clone has textually drifted from the first member — it isn't used to *discover* near-miss groups that failed to hash-match in the first place.

Two low-value categories are filtered out by default (each has an `--include-*` opt-out):

- **Fixture pairs** — functions living under recognized pass/fail-style directory pairs (`tests/pass` vs `tests/fail`, `good`/`bad`, `valid`/`invalid`, etc.) whose paths are otherwise identical once the tag is stripped. These are intentionally near-identical CERT-C-style test fixtures, not real extraction candidates.
- **Trivial noise** — groups where every member's body is ≤3 lines (getters, one-assert tests, dispatch stubs) *and* the group repeats fewer than 4 times. A getter duplicated 4+ times is judged deliberate copy-paste worth flagging; duplicated twice, it's noise. There's also a hard floor (`MIN_DUPLICATE_NODES = 20`) below which functions aren't fingerprinted at all, since the line-span heuristic alone can't be applied before grouping.

**Why it's a separate pass (`--find-duplicates`), not part of the default `--recursive` run**

Per-function metrics (McCabe, cognitive complexity, SLOC, etc.) fall out "for free" from the single parse each file already gets during the normal analysis walk. Duplicate detection is corpus-wide by nature — a function's fingerprint is meaningless until it's compared against every other function in the corpus — and requires a second, dedicated parse pass to build that fingerprint set. That's a real cost difference (not just a UX choice to reduce output noise), so it's gated behind an explicit flag rather than folded into the default pass.
