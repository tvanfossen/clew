## What determines a function's AIRD score

AIRD is computed by `calculate_aird` in `src/complexity.rs:1433`, a pure function of six already-computed metrics for that function:

```
raw = 55·norm(cognitive, /75) + 15·norm(sloc, /200) + 15·norm(nesting, /8)
      + 15·norm(test_score, /20) − 15·norm(doc_score, /10) + 10·norm(state_coupling, /12)

aird = round(clamp(raw, 0, 100))
```

- **cognitive** (55% weight, the dominant driver) — cognitive complexity of the function
- **sloc** (15%) — source lines, a proxy for context-window burden
- **nesting** (15%) — max nesting depth
- **test_score** (15%) — from `calculate_test_scoring`, an iteration-cost proxy
- **doc_score** (15%, subtracted) — documentation reduces the score
- **state_coupling** (10%) — coupling to the function's own struct/class fields

All six inputs come from pure tree-sitter AST traversals over that one function's syntax subtree — `calculate_cognitive_complexity`, `calculate_sloc`/language variant, `calculate_nesting_depth`, `calculate_test_scoring`, `calculate_state_coupling` — with no I/O, no randomness, no timestamps. `collect_function_metrics` (`src/lib.rs:891`) computes each of these and calls `calculate_aird` inline, once per function, in a single deterministic pass over the parse tree.

**But there's a second stage that isn't purely local to the function.** `apply_file_ce_to_aird` (`src/coupling.rs:162`) runs as a post-pass, *only in `--recursive` mode*, after the corpus-wide import graph is built. It looks up the file's efferent coupling (Ce — how many other corpus-internal files that file imports), computes a multiplier via `aird_file_ce_multiplier` (up to `AIRD_FILE_CE_MAX_BONUS`, capped at a 20% bump per the variable's brief), and rescales the already-computed AIRD, re-clamping to 0–100. So the *first* AIRD value is per-function and local; the *final, reported* AIRD is per-function-in-context-of-its-corpus.

## Would the same function score the same across two runs?

Yes, deterministically, **provided the run conditions are identical**:
- same source text for that function (unchanged bytes → identical AST → identical metric inputs),
- same knots version (weights/caps are hardcoded constants — `AIRD_FILE_CE_CAP`, `AIRD_FILE_CE_MAX_BONUS`, the 55/15/15/15/15/10 weights — so a version bump to these would change the score even for byte-identical code),
- and, critically, **the same corpus scope**. Because of the file-Ce fold-in, a function's final AIRD is not purely a property of the function's own text — it also depends on the efferent coupling of the file it lives in, computed from *the whole indexed corpus's* import graph. Run the tool on the file standalone vs. as part of `--recursive` on the full repo, or add/remove other files in the corpus that change that file's Ce, and the same unchanged function can get a different final AIRD even though its own cognitive/sloc/nesting/test/doc/coupling terms didn't move.

So: deterministic and reproducible in the narrow, single-file sense; not guaranteed identical if the corpus around it changes, because the Ce multiplier is a corpus-relative adjustment layered on top of a per-function base score. The index can't tell me the exact numeric bound the multiplier can reach (`AIRD_FILE_CE_MAX_BONUS`'s value wasn't returned as a literal, only its brief saying "capped at 20%") — worth confirming by reading `src/complexity.rs` directly if the exact cap value matters.
