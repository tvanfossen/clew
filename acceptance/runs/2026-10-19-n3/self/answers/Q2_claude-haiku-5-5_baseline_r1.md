**Short answer:** the reply separates the two cases mainly by grading the wording of the empty note, not by a structured field. The strong "definitive" claim is only made when the database has been checked for rows the query would have matched in corpora `search` does not read. The file-type report that says "I did not look there" has a gap: when a file type is absent, the reply can't distinguish "measured, nothing missed" from "build predates the measurement."

I read this from source, not a live index query. The `dossier` hint from the shell hook isn't applicable here; I don't have the clew tools loaded.

**How an empty `search` is graded** (`clew/mcp_server/emptiness.py`, `search_emptiness` and `_verdict`)

| Situation | Wording | Confidence it earns |
|---|---|---|
| One token, no hits in `search`'s corpora, no hits in unread kinds, `file_docs` present | "This IS a definitive empty result… Do not retry" | Strong, but only about this index, its build scope and its preprocessor variant. |
| One token, hits exist in an unread kind (typedef, macro, class, etc.) | "NOT DEFINITIVE — this index HOLDS matching rows…" with the kinds and counts named | Explicitly withdrawn. The reply names the rows and says to use `dossier`. |
| Multi-token conjunction | "NOT DEFINITIVE" plus per-token counts and the dead token | Low. The reply says which token to drop. |
| `search(corpus='prose')`, token exists in symbols | "NOT DEFINITIVE… these terms are just not in prose" | Low for prose, and it points at the symbol corpus. |
| No `file_docs` table or no markdown corpus | "NOT DEFINITIVE… rebuild with index(action='refresh')" | None. The index could not have looked. |
| Index schema older than the server | `_withdraw_definitive` replaces the claim with "NOT DEFINITIVE" | Withdrawn. A layer may be missing rather than empty. |

The `scope` key on the reply gives the covered shape: file count, top-level directories, extensions and `source` (`declared` or `whole-repo`). That is what lets a caller tell "outside the scope" from "not in the repo."

**The file-type report** (`clew/cli.py:_not_indexed_scope`, stamped at build time)

- At build time, it compares the scanned file set to the `path` table and stamps `not_indexed` (e.g. `.sh=3, .yml=1`) and `not_indexed_count`. The count is exact; the list is capped at 12.
- It answers "I did not look in the place it lives" only at the file level. A file that is registered in `path` but yields no symbols, for example because its grammar is absent, is not flagged. I did not confirm whether the shell/YAML front ends register those files, so treat that as unverified.
- It is measured at build time, deliberately, because a query-time walk would describe a different tree.

**The gap: the reply cannot tell two cases apart.** `_not_indexed_scope` returns `{}` both when nothing was missed and when the build never walked the tree. `_scope_payload` then drops the `not_indexed` keys in that empty case. Both an index built before this release and a fully covered index therefore produce the same reply with no `not_indexed` key. The tests `test_an_index_that_holds_everything_in_scope_stamps_nothing` and `test_an_index_built_before_this_release_claims_nothing` assert exactly this sameness, while the module docstring says the two must not read the same. The only available proxy is the `scope.source` field, which tells you the scope rows exist, not that the file-type comparison ran. That is a real defect against the stated design, and it is a one-line fix to stamp an explicit zero (for example `not_indexed_count = "0"`) when the comparison ran and found nothing missing.

**How much confidence each answer deserves**

- **"The symbol is not in this repository"**: only the strong-wording case, and only for the indexed scope and build time. The code's own rule is "trust the negative" for a single absent symbol, and it withdraws that rule for conjunctions, unread kinds, stale schemas and split repositories.
- **"This file type is not indexed"**: a real, measured, count-exact fact at file granularity, but it does not say the file's symbols were extracted.
- **"Nothing was missed"**: the reply cannot currently support this claim. A missing `not_indexed` key does not establish it.