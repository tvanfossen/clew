The reply separates the two cases by grading its own empty result. It does not report a flat "no results." The grading lives in `clew/mcp_server/emptiness.py`, and I read it from the code without running a query or the tests.

**What the reply carries when a search is empty**

- **A scope block (`scope` key).** This states what the index covers: file count, whether the scope was declared or derived from the whole repo, the extensions and top-level directories, and excludes. `not_indexed` appears only if the build recorded that report. An absent key means "not recorded," not "nothing was missed." Scope is the only part of the reply that says where the search could have looked, so it's the first thing to read.
- **A verdict sentence.** Its wording depends on what was checked:

| Condition | Wording |
|---|---|
| Single token, no match in any corpus `search` skips, file-docs corpus present | `_DEFINITIVE`: "This IS a definitive empty result… Do not retry" |
| Single token, but a match exists in a corpus `search` does not read | `_UNREAD_CORPUS`: "NOT DEFINITIVE… this index HOLDS matching rows that search does not read: {n} {kind}" with the hit counts also in `unsearched_corpus_hits` |
| Single token, file-docs corpus absent | `_NO_FILE_DOCS`: "NOT definitive… rebuild" |
| Multi-token | Conjunction note naming the token that emptied the match, with per-token counts in `token_hits` |
| `search(corpus='prose')` with the token in symbols | `_PROSE_ELSEWHERE`: "NOT DEFINITIVE… this repository DOES use these terms" |
| `search(corpus='prose')` with no markdown corpus | `_NO_PROSE_CORPUS`: "NOT definitive" |

The "definitive" claim is made only after the database has been asked whether any unread corpus holds the token (`q.unsearched_corpora`). Comments in the code record that an earlier version used the strong wording without this check and was wrong four times.

**How much confidence each answer deserves**

- **"Definitive, nothing in the index."** This is the strongest claim the reply makes, and it is still bounded. It means no kind of row the index holds matched. It does not mean the repository lacks the name. A file outside the declared or derived scope, or matching an exclude, produces the same empty result, and only the scope block shows that. Treat it as "not in the indexed scope," then check `scope` before trusting it.
- **"Not definitive, but present elsewhere."** This is a finding about location, not existence. The name is in the index under a corpus this search didn't read. Ask `dossier` by name, or `search(corpus='symbols')`.
- **"Not definitive, no corpus."** The index can't look at that layer, so it can't report a negative. Rebuild, or use the other corpus.
- **Known gap.** A layer that was never built does not downgrade a single-token verdict. The code says this was tried and reverted, because most indexes lacking a layer were built without one and the hedge would fire on nearly every reply. The file-docs check is the one exception. For layer state, `graph_stats.layer_states` distinguishes `absent` from `empty`, so an older index can still yield a "definitive" note and be wrong about a layer it never built.

**Short version:** a definitive empty result means "nothing in the indexed scope, across every corpus this build recorded." Anything wider needs the scope block, and anything the index can't check is labeled as not definitive.