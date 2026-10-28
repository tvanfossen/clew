<!-- SPDX-License-Identifier: MIT -->

# Known defects in this run

What is wrong with the measurement on this page, written by the party whose tool it flatters.
`RESULTS.md` carries the numbers; this carries the reasons to distrust them. Nothing here is
fixed in those numbers — `PRE-REGISTRATION.md` forbids a grader change once numbers exist, so
each of these is fixed for the NEXT run.

## 1. The quality gain is not attributable to clew alone — THE LARGEST CAVEAT

+12.34 pt on `index_only` is measured across a GRADER CHANGE. `5b14197` fixed a deterministic
`_key` bug that punished answers citing `path:line`, which is the citation style a code index
encourages — so the bug was asymmetric *against* the arm under test. Some unknown share of the
gain is the instrument no longer penalising clew.

**Resolving it** needs a held grader across two runs, which 1.3.0 can do now that the grader is
stable. This run could not: 16 code paths and the grader moved together.

## 2. k=3 voting is nullified by the verdict cache

`judge.py:570` computes the prompt once outside the sample loop; `ask()` is keyed on
`sha256(model + prompt)`, so samples 2 and 3 of every mark replay sample 1.

```
recorded judge samples   3,294
distinct cache entries   1,239
split decisions          0 / 1,098 voted      (1.1.0, pre-cache: 146 / 936 = 15.6%)
```

A 0.0% split rate is not a consistent judge; it is a vote that never happened. Both halves
shipped in `5b14197` — k=3 was raised *because* 12.7% of the grid's weight rested on single
calls, and the cache put it back.

**Consequence for these numbers:** every verdict is a valid single sample. None is voted. The
split rate pre-registered as this run's only noise indicator measures nothing, so the run has
**no** usable noise indicator at all.

**Fix for next run:** vary the prompt per sample, or key the cache on `(prompt, model, sample
index)`. Either restores k=3; the second keeps replay exact.

## 3. No noise floor

One grading pass, by ruling. A floor needs a second pass with `--no-judge-cache` — with the cache
on, pass two replays pass one and reports a floor of zero. 1.1.0's 8.95 pt is **not** reused: it
was measured through the buggy grader. The SD and SEM in `RESULTS.md` are cluster-to-cluster
variation and must not be read as judge variance.

## 4. The tree was dirty when the grid ran

`clew_dirty: true` at commit `844fee55`. The uncommitted change was the `_grade_line` fix
(defect 5), confined to `acceptance/__main__.py`, outside the fingerprinted directory, with
`grader_fingerprint` verified unmoved at `5489758d9a50`. A reader resolving that sha still does
not get the exact tree that ran.

**Fix for next run:** refuse to generate from a dirty tree, or record the diff.

## 5. A `None` score crashed grading 90 cells in

`QuestionResult.score()` returns `float | None`; None means nothing was ruled. The progress line
formatted it with `:6.1%` and killed `self`'s grading phase. The sidecar is written before that
line, so no score was lost. Fixed mid-run; it now prints `UNRULED`, never `0.0%`.

**What it says about the harness:** a scoring type changed and a formatter did not, because the
formatter was inline in a closure and unreachable from a test. It is now a tested function.

## 6. Both model ids float

`modelpin.floats()` is True for `claude-haiku-5-5` and `claude-sonnet-5-5` — no dated form
exists for the current families. A replay months from now may not answer or judge from the same
weights, and nothing in the record would say so.

## 7. The judge shares a vendor with the answering model

Sonnet 5.5 judges Haiku 5.5, so they are not the same weights — correlated error is REDUCED from
the same-model case. It is not removed: shared pretraining lineage means a judge can rule `hit`
on an answer wrong in the way the judge is also wrong. That lifts both arms and compresses the
separation toward zero, which makes clew's deficit read smaller. **The residual points in clew's
favour and this run cannot measure it.**

## 8. Four clusters regressed and are not explained

self Q2 (−20.63), entropic Q2 (−20.51), self Q4 (−16.09), self Q5 (−13.58). They are published
in the per-cluster table rather than absorbed into the mean. No root cause was investigated
before publication; doing so first would have meant reading the results and then deciding what
to say about them.

## 9. The grid is 16 clusters

SEM 3.87 pt on `index_only`. Widening to the three authored-but-unrun targets (knots, freertos,
zephyr) would take it to 25 clusters. Deferred by the owner; riot stays out because doxygen
exits 2 on it and **a provisioning failure is not a score of zero**.

## 10. `--skills` was not passed, deliberately

`SKILLS.md` did not exist when the 1.1.0 cells were generated — `--skills` landed a day later.
Passing it would have made this a different experiment. The usage document's effect is measured
separately in `acceptance/runs/2026-10-20-skills-ab/`.
