This is well-documented directly in the source, so the answer is grounded in `src/duplicates.rs`.

**What counts as a duplicate**

Two functions are grouped as duplicates when their AST subtrees hash identically — same node kinds in the same shape, via the substrate's structural fingerprinting (`lang_parsing_substrate::fingerprint` / `duplicate_groups`). This is deliberately text-blind: identifier names, literals, and formatting don't matter, only tree shape. That means it catches:

- **Type‑1 clones** — byte-identical bodies
- **Type‑2 clones** — renamed identifiers/literals but structurally identical

Groups are sorted largest-group-first, then by node count, so the highest-value clusters surface first. Each member also gets a `content_hash`-derived `group_id` that's stable across runs (so you can diff "did this clone shrink after refactoring" between two reports), and optionally a Levenshtein-based `byte_diff_percent` against the group's first member, capped at bodies under `MAX_DIFF_CHARS` (20,000 chars) for cost reasons.

Two filters strip out low-value noise before reporting (both on by default, opt-out via CLI flags):
- **Fixture pairs** — groups where members sit under matched `pass`/`fail`-style (or `compliant`/`noncompliant`, `good`/`bad`, `accept`/`reject`, `valid`/`invalid`) directory pairs with otherwise-identical paths — the classic CERT-C `tests/pass/CWE-190.c` vs `tests/fail/CWE-190.c` case, intentionally near-identical by design, not a real extraction candidate.
- **Trivial noise** — groups where every member's body is ≤3 lines (getters, one-assert tests, dispatch stubs) *and* the group repeats fewer than 4 times. A one-line accessor can still clear the 20-AST-node floor purely from type annotations/field-access chains, so node count alone doesn't filter it; line span does. Repeat ≥4 times and it's kept anyway, on the theory that's likely deliberate copy-paste worth a shared trait.

There's also a hard floor: functions under 20 AST nodes are skipped entirely regardless of grouping, since two single-line getters hashing alike isn't meaningful.

**What it deliberately misses**

**Type‑3 near-miss clones** — functions that are almost the same shape but differ by an extra statement, a reordered branch, an inserted guard, etc. The doc comment is explicit: this would require "a fuzzy similarity threshold the substrate deliberately doesn't provide." The design commits to exact structural-hash equality only, no fuzzy/similarity scoring.

**Why it's not part of the normal analysis pass**

Gated behind `--find-duplicates` rather than folded into the default `--recursive` run, for a cost reason: the per-function metrics (McCabe, cognitive complexity, SLOC, etc.) come for free from the single parse pass main.rs already does per file. Duplicate detection is corpus-wide by nature — it has to fingerprint and compare every function against every other function across the whole codebase — and requires a second parse of every file to build that corpus fingerprint. That's a materially different cost profile (O(corpus) vs. O(single file)), so it's opt-in rather than bundled into the default pass.
