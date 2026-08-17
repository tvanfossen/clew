<!-- SPDX-License-Identifier: MIT -->
# Acceptance methodology

Does the index measurably beat reading source? Measured as time, completeness against a rubric,
and quality against a baseline, across three model tiers.

**This file names no target and holds no measured figure.** Both belong to a target's own
`questions.md`, `evidence.md` and result document. A method that names its targets is one run's
report.

## Arms

| arm | gets | forbidden |
|---|---|---|
| `src` | source + grep/read/glob | any clew or MCP access |
| `mcp` | the real MCP server | `grep`/`rg`/`find`/`ls`/`sed`/`awk`/`cat`/`head`/`tail`, `Grep`/`Glob`, subagents. `Read` only to confirm a line the index already cited. **Also forbidden: direct database access** — no `sqlite3` CLI, no python `sqlite3`, no query script. The only permitted path is MCP tool calls, because that is the shipped surface. The audit flags direct-DB access as harshly as `grep`. |

Models: haiku, sonnet, opus × 3 runs × N questions × 2 arms, where **N is a property of the
target's rubric** and is stated in that target's result.

## Harness

Each cell is a fresh headless `claude -p` process, not an in-session subagent:

```
claude -p "<brief + question>" \
  --mcp-config <generated> \
  --model {haiku|sonnet|opus} \
  --output-format json \
  --allowedTools <arm's tools> --disallowedTools <the other arm's>
```

- **Isolation is AUDITED, not enforced** — and this reverses what this document used to claim.
  The arms are prioritisation plus audit: both carry the default toolset, and the only
  structural difference is that `--mcp-config` is attached to the index arm alone, so the
  source arm cannot reach the index because the server is not there. Everything else is
  observed after the fact from the transcript. A deliberate trade: a crippled arm does not
  measure real usage, so the comparison is `index+grep vs grep` — the honest question, and the
  harder one to win, because an arm that can also grep will grep when the index disappoints.
- **Two denials survive, and neither is about capability.** The open internet is refused to
  both arms, because a cell answering from GitHub measures neither arm. Direct database access
  — `sqlite3`, a `clew.db` path — is refused to the index arm, because SQL over the schema is
  not the tool a user has. MCP calls are the only permitted route to the index.
- **A source read by the index arm is REVIEWED, not counted against it.** It is the ordering
  evidence the hypothesis rests on: "reached for the index first" is a claim only the
  transcript settles. `review_count` in `metrics.csv` is that measurement, and it is not a
  defect tally.
- **Real MCP.** The agent sees `mcp__clew__*` and speaks the protocol to the real server.
- **Structured metrics for free:** `duration_ms`, `num_turns`, token breakdown, `permission_denials`.

Two failure modes the runner guards:

- A prompt that does not *require* a tool can answer before the MCP server finishes connecting,
  producing an index-arm cell that never touched the database. The brief must force a tool call
  and the runner must assert the cell used `mcp__clew__*` before counting it.
- MCP tools need explicit `--allowedTools`; without it the agent sees the tool and is refused,
  which looks like a broken tool.

## Execution model

`n=3`, three tiers, two arms. The session unit is **(model, run)**, so each arm runs **9
sessions** — and bringup happens **9 times, once per session, not once per run**.

| step | source arm | index arm | count |
|---|---|---|---|
| 0 | target resolution (harness, both arms) | same | 1 per run |
| 1 | **bringup skipped entirely** | build / refresh | 9 |
| 2 | n/a | structural target check | 9 |
| 3 | **no counterpart** | bringup question | 9 |
| 4 | Q1…QN | same | 9N per arm |
| 5 | restore tree | restore tree **and index** | after every cell |

Totals: **9N graded cells per arm, 18N overall, plus 9 bringup cells** attributed to the index
arm and excluded from the per-question average.

### Three constraints the harness must enforce

1. **Bringup → structural target check → bringup question.** Checking a target before the index
   exists checks nothing.
2. **A failed bringup ABORTS THE SESSION**, not just its cell. Every later answer from a session
   pointed at the wrong repository is void, and grading them spends capacity to pollute an
   average.
3. **Every cell starts from the pinned state, both halves.** The tree and the index are restored
   between cells, so a mutating cell cannot leak and **cell order is irrelevant**.

