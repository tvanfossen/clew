<!-- SPDX-License-Identifier: MIT -->
# questions.md — required shape

A rubric is a DATA FILE: questions and grading criteria. It is not documentation.
`acceptance/bench/bench_rubric.py` parses it; anything the parser does not read is noise.

Every target has two files in `acceptance/targets/<target>/`:

| file | contents | read by |
|---|---|---|
| `questions.md` | questions + marks | the harness, and the judge (marks only) |
| `evidence.md` | proof each mark is true at the pinned commit | humans |

The judge never sees `evidence.md`. It exists so a mark can be checked rather than trusted.

## Shape

```
<!-- SPDX-License-Identifier: MIT -->
---
target: owner/repo
commit: <full sha>
---

# Q1 — <title>

> **Question (frozen).** <what the answerer is asked>

## Marks (N)

- [ ] <mark>
- [ ] <mark>

---

# Q2 — <title>
...
```

## Front matter

Two keys. `target` and `commit`. Add a third only for a pinned submodule the questions depend on.

The commit is the version. Ground truth is derived from that tree, so the pin is the whole
provenance — no `version`, no `changelog`, no `measured`, no `status`, no counts.

## What the parser requires

| element | pattern | note |
|---|---|---|
| question heading | `# Qn — title` | one `#`, em dash or hyphen |
| prompt | any text before the marks | |
| marks heading | `## Marks (N)` | `N` must equal the bullet count |
| mark bullet | `- [ ] text` | continuation lines indent |

## Not permitted

- Any reference to clew, an index, a database, an MCP tool, a table or a layer name.
  A rubric grades the TARGET REPOSITORY. Both arms answer the same questions.
- A question one arm cannot attempt. That is a solo exam, not a comparison.
- Row counts, edge counts, confidence distributions — properties of an instrument, not the repo.
- Prompt text stating a figure. It hands the answerer a premise.
- Auto-fail clauses, bonus tiers, weighted marks. A mark is a mark; hit or miss; never past 100%.
- Changelogs, methodology, "expected difficulty", "why this question exists", grading essays,
  mark-total tables, structural-fairness notes.
- Arm fences. A fence is a defect in the question, not a property of the run.

## Immutability

A rubric is fixed for its commit. Never edit a mark in place: a score graded under a corrected
key is not comparable to one graded under the old key, and editing hides that. A wrong mark
produces a superseding rubric.

The marks themselves can be wrong — that is what `evidence.md` is for. A mark whose evidence
does not hold when followed is a rubric bug, and it has happened: one key asserted a single lock
nesting where source had three, another asserted two retry mechanisms where source had three.
Both would have graded a correct answer as a miss.

## Bringup

Not here. `acceptance/method/clew-bringup.md` is shared across every target, runs on the
index arm only, and is graded and costed separately.

## Check the parse

```
.venv/bin/python acceptance/bench/grade_matrix.py --rubric <questions.md> rubric
```

Every question must print `[OK]` and `0 fenced marks`.
