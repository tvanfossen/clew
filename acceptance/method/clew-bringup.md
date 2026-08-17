<!-- SPDX-License-Identifier: MIT -->
# Q0 — Bringup: is your information about this repository, and is it complete?

Index arm only. Asked once per (model, run) at setup, before any repository question. Graded and
costed separately; never folded into the per-question average. The source arm has no counterpart.

The heading must stay `# Q0 — …`: `bench_rubric._Q_HEADING` requires `# Q<digits> — ` and yields
nothing for any other shape.

> **Question (frozen).** Before answering any question about this repository: establish that
> the information you are about to answer from actually describes THIS repository, that it is
> current with the working tree, and that it covers enough of the repository to answer
> questions about it. Report which repository your information describes, how you established
> that, whether it was current, what you did about anything missing or out of date, and what
> that cost. Then state which parts of the repository your information does not cover, so that
> "I did not find it" and "it is not there" stay different answers.

## Hard gate

**If the information source an agent answers from describes a repository other than the one
under test, the cell is VOID.** Not low-scoring — void.

- Its remaining marks are not scored, and no score from it enters any average.
- It is reported by coordinates in the void list, with the foreign repository named.
- This holds however good the rest of the answer is, and it holds whether or not the agent
  noticed. An agent that notices and says so is a better agent and still a void cell: the cell
  produced no measurement of anything.

An agent may legitimately consult a registry that lists other repositories — looking at a list
is not answering from the wrong one. What voids the cell is an ANSWER drawn from a source that
is about a different repository.

## Marks (7)

- [ ] **establishes which repository its information describes, and states it, BEFORE making any
  substantive claim.** Naming it afterwards, or in response to being challenged, does not earn
  this mark — the ordering is the whole point
- [ ] **the repository it names is the one under test.** If it is not, the cell is void per the
  gate above and the remaining marks are not scored
- [ ] **checks currency against the working tree rather than assuming it.** A stated mechanism —
  a compared timestamp, a freshness report, a re-read — passes; "it should be current" does not
- [ ] **acts on what the check returned.** If the information was stale or absent, it was brought
  up to date and the answer says so; if it was current, the answer says so with the evidence
  rather than by not raising the topic
- [ ] **reports the cost of establishing currency as a measured number**, not an estimate and not
  a range recalled from somewhere else
- [ ] **states the coverage basis** — which parts of the repository its information does and does
  not cover — so that a later "not found" can be read as ignorance rather than as absence
- [ ] **does not begin substantive work before all of the above.** An answer that investigates
  first and validates afterwards has demonstrated the exact failure this question grades, even
  if every check eventually passes
