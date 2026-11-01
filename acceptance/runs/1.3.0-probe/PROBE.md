# 1.3.0 generation-only probe — mbedtls, `index_only`

**What this is.** A regression tripwire, run before the 1.3.0 grid is spent: one C target, the arm
the 1.3.0 changes touch, one replicate, **zero judge calls**. Four of the 1.3.0 changes are
cross-language — dispatch-family attribution in `unresolved_inbound`, the partial-index and
doxygen-failure stamps, the scope's silent-git and vendored-tree handling, and generated-file
ranking — so each can move a C target's index arm. A broken arm shows here as refusals, denied
calls, calls outside the index, transport errors or a collapse in tool use, for five cells
rather than a whole grid.

**What this is NOT.** A measurement. Nothing was graded, n=1 per question, and per-cell variance
at n=3 in 1.2.0 is wide enough that no figure below supports a delta in either direction. The
1.3.0 quality claim comes from the grid, never from this file.

## Provenance

| | |
|---|---|
| target | mbedtls `068ff080b369` (the held rubric, unchanged) |
| clew | `e73091f`, `clew_dirty: false`, build version 9 — recorded in `mbedtls/answers/run.json` and `mbedtls/provision.json` |
| grader | frozen at `72a6c7bd363d`; not invoked |
| model | `claude-haiku-5-5` (floats; see `acceptance/modelpin.py`) |
| arm / replicates / seed | `index_only` / 1 / 7 |

```bash
.venv/bin/python -m acceptance.provision --rubric acceptance/targets/mbedtls/questions.yaml \
    --root acceptance/runs/1.3.0-probe/mbedtls
.venv/bin/python -m acceptance generate --rubric acceptance/targets/mbedtls/questions.yaml \
    --models claude-haiku-5-5 --replicates 1 --seed 7 \
    --repo acceptance/runs/1.3.0-probe/mbedtls/repo \
    --out acceptance/runs/1.3.0-probe/mbedtls/answers \
    --mcp-config acceptance/runs/1.3.0-probe/mbedtls/mcp.json --arms index_only
```

## Result

**5 of 5 cells answered. 0 transport errors, 0 denied calls, 0 calls outside the index.**

Against the same five questions' `index_only` cells in `acceptance/runs/1.2.0-pending/`
(mean of three replicates there, one cell here), summed over the five:

| | 1.2.0 mean | 1.3.0 probe |
|---|---:|---:|
| tool calls | 45.0 | 50 |
| output tokens | 25,734 | 23,099 |
| cache-read tokens | 1,011,293 | 1,002,326 |
| wall seconds | 149.3 | 125.1 |

The largest per-question move is Q3's tool calls, 9.0 → 15. One cell cannot say whether that is
the model or the index; the grid's three replicates per arm can.

**Reading: no sign that the index arm on a C target is broken.** That is the only claim this probe
was built to support.
