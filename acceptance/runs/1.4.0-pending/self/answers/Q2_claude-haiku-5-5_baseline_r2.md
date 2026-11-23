**Short answer:** the reply separates the two cases by grading the empty result, not by reporting one flat "no rows" sentence. Only one grade earns the strong "definitive, do not retry" wording. Everything else says "not definitive" and names what to do next. I worked from the source, since the clew MCP tools are not in my toolset here.

**How the grading works** (`clew/mcp_server/emptiness.py`, `search_emptiness` and `_verdict`)

| Empty because… | Reply says | Confidence in a "no" |
|---|---|---|
| One token, no hits in any searched corpus, no hits in an unread corpus, `file_docs` present | `_DEFINITIVE`: "a definitive empty result… Do not retry" | High, but only for the indexed fields (below) |
| One token matches rows in a corpus `search` does not read (typedefs, enums, macros, etc.) | "NOT DEFINITIVE — this index HOLDS matching rows…", with kinds and counts; `unsearched_corpus_hits` in the payload | None for "not in repo". The rows exist. |
| Multi-token conjunction | Per-token counts (`token_hits`), naming dead tokens; "retry without them" or "retry with fewer tokens" | Low. It is a query-shape problem, not a repo fact. |
| No `file_docs` table | `_NO_FILE_DOCS`: "NOT definitive. Rebuild…" | None. The index could not have looked. |
| Prose search, no `supplementary_docs` | `_NO_PROSE_CORPUS` | None |

The unread-corpus check (`clew/query/symbols.py`, `unsearched_corpora`) is derived by subtraction. It takes the kinds actually present in the database minus the kinds `search` reads. So a new kind of symbol downgrades the verdict without an edit to the wording. The tests that pin this are in `tests/test_emptiness.py`, including `test_an_absent_symbol_keeps_the_definitive_note`, which is the control against hedging every answer.

**Where it looked: the scope block**

Every empty reply carries a `scope` payload (`_scope_payload`):
- file count and scope source (whole-repo or declared),
- the covered extensions and top-level directories, capped at 12 but checked uncapped in the grader,
- `not_indexed` and `not_indexed_count`: file types the build walked that hold no rows, by extension (`cli._not_indexed_scope`).

`not_indexed` is what separates "outside the declared scope" from "this build does not index that file type" from "not in the repo." When nothing was missed, or the build did not record it, both keys are dropped rather than set to empty. The code states this as the falsy-drop rule: an empty list would claim a measurement that never happened.

Layer-level absence (a layer that never ran versus one that ran empty) lives in `graph_stats.layer_states`, which reports `absent`, `empty` or `populated`. The search reply deliberately does not repeat this. A gate-layer downgrade was built and reverted (gh#393) because it would hedge nearly every reply.

**Limits on the strong claim**

- The single-token check is a case-insensitive substring match over symbol names, `@brief` text, macro expansions, class and file docs, and the other searched kinds. A token that appears only in function bodies or inline comments is invisible to it. The reply's own `_SEARCHED` string says "names + @brief", so the scope is disclosed, but the wording "the database records none" is broader than that.
- The claim is only as good as the index's freshness and scope. Stale or schema-old indexes are handled separately (`test_a_schema_stale_index_withdraws_the_definitive_claim`).

**Bottom line:** a single-token zero with the strong wording is good evidence that the indexed name and brief fields do not contain the token. A zero with any other wording is evidence about the query or the index, not about the repository. Check the `scope` and `not_indexed` fields before concluding "not in the repo."