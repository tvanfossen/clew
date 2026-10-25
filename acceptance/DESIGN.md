<!-- SPDX-License-Identifier: MIT -->
# Acceptance — schema and grading routine

**BUILT, AND MEASURING.** `docs/CORE_HYPOTHESIS.md` is the claim; this is the instrument that
tests it. Nothing from the previous generation was preserved — it was deleted rather than
migrated, because a rubric enumerated bottom-up from what a shell command surfaced is the anchor
this design exists to escape, and keeping it in the tree to "refer to" is how the anchor
reattaches.

This said "PROPOSAL, not yet built" through two grids and up to the first published one. A
status line that is wrong in the safe direction still teaches a reader to discount the document.

## What the instrument has to measure

Both arms can answer every question given unbounded budget. **What differs is where each arm
stops.** An agent retrieves what may invisibly be a subset of the complete answer and reports it
with the confidence of a whole one. So the rubric grades *completeness at the budget the agent
chose to spend*, on three axes: quality, cost, time.

Three consequences drive every decision below.

**A question earns its place by the cost of its COMPLETE answer, not by whether one arm can
answer it.** "Does this repo have a mutex?" is `ctrl-F` for a human and one call for either arm.
Grading there measures nothing.

**A SATURATED QUESTION, AND A PREDICTION DRAWN FROM IT.** Measured: an entropic question about
a two-call API idiom scored 100% for BOTH arms, and the baseline reached it in four turns with
three tool calls. Its answer was excellent — it distinguished the two call sites' different
first-call roles, cited the API contract, and independently found a real logging asymmetry.
Nothing was wrong with the marks; the instrument simply had no resolution left on that question.
A second question saturated the same way.

**THE PROPOSED EXPLANATION IS THAT BOTH ANSWERS LIVED IN ONE FILE**, and reading one file is
cheap for either arm — so a question discriminates best where the complete answer is assembled
from places no single read reaches: callers spread across a file, a gate in a config header away
from the code it guards, a failure value's fate at every site that receives it. That is also the
owner's framing of the hypothesis: **multi-file questions are the area where the index should
excel over a source harness.**

**IT IS A PREDICTION, NOT AN ESTABLISHED PROPERTY, AND THIS DOCUMENT SAID OTHERWISE.** An
earlier version stated it as a rule — "if the complete answer lives in one file, the question
cannot discriminate" — on the strength of n=1 over two questions, which cannot separate that
explanation from "those two questions were simply not hard". A gate was then written to fail a
build on it, which would have enforced a guess as policy.

So the number is REPORTED instead: `scripts/rubric_audit.py` prints files-cited per question and
exits 0 on it, and low-spread questions are kept deliberately as the NULL CASE. If single-file
questions saturate and multi-file ones separate, that is a measured result and the check can be
armed then.

**This is not visible to the discrimination gate**, which compares a shallow fixture against a
complete one. Both score high on a saturated question and the gap looks healthy. Saturation shows
up only when two real arms tie at the ceiling, so **report per-question arm separation after every
run** and treat a tie at the top as a question to replace rather than a result to average in.

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

**A `set` mark's members must have CANONICAL SPELLINGS** — file paths, symbol names, macro
names, directory names, numbers. Members are compared on a normalised key built for exactly
those, so a prose-valued member grades phrasing instead of knowledge: an answer saying
"definitive" does not match a member spelled "definitive for the scope". A collection whose
items have no canonical spelling belongs in a `conclusion` mark, where the judge handles wording
and the schema does not pretend to.

## Grading routine

Generation and grading are separate phases. Grading never runs inline, so the grader is never next
to the thing that knows the arm, and a scorer fix never costs a regeneration.

### The judge sees almost nothing

For a `retrieval` or `conclusion` mark, one judge call gets **one mark's text and the anonymised
answer**. The PROMPT carries no arm, model, transcript, other marks, evidence or target, and the
judge has no codebase access: its question is *"does the answer demonstrate this item"*, never
*"is this item true"*.

**THE ANSWER TEXT IDENTIFIES THE ARM ANYWAY, AND AN EARLIER VERSION OF THIS SECTION CLAIMED
OTHERWISE.** Measured on the 1.1.0 grid after `anonymise` had run: the word "index" survives in
30 of 30 `index_only` answers against 3 of 30 baseline answers, so a judge could name the arm at
roughly 95% accuracy. Two of `anonymise`'s three substitutions are inert — the `mcp__` rewrite
fired on none of 144 answers, and the header strip matches a header the answers do not carry.

This is NOT fixed by scrubbing harder: deleting "index" from an answer edits the evidence the
judge is grading. It is reported instead, with its direction. The index arm's characteristic
prose — "no shell", "cannot read", "the index does not hold" — appears in 20 of 48 of its answers
against 2 of 48 baseline, and that hedging is what a completeness rubric reads as a miss, so the
leak plausibly costs the index arm points rather than winning it any.

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

**Precision is not earned by silence.** An answer that names *nothing* has an empty prediction
set, so it has nothing spurious in it and would score clean — a decision satisfiable by saying
nothing, which is the failure this whole design forbids. Precision requires at least one named
item. Found by the discrimination check rather than by review: a deliberately shallow answer
named zero directories, missed every member, and still won the decision.

**THIS DOCUMENT DESCRIBED A SCORER THAT WAS NEVER BUILT, over a quarter of the run's weight.** It
said a set mark scores its weight only when recall and precision are both 1.0. `score_set` emits
**one decision per member plus one for precision, each at the mark's full weight** — partial
credit, so a weight-2 mark with three members contributes eight weight units, and set decisions
carry **24% of all weight** in a grid. `score.py`'s own module docstring has always documented the
real behaviour; this section did not, which is why the contradiction survived two runs.

