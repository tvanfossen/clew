**Short answer:** the reply separates the two cases by grading the empty result against what the index actually holds, not by a fixed sentence. A "definitive" answer covers only what was searched, and the reply attaches the scope so the caller can tell a scope miss from a true absence. I read the code but did not run a query against a built index, so the behaviour below is from source.

**How the grade is chosen** (`clew/mcp_server/emptiness.py`, `search_emptiness` at line 298)

| Situation | Wording | Confidence it earns |
|---|---|---|
| One token, no matching rows in any unread corpus, file docs present | `_DEFINITIVE` (line 150): "definitive… Do not retry" | Strong, but only about the indexed corpora (see below) |
| One token, but the index holds matching rows in a corpus `search` doesn't read (classes, variables, macros, typedefs, enums, …) | `_UNREAD_CORPUS` (line 161): "NOT DEFINITIVE", names the counts, points to `dossier` | None for "does not exist"; the name does exist |
| Multi-token conjunction empty | `_conjunction_note` (line 259): "NOT definitive", names the tokens with zero hits and says retry without them | Low; the miss comes from the query shape |
| No file-docs table in the build | `_NO_FILE_DOCS` (line 139): "NOT definitive", rebuild | None for conceptual queries |
| `corpus='prose'`, no markdown table | `_NO_PROSE_CORPUS` (line 428): "NOT definitive" | None |
| `corpus='prose'`, token present in symbol corpora | `_PROSE_ELSEWHERE` (line 420) | The repo uses the term; it is written elsewhere |

The unread-corpus check is the important one. `q.unsearched_corpora` (`clew/query/symbols.py:1806`) derives the unread kinds by subtraction from the kinds the database actually holds. It downgrades the verdict on any hit and publishes the hits as `unsearched_corpus_hits`, so the claim can be checked. The module's own docstring records that the strong wording was wrong four times before this was added.

**Where the place-it-lives answer comes from**

Every empty reply carries a `scope` block (`_scope_payload`, line 212) built from `q.index_scope` (`clew/query/corpus.py:288`): source tier (for example whole-repo or declared), `file_count`, `top_levels`, `extensions`, and `not_indexed_count`. The summary sentence says "see the `scope` key". The `reason` paragraph is stripped here to save bytes but is still in `status`. The caller is the one who has to compare the path they expected against those fields.

**What each answer is entitled to**

- **"Not in the index" (definitive):** high confidence that no indexed name, `@brief`, macro, class/struct/union, gated config symbol, or file doc matches that single token, at build time. It does not cover body text, comments outside those corpora, or anything else the searcher never reads.
- **"Not in the repository":** only if the scope covers the path. The strong sentence does not say that a scope miss is possible. Only the `scope` key and `not_indexed_count` do. A file outside the derived scope gets the same "definitive" wording as a file that does not exist. That is a real gap, and I did not find a code path that closes it inside the empty-search note.
- **Staleness:** the freshness module (`clew/mcp_server/freshness.py`, `notices`, line 573) says a source change since build ("answers may describe code that no longer exists") rides on query replies. A file added after the build is therefore a miss the index cannot see, and a `data` notice is the only signal for it.
- **Conjunction or prose miss:** low confidence by design. The reply names what to change, so it is a retry, not an answer.

**Net:** a single-token empty result is a strong claim about the index's named corpora at build time, and it is only a claim about the repository when the `scope` block shows the path was covered. The reply's wording does not enforce that second check, so the caller has to do it.