There is **no ordering rule for rubric authors**. Editing mid-session is what a real user does,
and within a cell the mutation is the question. Isolation is the fix; reordering is not — at
n=3, run 2 inherits run 1's edit wherever the question sits.

### Restoring both halves, and what it costs

Reverting the tree while leaving a probe symbol in the index hands the next cell a
stale-but-uncontrolled view, which the bringup question then grades as a finding the harness
manufactured.

- **Tree** — restore to the rubric's pinned commit and remove untracked files.
- **Index** — **copy back a snapshot** taken once after bringup. Byte-exact, tens of
  milliseconds for a database of a few tens of MB. A rebuild costs 8–20 s for a mid-size C/C++
  target (each target records its own `build_meta.refresh.duration_ms`) and is strictly weaker:
  a rebuild reproduces the bringup state only if bringup was deterministic; a copy reproduces it
  by construction.

### What the harness enforces today

`run_matrix` expands `question × arm × model × run` and runs each cell as an independent
process. It has **no session concept, no bringup step and no session abort.**

**Per-cell restore of BOTH halves now exists** (2026-08-10), and it is on by default. Before each
cell the runner resets the target tree (`git checkout -- .`, `git clean -fd`) and rebuilds the
index through `build_index`, so every cell's premise is identical whether or not the cell before
it mutated anything. Both halves or neither: a reset tree with a stale index would have the source
arm reading the restored files while the index arm answered from the mutated ones, which is a
comparison between two different repositories.

It is **BEFORE** each cell rather than after, because after-the-fact cleanup leaves the last
cell's edits in place for whatever runs next and cannot help a sweep that inherited a dirty tree
from something else.

It **refuses without an explicit opt-in.** `git clean -fd` deletes untracked files and `--target`
is an arbitrary path an operator types, so the tree itself must say it is disposable by carrying a
`.acceptance-disposable` marker file. A marker rather than a path heuristic: a heuristic is
satisfiable by accident and the failure mode here is somebody's uncommitted work. The refusal
names the remedy and fires at sweep start, not at cell 1.

`--no-restore` skips it. A sweep run that way is **not a clean measurement** — a mutating cell's
edits survive into every later cell — and the result must say it was used.

**Why this became necessary rather than merely desirable.** Before the arm reframe, `Write`/`Edit`
were denied to both arms, so only a question that provoked a refusal could dirty a tree, and the
mutating question was unattemptable — which is why its marks went ungraded. Now every cell *can*
mutate, so the exposure stopped being specific to one question.

### Bringup accounting

The source arm pays no bringup and **must not be charged a placeholder**. Report the index arm's
bringup wall time and tokens as their own line with median and range, separate from every
per-question figure, and state the N it amortises over.

## Void cells

A cell whose index answered about a **different repository** than the questions ask about is
**VOID**, not low-scoring: its marks are meaningless and so is its cost, because a cell that
discovers the wrong repository and bails is cheap.

Three layers:

1. `mcp_config_for` derives the server's `--repo` from the same `--target` the questions use, so
   the default target cannot disagree with the questions.
2. `preflight_target` samples the resolved index's paths against the target root before any cell
   runs.
3. `target_check.verify`, **per cell and structural**: every index reply stamps the repository
   that answered it, and the check compares that field to the target. This catches what the
   first two cannot — `--repo` sets only the DEFAULT target, and every query tool accepts a
   `target` argument, so an agent can name another indexed repository and both sweep-level
   guards still pass.

It is a **path comparison against a JSON field, never a prose match.** A prose version was
measured at 4 of 15 real cases with a false positive on a source-arm cell and dropped: a guard
that unreliable converts "unchecked" into "checked and fine".

Three outcomes, never two: `ok`, `void`, `unchecked` (no transcript, or no reply carried a
stamp). A void cell is excluded from every average **and named**; an unchecked one is graded and
reported as unchecked. The first void cell aborts the sweep.

## Metrics

`target,q,arm,model,run,tokens,tool_uses,duration_ms,build_ms,bringup_ms,marks_hit,marks_total,audit_clean,verdict`

