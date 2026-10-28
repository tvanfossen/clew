The reply separates the two cases by naming what it read, not by saying "no results." An empty `search` reply is never a bare "not found." It carries a `note`, a `scope` block, and `token_hits`, and together these say where the search did and did not look.

**What the reply shows**

- **Where it looked:** `scope` gives `source: whole-repo`, the file count (426 here), the extensions indexed, and the top-level directories covered.
- **What it did not read:** `scope.not_indexed` lists extensions that exist in the tree but were never indexed. Here that is `.rs=2`, `.toml=2`, `.lock=1`, `.sql=1`, `.csv=3`, and files with no extension. Also listed are `.motor` and `.jsonl`, and `not_indexed_count` is 14.
- **Which corpora were searched:** the `note` says names, `@brief` text, macros, typedefs, enums, classes, config symbols and file docs were searched. It also says markdown and Kconfig prose were not, and names `search(corpus='prose')` as the next place to look.
- **Which token emptied it:** `token_hits` gives the per-token count. Here both tokens were 0, so either alone empties the conjunction. When each token hits on its own but the pair does not, the reply says the combination is absent rather than either word.
- **Its own verdict:** the `note` explicitly says the result is "NOT an error" and "NOT a definitive negative either", and advises a retry without the emptying tokens.

**How much confidence each answer deserves**

| Claim | Entitled confidence |
|---|---|
| No indexed symbol, brief, macro, type or file doc matches all the tokens | High, for the searched corpus only |
| Each token is absent from those units (token_hits = 0) | High for that corpus. The token may still exist in prose, comments not captured in a brief, or other layers |
| The repository does not contain the thing | Low. The text may sit in a `not_indexed` extension (e.g. `.rs`, `.toml`, `.sql`), in a Makefile or CI config (outside the index by design, per the MCP instructions), or in markdown/Kconfig prose |
| The name is absent from a sub-index | Not established unless `not_searched` is absent. Split repositories name unread parts there |

So a zero from `search` licenses "no indexed code symbol by this name." It does not license "the repository does not contain it." The next step is to run `search(corpus='prose')` and retry with fewer tokens, then fall back to Grep for the `not_indexed` extensions. I checked the empty-result reply directly on this repo with a nonsense probe. The `src/` path I tried for a Grep fallback does not exist here, so I did not run that fallback.