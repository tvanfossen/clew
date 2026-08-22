<!-- SPDX-License-Identifier: MIT -->
# Rubric discrimination — does a shallow answer score badly?

**Not an arm simulation, and not a prediction of any run's numbers.** The answers here were
written by the same party that authored the marks, so they are a biased stand-in for either arm
and their scores say nothing about how a real agent would do.

What they test is narrower and load-bearing: **do the marks SEPARATE?** A deliberately shallow
answer that scores well means the marks are wrong — and learning that here costs judge calls,
where learning it from a paid run costs the run.

This is what replaces the free dry-run that the 002 overhaul removed. The previous generation's
transcripts could have been graded with a new rubric before spending anything; they were deleted,
and nothing else recovers that step.

## The pair

`Q1_shallow_*` stops at the surface rung — it names the gating macros, finds the pthread server,
names `handle_ssl_connection` and `debug_mutex`, and concludes mbedtls runs a thread per TLS
connection. Everything in it is TRUE about the lines it found. It is wrong about the repository.

`Q1_complete_*` reaches the conclusion: as shipped, both macros are commented out, the example
compiles to a stub `main`, and nothing runs concurrently at all.

## Result — mbedtls Q1

| answer | score | unmarked |
|---|---:|---:|
| complete | **100.0%** | 0.0% |
| shallow | **35.0%** | 0.0% |

Sixty-five points of separation on an answer whose every sentence is factually true. That is the
instrument doing its job: the shallow answer is not penalised for being wrong, it is penalised
for **stopping**.

## What the first run found, which is why it was worth running

The first run separated 100% / 50%. The mark fix below took the shallow answer to 35% and left
the complete one at 100% — **the correction moved only the answer it should have moved**, which
is the control on the fix as well as on the mark.

The shallow answer **HIT** a weight-3 conclusion mark it should have missed. The mark read
*"places every thread-creation site outside `library/`"*; the shallow answer named ONE site and
mentioned `library/threading.c` in passing, never establishing "every" — and the judge could read
the claim as implied.

**A mark satisfiable by a weaker claim than it states measures nothing.** It now requires both
halves of a contrast — that nothing in `library/` creates a thread AND that `library/`
nonetheless supplies the mutex abstraction — which cannot be satisfied by mentioning one site.
Completeness of the site list is measured by the set mark, where it belongs.

## An observation, not a defect

The `set_precision` decision is nearly free for any answer that does not hallucinate. The shallow
answer named one of two correct files, so its precision was 1/1 and it won that decision. That is
correct behaviour — precision measures false positives, and under-naming is the recall side's job,
which duly failed it. But it does mean a set mark's `+1` precision decision inflates a lazy
answer's score slightly, and a reader comparing set-heavy questions to conclusion-heavy ones
should know it.

## Re-run it whenever a rubric changes

```
.venv/bin/python -m acceptance grade \
    --rubric acceptance/targets/<target>/questions.yaml \
    --answers acceptance/operational/rubric-discrimination/<target>
```

A rubric edit that closes the gap between the two answers has made the instrument worse, and this
is the cheapest place to see it.
