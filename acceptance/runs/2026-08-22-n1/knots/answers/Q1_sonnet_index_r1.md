I now have the complete picture — I'll write the answer from what's grounded in the code.

## What counts as a duplicate

knots runs a separate, opt-in pass (`--find-duplicates`) that parses the corpus a second time and computes a **structural fingerprint** of every function-like subtree (`lang-parsing-substrate::function_fingerprints`). The fingerprint is a hash built from a pre-order walk that folds in each node's `kind()` and `child_count()` — the *shape* of the AST, not its text. Two functions land in the same group when their hashes match exactly (`duplicate_groups` in the substrate, wired through `find_duplicate_groups` in `src/duplicates.rs`).

Because identifiers and literals are never hashed, this catches:
- **Type-1 clones** — byte-identical functions (fall out for free, since identical text obviously has identical structure)
- **Type-2 clones** — renamed identifiers, changed constants/literals, but the same control-flow skeleton

One deliberate exception: the node's own **declared return type text** is folded in (not descendants' types — just the top-level node being hashed). This was added after a real false positive on an ~11k-function corpus, where two functions with the identical "build accumulator, delegate, return" skeleton but different return types (`-> Vec<String>` vs `-> Vec<RuleViolation>`) hashed identically, since `type_identifier` is the same *kind* regardless of which name it holds. Parameter and variable names stay ignored.

Grouping only fires on **exact hash equality**, and the pass filters out low-value noise before reporting:
- `MIN_DUPLICATE_NODES = 20` — subtrees smaller than this are dropped outright.
- Trivial-noise groups — every member's body is ≤3 lines *and* fewer than 4 members repeat it. A one-line accessor can clear the 20-node floor purely from type annotations and field-access chains, so the node-count floor alone doesn't catch it; this second heuristic does, unless it repeats 4+ times (at which point it reads as deliberate copy-paste worth a shared trait, not incidental overlap).
- Fixture pairs — groups where every member sits under a recognized pass/fail-style directory pair (`pass`/`fail`, `compliant`/`noncompliant`, `good`/`bad`, `accept`/`reject`, `valid`/`invalid`) and the paths are otherwise identical once the tag is normalized away. This exists specifically for CERT-C-style `tests/pass/CWE-190.c` vs `tests/fail/CWE-190.c` fixtures, which are intentionally near-identical and not extraction candidates.

Both filters are opt-out (`--include-fixture-pairs`, `--include-trivial-duplicates`), and groups are sorted largest-group-first then by node count so the highest-value clones surface first. Each group also gets a stable, content-derived `group_id` (a hex tag off the shared hash) rather than positional numbering, specifically so `--dump-duplicates`/`--diff-duplicates` can track "did this group shrink or vanish" across a refactor without being thrown off by files being added/removed elsewhere in the corpus.

## What it deliberately misses

- **Type-3 near-miss clones** — a function with one extra statement, a reordered check, an added guard clause — don't match, because there's no fuzzy/similarity threshold, only exact hash equality. The substrate's module doc is explicit that this is a deliberate scope boundary: fuzzy matching is left as a consumer concern, not something the primitive provides.
- **Nested functions/closures** are fingerprinted twice — once as part of the enclosing function's subtree, once independently — matching the crate's existing call-graph walk behavior of not stopping at function boundaries. That means a duplicate can show up at two granularities simultaneously rather than being deduplicated across levels.
- Sub-20-node functions and small-body/low-repeat groups are filtered by default, so genuinely duplicated tiny helpers (a 2-line duplicated getter) won't show up unless you pass `--include-trivial-duplicates`.

## Why it isn't part of the normal analysis pass

Stated directly in `duplicates.rs`'s file doc: per-function metrics (McCabe, cognitive, SLOC, ABC, etc.) come for free from the single parse `--recursive` already does per file. Duplicate detection is fundamentally different in scope — it's **corpus-wide** (a function isn't "duplicate" relative to anything in isolation, only relative to every other function across every other file) and requires re-parsing every file specifically to build fingerprints, which the normal per-file metrics walk has no reason to do. It's also only meaningful with `--recursive` in the first place — `recursive_duplicate_groups` gates on `ctx.recursive && ctx.find_duplicates` because a single file has no corpus to compare itself against. Bundling that second full-corpus parse into the default pass would tax every run of knots (including single-file and non-duplicate-interested runs) for a feature most invocations don't want, so it's kept as an explicit, separately-costed opt-in.
