**Short answer:** the reply separates the two cases by what it reports about the index, not by one sentence. A zero-row answer is "definitive" only after the code has checked that no unread corpus holds a match and that the file-docs corpus exists. Even then, the confidence covers only names and `@brief` text within this build's scope. I answered from reading the source. I did not run a live query against an index.

**How the reply tells the cases apart**

Every empty `search` carries a `scope` block (`clew/mcp_server/emptiness.py`, `_scope_payload`). It says how many files were indexed, whether the scope was `declared` or `whole-repo`, and the top-level directories and extensions. That lets a caller see whether the miss could be a scope miss at all.

Two further checks decide the verdict:

- **Unread corpora.** `q.unsearched_corpora` (`clew/query/symbols.py:1806`) takes the kinds the database holds, subtracts the kinds `search` reads, and counts matching names in what remains. Any hit replaces the verdict with "NOT DEFINITIVE — this index HOLDS matching rows that search does not read" and names them, with `unsearched_corpus_hits` in the payload. This check outranks everything else.
- **File docs.** A single-token miss gets the strong "definitive" wording only if the `file_docs` table exists (`has_file_docs`). Otherwise it gets "NOT definitive; rebuild".

Multi-token misses are treated as conjunctions. The reply gives per-token counts in `token_hits`. If a token matches nothing alone, it says to retry without that token. If every token matches alone, it says to use fewer tokens.

`not_indexed` and `not_indexed_count` are a separate claim (`clew/cli.py:2646`, `_not_indexed_scope`). At build time, the code compares the files the build walked against the `path` rows of type 1 and groups the gaps by extension. These keys appear only when something was missed. If the build never measured, the keys are omitted rather than set to empty, so "nothing missed" and "nobody checked" read differently.

**How much confidence each answer earns**

| Reply | What it entitles you to |
|---|---|
| "definitive", no unread hits, file docs present | No indexed name or `@brief` in the searched kinds matches. Strong, but limited to this build's scope and to names and briefs, not bodies or prose. |
| "NOT definitive", unread-corpus hits | The query has a real match in another corpus. The negative is false. Ask for that name with `dossier`. |
| "NOT definitive", conjunction | No claim about the repo. Retry with the dead tokens removed. |
| "NOT definitive", no file docs | No claim. Rebuild, or use the prose corpus. |
| `not_indexed` present | Files exist in the tree but were not indexed by file type. Read them directly. |
| `not_indexed` absent | Either nothing was missed or the build did not measure. The reply cannot tell these apart beyond the rule above. |

**Limits on these answers**

- Everything is measured at build time. The query never looks at the working tree, so an index built before later edits can be wrong in either direction.
- As I read `_not_indexed_scope`, it compares only files the build walked. Files excluded by scope before the walk should not appear in `not_indexed`, so the scope block is the only signal for them. I did not confirm this against a real build.
- The "definitive" wording is about names and briefs only. A symbol whose name differs from the query, or whose documentation does not contain the term, is missed without any flag.

A `PostToolUse` hook suggested calling `dossier`. I have no index tool in this session, so I answered from the source.