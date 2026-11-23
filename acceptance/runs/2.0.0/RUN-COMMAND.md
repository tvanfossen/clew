# The exact commands

## Pre-flight (no agent calls)

Into an EMPTY run directory: the 2026-11-16 pre-flight artifacts under
`acceptance/runs/2.0.0/<target>/` predate the current index build and are not reused.

```bash
cd /home/tvanfossen/Projects/clew
.venv/bin/python -m acceptance.matrix --out acceptance/runs/2.0.0 \
    --only mbedtls entropic self mattermost --models claude-haiku-5-5 \
    --replicates 5 --seed 7 --provision-only
```

## The grid — ONLY ON THE OWNER'S EXPLICIT APPROVAL, after a confirmed usage reset

```bash
cd /home/tvanfossen/Projects/clew
.venv/bin/python -m acceptance.matrix --out acceptance/runs/2.0.0 \
    --only mbedtls entropic self mattermost --models claude-haiku-5-5 \
    --replicates 5 --seed 7 --jobs 4 --resume
```

## Repair passes (judge errors from a usage window), per target, repeat until ≤ 2%

```bash
for t in mbedtls entropic self mattermost; do
  .venv/bin/python -m acceptance grade --rubric acceptance/targets/$t/questions.yaml \
      --answers acceptance/runs/2.0.0/$t/answers --jobs 4
done
.venv/bin/python scripts/judge_error_rate.py acceptance/runs/2.0.0
.venv/bin/python scripts/prune_judge_sessions.py   # after EVERY grading pass
```

## The figures (per repo; the run stands alone — PRE-REGISTRATION.md, amendment 2026-11-17)

```bash
.venv/bin/python scripts/gate_figures.py acceptance/runs/2.0.0
```
