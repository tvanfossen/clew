The reply separates the two cases by grading the empty result, not by one fixed sentence. The grading lives in `clew/mcp_server/emptiness.py` (`search_emptiness`, `_verdict`, `_conjunction_note`), and the facts behind it come from `clew/query/symbols.py` (`unsearched_corpora`) and `clew/query/corpus.py` (`index_scope`). I read the code and did not run it.

**What the reply carries**

- **Scope block:** `file_count`, top-level directories, extensions, and the scope `source`, read from the index's `build_meta`. This says what the build walked, which the caller can compare against the working tree.
- **`not_indexed` / `not_indexed_count`:** file types the build walked and produced no rows for. The build measured this against its own tree, not the query-time tree.
- **`unsearched_corpus_hits`:** rows the query would have matched in a corpus `search` does not read (for example typedefs, macros, or file docs). It is computed by subtracting the searched kinds from the kinds the database holds, so a new kind is picked up without an edit.
- **`token_hits`:** per-token counts for multi-token queries, so the reply can name the token that emptied the conjunction.

**Which verdict you get**

| Situation | Wording | Confidence entitled |
|---|---|---|
| Single token, no unread-corpus hits, file docs present | "definitive empty result… do not retry" | High, for this index's searched corpora |
| Single token, unread corpus holds a match | "NOT DEFINITIVE… the name exists… ask dossier" | The name exists; search just cannot see that kind |
| Single token, no `file_docs` table | "NOT definitive… rebuild" | None; the index cannot look |
| Multi-token miss | "NOT definitive"; names dead tokens or says retry with fewer | Only that the conjunction is over-specified |
| Prose query, token present in symbols | "NOT DEFINITIVE… these terms are in the repo, not in prose" | The repo uses the term; prose does not |
| Index predating the metadata | `scope.not_indexed` absent | Not recorded; absence is not "nothing missed" |

**How much each answer is worth**

- A definitive empty answer means only that no searched corpus in this index holds the token. It does not prove the file is absent from the tree. That depends on the scope block and on `not_indexed`.
- `not_indexed` covers file types the build walked and skipped. Files outside the walked scope are not listed, so the caller has to infer that from the scope `source` and the extension list.
- The code does not check whether the index is stale. `clew/mcp_server/freshness.py` exists and I did not read it, so I cannot say whether an empty answer is also freshness-checked.
- Undocumented files are handled: `file` rows are treated as unsearched, so a match on an undocumented file's name shows up as an unread-corpus hit rather than a definitive negative.

In short: "definitive" is earned per call by checking the other corpora, and it is a claim about this index, not the working tree. The scope fields are how the caller checks whether the index covered the place the thing would live.