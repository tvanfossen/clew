The reply separates the two cases by grading each empty result, not by a single fixed sentence. The grading lives in `clew/mcp_server/emptiness.py`: `search_emptiness` for symbol search and `prose_emptiness` for `corpus='prose'`. The grader only checks what the index holds. It never checks whether the file was in scope.

**How the reply tells the cases apart**

| Situation | Wording returned | What it claims |
|---|---|---|
| One token, no match in any searched corpus, no unread-corpus hits, file docs present | "This IS a definitive empty result… Do not retry" | The token is absent from the corpora `search` reads |
| Multi-token query, some token has zero hits | "NOT definitive". Names the dead token and says "RETRY WITHOUT THEM" | The conjunction emptied it, not the repo |
| Multi-token query, every token matches alone | "NOT definitive". Says to retry with fewer tokens or use `corpus='prose'` | No single unit carries all the tokens |
| Matching rows exist in a kind `search` doesn't read (typedef, enum, etc.) | "NOT DEFINITIVE… this index HOLDS matching rows…", with the kinds and counts named | The name exists; ask `dossier` for it |
| Prose query, token present in the symbol corpora | "NOT DEFINITIVE… this repository DOES use these terms" | The term is written somewhere else |
| No file-docs or no markdown corpus in the index | "NOT definitive. Rebuild with `index(action='refresh')`" | Nothing; the index can't look |

Every empty reply also carries a `Searched:` line, built from the search's own kind list, and a `scope` payload with the file count, top-level directories, extensions, and, when the build recorded it, `not_indexed`. That is how the reply answers "where did you look." The `not_indexed` field is only present when the build recorded it. Older indexes report it as absent, not as empty, so "nothing was missed" is never inferred.

**How much confidence each answer deserves**

- **The strong "definitive" reply** earns high confidence only that no searched corpus holds the token. The "unread corpus" check is a subtraction from the kinds actually in the database, so it adapts to new kinds. It does not earn confidence that the *repository* lacks the term. A file outside the index's scope, such as a `.c` file in an index that never ingested `.c`, still gets the strong wording. The only signal is the `scope` key, and the verdict itself never consults it. That is the gap this module was written to close (gh#21), and the `list_files` tool that exposed it is gone. I'd treat "definitive" as "absent from the indexed scope" and check `scope` before acting on it.
- **The "NOT definitive, rows exist elsewhere" replies** are high confidence. They come from counts over the database, so the match is real even though `search` didn't return it. The useful next step is `dossier` by name.
- **The "retry without these tokens" replies** are high confidence about the cause, since they're per-token counts, but say nothing about whether the repo contains the full phrase.
- **The "rebuild the index" replies** carry no confidence in a negative at all.

**Two limits worth knowing**

- Only the first 8 tokens are diagnosed (`MAX_DIAGNOSED_TOKENS`). Later tokens go unexamined in both the per-token counts and the unread-corpus check.
- An index lacking the preprocessor-gate layer is deliberately not downgraded (gh#393 tried and was reverted). That absence shows up in `graph_stats.layer_states` as `absent`, not in each search reply.