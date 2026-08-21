<!-- SPDX-License-Identifier: MIT -->
# Operational viability — measured, and deliberately NOT in the matrix

These measurements do not test the core hypothesis. They establish whether its **operational
preconditions** hold in practice. They live here, beside the matrix, and never inside it.

`docs/CORE_HYPOTHESIS.md` is the claim. `acceptance/targets/` is the instrument that tests it.
This directory holds everything that has to be true for the instrument's configuration to
resemble how anyone actually uses the tool.

## Why these are separate

**They are machine-bound.** Build and refresh times are a property of the hardware, not of the
retrieval claim. A potato is not a Threadripper, and a figure without a stated machine is not a
measurement.

**Putting them in the matrix would confound the time axis.** A slow refresh would cost the index
arm on wall-clock for a reason that has nothing to do with whether a lookup beats a read. The
arms would then differ on an operational variable and a retrieval variable at once, and no
single number could separate them.

**They test preconditions, not the claim.** "Does an index help a model answer?" and "is the
index cheap enough to keep current?" are different questions with different failure modes. An
LSP pays a re-parse delay too, and nobody treats that as a refutation of language servers.

## What is measured here

### 1. Cold build time

Per target, per machine, stated. One-time and amortised in normal use.

**It is amortised to zero in the matrix, and that is an ASSUMPTION rather than a measurement.**
A real user builds once and works for weeks, so the per-question share approaches nothing. On a
single question the build dominates everything. The matrix hands the index arm a pre-built index
and the baseline arm has no setup cost at all; that asymmetry is defensible and it is not
measured, so it is stated instead of inferred.

### 2. Incremental refresh time as a function of changed-file count

Not a single number — a curve. Refresh is fast when four files changed and is a full build after
a rebase, a branch switch, or a regenerated tree. **The tail is the interesting part**, because
the tail is what a policy has to guard against.

### 3. Estimator accuracy — the measurement that actually decides the policy

This is the one that matters most and reads like the least important.

If incremental refresh is fast enough, staleness stops being a correctness problem and becomes a
policy: **refresh, then report.** That policy is only safe if the cost estimate is good enough to
gate on — refresh when the estimate is under the threshold, warn when it is over. A
mis-predicting estimator fires the gate wrongly in both directions.

Measured mis-prediction to date, both on public evidence:

| source | advertised | actual |
|---|---|---|
| gh#10 reporter | ~88 s | 41.9 s |
| this repo's self-index | 7,999 ms / 300 files | 8,603 ms / 416 files |

The second looks close and is not: the two change sets merely happened to resemble each other.
The block quotes the **last full refresh cost**, not an estimate for *this* refresh.

### The threshold is RELATIVE, not absolute

Do not pick a wall-clock number. The baseline harness pays a file read to be current; if a
refresh costs less than the equivalent read, refresh-then-report is strictly better and there is
nothing left to decide. Expressing the threshold against the baseline's cost of currency makes it
portable across machines; expressing it in milliseconds bakes in whichever machine it was taken
on.

## What this leaves on the matrix as declared scope conditions

Both belong in `docs/CORE_HYPOTHESIS.md` so no one reads a matrix result as evidence about them:

1. **H₁ is measured on a static pinned tree with a fresh index.** Under a moving tree the index
   carries a staleness signal, but that signal is *index-level* and flags **invalidity** better
   than **incompleteness**. A body that moved is reported (`anchor_mismatch`); a new call site in
   a changed file produces a silently short list. gh#12 is the acute form — a symbol added since
   the build reports `found: false` as a definitive negative.
2. **Index build cost is amortised to zero in the matrix.** Assumed, not measured. See §1.

## What this does NOT change about the matrix

**Adopting refresh-then-report does not contaminate a run.** The matrix executes on a pinned
tree, so a refresh is a no-op costing one freshness check. The shipped policy and the measured
configuration stay identical — which is not usually true when a default changes mid-campaign.

## A ruling this reopens

Refresh-on-query was rejected on gh#10 because it "pays the latency inside a lookup, which the
report explicitly called a bad surprise." **That rejection was made at the current cost floor**,
where the doxygen stage re-runs whole-scope on any single changed file. It is conditional on that
floor, not permanent: below the threshold in §3 the objection evaporates.

## Layout

```
operational/
  README.md                      this file — what is measured and why it is not in the matrix
  <machine>/                     one directory per machine; a figure without a machine is not a
                                 measurement
    machine.md                   CPU, cores, RAM, storage, OS — enough to reproduce
    build-cold.md                per target, with target commit and CLEW_BUILD_VERSION
    refresh-curve.md             refresh time against changed-file count, including the tail
    estimator-accuracy.md        predicted against actual, per sample
```

## Standing caveats

**No figure here is portable.** Every one is machine-bound and must be re-taken on any machine
whose numbers are going to be quoted. The figures cited above were taken on a machine that was
never characterised, which is itself the defect this layout exists to prevent.

**Cite a public target or cite nothing.** The sanctioned targets are
[Mbed-TLS/mbedtls](https://github.com/Mbed-TLS/mbedtls),
[tvanfossen/entropic](https://github.com/tvanfossen/entropic), and this repository's self-index.
A timing taken on a private target is not citable and does not belong in this directory.
