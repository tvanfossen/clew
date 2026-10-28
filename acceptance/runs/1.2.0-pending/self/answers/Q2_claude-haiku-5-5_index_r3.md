The reply does not give a single yes/no. It reports where it looked and what it did not look at, and the confidence you can place in the empty result depends on those fields. I ran a deliberately nonsense query to see the shape. It returned `count: 0`, `results: []`, and:

- **`note`**: "NOT an error and NOT a malformed call, and it is NOT a definitive negative either." It also says which corpora were searched (names and `@brief` of functions, variables, macros, typedefs, enums, classes, config symbols, file docs) and which were not (markdown and Kconfig prose, which need `corpus='prose'`).
- **`token_hits`**: per-token counts. Matching is a conjunction, so a multi-word miss can be caused by one token. Here both tokens were 0, and the note says to retry without them.
- **`scope`**: `source: whole-repo`, 426 indexed files, the extensions covered, and `not_indexed` with counts (for example `.rs=2`, `.sql=1`, and 14 kinds in total). Files of those types are invisible to every query.
- **`target`**: the repository that answered. A wrong target produces a clean-looking miss.

Where the reply can say "not looked", it uses `not_searched` (split indexes, reported by dossier and search) and the `not_indexed` list. I did not see `not_searched` in this whole-repo reply, so it was not triggered here.

How much confidence each answer deserves:

| Empty result situation | Confidence it is a real absence |
|---|---|
| Symbol corpus, whole-repo scope, `target` is the repo you meant, the file type is in the covered extensions, `token_hits` all zero | **Reasonably strong.** Still a negative only for symbols that were parsed and indexed. |
| Same query, but the term is conceptual or lives in docs or Kconfig help | **Weak.** Re-run with `corpus='prose'` before concluding anything. |
| The thing is in a file type listed under `not_indexed`, or in a Makefile, CI config, or other non-indexed file | **None.** The index never saw it. Use Grep or Read. |
| `target` is not the repository you intended, or `staleness` is present | **None until fixed.** The miss may be against the wrong or outdated tree. |
| A multi-token query misses but one token has hits | **Not a miss.** Retry with the token that has hits. |

So the index can give you a confident "not in the symbol index of this repo, for these extensions." It cannot give you "not in the repo." The fields that separate the two cases are `scope.not_indexed`, `token_hits`, `target`, and the `note`'s list of what was not searched. Read those before treating an empty result as a negative.