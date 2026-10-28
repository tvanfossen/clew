# The exact command, and why each flag is there

Written BEFORE the run, beside `PRE-REGISTRATION.md`, so the composition of the grid lives in
the repository rather than in an operator's shell history. 1.1.0's grid is reproducible only
because three targets happened to be all that existed; seven are authored now.

## The command

```bash
cd /home/tvanfossen/Projects/clew
.venv/bin/python -m acceptance.matrix \
    --out acceptance/runs/1.2.0-pending \
    --only mbedtls entropic self \
    --models claude-haiku-5-5 \
    --replicates 3 \
    --seed 7 \
    --jobs 4 \
    --resume
```

One invocation. It provisions all three, generates every cell, grades once, reports.

## Every flag, and the one that is deliberately absent

| flag | value | why this value |
|---|---|---|
| `--only` | `mbedtls entropic self` | 1.1.0's three. An unknown name refuses the grid rather than shrinking it. |
| `--models` | `claude-haiku-5-5` | The model 1.1.0 answered with. `acceptance/modelpin.py` applies the same rule to both halves: a provider-canonical id is accepted, a client shortcut (`haiku`) is refused. |
| `--replicates` | `3` | 16 questions x 3 arms x 3 replicates = **144 cells**. |
| `--seed` | `7` | 1.1.0's seed. It drives arm rotation per replicate, not sampling — the `claude` CLI exposes no seed. |
| `--jobs` | `4` | Grading only; generation stays serial because a cell's wall-clock IS a reported axis. |
| `--resume` | — | Skips cells already answered, so a capacity stop resumes instead of regenerating. Generation is the half that cannot be re-run cheaply. |
| `--skip-graded` | **omitted** | One grading pass, per the ruling. `--skip-graded 1` would be needed only to resume a stalled grading phase. |
| `--skills` | **omitted, and this is load-bearing** | `SKILLS.md` did not exist when the 1.1.0 cells were generated — `--skills` landed in `5688814` on 2026-10-20, a day after. Passing it would change what the agent receives and make this grid a different experiment. The usage document's effect was measured separately in `acceptance/runs/2026-10-20-skills-ab/`. |

`--arms` is not a matrix flag: all three arms run, `baseline`, `index_only`, `index`.

## What it costs

| | |
|---|---|
| cells generated | **144** |
| judge samples, one pass | **~3,300**, upper bound 3,672 |

**THE FORMULA OVER-COUNTS AND THE MEASUREMENT IS THE ONE TO TRUST.** The rubric formula — 3
calls per mark where `weight >= samples_when_weight_at_least`, else 1, times 9 cells per
question — gives **3,240** at 1.1.0's threshold of 2. The 1.1.0 run actually consumed
**2,970**, measured from its own sidecars. The formula is 9% high because a set mark's per-item
decisions land with `samples: 1` regardless of the mark's weight, so it is an UPPER BOUND and
not a derivation. At threshold 1 that bound is 3,672; scaling the measurement by the same ratio
gives ~3,300, and the method for that number is this paragraph.

An earlier version of this file printed 3,672 as "derived, not estimated". It was neither.

**WHAT THE EXTRA CALLS BUY, measured rather than assumed.** Under the Sonnet judge, 146 of 936
voted decisions had the three samples DISAGREE — 15.6%, and 16.0% at weight 3. On roughly one
voted decision in six, a single sample is a coin flip. That is why k=3 is not waste, and
`5b14197` raised it to every mark because 12.7% of the grid's weight was still being decided by
one call.

**COST IS CAPACITY, NOT DOLLARS.** `acceptance/grader/judge.py` reaches the model through the
`claude` CLI, so judge calls spend subscription capacity and no token count or price is recorded
for them anywhere — this file states no dollar figure for grading because the evidence for one
does not exist. The ANSWERING side is recorded: the whole 144-cell 1.1.0 generation cost
**$1.71**, with 42.5M cache-read and 722K output tokens. `--skip-graded` exists because capacity
windows, not money, are what has actually stopped a grid: one window graded 23 cells, the next
re-graded those same 23 and reached 30.

**No second grading pass.** A noise floor would need one with `--no-judge-cache` — with the
verdict cache on, pass two replays pass one and reports a floor of zero. The ruling is one pass,
and `PRE-REGISTRATION.md` section 1 states what that costs the claim.

## Pre-flight, already run

```
3 target(s): entropic, mbedtls, self
provisioned 3/3 target(s); no phases run
```

| target | pinned commit | index built |
|---|---|---|
| mbedtls | `068ff080b369adfac81509f9b57b2afabaf82dc5` | 17.2 MB |
| entropic | `6dcb4c814639fd58ead85aea06809637010f34f1` | 13.3 MB |
| self | `a6dd8ed919e69dd0549ae2b14306c339c62db0a2` | 13.2 MB |

`provision()` runs `check_index_tools_reachable`, so this is an end-to-end pre-flight and not a
clone. The sizes are quoted because a provisioner that reported success on an empty database is
the failure this harness has actually shipped.

**The first pre-flight found a real defect and it is fixed rather than noted.** All three
`provision.json` files stamped `clew_version: 1.1.0` onto a 1.1.3 tree: `pip install -e .` writes
the version into `.dist-info` once and a later bump never rewrites it. The recorded version now
comes from the checkout's `pyproject.toml`, and `clew_version_installed` appears only when the
two disagree.

## Pins, verified against the rubrics rather than transcribed

| | |
|---|---|
| questions / marks / weight | 16 / 136 / 318 |
| mbedtls | 5 / 41 / 97, digest `d05822f1233ad005` |
| entropic | 5 / 41 / 96, digest `f908046b6fa97f44` |
| self | 6 / 54 / 125, digest `237ee289ee1b5023` |
| judge | `claude-haiku-5-5` — the same model that answers; floating, and `PRE-REGISTRATION.md` states what that costs |
| `grader_fingerprint` | `5489758d9a50` |

## Before starting, and after

```bash
# nothing uncommitted: provision records clew_dirty, and a dirty tree makes the record unresolvable
git status --short

# the fingerprint the report will be keyed on
.venv/bin/python -c "import sys; sys.path.insert(0,'.'); \
    from acceptance.grader.score import grader_fingerprint; print(grader_fingerprint())"
# expect 5489758d9a50

# after: the judge error rate, which criterion 4 can withhold the quality figure on
.venv/bin/python scripts/judge_error_rate.py acceptance/runs/1.2.0-pending --threshold 2
# exit 1 means DEGRADED and the quality figure is withheld
```

Judge error above 2% means the run is reported degraded and the quality figure is withheld.
The counter is verified against committed evidence rather than trusted: run against
`acceptance/runs/2026-10-19-n3` it reports **152 of 2,970 samples, 5.12%**, which is the figure
`PRE-REGISTRATION.md` cites. 1.1.0 was recoverable from its own sidecars the whole time; no
command computed it, so no reader saw it.

The same command prints the **split rate** — how often three samples of one mark disagreed. The
judge changed from `claude-sonnet-4-5-20250929` to `claude-haiku-5-5` this round and there is no
floor pass, so this is the only indicator available of whether the cheaper judge is noisier.
Sonnet's figure was **146/936 voted = 15.6%**, printed alongside for comparison. It is NOT a
noise floor.
