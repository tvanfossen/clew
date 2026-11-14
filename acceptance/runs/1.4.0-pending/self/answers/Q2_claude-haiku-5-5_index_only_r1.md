The reply is built to refuse a flat "not found." An empty result is explicitly labelled as neither an error nor a definitive negative. I checked this with a nonsense probe against this repo (`zzqxnonexistentsymbol frobnicate`). It returned `count: 0`, `results: []`, and a `note` saying the empty result is not a malformed call and not a definitive negative. It also returned `token_hits` showing each token matched 0 times, and a `scope` block describing what was covered.

**How the reply separates "absent" from "not looked"**

| Signal in the reply | What it tells you |
|---|---|
| `token_hits` (per token) | Matching is a conjunction. If every token has hits but the whole query is empty, the miss is a query-shape problem, and the note says to retry with fewer tokens. |
| `note`: "Searched: …" / "NOT searched: …" | Lists which corpora were covered: names, `@brief`s, macros, typedefs, enums, classes, config symbols, file docs. It says prose (markdown, Kconfig) and function bodies were not searched, and points to `corpus='prose'` or `corpus='code'`. |
| `scope` (`file_count`, `extensions`, `not_indexed`) | The files that were actually read, and the extensions that were never parsed. Here `.rs`, `.toml`, `.csv`, `.sql`, `.lock`, `.jsonl`, `.motor` and extensionless files are not indexed. A symbol living there is invisible to a symbol search. |
| `target` | Which repository answered. A search can be correct for the wrong repo. |
| `not_searched` | Parts of a split repository (sub-indexes) that were not read. Absent in the probe because this repo is not split. |
| `index(status)`: `stale`, `source_changed_files`, `matches_source` | Whether the index reflects the source. This repo reported fresh: `stale: false`, 0 changed files, matching fingerprints. |
| `coverage` (barren/undocumented files) | Files that were parsed but yielded no symbols. Here 15 barren files, mostly YAML question files and `requirements.yaml`. |

**How much confidence each answer gets**

- **Strongest "not in this repo":** a distinctive name returns 0 on all corpora (symbols, `prose`, `code`). The index is fresh, the file type is in `scope` and not in `not_indexed`, and the `target` is the repo you meant. This is good evidence for an indexed-language identifier, but the tool's own wording still says it is not definitive.
- **Weak, probably a "did not look":** the note lists an unsearched corpus that the name could live in (a prose or Kconfig phrase, a literal inside a body), or the likely file type is in `not_indexed`, or the index is stale, or the `target` is not the repo you meant.
- **Retry, not a conclusion:** `token_hits` shows an individual token has 0 hits, or every token hits but the conjunction is empty. The tool says to drop tokens and retry.

**Caveats from this check**

- I ran only a nonsense probe. That confirms the reply shape, not the answer for any real name in this repo.
- The counts disagree. `search` reports 426 files in scope, while `index(status)` reports 435 files in scope and 397 indexed. I did not resolve this from the index alone; it may be the difference between scope and parsed files, but it is unverified.