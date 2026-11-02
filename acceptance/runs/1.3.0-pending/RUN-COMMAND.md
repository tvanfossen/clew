# The exact command, and why each flag is there

Written BEFORE the run, beside `PRE-REGISTRATION.md`, so the composition of the grid lives in
the repository rather than in an operator's shell history.

## Pre-flight (no agent calls)

```bash
cd /home/tvanfossen/Projects/clew
.venv/bin/python -m acceptance.matrix \
    --out acceptance/runs/1.3.0-pending \
    --only mbedtls entropic self mattermost \
    --models claude-haiku-5-5 \
    --replicates 3 \
    --seed 7 \
    --provision-only
```

## The grid — RUN ONLY ON THE OWNER'S EXPLICIT APPROVAL

```bash
cd /home/tvanfossen/Projects/clew
.venv/bin/python -m acceptance.matrix \
    --out acceptance/runs/1.3.0-pending \
    --only mbedtls entropic self mattermost \
    --models claude-haiku-5-5 \
    --replicates 3 \
    --seed 7 \
    --jobs 4 \
    --resume
```

One invocation. It provisions all four, generates every cell, grades once, reports.

## The comparator — 1.2.0's answers re-graded (Decision A), ALSO ON APPROVAL ONLY

On a COPY, so nothing under `acceptance/runs/1.2.0-pending/` changes — grading overwrites each
cell's `.grade.json`. The copy carries `answers/judge-cache`, so sample 0 of every vote replays and
only samples 1 and 2 reach the judge.

```bash
cd /home/tvanfossen/Projects/clew
for t in mbedtls entropic self; do
    mkdir -p acceptance/runs/1.3.0-pending/regrade-1.2.0/$t
    cp -a acceptance/runs/1.2.0-pending/$t/answers acceptance/runs/1.3.0-pending/regrade-1.2.0/$t/
    .venv/bin/python -m acceptance grade \
        --rubric acceptance/targets/$t/questions.yaml \
        --answers acceptance/runs/1.3.0-pending/regrade-1.2.0/$t/answers \
        --jobs 4
done
```

No `--skip-graded`: every copied cell carries 1.2.0's pass at `5489758d9a50`, which is a different
fingerprint, so each is graded once at `72a6c7bd363d`.

## Every flag, and the ones deliberately absent

| flag | value | why this value |
|---|---|---|
| `--only` | `mbedtls entropic self mattermost` | 1.2.0's three, unchanged, plus the ONE new target the owner approved for 1.3.0. An unknown name refuses the grid rather than shrinking it. |
| `--models` | `claude-haiku-5-5` | 1.2.0's answering model. Floats; disclosed in the pre-registration. |
| `--replicates` | `3` | 21 questions x 3 arms x 3 replicates = **189 cells** (144 held + 45 mattermost). |
| `--seed` | `7` | 1.2.0's seed. It drives arm rotation per replicate, not sampling. |
| `--jobs` | `4` | Grading only; generation stays serial because a cell's wall-clock IS a reported axis. |
| `--resume` | — | Skips cells already answered, so a capacity stop resumes instead of regenerating. |
| `--skip-graded` | **omitted** | One grading pass. Needed only to resume a stalled grading phase. |
| `--skills` | **omitted** | As in 1.2.0. Passing it would change what the agent receives and make the held 16 a different experiment from 1.2.0's. |

**Every arm is regenerated**, `baseline` included (owner, 2026-11-01). Reusing 1.2.0's baseline
answers would put weeks of model drift inside every separation, which the per-replicate arm
rotation exists to prevent.

**The clew tree must be committed and clean.** `generate` and `provision` refuse otherwise, so the
`clew_commit` every cell records resolves to the code that answered — 1.2.0's grid ran dirty and
had to concede that afterwards.
