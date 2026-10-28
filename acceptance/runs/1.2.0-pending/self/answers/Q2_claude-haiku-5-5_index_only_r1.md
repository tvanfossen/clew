The reply separates the two cases by describing what the search covered, not by a yes/no flag. I ran two probes with a nonsense name to see the shape. Both came back empty, and both were graded.

**What the reply says for a symbol search (`corpus='symbols'`, the default)**

- `note` says plainly that an empty result is "NOT an error" and "NOT a definitive negative."
- `token_hits` gives per-token counts. Matching is a conjunction, so a zero on one token tells you which token emptied the result. The reply then tells you to retry without it.
- `note` lists what was searched: names, `@brief` text, macros, typedefs, enums, classes, the config symbols the repo gates on, and file docs.
- It lists what was not searched: markdown and Kconfig prose, which need `corpus='prose'`.
- `scope` gives the coverage: `file_count`, the extensions held, and `not_indexed`, which names extensions with no grammar (here `.rs`, `.toml`, `.sql`, and extensionless files). That field is how you tell "not in the repo" from "not parsed."
- `target` names the repository that answered.

**What the `files` corpus says**

It states that the corpus holds indexed source files only. A build script, Doxyfile, or data file is absent by construction, and the reply says so. It points to `inventory` and `doc_scope` and tells you to re-glob or go to the shell.

**How much confidence each answer deserves**

| Empty result | What it licenses |
|---|---|
| Symbol search, every token zero, `scope` whole-repo | Moderate-to-high: no indexed symbol or brief carries that name in the 426 indexed files. It does not say the text is absent from bodies, comments, or prose. |
| Single token zero, others hit | Narrow: that token is absent from the searched fields. The conjunction is what emptied the result. |
| Prose corpus empty | Only the prose that was indexed. Conceptual phrases are the ones prose search catches. |
| Files corpus empty | Weak: it only means no indexed source file matches. Non-source files were never in scope. |
| Anything with an extension in `not_indexed`, a Makefile, CI config, or an unindexed vendored tree | None. The index never looked there, so it cannot say the thing is absent. |

The reply's signal is the difference between "searched and found nothing" and "this was never in reach." A zero with `scope` and `not_searched` naming the place where the thing would live is a gap, not an answer. In practice: the symbol result is a strong negative for named functions, variables, and types in indexed source, and a weak one for everything else. Confirm an absence in prose, build files, or unparsed extensions before concluding anything.