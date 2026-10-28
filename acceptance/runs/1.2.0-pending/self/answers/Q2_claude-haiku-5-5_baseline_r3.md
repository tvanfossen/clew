The reply separates the two cases by checking the index itself, not by the wording of the note. Each empty answer is graded against what the build recorded and what the query could have matched elsewhere. I read this from the code and did not run a live query or the test suite.

**The verdicts** (`clew/mcp_server/emptiness.py`, `search_emptiness` and `_verdict`)

| Situation | Reply says | Confidence it earns |
|---|---|---|
| One token, zero hits in read corpora, zero hits in corpora `search` does not read, file docs present | "This IS a definitive empty result…" | Strong, but only about the indexed scope |
| One token, but rows exist in an unread corpus (e.g. a typedef) | "NOT DEFINITIVE — this index HOLDS matching rows… ask by name with dossier" with counts | None for `search`; the name exists |
| No `file_docs` table | "NOT DEFINITIVE… Rebuild" | None; the index cannot look |
| Multi-token query | Always "NOT DEFINITIVE", with per-token hits and the token(s) with zero hits named | Retry without the dead tokens, or with fewer tokens |
| `search(corpus='prose')`, token present in symbol corpora | "NOT DEFINITIVE — this repository DOES use these terms" | Negative only for prose |

The strong wording is the exception. The control test `test_an_absent_symbol_keeps_the_definitive_note` (`tests/test_emptiness.py:131`) exists to stop it being hedged away.

**Where "did not look" is recorded**

- **Scope on every empty reply.** `_scope_payload` adds `scope` with file count, top-level directories, extensions and the source tier (whole-repo or declared). The `reason` paragraph is dropped from this reply and kept in `status`.
- **File types the build skipped.** `cli._not_indexed_scope` compares the scanned tree against `path` rows and reports the gap by extension, with an exact count. If the build recorded nothing, the key is absent; an empty list would wrongly claim nothing was missed (`clew/query/corpus.py:255-318`).
- **Corpora read.** The `Searched:` clause is built from `SEARCHED_MEMBERDEF_KINDS`, so it cannot drift from what the searcher reads. It also states the markdown and Kconfig prose that were not read.
- **Unread kinds in this database.** `q.unsearched_corpora` subtracts the searched kinds from the kinds the database holds, and any hit downgrades the verdict and is published as `unsearched_corpus_hits`.
- **Split repositories.** `RepoIndexes`/`Target` carry `sub_index`, `not_searched` and `split` (from `.gitmodules` even when no sibling is built). A negative from one part is rewritten as "NOT DEFINITIVE FOR THE REPOSITORY" and points to the other parts (`tools_query.py:354`).
- **Stale index.** A schema-axis or drift-axis staleness withdraws the definitive wording (`_withdraw_definitive`).

**How much to trust each**

- A definitive negative is trustworthy only for the scope named in `scope` and for the build's measurement time. A file type listed in `not_indexed` is a build-time fact, not a live one. Files edited after the build are visible only through the staleness axes.
- A missing `not_indexed` key means "not measured", not "nothing skipped".
- The check for unread corpora covers only the first `MAX_DIAGNOSED_TOKENS` tokens, and it asks about kinds, not about the working tree.
- The code grades the index, not the repository. A repository split into parts is graded per part, and the reply says so.

In short: the reply can tell "outside the indexed scope or in an unread corpus" from "the name is absent from the searched index", and it grades the second as definitive only when no check in the list above fails.