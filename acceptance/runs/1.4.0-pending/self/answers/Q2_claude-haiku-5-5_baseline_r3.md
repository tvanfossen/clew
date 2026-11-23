A zero-row reply carries two separate signals. The first is a verdict on the query. The second is a scope block that says what the index covers. Only the verdict is worded as definitive, and it is earned case by case.

**The verdict** (`clew/mcp_server/emptiness.py`, `search_emptiness` and `_verdict`)

- **Single token, nothing matched anywhere:** the strong wording ("definitive… do not retry or fall back to guessing") is used, but only after two checks. `q.unsearched_corpora` must find no matching rows in corpora that `search` does not read. And `q.has_file_docs` must confirm the file-docs corpus exists. If the file-docs corpus is missing, the reply says "NOT definitive" and points to a rebuild.
- **Single token, but the index holds rows in an unread corpus:** the reply says "NOT DEFINITIVE", names the kinds and counts, and tells the caller to use `dossier` with the name. The docstring explains why this check outranks the others: the reply should not send the caller to fix the wrong thing.
- **Multi-token query:** never definitive. `search` is a conjunction, so the reply reports per-token hit counts. If one token has zero hits, it is named as the cause and the caller is told to retry without it. Otherwise it says to retry with fewer tokens.
- **Prose query (`search_prose`):** `prose_emptiness` says the same thing about the prose corpus. If the symbol corpora hold the token, the reply is "NOT DEFINITIVE — this repository does use these terms." It is definitive only when neither the prose corpus nor the symbol corpora hold the token.

**The scope block** (`_scope_payload`, `_not_indexed_scope` in `clew/cli.py`)

This is the part that answers "I did not look in the place it lives." At build time, the build walks the repo and records which file extensions it had in scope but produced no `path` rows for. That is stored as `not_indexed` (top 12 by count) and `not_indexed_count`, and the reply includes them. The reply also includes `file_count`, `source` (whole-repo or declared), and the covered shape. The `reason` paragraph is removed on this surface and left to `status`.

Two details matter for reading the scope block:

- The falsy-drop rule means an absent `not_indexed` key is "not recorded," not "nothing was missed." An index built before this was stamped, or a rustdoc-only build that never walked the tree, shows no key at all.
- The check is by file type, not by directory. A file in an included extension but an excluded directory is not reported by `not_indexed`. That is a scope question, and the caller has to read `status.scope` for it.

**How much confidence each answer deserves**

| Reply shape | What it licenses |
|---|---|
| Definitive, no unread hits, file docs present, single token | Trust the negative. A retry will not help. |
| "NOT DEFINITIVE — rows in unread corpus" | The symbol exists. Go to `dossier` by name. |
| Conjunction note | Not a negative. Drop the named token and retry. |
| Prose miss, symbols hit | The repo uses the term. Search symbols or `dossier`. |
| `not_indexed` present | The listed file types were in scope and produced no rows. Read those files directly. |
| `not_indexed` absent | Unknown. Do not read it as "nothing missed." |
| Scope says "whole-repo" or "declared" with a small file count | Check whether the file is outside the scope before concluding the repo lacks it. |

The design rule stated in the code is "fix the corpus, not the sentence about the corpus." The code also has a control test, `test_an_absent_symbol_keeps_the_definitive_note`, that is meant to stop the wording from becoming a blanket hedge.

I read the code and did not run a query against a live index, so these are the intended behaviors as written, not measured outputs. The graded cases are covered by `tests/test_emptiness.py`, and `tests/test_not_indexed_report.py` covers the scope side. I did not run those tests.