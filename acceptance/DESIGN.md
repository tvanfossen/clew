<!-- SPDX-License-Identifier: MIT -->
# Acceptance — schema and grading routine

**PROPOSAL, not yet built.** `docs/CORE_HYPOTHESIS.md` is the claim; this is the instrument
proposed to test it. Nothing from the previous generation was preserved — it was deleted rather
than migrated, because a rubric enumerated bottom-up from what a shell command surfaced is the
anchor this design exists to escape, and keeping it in the tree to "refer to" is how the anchor
reattaches.

## What the instrument has to measure

Both arms can answer every question given unbounded budget. **What differs is where each arm
stops.** An agent retrieves what may invisibly be a subset of the complete answer and reports it
with the confidence of a whole one. So the rubric grades *completeness at the budget the agent
chose to spend*, on three axes: quality, cost, time.

Three consequences drive every decision below.

**A question earns its place by the cost of its COMPLETE answer, not by whether one arm can
answer it.** "Does this repo have a mutex?" is `ctrl-F` for a human and one call for either arm.
Grading there measures nothing.

**A mark earns its place by how it was DERIVED, not by how hard it is.** A component belongs if a
complete answer genuinely contains it. It does not belong because a tool surfaces it — and that
rule cuts identically in both directions, so it also excludes surface marks that exist because a
grep found them.

**Nothing the answering agent sees may hint at the answer.** No response schema, no field list, no
enumerated vocabulary. `CONCURRENCY: NONE | <list>` announces that NONE is on the menu, which is
exactly the inference under test — and it helps the baseline arm *more*, because the index arm
would surface gate state anyway. All structure lives at grading time.

## The schema

```yaml
schema: 1                       # this document's version; a rubric declaring an unknown
                                # schema is REFUSED, not best-effort parsed

target: Mbed-TLS/mbedtls
commit: 068ff080b369adfac81509f9b57b2afabaf82dc5
ref: mbedtls-3.6.7              # human label only; `commit` is authoritative
version: 2.0.0                  # rubric version. REQUIRED — two rubrics in the previous
                                # generation had no version key, so version preflight was
                                # inert on them and nothing said so

ground_truth: |
  Read from the target's own source at the commit above. State here anything that came from
  somewhere else, and why.

judge:
  model: claude-sonnet-4-5-20250929   # A DATED ID, NEVER AN ALIAS. `sonnet` moves under the
                                      # rubric without the pin changing, and "repeatable so
                                      # long as the pin holds" is then false.
  samples_when_weight_at_least: 2     # k=3 on high-weight marks; k=1 below (see Voting)

index:                          # HOW THE INDEX UNDER TEST WAS BUILT, in the rubric, because
                                # marks can ask about things the build changed
  declare:                      # inline; no second file to drift
    preprocessor:
      predefined: [MBEDTLS_THREADING_C, MBEDTLS_THREADING_PTHREAD]
  variant_note: |
    REQUIRED whenever `declare` makes the build differ from what the target ships. Here both
    macros are defined ON so the preprocessor can reach guarded code — the inverse of the
    shipped default. Q3 asks what the shipped default is, so a reader must be told that the
    index and the source disagree on purpose.

questions:
  - id: Q3
    intent: |
      Which hypothesis property this probes. Not shown to any agent — it is the author's
      statement of why the question exists, and it is what a reviewer checks the marks against.
      Here: whether the agent stops at "there are threads" or reaches "nothing runs as shipped".

    prompt: |
      mbedtls ships mutex and thread code. As the library is configured by default, what
      actually runs concurrently, and what protects what?

    marks:
      - text: names MBEDTLS_THREADING_C and MBEDTLS_THREADING_PTHREAD as the gating macros
        type: retrieval
        weight: 1
        evidence: |
          include/mbedtls/mbedtls_config.h:2196, :3787
        refs: [["include/mbedtls/mbedtls_config.h", 2196], ["include/mbedtls/mbedtls_config.h", 3787]]

      - text: >-
          states that both macros are commented out in the shipped config, so a default build
          defines neither
        type: conclusion
        weight: 3
        evidence: |
          Both lines are `//#define`. Verified at the pinned commit.
        refs: [["include/mbedtls/mbedtls_config.h", 2196], ["include/mbedtls/mbedtls_config.h", 3787]]

      - text: concludes that a default build creates no threads at all
        type: conclusion
        weight: 3
        evidence: |
          ssl_pthread_server.c:24 compiles a stub main under
          `#elif !defined(MBEDTLS_THREADING_C) || !defined(MBEDTLS_THREADING_PTHREAD)`.
        refs: [["programs/ssl/ssl_pthread_server.c", 24, 29]]

      - text: every source file containing a thread-creation site
        type: set
        weight: 3
        extract: |
          List every file path the answer names as containing a site where a thread is
          created. Paths only, one per line, exactly as the answer writes them. If it names
          none, reply NONE.
        members:
          - {value: "programs/ssl/ssl_pthread_server.c", evidence: "pthread_create at :277"}
          - {value: "programs/test/benchmark.c", evidence: "_beginthread at :430, Windows-only"}

      - text: >-
          identifies debug_mutex as serialising debug output across the per-connection threads
        type: conclusion
        weight: 2
        evidence: |
          Declared ssl_pthread_server.c:65; locked :73, unlocked :80; init :321, free :483.
        refs: [["programs/ssl/ssl_pthread_server.c", 65], ["programs/ssl/ssl_pthread_server.c", 73, 80]]
