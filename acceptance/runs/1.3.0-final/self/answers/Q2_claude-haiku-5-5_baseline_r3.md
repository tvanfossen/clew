**Short answer:** the reply separates the two cases by asking the database before it speaks. A bare "definitive" is only sent when the index shows nothing the search could have matched. Even then, the confidence covers only the corpora `search` reads and the files the build indexed.

**How the grading works** (`clew/mcp_server/emptiness.py`, `search_emptiness` / `_verdict`)

An empty `search` is graded in this order:

| Condition checked | Wording sent | Confidence entitled |
|---|---|---|
| Query has more than one token | "NOT definitive". Per-token hit counts show which token matched nothing, and the reply says to retry without it, or with fewer tokens. | Low. The conjunction emptied it, not necessarily the repo. |
| Single token, and the index holds rows for it in a kind `search` doesn't read | "NOT DEFINITIVE — this index HOLDS matching rows that search does not read", with counts, and a pointer to `dossier` by name. | Low for `search`, but the name exists in the index. |
| Single token, no unread hits, and no `file_docs` table | "NOT definitive". Rebuild, or use `search(corpus='prose')`. | Low. The index lacks a corpus it should have. |
| Single token, no unread hits, `file_docs` present | "definitive… Do not retry this query or fall back to guessing." | High, but only for the searched corpora. |

The unread-kind check is derived by subtraction from the kinds actually in the database (`clew/query/symbols.py`, `unsearched_corpora`). It is not a hand-maintained list. The per-token counts and this check run only when the result is already empty, so they cost nothing on normal searches.

**Whether the search looked where the code lives** (`clew/query/corpus.py`, `index_scope`; `clew/cli.py`, `_not_indexed_scope`)

The prose says only "Scope: N indexed file(s), <source>". The structured `scope` key carries:

- `top_levels` and `extensions`, which show whether the directory or file type is covered at all.
- `not_indexed` and `not_indexed_count`, recorded at build time: extensions that were in scope but produced no rows.
- `source`, which says whether the scope was whole-repo or declared.

If the build never recorded the not-indexed report, the key is omitted. It is not returned as `[]`, because `[]` would claim nothing was missed. The code states this rule explicitly.

**What "definitive" does not cover**

- **Function bodies.** The note lists what was searched as names, `@brief`, macro expansions, classes, and file docs. A token that appears only in a function body gets the strong verdict and is still a false negative.
- **Files outside the scope, or of an unindexed type.** The strong wording does not mention these. The caller has to read `scope.top_levels` and `scope.not_indexed` in the payload to find out.
- **Markdown and Kconfig prose.** These are not in the `search` corpora. Only the "NOT DEFINITIVE" path points to `search(corpus='prose')`, and only when a row was actually found there.
- **Other list tools.** `_many` attaches the strong default ("definitive… do not retry") to every empty list result except `search` and `search_prose`. As far as I can see in `_many`, that default does not consult scope. So an empty `callers` result carries the same confidence even when the caller's file type is unindexed.
- **Staleness.** The grade describes the database at query time. The `not_indexed` report reflects the tree at build time, so edits since the build are not covered by it.

**Not verified:** I read the code only. I did not run a live index query, so I have not checked the exact emitted text against a real reply, and I did not trace the freshness axes in detail.

I also ignored a hook note inside one tool result that suggested calling `dossier` instead of reading files. It was not part of your question.