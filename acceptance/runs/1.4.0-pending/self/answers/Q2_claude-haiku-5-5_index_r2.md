**Short answer:** an empty reply is not one signal. The reply carries several fields and wordings that separate "not in this index" from "not looked for there," and only the strong "definitive negative" wording is entitled to high confidence. I checked this by reading the source (`clew/mcp_server/emptiness.py`, `routing.py`, `query/subject.py`). I did not run an empty query against a deliberately gapped index, so the behaviour below is what the code says it does, not something I observed.

**What separates the two readings**

| Signal in the reply | Meaning |
|---|---|
| `target` | Which database answered. A negative covers that index only. |
| `not_searched` | Other parts of a split repo that were not read. Empty for a whole-repo answer. Unbuilt vendored parts are listed too, so a miss there is "more partial," not "definitive." |
| Unread corpora | `search` reads only some corpora. If the database holds a match in one it doesn't read, the reply says "NOT DEFINITIVE" and names that kind. |
| Multi-token miss | Every token must match in one unit. The reply names the token that emptied the query. |
| Dossier kind gap | For kinds the subject surface doesn't describe (typedef, file), a miss is worded as a limitation, not a negative. Enums were fixed; the mechanism stays. |
| `staleness` | Present only when the index is older than its sources. |
| No database built | Not an empty reply. It is a refusal naming the target and the build to run. |

**Confidence each reading earns**

- **"Definitive negative" (strong):** the whole repository answered, no unread corpus holds the query, and the kind is one the surface describes. This is a claim about the index as built, within its scope. Excludes, vendored trees and untracked files are outside it. Trust it as "not in this index."
- **"NOT DEFINITIVE" / limitation wording:** the name may exist in a corpus or kind this surface doesn't read. Use `dossier` on the name or query another corpus before concluding anything.
- **Sub-index answer with `not_searched` non-empty:** a negative covers that part only. Check the listed parts before concluding the symbol is absent from the repository.
- **Stale index:** the symbol may postdate the last build. Refresh before trusting absence.

**Practical rule:** on an empty answer, check `target`, `not_searched` and whether the wording says "definitive." If it doesn't, treat the miss as unknown and fall back to grep or a source read. The code deliberately keeps only one "absent corpus" downgrade, so a missing layer alone doesn't turn every reply into a hedge. That means an empty answer on an index missing a layer can still read as definitive.