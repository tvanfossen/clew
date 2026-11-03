**Short answer:** an empty reply is never reported as a bare "not there." It comes back with a grade. The reply says what was searched, what was not, and how much a zero is worth. I ran one probe with a nonsense name to see the shape.

**What an empty reply contains**

- `count: 0` and `results: []`, plus a `note` that says the zero is "NOT an error and NOT a malformed call, and it is NOT a definitive negative either."
- `token_hits`, which gives a per-token count. Matching is a conjunction, so one token with zero hits empties the whole query. The note names the culprit and says "RETRY WITHOUT THEM."
- A `scope` block: `source`, `file_count` (426 in this repo), `top_levels`, the indexed `extensions`, and `not_indexed` (extensions the index never read, such as `.rs`, `.toml`, `.sql`, `.csv`, extensionless files, and `.lock`).
- A `note` listing what was searched: names, `@brief` text, macros, typedefs, enums, classes, configured symbols and file docs.
- A `note` listing what was not searched: markdown and Kconfig prose, which needs `search(corpus='prose')`.
- `target`, which names the repository that answered. A `staleness` block appears only if the index is stale.

**How it separates "absent" from "not looked"**

| Signal in the reply | Meaning |
|---|---|
| `scope.not_indexed` and the `NOT searched` note | Place the search never reached: this is "did not look." |
| `token_hits` with a zero | Which token emptied the query. Retry with fewer tokens before concluding anything. |
| `target` and `not_searched` (on sub-index setups) | Which repository or part of a split index answered. |
| Missing `staleness` | The index is current. Its absence of a match is not stale. |
| The `note`'s "NOT a definitive negative" | The reply itself makes no absence claim. |

**Confidence each answer deserves**

- **"Not in the indexed symbol layer":** moderate, and only for the stated scope. This is a zero across names, `@brief`s, macros, types and file docs of the 426 indexed files, with no staleness flag. It does not cover function bodies or comments beyond `@brief`.
- **"Not in this repository":** not entitled to that. It also needs a prose search, a check of the extensions in `not_indexed`, and a sub-index check where one applies. Only then does the zero cover the places the name could live.
- **"Multi-token miss":** not evidence of absence for the whole phrase. Retry with the token that had zero hits removed, as the note instructs.
- **Anything in `not_indexed`:** unknown to the index. Fall back to reading the source.

The rule to apply is the one in this repo's AGENTS.md: an empty result means "we looked and found nothing," and that claim is only as wide as the `scope` block. Read the scope before you read the zero.