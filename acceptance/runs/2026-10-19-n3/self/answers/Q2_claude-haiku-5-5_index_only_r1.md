**Short answer:** an empty reply is never just "zero rows." It carries a scope block, a list of what was not searched, and a note that says whether the emptiness is definitive. Confidence depends on whether the miss falls inside that scope.

I checked this against the live index with a nonsense token. Both empty replies said "This IS a definitive empty result from the database, NOT an error," and both named the `target` they searched.

**What the reply tells you**

| Field | What it tells you |
|---|---|
| `target` | Which repository answered. Check this first, since the wrong repo gives a false "not here." |
| `scope` (symbols) | The coverage: `file_count` (426 here), `top_levels`, `extensions` searched, and `not_indexed` with counts. |
| `note` (symbols) | Lists what was searched (names, `@brief`, macros, typedefs, enums, classes, config symbols, file docs) and what was not (markdown and Kconfig prose, which belong to `corpus='prose'`). |
| `token_hits` (prose) | Per-token counts for multi-word queries, so you can see which token emptied the match. |
| `not_searched` / `sub_index` | On split repositories, names any sub-index that was not read. |
| `staleness` | Present only if the index is older than the source. |

**How confident each answer is**

- **"Not in this repository" (high confidence):** the search covered the index's scope, the target is correct, the index is not stale, and the `note` says the result is definitive. That is a claim about the indexed file set, not the whole tree.
- **"I did not look where it lives" (the reply names it):**
  - The corpus. Symbols does not search prose, and prose does not search symbols. A conceptual phrase often lands only in prose.
  - The file types. Extensions listed under `not_indexed` (for example `.rs`, `.toml`, `.sql`, `.lock`, and extensionless files in this repo) were never read.
  - Things outside the indexed file set. The server's instructions say it cannot settle anything in a Makefile or a CI config.
  - Other parts of a split repository, which show up in `not_searched`.
- **Multi-token queries:** every token must appear in one searchable unit. A miss can mean the tokens sit in different places, not that the concept is absent. `token_hits` shows which token failed.
- **Spelling (low confidence):** a miss can also mean the name is spelled differently for another consumer, which the index cannot settle.
- **Stale index (lower confidence):** if `staleness` is present, the empty result reflects older source, so re-check after `index(action='refresh')`.

**Practical rule:** treat an empty result as "absent from the indexed symbols/prose of this target." Before concluding a thing does not exist, re-run against the other corpus (`prose`), check the scope's `not_indexed` extensions, and read the source directly for any path the index names as out of reach.