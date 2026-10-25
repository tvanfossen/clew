**Short answer:** an empty reply is not one signal. It carries a `note` and a `scope` block that tell you what was searched and what wasn't. Absence among the searched symbols is fairly strong. Absence from the repo as a whole is weaker, because some of the repo was never indexed.

I ran one probe with a nonsense token to see the real shape. The reply had `count: 0`, `results: []`, and these fields:

| Field | What it tells you |
|---|---|
| `note` | Says whether the empty result is definitive. Here it said "a definitive empty result from the database, NOT an error," and listed what was searched and what was not. |
| `note` (searched) | Names, `@brief`s of functions, variables, macros, typedefs, enums, enum values, macro expansions, classes/structs/unions, the config symbols the repo gates on, and file docs. |
| `note` (not searched) | Markdown and Kconfig prose. Those live in `search(corpus='prose')`, where conceptual phrases often match. |
| `scope` | Whole-repo, 426 indexed files, top levels, indexed extensions (`.c .cpp .h .json .md .py .yaml`), and `not_indexed` extensions with counts (`.rs`, `.toml`, `.sql`, `.csv`, `.jsonl`, `.lock`, `.motor`, extensionless files). |
| `target` | The repository that answered. A miss against the wrong repo means nothing. |
| `staleness` | Absent here, which means the index is current. If the index were stale, the block would appear on this reply. |

**How the two cases are told apart**

- **"Not in the place it lives":** the reply names the places it did not read (prose, Kconfig prose, unindexed extensions) and the scope it did read. For a conceptual phrase, the right move is the prose corpus, not a retry of the same symbol query. The tool text also says a multi-token miss names the token that emptied it. I did not exercise that case.
- **"Does not contain it":** the reply is a database-level empty result over the searched corpora. The `note` says not to retry the same query.

**How much confidence each answer deserves**

- **High:** no indexed symbol with that name or brief exists in the 426 indexed files, in the indexed extensions, for the named `target`, with no `staleness` block.
- **Medium-low:** the repo does not contain the thing at all. Unindexed extensions (for example `.rs` and `.toml`), unindexed files (the tool says a Makefile or CI config is outside the index), and prose are all outside the symbol search. Conceptual or config-level facts can exist and still miss.
- **Not established:** anything about the index being current, if `staleness` were absent but the index was built from an older declaration. The reply does not cover that case, so treat it as unknown.

**Practical sequence after an empty result:** confirm `target`, check the `not_searched` and `scope` lists, run `search(corpus='prose')` for conceptual terms, and only then conclude absence. For anything outside the index, read the source directly with the repo's own tools. This session has no shell or file access, so I could not do that here.