A zero-row reply does not settle the question by itself. It carries enough fields to tell the two cases apart, but only if you read them.

**What the empty reply says.** My probe for a made-up name returned `count: 0` and `results: []`. The `note` field says outright that this is "NOT an error" and "NOT a definitive negative either." The reply then gives the evidence for each reading:

| Field | What it tells you |
|---|---|
| `token_hits` | Per-token counts. Here both tokens were 0. Matching is a conjunction, so a multi-token miss may be caused by one token alone. |
| `scope` | What was indexed: 426 files, `top_levels`, the `extensions` covered, and `not_indexed` (14 kinds, including `.rs`, `.toml`, `.sql`, `.csv`, and extensionless files). |
| `note` (searched) | Names and `@brief` for functions, variables, macros, typedefs, enums, classes/structs/unions, config symbols, and file docs. |
| `note` (not searched) | Markdown and Kconfig prose. That needs `search(corpus='prose')`. |
| `target` | Which repository answered. A wrong target gives a false negative. |
| `staleness` | Present only if the index is stale. Absence means it is current. |

**Confidence each answer earns**

| Situation | What a miss means | Confidence |
|---|---|---|
| Symbol-layer miss, `target` is the right repo, no `staleness`, the name's kind is in `scope`, prose also empty | Not defined under that name in the indexed symbol layer | High, within `scope` |
| Single-token miss (the `token_hits` tell you which token emptied it) | Fairly reliable, since there is no conjunction to blame | Moderate to high |
| Multi-token miss | One token may have caused it. Retry with the most distinctive single token | Low until retried |
| Only the prose corpus would hold it (docs, Kconfig help) | Not searched by default | None until `corpus='prose'` is run |
| File type in `not_indexed`, or outside the repo (Makefile, CI config) | Not indexed at all | None. Read the file directly |
| `staleness` present | Built before the current source, so newer symbols may be missing | None until `index(action='refresh')` |
| Wrong or unexpected `target` | Searched a different repository | None until the target is checked |

**How I'd act on an empty reply:**
1. Check `token_hits` and retry with one distinctive token.
2. Run `search(corpus='prose')` if the term could be documentation.
3. Check `scope` to see whether the file type is indexed at all.
4. Check `target` and `staleness`.

Only after those steps should you conclude "this repository does not contain that," and then only "not in the indexed symbol layer, within `scope`." Name spelling is a separate gap: the index cannot tell you how one name is spelled for different consumers.