<!-- SPDX-License-Identifier: MIT -->
# mbedtls — pre-release grid

**Target** Mbed-TLS/mbedtls at `068ff080b369adfac81509f9b57b2afabaf82dc5`
**Rubric** `acceptance/targets/mbedtls/questions.yaml` version 1.0.0
**Design** n=1 · Q1–Q11 · both arms (`mcp` = index, `src` = source-reading) · models haiku + sonnet
**Graded** 44 cells, `unmarked_pct` 0.0%, `index_false` 0 — no judge errors, no false index answers

Q0 ran index-arm only (orientation; no source-arm counterpart) and is excluded from every
figure below. 158 marks = Q1–Q11.

## Result

| model | marks | index | source | Δ marks | total_tokens | result_bytes | turns |
|---|---|---|---|---|---|---|---|
| haiku | 158 | 59.5% (94) | 60.8% (96) | −2 | −43% | −9% | 179 v 261 |
| sonnet | 158 | 76.6% (121) | 79.7% (126) | −5 | +15% | +42% | 125 v 129 |

`total_tokens` is a round-trip counter times a ~80k static prompt; it is not a retrieval
measure. `result_bytes` is. The two disagree in sign at sonnet, and that disagreement is the
finding, not a rounding artefact: the index arm pulls more payload per turn at the same turn
count.

## Per question (marks met, index v source)

| Q | marks | haiku idx | haiku src | sonnet idx | sonnet src |
|---|---|---|---|---|---|
| Q1 | 31 | 22 | 23 | 28 | 30 |
| Q2 | 24 | 14 | 14 | 16 | 19 |
| Q3 | 26 | 11 | 8 | 16 | 17 |
| Q4 | 26 | 19 | 19 | 18 | 21 |
| Q5 | 7 | 3 | 3 | 5 | 4 |
| Q6 | 8 | 5 | 6 | 6 | 6 |
| Q7 | 7 | 6 | 3 | 7 | 7 |
| Q8 | 7 | 5 | 6 | 7 | 5 |
| Q9 | 8 | 3 | 5 | 5 | 5 |
| Q10 | 6 | 1 | 4 | 5 | 4 |
| Q11 | 8 | 5 | 5 | 8 | 8 |

Largest index wins: Q3 haiku (+3), Q7 haiku (+3), Q8 sonnet (+2).
Largest index losses: Q10 haiku (−3), Q2 sonnet (−3), Q4 sonnet (−3).

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
  --rubric acceptance/targets/mbedtls/questions.yaml --target mbedtls \
  --arms mcp,src --models haiku,sonnet --runs 1 --out <dir>
.venv/bin/python acceptance/bench/grade_matrix.py \
  --rubric acceptance/targets/mbedtls/questions.yaml complete --answers <dir>
```

## Standing caveats

- **n=1.** No noise floor is established here. A Δ of 2–5 marks in 158 is not shown to be
  distinguishable from run-to-run variance.
- **Contaminated marks.** Fixes that added to a tool description what the rubric grades make
  those marks non-comparable across runs. See `gaps.md`.
- **No verdict is recorded here.** The harness reports; the owner rules (D1).
