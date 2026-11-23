**Short answer:** an empty reply is not one signal. Its fields say which corpora were read, which file types were never indexed, and which repository answered. Confidence attaches to the scope the reply states, not to the repository as a whole.

I ran one nonsense token against the default `symbols` corpus and against `prose` to check the shape. Both came back empty, and each says what it covered.

**What the reply says when it did look**

- The `note` says the empty result "IS a definitive empty result from the database, NOT an error and NOT a malformed call," and tells you not to retry.
- It names what was searched: names, `@brief`s, macros, typedefs, enums, classes, config symbols, and file docs.
- It also names what was not searched: markdown and Kconfig prose (`corpus='prose'`) and function bodies (`corpus='code'`).
- `scope` gives `file_count` (426), `top_levels`, the `extensions` covered, and `not_indexed`, which lists extensions the index never read (`.rs=2`, `.toml=2`, `.sql=1`, no-extension files, and others).
- `target` names the repository that answered.
- In the `prose` reply, `token_hits` shows per-token counts, so in a multi-token miss you can see which token emptied it.

**What the reply says when it did not look**

- The `not_indexed` list is the "never looked" channel. A Rust or TOML symbol will return zero rows here for a reason unrelated to whether it exists.
- The corpus note is the second channel. A conceptual phrase that misses in `symbols` may still land in `prose`, and a literal may only appear in `code`.
- Files outside the index (Makefile, CI config) are not searched at all. AGENTS.md says to read the source for those.
- `staleness` appears only when the index is stale. Its absence means the index is current. I did not reproduce a stale or multi-token case, so I can't show its exact wording.

**Confidence each answer is entitled to**

| Claim | Entitled confidence |
|---|---|
| No symbol with this name or brief exists in the indexed files of the listed extensions | High. The database was queried in full. |
| No prose or code mentions the concept or literal | Unknown until you run that corpus. |
| The repository does not contain it | Not established. The reply itself rules this out when `not_indexed` lists extensions that could hold it. |
| The name is absent from a non-indexed file type | None. That file type was never read. |

So the reply supports "not in the indexed symbols of these file types, in this target." It does not support "not in the repository." To close the gap, run `corpus='prose'` and `corpus='code'`, and read the source for any unindexed extension that could plausibly hold the name.