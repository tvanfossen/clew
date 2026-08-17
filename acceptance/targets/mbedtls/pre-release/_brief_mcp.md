# Benchmark agent brief — INDEX arm

You are answering ONE question about the codebase at
`{TARGET}`.

## Your tools

A queryable index of that repository, served over MCP, plus the ordinary
source-reading tools. The index is already built and current — no setup step.

Reach for the index FIRST; that is the claim under test. If it does not answer,
read the source — and say so in the gaps section, because a lookup that failed is
a result worth having.

One hard limit: reach the index through its MCP tools, never the database file
directly (no `sqlite3`, no query script, no `Read` of `docs.db`) — that would
measure a schema rather than the tool a user has.

## Output

Reply with your FULL answer as your final message. Requirements:

- Every factual claim carries a `file:line` citation, with the path written
  relative to the repo root (e.g. `app/src/main.cpp:1427`).
- End with a `## Gaps` section naming anything you could not resolve and what
  you tried. An incomplete answer is a valid result; do not guess to fill it.

Do not write files. Your final message IS the answer.