```

### Field rules

**No counts are ever written.** A mark's index is its list position and a question's mark count is
the list length. Every written count in the previous generation's history was wrong at some point.

**`type` is DECLARED, never inferred.** The previous generation derived "conceptual" from the
*absence* of symbols and refs, so a backtick decided whether a mark was machine-checkable. Three
values:

| type | meaning |
|---|---|
| `retrieval` | one lookup yields it |
| `conclusion` | reachable only by argument over what was read |
| `set` | a collection whose completeness is the measurement |

**Every question must carry at least one `conclusion` mark.** A question with none is testing
retrieval and is re-authored or dropped. This is checkable because `type` is a field.

**`weight` is importance, not partial credit.** A mark is still binary — hit or miss, no half
points. Score is `Σ(weight × hit) / Σ(weight)`, so it never exceeds 100%. Without weights the
surface rung of a depth ladder dominates by count, which is the failure being escaped.

**`arm_only` is absent by default and enumerated when present** (`baseline` | `index`), with a
required `reason`. An unknown value is REFUSED by name. The previous generation spelled a fence
one way and parsed it another, reported zero fenced marks, and counted them against the wrong arm
— a valid-looking value nobody read.

**`evidence` is inline.** A sibling evidence document lets a mark and its ground truth drift
independently.

## Grading routine

Generation and grading are separate phases. Grading never runs inline, so the grader is never next
to the thing that knows the arm, and a scorer fix never costs a regeneration.

### The judge sees almost nothing

For a `retrieval` or `conclusion` mark, one judge call gets **one mark's text and the anonymised
answer**. Not the arm, not the model, not the transcript, not the other marks, not the evidence,
not the target. It has no codebase access: its question is *"does the answer demonstrate this
item"*, never *"is this item true"*.

Two verdicts, HIT and MISS. No middle: under atomic marks a half point is a refusal to decide
averaged into a headline.

### Set marks are extracted, then scored by script

A `set` mark uses a different prompt shape. The judge is asked to **extract** — *"list every file
path the answer names as containing a thread-creation site"* — and is never told what the correct
set is. The script then computes:

- **recall** = |correct ∩ answered| / |correct| — this *is* the stopping point, measured directly
- **precision** = |correct ∩ answered| / |answered|

**Precision is mandatory, not optional.** Once grading is known to be mechanical, the optimal
strategy for recall alone is to name everything. Both arms are subject to it identically, so it is
not a bias — it removes the incentive to dump.

A set mark scores its weight only when recall is 1.0 and precision is 1.0. Partial recall is
reported per-member and carried in the sidecar, because *which* members an arm reached is the most
informative thing the whole instrument produces.

### Voting

**Measured 2026-08-21: 0 flips in 40 pairs × 3 reps, 0 transport errors in 120 calls** — see
`operational/README.md`. That bounds the per-pair flip rate at ≈≤7.5% at 95% confidence; it does
not show it is zero.

So: **k=3 with majority for marks of weight ≥ 2, k=1 below.** A flip on a weight-3 conclusion mark
costs three points and those are the marks that carry the question. Cheap, targeted, and it makes
the residual tail visible rather than assumed away.

A judge error is **never** a MISS. It is recorded as its own state and `unmarked_pct` is reported
beside every score. Weighing an error 0.0 makes it arithmetically identical to a genuine miss, and
that once converted 102 unruled marks into failures against both arms.

### Prompt symmetry is checked structurally

The two arms' briefs must be byte-identical except for the sentence listing available tools. The
harness diffs them and refuses to run on any other difference. Asymmetry in what an arm is *told*
is a handicap built into the instrument, and "is the baseline arm good enough" is otherwise an
opinion.

## Repeatability requirements

Four things must be pinned, and only the first currently is:

1. the target commit — `preflight_target_revision` refuses on mismatch
2. **the judge model, by dated id** — an alias moves under the rubric silently
3. the scorer version, recorded in every sidecar
4. the question-order seed, recorded with the run

## Deliberately absent

**No response format shown to the answering agent.** See the leak argument above.

**No pairwise arm comparison.** It requires the judge to see both answers, which reintroduces the
comparison the per-mark grading already makes, with a new order-effect to control.

**No falsity veto.** One judge call able to zero a whole question, fed mark texts as established
facts, inverted on a correct answer once already. If a "the answer asserts something false" signal
is wanted later, it is a separate mark type with its own evidence — not a whole-question override.

**No edit/refresh/read question.** Refresh latency is machine-bound and would confound the time
axis with an operational variable. It is measured in `operational/`.

## Open, and needing a ruling

1. **Set-mark scoring is all-or-nothing at weight level.** The alternative — award `weight ×
   recall` — makes the score continuous and reintroduces partial credit by another name. I lean
   all-or-nothing with per-member detail in the sidecar; the counter-argument is that it discards
   the very gradient the instrument was built to see.
2. **`intent` is unenforceable.** It is the field that would catch a mark drifting away from the
   question's purpose, and nothing can check it but a reviewer.
3. **Deleting the previous transcripts removed the free dry-run** — grading a new rubric against
   old answers before spending a run. Those answers respond to different questions, so its value
   was limited, but it is now zero. The first new rubric will be validated only by a paid run
   unless something replaces that step.
