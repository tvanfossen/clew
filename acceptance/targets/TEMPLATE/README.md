<!-- SPDX-License-Identifier: MIT -->
# Measuring clew on your own repository

A standard procedure, so results from different people are comparable. If you deviate, say where
in your `result.md` — an undisclosed deviation is worse than a missing measurement.

## What is being measured

Two arms answer the same questions about the same repository, same model, same sitting.

| arm | tools |
|---|---|
| `mcp` (index) | clew MCP tools **plus** the ordinary source tools, told to reach for the index first |
| `src` (source) | `Read`/`Grep`/`Glob`/`Bash` only — the index is fenced off entirely |

Neither arm is the shipped product: real use has both with no preference. That third arm is not
yet part of the standard suite. Until it is, **report the union too** (below) — across four
targets it has been the largest effect in the data and the head-to-head hides it.

## 1. Build an index

```
pip install clew-trace    # needs the `doxygen` binary on PATH
clew init                 # registers the MCP server; restart your client
```

Then ask the agent anything about your repo, or build explicitly. **No declaration file is
required** — three of the four measured targets ran on defaults. If `status.diagnostics` names
accessor families or spawn primitives it could not see, declaring them in `.clew.yaml` is
worth doing *before* you measure, and worth recording that you did.

## 2. Write the rubric

Copy `questions.yaml` from this directory and follow its inline rules. Budget realistically: the
targets in this set run 7–14 questions and 79–173 marks, and writing one honestly takes longer
than running it.

Two things that decide whether your number means anything:

- **Ground truth from source, not from the index.** An index-derived figure moves when the
  pipeline moves, and then you are grading the tool against its own output.
- **Pin the commit.** The harness refuses to run against a different tree.

## 3. Run

Point `--target` at a **disposable clone at the pin**, never your working checkout — the harness
resets the tree and rebuilds the index between cells, which deletes uncommitted work. It refuses
without an explicit opt-in marker:

```
git clone <repo> ~/targets/mine && cd ~/targets/mine && git checkout <pin>
touch .acceptance-disposable
```

```
.venv/bin/python acceptance/bench/run_matrix.py run \
  --target ~/targets/mine --questions acceptance/targets/mine/questions.yaml \
  --arm both --model haiku --model sonnet --runs 1 \
  --out <dir> --yes
```

Preflights refuse on: no index, wrong revision, an unpinned rubric, a declaration that never
reached the build. A refusal is the harness working.

## 4. Grade

```
.venv/bin/python acceptance/bench/grade_matrix.py --rubric <rubric> complete --answers <dir>
.venv/bin/python acceptance/bench/arm_headroom.py --answers <dir>
```

Grading is resumable — a cell holding judge errors is re-graded, complete cells are skipped. If it
aborts on consecutive judge errors you have hit a capacity limit; re-run the same command later.

**Do not report until `unmarked_pct` is 0.0% on every cell.** A mark the judge never ruled on
weighs the same as a MISS, so an unfinished grading pass reads as a bad result for both arms.

## 5. Report

Copy the shape of `acceptance/targets/self/pre-release/result.md`. Required:

| | why |
|---|---|
| marks met, both arms, per model | the headline |
| `unmarked_pct` and `index_false` beside every score | an unruled mark is not a MISS; an unchecked veto is not a clean one |
| **`total_tokens` AND `result_bytes`** | tokens is a round-trip counter (r²≈0.90 on turns, ≈0.35 on retrieved bytes). The two have disagreed in sign on 3 of 8 measured cells. Reporting one is how you get a wrong verdict |
| turns | on one target the index arm took MORE turns and spent FEWER tokens — do not phrase a cost win as "fewer round trips" without checking |
| per-question breakdown | an aggregate tie can hide one arm winning half the questions |
| the union from `arm_headroom` | the biggest effect, invisible to the head-to-head |
| n, and what was excluded | at n=1 nothing is significant. Bringup and refresh cost are excluded by default — say so |

**Report the axis that hurts first.** The first grid in this project published a cost win and a
quality figure it had not checked, and the verdict was wrong.

## What we know so far, so you can compare

Four targets, n=1, two model tiers, 1,018 marks, all cells clean:

| target | language | index | source |
|---|---|---|---|
| Mbed-TLS/mbedtls | C | 59.5 / 76.6% | 60.8 / 79.7% |
| tvanfossen/entropic | C++ | 50.6 / 69.6% | 51.9 / 70.9% |
| clew itself | Python | **60.6 / 70.7%** | 56.6 / 69.7% |
| one private firmware | C | 56.6 / **75.7%** | 59.5 / 72.8% |

Aggregate: **65.7% index against 66.1% source** — a dead heat, −4 marks in 1,018, well inside the
noise floor at n=1. Cost splits by model rather than by language. **The union is 75.4% against
66.1% for the better single arm.**

So: expect a tie on completeness, expect a cost win at the weaker tier, and expect the two arms to
answer *different* questions. If your target contradicts any of that, **that is the interesting
result** — file it at the issue tracker with the run directory attached.

## Roadmap for this suite

- **1.0.0** — n=1, two tiers. Where we are.
- **1.1.0** — n=5, three tiers (opus / sonnet / haiku). Establishes a real noise floor and makes
  per-target deltas interpretable for the first time.
- **1.2.0** — add an open-weight tier (Gemma 4 e4b, via entropic) to test whether the index's
  value scales with model capability or inversely to it.
