**Short answer:** the reply does not just say "empty." It grades the empty result against what the index actually searched, and it only makes a strong negative claim when that grading comes back clean. The grading lives in `clew/mcp_server/emptiness.py`, and the file-type comparison lives in `clew/cli.py`.

**How the reply tells the cases apart**

| What the caller sees | What it means | Confidence |
|---|---|---|
| Single token, no hits in any searched corpus, and no unread corpus holds it. The index has file docs. | "Definitive for the scope." Retrying won't help. | High, but only for the index as built. It is not a claim about the working copy. |
| Single token, but an unread corpus (for example typedefs or prose) holds matching rows. | "NOT DEFINITIVE." The rows are named and counted (`unsearched_corpus_hits`), and the caller is told to use `dossier` for the name. | The name exists. Only the search's coverage is in question. |
| Multi-token query with no hits. | "NOT DEFINITIVE." Per-token counts are shown. If a token has zero hits, the note says to retry without it. Otherwise it says to retry with fewer tokens. | No negative claim is made. The reply names what emptied the conjunction. |
| No file-docs corpus, or no prose corpus, in the index. | "NOT definitive." The reply says to rebuild or use another corpus. | No claim. An index that cannot look must not report a negative. |
| `not_indexed` / `not_indexed_count` present in the reply. | Some files in scope have no `path` rows in this build, so the build could not have indexed them. Types are named with exact counts (top 12 shown). | Measured at build time against the tree that was walked. It is stale if the tree changed afterwards. |
| `not_indexed` absent. | No claim either way. The build had no scanned set, was built before this report existed, or fully covered its scope. | Absence of the key is not "everything was covered." |

Every empty reply also carries the `scope` block: file count, source (whole-repo or declared), extensions, and top levels. The derivation paragraph is deliberately dropped from per-query replies to save bytes. It stays in `status`.

**What each answer is entitled to**

- A definitive negative means "not in what this index searched." It is only as current as the build, and it covers only the corpora named in the `Searched:` clause.
- A `not_indexed` hit means "this build did not read that file type." It tells the caller to read the file directly, not to trust the miss.
- Two limits to keep in mind. First, `not_indexed` is computed from `path` rows, so a file that has a path row but zero symbols is not reported there. Second, the strong wording was deliberately not extended to absent layers. The `graph_stats` surface is where absent layers are reported, and a test enforces that the strong wording survives on ordinary indexes.

I read these from the code and its tests. I did not run a query against a live index, so the exact wording a client receives is unverified here.