`build_ms` is measured per cell from the transcript by pairing each `build_or_refresh`
`tool_use` with the `tool_result` carrying its id — the build happens inside the cell's own
server process. It is written EMPTY, not `0`, for a cell that built nothing.

**It INCLUDES the doxygen run and is reported unsplit** (owner decision). That is what an
operator waits for; measuring a pre-warmed build would measure something no user experiences.
A cold mbedtls bringup is ~32 s of doxygen and that is allowed to be the headline.

`bringup_ms` is the same measurement widened to every bringup tool — `build_or_refresh` plus
`propose_declaration`, the surface an agent uses to work out what a repository has to declare
before it can answer. Reported BESIDE `build_ms`, never instead of it: bringup is a cost of its
own ("bringup is a cost that must be quantified directly"), and charging the discovery of a
missed declaration to whichever question exposed it would fold a fourth axis into the first
question's cost. `bringup_ms == build_ms` for a cell that declared nothing, which is the common
case and the correct negative.

`metrics.csv` is APPEND-ONLY, so the field list is a schema. `append_row` compares the existing
header against `CSV_FIELDS` and refuses on a mismatch: appending a wider row to a narrower file
shifts every value after the new column while `DictReader` keeps reading the file's own header,
so old rows stay right and new ones are silently wrong. A sweep resumed into an older directory
needs a fresh `--out`; nothing is lost, because resumption keys on the answer files.

## Judge reliability

The completeness judge is nondeterministic. Three safeguards, cheapest first:

1. **Objective-first.** A mark naming a symbol or `file:line` is settled by citation matching.
   The judge runs only on marks no string match can decide, and where the objective pass and the
   judge disagree. Most of the score is deterministic.
2. **Majority vote on contested marks** (`bench_judge.vote`, default n=3, odd to avoid ties).
   The report records the agreement ratio, so a 2-of-3 verdict is visibly shakier than 3-of-3.
   An unparseable sample is an error, not a vote.
3. **`score_strict` is the conservative headline.** Where the judge disagrees downward with the
   objective pass, strict defers to the judge. Both numbers are printed.

Position bias is handled separately for pairwise quality: every comparison runs A/B and B/A, and
a verdict that flips under the swap marks that pair unreliable rather than being counted.

## Grading axes

1. **Time** — wall clock per cell; bringup reported separately.
2. **Completeness** — score against the rubric's marks. Objective match first, judge for marks
   phrased conceptually. Grades stay human-reviewable; the comparison arm is a reference point,
   not a gold standard — a less complete but correct answer is not a failure.
3. **Quality** — blind pairwise on the same question, arms anonymised, judging correctness,
   causal completeness and citation integrity.

## Rules that must be preserved

- **An incomplete answer is a valid result.** BOTH briefs require a `## Gaps` section — "the
  index cannot reach X" is a primary output and feeds the generator. The section used to be
  called `## Index gaps` in the `mcp` brief only, which asked the same thing under a name that
  primes attribution to the index, in a section the judge reads. The two output contracts are
  now byte-identical and a test compares them as text, because anything one arm is told and the
  other is not is a handicap built into the harness — and the gaps an arm actually hit are
  captured from the transcript by `fallback_audit`, which an agent cannot flatter by
  manufacturing something to report.
- **Bringup cost is reported separately and never folded into a per-question mean.**
  `build_ms` is what a refresh costs; `bringup_ms` adds the `propose_declaration` runs needed to
  work out what a repository has to declare. Both were collected for several rounds and printed
  nowhere, which reads as though bringup were free; `report.md` now carries its own section, and
  says NOT MEASURED rather than going silent when no cell built anything.
- **Questions are frozen and verbatim.** Briefs verbatim and committed.
- **Fixed harness overhead applies to BOTH arms** — roughly 3k tokens per cell. It puts a floor
  under any percentage; state it rather than hide it.
- **Smoke-test every tier-1 tool against the real built index before spending a single run.** A
  silently broken search dispatch once returned "Query was empty" and exited 0 for a whole
  round, so agents guessed names and the measured arm was not the arm anyone thought they were
  measuring.
- **`grading_coverage.py` treats an empty or missing answers directory as an ERROR**, not as
  completeness. Zero cells means zero degraded cells, which is reassurance without measurement.
