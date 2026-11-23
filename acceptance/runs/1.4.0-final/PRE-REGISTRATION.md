# 1.4.0-final — pre-registration

Written BEFORE the grid. This run REPLACES `acceptance/runs/1.4.0-pending/`, whose grid at
`0dd5ba1b` missed the gate on 2 of 4 repos (`1.4.0-pending/RESULTS.md`). Everything in
`1.4.0-pending/PRE-REGISTRATION.md` holds unchanged — targets, arms, models, grader fingerprint
`72a6c7bd363d`, replicates 3, seed 7, comparator `acceptance/runs/1.3.0-final/`, and THE GATE AS
WRITTEN — except the tool commit, which is the commit carrying the fixes below (recorded by the
harness as `clew_commit`; the run refuses a dirty tree). Owner, 2026-11-14: full grid, same gate.

## What changed since 1.4.0-pending, and why (from that grid's transcripts)

| fix | measured cause in the 1.4.0-pending grid |
|---|---|
| `direction='back'` accepted (the served text offered it) | 6 of 14 direction-setting calls refused |
| `qualified` narrows a variable's `sites`, or says it did not | one 48.9 KB all-sites reply returned 3× (mattermost Q4 r2, 711k tokens) |
| reply cap 65,536 → 40,960 bytes | replies at 48–50 KB: over the client's persist threshold (unreadable stub for index_only) or carried inline (one batch ≈ 100k tokens over 5 turns) |
| `compact_docs` drops only sentences the SERVED, untruncated body shows | `detail_in_body` on truncated bodies; `## @param` text dropped by word overlap |
| steering restored in served text (+485 chars) | `index(action='status')` openers 0 → 29; guessed `target` slugs refused 0 → 2; `corpus='files'` globs 17 → 46 |
| miss note no longer says "call status" | the reply already carries `staleness` when stale |

Offline replay of the exact failing calls on the 1.4.0-pending indexes
(`scripts/replay_grid_calls.py`): `back` REFUSED → answered; `enhanced` 50,048 B / 49 sites →
1,890 B / 1 site; the 9-subject batch 48,507 B → 35,570 B with `_limited`; miss note no longer
names status. Compact dossier bytes, 300 seeded function subjects: self −0.8%, entropic −1.4%.

## Hypotheses, per repo

Not re-projected: the offline changes are small next to the replicate variance the 1.4.0-pending
grid showed (mattermost without its two outlier cells ≈ +11.8% index_only tokens). The hypothesis
is the gate: index_only tokens vs baseline below 1.3.0-final's, separation within 3.0 pt of it,
for every repo.

DISCLOSED CONFOUND, self only: its rubric asks about clew, so served text can answer it. Two of
the restored sentences — search's "claims certainty only when no corpus outside search's reach
could hold a match" and index's "READS ARE UNAFFECTED BY THE `code` AXIS" — coincide with self
rubric marks (Q2 M1, Q3 M3; ~5 pt of the 1.4.0-pending miss). They are restored because they
tell any agent what an empty result and a `code` staleness notice are worth, and they were in
1.3.0-final's served text, so the comparator saw them too; a self gain on those two marks is
not evidence about the index.
