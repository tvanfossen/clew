The reply separates the two cases by what it tells you to do next, and the two empty results I just ran show the difference.

**What an empty reply says**

- **Symbol corpus (the default).** The reply says "This is NOT an error... and it is NOT a definitive negative either." It lists what was searched: function, variable, macro, typedef, enum, and class names and briefs, macro expansions, config symbols, and file docs. It lists what was not searched: markdown and Kconfig prose. It also gives `scope` (426 files, whole repo, with extensions and `not_indexed` counts) and `token_hits`, which name the token that emptied the conjunction. The advice is to retry without that token, or switch corpus.
- **Prose corpus.** The reply says "This IS a definitive empty result from the database... Do not retry." That is a firm negative, but only for the markdown and prose text of this target.
- **Where it looked.** Every reply carries `target`, the repo that answered. A split repo adds `sub_index` and `not_searched`, naming parts that were not read. This repo is not split, so neither key appeared.

**How much confidence each answer gets**

| Empty result | What it licenses |
|---|---|
| Symbol corpus, one token has zero hits | Almost none. The name may be spelled differently, live in prose, or sit in a non-indexed file type. Retry with the distinctive token alone. |
| Symbol corpus, both tokens zero | Weak. Nothing indexed as a symbol matches, but the reply itself says this is not definitive. |
| Prose corpus, zero hits | Strong for markdown in this target. Says nothing about code. |
| Both corpora empty, `target` correct, no `staleness`, no `not_searched` | Reasonable evidence the indexed repo lacks the name. Still check the gaps before concluding absence. |

**Gaps that can produce a false "not here"**

- **Unindexed extensions.** The index covers `.c`, `.cpp`, `.h`, `.json`, `.md`, `.py`, `.yaml`. Here `.rs`, `.toml`, `.sql`, `.csv`, `.lock`, and extensionless files are excluded (14 kinds in total). A Makefile, CI config, or Rust file never reaches the index.
- **Stale data.** A `staleness` block appears only when the index is older than the source. Its absence means the index is current.
- **Other sub-indexes.** Any `not_searched` entry is a part the query never read.

So a clean symbol miss means "not among the indexed symbols," not "not in the repository." Before concluding absence, confirm with Grep over the gap areas: prose, the unindexed extensions, and any `not_searched` parts. The index is intended to point you at the file. It cannot settle what lies outside its file set.