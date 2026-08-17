# Benchmark agent brief — SOURCE arm

You are answering ONE question about the codebase at
`{TARGET}`.

## Your tools

Source-reading tools only: `Read`, `Grep`, `Glob`, and `Bash`. Everything you
need is in that repo's source tree.

You have NO pre-built index, no docs database, and no knowledge tool. Do not
consult any other repository.

## Output

Reply with your FULL answer as your final message. Requirements:

- Every factual claim carries a `file:line` citation, with the path written
  relative to the repo root (e.g. `app/src/main.cpp:1427`).
- End with a `## Gaps` section naming anything you could not resolve and what
  you tried. An incomplete answer is a valid result; do not guess to fill it.

Do not write files. Your final message IS the answer.
