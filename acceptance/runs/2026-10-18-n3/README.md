<!-- SPDX-License-Identifier: MIT -->
# 2026-10-18-n3 — INSTRUMENT VALIDATION, not a published result

**Owner ruling, 2026-10-19:** *"we treat the initial runs already performed as baselining to
improve the test matrix quality so that it performs accurately and honestly."*

These cells were generated against a clew that **did not ship**. Between this run and 1.1.0:

- `lang-parsing-substrate` moved from a locally built fork to published **0.12.0**;
- `macro_refs` stopped resolving a caller by bare name across the whole index (PR #55) — a
  correctness fix that changes `ast` macro-reference rows on every target, 13,693 of them in
  this run's own mbedtls index, in a tree holding 121 functions named `main`;
- `chunk_markdown` moved from a regex to the grammar's own section list, changing prose chunks.

So no score here describes 1.1.0, and none may be quoted as one. The formal 1.1.0 baseline is a
separate run directory.

## What this run DID establish, which is why it is kept

It was the instrument's first real exercise, and it found four defects in the instrument rather
than in the tool:

1. **An asymmetric brief.** `index_only` was told *"an honest gap is the useful answer here"*
   while `baseline` was told nothing of the kind, on a rubric that scores COMPLETENESS.
   `check_symmetry` structurally cannot see this: it verifies that the tool sentence is the only
   line that differs, never that the sentences license the same behaviour.
2. **A blindness check watching an arm the grid does not run.** `arm == "index"` while `ARMS` was
   ("baseline", "index_only"), so the one signal that an index arm answered without its index was
   dead for the compared pair.
3. **Grading that could not finish.** No notion of an already-graded cell, so each capacity
   window re-graded its own start and advanced the frontier about seven cells. Two of three
   targets were unreachable.
4. **A retry policy that waited minutes on calls that failed in zero milliseconds**, converting
   12.2% of one target's decisions into holes attributed to the answers.

It also produced one result worth carrying forward as a hypothesis to re-test, NOT as a number:
on entropic — uncontaminated, clean at 0.0% unmarked — `index_only` scored **-17.4pt** against
baseline over 15 pairs while costing 15% less wall time and 26% fewer output tokens. The index
arm was cheaper AND less complete. If that survives on shipped code it is the finding that
matters, because it is a reply-completeness problem rather than a retrieval-coverage one.

## Contents

- `PRE-REGISTRATION.md` — the criterion, committed before any cell existed, plus Amendment 1.
  It governs the FORMAL run too; the criterion did not change when the code did.
- `<target>/answers/` — 144 generated cells, entropic fully graded, mbedtls 6 cells, self none.
- `mbedtls/answers-superseded-two-arm/` — an earlier TWO-ARM instrument, archived with its own
  README. Nested supersession, deliberately: each layer says what it measured.
- `provision.json` per target — clew commit, build version and `substrate_languages`, which is
  the only field that distinguishes the fork from published 0.11.2.
