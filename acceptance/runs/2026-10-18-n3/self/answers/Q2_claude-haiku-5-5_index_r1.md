The reply separates the two cases by naming what it read, not by a yes/no flag. I ran two empty queries to confirm the shape.

**What a symbol-corpus miss says.** The `note` states that the result is "a definitive empty result from the database", and then lists what was searched: names and `@brief` of functions, variables, macros, typedefs, enums, classes, and structs, plus macro expansions, the config symbols the repo gates on, and file docs. It also lists what was not: "markdown or Kconfig prose". The `scope` block gives the file count (426), the extensions covered, and `not_indexed` (`.rs`, `.toml`, `.sql`, `.lock`, extensionless files, and others, 14 in total). The `target` names the repo that answered.

**What a prose-corpus miss says.** The reply is thinner. It says "definitive" and gives `token_hits` per token, but it has no `scope` or `not_searched` block. You have to know that prose means markdown only.

**Confidence in each answer:**

| Reply | What it licenses |
|---|---|
| Empty, `target` is the repo you meant, no `staleness` block | Strong: the name is not a symbol of those kinds in the indexed files. |
| Empty, but the name lives in an unindexed extension or in prose | Nothing. Check `not_searched`/`scope` and read the files directly (e.g. Makefile, CI config, `.toml`, `.rs`). |
| Empty, `staleness` block present | Weak until refreshed. A `data` axis means the index is older than source. |
| Empty from the wrong `target`, or a split repo with `sub_index` not searched | Nothing about this repo. |

Two limits remain even on a clean empty result. The tool cannot see how a name is spelled differently for another consumer, such as a Python binding or a generated header. It also cannot see anything outside the indexed file set.

**What I did not check.** The tool description says a multi-token miss names the token that emptied the query, and that matching is a conjunction across one searchable unit. I did not test that with a multi-token query, so treat it as documented, not verified here.

**Practical rule:** an empty symbol search means "not a symbol in these 426 files". Before saying "this repo does not have X", check the `scope`, run the prose corpus if the name might appear in docs, and grep the unindexed file types. Only then state absence.