The code is left alone and the description corrected: per-member credit is what the instrument
measures, and *which* members an arm reached is the most informative thing it produces. Open
ruling 1 below is therefore already decided in practice, by the scorer rather than by a ruling.

### Voting

**Measured 2026-08-21: 0 flips in 40 pairs × 3 reps, 0 transport errors in 120 calls** — see
`operational/README.md`. That bounds the per-pair flip rate at ≈≤7.5% at 95% confidence; it does
not show it is zero.

So: **k=3 with majority for marks of weight ≥ 2, k=1 below.** A flip on a weight-3 conclusion mark
costs three points and those are the marks that carry the question. Cheap, targeted, and it makes
the residual tail visible rather than assumed away.

A judge error is recorded as its own state and `unmarked_pct` is reported beside every score.

**BUT IT IS ARITHMETICALLY A MISS, AND THIS SECTION CLAIMED IT WAS NOT.** `QuestionResult.score`
puts unruled weight in the DENOMINATOR and leaves it out of the numerator, so an unruled decision
costs exactly what a miss costs. Measured on the 1.1.0 grid: four cells published
`score = 0.000` with `unmarked_pct = 1.000`, every decision reading `rc=1 after 4 attempt(s)`
with `duration_api_ms: 0` — a judge that never reached the server, published as answer quality.

`unmarked_pct` is therefore a WARNING a reader must act on, not a correction the arithmetic has
already applied. Any cell above a few percent unruled is unusable, and a reporting surface that
quotes a score without it is quoting half.

### Prompt symmetry is checked structurally

The two arms' briefs must be byte-identical except for the sentence listing available tools. The
harness diffs them and refuses to run on any other difference. Asymmetry in what an arm is *told*
is a handicap built into the instrument, and "is the baseline arm good enough" is otherwise an
opinion.

## Running a grid

One command drives every target through provision → generate → grade → report:

```bash
.venv/bin/python -m acceptance.matrix --out acceptance/runs/<date>-n3 --models sonnet --replicates 3 --seed 7
```

**Do not run the four phases per target by hand.** That is sixteen commands carrying their own
paths, and every path defect this harness has shipped came from that sequence — a relative
`--mcp-config` the agent could not resolve, a `--repo` naming the wrong tree, and a build that
inherited the operator's own `CLEW_STATE_HOME` and overwrote their personal index. None were
logic errors. The driver derives every path from `--out` plus the target's directory name, so
the directory generation writes and the directory grading reads are the same expression.

**Pre-flight first.** `--provision-only` fetches every target at its pin, builds each index under
its own isolated state root, verifies the declaration reached `build_meta`, writes the MCP config
and probes that the index tools actually register — then stops without spending a single agent
call. Provisioning is where a grid fails cheaply; every one of those failures is worth finding
before a weekend of generation rather than on cell 40 of 120.

Verified end to end rather than only in tests: driving a real provision produced a checkout at
the pin, an index with the same row counts as the previous run, and an MCP config naming the
run's OWN checkout and state root — the two paths whose earlier divergence produced an index arm
with no index, and a build that overwrote the operator's personal database.

A target that refuses is recorded by NAME and PHASE and the rest of the grid still runs; the
exit code is the number of failed targets. Generation runs for every target before any target
grades, so a stop midway leaves whole targets ungenerated — a gap a reader can see — rather than
every target half-graded.

The single phases remain available (`plan`, `generate`, `grade`, `report`) for re-grading a
finished run, which is cheap and re-runnable in a way generation is not. `report` takes an
optional `--rubric`; with it, the separation table carries files-cited per question.

**Grading is additive.** `<stem>.grade.json` holds the latest pass and `<stem>.grades.jsonl`
holds every pass, appended, with each line carrying its own rubric digest. Regrading used to
overwrite: one measured regrade moved a cell by 12.1 points and which marks flipped was
unrecoverable, because the second pass had eaten the first. With two or more passes at the
current digest, `report` prints the spread and NAMES the marks that moved.

**The noise floor is unmeasured**, and one regrade of five cells is not a measurement of it —
that pass spread from −12.1pt to +10.0pt, which is wide enough that a per-question delta inside
it says nothing. Two things are worth knowing before reading any grid: run `grade` more than
once on the same answers to get a floor, and treat a separation smaller than that floor as
unresolved rather than as a result.

## Repeatability requirements

Five things must be pinned, and the fifth was missing from this list as well as from the
artifacts:

1. the target commit — `check_revision` refuses on mismatch, and on a dirty tree
2. **the judge model, by dated id** — an alias moves under the rubric silently. Every shipped
   rubric pins one, and `grader/rubric.py` REFUSES a value that looks like an alias
3. the scorer version — `grader_fingerprint`, a hash of every file under `grader/`, in every
   sidecar
4. the question-order seed, recorded in `run.json`
5. **the clew under test** — and this list omitted it, which is how a grid came to record every
   input to the measurement and nothing about its subject. `acceptance/identity.py` now stamps
   the clew version, commit, dirty flag and build version into `run.json` and `provision.json`.

   The field that matters most there is **`substrate_languages`, not `substrate_version`**. The
   five configuration grammars 1.1.0 reads live in a fork whose wheel reports the same version
   string as the published one, so the version cannot say which wheel answered. The compiled-in
   key set can.

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
