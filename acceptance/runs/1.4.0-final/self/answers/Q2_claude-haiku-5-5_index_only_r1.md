**Short answer:** the reply separates the two cases by what it says about the places it read. Its confidence is strong for "no such name in the indexed symbol layer" and weak for "the repository does not contain it."

I checked this by searching for a made-up name, `zzqxnonexistentsymbol`, with both `search` and `dossier`. Both came back empty, and the replies show the distinction:

| Field | What it tells you |
|---|---|
| `count: 0` / `found: false` | The lookup ran and matched nothing. |
| `note` | Says the empty result is "definitive from the database, NOT an error." It also lists what was and was not searched. |
| `scope` (search only) | Gives the coverage: `source: whole-repo`, `file_count: 426`, `top_levels`, `extensions`, and `not_indexed`, which lists file kinds that were never read. |
| `target` | The repository that answered. Check it is the one you meant. |
| `staleness` | Present only when the index is stale. Its absence means the index is current. |
| `not_searched` | Documented for split indexes (`sub_index`). It did not appear here because this repo is not split. |

**What each answer is entitled to:**

- **"No symbol by that name" (high confidence).** The replies say this covers names, `@brief` text, macros, typedefs, enums, classes, config symbols and file docs, in the `target` repo, with no staleness block. This is a real negative within that scope.
- **"Not in the repo" (low confidence).** Several places are outside the search:
  - **Function bodies.** A literal, key or property is only found with `search(corpus='code')`.
  - **Prose.** Markdown and Kconfig prose need `search(corpus='prose')`, where a conceptual phrase often matches.
  - **Unindexed file kinds.** `scope.not_indexed` lists extensions that were never read: `.rs=2`, `.toml=2`, `.csv=3`, `.sql=1`, `.lock=1`, `.jsonl=1`, `.motor=1`, and 3 extensionless files. A miss in those is "never looked," not "absent," even though the note calls it definitive.

**Practical rule:** a miss is trustworthy only after you have checked `target`, confirmed no `staleness` block, and, for text-like questions, retried in the layer the note names (`code` or `prose`). Otherwise, treat it as "not in the symbol layer" and read the source for the rest.