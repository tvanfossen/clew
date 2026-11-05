The reply separates the two cases by what it searched, not by a single flag. I ran three empty queries against this repo to see the shapes.

**What an empty reply carries**

- **`note`**: the server's verdict on this specific miss. For a single-token symbol miss it says "a definitive empty result from the database," and it names the corpora it did not read: markdown and Kconfig prose, and function bodies. For a multi-token miss it instead says it is "NOT a definitive negative either" and lists per-token hits.
- **`scope`**: the covered shape. Here that is 426 files, whole-repo, with `top_levels`, the indexed `extensions`, and `not_indexed` with counts (`.rs=2`, `.toml=2`, `.csv=3`, `.sql=1`, no-extension=3, and others).
- **`target`**: the repository the answer came from. A miss against the wrong target is meaningless.
- **`token_hits`** (multi-token only): per-token counts, so you can see which word emptied the conjunction.
- **`staleness`**: absent here, which means the index is current. If it were stale, the block would appear on this reply.

**The three shapes**

| Query | Corpus | Reply says | Confidence it supports |
|---|---|---|---|
| `zzqx…` | symbols (default) | definitive for names, `@brief`, macros, typedefs, enums, classes, config symbols, file docs | High, but only for those things |
| `zzqx…` | `code` (bodies) | "definitive empty result" | Moderate: a literal absent from every indexed function body |
| `zzqx… missingtoken` | symbols | "NOT a definitive negative"; both tokens are 0 | None yet. Retry each token alone |

**How much each answer is worth**

- **"Not in the repo," high confidence:** a single-token miss in the right corpus, with `target` correct, no `staleness` block, and the file type inside `extensions`.
- **"Not in the symbols I searched":** a symbol-corpus miss does not rule out a string in a function body, in prose, or in a Kconfig help. Search `prose` or `code` before concluding anything.
- **"Not in function bodies":** this misses globals, initialisers, macros outside functions, and anything in an unindexed file type. Treat it as "no function body contains this."
- **Nothing at all:** anything in a `not_indexed` extension (a `.rs` or `.toml` file, say) was never looked at. The reply cannot say the thing is absent. Fall back to `Grep` or `Read` on those files.

The server's "definitive" wording is accurate relative to the scope the reply enumerates, not to the repository as a whole. The `scope` and `not searched` clauses are what cap the confidence. Read them before turning an empty result into a claim about the code.