A symbol search that comes back empty does not, by itself, tell you whether the thing is missing. The reply is built to show you which places were covered, and you have to read that part before drawing a conclusion.

I ran a control query (`zqxwvnonexistenttoken`, `corpus='symbols'`). The reply had `count: 0` and a `note` that calls the result "a definitive empty result from the database, NOT an error." It then lists what was searched and what was not:

- **Searched:** names and `@brief` text of functions, variables, macros, typedefs, enums, enum values, macro expansions, classes/structs/unions, the config symbols the repo gates on, and file docs.
- **Not searched:** markdown and Kconfig prose (that is `corpus='prose'`) and function bodies (that is `corpus='code'`, which finds keys, literals and strings).
- **Scope:** `426` indexed files, `whole-repo`, with `top_levels`, `extensions` and a `not_indexed` breakdown. Every reply carries a `target`, and the `not_searched` field is present whenever a split index was skipped.

So the reply separates the two cases in three ways:

1. **Looked and found nothing.** The layer was read, and the reply says so by naming the corpus and the file count it covered.
2. **Did not look in that layer.** The `note` names the other corpora by name and points you to them.
3. **Never read at all.** The `scope.not_indexed` block lists extensions and counts that were never indexed. Here that is `.rs=2`, `.toml=2`, `.sql=1`, `.csv=3`, `.jsonl=1`, `.lock=1`, `.motor=1` and 3 extensionless files, 14 kinds in total. Those files are invisible to every corpus, so an empty answer about them means "unread," not "absent."

**How much confidence each answer deserves**

| Empty result means | Confidence |
|---|---|
| No symbol in the searched layer, in an indexed file, for this target | High. The reply calls it definitive. |
| Not in prose, or not in a function body | Not established. Re-query with `corpus='prose'` or `corpus='code'`. |
| In a file type listed under `not_indexed` | None. The file was never read. |
| Anything in a Makefile, CI config, or other file outside the index | None. The index cannot answer. |
| Anything in a part named in `not_searched` (split indexes) | None until that part is queried. |

The practical rule is to check `target`, `scope.not_indexed` and any `not_searched` before concluding that something does not exist. The index also treats absence and emptiness as different facts. A layer that ran and found nothing reports an empty result. A layer that never ran is missing from the reply, and the reply does not fill it in with zero.

My caveat: this check used one control query for a token that cannot exist. I did not test a real symbol in prose or a Rust/TOML file, so the table above is the documented contract, not something I have observed in every case.