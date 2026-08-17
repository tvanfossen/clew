<!-- SPDX-License-Identifier: MIT -->
# entropic — pre-release grid

**Target** tvanfossen/entropic at `6dcb4c814639fd58ead85aea06809637010f34f1`
**Rubric** `acceptance/targets/entropic/questions.yaml` (`build_version: 50`)
**Design** n=1 · 7 questions · both arms (`mcp` = index, `src` = source-reading) · haiku + sonnet
**Graded** 28 cells, `unmarked_pct` 0.0%, `index_false` 0 — no judge errors, no false index answers

## Result

| model | marks | index | source | Δ marks | total_tokens | result_bytes | turns |
|---|---|---|---|---|---|---|---|
| haiku | 79 | 50.6% (40) | 51.9% (41) | −1 | −45% | −27% | 149 v 230 |
| sonnet | 79 | 69.6% (55) | 70.9% (56) | −1 | +14% | +34% | 86 v 84 |

`total_tokens` is a round-trip counter times a ~80k static prompt, not a retrieval measure;
`result_bytes` is. They disagree in sign at sonnet.

## Per question (marks met, index v source)

| Q | marks | haiku idx | haiku src | sonnet idx | sonnet src |
|---|---|---|---|---|---|
| Q1 | 11 | 5 | 8 | 7 | 9 |
| Q2 | 12 | 4 | 5 | 8 | 8 |
| Q3 | 11 | 6 | 6 | 4 | 8 |
| Q7 | 11 | 4 | 4 | 9 | 8 |
| Q9 | 11 | 7 | 4 | 9 | 6 |
| Q10 | 10 | 7 | 8 | 9 | 8 |
| Q12 | 13 | 7 | 6 | 9 | 9 |

**The index's whole deficit is Q1 and Q3** (−3/−2 and 0/−4). Q9 is its largest win (+3 at both
models). Q1 and Q3 are also this rubric's two compound-mark questions — marks that weld several
requirements into one binary verdict, which D2 forbids and which mbedtls Q1–Q4 had removed by
atomisation (33 compound marks → 108 atomic). Entropic never had that pass. **So the −1 overall
is confounded with rubric shape and should not be read as a capability gap** until those marks
are atomised (task #448).

## What is in this directory

| path | what |
|---|---|
| `metrics.csv` | one row per cell: tokens, `result_bytes`/`db_result_bytes`, turns, tool uses, validity |
| `*.md` | the agent's final answer per cell — the graded text |
| `*.grade.json` | per-mark verdicts, judge quotes, `unmarked_pct`, `index_false` |
| `history/*.jsonl` | full transcripts — every tool call and result |
| `raw/` | the raw `claude -p` JSON plus the per-cell target check |
| `argv/` | the exact argv each cell ran, sanitised of machine paths |
| `_brief_mcp.md`, `_brief_src.md` | the two arm briefs, verbatim |
| `mcp-bench.json` | the MCP config the index arm ran under |

## Reproduce

```
.venv/bin/python acceptance/bench/run_matrix.py \
  --rubric acceptance/targets/entropic/questions.yaml --target entropic \
  --arms mcp,src --models haiku,sonnet --runs 1 --out <dir>
.venv/bin/python acceptance/bench/grade_matrix.py \
  --rubric acceptance/targets/entropic/questions.yaml complete --answers <dir>
```

The run refuses unless the checkout sits at the pinned commit (`preflight_target_revision`).

## THE RUBRIC HAS MOVED SINCE THIS RAN

These figures were graded against the **79-mark** version of `questions.yaml`. That rubric has
since been atomised to **87 marks**: Q1's mutex-count mark and Q3's spawn-count mark were each one
mark welding five separately failable requirements, and each was split five ways.

**Do not put these numbers in a table with any later run.** The denominators differ, and the
compound marks that were split are exactly the ones this result attributes the index arm's deficit
to — so a later run may move on Q1 and Q3 for reasons that have nothing to do with either tool.

No figure changed in the split. Every count carried into the new marks was re-verified against the
live index at the pinned commit first, and all of it reproduced.

## Standing caveats

- **n=1.** No noise floor. A Δ of 1 mark in 79 is not shown to be distinguishable from zero.
- **Compound marks.** See above — this rubric has not had the atomisation pass.
- **No verdict is recorded here.** The harness reports; the owner rules (D1).
