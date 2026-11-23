The reply does not give one bare "no". It names the place it looked, and the wording of the empty result tells you how much to trust it. I checked this with two empty searches against this repo.

**What the reply tells you about where it looked**

- `target` names the repository that answered. Check it before anything else.
- `scope` gives the covered shape: `file_count` (426 here), `top_levels`, `extensions`, and `not_indexed` (file types the index skips, such as `.rs`, `.toml`, `.sql`, and extensionless files).
- `not_searched` and `sub_index` cover split indexes. A part that was not read is listed, not silently skipped.
- The `note` lists what was searched and what was not. For a symbol search it says prose and Kconfig text were not searched, and that function bodies need `corpus='code'`.

**The two empty results behave differently**

| Reply | What it says | Confidence |
|---|---|---|
| `corpus='symbols'`, 0 rows, multi-token query | "NOT a definitive negative." `token_hits` shows which tokens matched nothing. | Low. A conjunction miss says only that one token has no hit in names, `@brief`s, macros, types, or file docs. Retry with the single distinctive token, then try `prose` or `code`. |
| `corpus='code'`, 0 rows | "A definitive empty result from the database." | High, but bounded. It covers the function bodies of indexed files only, across the whole repo, and only for the extensions in `scope`. |

**How to read each answer**

- **"Not in this repository":** trust it only when `target` is the repo you meant, the file types where the thing would live appear in `scope.extensions`, and the search was over `code` or an unambiguous name. Otherwise the answer is "not in the indexed part of the repo."
- **"I did not look where it lives":** this is what `not_indexed`, `not_searched`, and the note's list of unsearched corpora mean. A Rust file, a TOML config, a Makefile, or CI YAML outside the indexed extensions is unreachable by the index. The server instructions say to read those files directly.
- **Symbol-name misses:** a name can be absent from the symbol layer yet present in a comment, a string, or a config file. That is why the reply points you to the other corpora.

The index's own rule is that an empty result must not be read as "nothing was missed." The fields that carry the coverage claim are the ones to check: `target`, `scope`, `not_searched`, and `token_hits`. The row count alone does not carry the claim.