<!-- SPDX-License-Identifier: MIT -->
# self — pre-release grid

**Target** tvanfossen/doxyguard-db at `d091b1d1860fbf16109a7a01d9350a5aeb388235`, run against a
disposable clone at that commit rather than the working checkout.
**Rubric** `acceptance/targets/self/questions.yaml` version 1.0.0, ground truth read from source
**Design** n=1 · 7 questions · 99 marks · both arms · haiku + sonnet
**Graded** 28 cells, `unmarked_pct` 0.0%, `index_false` 0

**This is the reference set's only Python target.** The query surface was known to work on Python;
it had never been graded on a Python repository, so that was a claim about a capability rather
than a measurement of one.

## Result

| model | marks | index | source | Δ marks | total_tokens | result_bytes | turns |
|---|---|---|---|---|---|---|---|
| haiku | 99 | **60.6%** (60) | 56.6% (56) | **+4** | −2.6% | −5.7% | 155 v 130 |
| sonnet | 99 | **70.7%** (70) | 69.7% (69) | **+1** | **−11.9%** | **−44.4%** | 88 v 79 |

**This is the first target where the index arm wins on completeness at BOTH model tiers**, and the
first where the stronger tier is cheaper on both cost axes — mbedtls and entropic both put sonnet's
index arm at +14–15% tokens and +34–42% bytes.

**The turn/token relationship inverts here.** The index arm takes MORE turns at both tiers (155 v
130, 88 v 79) and still spends FEWER tokens. On the other two targets tokens tracked turns at
r²≈0.9. The mechanism visible in the transcripts is that the source arm's per-turn prompt grows
faster because file reads accumulate in context, so its fewer turns are individually more
expensive. Any cost claim stated as "fewer round trips" would have the sign backwards on this
target.

## Per question (marks met, index v source)

| Q | marks | haiku idx | haiku src | sonnet idx | sonnet src |
|---|---|---|---|---|---|
| Q1 scope decision | 13 | **7** | 4 | 10 | 10 |
| Q2 nested repositories | 15 | 9 | **11** | 12 | **13** |
| Q3 Doxyfile resolution | 15 | **12** | 10 | **11** | 10 |
| Q4 precedence | 13 | 3 | 2 | 3 | 2 |
| Q5 vocabulary module | 13 | **8** | 6 | 10 | 10 |
| Q6 misspelled key | 14 | 6 | **9** | 9 | 9 |
| Q7 incrementality | 16 | **15** | 14 | 15 | 15 |

**Q4 is the hardest question for both arms at both tiers** — 2–3 of 13 everywhere. That is a
question about a precedence rule whose vocabulary is spread across a module docstring, and neither
tool assembles it.

## Headroom

Union **71.7%** against 65.7% for the better single arm (+6.0). 56 of 198 mark-instances are
missed by both. Each arm's hit-rate on the other's misses (23.3% / 17.6%) is well below its
unconditional rate, so a substantial part of the tie is a shared ceiling rather than equivalence —
the same shape as the other two targets. Reproduce with `acceptance/bench/arm_headroom.py`.

## THE VETO FIRED, AND THE RUBRIC WAS WRONG

`index_false` reads 0 above only because a false mark was corrected. On the first grading pass the
D3 falsity veto fired for the first time in this project's history — unanimous 3/3 on
`Q4_haiku_mcp` — against this mark:

> states that an empty value CHANGES NOTHING and is not an error — it means inherit, not
> withdraw-to-empty

**The mark was false and the answer was right.** The source states the rule in five places
(`cli.py:289`, `:465`, `:765`, `:1023`, `declaration.py:402`): **absent inherits, empty WITHDRAWS,
non-empty replaces**. The served `index` tool description says the same — *"omit to inherit, pass
an empty list to withdraw"*.

The error came from misreading `apply_options`, whose docstring says *"`None` and `{}` both change
nothing"* — that is about the OPTIONS MAPPING as a whole, not about an individual option's empty
value, and the very next sentence names the *"absent/empty/replaces convention"* that refutes the
misreading.

This is exactly the failure this project predicted and wrote down before it happened: **fed a
false fact, the veto inverts and zeroes the MORE accurate answer.** It is worth recording that the
prediction was correct on the veto's first live firing, and that the model was a better reader of
this codebase than the rubric author on this point. The mark now states the three-state rule and
the distinction from the mapping-level case; re-graded, the veto does not fire anywhere.

## Standing caveats

- **n=1.** No replicate; a Δ of 1–4 marks in 99 is not shown to be distinguishable from noise.
- **Reachable payload, not observed used.** `index(action='status')` returns a `scope.reason`
  string that states several Q1 facts nearly verbatim. Checked: no answer quotes it, so the Q1
  result is not payload-parroting — but the surface is reachable and the risk is structural.
- **Index noise.** This repository now carries ~20MB of committed grid transcripts and declares no
  `index_scope`, so the whole-repo tier indexes them (3,281 suppressed doxygen warnings). Symbol
  impact is small; the prose corpus is the open question (#455).
- **No verdict is recorded here.** The harness reports; the owner rules (D1).
