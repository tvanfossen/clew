The reply separates the two cases by grading the empty result, not by using one sentence for every empty result. The grading lives in `clew/mcp_server/emptiness.py`. I read the code and did not run a live query, so this is from source.

**What the reply says about the answer**

For a single-token `search` that returns nothing, `_verdict` picks one of three wordings:

| Condition | Wording | Entitled confidence |
|---|---|---|
| No unread corpus holds the name, and file docs were built | "This IS a definitive empty result from the database… Do not retry" | Strong, but only about the database and its searched corpora |
| An unread corpus holds matching rows | "NOT DEFINITIVE — this index HOLDS matching rows that search does not read: N kind" | None for the negative. The name exists; ask `dossier` for it |
| Index has no file-level docs corpus | "NOT definitive… Rebuild with index(action='refresh')" | None. The index could not have looked |

For multi-token queries the reply is never definitive. It names each token with zero independent hits and says to retry without it, or with fewer tokens. The `search(corpus='prose')` path grades the same way: "definitive" only when the symbol corpora also hold nothing for the token.

**How the reply shows where it looked**

Every empty reply carries a `scope` block (file count, whole-repo vs. declared source, extensions, top levels). It also carries `not_indexed` and its count, but only when the build recorded that report. An unrecorded report is dropped rather than shown as `[]`. A "Searched:" line lists the symbol kinds read and says markdown and Kconfig prose were not searched.

The envelope has a `target` naming the repository answered from, and `sub_index` and `not_searched` in `Answering` (`clew/mcp_server/state.py:296`). On a split repository, a negative from one part lists the sibling parts it did not read, including parts that are known but not yet built (`clew/mcp_server/routing.py:125`). `status` adds a `staleness` block only when the index is stale.

**How much confidence each answer deserves**

- **"Definitive" from a single-token search** is the strongest the reply will say. It means the token is absent from every corpus `search` reads, the file docs corpus exists, and the name is not in an unread corpus. It does not mean the repository lacks the name. Four things still limit it: files outside the indexed scope, a stale index, a detector that is blind to a construct, and a layer that is absent rather than empty. The vocabulary comment in `clew/vocabulary.py:954` gives the blind-detector case: mbedtls's accessors are macros and the detector recorded zero rows.
- **"Empty" with `not_searched` non-empty** is a negative about one part only. The server description (`clew/mcp_server/server.py:483`) says to check `target` and `not_searched` before concluding a symbol does not exist.
- **"Not definitive" wording** is a deliberate downgrade. It says the search is not an error and not a malformed call, and that the caller should look elsewhere before concluding absence.

**Gaps in the design**

The reply can only say "I did not look there" for places the code names: unread corpora, out-of-scope files, unbuilt sibling parts, stale indexes, and absent corpora. A detector blind spot that is not recorded, such as a macro-generated symbol with no rows, shows up as a plain strong negative. The code's own rule is "fix the corpus, not the sentence about the corpus," which means a detector gap is not hedged in the wording.