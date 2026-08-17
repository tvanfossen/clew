<!-- SPDX-License-Identifier: MIT -->
# Reading the acceptance evidence

A run produces `18N` graded cells plus `9` bringup cells for a rubric of N questions. This says
what each artifact is and how to check a result without trusting the summary.

## Artifacts

| file | what it answers | trust |
|---|---|---|
| `matrix-result.md` | the headline: four metrics, per target and model tier | derived |
| `<Q>_<model>_<arm>_r<n>.md` | what the model produced, as submitted | primary |
| `history/<cell>.history.md` | every tool call, what it asked, what came back | derived |
| `history/<cell>.transcript.jsonl` | the complete session record | authoritative |
| `<cell>.grade.json` | per-mark verdict with the judge's quote | derived |
| `metrics.csv` | tokens, wall time, turns, tool counts, cost per cell | primary |
| `raw/<cell>.json` | the runner's untouched reply payload | authoritative |
| `raw/<cell>.target.json` | which repository the index answered from (`ok`/`void`/`unchecked`) | derived |
| `argv/<cell>.json` | the exact command the cell ran, including the prompt | authoritative |
| `mcp-bench.json` | the server config the run generated | authoritative, DEFAULT target only |

Where a derived file and an authoritative one disagree, the authoritative one is correct and the
derivation is a bug.

## Committed artifacts are normalised

Home-directory prefixes are rewritten to `~` by `acceptance/bench/bench_publish.py`. Nothing else
is altered. **No gate enforces this** — normalisation on write is the only protection, so a
missed shape reaches HEAD unchallenged.

## Checking one cell

1. `history/<cell>.history.md` — did the agent ask sensible questions and get real answers?
2. `<cell>.md` — does the answer follow from what the history shows?
3. `<cell>.grade.json` — each mark carries the judge's quote and reasoning. Overturn what you
   disagree with.

## Checking the claim

- **Right repository?** `metrics.csv` `target_ok` and `raw/<cell>.target.json`. Three verdicts
  mean three things: `ok`, `void`, `unchecked`. A run with no `target_ok` column is UNCHECKED,
  not clean. `--repo` in `argv`/`mcp-bench.json` is weaker: it sets only the default target.
- **Void cells excluded AND named?** A void cell's marks are meaningless and so is its cost.
- **Whole exam marked?** `unmarked_pct` above 0 means the judge did not rule on part of it. A
  `JUDGE_ERROR` scores 0.0, which is indistinguishable from a MISS.
- **`arm_fenced_marks` is ZERO?** A fence is a defect in the rubric, not a footnote about the run.
- **Bringup on its own line?** The index arm pays it; the source arm does not. Never smeared into
  a per-question figure, never mirrored onto the source arm.
- **Did a mutating cell leak?** Until the harness restores the tree and index between cells, an
  edit by one cell is present for every cell after it.

## Standing constraints

- No release claim of a specific improvement until the owner has vetted the grading and the run.
- Report per target, never averaged. Every metric varies with repo size, language and how much
  the target declares.
- Report the axis that hurts first.
