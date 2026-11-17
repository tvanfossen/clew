# The exact commands

## Pre-flight (no agent calls)

```bash
cd /home/tvanfossen/Projects/clew
.venv/bin/python -m acceptance.matrix --out acceptance/runs/2.0.0 \
    --only mbedtls entropic self mattermost --models claude-haiku-5-5 \
    --replicates 3 --seed 7 --provision-only
```

## The grid — ONLY ON THE OWNER'S EXPLICIT APPROVAL, after a confirmed usage reset

```bash
cd /home/tvanfossen/Projects/clew
.venv/bin/python -m acceptance.matrix --out acceptance/runs/2.0.0 \
    --only mbedtls entropic self mattermost --models claude-haiku-5-5 \
    --replicates 3 --seed 7 --jobs 4 --resume
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

## The figures (per repo; 1.3.0-final and 1.4.0-final for context)

```bash
.venv/bin/python scripts/gate_figures.py acceptance/runs/2.0.0 acceptance/runs/1.3.0-final
.venv/bin/python scripts/gate_figures.py acceptance/runs/2.0.0 acceptance/runs/1.4.0-final
```
